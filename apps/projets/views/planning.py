"""Vues du planning (Gantt), de la courbe en S et de l'import MS Project (.xml).

- `GET /api/v1/projets/{id}/planning/` : arbre actif du projet, dates contractuelles,
  prévues et baseline, indicateurs physiques/temporels, dépendances et état d'éligibilité
  à l'import MS Project.
- `POST /api/v1/projets/{id}/planning/ms-project/analyser/` : analyse sans écriture d'un
  fichier Microsoft Project `.xml`.
- `POST /api/v1/projets/{id}/planning/ms-project/importer/` : import atomique d'un fichier
  Microsoft Project `.xml` dans le découpage et les dépendances du projet.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import GardePermissionProjet
from apps.projets.models import Dependance, Projet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.selectors.arbre_api import COMPLET, visibilite
from apps.projets.services.dependances import respectee
from apps.projets.services.indicateurs_temporels import calendrier_pour_elements
from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture
from apps.projets.services.ms_project import (
    analyser_ms_project,
    etat_import_ms_project,
    importer_ms_project,
)
from apps.projets.services.perimetres import perimetre_de
from apps.projets.services.sante_calculs import calculer_arbre, calculer_temporels_arbre

__all__ = [
    "ProjetCourbeView",
    "ProjetPlanningMsProjectAnalyserView",
    "ProjetPlanningMsProjectImporterView",
    "ProjetPlanningView",
]


# --------------------------------------------------------------------------
# Serializers OpenAPI & réponse
# --------------------------------------------------------------------------
class EtatImportMsProjectSerializer(serializers.Serializer):
    autorise = serializers.BooleanField()
    decoupage_existant = serializers.BooleanField()
    remplacement_requis = serializers.BooleanField()
    motif_blocage = serializers.CharField(allow_null=True)


class PlanningCaseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    libelle = serializers.CharField()
    numero = serializers.CharField(allow_null=True)
    niveau = serializers.CharField(allow_null=True)
    debut = serializers.DateField(allow_null=True)
    fin = serializers.DateField(allow_null=True)
    debut_prevu = serializers.DateField(allow_null=True)
    fin_prevue = serializers.DateField(allow_null=True)
    debut_baseline = serializers.DateField(allow_null=True)
    fin_baseline = serializers.DateField(allow_null=True)
    avancement = serializers.FloatField(allow_null=True)
    avancement_temporel = serializers.FloatField(allow_null=True)
    delta_retard = serializers.FloatField(allow_null=True)
    statut = serializers.CharField()
    acces = serializers.CharField()
    est_feuille = serializers.BooleanField()
    mode_mesure = serializers.CharField(allow_null=True)
    enfants = serializers.ListField(child=serializers.DictField())


class PlanningDependanceSerializer(serializers.Serializer):
    """Une flèche du Gantt : B commence après la fin de A."""

    id = serializers.UUIDField()
    predecesseur_id = serializers.UUIDField()
    successeur_id = serializers.UUIDField()
    respectee = serializers.BooleanField(
        allow_null=True,
        help_text="Faux : B commence avant la fin de A ; nul : une des deux dates manque.",
    )


class PlanningSerializer(serializers.Serializer):
    aujourdhui = serializers.DateField()
    projet_debut = serializers.DateField(allow_null=True)
    projet_fin = serializers.DateField(allow_null=True)
    import_ms_project = EtatImportMsProjectSerializer()
    cases = PlanningCaseSerializer(many=True)
    dependances = PlanningDependanceSerializer(many=True)


class MsProjectProjetXmlSerializer(serializers.Serializer):
    titre = serializers.CharField(allow_null=True)
    date_debut = serializers.DateField(allow_null=True)
    date_fin = serializers.DateField(allow_null=True)


class MsProjectNiveauSerializer(serializers.Serializer):
    ordre = serializers.IntegerField()
    libelle = serializers.CharField()


class MsProjectTacheSerializer(serializers.Serializer):
    uid = serializers.CharField()
    numero = serializers.CharField()
    libelle = serializers.CharField()
    niveau_ordre = serializers.IntegerField()
    niveau = serializers.CharField()
    debut = serializers.DateField(allow_null=True)
    fin = serializers.DateField(allow_null=True)
    duree_heures = serializers.FloatField(allow_null=True)
    est_jalon = serializers.BooleanField()
    est_feuille = serializers.BooleanField()
    pourcentage_xml = serializers.FloatField(allow_null=True)
    enfants = serializers.ListField(child=serializers.DictField())


class MsProjectDependanceSerializer(serializers.Serializer):
    predecesseur_uid = serializers.CharField()
    predecesseur_libelle = serializers.CharField()
    successeur_uid = serializers.CharField()
    successeur_libelle = serializers.CharField()
    type = serializers.CharField()
    respectee = serializers.BooleanField(allow_null=True)


class MsProjectStatistiquesSerializer(serializers.Serializer):
    total_taches = serializers.IntegerField()
    feuilles = serializers.IntegerField()
    jalons = serializers.IntegerField()
    dependances_retenues = serializers.IntegerField()
    dependances_ignorees = serializers.IntegerField()


class MsProjectAvertissementSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()


class MsProjectAnalyseResponseSerializer(serializers.Serializer):
    etat_import = EtatImportMsProjectSerializer()
    projet_xml = MsProjectProjetXmlSerializer()
    niveaux = MsProjectNiveauSerializer(many=True)
    taches = MsProjectTacheSerializer(many=True)
    dependances = MsProjectDependanceSerializer(many=True)
    statistiques = MsProjectStatistiquesSerializer()
    avertissements = MsProjectAvertissementSerializer(many=True)


class MsProjectImportResponseSerializer(serializers.Serializer):
    elements_crees = serializers.IntegerField()
    niveaux_crees = serializers.IntegerField()
    dependances_creees = serializers.IntegerField()
    remplacement_effectue = serializers.BooleanField()
    avertissements = MsProjectAvertissementSerializer(many=True)
    planning = PlanningSerializer()


# --------------------------------------------------------------------------
# Helpers internes
# --------------------------------------------------------------------------
def _iso(valeur) -> str | None:
    return valeur.isoformat() if valeur else None


def _dates_contractuelles(element) -> tuple[str | None, str | None]:
    """Baseline si la paire est complète, sinon dates prévues (ISO ou None)."""
    if element.date_debut_baseline and element.date_fin_baseline:
        debut, fin = element.date_debut_baseline, element.date_fin_baseline
    else:
        debut, fin = element.date_debut_prevue, element.date_fin_prevue
    return _iso(debut), _iso(fin)


def _arrondi(valeur) -> float | None:
    return None if valeur is None else round(float(valeur), 1)


def _construire_planning(projet: Projet, utilisateur, request) -> dict:
    arbre = charger_arbre(projet, actifs_seulement=True)
    acces = visibilite(arbre, utilisateur, request)
    aujourdhui = timezone.localdate()
    calendrier = calendrier_pour_elements([projet, *arbre.elements], aujourdhui)
    resultats = calculer_arbre(arbre)
    temporels = calculer_temporels_arbre(arbre, resultats, aujourdhui, calendrier)
    numeros = arbre.numerotation()

    def case(element):
        debut, fin = _dates_contractuelles(element)
        resultat = resultats.get(element.pk)
        physique = resultat.physique if resultat else None
        temporel = temporels.get(element.pk)
        complet = acces[element.pk] == COMPLET
        niveau = arbre.niveau(element)
        return {
            "id": str(element.pk),
            "libelle": element.libelle,
            "numero": numeros.get(element.pk),
            "niveau": niveau.libelle if niveau else None,
            "debut": debut if complet else None,
            "fin": fin if complet else None,
            "debut_prevu": _iso(element.date_debut_prevue) if complet else None,
            "fin_prevue": _iso(element.date_fin_prevue) if complet else None,
            "debut_baseline": _iso(element.date_debut_baseline) if complet else None,
            "fin_baseline": _iso(element.date_fin_baseline) if complet else None,
            "avancement": _arrondi(physique) if complet else None,
            "avancement_temporel": _arrondi(temporel) if complet else None,
            "delta_retard": (
                _arrondi(temporel - physique)
                if complet and temporel is not None and physique is not None
                else None
            ),
            "statut": element.statut,
            "acces": acces[element.pk],
            "est_feuille": arbre.est_feuille(element),
            "mode_mesure": element.mode_mesure if complet else None,
            "enfants": [case(e) for e in arbre.enfants_actifs(element) if e.pk in acces],
        }

    projet_debut = (
        projet.date_debut_prevue
        or projet.date_debut_baseline
        or projet.date_debut_contractuelle
    )
    projet_fin = (
        projet.date_fin_prevue
        or projet.date_fin_baseline
        or projet.date_fin_contractuelle
    )

    donnees = {
        "aujourdhui": aujourdhui.isoformat(),
        "projet_debut": _iso(projet_debut),
        "projet_fin": _iso(projet_fin),
        "import_ms_project": etat_import_ms_project(projet),
        "cases": [case(e) for e in arbre.racines() if e.pk in acces],
        # Les flèches entre tâches que la personne voit toutes deux en entier.
        "dependances": [
            {
                "id": lien.pk,
                "predecesseur_id": lien.predecesseur_id,
                "successeur_id": lien.successeur_id,
                "respectee": respectee(
                    arbre.par_id[lien.predecesseur_id], arbre.par_id[lien.successeur_id]
                ),
            }
            for lien in Dependance.objects.filter(projet=projet)
            if acces.get(lien.predecesseur_id) == COMPLET
            and acces.get(lien.successeur_id) == COMPLET
        ],
    }
    return PlanningSerializer(donnees).data


def _exiger_permission_ms_project(request, projet: Projet) -> None:
    """L'analyse ou l'import MS Project exige `projets.decouper` ou `projets.planifier` sur
    l'ensemble du projet."""
    perimetre = perimetre_de(request.user, projet, request)
    if perimetre.peut("projets.decouper") or perimetre.peut("projets.planifier"):
        return
    if perimetre.peut_quelque_part("projets.decouper") or perimetre.peut_quelque_part(
        "projets.planifier"
    ):
        raise PermissionDenied(
            _("Cette action porte sur tout le projet : votre périmètre ne le couvre pas.")
        )
    raise PermissionDenied(
        _(
            "Votre rôle sur ce projet n'a pas la permission « projets.decouper » ou "
            "« projets.planifier »."
        )
    )


