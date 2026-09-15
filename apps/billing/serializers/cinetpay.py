"""Sérialiseurs pour l'intégration de paiement CinetPay et catalogue des forfaits."""

from rest_framework import serializers

from apps.billing.models import Plan

__all__ = [
    "AnnulerPaiementRequestSerializer",
    "AnnulerPaiementResponseSerializer",
    "CinetPayWebhookRequestSerializer",
    "CinetPayWebhookResponseSerializer",
    "InitierPaiementRequestSerializer",
    "InitierPaiementResponseSerializer",
    "PaiementEnCoursSerializer",
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


class AnnulerPaiementRequestSerializer(serializers.Serializer):
    """Paramètres pour annuler explicitement une transaction en cours (Option A2)."""

    transaction_id = serializers.CharField(
        help_text="Identifiant de transaction CinetPay ou référence de commande à annuler",
    )
    motif = serializers.CharField(
        required=False,
        default="Annulation demandée par l'utilisateur",
        help_text="Motif facultatif de l'annulation",
    )


class AnnulerPaiementResponseSerializer(serializers.Serializer):
    """Réponse confirmant l'annulation d'une transaction."""

    statut = serializers.CharField()
    transaction_id = serializers.CharField()
    message = serializers.CharField()


class PaiementEnCoursSerializer(serializers.Serializer):
    """Détail d'un paiement en cours de confirmation Mobile Money."""

    transaction_id = serializers.CharField()
    reference_facture = serializers.CharField()
    montant_fcfa = serializers.IntegerField()
    forfait = serializers.CharField()
    statut = serializers.CharField()
    secondes_restantes = serializers.IntegerField()
    cree_le = serializers.CharField(required=False, allow_null=True)


class CinetPayWebhookRequestSerializer(serializers.Serializer):
    """Charge utile envoyée par CinetPay lors de la notification IPN."""

    cpm_trans_id = serializers.CharField(
        required=False, help_text="Identifiant de transaction CinetPay"
    )
    transaction_id = serializers.CharField(
        required=False, help_text="Identifiant alternatif de transaction"
    )
    cpm_site_id = serializers.CharField(required=False, help_text="Identifiant du site marchand")
    cpm_amount = serializers.CharField(required=False, help_text="Montant encaissé")
    cpm_trans_status = serializers.CharField(
        required=False, help_text="Code statut CinetPay (00 = succès)"
    )
    cpm_custom = serializers.CharField(
        required=False, help_text="Données personnalisées / référence commande"
    )


class CinetPayWebhookResponseSerializer(serializers.Serializer):
    """Accusé de réception retourné à CinetPay."""

    status = serializers.CharField(help_text="ACCEPTED, REJECTED, ou IGNORED")
    message = serializers.CharField(help_text="Message descriptif du traitement")
    transaction_id = serializers.CharField(
        required=False, help_text="Identifiant de transaction traitée"
    )
