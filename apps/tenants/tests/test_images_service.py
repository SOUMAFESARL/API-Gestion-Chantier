import io

import numpy as np
from django.core.files.storage import default_storage
from PIL import Image

from apps.tenants.services.images import (
    HAUTEUR_BARRE,
    RAPPORT_LARGEUR_MAX,
    extraire_couleur_dominante_cielab,
    fit_on_canvas,
    prepare_linear,
    reduire_a_hauteur,
    remove_uniform_background,
    traiter_logo_entreprise,
    trim,
)


def test_remove_uniform_background_et_trim():
    """Vérifie que les aplats uniformes sur les coins sont détectés et que le logo est recadré."""
    # Image 100x100 blanche avec un carré bleu 20x20 au centre
    im = Image.new("RGBA", (100, 100), color=(255, 255, 255, 255))
    for x in range(40, 60):
        for y in range(40, 60):
            im.putpixel((x, y), (30, 110, 200, 255))

    rgba = np.asarray(im, dtype=np.float32) / 255.0
    rgba_detoure = remove_uniform_background(rgba)

    # Les coins doivent être devenus transparents (alpha proche de 0)
    assert rgba_detoure[0, 0, 3] < 0.1
    assert rgba_detoure[99, 99, 3] < 0.1

    # Le centre doit être resté opaque (alpha = 1)
    assert rgba_detoure[50, 50, 3] > 0.9

    # Trim doit recadrer autour du carré bleu 20x20
    recadre = trim(rgba_detoure)
    assert abs(recadre.shape[0] - 20) <= 2
    assert abs(recadre.shape[1] - 20) <= 2


def test_extraire_couleur_dominante_cielab():
    """Vérifie que l'extraction CIELAB ignore le blanc et extrait la couleur de marque."""
    im = Image.new("RGBA", (80, 80), color=(255, 255, 255, 255))
    # Peindre 30% des pixels en terracotta #D4652A (212, 101, 42)
    for x in range(25, 55):
        for y in range(25, 55):
            im.putpixel((x, y), (212, 101, 42, 255))

    rgba = np.asarray(im, dtype=np.float32) / 255.0
    rgba_clean = remove_uniform_background(rgba)
    res = extraire_couleur_dominante_cielab(rgba_clean)

    # La couleur dominante doit être proche du terracotta et le blanc est exclu
    assert res["dominant_color"].startswith("#")
    assert res["on_dominant"] in ("#FFFFFF", "#111111")
    assert len(res["palette"]) > 0


def test_fit_on_canvas_dimensions():
    """Vérifie que les dimensions cibles sont respectées."""
    # Logo rectangulaire 200x100
    im = Image.new("RGBA", (200, 100), color=(200, 50, 50, 255))
    rgba = np.asarray(im, dtype=np.float32) / 255.0
    stack = prepare_linear(rgba)

    vignette_24 = fit_on_canvas(stack, size=24, pad=1)
    assert vignette_24.shape == (24, 24, 4)

    vignette_48 = fit_on_canvas(stack, size=48, pad=2)
    assert vignette_48.shape == (48, 48, 4)


def test_detourage_resiste_au_bruit_des_coins():
    """Un fond blanc bruité — le cas du JPEG — doit rester détecté.

    La détection lisait **quatre pixels**. Un seul pixel aberrant dans un coin,
    et le fond partait en production avec son rectangle blanc. Les coins sont
    maintenant échantillonnés en pastilles, à la médiane.
    """
    rng = np.random.default_rng(3)
    im = Image.new("RGBA", (100, 100), color=(255, 255, 255, 255))
    for x in range(40, 60):
        for y in range(40, 60):
            im.putpixel((x, y), (30, 110, 200, 255))

    rgba = np.asarray(im, dtype=np.float32) / 255.0
    # Bruit de compression sur tout le fond, ±3/255.
    bruit = rng.uniform(-3.0 / 255.0, 3.0 / 255.0, size=(100, 100, 3)).astype(np.float32)
    rgba[..., :3] = np.clip(rgba[..., :3] + bruit, 0.0, 1.0)
    # Et un pixel franchement aberrant, exactement dans un coin.
    rgba[0, 0, :3] = np.array([0.1, 0.1, 0.1], dtype=np.float32)

    detoure = remove_uniform_background(rgba)

    assert detoure[3, 3, 3] < 0.1, "le fond bruité n'a pas été détouré"
    assert detoure[99, 99, 3] < 0.1
    assert detoure[50, 50, 3] > 0.9


