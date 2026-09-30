"""Serializers pour la gestion des modules par le Super Admin."""

from rest_framework import serializers

from apps.accounts.models import Module

__all__ = [
    "AdminModuleCreateSerializer",
    "AdminModuleDetailSerializer",
    "AdminModuleListSerializer",
    "AdminModuleUpdateSerializer",
]


class AdminModuleListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = [
            "id",
            "code",
            "libelle",
            "description",
            "ordre",
            "icone",
            "est_actif",
            "cree_le",
            "modifie_le",
        ]


class AdminModuleDetailSerializer(AdminModuleListSerializer):
    class Meta(AdminModuleListSerializer.Meta):
        fields = AdminModuleListSerializer.Meta.fields


class AdminModuleCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=30)
    libelle = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    ordre = serializers.IntegerField(required=False, default=0, min_value=0)
    icone = serializers.CharField(required=False, allow_blank=True, default="box", max_length=50)
    est_actif = serializers.BooleanField(required=False, default=True)

    def validate_code(self, value: str) -> str:
        code = value.strip().lower()
        if not code:
            raise serializers.ValidationError("Le code du module est obligatoire.")
        if Module.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise serializers.ValidationError(f"Un module avec le code '{code}' existe déjà.")
        return code

    def validate_libelle(self, value: str) -> str:
        libelle = value.strip()
        if not libelle:
            raise serializers.ValidationError("Le libellé du module est obligatoire.")
        return libelle


class AdminModuleUpdateSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    ordre = serializers.IntegerField(required=False, min_value=0)
    icone = serializers.CharField(required=False, allow_blank=True, max_length=50)
    est_actif = serializers.BooleanField(required=False)
