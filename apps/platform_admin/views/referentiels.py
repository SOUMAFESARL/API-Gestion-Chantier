"""`/api/v1/admins/referentiels/{types-projet|lots}/` — référentiels de la plateforme.

Ce qui s'ajoute ici est proposé aussitôt à toutes les entreprises (lu depuis le
schéma public), qui ne peuvent pas le retirer. Arbitrage du 16/10/2026.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404
from django_tenants.utils import schema_context
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogue.models.referentiel import (
    ReferentielPlateforme,
    cle_comparaison,
    code_depuis_libelle,
)
from apps.platform_admin.permissions import EstSuperAdminPlateforme, exiger_superviseur
from apps.platform_admin.services.notifications import journaliser_plateforme
from apps.projets.services.referentiels import CATEGORIES_URL

__all__ = ["ReferentielPlateformeDetailView", "ReferentielPlateformeListeView"]


class EntreeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferentielPlateforme
        fields = ["id", "code", "libelle", "groupe"]


class SaisieSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=150)
    groupe = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


def _categorie(segment: str) -> str:
    try:
        return CATEGORIES_URL[segment]
    except KeyError:
        raise Http404 from None


def _refuser_doublon(categorie: str, libelle: str, exclure_id=None) -> None:
    cle = cle_comparaison(libelle)
    autres = ReferentielPlateforme.objects.filter(categorie=categorie).exclude(id=exclure_id)
    if any(cle_comparaison(e.libelle) == cle for e in autres):
        raise ValidationError({"libelle": "Ce libellé figure déjà dans la liste."})


class ReferentielPlateformeListeView(APIView):
    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister un référentiel de la plateforme", responses=EntreeSerializer(many=True)
    )
    def get(self, request, categorie):
        cat = _categorie(categorie)
        with schema_context("public"):
            entrees = ReferentielPlateforme.objects.filter(categorie=cat)
            return Response(EntreeSerializer(entrees, many=True).data)

    @extend_schema(
        summary="Ajouter une entrée, proposée à toutes les entreprises",
        request=SaisieSerializer,
        responses={201: EntreeSerializer},
    )
    def post(self, request, categorie):
        exiger_superviseur(request)
        cat = _categorie(categorie)
        saisie = SaisieSerializer(data=request.data)
        saisie.is_valid(raise_exception=True)
        libelle = " ".join(saisie.validated_data["libelle"].split())
        with schema_context("public"):
            _refuser_doublon(cat, libelle)
            tous = ReferentielPlateforme.tous_objets.filter(categorie=cat)
            codes = set(tous.values_list("code", flat=True))
            base = code_depuis_libelle(libelle)
            code, rang = base, 2
            while code in codes:
                code = f"{base[:56]}_{rang}"
                rang += 1
            dernier = ReferentielPlateforme.objects.filter(categorie=cat).order_by("-ordre").first()
            entree = ReferentielPlateforme.objects.create(
                categorie=cat,
                code=code,
                libelle=libelle,
                groupe=saisie.validated_data["groupe"].strip(),
                ordre=(dernier.ordre + 1) if dernier else 0,
                cree_par=request.user,
            )
            donnees = EntreeSerializer(entree).data
        journaliser_plateforme(
            action="AJOUT_REFERENTIEL",
            acteur=request.user,
            detail={"categorie": cat, "code": code, "libelle": libelle},
        )
        return Response(donnees, status=status.HTTP_201_CREATED)


class ReferentielPlateformeDetailView(APIView):
    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Modifier le libellé ou le groupe (le code reste)",
        request=SaisieSerializer,
        responses=EntreeSerializer,
    )
    def patch(self, request, categorie, pk):
        exiger_superviseur(request)
        cat = _categorie(categorie)
        saisie = SaisieSerializer(data=request.data)
        saisie.is_valid(raise_exception=True)
        libelle = " ".join(saisie.validated_data["libelle"].split())
        with schema_context("public"):
            entree = get_object_or_404(ReferentielPlateforme, pk=pk, categorie=cat)
            _refuser_doublon(cat, libelle, exclure_id=entree.id)
            avant = {"libelle": entree.libelle, "groupe": entree.groupe}
            entree.libelle = libelle
            entree.groupe = saisie.validated_data["groupe"].strip()
            entree.save(update_fields=["libelle", "groupe", "modifie_le"])
            donnees = EntreeSerializer(entree).data
        journaliser_plateforme(
            action="MODIFICATION_REFERENTIEL",
            acteur=request.user,
            detail={"categorie": cat, "code": entree.code, "avant": avant, "apres": donnees},
        )
        return Response(donnees)

    @extend_schema(summary="Retirer une entrée (les projets qui l'utilisent la gardent)")
    def delete(self, request, categorie, pk):
        exiger_superviseur(request)
        cat = _categorie(categorie)
        with schema_context("public"):
            entree = get_object_or_404(ReferentielPlateforme, pk=pk, categorie=cat)
            entree.delete(utilisateur=request.user)
        journaliser_plateforme(
            action="SUPPRESSION_REFERENTIEL",
            acteur=request.user,
            detail={"categorie": cat, "code": entree.code, "libelle": entree.libelle},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
