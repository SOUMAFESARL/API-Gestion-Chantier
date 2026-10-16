"""`/api/v1/referentiels/{types-projet|lots}/` — listes dynamiques du module Projets."""

from django.http import Http404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.droits import APermission, a_permission
from apps.projets.services.referentiels import (
    CATEGORIES_URL,
    ajouter_entree,
    lister_referentiel,
    retirer_entree,
)

__all__ = ["ReferentielEntreeView", "ReferentielListeView"]

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


def _exiger_ecriture(request) -> None:
    """Ajouter ou retirer : qui peut créer un projet ou modifier sa structure (lots)."""
    if not (
        a_permission(request.user, "projets.creer", request=request)
        or a_permission(request.user, "projets.ecrire", request=request)
    ):
        raise PermissionDenied(APermission.message)


class ReferentielListeView(APIView):
    parser_classes = [JSONParser]

    def get_permissions(self):
        return [IsAuthenticated(), APermission.pour("projets.lire")()]

    @extend_schema(summary="Liste d'un référentiel (plateforme + entreprise)", responses=ENTREE)
    def get(self, request, categorie):
        return Response(lister_referentiel(_categorie(categorie)))

    @extend_schema(
        summary="Ajouter une entrée de l'entreprise au référentiel",
        request=inline_serializer("AjoutReferentiel", fields={"libelle": serializers.CharField()}),
        responses={201: ENTREE},
    )
    def post(self, request, categorie):
        cat = _categorie(categorie)
        _exiger_ecriture(request)
        entree = ajouter_entree(cat, request.data.get("libelle", ""), auteur=request.user)
        return Response(entree, status=status.HTTP_201_CREATED)


class ReferentielEntreeView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), APermission.pour("projets.lire")()]

    @extend_schema(summary="Retirer une entrée de l'entreprise (jamais une de la plateforme)")
    def delete(self, request, categorie, code):
        cat = _categorie(categorie)
        _exiger_ecriture(request)
        retirer_entree(cat, code, auteur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
