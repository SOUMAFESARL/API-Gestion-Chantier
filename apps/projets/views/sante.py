"""Vues pour la consultation de l'indice de santé d'un projet BTP."""

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import GardePermissionProjet
from apps.projets.models import Projet, SanteProjetSnapshot
from apps.projets.serializers.sante import (
    SanteApercuSerializer,
    SanteDetailResponseSerializer,
    SanteHistoriqueItemSerializer,
)
from apps.projets.services.sante_calculs import calculer_indice_sante_projet

__all__ = [
    "ProjetSanteApercuView",
    "ProjetSanteDetailView",
    "ProjetSanteHistoriqueView",
]


class ProjetSanteApercuView(APIView):
    """`GET /api/v1/projets/{id}/sante/` — Synthèse de santé du projet."""

    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.lire"),
    ]

    @extend_schema(
        summary="Aperçu de la santé du projet",
        description="Renvoie le score de santé consolidé (0-100), le badge opérationnel et les métriques d'avancement.",
        responses={200: SanteApercuSerializer},
    )
    def get(self, request, pk):
        projet = get_object_or_404(
            Projet.objects.filter(supprime_le__isnull=True),
            pk=pk,
        )
        self.check_object_permissions(request, projet)

        reel = float(projet.avancement_reel or 0)
        theorique = float(projet.avancement_theorique or 0)
        ecart = round(reel - theorique, 1)

        indice = projet.indice_sante
        badge = projet.badge_sante
        if indice is None and projet.statut == StatutProjet.EN_ATTENTE:
            indice = 100
            badge = "VERT"

        data = {
            "projet_id": projet.id,
            "reference": projet.reference,
            "nom": projet.nom,
            "statut": projet.statut,
            "avancement_reel": reel,
            "avancement_theorique": theorique,
            "ecart": ecart,
            "indice_sante": indice,
            "badge_sante": badge,
            "calcule_le": projet.indice_sante_calcule_le,
        }
        serializer = SanteApercuSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProjetSanteHistoriqueView(APIView):
    """`GET /api/v1/projets/{id}/sante/historique/` — Historique des snapshots de santé."""

    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.lire"),
    ]

    @extend_schema(
        summary="Historique des snapshots de santé",
        description="Liste l'historique chronologique des calculs et pénalités de santé enregistrés pour ce projet.",
        responses={200: SanteHistoriqueItemSerializer(many=True)},
    )
    def get(self, request, pk):
        projet = get_object_or_404(
            Projet.objects.filter(supprime_le__isnull=True),
            pk=pk,
        )
        self.check_object_permissions(request, projet)

        snapshots = SanteProjetSnapshot.objects.filter(projet=projet).order_by("-date_calcul")[:30]
        serializer = SanteHistoriqueItemSerializer(snapshots, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProjetSanteDetailView(APIView):
    """`GET /api/v1/projets/{id}/sante/detail/` — Décomposition exhaustive du calcul de santé."""

    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.lire"),
    ]

    @extend_schema(
        summary="Détail exhaustif du calcul d'indice de santé",
        description=(
            "Fournit la transparence totale sur les composantes de calcul : avancement physique et temporel, "
            "retard en points (retard_pts), seuil toléré, pénalité délais, inventaire des blocages par sévérité, "
            "pénalité blocages, taux de couverture des rapports journaliers sur 14 jours, plancher de gravité "
            "et éventuels avertissements (ex: JOURS_FERIES_INCOMPLETS)."
        ),
        responses={200: SanteDetailResponseSerializer},
    )
    def get(self, request, pk):
        projet = get_object_or_404(
            Projet.objects.filter(supprime_le__isnull=True),
            pk=pk,
        )
        self.check_object_permissions(request, projet)

        res = calculer_indice_sante_projet(projet)

        seuil_retard = float(getattr(settings, "SANTE_SEUIL_RETARD_TOLERE_PTS", 5.0))
        data = {
            "projet_id": projet.id,
            "statut": projet.statut,
            "etat_calcul": res.etat,
            "score": res.score,
            "badge": res.badge_final,
            "badge_brut": res.badge_brut,
            "avancement_physique": res.avancement_physique,
            "avancement_temporel": res.avancement_temporel,
            "retard_pts": res.retard_pts,
            "seuil_retard": seuil_retard,
            "penalite_delais": res.p_delais,
            "blocages_critiques": res.blocages_ouverts_par_severite.get("CRITIQUE", 0),
            "blocages_majeurs": res.blocages_ouverts_par_severite.get("MAJEUR", 0),
            "blocages_moderes": res.blocages_ouverts_par_severite.get("MINEUR", 0),
            "penalite_blocages": res.p_blocages,
            "taux_reporting": res.taux_reporting,
            "penalite_reporting": res.p_reporting,
            "plancher_applique": res.plancher_applique,
            "formule_appliquee": "max(0, 100 - (P_delais + P_blocages + P_reporting))",
            "avertissements": res.avertissements,
            "calcule_le": projet.indice_sante_calcule_le or timezone.now(),
        }
        serializer = SanteDetailResponseSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
