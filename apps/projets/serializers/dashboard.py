"""Serializers pour le tableau de bord consolidé de pilotage BTP."""

from rest_framework import serializers


class SanteDetailsSerializer(serializers.Serializer):
    """Sous-notes de santé du portefeuille de chantiers (0-100)."""

    securite = serializers.IntegerField(help_text="Sous-note sécurité basée sur les incidents.")
    delais = serializers.IntegerField(help_text="Sous-note respect des plannings.")
    budget = serializers.IntegerField(help_text="Sous-note maîtrise budgétaire.")


class EffectifsSurSiteSerializer(serializers.Serializer):
    """Effectifs d'ouvriers et tâcherons présents ce jour."""

    total = serializers.IntegerField(help_text="Total des effectifs mobilisés.")
    regie = serializers.IntegerField(help_text="Effectifs salariés en régie.")
    tacherons = serializers.IntegerField(help_text="Effectifs des sous-traitants et tâcherons.")


class RapportsJournaliersStatutSerializer(serializers.Serializer):
    """Avancement de la soumission des rapports quotidiens."""

    soumis = serializers.IntegerField(help_text="Nombre de rapports soumis aujourd'hui.")
    attendus = serializers.IntegerField(
        help_text="Nombre total de rapports attendus (chantiers actifs)."
    )


class MetriquesDashboardSerializer(serializers.Serializer):
    """Indicateurs clés de performance (KPIs) consolidés."""

    chantiers_actifs = serializers.IntegerField(
        help_text="Nombre de chantiers actuellement en cours."
    )
    chantiers_conformes = serializers.IntegerField(
        help_text="Chantiers dans les délais et budgets."
    )
    chantiers_en_retard = serializers.IntegerField(
        help_text="Chantiers présentant un retard d'exécution."
    )
    sante_globale = serializers.IntegerField(
        help_text="Score synthétique de santé globale (0 à 100)."
    )
    sante_details = SanteDetailsSerializer()
    budget_total_montant = serializers.IntegerField(
        help_text="Montant total des budgets alloués (en centimes FCFA)."
    )
    budget_engage_montant = serializers.IntegerField(
        help_text="Montant réel engagé (en centimes FCFA)."
    )
    bons_a_signer_count = serializers.IntegerField(
        help_text="Nombre de bons de paiement en attente de signature."
    )
    bons_a_signer_montant = serializers.IntegerField(
        help_text="Montant total des bons en attente de signature (en centimes FCFA)."
    )
    effectifs_sur_site = EffectifsSurSiteSerializer()
    rapports_journaliers = RapportsJournaliersStatutSerializer()


class ProjetDashboardItemSerializer(serializers.Serializer):
    """Synthèse d'un chantier affichée sur le tableau de bord."""

    id = serializers.UUIDField()
    reference = serializers.CharField()
    nom = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    client_nom = serializers.CharField()
    ville = serializers.CharField()
    quartier = serializers.CharField(allow_blank=True)
    statut = serializers.CharField()
    avancement_reel = serializers.IntegerField()
    avancement_theorique = serializers.IntegerField()
    ecart = serializers.IntegerField()
    budget_initial_montant = serializers.IntegerField(allow_null=True)
    budget_consomme_montant = serializers.IntegerField()
    rapport_jour_statut = serializers.CharField(help_text="SOUMIS ou EN_ATTENTE")
    indice_sante = serializers.IntegerField(help_text="Note sur 100")
    chef_projet_nom = serializers.CharField()
    conducteur_travaux_nom = serializers.CharField()


class BonPaiementDashboardItemSerializer(serializers.Serializer):
    """Bon de paiement urgent nécessitant signature ou validation."""

    id = serializers.UUIDField()
    reference = serializers.CharField()
    beneficiaire = serializers.CharField()
    corps_etat = serializers.CharField()
    montant = serializers.IntegerField(help_text="Montant net en centimes FCFA")
    statut = serializers.CharField()


class ReceptionMateriauDashboardItemSerializer(serializers.Serializer):
    """Réception récente d'approvisionnement sur chantier."""

    id = serializers.UUIDField()
    projet = serializers.CharField()
    description = serializers.CharField()
    conforme = serializers.BooleanField()
    date_reception = serializers.CharField()


class AlerteIntemperiesSerializer(serializers.Serializer):
    """Alerte météo critique impactant la sécurité ou le travail sur chantier."""

    projet = serializers.CharField()
    ville = serializers.CharField()
    alerte = serializers.CharField(required=False, allow_null=True)
    condition = serializers.CharField(required=False, allow_null=True)


class TableauDeBordResponseSerializer(serializers.Serializer):
    """Réponse complète de l'agrégation de pilotage décisionnel BTP."""

    metriques = MetriquesDashboardSerializer()
    projets = ProjetDashboardItemSerializer(many=True)
    bons_paiement_a_valider = BonPaiementDashboardItemSerializer(many=True)
    receptions_materiaux = ReceptionMateriauDashboardItemSerializer(many=True)
    meteo = serializers.DictField(help_text="Données météo du premier chantier ou du siège.")
    alerte_intemperies = AlerteIntemperiesSerializer(required=False, allow_null=True)
    aucun_chantier = serializers.BooleanField(
        help_text="True si l'entreprise n'a encore créé aucun chantier."
    )