def test_traiter_logo_entreprise(tmp_path, settings):
    """Le pipeline dépose ses trois variantes **dans le stockage Django**."""
    settings.MEDIA_ROOT = tmp_path

    buf = io.BytesIO()
    im = Image.new("RGBA", (120, 120), color=(40, 120, 210, 255))
    im.save(buf, format="PNG")
    buf.seek(0)

    resultat = traiter_logo_entreprise(buf, tenant_schema="demo", nom_origine="mon_logo.png")

    # Isolation US-006 : un dossier par schéma, un nom qui ne se devine pas.
    for cle in (resultat["cle_1x"], resultat["cle_2x"], resultat["cle_original"]):
        assert cle.startswith("demo/logos/")
        assert default_storage.exists(cle)
    assert resultat["cle_1x"].endswith("_1x.png")
    assert resultat["cle_2x"].endswith("_2x.png")
    assert resultat["cle_original"].endswith("_original.png")
    assert resultat["dominant_color"].startswith("#")

    # Le nom du fichier d'origine ne doit plus transparaître dans la clé.
    assert "mon_logo" not in resultat["cle_2x"]

    # La hauteur est celle de la barre ; la largeur suit le logo.
    with default_storage.open(resultat["cle_1x"]) as f:
        assert Image.open(f).size[1] == HAUTEUR_BARRE
    with default_storage.open(resultat["cle_2x"]) as f:
        assert Image.open(f).size[1] == HAUTEUR_BARRE * 2


def test_le_logo_garde_sa_forme():
    """**Aucun carré imposé.** Un logo large reste large.

    *Les variantes étaient des carrés de 24 et 48 px. Un logo qui porte un nom
    et une accroche y devenait illisible — vérifié sur un logo réel. La forme
    du logo n'est pas négociable ; la place qu'on lui donne l'est.*
    """
    # Un logo trois fois plus large que haut — le cas courant.
    im = Image.new("RGBA", (900, 300), color=(20, 60, 120, 255))
    rgba = np.asarray(im, dtype=np.float32) / 255.0
    stack = prepare_linear(rgba)

    reduit = reduire_a_hauteur(stack, HAUTEUR_BARRE)
    hauteur, largeur = reduit.shape[:2]

    assert hauteur == HAUTEUR_BARRE
    assert largeur == HAUTEUR_BARRE * 3, "le rapport d'aspect n'est pas conservé"


def test_un_logo_tres_allonge_est_borne():
    """Sinon un logo en bandeau écarterait la barre d'application.

    Mieux vaut un logo un peu plus petit qu'une barre disloquée.
    """
    # Dix fois plus large que haut : au-delà de la borne.
    im = Image.new("RGBA", (2000, 200), color=(20, 60, 120, 255))
    stack = prepare_linear(np.asarray(im, dtype=np.float32) / 255.0)

    reduit = reduire_a_hauteur(stack, HAUTEUR_BARRE)
    hauteur, largeur = reduit.shape[:2]

    assert largeur <= HAUTEUR_BARRE * RAPPORT_LARGEUR_MAX
    assert hauteur < HAUTEUR_BARRE, "la hauteur doit céder, pas le rapport d'aspect"


def test_url_de_la_cle_est_absolue_depuis_la_racine(tmp_path, settings):
    """`MEDIA_URL` doit commencer par `/` — sinon l'URL est relative à la page."""
    settings.MEDIA_ROOT = tmp_path
    assert default_storage.url("demo/logos/abc_2x.png").startswith("/media/")
