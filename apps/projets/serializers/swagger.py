"""Contrats OpenAPI distincts ; validation métier dans ProjetCreationSerializer."""

from drf_spectacular.utils import extend_schema_serializer

from apps.projets.serializers import ProjetCreationSerializer


@extend_schema_serializer(exclude_fields=["id", "lots_supprimer_ids"])
class ProjetPostSerializer(ProjetCreationSerializer):
    """Informations, lots restants du formulaire et équipe à créer ensemble."""


@extend_schema_serializer(
    exclude_fields=[
        "id",
        "equipe",
        "chef_projet_invite",
        "conducteur_travaux_invite",
        "chefs_chantier_ids",
        "visiteurs_ids",
    ]
)
class ProjetPatchSerializer(ProjetCreationSerializer):
    """Champs modifiables et opérations groupées sur les lots."""
