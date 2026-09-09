"""Service de déconnexion — révocation de session côté serveur (DEV-3.6).

Révoque le jeton de renouvellement (`jti`) et la session (`sid`) dans la liste
noire Redis afin qu'ils ne puissent plus être présentés pour obtenir de nouveaux
jetons d'accès.
"""

import logging
import time

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services import liste_noire

logger = logging.getLogger(__name__)

__all__ = ["deconnecter"]


def deconnecter(
    jeton_brut: str | None, *, adresse_ip: str | None = None, appareil: str = ""
) -> None:
    """Révoque le jeton de renouvellement et sa session associée.

    L'opération est idempotente et tolère un jeton déjà expiré ou invalide :
    une déconnexion ne doit jamais échouer si le jeton est déjà mort.
    """
    if not jeton_brut:
        return

    try:
        jeton = RefreshToken(jeton_brut)
    except TokenError:
        # Jeton expiré, corrompu ou déjà invalide. Rien à révoquer.
        return

    jti = jeton.get("jti")
    sid = jeton.get("sid")
    exp = jeton.get("exp")
    user_id = jeton.get("user_id")

    ttl = max(0, int(exp - time.time())) if exp else 3600

    if jti:
        try:
            liste_noire.revoquer_jeton(jti, ttl=ttl, motif=liste_noire.MOTIF_DECONNEXION)
        except Exception:
            logger.exception("Échec de révocation du jeton lors de la déconnexion")

    if sid:
        try:
            liste_noire.revoquer_session(sid, ttl=ttl, motif=liste_noire.MOTIF_DECONNEXION)
        except Exception:
            logger.exception("Échec de révocation de la session lors de la déconnexion")

    if user_id:
        try:
            from apps.audit.services import journaliser
            from apps.core.enums import ActionAudit

            journaliser(
                action=ActionAudit.DECONNEXION,
                type_entite="utilisateur",
                entite_id=user_id,
                utilisateur_id=user_id,
                valeur_apres={"sid": sid} if sid else None,
                adresse_ip=adresse_ip,
                appareil=appareil,
            )
        except Exception:
            logger.exception("Échec de journalisation de la déconnexion")
