"""Contrats OpenAPI distincts ; validation métier dans ProjetCreationSerializer."""

from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.projets.serializers import ProjetCreationSerializer


@extend_schema_serializer(exclude_fields=["id", "lots_supprimer_ids"])
class ProjetPostSerializer(ProjetCreationSerializer):
    """Identification initiale, avec planning et équipe facultatifs pour la direction."""

    maitre_ouvrage = serializers.CharField(
        max_length=200,
        required=False,
        help_text="Nom de l'entreprise ou du particulier. Requis sauf si client est fourni.",
    )
    reference = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        default="",
        help_text="Générée automatiquement au format PRJ-AAAA-NNN si omise ou vide.",
    )
    date_debut_prevue = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Facultative : le planning peut être défini après création via PATCH.",
    )
    date_fin_prevue = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Facultative. Strictement après le début lorsque les deux dates sont définies.",
    )
    chef_projet_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "Facultatif. La création de projet est réservée à la direction."
        ),
    )


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