def _lire_booleen(valeur) -> bool:
    if isinstance(valeur, bool):
        return valeur
    if valeur is None:
        return False
    texte = str(valeur).strip().lower()
    if texte in ("", "false", "0", "no", "non", "off"):
        return False
    if texte in ("true", "1", "yes", "oui", "on"):
        return True
    raise ValidationError(
        {"confirmer_remplacement": _("Valeur booléenne attendue (true ou false).")}
    )


# --------------------------------------------------------------------------
# Vues API
# --------------------------------------------------------------------------
class ProjetPlanningView(APIView):
    """`GET /api/v1/projets/{id}/planning/` — données complètes du Gantt."""

    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.lire"),
    ]

    @extend_schema(
        summary="Données du planning (Gantt) d'un projet",
        tags=["projets"],
        description=(
            "Cases actives de l'arbre imbriquées avec dates contractuelles, prévues et baseline, "
            "pourcentages arrondis à 1 décimale, mode de mesure, indicateur feuille, dépendances "
            "entre tâches, bornes du projet et état d'éligibilité à l'import MS Project. "
            "Le périmètre de lecture s'applique."
        ),
        responses={
            200: PlanningSerializer,
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Accès au projet refusé."),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
        },
    )
    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        return Response(
            _construire_planning(projet, request.user, request),
            status=status.HTTP_200_OK,
        )


