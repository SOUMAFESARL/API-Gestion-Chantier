"""API de la synthèse périodique, sous /api/v1/chantier/syntheses/.

- `GET  syntheses/?projet=&type=&date_debut=&date_fin=` — la synthèse d'une période ;
- `GET  syntheses/suivi/?projet=` — où en sont les synthèses enregistrées ;
- `POST syntheses/redaction/` — le CT enregistre son appréciation et ses objectifs ;
- `POST syntheses/soumettre/` — le CT enregistre et signe ;
- `POST syntheses/{id}/approuver/` et `syntheses/{id}/rejeter/` — le CP décide.

Une synthèse n'a d'identifiant qu'une fois que le CT y a écrit : avant, elle
se désigne par son chantier et sa période, comme dans l'adresse de l'écran.
"""

from datetime import timedelta
from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chantier.models import SynthesePeriodique
from apps.chantier.permissions import (
    PeutConsulterRapports,
    PeutRedigerRapports,
    PeutValiderRapports,
)
from apps.chantier.selectors.journal import projets_visibles
from apps.chantier.selectors.synthese import projection, suivi
from apps.chantier.serializers.journal import RejetJournalSerializer, SignatureJournalSerializer
from apps.chantier.serializers.synthese import (
    DemandeSyntheseSerializer,
    RedactionSyntheseSerializer,
)
from apps.chantier.services.journal import aujourdhui
from apps.chantier.services.synthese import (
    approuver_synthese,
    enregistrer_synthese,
    rejeter_synthese,
    soumettre_synthese,
)

#: Le suivi remonte assez loin pour couvrir les trois derniers mois proposés à l'écran.
PROFONDEUR_SUIVI = timedelta(days=100)

ETIQUETTE = ["Journal de chantier — synthèse"]


def _projet(view, request, identifiant):
    projet = get_object_or_404(projets_visibles(request), pk=identifiant)
    view.check_object_permissions(request, projet)
    return projet


def _reponse(request, synthese):
    return Response(
        projection(request, synthese.projet, synthese.type, synthese.date_debut, synthese.date_fin)
    )


class SyntheseView(APIView):
    permission_classes = [IsAuthenticated, PeutConsulterRapports]

    @extend_schema(
        tags=ETIQUETTE,
        parameters=[DemandeSyntheseSerializer],
        responses=OpenApiTypes.OBJECT,
        summary="Lire la synthèse d'un chantier sur une semaine, un mois ou une période libre",
        operation_id="journal_synthese_lire",
    )
    def get(self, request):
        demande = DemandeSyntheseSerializer(data=request.query_params)
        demande.is_valid(raise_exception=True)
        params = demande.validated_data
        projet = _projet(self, request, params["projet"])
        return Response(
            projection(request, projet, params["type"], params["date_debut"], params["date_fin"])
        )


class SyntheseSuiviView(APIView):
    permission_classes = [IsAuthenticated, PeutConsulterRapports]

    @extend_schema(
        tags=ETIQUETTE,
        responses=OpenApiTypes.OBJECT,
        summary="Où en sont les synthèses enregistrées des chantiers visibles",
        operation_id="journal_synthese_suivi",
    )
    def get(self, request):
        projet_id = request.query_params.get("projet")
        if projet_id:
            try:
                UUID(projet_id)
            except ValueError:
                raise ValidationError({"projet": "Identifiant de chantier invalide."}) from None
        return Response(
            {
                "resultats": suivi(
                    request, projet_id=projet_id, depuis=aujourdhui() - PROFONDEUR_SUIVI
                )
            }
        )


class SyntheseRedactionView(APIView):
    """Le CT tient l'accès « validation » du journal : c'est lui qui rédige la synthèse."""

    permission_classes = [IsAuthenticated, PeutValiderRapports]
    soumettre = False

    def _rediger(self, request):
        serializer = RedactionSyntheseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data
        projet = _projet(self, request, donnees["projet"])
        redaction = {
            "projet": projet,
            "type_": donnees["type"],
            "debut": donnees["date_debut"],
            "fin": donnees["date_fin"],
            "utilisateur": request.user,
            "appreciation": donnees["appreciation"],
            "objectifs": [dict(objectif) for objectif in donnees["objectifs"]],
        }
        if self.soumettre:
            return _reponse(request, soumettre_synthese(request=request, **redaction))
        return _reponse(request, enregistrer_synthese(**redaction))

    @extend_schema(
        tags=ETIQUETTE,
        request=RedactionSyntheseSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Enregistrer l'appréciation et les objectifs du conducteur de travaux",
        operation_id="journal_synthese_rediger",
    )
    def post(self, request):
        return self._rediger(request)


class SyntheseSoumettreView(SyntheseRedactionView):
    soumettre = True

    @extend_schema(
        tags=ETIQUETTE,
        request=RedactionSyntheseSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Enregistrer et signer la synthèse au nom du conducteur de travaux",
        operation_id="journal_synthese_soumettre",
    )
    def post(self, request):
        return self._rediger(request)


def _synthese(view, request, pk):
    synthese = get_object_or_404(
        SynthesePeriodique.objects.select_related("projet").filter(
            projet__in=projets_visibles(request)
        ),
        pk=pk,
    )
    view.check_object_permissions(request, synthese)
    return synthese


class SyntheseApprouverView(APIView):
    # Comme pour le rapport : le gabarit CP tient `chantier.rediger`, et le
    # service exige en plus la fonction de chef de projet sur le chantier.
    permission_classes = [IsAuthenticated, PeutRedigerRapports]

    @extend_schema(
        tags=ETIQUETTE,
        request=SignatureJournalSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Approuver la synthèse au niveau CP",
        operation_id="journal_synthese_approuver",
    )
    def post(self, request, pk):
        synthese = _synthese(self, request, pk)
        serializer = SignatureJournalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        synthese = approuver_synthese(
            synthese=synthese,
            utilisateur=request.user,
            commentaire=serializer.validated_data["commentaire"],
        )
        return _reponse(request, synthese)


class SyntheseRejeterView(APIView):
    permission_classes = [IsAuthenticated, PeutValiderRapports | PeutRedigerRapports]

    @extend_schema(
        tags=ETIQUETTE,
        request=RejetJournalSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Rejeter la synthèse au niveau CP, avec motif",
        operation_id="journal_synthese_rejeter",
    )
    def post(self, request, pk):
        synthese = _synthese(self, request, pk)
        serializer = RejetJournalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        synthese = rejeter_synthese(
            synthese=synthese, utilisateur=request.user, motif=serializer.validated_data["motif"]
        )
        return _reponse(request, synthese)
