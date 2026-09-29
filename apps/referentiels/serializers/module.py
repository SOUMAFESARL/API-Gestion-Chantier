"""Serializers pour le catalogue des modules et niveaux d'accès."""

from rest_framework import serializers

__all__ = ["ModuleItemSerializer", "NiveauAccesDetailSerializer"]


class NiveauAccesDetailSerializer(serializers.Serializer):
    """Niveau d'accès supporté pour un module (RBAC)."""

    niveau = serializers.IntegerField(help_text="Valeur numérique du niveau d'accès (0 à 3)")
    code = serializers.CharField(help_text="Code symbolique du niveau (AUCUN, LECTURE, ECRITURE, VALIDATION)")
    libelle = serializers.CharField(help_text="Libellé lisible du niveau d'accès en français")


class ModuleItemSerializer(serializers.Serializer):
    """Description détaillée d'un module applicatif souverain de CCD Digital."""

    code = serializers.CharField(help_text="Code technique unique du module (ex: projets, chantier)")
    libelle = serializers.CharField(help_text="Libellé officiel du module")
    description = serializers.CharField(help_text="Description du périmètre métier du module")
    ordre = serializers.IntegerField(help_text="Position ordonnée d'affichage dans la navigation")
    icone = serializers.CharField(help_text="Identifiant d'icône recommandé pour le client frontend")
    niveaux_supportes = NiveauAccesDetailSerializer(
        many=True,
        help_text="Liste des 4 niveaux d'accès RBAC supportés par ce module",
    )
