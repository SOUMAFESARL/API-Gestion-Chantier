"""Serializers pour la consultation de l'indice de santé des projets."""

from rest_framework import serializers


class SanteApercuSerializer(serializers.Serializer):
    """Aperçu synthétique de la santé d'un projet."""

    projet_id = serializers.UUIDField(help_text="Identifiant unique du projet.")
    reference = serializers.CharField(help_text="Référence contractuelle du projet.")
    nom = serializers.CharField(help_text="Intitulé du projet.")
    statut = serializers.CharField(help_text="Statut calendaire actuel du projet.")
    avancement_reel = serializers.FloatField(
        allow_null=True, help_text="Avancement physique pondéré réel (%)."
    )
    avancement_theorique = serializers.FloatField(
        allow_null=True, help_text="Avancement temporel théorique (%)."
    )
    ecart = serializers.FloatField(
        allow_null=True, help_text="Écart d'avancement réel - théorique (pts)."
    )
    indice_sante = serializers.IntegerField(
        allow_null=True, help_text="Score synthétique de santé (0-100)."
    )
    badge_sante = serializers.CharField(
        allow_null=True, help_text="Badge opérationnel (VERT, ORANGE, ROUGE)."
    )
    calcule_le = serializers.DateTimeField(
        allow_null=True, help_text="Horodatage du dernier calcul."
    )


class SanteHistoriqueItemSerializer(serializers.Serializer):
    """Snapshot historique d'un calcul d'indice de santé."""

    id = serializers.UUIDField(help_text="Identifiant unique du snapshot.")
    score = serializers.IntegerField(help_text="Score de santé (0-100).")
    badge = serializers.CharField(help_text="Badge de santé final.")
    penalite_delais = serializers.FloatField(help_text="Pénalité Délais (pts).")
    penalite_blocages = serializers.FloatField(help_text="Pénalité Blocages (pts).")
    penalite_reporting = serializers.FloatField(help_text="Pénalité Reporting (pts).")
    retard_pts = serializers.FloatField(help_text="Retard temporel en points de pourcentage.")
    avancement_physique = serializers.FloatField(help_text="Avancement physique (%).")
    avancement_temporel = serializers.FloatField(help_text="Avancement temporel (%).")
    taux_reporting = serializers.FloatField(help_text="Taux de couverture des rapports journaliers (%).")
    calcule_le = serializers.DateTimeField(help_text="Date et heure du snapshot.")


class SanteDetailResponseSerializer(serializers.Serializer):
    """Détail exhaustif du calcul de l'indice de santé du projet."""

    projet_id = serializers.UUIDField(help_text="Identifiant unique du projet.")
    statut = serializers.CharField(help_text="Statut calendaire du projet.")
    etat_calcul = serializers.CharField(help_text="État du calcul : NON_DEMARRE, ACTIF, FIGE.")
    score = serializers.IntegerField(
        allow_null=True, help_text="Score final d'indice de santé (0-100)."
    )
    badge = serializers.CharField(
        allow_null=True, help_text="Badge final (après application du plancher)."
    )
    badge_brut = serializers.CharField(
        allow_null=True, help_text="Badge brut avant application du plancher."
    )

    # Indicateurs d'avancement
    avancement_physique = serializers.FloatField(help_text="Avancement physique pondéré (%).")
    avancement_temporel = serializers.FloatField(help_text="Avancement temporel théorique (%).")
    retard_pts = serializers.FloatField(
        help_text="Retard en points (temporel - physique ; positif si retard)."
    )
    seuil_retard = serializers.FloatField(help_text="Seuil de retard toléré avant pénalité (pts).")
    penalite_delais = serializers.FloatField(help_text="Pénalité Délais appliquée (pts, max 40).")

    # Blocages
    blocages_critiques = serializers.IntegerField(help_text="Nombre de blocages critiques ouverts.")
    blocages_majeurs = serializers.IntegerField(help_text="Nombre de blocages majeurs ouverts.")
    blocages_moderes = serializers.IntegerField(help_text="Nombre de blocages modérés/mineurs ouverts.")
    penalite_blocages = serializers.FloatField(help_text="Pénalité Blocages appliquée (pts, max 35).")

    # Reporting
    taux_reporting = serializers.FloatField(
        help_text="Taux de rapports journaliers soumis/approuvés sur 14 jours (%)."
    )
    penalite_reporting = serializers.FloatField(help_text="Pénalité Reporting appliquée (pts, max 25).")

    # Gouvernance et règles
    plancher_applique = serializers.BooleanField(
        help_text="True si un plancher de gravité a forcé un déclassement de badge."
    )
    formule_appliquee = serializers.CharField(help_text="Expression mathématique de la formule.")
    avertissements = serializers.ListField(
        child=serializers.CharField(),
        help_text="Liste des avertissements (ex: JOURS_FERIES_INCOMPLETS).",
    )
    calcule_le = serializers.DateTimeField(
        allow_null=True, help_text="Horodatage du calcul ou dernier snapshot."
    )
