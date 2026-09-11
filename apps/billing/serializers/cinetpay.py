"""Sérialiseurs pour l'intégration de paiement CinetPay et catalogue des forfaits."""

from rest_framework import serializers

from apps.billing.models import Plan

__all__ = [
    "InitierPaiementRequestSerializer",
    "InitierPaiementResponseSerializer",
    "PlanCatalogueSerializer",
    "StatutPaiementResponseSerializer",
]


class PlanCatalogueSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la présentation des forfaits BTP aux utilisateurs."""

    prix_mensuel_fcfa = serializers.SerializerMethodField()
    prix_annuel_fcfa = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "libelle",
            "prix_mensuel_montant",
            "prix_mensuel_fcfa",
            "prix_annuel_montant",
            "prix_annuel_fcfa",
            "limite_projets",
            "limite_utilisateurs",
            "limite_stockage_mo",
            "acces_ia",
            "est_actif",
        ]

    def get_prix_mensuel_fcfa(self, obj: Plan) -> int | None:
        return int(obj.prix_mensuel_montant // 100) if obj.prix_mensuel_montant else None

    def get_prix_annuel_fcfa(self, obj: Plan) -> int | None:
        return int(obj.prix_annuel_montant // 100) if obj.prix_annuel_montant else None


class InitierPaiementRequestSerializer(serializers.Serializer):
    """Paramètres pour demander l'ouverture d'une session de paiement."""

    plan_code = serializers.ChoiceField(
        choices=Plan.Code.choices,
        help_text="Code du forfait souhaité (BATISSEUR, MAITRE_OEUVRE, PROMOTEUR)",
    )
    cycle = serializers.ChoiceField(
        choices=["MENSUEL", "ANNUEL"],
        default="MENSUEL",
        help_text="Périodicité de facturation (MENSUEL ou ANNUEL)",
    )
    return_url = serializers.URLField(
        required=False,
        allow_blank=True,
        help_text="URL frontend de retour personnalisé après paiement",
    )


class InitierPaiementResponseSerializer(serializers.Serializer):
    """Réponse contenant l'URL du guichet CinetPay vers lequel rediriger le client."""

    transaction_id = serializers.CharField()
    payment_url = serializers.CharField()
    payment_token = serializers.CharField(required=False, allow_null=True)
    numero_facture = serializers.CharField()
    montant_fcfa = serializers.IntegerField()
    forfait = serializers.CharField()
    cycle = serializers.CharField()
    mode_simulation = serializers.BooleanField()


class StatutPaiementResponseSerializer(serializers.Serializer):
    """Consultation de l'état d'un paiement (pour la page de retour frontend)."""

    transaction_id = serializers.CharField()
    statut = serializers.CharField()
    statut_affichage = serializers.CharField()
    mode_paiement = serializers.CharField(required=False, allow_null=True)
    moyen_paiement = serializers.CharField(required=False, allow_null=True)
    montant_fcfa = serializers.IntegerField(required=False, allow_null=True)
    numero_facture = serializers.CharField(required=False, allow_null=True)
    reference_facture = serializers.CharField(required=False, allow_null=True)
    paye_le = serializers.DateTimeField(required=False, allow_null=True)
    abonnement_actif = serializers.BooleanField()
    est_valide = serializers.BooleanField(required=False)
    date_fin = serializers.DateField(required=False, allow_null=True)
    abonnement_expire_le = serializers.CharField(required=False, allow_null=True)
    entreprise = serializers.CharField(required=False, allow_null=True)
    plan = serializers.CharField(required=False, allow_null=True)
