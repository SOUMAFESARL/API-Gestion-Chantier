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
        .prefetch_related("permissions_catalogue")
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
        """Dictionnaire dynamique associant chaque module actif à la liste ordonnée de ses codes de permissions.

        Zéro hardcodage : interroge directement les relations M2M en base de données.
        Garantit que tous les modules actifs du catalogue apparaissent (liste vide [] si aucune permission).
        Fournit à la fois les codes majuscules (ex: 'LECTURE') et les minuscules normalisées Next.js
        ('lecture', 'saisie', 'validation') pour garantir la compatibilité totale frontend & backend.
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
            .prefetch_related("permissions_catalogue")
        )
        rpm_par_module_id = {rmp.module_id: rmp for rmp in rpm_qs}

        resultat: dict[str, list[str]] = {}
        for mod in modules_actifs:
            rmp = rpm_par_module_id.get(mod.id)
            if rmp:
                raw_perms = list(
                    rmp.permissions_catalogue.filter(est_actif=True, supprime_le__isnull=True)
                    .order_by("ordre", "code")
                    .values_list("code", flat=True)
                )
                perms = []
                for p in raw_perms:
                    if p not in perms:
                        perms.append(p)
                    p_up = p.upper()
                    if p_up == "LECTURE" or p.endswith(".lire"):
                        for alias in ("lecture", "LECTURE"):
                            if alias not in perms:
                                perms.append(alias)
                    elif p_up == "ECRITURE" or p.endswith(".ecrire") or p.endswith(".rediger"):
                        for alias in ("saisie", "ECRITURE"):
                            if alias not in perms:
                                perms.append(alias)
                    elif p_up == "VALIDATION" or p.endswith(".valider") or p == "projets.changer_statut":
                        for alias in ("validation", "VALIDATION"):
                            if alias not in perms:
                                perms.append(alias)
                # Repli de compatibilité scalaire (ex: modules sans codes granulaires catalogue comme GED)
                if getattr(rmp, "niveau", None):
                    if rmp.niveau >= 1:
                        for alias in ("lecture", "LECTURE"):
                            if alias not in perms:
                                perms.append(alias)
                    if rmp.niveau >= 2:
                        for alias in ("saisie", "ECRITURE"):
                            if alias not in perms:
                                perms.append(alias)
                    if rmp.niveau >= 3:
                        for alias in ("validation", "VALIDATION"):
                            if alias not in perms:
                                perms.append(alias)
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
        from apps.core.registre_permissions import REGISTRE
        from apps.catalogue.models import CataloguePermission

        perms_cat_valides = {
            c.lower()
            for c in CataloguePermission.objects.filter(
                est_actif=True, supprime_le__isnull=True
            ).values_list("code", flat=True)
        }

        for perm in value:
            p_str = str(perm).strip().lower()
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
                    f"La permission '{perm}' n'appartient pas au REGISTRE officiel ni au catalogue actif (A-01, A-05)."
                )
        return value

    def validate_permissions_modules(self, value):
        modules_valides = set(
            Module.objects.filter(est_actif=True, supprime_le__isnull=True).values_list(
                "code", flat=True
            )
        )
        if isinstance(value, dict):
            for module in value:
                m_str = str(module).lower()
                if m_str == "administration":
                    raise serializers.ValidationError(
                        "Les permissions d'administration ne peuvent pas être configurées sur un rôle (B-05)."
                    )
                if m_str not in modules_valides:
                    raise serializers.ValidationError(f"Module inconnu : '{module}'.")
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
        return value


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
        from apps.core.registre_permissions import REGISTRE
        from apps.catalogue.models import CataloguePermission

        perms_cat_valides = {
            c.lower()
            for c in CataloguePermission.objects.filter(
                est_actif=True, supprime_le__isnull=True
            ).values_list("code", flat=True)
        }

        for perm in value:
            p_str = str(perm).strip().lower()
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
                    f"La permission '{perm}' n'appartient pas au REGISTRE officiel ni au catalogue actif (A-01, A-05)."
                )
        return value

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
                m_str = str(module).lower()
                if m_str == "administration":
                    raise serializers.ValidationError(
                        "Les permissions d'administration ne peuvent pas être configurées sur un rôle (B-05)."
                    )
                if m_str not in modules_valides:
                    raise serializers.ValidationError(f"Module inconnu : '{module}'.")
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
        return value


class RoleSuppressionSerializer(serializers.Serializer):
    role_substitution_id = serializers.UUIDField(required=False, allow_null=True)
    role_reassignation_id = serializers.UUIDField(required=False, allow_null=True)
    reassigner_vers_role_id = serializers.UUIDField(required=False, allow_null=True)
    supprimer_collaborateurs = serializers.BooleanField(required=False, default=False)
