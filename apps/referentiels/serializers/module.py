"""Serializers pour le catalogue des modules et niveaux d'accès."""

from rest_framework import serializers

__all__ = [
    "ModuleItemSerializer",
    "NiveauAccesDetailSerializer",
    "PermissionItemSerializer",
]


class NiveauAccesDetailSerializer(serializers.Serializer):
    """[Déprécié] Niveau d'accès scalaire pour un module (rétrocompatibilité)."""

    niveau = serializers.IntegerField(help_text="Valeur numérique du niveau d'accès (0 à 3)")
    code = serializers.CharField(help_text="Code symbolique du niveau (AUCUN, LECTURE, ECRITURE, VALIDATION)")
    libelle = serializers.CharField(help_text="Libellé lisible du niveau d'accès en français")


class PermissionItemSerializer(serializers.Serializer):
    """Autorisation granulaire dynamique supportée par un module."""

    id = serializers.UUIDField(help_text="Identifiant unique de la permission")
    code = serializers.CharField(help_text="Code technique de la permission (ex: LECTURE, ECRITURE, VALIDATION)")
    libelle = serializers.CharField(help_text="Libellé officiel de la permission")
    description = serializers.CharField(help_text="Description du périmètre de l'autorisation", allow_blank=True, default="")
    ordre = serializers.IntegerField(help_text="Position ordonnée d'affichage")


class ModuleItemSerializer(serializers.Serializer):
    """Description détaillée d'un module applicatif souverain de CCD Digital."""

    code = serializers.CharField(help_text="Code technique unique du module (ex: projets, chantier)")
    libelle = serializers.CharField(help_text="Libellé officiel du module")
    description = serializers.CharField(help_text="Description du périmètre métier du module")
    ordre = serializers.IntegerField(help_text="Position ordonnée d'affichage dans la navigation")
    icone = serializers.CharField(help_text="Identifiant d'icône recommandé pour le client frontend")
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
    niveaux_supportes = NiveauAccesDetailSerializer(
        many=True,
        required=False,
        help_text="[Déprécié] Liste des 4 niveaux d'accès RBAC supportés par ce module (rétrocompatibilité)",
    )
