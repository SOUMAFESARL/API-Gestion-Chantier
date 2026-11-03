"""`/api/v1/admins/decoupage/…` — listes de valeurs et modèles de découpage de la plateforme.

Ce qui s'écrit ici est lu aussitôt par toutes les entreprises, sans copie (décisions v1.2, §3.3
et §4.1). La lecture est ouverte au SUPPORT ; l'écriture est réservée au SUPERVISEUR
(`exiger_superviseur`, en tête de chaque méthode d'écriture).

Les vues restent sans logique : permission, validation, service, réponse
(`apps.platform_admin.services.decoupage`).
"""

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform_admin.permissions import EstSuperAdminPlateforme, exiger_superviseur
from apps.platform_admin.serializers.decoupage import (
    AjoutValeursSerializer,
    CreationListeSerializer,
    ModelePlateformeEnregistrementSerializer,
    ModificationListeSerializer,
    ModificationValeurSerializer,
)
from apps.platform_admin.services import decoupage as service

__all__ = [
    "DecoupageListeDetailView",
    "DecoupageListeModeleExcelView",
    "DecoupageListeValeursImporterView",
    "DecoupageListeValeursView",
    "DecoupageListesView",
    "DecoupageModeleDetailView",
    "DecoupageModeleExcelView",
    "DecoupageModeleImporterFichierView",
    "DecoupageModelesView",
    "DecoupageValeurDetailView",
]

TAGS = ["admins — découpage"]


def schema(**options):
    """Les réponses sont des représentations composées, décrites dans `docs/`."""
    options.setdefault("tags", TAGS)
    options.setdefault("responses", OpenApiTypes.OBJECT)
    return extend_schema(**options)


def _niveaux(niveaux: list[dict]) -> list[dict]:
    """Les références de liste validées portent un UUID : on les rend en texte."""
    return [
        {
            **n,
            "liste": {"origine": n["liste"]["origine"], "id": str(n["liste"]["id"])}
            if n.get("liste")
            else None,
        }
        for n in niveaux
    ]


# --------------------------------------------------------------------------
# Listes de valeurs
# --------------------------------------------------------------------------
class DecoupageListesView(APIView):
    """`GET`/`POST /api/v1/admins/decoupage/listes/`."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @schema(
        summary="Listes de valeurs de la plateforme",
        operation_id="admins_decoupage_listes_liste",
        parameters=[OpenApiParameter("valeurs", bool, description="Faux : sans les valeurs.")],
    )
    def get(self, request):
        avec = request.query_params.get("valeurs", "true").lower() != "false"
        return Response(service.lister_listes(avec_valeurs=avec))

    @schema(summary="Créer une liste de la plateforme", request=CreationListeSerializer)
    def post(self, request):
        exiger_superviseur(request)
        donnees = CreationListeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        liste = service.creer_liste(**donnees.validated_data, auteur=request.user)
        return Response(liste, status=status.HTTP_201_CREATED)


class DecoupageListeDetailView(APIView):
    """`GET`/`PATCH`/`DELETE /api/v1/admins/decoupage/listes/{id}/`."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @schema(summary="Une liste de la plateforme et ses valeurs")
    def get(self, request, pk):
        return Response(service.lire_liste(pk))

    @schema(
        summary="Renommer, décrire ou réordonner une liste", request=ModificationListeSerializer
    )
    def patch(self, request, pk):
        exiger_superviseur(request)
        donnees = ModificationListeSerializer(data=request.data, partial=True)
        donnees.is_valid(raise_exception=True)
        return Response(
            service.modifier_liste(pk, donnees=donnees.validated_data, auteur=request.user)
        )

    @schema(summary="Retirer une liste (suppression logique)", responses={204: None})
    def delete(self, request, pk):
        exiger_superviseur(request)
        service.retirer_liste(pk, auteur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DecoupageListeValeursView(APIView):
    """`POST /api/v1/admins/decoupage/listes/{id}/valeurs/` — ajout en masse, sans doublon."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @schema(
        summary="Ajouter des valeurs à une liste de la plateforme", request=AjoutValeursSerializer
    )
    def post(self, request, pk):
        exiger_superviseur(request)
        donnees = AjoutValeursSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        resultat = service.ajouter_valeurs(pk, **donnees.validated_data, auteur=request.user)
        return Response(resultat, status=status.HTTP_201_CREATED)


class DecoupageListeValeursImporterView(APIView):
    """`POST /api/v1/admins/decoupage/listes/{id}/valeurs/importer/` — import Excel/CSV."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [MultiPartParser]

    @schema(
        summary="Importer les valeurs d'une liste de la plateforme depuis un fichier Excel ou CSV",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"fichier": {"type": "string", "format": "binary"}},
                "required": ["fichier"],
            }
        },
    )
    def post(self, request, pk):
        exiger_superviseur(request)
        fichier = request.FILES.get("fichier")
        if fichier is None:
            raise ValidationError({"fichier": "Joignez un fichier .xlsx ou .csv."})
        resultat = service.importer_valeurs_fichier(pk, fichier=fichier, auteur=request.user)
        return Response(resultat, status=status.HTTP_201_CREATED)


