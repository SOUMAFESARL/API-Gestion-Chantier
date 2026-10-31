"""`/api/v1/referentiels/{types-projet|modes-execution}/` — listes dynamiques du module Projets.

Les noms de lot ne passent plus par ici : ce sont les valeurs de la liste « Lots » du découpage
(`/api/v1/decoupage/listes/`).
"""

from django.http import Http404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.droits import APermission, a_permission, est_administrateur, est_dg
from apps.projets.services.referentiels import (
    CATEGORIES_URL,
    ajouter_entree,
    lister_referentiel,
    retirer_entree,
)

__all__ = ["ReferentielDroitsView", "ReferentielEntreeView", "ReferentielListeView"]

ENTREE = inline_serializer(
    "EntreeReferentiel",
    fields={
        "code": serializers.CharField(),
        "libelle": serializers.CharField(),
        "groupe": serializers.CharField(),
        "origine": serializers.ChoiceField(choices=["PLATEFORME", "ENTREPRISE"]),
    },
)


def _categorie(segment: str) -> str:
    try:
        return CATEGORIES_URL[segment]
    except KeyError:
        raise Http404 from None


def _peut_ajouter(request) -> bool:
    """Ajouter : une permission attribuable dans la matrice (le DG la détient d'office)."""
    return a_permission(request.user, "projets.referentiels_ajouter", request=request)


def _peut_retirer(request) -> bool:
    """Retirer : réservé au DG et à l'administrateur, aucune permission ne l'ouvre."""
    return est_dg(request.user) or est_administrateur(request.user)


def _exiger_ajout(request) -> None:
    if not _peut_ajouter(request):
        raise PermissionDenied("Vous n'avez pas le droit d'ajouter à cette liste.")


def _exiger_retrait(request) -> None:
    if not _peut_retirer(request):
        raise PermissionDenied(
            "Seuls le Directeur Général et l'administrateur peuvent retirer une entrée de la liste."
        )


class ReferentielListeView(APIView):
    parser_classes = [JSONParser]

    def get_permissions(self):
        return [IsAuthenticated(), APermission.pour("projets.lire")()]

    @extend_schema(summary="Liste d'un référentiel (plateforme + entreprise)", responses=ENTREE)
    def get(self, request, categorie):
        return Response(lister_referentiel(_categorie(categorie)))

    @extend_schema(
        summary="Ajouter une entrée de l'entreprise au référentiel",
        request=inline_serializer(
            "AjoutReferentiel",
            fields={
                "libelle": serializers.CharField(),
                "groupe": serializers.CharField(required=False, max_length=100),
            },
        ),
        responses={201: ENTREE},
    )
    def post(self, request, categorie):
        cat = _categorie(categorie)
        _exiger_ajout(request)
        entree = ajouter_entree(
            cat,
            request.data.get("libelle", ""),
            groupe=request.data.get("groupe") or "",
            auteur=request.user,
        )
        return Response(entree, status=status.HTTP_201_CREATED)


class ReferentielEntreeView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), APermission.pour("projets.lire")()]

    @extend_schema(summary="Retirer une entrée de l'entreprise (jamais une de la plateforme)")
    def delete(self, request, categorie, code):
        cat = _categorie(categorie)
        _exiger_retrait(request)
        retirer_entree(cat, code, auteur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReferentielDroitsView(APIView):
    """Ce que l'utilisateur courant peut faire sur les listes (boutons à afficher côté client)."""

    def get_permissions(self):
        return [IsAuthenticated(), APermission.pour("projets.lire")()]

    @extend_schema(
        summary="Droits de l'utilisateur courant sur les référentiels",
        responses=inline_serializer(
            "DroitsReferentiels",
            fields={
                "peut_ajouter": serializers.BooleanField(),
                "peut_retirer": serializers.BooleanField(),
            },
        ),
    )
    def get(self, request):
        return Response(
            {"peut_ajouter": _peut_ajouter(request), "peut_retirer": _peut_retirer(request)}
        )
