"""Serializers pour le catalogue des modules et autorisations granulaires."""

from rest_framework import serializers

__all__ = [
    "ModuleItemSerializer",
    "PermissionItemSerializer",
]


class PermissionItemSerializer(serializers.Serializer):
    """Autorisation granulaire dynamique supportée par un module."""

    id = serializers.UUIDField(help_text="Identifiant unique de la permission")
    code = serializers.CharField(help_text="Code technique de la permission (ex: projets.lire, chantier.valider)")
    libelle = serializers.CharField(help_text="Libellé officiel de la permission")
    description = serializers.CharField(help_text="Description du périmètre de l'autorisation", allow_blank=True, default="")
    ordre = serializers.IntegerField(help_text="Position ordonnée d'affichage")


class ModuleItemSerializer(serializers.Serializer):
    """Description détaillée d'un module applicatif souverain de CCD Digital."""

    id = serializers.CharField(required=False, help_text="Identifiant unique du module")
    code = serializers.CharField(help_text="Code technique unique du module (ex: projets, chantier)")
    libelle = serializers.CharField(help_text="Libellé officiel du module")
    description = serializers.CharField(help_text="Description du périmètre métier du module")
    ordre = serializers.IntegerField(help_text="Position ordonnée d'affichage dans la navigation")
    icone = serializers.CharField(help_text="Identifiant d'icône recommandé pour le client frontend")
    statut = serializers.CharField(required=False, default="ACTIF", help_text="Statut d'activation du module (ACTIF/INACTIF)")
    permissions = PermissionItemSerializer(
        many=True,
        required=False,
        help_text="Liste des autorisations granulaires dynamiques supportées par ce module",
    )
    permissions_codes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Liste plate des codes des autorisations supportées par ce module",
    )