class ProjetPlanningMsProjectAnalyserView(APIView):
    """`POST /api/v1/projets/{id}/planning/ms-project/analyser/` — aperçu sans écriture."""

    parser_classes = [MultiPartParser]
    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.lire"),
    ]

    @extend_schema(
        summary="Analyser un fichier Microsoft Project (.xml) sans écriture",
        tags=["projets"],
        description=(
            "Valide et analyse un fichier Microsoft Project `.xml` (20 Mo max, protection "
            "anti-XXE) afin de prévisualiser les niveaux, tâches, jalons, dépendances FS "
            "retenues, statistiques et avertissements avant import."
        ),
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "fichier": {"type": "string", "format": "binary"},
                },
                "required": ["fichier"],
            }
        },
        responses={
            200: MsProjectAnalyseResponseSerializer,
            400: OpenApiResponse(description="Fichier absent, invalide ou rejeté."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(
                description="Permission projets.decouper ou projets.planifier requise."
            ),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
        },
    )
    def post(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        _exiger_permission_ms_project(request, projet)
        fichier = request.FILES.get("fichier")
        if fichier is None:
            raise ValidationError({"fichier": _("Joignez un fichier MS Project au format .xml.")})
        resultat = analyser_ms_project(projet, fichier)
        return Response(resultat, status=status.HTTP_200_OK)


class ProjetPlanningMsProjectImporterView(APIView):
    """`POST /api/v1/projets/{id}/planning/ms-project/importer/` — import atomique MS Project."""

    parser_classes = [MultiPartParser]
    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.lire"),
    ]

    @extend_schema(
        summary="Importer un planning Microsoft Project (.xml) dans le projet",
        tags=["projets"],
        description=(
            "Crée les niveaux, tâches, jalons et dépendances Fin→Début depuis un fichier "
            "Microsoft Project `.xml`. Bloqué (`import_ms_project_bloque`) si l'exécution du "
            "projet a déjà démarré. Si un découpage non démarré existe déjà, exige "
            "`confirmer_remplacement=true` (`remplacement_decoupage_requis`) et supprime "
            "logiquement l'ancien découpage."
        ),
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "fichier": {"type": "string", "format": "binary"},
                    "confirmer_remplacement": {"type": "boolean", "default": False},
                },
                "required": ["fichier"],
            }
        },
        responses={
            201: MsProjectImportResponseSerializer,
            400: OpenApiResponse(description="Fichier absent, invalide ou rejeté."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(
                description="Permission projets.decouper ou projets.planifier requise."
            ),
            404: OpenApiResponse(description="Projet absent ou supprimé."),
            409: OpenApiResponse(description="Projet clos (lecture seule)."),
            422: OpenApiResponse(
                description=(
                    "Import bloqué (projet démarré) ou confirmation de remplacement requise."
                )
            ),
        },
    )
    def post(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        verifier_statut_projet_pour_ecriture(projet)
        _exiger_permission_ms_project(request, projet)

        fichier = request.FILES.get("fichier")
        if fichier is None:
            raise ValidationError({"fichier": _("Joignez un fichier MS Project au format .xml.")})
        confirmer = _lire_booleen(request.data.get("confirmer_remplacement"))

        resultat = importer_ms_project(
            projet,
            fichier,
            auteur=request.user,
            confirmer_remplacement=confirmer,
        )
        projet.refresh_from_db()
        planning = _construire_planning(projet, request.user, request)
        return Response(
            {**resultat, "planning": planning},
            status=status.HTTP_201_CREATED,
        )


class ProjetCourbeView(APIView):
    """`GET /api/v1/projets/{id}/courbe/?element=<id>` — la courbe en S (30/10/2026).

    Le prévu (dates et montants), le réel (relevés de nuit et valeur du jour) et la fin estimée
    au rythme des 4 dernières semaines, affichée seulement. Sans `element` : le projet entier.
    """

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @extend_schema(
        summary="Courbe en S d'un projet ou d'une case",
        tags=["projets"],
        parameters=[OpenApiParameter("element", str, description="Une case ; vide : le projet.")],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request, pk):
        from apps.projets.models import Element
        from apps.projets.services.courbe import courbe

        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        element = None
        if request.query_params.get("element"):
            element = get_object_or_404(
                Element,
                pk=request.query_params["element"],
                projet=projet,
                est_actif=True,
            )
            arbre = charger_arbre(projet, actifs_seulement=True)
            acces = visibilite(arbre, request.user, request)
            if acces.get(element.pk) != COMPLET:
                raise PermissionDenied("Cette case est en dehors de votre périmètre.")
        return Response(courbe(projet, element))
