"""Serializers pour les indicateurs et tendances de la plateforme."""

from rest_framework import serializers


class IndicateursPlateformeSerializer(serializers.Serializer):
    """Indicateurs clés consolidés de la plateforme (KPIs)."""

    nb_clients = serializers.IntegerField(help_text="Nombre total d'entreprises clientes.")
    nb_clients_actifs = serializers.IntegerField(help_text="Nombre d'entreprises actives.")
    nb_clients_en_essai = serializers.IntegerField(
        help_text="Nombre d'entreprises en période d'essai."
    )
    nb_clients_impayes = serializers.IntegerField(help_text="Nombre d'entreprises ayant un impayé.")
    revenu_mensuel_centimes = serializers.IntegerField(
        help_text="Revenu mensuel récurrent (MRR) en centimes FCFA."
    )


class TendanceIndicateurSerializer(serializers.Serializer):
    """Tendance historique sparkline et variation mensuelle d'un indicateur."""

    cle = serializers.ChoiceField(
        choices=[
            "nb_clients",
            "nb_clients_actifs",
            "nb_clients_en_essai",
            "nb_clients_impayes",
            "revenu_mensuel_centimes",
        ],
        help_text="Clé identifiant l'indicateur.",
    )
    points = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Historique chronologique des 5 derniers points.",
    )
    variation_pourcent = serializers.IntegerField(
        help_text="Variation relative en pourcentage par rapport au mois précédent."
    )


class PointEvolutionSerializer(serializers.Serializer):
    """Point journalier pour le graphique des renouvellements sur 90 jours."""

    date = serializers.CharField(help_text="Date au format ISO YYYY-MM-DD.")
    renouveles = serializers.IntegerField(help_text="Nombre d'abonnements renouvelés ce jour.")
    non_renouveles = serializers.IntegerField(
        help_text="Nombre d'abonnements non renouvelés ce jour."
    )
