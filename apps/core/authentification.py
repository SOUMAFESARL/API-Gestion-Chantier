"""Authentification JWT qui active l'entreprise de la requête — décision D9, règle R-7.

L'entreprise d'une requête ne se lit ni dans le nom d'hôte ni dans un en-tête : **seul le jeton
vérifié la désigne**. Après la vérification de la signature, on charge l'utilisateur, on compare
le claim `entreprise` du jeton à `utilisateur.entreprise_id` — c'est la barrière que
`authentification_jwt_CCD_Digital.md` §5.2 exigeait, et qu'aucun code ne faisait —, puis on active
l'entreprise pour le reste de la requête.

*Lot 1* : tant que les comptes vivent dans un schéma par entreprise, ni le jeton ne porte de claim
`entreprise`, ni l'utilisateur de colonne `entreprise_id`. La classe se comporte alors exactement
comme `JWTAuthentication`. Elle prend effet au lot 5, quand le jeton porte le claim.
"""

from __future__ import annotations

import logging

from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.contexte import activer_entreprise

logger = logging.getLogger(__name__)

CLAIM_ENTREPRISE = "entreprise"


class AuthentificationEntreprise(JWTAuthentication):
    """`JWTAuthentication`, plus la comparaison du claim `entreprise` et son activation."""

    def authenticate(self, request):
        resultat = super().authenticate(request)
        if resultat is None:
            return None
        utilisateur, jeton = resultat
        verifier_et_activer(utilisateur, jeton)
        return utilisateur, jeton


def verifier_et_activer(utilisateur, jeton) -> None:
    """Compare le claim du jeton à l'entreprise de l'utilisateur, puis active celle-ci.

    | Claim `entreprise` | `utilisateur.entreprise_id` | Issue |
    |---|---|---|
    | absent | absent (personnel de l'éditeur, ou lot 1) | aucune entreprise activée |
    | présent | égal | l'entreprise est activée |
    | présent | différent, ou absent | refus `401`, journalisé |
    | absent | présent | refus `401` : un compte d'entreprise doit présenter son entreprise |
    """
    claim = jeton.get(CLAIM_ENTREPRISE) if hasattr(jeton, "get") else None
    a_une_colonne = hasattr(utilisateur, "entreprise_id")
    attendue = getattr(utilisateur, "entreprise_id", None)

    if claim is None and attendue is None:
        return
    if claim is None and a_une_colonne:
        logger.warning(
            "Jeton sans entreprise présenté par un compte d'entreprise (%s)", utilisateur.pk
        )
        raise AuthenticationFailed(
            _("Jeton invalide pour ce compte."), code="jeton_entreprise_absente"
        )
    if attendue is None or str(claim) != str(attendue):
        logger.warning(
            "Jeton de l'entreprise %s présenté par le compte %s (entreprise %s)",
            claim, utilisateur.pk, attendue,
        )
        raise AuthenticationFailed(
            _("Jeton invalide pour ce compte."), code="jeton_entreprise_differente"
        )
    activer_entreprise(attendue)
