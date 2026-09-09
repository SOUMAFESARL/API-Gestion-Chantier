"""Liste noire des jetons — spécification T-008 §3.

Le code ne connaît que `django.core.cache` : **Redis en production, cache
local en développement**. Le support est un réglage, pas une dépendance.

**Pourquoi pas les tables `token_blacklist` de SimpleJWT** — décision S4.
`OutstandingToken` porte une clé étrangère vers `AUTH_USER_MODEL`, et
`utilisateur` existe dans `public` **et** dans chaque schéma client (écart
E1) : placée dans `SHARED_APPS` la table pointerait vers `public.utilisateur`,
où l'UUID d'un utilisateur de `demo` n'existe pas ; placée dans `TENANT_APPS`
elle ne couvrirait pas le personnel de la plateforme. Deux autres raisons en
§3.1 : la table grandit sans fin, et le renouvellement est la requête la plus
fréquente de l'API après la lecture.

**Le code du schéma est obligatoire dans chaque clé.** Redis est partagé par
tous les clients : contrairement à PostgreSQL il n'offre aucune isolation, et
c'est la forme de la clé qui la porte — T-008 §3.2. Sans le schéma, le `jti`
révoqué d'un client refuserait le jeton d'un autre.
"""

import time

from django.core.cache import cache
from django.db import connection
from django.utils.translation import gettext_lazy as _
from rest_framework import status

from apps.core.exceptions import ErreurMetier

__all__ = [
    "MOTIF_ADMINISTRATEUR",
    "MOTIF_DECONNEXION",
    "MOTIF_REJEU",
    "MOTIF_ROTATION",
    "ServiceIndisponible",
    "epoque_utilisateur",
    "revocation",
    "revoquer_jeton",
    "revoquer_session",
    "revoquer_utilisateur",
    "session_revoquee",
]

# Motifs de révocation — T-008 §3.2. La valeur sert deux fois : distinguer un
# rejeu bénin d'un vol (§4.2), et renseigner le journal d'audit sans requête
# supplémentaire.
MOTIF_ROTATION = "rotation"
MOTIF_DECONNEXION = "deconnexion"
MOTIF_ADMINISTRATEUR = "administrateur"
MOTIF_REJEU = "rejeu"

PREFIXE = "ccd:jwt"


class ServiceIndisponible(ErreurMetier):
    """La liste noire est injoignable — T-008 §3.5.

    `503`, et non `401` : les deux décrivent la même panne au serveur, mais
    commandent deux comportements opposés au client. Un `401` lui fait jeter
    ses jetons ; une coupure de trente secondes déconnecterait alors tout le
    monde, chefs de chantier en pleine saisie compris. Un `503` lui dit
    d'attendre et de garder ce qu'il a.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code_metier = "service_indisponible"
    default_detail = _("Service momentanément indisponible. Réessayez dans un instant.")


def _schema() -> str:
    """Le schéma courant, résolu par django-tenants avant la vue."""
    return getattr(connection, "schema_name", "public")


def _cle_revoque(jti: str) -> str:
    return f"{PREFIXE}:revoque:{_schema()}:{jti}"


def _cle_session(sid: str) -> str:
    return f"{PREFIXE}:session:{_schema()}:{sid}"


def _cle_epoque(utilisateur_id) -> str:
    return f"{PREFIXE}:epoque:{_schema()}:{utilisateur_id}"


def _ecrire(cle: str, valeur: str, ttl: int) -> None:
    if ttl <= 0:
        # Le jeton est déjà mort : la vérification d'expiration le refuse de
        # toute façon. Mémoriser sa révocation ne servirait à rien.
        return
    try:
        cache.set(cle, valeur, timeout=ttl)
    except Exception as exc:  # pragma: no cover - dépend du support
        raise ServiceIndisponible() from exc


def _lire(cle: str) -> str | None:
    try:
        return cache.get(cle)
    except Exception as exc:  # pragma: no cover - dépend du support
        raise ServiceIndisponible() from exc


# --------------------------------------------------------------------------
# Révocation d'un jeton
# --------------------------------------------------------------------------
def revoquer_jeton(jti: str, *, ttl: int, motif: str = MOTIF_ROTATION) -> None:
    """Révoque **un** jeton jusqu'à sa mort naturelle.

    Le TTL est ce qui rend la liste noire correcte, pas seulement économe :
    au-delà de l'expiration du jeton, il n'existe aucune fenêtre pendant
    laquelle une clé disparue laisserait passer un jeton révoqué.
    """
    _ecrire(_cle_revoque(jti), f"{motif}:{time.time():.3f}", ttl)


def revocation(jti: str) -> tuple[str, float] | None:
    """Le motif et l'instant de la révocation, ou `None` si le jeton est vivant."""
    valeur = _lire(_cle_revoque(jti))
    if not valeur:
        return None
    motif, _, horodatage = str(valeur).partition(":")
    try:
        return motif, float(horodatage)
    except ValueError:
        # Valeur écrite par une version antérieure : on la traite comme une
        # révocation sans date, donc hors de toute fenêtre de grâce.
        return motif, 0.0


# --------------------------------------------------------------------------
# Révocation d'une session entière
# --------------------------------------------------------------------------
def revoquer_session(sid: str, *, ttl: int, motif: str = MOTIF_REJEU) -> None:
    """Révoque **une** session — tous ses jetons, présents et à venir.

    C'est la portée que le rejeu déclenche (T-008 §4.2) : ni le voleur ni la
    victime ne peuvent continuer, et la victime se reconnecte. Révoquer le
    seul `jti` présenté ne servirait à rien, puisque l'autre moitié de la
    course détient déjà la paire suivante.
    """
    _ecrire(_cle_session(sid), f"{motif}:{time.time():.3f}", ttl)


def session_revoquee(sid: str) -> bool:
    return bool(_lire(_cle_session(sid)))


# --------------------------------------------------------------------------
# Révocation de tous les jetons d'un utilisateur
# --------------------------------------------------------------------------
def revoquer_utilisateur(utilisateur_id, *, ttl: int) -> None:
    """Révoque **tout** pour un utilisateur — Socle §2.2.

    Tout jeton dont `iat` est antérieur à cette époque est refusé. C'est ce
    que la désactivation d'un collaborateur pousse (T-017 §6, effet 4) : sans
    elle, les jetons déjà émis survivraient à la désactivation.
    """
    _ecrire(_cle_epoque(utilisateur_id), f"{time.time():.3f}", ttl)


def epoque_utilisateur(utilisateur_id) -> float | None:
    """Horodatage Unix avant lequel tout jeton de cet utilisateur est refusé."""
    valeur = _lire(_cle_epoque(utilisateur_id))
    if not valeur:
        return None
    try:
        return float(valeur)
    except ValueError:  # pragma: no cover
        return None
