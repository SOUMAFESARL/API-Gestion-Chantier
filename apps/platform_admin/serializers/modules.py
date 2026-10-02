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


MAPPING_PERM_VERS_ACCES = {
    "LECTURE": "lecture",
    "ECRITURE": "saisie",
    "VALIDATION": "validation",
}

MAPPING_ACCES_VERS_PERM = {
    "lecture": "LECTURE",
    "saisie": "ECRITURE",
    "ecriture": "ECRITURE",
    "validation": "VALIDATION",
    "suppression": "SUPPRESSION",
}


class AdminPermissionSimpleSerializer(serializers.ModelSerializer):
    """Représentation allégée d'une permission liée à un module."""

    class Meta:
        model = Permission
        fields = ["id", "code", "libelle", "description", "ordre"]


class AdminModuleListSerializer(serializers.ModelSerializer):
    """Vue liste d'un module avec ses autorisations granulaires rattachées."""

    permissions = AdminPermissionSimpleSerializer(many=True, read_only=True)
    permissions_codes = serializers.SerializerMethodField()
    statut = serializers.SerializerMethodField()
    acces_par_defaut = serializers.SerializerMethodField()

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
            "statut",
            "acces_par_defaut",
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

    def get_statut(self, obj: Module) -> str:
        return "ACTIF" if obj.est_actif else "INACTIF"

    def get_acces_par_defaut(self, obj: Module) -> list[str]:
        codes = self.get_permissions_codes(obj)
        acces = []
        for c in codes:
            acc = MAPPING_PERM_VERS_ACCES.get(c.upper(), c.lower())
            if acc not in acces:
                acces.append(acc)
        return acces


class AdminModuleDetailSerializer(AdminModuleListSerializer):
    """Vue détaillée complète d'un module applicatif."""

    class Meta(AdminModuleListSerializer.Meta):
        fields = AdminModuleListSerializer.Meta.fields


class AdminModuleCreateSerializer(serializers.Serializer):
    """Données requises pour la création d'un module par le Super Admin."""

    code = serializers.CharField(max_length=30, required=False, allow_blank=True)
    libelle = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    ordre = serializers.IntegerField(required=False, default=0, min_value=0)
    icone = serializers.CharField(required=False, allow_blank=True, default="box", max_length=50)
    est_actif = serializers.BooleanField(required=False, default=True)
    statut = serializers.CharField(required=False, allow_blank=True)
    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        help_text="Liste facultative des codes ou IDs de permissions autorisées pour ce module.",
    )
    acces_par_defaut = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        help_text="Liste des accès par défaut envoyée par le frontend (ex: ['lecture', 'saisie', 'validation']).",
    )

    def validate_libelle(self, value: str) -> str:
        libelle = value.strip()
        if not libelle:
            raise serializers.ValidationError("Le libellé du module est obligatoire.")
        return libelle

    def validate(self, attrs):
        # 1. Résolution du code s'il est absent (dérivation depuis le libellé)
        code = attrs.get("code")
        if not code:
            import re
            import unicodedata
            norm = unicodedata.normalize("NFKD", attrs["libelle"]).encode("ascii", "ignore").decode("utf-8")
            code = re.sub(r"[^a-z0-9]+", "_", norm.lower()).strip("_")[:30]
            if not code:
                code = "module"
            attrs["code"] = code

        code = attrs["code"].strip().lower()
        if Module.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise serializers.ValidationError({"code": [f"Un module avec le code '{code}' existe déjà."]})
        attrs["code"] = code

        # 2. Gestion de statut -> est_actif
        statut = attrs.get("statut")
        if statut:
            attrs["est_actif"] = (statut.upper() == "ACTIF")

        # 3. Gestion de acces_par_defaut -> permissions
        acces_par_defaut = attrs.get("acces_par_defaut")
        if acces_par_defaut and not attrs.get("permissions"):
            attrs["permissions"] = [
                MAPPING_ACCES_VERS_PERM.get(a.lower(), a.upper()) for a in acces_par_defaut
            ]

        return attrs


class AdminModuleUpdateSerializer(serializers.Serializer):
    """Données modifiables d'un module par le Super Admin."""

    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    ordre = serializers.IntegerField(required=False, min_value=0)
    icone = serializers.CharField(required=False, allow_blank=True, max_length=50)
    est_actif = serializers.BooleanField(required=False)
    statut = serializers.CharField(required=False, allow_blank=True)
    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Liste mise à jour des codes ou IDs de permissions autorisées pour ce module.",
    )
    acces_par_defaut = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Liste des accès mise à jour depuis le frontend.",
    )

    def validate(self, attrs):
        statut = attrs.get("statut")
        if statut:
            attrs["est_actif"] = (statut.upper() == "ACTIF")

        acces_par_defaut = attrs.get("acces_par_defaut")
        if acces_par_defaut is not None and "permissions" not in attrs:
            attrs["permissions"] = [
                MAPPING_ACCES_VERS_PERM.get(a.lower(), a.upper()) for a in acces_par_defaut
            ]
        return attrs


class AdminModuleAffecterPermissionsSerializer(serializers.Serializer):
    """Contrat pour l'affectation ou le remplacement exclusif des permissions d'un module."""

    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=True,
        help_text="Liste des codes ou identifiants UUID des autorisations à associer à ce module.",
    )
