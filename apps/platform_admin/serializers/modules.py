"""Serializers pour la gestion des modules par le Super Admin."""

from rest_framework import serializers

from apps.accounts.models import Module, Permission

__all__ = [
    "AdminModuleAffecterPermissionsSerializer",
    "AdminModuleCreateSerializer",
    "AdminModuleDetailSerializer",
    "AdminModuleListSerializer",
    "AdminModuleUpdateSerializer",
    "AdminPermissionSimpleSerializer",
]


class AdminPermissionSimpleSerializer(serializers.ModelSerializer):
    """Représentation allégée d'une permission liée à un module."""

    class Meta:
        model = Permission
        fields = ["id", "code", "libelle", "description", "ordre"]


class AdminModuleListSerializer(serializers.ModelSerializer):
    """Vue liste d'un module avec ses autorisations granulaires rattachées."""

    permissions = AdminPermissionSimpleSerializer(many=True, read_only=True)
    permissions_codes = serializers.SerializerMethodField()

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
            "permissions",
            "permissions_codes",
            "cree_le",
            "modifie_le",
        ]

    def get_permissions_codes(self, obj: Module) -> list[str]:
        return [
            p.code
            for p in obj.permissions.all()
            if getattr(p, "supprime_le", None) is None
        ]


class AdminModuleDetailSerializer(AdminModuleListSerializer):
    """Vue détaillée complète d'un module applicatif."""

    class Meta(AdminModuleListSerializer.Meta):
        fields = AdminModuleListSerializer.Meta.fields


class AdminModuleCreateSerializer(serializers.Serializer):
    """Données requises pour la création d'un module par le Super Admin."""

    code = serializers.CharField(max_length=30)
    libelle = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    ordre = serializers.IntegerField(required=False, default=0, min_value=0)
    icone = serializers.CharField(required=False, allow_blank=True, default="box", max_length=50)
    est_actif = serializers.BooleanField(required=False, default=True)
    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        help_text="Liste facultative des codes ou IDs de permissions autorisées pour ce module.",
    )

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
    """Données modifiables d'un module par le Super Admin."""

    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    ordre = serializers.IntegerField(required=False, min_value=0)
    icone = serializers.CharField(required=False, allow_blank=True, max_length=50)
    est_actif = serializers.BooleanField(required=False)
    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Liste mise à jour des codes ou IDs de permissions autorisées pour ce module.",
    )


class AdminModuleAffecterPermissionsSerializer(serializers.Serializer):
    """Contrat pour l'affectation ou le remplacement exclusif des permissions d'un module."""

    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=True,
        help_text="Liste des codes ou identifiants UUID des autorisations à associer à ce module.",
    )
