"""Serializers des rôles système gérés par le super admin (gabarits `ModeleRole`)."""

from rest_framework import serializers

from apps.catalogue.models import ModeleRole

__all__ = [
    "RoleSystemeCreationSerializer",
    "RoleSystemeModificationSerializer",
    "RoleSystemeSerializer",
]

PORTEES = [("ENTREPRISE", "Entreprise"), ("PROJET", "Projet")]


class RoleSystemeSerializer(serializers.ModelSerializer):
    modules = serializers.SerializerMethodField()

    class Meta:
        model = ModeleRole
        fields = ["id", "code", "libelle", "description", "portee", "modules"]

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
    portee = serializers.ChoiceField(choices=PORTEES, default="PROJET")
    modules = serializers.ListField(child=serializers.CharField(max_length=50), allow_empty=True)


class RoleSystemeModificationSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    portee = serializers.ChoiceField(choices=PORTEES, required=False)
    modules = serializers.ListField(
        child=serializers.CharField(max_length=50), allow_empty=True, required=False
    )
