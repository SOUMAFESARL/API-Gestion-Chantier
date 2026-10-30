"""Serializers des rôles système gérés par le super admin (gabarits `ModeleRole`)."""

from rest_framework import serializers

from apps.catalogue.models import ModeleRole

__all__ = [
    "RoleSystemeCreationSerializer",
    "RoleSystemeModificationSerializer",
    "RoleSystemeSerializer",
]

class RoleSystemeSerializer(serializers.ModelSerializer):
    modules = serializers.SerializerMethodField()

    class Meta:
        model = ModeleRole
        fields = ["id", "code", "libelle", "description", "portee", "unique_par_projet", "modules"]

    def get_modules(self, obj: ModeleRole) -> list[str]:
        return sorted(
            m.module_code for m in obj.modules_plafonds.all() if m.supprime_le is None
        )


class RoleSystemeCreationSerializer(serializers.Serializer):
    code = serializers.RegexField(
        r"^[A-Za-z][A-Za-z0-9_]{1,29}$",
        error_messages={
            "invalid": "Le code commence par une lettre : lettres, chiffres et _ (2 à 30)."
        },
    )
    libelle = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    unique_par_projet = serializers.BooleanField(required=False, default=False)


class RoleSystemeModificationSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    unique_par_projet = serializers.BooleanField(required=False)
