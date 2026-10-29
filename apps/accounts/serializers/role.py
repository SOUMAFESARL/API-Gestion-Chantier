"""Serializers pour la gestion dynamique des rôles et des habilitations par module."""

from rest_framework import serializers

from apps.accounts.models import Permission, Role, RoleModulePermission
from apps.accounts.services.roles import (
    compter_utilisateurs_et_affectations,
    modules_locaux_ouverts,
)

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
    permissions = PermissionItemSerializer(many=True, read_only=True)

    class Meta:
        model = RoleModulePermission
        fields = ["module", "module_code", "module_libelle", "permissions"]


def _construire_tableau_dynamique_modules(role: Role):
    """Construit le tableau dynamique complet de tous les modules actifs et de leurs permissions pour le rôle."""
    rpm_qs = (
        RoleModulePermission.objects.filter(
            role=role,
            supprime_le__isnull=True,
            module__in=modules_locaux_ouverts(),
        )
        .select_related("module")
        .prefetch_related("permissions_catalogue")
        .order_by("module__ordre", "module__code")
    )

    modules_actifs = list(modules_locaux_ouverts())
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
            for p in rmp.permissions_catalogue.filter(est_actif=True, supprime_le__isnull=True).order_by(
                "ordre", "code"
            )
        ]
        resultats.append(
            {
                "module_id": str(rmp.module.id),
                "module_code": rmp.module.code,
                "module_libelle": rmp.module.libelle,
                "module_description": rmp.module.description,
                "module_icone": rmp.module.icone,
                "module_ordre": rmp.module.ordre,
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
                    "permissions": [],
                }
            )

    resultats.sort(key=lambda x: (x["module_ordre"], x["module_code"]))
    return resultats


def _valider_code_permission(perm, perms_cat_valides: set[str]):
    from apps.core.registre_permissions import REGISTRE

    if isinstance(perm, (int, bool)):
        raise serializers.ValidationError(f"Permission inconnue : « {perm} ».")
    p_raw = perm.get("code") if isinstance(perm, dict) else perm
    p_str = str(p_raw or "").strip().lower()
    if not p_str:
        raise serializers.ValidationError(f"Permission inconnue : « {perm} ».")
    if p_str.startswith("administration."):
        raise serializers.ValidationError(
            "Les permissions d'administration ne peuvent pas être cochées sur un rôle (B-05)."
        )
    def_p = REGISTRE.get(p_str)
    if def_p and getattr(def_p, "reservee_administration", False):
        raise serializers.ValidationError(
            "Les permissions réservées à l'administration ne peuvent pas être cochées sur un rôle (B-05)."
        )
    if p_str not in REGISTRE and p_str not in perms_cat_valides:
        raise serializers.ValidationError(
            f"Permission inconnue : « {p_raw} »."
        )


def _valider_permissions_modules_structure(value):
    if value is None:
        return value
    from apps.catalogue.models import CataloguePermission

    modules_valides = {
        m.lower()
        for m in modules_locaux_ouverts().values_list("code", flat=True)
    }
    perms_cat_valides = {
        c.lower()
        for c in CataloguePermission.objects.filter(
            est_actif=True, supprime_le__isnull=True
        ).values_list("code", flat=True)
    }

    if isinstance(value, dict):
        for module, codes in value.items():
            m_str = str(module).lower()
            if m_str == "administration":
                raise serializers.ValidationError(
                    "Les permissions d'administration ne peuvent pas être configurées sur un rôle (B-05)."
                )
            if m_str not in modules_valides:
                raise serializers.ValidationError(f"Module inconnu : '{module}'.")
            if not isinstance(codes, (list, tuple, set)):
                raise serializers.ValidationError(f"Permission inconnue : « {codes} ».")
            for c in codes:
                _valider_code_permission(c, perms_cat_valides)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                m = item.get("module") or item.get("module_code")
                if m and str(m).lower() == "administration":
                    raise serializers.ValidationError(
                        "Les permissions d'administration ne peuvent pas être configurées sur un rôle (B-05)."
                    )
                if m and str(m).lower() not in modules_valides:
                    raise serializers.ValidationError(f"Module inconnu : '{m}'.")
                p_items = item.get("permissions") or []
                if not isinstance(p_items, (list, tuple, set)):
                    raise serializers.ValidationError(f"Permission inconnue : « {p_items} ».")
                for c in p_items:
                    _valider_code_permission(c, perms_cat_valides)
            else:
                _valider_code_permission(item, perms_cat_valides)
    return value


