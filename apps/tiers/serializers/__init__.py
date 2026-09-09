"""Serializers pour l'application tiers."""

from rest_framework import serializers

from apps.core.enums import RoleTiersChoix, TypeTiers
from apps.tiers.models import RoleTiers, Tiers

__all__ = ["RoleTiersSerializer", "TiersCreationSerializer", "TiersSerializer"]


class RoleTiersSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleTiers
        fields = ["id", "role"]


class TiersSerializer(serializers.ModelSerializer):
    roles = RoleTiersSerializer(many=True, read_only=True)

    class Meta:
        model = Tiers
        fields = [
            "id",
            "type_tiers",
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
        ]


class TiersCreationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    type_tiers = serializers.ChoiceField(choices=TypeTiers.choices, default=TypeTiers.ENTREPRISE)
    raison_sociale = serializers.CharField(max_length=200)
    telephone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    adresse = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    ville = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    rccm = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    nif = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=RoleTiersChoix.choices),
        required=False,
        default=list,
    )

    def create(self, validated_data):
        roles_data = validated_data.pop("roles", [])
        tiers = Tiers.objects.create(**validated_data)
        for r in roles_data:
            RoleTiers.objects.get_or_create(tiers=tiers, role=r)
        return tiers

    def update(self, instance, validated_data):
        roles_data = validated_data.pop("roles", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if roles_data is not None:
            instance.roles.all().delete()
            for r in roles_data:
                RoleTiers.objects.get_or_create(tiers=instance, role=r)
        return instance
