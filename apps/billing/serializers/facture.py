"""Contrat de consultation des factures, montants en centimes XOF."""

from rest_framework import serializers

from apps.billing.models import Facture, PaiementAbonnement


class PaiementFactureSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaiementAbonnement
        fields = ("reference_transaction", "mode", "statut", "montant", "paye_le")
        read_only_fields = fields


class FactureSerializer(serializers.ModelSerializer):
    paiements = PaiementFactureSerializer(many=True, read_only=True)
    statut_affichage = serializers.CharField(source="get_statut_display", read_only=True)
    devise = serializers.CharField(default="XOF", read_only=True)

    class Meta:
        model = Facture
        fields = (
            "id",
            "numero",
            "entreprise",
            "abonnement",
            "statut",
            "statut_affichage",
            "devise",
            "date_emission",
            "date_echeance",
            "periode_debut",
            "periode_fin",
            "montant_ht",
            "taux_tva",
            "montant_tva",
            "montant_ttc",
            "contexte_facturation",
            "paiements",
        )
        read_only_fields = fields