class DecoupageListeModeleExcelView(APIView):
    """`GET /api/v1/admins/decoupage/listes/modele-excel/` — exemple type Excel à remplir."""

    permission_classes = [EstSuperAdminPlateforme]

    @schema(
        summary="Télécharger le modèle Excel d'import de liste de valeurs",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request):
        from django.http import HttpResponse

        from apps.projets.services.listes_modeles import generer_modele_excel_liste

        contenu, type_mime = generer_modele_excel_liste()
        reponse = HttpResponse(contenu, content_type=type_mime)
        reponse["Content-Disposition"] = 'attachment; filename="modele-liste-valeurs.xlsx"'
        return reponse


class DecoupageValeurDetailView(APIView):
    """`PATCH`/`DELETE /api/v1/admins/decoupage/valeurs/{id}/`."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @schema(summary="Corriger une valeur de la plateforme", request=ModificationValeurSerializer)
    def patch(self, request, pk):
        exiger_superviseur(request)
        donnees = ModificationValeurSerializer(data=request.data, partial=True)
        donnees.is_valid(raise_exception=True)
        return Response(
            service.modifier_valeur(pk, donnees=donnees.validated_data, auteur=request.user)
        )

    @schema(summary="Retirer une valeur de la plateforme", responses={204: None})
    def delete(self, request, pk):
        exiger_superviseur(request)
        service.retirer_valeur(pk, auteur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# Modèles de découpage
# --------------------------------------------------------------------------
class DecoupageModelesView(APIView):
    """`GET`/`POST /api/v1/admins/decoupage/modeles/`."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @schema(
        summary="Modèles de découpage de la plateforme",
        operation_id="admins_decoupage_modeles_liste",
    )
    def get(self, request):
        return Response(service.lister_modeles())

    @schema(
        summary="Créer un modèle de la plateforme",
        request=ModelePlateformeEnregistrementSerializer,
    )
    def post(self, request):
        exiger_superviseur(request)
        donnees = ModelePlateformeEnregistrementSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        valides = {**donnees.validated_data, "niveaux": _niveaux(donnees.validated_data["niveaux"])}
        modele = service.enregistrer_modele(auteur=request.user, **valides)
        return Response(modele, status=status.HTTP_201_CREATED)


class DecoupageModeleDetailView(APIView):
    """`GET`/`PUT`/`DELETE /api/v1/admins/decoupage/modeles/{id}/`."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [JSONParser]

    @schema(summary="Un modèle de la plateforme, avec son gabarit et ses lignes types")
    def get(self, request, pk):
        return Response(service.lire_modele(pk))

    @schema(
        summary="Mettre à jour un modèle de la plateforme (sa version augmente)",
        request=ModelePlateformeEnregistrementSerializer,
    )
    def put(self, request, pk):
        exiger_superviseur(request)
        donnees = ModelePlateformeEnregistrementSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        valides = {**donnees.validated_data, "niveaux": _niveaux(donnees.validated_data["niveaux"])}
        return Response(service.enregistrer_modele(pk, auteur=request.user, **valides))

    @schema(
        summary="Mettre à jour un modèle de la plateforme (sa version augmente)",
        request=ModelePlateformeEnregistrementSerializer,
    )
    def patch(self, request, pk):
        return self.put(request, pk)

    @schema(
        summary="Retirer un modèle de la plateforme (suppression logique)", responses={204: None}
    )
    def delete(self, request, pk):
        exiger_superviseur(request)
        service.retirer_modele(pk, auteur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DecoupageModeleExcelView(APIView):
    """`GET /api/v1/admins/decoupage/modeles/modele-excel/` — exemple type Excel (.xlsx)."""

    permission_classes = [EstSuperAdminPlateforme]

    @schema(
        summary="Télécharger un exemple type Excel (.xlsx) de modèle de découpage",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request):
        from django.http import HttpResponse

        from apps.projets.services.import_export import generer_modele_excel_decoupage

        contenu = generer_modele_excel_decoupage()
        reponse = HttpResponse(
            contenu,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        reponse["Content-Disposition"] = 'attachment; filename="modele-decoupage-plateforme.xlsx"'
        return reponse


class DecoupageModeleImporterFichierView(APIView):
    """`POST /api/v1/admins/decoupage/modeles/importer-fichier/` — extrait niveaux et lignes."""

    permission_classes = [EstSuperAdminPlateforme]
    parser_classes = [MultiPartParser]

    @schema(
        summary="Importer les niveaux et lignes d'un modèle depuis un fichier Excel ou CSV",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"fichier": {"type": "string", "format": "binary"}},
                "required": ["fichier"],
            }
        },
    )
    def post(self, request):
        from apps.projets.services.import_export import importer_modele_fichier

        exiger_superviseur(request)
        fichier = request.FILES.get("fichier")
        if fichier is None:
            raise ValidationError({"fichier": "Joignez un fichier .xlsx ou .csv."})
        return Response(importer_modele_fichier(fichier, pour_plateforme=True))
