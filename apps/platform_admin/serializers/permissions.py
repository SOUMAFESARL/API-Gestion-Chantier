"""Serializers pour la gestion des permissions par le Super Admin."""

from rest_framework import serializers

from apps.accounts.models import Permission

__all__ = [
    "AdminPermissionCreateSerializer",
    "AdminPermissionSerializer",
    "AdminPermissionUpdateSerializer",
]


class AdminPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = [
            "id",
            "code",
            "libelle",
            "description",
            "ordre",
            "est_actif",
            "cree_le",
            "modifie_le",
        ]


class AdminPermissionCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    libelle = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    ordre = serializers.IntegerField(required=False, default=0, min_value=0)
    est_actif = serializers.BooleanField(required=False, default=True)

    def validate_code(self, value: str) -> str:
        code = value.strip().upper()
        if not code:
            raise serializers.ValidationError("Le code de la permission est obligatoire.")
        if Permission.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise serializers.ValidationError(f"Une permission avec le code '{code}' existe déjà.")
        return code

    def validate_libelle(self, value: str) -> str:
        libelle = value.strip()
        if not libelle:
            raise serializers.ValidationError("Le libellé de la permission est obligatoire.")
        return libelle


class AdminPermissionUpdateSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    ordre = serializers.IntegerField(required=False, min_value=0)
    est_actif = serializers.BooleanField(required=False)
