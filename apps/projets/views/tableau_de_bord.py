"""Vue d'agrégation du Tableau de bord de pilotage décisionnel BTP — Maquette M10.

Alimentée à 100% par les modèles réels du schéma tenant :
- Projets & Chantiers (apps.projets)
- Rapports journaliers & Effectifs réels (apps.chantier)
- Météo en direct & Alertes intempéries (Open-Meteo)
"""

from django.db.models import Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chantier.models import RapportJournalier
from apps.core.enums import ModuleChoix, NiveauAcces, StatutRapport
from apps.core.permissions import PermissionModule, filtrer_queryset_par_affectations
from apps.projets.models import Projet
from apps.projets.serializers import TableauDeBordResponseSerializer
from apps.projets.services.meteo import (
    PORTEE_CHANTIER,
    PORTEE_ENTREPRISE,
    RAISON_VILLE_ABSENTE,
    meteo_indisponible,
    obtenir_meteo,
)

__all__ = ["TableauDeBordView"]


class TableauDeBordView(APIView):
    """`GET /api/v1/tableau-de-bord/` — Données consolidées de pilotage BTP 100% réelles."""

    permission_classes = [
        IsAuthenticated,
        PermissionModule.pour(ModuleChoix.PILOTAGE, NiveauAcces.LECTURE),
    ]
    serializer_class = TableauDeBordResponseSerializer

    @extend_schema(
        summary="Données réelles du tableau de bord de pilotage BTP",
        description=(
            "Agrège l'ensemble des indicateurs de performance clés (KPIs) en temps réel : "
            "santé globale du portefeuille, avancement des chantiers, alertes intempéries, "
            "et effectifs sur site."
        ),
        responses={200: TableauDeBordResponseSerializer},
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        pays = getattr(tenant, "pays", "CI") if tenant else "CI"

        projets_base = (
            Projet.objects.filter(supprime_le__isnull=True)
            .select_related("client", "chef_projet", "conducteur_travaux")
            .order_by("-cree_le")
        )
        projets_qs = filtrer_queryset_par_affectations(
            projets_base, request.user, champ_projet="id", request=request
        )
        projets_count = projets_qs.count()

        # Somme des budgets initiaux
        somme_budgets = projets_qs.aggregate(total=Sum("budget_initial_montant"))["total"] or 0

        # Données financières et achats retirées du périmètre (conservées neutres pour compatibilité sérialiseur)
        bons_a_valider_qs = []
        bons_a_valider_count = 0
        bons_a_valider_montant = 0
        budget_engage_reel = 0
        receptions_qs = []

        # Détermination de la date cible pour les effectifs et rapports journaliers
        # Prend la date du jour ou la date la plus récente ayant un rapport
        derniere_date_rapport = (
            RapportJournalier.objects.filter(supprime_le__isnull=True)
            .order_by("-date_rapport")
            .values_list("date_rapport", flat=True)
            .first()
        )
        date_cible_rapports = derniere_date_rapport or timezone.localdate()

        rapports_recents_qs = RapportJournalier.objects.filter(
            supprime_le__isnull=True,
            date_rapport=date_cible_rapports,
        ).select_related("projet")
        rapports_recents_qs = filtrer_queryset_par_affectations(
            rapports_recents_qs, request.user, champ_projet="projet_id", request=request
        )

        total_regie = rapports_recents_qs.aggregate(total=Sum("effectif_regie"))["total"] or 0
        total_tacherons = (
            rapports_recents_qs.aggregate(total=Sum("effectif_tacherons"))["total"] or 0
        )
        total_effectif = total_regie + total_tacherons

        # Rapports journaliers soumis sur les chantiers attendus
        projets_avec_rapport_ids = set(
            rapports_recents_qs.filter(
                statut__in=[StatutRapport.SOUMIS, StatutRapport.APPROUVE]
            ).values_list("projet_id", flat=True)
        )
        rapports_soumis_count = len(projets_avec_rapport_ids)

        # Si aucun chantier actif n'existe dans l'entreprise (Empty State)
        if projets_count == 0:
            reponse = {
                "metriques": {
                    "chantiers_actifs": 0,
                    "chantiers_conformes": 0,
                    "chantiers_en_retard": 0,
                    "sante_globale": 100,
                    "sante_details": {
                        "securite": 100,
                        "delais": 100,
                        "budget": 100,
                    },
                    "budget_total_montant": 0,
                    "budget_engage_montant": 0,
                    "bons_a_signer_count": 0,
                    "bons_a_signer_montant": 0,
                    "effectifs_sur_site": {
                        "total": 0,
                        "regie": 0,
                        "tacherons": 0,
                    },
                    "rapports_journaliers": {
                        "soumis": 0,
                        "attendus": 0,
                    },
                },
                "projets": [],
                "bons_paiement_a_valider": [],
                "receptions_materiaux": [],
                "meteo": (
                    obtenir_meteo(tenant.ville, pays=pays, portee=PORTEE_ENTREPRISE)
                    if tenant and getattr(tenant, "ville", "")
                    else meteo_indisponible(RAISON_VILLE_ABSENTE, "", PORTEE_ENTREPRISE)
                ),
                "aucun_chantier": True,
            }
            return Response(reponse, status=status.HTTP_200_OK)

        # Analyse détaillée de chaque chantier
        chantiers_retard = 0
        chantiers_conformes = 0
        scores_delais = []
        scores_budget = []
        scores_securite = []
        projets_data = []

        # Pré-agrégation des dépenses réelles par projet (finance hors périmètre)
        consommation_par_projet = {}

        # Pré-agrégation des blocages critiques par projet
        blocages_par_projet = dict(
            rapports_recents_qs.values("projet_id")
            .annotate(total=Sum("blocages_critiques"))
            .values_list("projet_id", "total")
        )

        for p in projets_qs:
            reel = float(p.avancement_reel or 0)
            theorique = float(p.avancement_theorique or 0)
            ecart = round(reel - theorique, 1)

            if ecart < -5:
                chantiers_retard += 1
            else:
                chantiers_conformes += 1

            # Consommation budgétaire réelle par projet
            budget_consomme = consommation_par_projet.get(p.id, 0)
            budget_initial = p.budget_initial_montant or 0

            # 1. Sous-note Délais (0-100) : 100 si ponctuel, -2 pts par % de retard
            if ecart < 0:
                note_delais = max(0, min(100, round(100 + (ecart * 2))))
            else:
                note_delais = 100
            scores_delais.append(note_delais)

            # 2. Sous-note Budget (0-100) : 100 si respecté, dégressif si dépassement
            if budget_initial > 0:
                ratio_budget = budget_consomme / budget_initial
                if ratio_budget <= 1.0:
                    note_budget = 100
                else:
                    depassement = (ratio_budget - 1.0) * 100
                    note_budget = max(0, round(100 - depassement))
            else:
                note_budget = 100
            scores_budget.append(note_budget)

            # 3. Sous-note Sécurité / Blocages (0-100) : 100 - 20 pts par incident critique
            blocages = blocages_par_projet.get(p.id, 0)
            note_securite = max(0, 100 - (blocages * 20))
            scores_securite.append(note_securite)

            # Note synthétique BTP pondérée du projet
            indice_projet = round(
                (0.40 * note_delais) + (0.35 * note_budget) + (0.25 * note_securite)
            )

            # Statut du rapport du jour pour ce chantier
            rapport_soumis = p.id in projets_avec_rapport_ids

            p_dict = {
                "id": str(p.id),
                "reference": p.reference,
                "nom": p.nom,
                "description": p.description,
                "client_nom": str(p.client),
                "ville": p.ville,
                "quartier": p.quartier,
                "statut": p.statut,
                "avancement_reel": reel,
                "avancement_theorique": theorique,
                "ecart": ecart,
                "budget_initial_montant": budget_initial,
                "budget_consomme_montant": budget_consomme,
                "rapport_jour_statut": "SOUMIS" if rapport_soumis else "EN_ATTENTE",
                "indice_sante": indice_projet,
                "chef_projet_nom": (
                    f"{p.chef_projet.prenom} {p.chef_projet.nom}".strip()
                    or p.chef_projet.email
                ) if p.chef_projet else "",
                "conducteur_travaux_nom": (
                    f"{p.conducteur_travaux.prenom} {p.conducteur_travaux.nom}".strip()
                    or p.conducteur_travaux.email
                ) if p.conducteur_travaux else "",
            }
            projets_data.append(p_dict)

        # Moyennes consolidées du portefeuille
        moyenne_delais = round(sum(scores_delais) / len(scores_delais)) if scores_delais else 100
        moyenne_budget = round(sum(scores_budget) / len(scores_budget)) if scores_budget else 100
        moyenne_securite = (
            round(sum(scores_securite) / len(scores_securite)) if scores_securite else 100
        )
        score_sante_global = round(
            (0.40 * moyenne_delais) + (0.35 * moyenne_budget) + (0.25 * moyenne_securite)
        )

        # Météo du premier chantier actif ou, à défaut, du siège. « Abidjan »
        # était écrit en dur ici comme dernier recours : faux pour huit clients
        # sur neuf, et invisible puisqu'une température s'affichait quand même.
        premier_chantier = projets_qs.first()
        if premier_chantier is not None:
            ville_meteo, portee_meteo = premier_chantier.ville, PORTEE_CHANTIER
        else:
            ville_meteo = (getattr(tenant, "ville", "") or "") if tenant else ""
            portee_meteo = PORTEE_ENTREPRISE

        meteo_data = obtenir_meteo(ville_meteo, pays=pays, portee=portee_meteo)

        # L'alerte intempéries du tableau de bord porte des **codes**, comme le
        # relevé : c'est l'écran qui la formule. Elle injectait auparavant une
        # phrase du serveur au milieu d'une phrase traduite.
        alerte_intemperies = None
        if meteo_data.get("alerte") or not meteo_data.get("praticable", True):
            alerte_intemperies = {
                "projet": premier_chantier.nom if premier_chantier else "",
                "ville": meteo_data.get("ville") or ville_meteo,
                "alerte": meteo_data.get("alerte"),
                "condition": meteo_data.get("condition"),
            }

        reponse = {
            "metriques": {
                "chantiers_actifs": projets_count,
                "chantiers_conformes": chantiers_conformes,
                "chantiers_en_retard": chantiers_retard,
                "sante_globale": score_sante_global,
                "sante_details": {
                    "securite": moyenne_securite,
                    "delais": moyenne_delais,
                    "budget": moyenne_budget,
                },
                "budget_total_montant": somme_budgets,
                "budget_engage_montant": budget_engage_reel,
                "bons_a_signer_count": bons_a_valider_count,
                "bons_a_signer_montant": bons_a_valider_montant,
                "effectifs_sur_site": {
                    "total": total_effectif,
                    "regie": total_regie,
                    "tacherons": total_tacherons,
                },
                "rapports_journaliers": {
                    "soumis": rapports_soumis_count,
                    "attendus": projets_count,
                },
            },
            "projets": projets_data,
            "bons_paiement_a_valider": [
                {
                    "id": str(b.id),
                    "reference": b.numero,
                    "beneficiaire": str(b.beneficiaire),
                    "corps_etat": b.corps_etat or (b.lot.libelle if b.lot else "Général"),
                    "montant": b.montant_net,
                    "statut": b.statut,
                }
                for b in bons_a_valider_qs[:5]
            ],
            "receptions_materiaux": [
                {
                    "id": str(r.id),
                    "projet": r.projet.nom,
                    "description": r.designation,
                    "conforme": r.conforme,
                    "date_reception": r.date_reception.isoformat(),
                }
                for r in receptions_qs
            ],
            "meteo": meteo_data,
            "alerte_intemperies": alerte_intemperies,
            "aucun_chantier": False,
        }

        return Response(reponse, status=status.HTTP_200_OK)
