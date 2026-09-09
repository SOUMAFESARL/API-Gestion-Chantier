"""Serializers pour la gestion dynamique des rôles et des habilitations par module."""

from rest_framework import serializers

from apps.accounts.models import Role, RoleModulePermission
from apps.accounts.services.roles import compter_utilisateurs_et_affectations
from apps.core.enums import ModuleChoix

__all__ = [
    "RoleCreationSerializer",
    "RoleDetailSerializer",
    "RoleModificationSerializer",
    "RoleModulePermissionSerializer",
    "RoleSerializer",
    "RoleSuppressionSerializer",
]


class RoleModulePermissionSerializer(serializers.ModelSerializer):
    niveau_libelle = serializers.CharField(source="get_niveau_display", read_only=True)

    class Meta:
        model = RoleModulePermission
        fields = ["module", "niveau", "niveau_libelle"]


class RoleSerializer(serializers.ModelSerializer):
    """Serializer synthétique pour les listes de rôles."""

    nb_utilisateurs = serializers.SerializerMethodField()
    permissions_modules = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "libelle",
            "description",
            "est_systeme",
            "est_actif",
            "nb_utilisateurs",
            "permissions_modules",
        ]

    def get_nb_utilisateurs(self, obj: Role) -> int:
        return compter_utilisateurs_et_affectations(obj)["total"]

    def get_permissions_modules(self, obj: Role) -> dict[str, int]:
        perms = RoleModulePermission.objects.filter(role=obj, supprime_le__isnull=True)
        return {p.module: p.niveau for p in perms}


class RoleDetailSerializer(RoleSerializer):
    """Serializer détaillé incluant le comptage utilisateurs et affectations séparé."""

    comptage = serializers.SerializerMethodField()

    class Meta(RoleSerializer.Meta):
        fields = [*RoleSerializer.Meta.fields, "comptage"]

    def get_comptage(self, obj: Role) -> dict[str, int]:
        return compter_utilisateurs_et_affectations(obj)


class RoleCreationSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    libelle = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    permissions_modules = serializers.DictField(
        child=serializers.IntegerField(min_value=0, max_value=3),
        required=False,
        default=dict,
    )

    def validate_code(self, value: str) -> str:
        code = value.strip().upper()
        if Role.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise serializers.ValidationError(f"Un rôle avec le code '{code}' existe déjà.")
        return code

    def validate_permissions_modules(self, value: dict) -> dict:
        modules_valides = set(ModuleChoix.values)
        for module in value:
            if module not in modules_valides:
                raise serializers.ValidationError(f"Module inconnu : '{module}'.")
        return value


class RoleModificationSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    permissions_modules = serializers.DictField(
        child=serializers.IntegerField(min_value=0, max_value=3),
        required=False,
    )

    def validate_permissions_modules(self, value: dict) -> dict:
        modules_valides = set(ModuleChoix.values)
        for module in value:
            if module not in modules_valides:
                raise serializers.ValidationError(f"Module inconnu : '{module}'.")
        return value


class RoleSuppressionSerializer(serializers.Serializer):
    role_substitution_id = serializers.UUIDField(required=False, allow_null=True)
    reassigner_vers_role_id = serializers.UUIDField(required=False, allow_null=True)
