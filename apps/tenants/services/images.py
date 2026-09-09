"""Service de traitement et d'optimisation haute fidélité des logos d'entreprise.

Ce module adapte l'algorithme de réduction optique de logo24 pour l'environnement
serveur de CCD Digital :
  1. Sécurité : limitation anti-bombe de décompression (Pixel Floods) et allocation
     mémoire optimisée en float32.
  2. Détection du fond uniforme et mise en transparence douce (remove_uniform_background).
  3. Recadrage automatique sur le tracé réel (trim).
  4. Réduction optique de pointe :
     - Passage en lumière linéaire (compensation du gamma sRGB pour éviter les assombrissements).
     - Prémultiplication de l'alpha (élimination des halos noirs/blancs parasites).
     - Réduction hybride (moyenne par blocs vectorisés + rééchantillonnage Lanczos3).
     - Masque flou calibré pour préserver le piqué à 24/48 px.
  5. Extraction de la couleur dominante dans l'espace perceptuel CIELAB via k-means++ pondéré
     avec pénalisation des extrêmes (blanc/noir/gris) et valorisation de la saturation chromatique.
"""

from __future__ import annotations

import io
import math
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image

# Protection serveur contre les bombes de décompression (30 millions de pixels max)
Image.MAX_IMAGE_PIXELS = 30_000_000

# ---------------------------------------------------------------------------
# 1. Espaces Colorimétriques : sRGB, Linéaire et CIELAB
# ---------------------------------------------------------------------------

_SRGB_LUT = np.where(
    (np.arange(256, dtype=np.float32) / 255.0) <= 0.04045,
    (np.arange(256, dtype=np.float32) / 255.0) / 12.92,
    (((np.arange(256, dtype=np.float32) / 255.0) + 0.055) / 1.055) ** 2.4,
).astype(np.float32)


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    """sRGB [0, 1] -> Lumière linéaire [0, 1]."""
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    """Lumière linéaire [0, 1] -> sRGB [0, 1]."""
    c = np.clip(c, 0.0, 1.0)
    return np.where(
        c <= 0.0031308,
        c * 12.92,
        1.055 * np.power(np.maximum(c, 1e-8), 1.0 / 2.4) - 0.055,
    ).astype(np.float32)


_M_RGB2XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ],
    dtype=np.float32,
)
_WHITE_D65 = np.array([0.95047, 1.00000, 1.08883], dtype=np.float32)


def linear_rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """RGB linéaire (N, 3) -> CIELAB (N, 3), illuminant D65."""
    xyz = rgb @ _M_RGB2XYZ.T
    t = xyz / _WHITE_D65
    d = 6.0 / 29.0
    f = np.where(t > d**3, np.cbrt(np.maximum(t, 0.0)), t / (3 * d * d) + 4.0 / 29.0)
    return np.stack(
        [116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])],
        axis=1,
    ).astype(np.float32)


def lab_to_srgb_hex(lab: np.ndarray) -> str:
    """CIELAB (3,) -> Code hexadécimal sRGB."""
    clarte, a, b = float(lab[0]), float(lab[1]), float(lab[2])
    fy = (clarte + 16) / 116.0
    fx, fz = fy + a / 500.0, fy - b / 200.0
    d = 6.0 / 29.0

    def finv(val: float) -> float:
        return val**3 if val > d else 3 * d * d * (val - 4.0 / 29.0)

    xyz = np.array([finv(fx), finv(fy), finv(fz)], dtype=np.float32) * _WHITE_D65
    rgb_lin = np.linalg.solve(_M_RGB2XYZ, xyz)
    rgb = np.clip(linear_to_srgb(np.clip(rgb_lin, 0.0, 1.0)), 0.0, 1.0)
    r, g, bl = np.round(rgb * 255).astype(int).tolist()
    return f"#{r:02X}{g:02X}{bl:02X}"


# ---------------------------------------------------------------------------
# 2. Nettoyage : Suppression de Fond Uniforme et Recadrage
# ---------------------------------------------------------------------------


