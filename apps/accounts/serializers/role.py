"""Serializers pour la gestion dynamique des rôles et des habilitations par module."""

from rest_framework import serializers

from apps.accounts.models import Module, Permission, Role, RoleModulePermission
from apps.accounts.services.roles import compter_utilisateurs_et_affectations

__all__ = [
    "PermissionItemSerializer",
    "RoleCreationSerializer",
    "RoleDetailSerializer",
    "RoleModificationSerializer",
    "RoleModuleItemSerializer",
    "RoleModulePermissionSerializer",
    "RoleSerializer",
    "RoleSuppressionSerializer",
]


class PermissionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "libelle", "description", "ordre"]


class RoleModuleItemSerializer(serializers.Serializer):
    module_id = serializers.UUIDField(source="module.id")
    module_code = serializers.CharField(source="module.code")
    module_libelle = serializers.CharField(source="module.libelle")
    module_description = serializers.CharField(source="module.description", default="")
    module_icone = serializers.CharField(source="module.icone", default="box")
    module_ordre = serializers.IntegerField(source="module.ordre", default=0)
    permissions = PermissionItemSerializer(many=True)


class RoleModulePermissionSerializer(serializers.ModelSerializer):
    module_code = serializers.CharField(source="module.code", read_only=True)
    module_libelle = serializers.CharField(source="module.libelle", read_only=True)
    niveau_libelle = serializers.CharField(source="get_niveau_display", read_only=True)
    permissions = PermissionItemSerializer(many=True, read_only=True)

    class Meta:
        model = RoleModulePermission
        fields = ["module", "module_code", "module_libelle", "niveau", "niveau_libelle", "permissions"]


def _construire_tableau_dynamique_modules(role: Role):
    """Construit le tableau dynamique complet de tous les modules actifs et de leurs permissions pour le rôle."""
    rpm_qs = (
        RoleModulePermission.objects.filter(
            role=role,
            supprime_le__isnull=True,
            module__est_actif=True,
            module__supprime_le__isnull=True,
        )
        .select_related("module")
        .prefetch_related("permissions")
        .order_by("module__ordre", "module__code")
    )

    modules_actifs = list(
        Module.objects.filter(est_actif=True, supprime_le__isnull=True).order_by("ordre", "code")
    )
    modules_couverts = set()

    resultats = []
    for rmp in rpm_qs:
        modules_couverts.add(rmp.module_id)
        perms_list = [
            {
                "id": str(p.id),
                "code": p.code,
                "libelle": p.libelle,
                "description": p.description,
                "ordre": p.ordre,
            }
            for p in rmp.permissions.filter(est_actif=True, supprime_le__isnull=True).prefetch_related("modules").order_by(
                "ordre", "code"
            )
            if not p.modules.exists() or p.modules.filter(id=rmp.module_id).exists()
        ]
        resultats.append(
            {
                "module_id": str(rmp.module.id),
                "module_code": rmp.module.code,
                "module_libelle": rmp.module.libelle,
                "module_description": rmp.module.description,
                "module_icone": rmp.module.icone,
                "module_ordre": rmp.module.ordre,
                "niveau": rmp.niveau,
                "permissions": perms_list,
            }
        )

    # Invariant de complétude : s'assurer que même les modules actifs sans entrée apparaissent (avec permissions=[])
    for m in modules_actifs:
        if m.id not in modules_couverts:
            resultats.append(
                {
                    "module_id": str(m.id),
                    "module_code": m.code,
                    "module_libelle": m.libelle,
                    "module_description": m.description,
                    "module_icone": m.icone,
                    "module_ordre": m.ordre,
                    "niveau": 0,
                    "permissions": [],
                }
            )

    resultats.sort(key=lambda x: (x["module_ordre"], x["module_code"]))
    return resultats


class RoleSerializer(serializers.ModelSerializer):
    """Serializer synthétique pour les rôles avec tableau dynamique des modules et permissions."""

    nb_utilisateurs = serializers.SerializerMethodField()
    modules = serializers.SerializerMethodField()
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
            "modules",
            "permissions_modules",
        ]

    def get_nb_utilisateurs(self, obj: Role) -> int:
        return compter_utilisateurs_et_affectations(obj)["total"]

    def get_modules(self, obj: Role):
        return _construire_tableau_dynamique_modules(obj)

    def get_permissions_modules(self, obj: Role) -> dict[str, list[str]]:
        """Dictionnaire dynamique associant chaque module actif à la liste ordonnée de ses codes de permissions.

        Zéro hardcodage : interroge directement les relations M2M en base de données.
        Garantit que tous les modules actifs du catalogue apparaissent (liste vide [] si aucune permission).
        """
        modules_actifs = list(
            Module.objects.filter(est_actif=True, supprime_le__isnull=True).order_by("ordre", "code")
        )
        rpm_qs = (
            RoleModulePermission.objects.filter(
                role=obj,
                supprime_le__isnull=True,
                module__in=modules_actifs,
            )
            .select_related("module")
            .prefetch_related("permissions")
        )
        rpm_par_module_id = {rmp.module_id: rmp for rmp in rpm_qs}

        resultat: dict[str, list[str]] = {}
        for mod in modules_actifs:
            rmp = rpm_par_module_id.get(mod.id)
            if rmp:
                perms = list(
                    rmp.permissions.filter(est_actif=True, supprime_le__isnull=True)
                    .order_by("ordre", "code")
                    .values_list("code", flat=True)
                )
                resultat[mod.code] = perms
            else:
                resultat[mod.code] = []
        return resultat


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
    permissions_modules = serializers.JSONField(required=False, default=list)

    def validate_code(self, value: str) -> str:
        code = value.strip().upper()
        if Role.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise serializers.ValidationError(f"Un rôle avec le code '{code}' existe déjà.")
        return code

    def validate_permissions_modules(self, value):
        modules_valides = set(
            Module.objects.filter(est_actif=True, supprime_le__isnull=True).values_list(
                "code", flat=True
            )
        )
        if isinstance(value, dict):
            for module in value:
                if str(module).lower() not in modules_valides:
                    raise serializers.ValidationError(f"Module inconnu : '{module}'.")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    m = item.get("module") or item.get("module_code")
                    if m and str(m).lower() not in modules_valides:
                        raise serializers.ValidationError(f"Module inconnu : '{m}'.")
        return value


class RoleModificationSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    permissions_modules = serializers.JSONField(required=False)

    def validate_permissions_modules(self, value):
        if value is None:
            return value
        modules_valides = set(
            Module.objects.filter(est_actif=True, supprime_le__isnull=True).values_list(
                "code", flat=True
            )
        )
        if isinstance(value, dict):
            for module in value:
                if str(module).lower() not in modules_valides:
                    raise serializers.ValidationError(f"Module inconnu : '{module}'.")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    m = item.get("module") or item.get("module_code")
                    if m and str(m).lower() not in modules_valides:
                        raise serializers.ValidationError(f"Module inconnu : '{m}'.")
        return value


class RoleSuppressionSerializer(serializers.Serializer):
    role_substitution_id = serializers.UUIDField(required=False, allow_null=True)
    reassigner_vers_role_id = serializers.UUIDField(required=False, allow_null=True)
