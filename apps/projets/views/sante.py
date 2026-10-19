"""Vues pour la consultation de l'indice de santé d'un projet BTP."""

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import SeveriteBlocage, StatutBlocage, StatutProjet
from apps.core.permissions import GardePermissionProjet
from apps.projets.models import Projet, SanteProjetSnapshot
from apps.projets.serializers.sante import (
    SanteApercuSerializer,
    SanteDetailResponseSerializer,
    SanteHistoriqueItemSerializer,
)
from apps.projets.services.indicateurs_temporels import indicateurs_temporels_projet
from apps.projets.services.indice_sante import STATUTS_SANTE_FIGES, evaluer_indice_sante
from apps.projets.services.sante_calculs import calculer_avancement_physique_projet

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

        indics = indicateurs_temporels_projet(projet)
        theorique = indics["avancement_temporel"]
        reel = float(projet.avancement_reel or 0)
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

        # Détermination de l'état de calcul
        statut = projet.statut
        if statut == StatutProjet.EN_ATTENTE:
            etat_calcul = "NON_DEMARRE"
        elif statut in STATUTS_SANTE_FIGES:
            etat_calcul = "FIGE"
        else:
            etat_calcul = "ACTIF"

        seuil_retard = float(getattr(settings, "SANTE_SEUIL_RETARD_TOLERE_PTS", 5.0))

        if etat_calcul == "ACTIF":
            res = evaluer_indice_sante(projet)
            score = res.indice
            badge = res.badge
            scores = res.scores
            retard_pts = res.delta
            av_physique, _ = calculer_avancement_physique_projet(projet)
            av_temporel = float(round(av_physique + res.delta, 2))
            avancement_physique = av_physique
            avancement_temporel = av_temporel
            taux_reporting = round(res.taux_rapports / 100, 4)
            avertissements = res.avertissements
            calcule_le = projet.indice_sante_calcule_le or timezone.now()

            severites_actives = list(
                projet.blocages.filter(
                    supprime_le__isnull=True,
                    statut__in=[StatutBlocage.OUVERT, StatutBlocage.PRIS_EN_CHARGE],
                ).values_list("severite", flat=True)
            )
            blocages_critiques = severites_actives.count(SeveriteBlocage.CRITIQUE)
            blocages_majeurs = severites_actives.count(SeveriteBlocage.MAJEUR)
            blocages_moderes = severites_actives.count(SeveriteBlocage.MINEUR)
        else:
            # NON_DEMARRE ou FIGE : rien n'est recalculé en direct
            score = projet.indice_sante
            badge = projet.badge_sante

            snapshot = (
                SanteProjetSnapshot.objects.filter(projet=projet)
                .order_by("-date_calcul")
                .first()
                if etat_calcul == "FIGE"
                else None
            )

            if snapshot:
                snap_scores = snapshot.scores if isinstance(snapshot.scores, dict) else {}
                scores = {
                    k: int(snap_scores[k])
                    for k in ("delais", "rapports", "blocages", "incidents")
                    if k in snap_scores and snap_scores[k] is not None
                }
                retard_pts = float(snapshot.delta)
                avancement_physique = float(snapshot.avancement_physique)
                avancement_temporel = float(snapshot.avancement_temporel)
                taux_reporting = float(snapshot.taux_reporting)
                avertissements = []
                calcule_le = snapshot.date_calcul
                blocages_critiques = (
                    int(snapshot.blocages_ouverts_par_severite.get("CRITIQUE", 0))
                    if isinstance(snapshot.blocages_ouverts_par_severite, dict)
                    else 0
                )
                blocages_majeurs = (
                    int(snapshot.blocages_ouverts_par_severite.get("MAJEUR", 0))
                    if isinstance(snapshot.blocages_ouverts_par_severite, dict)
                    else 0
                )
                blocages_moderes = (
                    int(snapshot.blocages_ouverts_par_severite.get("MINEUR", 0))
                    if isinstance(snapshot.blocages_ouverts_par_severite, dict)
                    else 0
                )
            else:
                # Sans snapshot, ou pour NON_DEMARRE
                scores = {}
                retard_pts = 0.0
                avancement_physique = float(projet.avancement_reel or 0)
                avancement_temporel = float(projet.avancement_theorique or 0)
                taux_reporting = 1.0
                avertissements = []
                calcule_le = projet.indice_sante_calcule_le
                blocages_critiques = 0
                blocages_majeurs = 0
                blocages_moderes = 0

        data = {
            "projet_id": projet.id,
            "statut": projet.statut,
            "etat_calcul": etat_calcul,
            "score": score,
            "badge": badge,
            "badge_brut": badge,
            "scores": scores,
            "avancement_physique": avancement_physique,
            "avancement_temporel": avancement_temporel,
            "retard_pts": retard_pts,
            "seuil_retard": seuil_retard,
            "penalite_delais": 0.0,
            "blocages_critiques": blocages_critiques,
            "blocages_majeurs": blocages_majeurs,
            "blocages_moderes": blocages_moderes,
            "penalite_blocages": 0.0,
            "taux_reporting": taux_reporting,
            "penalite_reporting": 0.0,
            "plancher_applique": False,
            "formule_appliquee": "arrondi(somme(score * ponderation / 100))",
            "avertissements": avertissements,
            "calcule_le": calcule_le,
        }
        serializer = SanteDetailResponseSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