def remove_uniform_background(rgba: np.ndarray, tolerance: float = 0.055) -> np.ndarray:
    """Supprime un fond uniforme (ex: aplat blanc ou noir) avec dégradé doux sur les bords."""
    alpha = rgba[..., 3]
    if float(alpha.min()) < 0.96:
        return rgba

    h, w, _ = rgba.shape

    # Les coins sont échantillonnés en **pastilles**, pas en pixels isolés.
    # Un seul pixel suffisait à faire échouer la détection — bruit de
    # compression JPEG, liseré d'un pixel autour du cadre, antialiasing d'un
    # coin arrondi — et le fond restait alors en place jusque dans la barre.
    # La médiane d'une pastille ignore ces accidents.
    cote = int(max(2, min(8, h // 20, w // 20)))
    pastilles = np.stack(
        [
            np.median(rgba[:cote, :cote, :3].reshape(-1, 3), axis=0),
            np.median(rgba[:cote, w - cote :, :3].reshape(-1, 3), axis=0),
            np.median(rgba[h - cote :, :cote, :3].reshape(-1, 3), axis=0),
            np.median(rgba[h - cote :, w - cote :, :3].reshape(-1, 3), axis=0),
        ]
    ).astype(np.float32)
    if float(np.abs(pastilles - pastilles.mean(0)).max()) > tolerance:
        return rgba

    bg = pastilles.mean(0)
    dist = np.sqrt(((rgba[..., :3] - bg) ** 2).sum(-1) / 3.0)
    new_alpha = np.clip((dist - tolerance) / max(tolerance, 1e-6), 0.0, 1.0)

    if float((new_alpha > 0.5).mean()) < 0.002:
        return rgba

    out = rgba.copy()
    out[..., 3] = new_alpha.astype(np.float32)
    return out


def trim(rgba: np.ndarray, threshold: float = 0.02) -> np.ndarray:
    """Recadre sur la boîte englobante du contenu non transparent."""
    mask = rgba[..., 3] > threshold
    if not mask.any():
        return rgba
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    return rgba[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]


# ---------------------------------------------------------------------------
# 3. Filtrage Numérique & Réduction Optique
# ---------------------------------------------------------------------------


def _blur1d(arr: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    r = (len(kernel) - 1) // 2
    pad = [(0, 0)] * arr.ndim
    pad[axis] = (r, r)
    p = np.pad(arr, pad, mode="edge")
    out = np.zeros_like(arr, dtype=np.float32)
    for i, w in enumerate(kernel):
        sl = [slice(None)] * arr.ndim
        sl[axis] = slice(i, i + arr.shape[axis])
        out += (w * p[tuple(sl)]).astype(np.float32)
    return out


def gaussian_blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Flou gaussien séparable en float32."""
    if sigma <= 0:
        return arr.astype(np.float32)
    r = max(1, math.ceil(3 * sigma))
    x = np.arange(-r, r + 1, dtype=np.float32)
    k = np.exp(-(x**2) / (2 * sigma * sigma)).astype(np.float32)
    k /= k.sum()
    return _blur1d(_blur1d(arr.astype(np.float32), k, 0), k, 1)


def block_reduce(arr: np.ndarray, k: int) -> np.ndarray:
    """Moyenne exacte par blocs k x k (filtre boîte pour grandes réductions)."""
    if k <= 1:
        return arr
    h, w = arr.shape[:2]
    ph, pw = (-h) % k, (-w) % k
    if ph or pw:
        arr = np.pad(arr, ((0, ph), (0, pw), (0, 0)), mode="edge")
        h, w = arr.shape[:2]
    return arr.reshape(h // k, k, w // k, k, arr.shape[2]).mean(axis=(1, 3)).astype(np.float32)


def lanczos_resize(plane: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Rééchantillonnage Lanczos3 d'un plan float32."""
    im = Image.fromarray(plane.astype(np.float32), mode="F")
    return np.asarray(im.resize(size, Image.Resampling.LANCZOS), dtype=np.float32)


def prepare_linear(rgba: np.ndarray) -> np.ndarray:
    """Conversion sRGB non prémultiplié -> [RGB linéaire prémultiplié, alpha]."""
    idx = np.round(np.clip(rgba[..., :3], 0.0, 1.0) * 255).astype(np.uint8)
    rgb_lin = _SRGB_LUT[idx]
    alpha = rgba[..., 3].astype(np.float32)
    return np.dstack([rgb_lin * alpha[..., None], alpha[..., None]]).astype(np.float32)


def downscale_hq(
    stack: np.ndarray,
    target: tuple[int, int],
    sharpen: float = 0.5,
    sharpen_radius: float = 0.55,
    edge_contrast: float = 1.12,
) -> np.ndarray:
    """Réduction haute fidélité avec correction de gamma et anti-ringing."""
    factor = max(stack.shape[1] / target[0], stack.shape[0] / target[1])
    k = int(factor // 4)
    if k >= 2:
        stack = block_reduce(stack, k)

    pm_s = np.stack([lanczos_resize(stack[..., i], target) for i in range(3)], axis=-1)
    a_s = lanczos_resize(stack[..., 3], target)

    a_s = np.clip(a_s, 0.0, 1.0)
    pm_s = np.clip(pm_s, 0.0, a_s[..., None])

    if sharpen > 0:
        quad = np.dstack([pm_s, a_s[..., None]])
        blurred = np.stack([gaussian_blur(quad[..., i], sharpen_radius) for i in range(4)], axis=-1)
        quad = np.clip(quad + sharpen * (quad - blurred), 0.0, None)
        pm_s, a_s = quad[..., :3], np.clip(quad[..., 3], 0.0, 1.0)

    pm_s = np.clip(pm_s, 0.0, a_s[..., None])

    safe_a = np.maximum(a_s, 1e-6)[..., None]
    rgb_out = linear_to_srgb(np.clip(pm_s / safe_a, 0.0, 1.0))

    if edge_contrast and edge_contrast != 1.0:
        a_s = np.clip((a_s - 0.5) * edge_contrast + 0.5, 0.0, 1.0)

    rgb_out = np.where(a_s[..., None] > 1e-4, rgb_out, 0.0)
    return np.clip(np.dstack([rgb_out, a_s]), 0.0, 1.0).astype(np.float32)


# La barre d'application réserve **32 pixels de haut**, et la largeur suit.
#
# *Un carré de 24 px était imposé auparavant.* Un logo d'entreprise porte
# presque toujours un nom, souvent une accroche : pressé dans un carré de
# 24 px, ce texte disparaît, et aucune finesse de réduction n'y change rien.
# **La forme du logo n'est pas négociable, la place qu'on lui donne l'est.**
HAUTEUR_BARRE = 32

# Au-delà, un logo très allongé écarterait la barre : on le réduit encore.
RAPPORT_LARGEUR_MAX = 4.0


def reduire_a_hauteur(stack: np.ndarray, hauteur: int) -> np.ndarray:
    """Réduit à `hauteur` pixels **en conservant le rapport d'aspect**.

    Retourne un tableau de la forme naturelle du logo, jamais un carré. Une
    largeur au-delà de `RAPPORT_LARGEUR_MAX` fois la hauteur est ramenée à cette
    borne, en réduisant la hauteur d'autant : mieux vaut un logo un peu plus
    petit qu'une barre disloquée.
    """
    haut_source, larg_source = stack.shape[:2]
    largeur = max(1, round(larg_source * hauteur / haut_source))

    plafond = round(RAPPORT_LARGEUR_MAX * hauteur)
    if largeur > plafond:
        hauteur = max(1, round(hauteur * plafond / largeur))
        largeur = plafond

    return downscale_hq(stack, (largeur, hauteur))


def fit_on_canvas(stack: np.ndarray, size: int, pad: int = 0) -> np.ndarray:
    """Réduit en conservant le ratio d'aspect et centre sur un canevas carré."""
    inner = max(1, size - 2 * pad)
    h, w = stack.shape[:2]
    scale = min(inner / w, inner / h)
    tw, th = max(1, round(w * scale)), max(1, round(h * scale))
    small = downscale_hq(stack, (tw, th))

    canvas = np.zeros((size, size, 4), dtype=np.float32)
    x0, y0 = (size - tw) // 2, (size - th) // 2
    canvas[y0 : y0 + th, x0 : x0 + tw] = small
    return canvas


def to_pil_rgba(arr: np.ndarray) -> Image.Image:
    """Convertit un tableau float32 [0, 1] en Image PIL RGBA 8 bits."""
    return Image.fromarray(np.round(np.clip(arr, 0.0, 1.0) * 255).astype(np.uint8), mode="RGBA")


# ---------------------------------------------------------------------------
# 4. Analyse Colorimétrique Perceptuelle (CIELAB k-means++)
# ---------------------------------------------------------------------------


def _kmeans(
    data: np.ndarray, weights: np.ndarray, k: int, iters: int = 40, seed: int = 7
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = len(data)
    k = min(k, n)

    centers = [data[rng.integers(n)]]
    for _ in range(k - 1):
        d2 = np.min(((data[:, None, :] - np.array(centers)[None, :, :]) ** 2).sum(-1), axis=1)
        p = d2 * weights
        total = p.sum()
        centers.append(data[rng.choice(n, p=p / total) if total > 0 else rng.integers(n)])
    centers = np.array(centers, dtype=np.float32)

    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        d2 = ((data[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
        new_labels = d2.argmin(1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for j in range(k):
            m = labels == j
            wsum = weights[m].sum()
            if wsum > 0:
                centers[j] = (data[m] * weights[m, None]).sum(0) / wsum
    return centers, labels


def extraire_couleur_dominante_cielab(
    rgba: np.ndarray,
    k: int = 6,
    max_samples: int = 25000,
    alpha_min: float = 0.55,
    seed: int = 7,
) -> dict[str, Any]:
    """Extrait la couleur dominante dans l'espace perceptuel CIELAB avec scoring de chroma."""
    h, w = rgba.shape[:2]
    step = max(1, int(math.sqrt((h * w) / (max_samples * 4.0))))
    sub = rgba[::step, ::step]

    flat = sub.reshape(-1, 4)
    px = flat[flat[:, 3] >= alpha_min]
    if len(px) == 0:
        px = flat[flat[:, 3] > 0.02]
    if len(px) == 0:
        return {
            "dominant_color": "#D4652A",
            "palette": [],
            "on_dominant": "#FFFFFF",
        }

    if len(px) > max_samples:
        idx = np.random.default_rng(seed).choice(len(px), max_samples, replace=False)
        px = px[idx]

    lab = linear_rgb_to_lab(srgb_to_linear(px[:, :3]))
    weights = px[:, 3].astype(np.float32)

    centers, labels = _kmeans(lab, weights, k, seed=seed)

    clusters = []
    total_w = weights.sum()
    for j in range(len(centers)):
        m = labels == j
        wj = float(weights[m].sum())
        if wj <= 0:
            continue
        clarte, a, b = centers[j]
        chroma = float(math.hypot(a, b))
        share = wj / total_w

        score = share * (1.0 + min(chroma, 60.0) / 45.0)
        if chroma < 8 and clarte > 92:
            score *= 0.12
        elif chroma < 8 and clarte < 12:
            score *= 0.30
        elif chroma < 8:
            score *= 0.55
        clusters.append(
            {
                "hex": lab_to_srgb_hex(centers[j]),
                "share": round(share, 4),
                "chroma": round(chroma, 2),
                "lightness": round(float(clarte), 2),
                "score": score,
            }
        )

    if not clusters:
        mean_lab = (lab * weights[:, None]).sum(0) / max(weights.sum(), 1e-9)
        clusters = [
            {
                "hex": lab_to_srgb_hex(mean_lab),
                "share": 1.0,
                "chroma": round(float(math.hypot(mean_lab[1], mean_lab[2])), 2),
                "lightness": round(float(mean_lab[0]), 2),
                "score": 1.0,
            }
        ]

    clusters.sort(key=lambda c: c["score"], reverse=True)
    best = clusters[0]
    for c in clusters:
        c.pop("score", None)

    return {
        "dominant_color": best["hex"],
        "palette": clusters[:5],
        "on_dominant": "#FFFFFF" if best["lightness"] < 60 else "#111111",
    }


# ---------------------------------------------------------------------------
# 5. Pipeline Orchestrateur Complet
# ---------------------------------------------------------------------------


def traiter_logo_entreprise(
    fichier_ou_flux: Any,
    tenant_schema: str,
    nom_origine: str,
) -> dict[str, Any]:
    """Traite un logo uploadé et dépose les trois variantes dans le stockage Django.

    Retourne les **clés de stockage** des vignettes 24 px, 48 px et du master
    recadré, la couleur dominante, et `fond_retire` — le détourage a-t-il eu
    lieu. `nom_origine` ne sert plus à nommer les fichiers (le nom du fichier
    d'un client n'a rien à faire dans une URL publique) ; il reste au contrat
    pour le journal d'audit.
    """
    if hasattr(fichier_ou_flux, "read") or isinstance(fichier_ou_flux, (str, Path)):
        im_source = Image.open(fichier_ou_flux).convert("RGBA")
    else:
        im_source = Image.open(io.BytesIO(fichier_ou_flux)).convert("RGBA")

    if getattr(im_source, "n_frames", 1) > 1:
        best, best_area = im_source, 0
        for i in range(im_source.n_frames):
            im_source.seek(i)
            area = im_source.size[0] * im_source.size[1]
            if area > best_area:
                best, best_area = im_source.copy(), area
        im_source = best

    rgba = np.asarray(im_source, dtype=np.float32) / np.float32(255.0)

    # 1. Détection du fond uniforme et recadrage
    rgba = remove_uniform_background(rgba)
    rgba = trim(rgba)

    # Le détourage n'est pas garanti : il ne s'applique qu'à un fond **uniforme**
    # aux quatre coins. Un dégradé, une photo, un cadre décoratif le font
    # échouer — légitimement. Ce qui n'était pas légitime, c'est que l'échec
    # passe inaperçu : le logo partait alors en barre avec son rectangle blanc,
    # et personne ne savait pourquoi. L'appelant reçoit le verdict.
    fond_retire = float(rgba[..., 3].min()) < 0.96

    # 2. Extraction couleur dominante CIELAB
    analyse_couleur = extraire_couleur_dominante_cielab(rgba)

    # 3. Réduction optique haute fidélité
    stack = prepare_linear(rgba)
    # Deux variantes pour la barre, à la forme du logo : une par densité
    # d'écran. `srcset` choisit, et le logo n'est jamais rééchantillonné par le
    # navigateur — c'est tout l'intérêt de les tailler ici, en lumière linéaire.
    vignette_1x = to_pil_rgba(reduire_a_hauteur(stack, HAUTEUR_BARRE))
    vignette_2x = to_pil_rgba(reduire_a_hauteur(stack, HAUTEUR_BARRE * 2))
    master_recadre = to_pil_rgba(rgba)

    # 4. Enregistrement — par le stockage Django, jamais par le disque
    #
    # `default_storage`, et non `MEDIA_ROOT`. En production le stockage est S3
    # avec URL signées (`production.py` §STORAGES) ; écrire directement sur le
    # système de fichiers déposait les vignettes **à côté** du stockage réel.
    # Elles existaient en développement, où `MEDIA_ROOT` est servi par
    # `static()` sous `DEBUG`, et nulle part ailleurs : en production le logo
    # d'un client ne s'est jamais affiché une seule fois.
    #
    # La clé suit l'isolation US-006 `{schema}/{module}/{uuid}`. L'ancien
    # nommage `{schema}_{timestamp}_{slug}` rangeait tous les clients dans un
    # même dossier plat, sous un nom devinable, et publiait le nom de schéma
    # dans une URL sans authentification.
    racine = f"{tenant_schema}/logos/{uuid.uuid4().hex}"

    def _enregistrer(image: Image.Image, suffixe: str) -> str:
        tampon = io.BytesIO()
        image.save(tampon, format="PNG", optimize=True)
        tampon.seek(0)
        return default_storage.save(f"{racine}_{suffixe}.png", ContentFile(tampon.read()))

    # Ce sont des **clés de stockage** qui remontent, pas des URL. Une URL S3
    # est signée : la persister reviendrait à mettre en base un lien qui meurt
    # au bout de quelques heures. L'URL se calcule à la lecture.
    return {
        "cle_1x": _enregistrer(vignette_1x, "1x"),
        "cle_2x": _enregistrer(vignette_2x, "2x"),
        "cle_original": _enregistrer(master_recadre, "original"),
        # La forme réelle, pour que l'écran réserve la bonne largeur sans
        # attendre le chargement de l'image.
        "largeur_1x": vignette_1x.width,
        "hauteur_1x": vignette_1x.height,
        "fond_retire": fond_retire,
        "dominant_color": analyse_couleur["dominant_color"],
        "on_dominant": analyse_couleur["on_dominant"],
        "palette": analyse_couleur["palette"],
    }
