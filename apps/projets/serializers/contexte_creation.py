"""Contrat de préparation du formulaire de création de projet."""

from rest_framework import serializers

from apps.accounts.serializers.profil import (
    ProfilDetailResponseSerializer,
    ProfilEntrepriseSerializer,
)
from apps.projets.serializers import ChefProjetEnrichiSerializer


class CollaborateurProjetChoixSerializer(ChefProjetEnrichiSerializer):
    assignable_responsable = serializers.SerializerMethodField()

    class Meta(ChefProjetEnrichiSerializer.Meta):
        fields = [
            *ChefProjetEnrichiSerializer.Meta.fields,
            "role_global",
            "assignable_responsable",
        ]

    def get_assignable_responsable(self, obj) -> bool:
        return not (obj.is_dg or obj.is_owner)


class ClientProjetChoixSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    raison_sociale = serializers.CharField()


class ChoixProjetSerializer(serializers.Serializer):
    valeur = serializers.CharField()
    libelle = serializers.CharField()


class ContexteCreationProjetSerializer(serializers.Serializer):
    utilisateur = ProfilDetailResponseSerializer()
    entreprise = ProfilEntrepriseSerializer()
    collaborateurs = CollaborateurProjetChoixSerializer(many=True)
    clients = ClientProjetChoixSerializer(many=True)
    types_projet = ChoixProjetSerializer(many=True)
    modes_execution = ChoixProjetSerializer(many=True)
    types_bordereau = ChoixProjetSerializer(many=True)
    roles_projet = ChoixProjetSerializer(many=True)