class RoleSerializer(serializers.ModelSerializer):
    """Serializer synthétique pour les rôles avec tableau dynamique des modules et permissions."""

    nb_utilisateurs = serializers.SerializerMethodField()
    modules = serializers.SerializerMethodField()
    permissions_modules = serializers.SerializerMethodField()
    avertissements = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "libelle",
            "description",
            "est_systeme",
            "est_actif",
            "portee",
            "nb_utilisateurs",
            "modules",
            "permissions_modules",
            "avertissements",
        ]

    def get_avertissements(self, obj: Role) -> list[str]:
        if obj.portee != "PROJET":
            return []
        from apps.accounts.models import RoleModulePermission
        rpm_qs = RoleModulePermission.objects.filter(
            role=obj,
            supprime_le__isnull=True,
        ).select_related("module").prefetch_related("permissions_catalogue")
        for rmp in rpm_qs:
            for p in rmp.permissions_catalogue.filter(est_actif=True, supprime_le__isnull=True):
                mod_code = rmp.module.code.lower() if rmp.module else p.code.split(".")[0].lower()
                if mod_code not in ("projets", "projet"):
                    return ["permission_globale_sur_role_projet"]
        return []

    def get_nb_utilisateurs(self, obj: Role) -> int:
        return compter_utilisateurs_et_affectations(obj)["total"]

    def get_modules(self, obj: Role) -> list[dict]:
        return _construire_tableau_dynamique_modules(obj)

    def get_permissions_modules(self, obj: Role) -> dict[str, list[str]]:
        """Dictionnaire dynamique associant chaque module actif à la liste ordonnée de ses codes de permissions."""
        modules_actifs = list(modules_locaux_ouverts())
        rpm_qs = (
            RoleModulePermission.objects.filter(
                role=obj,
                supprime_le__isnull=True,
                module__in=modules_actifs,
            )
            .select_related("module")
            .prefetch_related("permissions_catalogue")
        )
        rpm_par_module_id = {rmp.module_id: rmp for rmp in rpm_qs}

        resultat: dict[str, list[str]] = {}
        for mod in modules_actifs:
            rmp = rpm_par_module_id.get(mod.id)
            if rmp:
                resultat[mod.code] = list(
                    rmp.permissions_catalogue.filter(est_actif=True, supprime_le__isnull=True)
                    .order_by("ordre", "code")
                    .values_list("code", flat=True)
                )
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
    portee = serializers.ChoiceField(
        choices=["ENTREPRISE", "PROJET"],
        required=False,
        default="PROJET",
    )
    permissions_modules = serializers.JSONField(required=False, default=list)
    permissions = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )

    def validate_code(self, value: str) -> str:
        code = value.strip().upper()
        if Role.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise serializers.ValidationError(f"Un rôle avec le code '{code}' existe déjà.")
        return code

    def validate_permissions(self, value):
        if not value:
            return value
        from apps.catalogue.models import CataloguePermission

        perms_cat_valides = {
            c.lower()
            for c in CataloguePermission.objects.filter(
                est_actif=True, supprime_le__isnull=True
            ).values_list("code", flat=True)
        }
        for perm in value:
            _valider_code_permission(perm, perms_cat_valides)
        return value

    def validate_permissions_modules(self, value):
        return _valider_permissions_modules_structure(value)


class RoleModificationSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    portee = serializers.ChoiceField(
        choices=["ENTREPRISE", "PROJET"],
        required=False,
    )
    confirmer = serializers.BooleanField(required=False, default=False)
    permissions_modules = serializers.JSONField(required=False)
    permissions = serializers.ListField(
        child=serializers.CharField(), required=False
    )

    def validate_permissions(self, value):
        if not value:
            return value
        from apps.catalogue.models import CataloguePermission

        perms_cat_valides = {
            c.lower()
            for c in CataloguePermission.objects.filter(
                est_actif=True, supprime_le__isnull=True
            ).values_list("code", flat=True)
        }
        for perm in value:
            _valider_code_permission(perm, perms_cat_valides)
        return value

    def validate_permissions_modules(self, value):
        return _valider_permissions_modules_structure(value)


class RoleSuppressionSerializer(serializers.Serializer):
    role_substitution_id = serializers.UUIDField(required=False, allow_null=True)
    role_reassignation_id = serializers.UUIDField(required=False, allow_null=True)
    reassigner_vers_role_id = serializers.UUIDField(required=False, allow_null=True)
    supprimer_collaborateurs = serializers.BooleanField(required=False, default=False)
