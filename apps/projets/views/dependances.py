"""Routes des dépendances entre tâches (§13quinquies.5 ; amendement 25/11/2026).

Quatre types de lien (`FS`, `SS`, `FF`, `SF`) avec décalage signé en jours ouvrés.
Créer ou retirer un lien exige `projets.planifier` dans le périmètre **des deux** tâches ;
les lire exige de voir la case en entier.

Les vues restent sans logique : permission, validation, service, réponse
(`services.dependances`).
"""

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projets.models import Dependance, Element
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.selectors.arbre_api import COMPLET, visibilite
from apps.projets.serializers.decoupage import DependanceCreationSerializer
from apps.projets.services import dependances as service
from apps.projets.services.perimetres import exiger
from apps.projets.views.decoupage import _element, schema

__all__ = ["DependanceDetailView", "ElementDependancesView"]


def _acces_complet(request, element) -> dict:
    acces = visibilite(charger_arbre(element.projet), request.user, request)
    if acces.get(element.pk) != COMPLET:
        raise PermissionDenied(
            _(
                "Vous ne voyez que l'intitulé de cette case : ses dépendances sont hors de votre "
                "périmètre."
            )
        )
    return acces


def _lien_en_dict(lien) -> dict:
    a, b = lien.predecesseur, lien.successeur
    return {
        "id": str(lien.pk),
        "type_lien": lien.type_lien,
        "decalage_jours": lien.decalage_jours,
        "predecesseur": {
            "id": str(a.pk),
            "libelle": a.libelle,
            "date_debut_prevue": a.date_debut_prevue,
            "date_fin_prevue": a.date_fin_prevue,
        },
        "successeur": {
            "id": str(b.pk),
            "libelle": b.libelle,
            "date_debut_prevue": b.date_debut_prevue,
            "date_fin_prevue": b.date_fin_prevue,
        },
        "respectee": service.respectee(lien),
    }


class ElementDependancesView(APIView):
    """`GET`/`POST /api/v1/elements/{id}/dependances/` — les liens d'une tâche."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @schema(summary="Prédécesseurs et successeurs d'une tâche")
    def get(self, request, pk):
        element = _element(request, pk)
        acces = _acces_complet(request, element)
        return Response({"element_id": str(element.pk), **service.liens_de_la_case(element, acces)})

    @schema(
        summary="Lier deux tâches (FS, SS, FF ou SF avec décalage en jours ouvrés)",
        request=DependanceCreationSerializer,
    )
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        donnees = DependanceCreationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        autre_id = donnees.validated_data.get("predecesseur_id") or donnees.validated_data.get(
            "successeur_id"
        )
        autre = get_object_or_404(Element, pk=autre_id, projet=element.projet)
        if donnees.validated_data.get("predecesseur_id"):
            predecesseur, successeur = autre, element
        else:
            predecesseur, successeur = element, autre
        for case in (predecesseur, successeur):
            exiger(request.user, "projets.planifier", element.projet, case, request=request)
        lien = service.ajouter_lien(
            predecesseur,
            successeur,
            type_lien=donnees.validated_data["type_lien"],
            decalage_jours=donnees.validated_data["decalage_jours"],
            auteur=request.user,
        )
        return Response(_lien_en_dict(lien), status=status.HTTP_201_CREATED)


class DependanceDetailView(APIView):
    """`DELETE /api/v1/dependances/{id}/` — retirer un lien (suppression logique)."""

    permission_classes = [IsAuthenticated]

    @schema(summary="Retirer un lien entre deux tâches", responses={204: None})
    def delete(self, request, pk):
        lien = get_object_or_404(
            Dependance.objects.select_related("predecesseur", "successeur", "projet"), pk=pk
        )
        _element(request, lien.successeur_id, ecriture=True)
        for case in (lien.predecesseur, lien.successeur):
            exiger(request.user, "projets.planifier", lien.projet, case, request=request)
        service.retirer_lien(lien, auteur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
