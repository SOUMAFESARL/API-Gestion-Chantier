"""Sérialiseurs pour la gestion des comptes administrateurs de la plateforme (Super Admin)."""

from django.utils.translation import gettext_lazy as _
from django_tenants.utils import schema_context
from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.core.enums import StatutUtilisateur

__all__ = [
    "CompteAdministrateurDetailSerializer",
    "CompteAdministrateurSerializer",
    "CreerCompteAdministrateurSerializer",
    "ModifierProfilAdminSerializer",
    "ProfilCompletAdminSerializer",
]


class CompteAdministrateurSerializer(serializers.ModelSerializer):
    """Représentation d'un agent de la plateforme (schéma public) pour le back-office."""

    nom_complet = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    statut = serializers.SerializerMethodField()
    derniere_connexion = serializers.DateTimeField(source="last_login", allow_null=True)

    class Meta:
        model = Utilisateur
        fields = [
            "id",
            "email",
            "nom",
            "prenom",
            "nom_complet",
            "telephone",
            "role",
            "statut",
            "cree_le",
            "derniere_connexion",
        ]

    def get_nom_complet(self, obj: Utilisateur) -> str:
        complet = f"{obj.prenom} {obj.nom}".strip()
        return complet or obj.email

    def get_role(self, obj: Utilisateur) -> str:
        return "SUPERVISEUR" if obj.is_superuser else "SUPPORT"

    def get_statut(self, obj: Utilisateur) -> str:
        if obj.is_active and getattr(obj, "statut", None) == StatutUtilisateur.ACTIF:
            return "ACTIF"
        return "SUSPENDU"


class CompteAdministrateurDetailSerializer(CompteAdministrateurSerializer):
    pass


class CreerCompteAdministrateurSerializer(serializers.Serializer):
    """Création ou invitation d'un agent de la plateforme."""

    prenom = serializers.CharField(max_length=100)
    nom = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=["SUPERVISEUR", "SUPPORT"], default="SUPPORT")

    def validate_email(self, val: str) -> str:
        email = val.strip().lower()
        with schema_context("public"):
            if Utilisateur.objects.filter(email=email, supprime_le__isnull=True).exists():
                raise serializers.ValidationError(_("Un compte avec cette adresse email existe déjà."))
        return email


class ProfilCompletAdminSerializer(serializers.ModelSerializer):
    """Profil complet de l'administrateur connecté pour GET /admins/moi/."""

    role_global = serializers.CharField(default="AD", read_only=True)
    role_libelle = serializers.SerializerMethodField()
    schema = serializers.CharField(default="public", read_only=True)
    langue = serializers.CharField(default="fr", read_only=True)
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = [
            "id",
            "email",
            "nom",
            "prenom",
            "telephone",
            "photo_url",
            "role_global",
            "role_libelle",
            "is_superuser",
            "is_staff",
            "langue",
            "schema",
        ]

    def get_role_libelle(self, obj: Utilisateur) -> str:
        return str(_("Superviseur Plateforme") if obj.is_superuser else _("Support Plateforme"))

    def get_photo_url(self, obj: Utilisateur) -> str | None:
        if obj.avatar:
            try:
                return obj.avatar.url
            except Exception:
                return None
        return None


class ModifierProfilAdminSerializer(serializers.Serializer):
    """Données modifiables de son propre profil pour PATCH /admins/moi/."""

    prenom = serializers.CharField(max_length=100, required=False)
    nom = serializers.CharField(max_length=100, required=False)
    email = serializers.EmailField(required=False)
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_email(self, val: str) -> str:
        email = val.strip().lower()
        user = self.context.get("user")
        with schema_context("public"):
            qs = Utilisateur.objects.filter(email=email, supprime_le__isnull=True)
            if user:
                qs = qs.exclude(id=user.id)
            if qs.exists():
                raise serializers.ValidationError(_("Cette adresse email est déjà utilisée."))
        return email
