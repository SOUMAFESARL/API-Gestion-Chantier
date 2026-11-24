"""Serializers pour l'application tiers."""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.core.enums import RoleTiersChoix, TypeTiers
from apps.tiers.models import RoleTiers, Tiers
from apps.tiers.selectors import (
    nombre_projets_par_tiers,
    projets_lies_du_tiers,
    references_du_tiers,
)
from apps.tiers.services import creer_tiers, modifier_tiers

__all__ = [
    "RoleTiersSerializer",
    "TiersCreationSerializer",
    "TiersDetailSerializer",
    "TiersSerializer",
]


class RoleTiersSerializer(serializers.ModelSerializer):
    libelle = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = RoleTiers
        fields = ["id", "role", "libelle"]


class TiersSerializer(serializers.ModelSerializer):
    type_tiers_libelle = serializers.CharField(source="get_type_tiers_display", read_only=True)
    roles = RoleTiersSerializer(many=True, read_only=True)
    roles_codes = serializers.SerializerMethodField()
    nombre_projets = serializers.SerializerMethodField()

    class Meta:
        model = Tiers
        fields = [
            "id",
            "type_tiers",
            "type_tiers_libelle",
            "raison_sociale",
            "rccm",
            "nif",
            "telephone",
            "email",
            "adresse",
            "ville",
            "note_evaluation",
            "est_actif",
            "roles",
            "roles_codes",
            "nombre_projets",
            "cree_le",
            "modifie_le",
        ]

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_roles_codes(self, obj: Tiers) -> list[str]:
        return [r.role for r in obj.roles.all() if r.supprime_le is None]

    @extend_schema_field(serializers.IntegerField())
    def get_nombre_projets(self, obj: Tiers) -> int:
        nombres = (self.context or {}).get("nombres_projets")
        if nombres is not None:
            return int(nombres.get(obj.pk, 0))
        return int(nombre_projets_par_tiers([obj.pk]).get(obj.pk, 0))


class TiersDetailSerializer(TiersSerializer):
    """Forme détaillée d'un tiers avec les projets liés et l'état de référencement."""

    projets_lies = serializers.SerializerMethodField()
    est_reference = serializers.SerializerMethodField()

    class Meta(TiersSerializer.Meta):
        fields = [
            *TiersSerializer.Meta.fields,
            "projets_lies",
            "est_reference",
        ]

    def _projets_lies(self, obj: Tiers) -> list[dict]:
        if not hasattr(obj, "_projets_lies_cache"):
            obj._projets_lies_cache = projets_lies_du_tiers(obj)
        return obj._projets_lies_cache

    @extend_schema_field(serializers.IntegerField())
    def get_nombre_projets(self, obj: Tiers) -> int:
        return len(self._projets_lies(obj))

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_projets_lies(self, obj: Tiers) -> list[dict]:
        return self._projets_lies(obj)

    @extend_schema_field(serializers.BooleanField())
    def get_est_reference(self, obj: Tiers) -> bool:
        return bool(references_du_tiers(obj))


class TiersCreationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    type_tiers = serializers.ChoiceField(choices=TypeTiers.choices, default=TypeTiers.ENTREPRISE)
    raison_sociale = serializers.CharField(max_length=200)
    telephone = serializers.CharField(max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    adresse = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    ville = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    rccm = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    nif = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    note_evaluation = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("5"),
        required=False,
        allow_null=True,
    )
    est_actif = serializers.BooleanField(required=False, default=True)
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=RoleTiersChoix.choices),
        required=False,
        default=list,
    )

    def validate_raison_sociale(self, value: str) -> str:
        propre = (value or "").strip()
        if not propre:
            raise serializers.ValidationError(_("La raison sociale est obligatoire."))
        return propre

    def validate_telephone(self, value: str) -> str:
        propre = (value or "").strip()
        if not propre:
            raise serializers.ValidationError(_("Le numéro de téléphone est obligatoire."))
        return propre

    def create(self, validated_data):
        request = (self.context or {}).get("request")
        auteur = getattr(request, "user", None) if request else None
        return creer_tiers(validated_data, auteur=auteur)

    def update(self, instance, validated_data):
        request = (self.context or {}).get("request")
        auteur = getattr(request, "user", None) if request else None
        return modifier_tiers(instance, validated_data, auteur=auteur)
