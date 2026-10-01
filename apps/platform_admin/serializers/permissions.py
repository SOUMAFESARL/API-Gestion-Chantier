from rest_framework import serializers

from apps.accounts.models import Module, Permission

__all__ = [
    "AdminModuleSimpleSerializer",
    "AdminPermissionAffecterModulesSerializer",
    "AdminPermissionCreateSerializer",
    "AdminPermissionSerializer",
    "AdminPermissionUpdateSerializer",
]


class AdminModuleSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ["id", "code", "libelle", "icone"]


class AdminPermissionSerializer(serializers.ModelSerializer):
    modules = AdminModuleSimpleSerializer(many=True, read_only=True)
    modules_codes = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = [
            "id",
            "code",
            "libelle",
            "description",
            "ordre",
            "est_actif",
            "modules",
            "modules_codes",
            "cree_le",
            "modifie_le",
        ]

    def get_modules_codes(self, obj: Permission) -> list[str]:
        return list(obj.modules.filter(supprime_le__isnull=True).values_list("code", flat=True))


class AdminPermissionCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    libelle = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    ordre = serializers.IntegerField(required=False, default=0, min_value=0)
    est_actif = serializers.BooleanField(required=False, default=True)
    modules = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        help_text="Liste facultative des codes ou IDs de modules autorisés à porter cette permission.",
    )

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
    modules = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Liste mise à jour des modules autorisés à porter cette permission.",
    )


class AdminPermissionAffecterModulesSerializer(serializers.Serializer):
    modules = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=True,
        help_text="Liste des codes ou identifiants UUID des modules autorisés à porter cette permission.",
    )
