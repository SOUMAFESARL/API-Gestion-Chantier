"""Authentification JWT qui active l'entreprise de la requête — décision D9, règle R-7.

L'entreprise d'une requête ne se lit ni dans le nom d'hôte ni dans un en-tête : **seul le jeton
vérifié la désigne**. Après la vérification de la signature, on charge l'utilisateur, on compare
le claim `entreprise` du jeton à `utilisateur.entreprise_id` — c'est la barrière que
`authentification_jwt_CCD_Digital.md` §5.2 exigeait, et qu'aucun code ne faisait —, puis on active
l'entreprise pour le reste de la requête.

**Le compte se charge dans l'entreprise du claim.** La table `utilisateur` est cloisonnée
(`RequeteComptes`) : sans entreprise active, elle ne rend que le personnel de l'éditeur. Le compte
d'un jeton qui porte un claim est donc cherché **dans cette entreprise** ; un claim qui ne
correspond pas au compte ne le trouve pas, et le refus tombe avant même la comparaison.
"""

from __future__ import annotations

import logging
import uuid

from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.core.contexte import activer_entreprise, contexte_entreprise

logger = logging.getLogger(__name__)

CLAIM_ENTREPRISE = "entreprise"


class AuthentificationEntreprise(JWTAuthentication):
    """`JWTAuthentication`, plus la comparaison du claim `entreprise` et son activation."""

    def get_user(self, validated_token):
        """Le compte du jeton, cherché dans l'entreprise que le claim désigne."""
        claim = validated_token.get(CLAIM_ENTREPRISE)
        if not claim:
            return super().get_user(validated_token)
        try:
            with contexte_entreprise(claim):
                return super().get_user(validated_token)
        except ValueError as exc:  # claim illisible
            raise AuthenticationFailed(
                _("Jeton invalide pour ce compte."), code="jeton_entreprise_illisible"
            ) from exc

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


_NON_LU = object()


def entreprise_du_jeton(request) -> uuid.UUID | None:
    """L'entreprise que désigne le jeton d'accès **vérifié** de la requête, ou `None`.

    Pour les middlewares, qui passent avant l'authentification de DRF et n'ont plus de
    d'entreprise posée. La signature et l'expiration sont vérifiées, mais le compte n'est pas
    encore comparé au claim : ce qu'un middleware en tire ne doit **que restreindre** (lecture
    seule, module fermé), jamais ouvrir un accès. Lu une fois par requête.
    """
    deja = getattr(request, "_entreprise_du_jeton", _NON_LU)
    if deja is not _NON_LU:
        return deja
    resultat = None
    entete = request.META.get("HTTP_AUTHORIZATION", "")
    if entete.startswith("Bearer "):
        try:
            claim = AccessToken(entete[7:].strip()).get(CLAIM_ENTREPRISE)
            resultat = uuid.UUID(str(claim)) if claim else None
        except (TokenError, ValueError):
            resultat = None
    request._entreprise_du_jeton = resultat
    return resultat
