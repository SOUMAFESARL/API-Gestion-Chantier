"""Donnees publiques de la demande, sans jeton ni empreinte de mot de passe."""

from rest_framework import serializers

from apps.tenants.models import DemandeInscription


class DemandeInscriptionAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = DemandeInscription
        fields = (
            "id",
            "raison_sociale",
            "pays",
            "email",
            "nom",
            "prenom",
            "statut",
            "cree_le",
            "utilise_le",
            "decision_par",
            "decision_le",
            "motif_refus",
            "entreprise",
        )
        read_only_fields = fields


class RefusInscriptionSerializer(serializers.Serializer):
    motif = serializers.CharField(max_length=1000, allow_blank=False, trim_whitespace=True)
