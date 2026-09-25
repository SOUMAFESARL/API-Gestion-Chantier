"""Serializers pour la ressource profil utilisateur."""

import re

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

__all__ = [
    "AvatarReponseSerializer",
    "AvatarUploadSerializer",
    "ChangerMotDePasseReponseSerializer",
    "ChangerMotDePasseSerializer",
    "ProfilDetailResponseSerializer",
    "ProfilUpdateSerializer",
]


class ProfilEntrepriseSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    raison_sociale = serializers.CharField(read_only=True)
    schema_name = serializers.CharField(read_only=True)
    logo_url = serializers.CharField(read_only=True, allow_null=True)


class ProfilRolePersonnaliseSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    libelle = serializers.CharField(read_only=True)


class ProfilDetailResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    nom = serializers.CharField(read_only=True)
    prenom = serializers.CharField(read_only=True, allow_blank=True)
    nom_complet = serializers.CharField(read_only=True)
    telephone = serializers.CharField(read_only=True, allow_blank=True)
    avatar_url = serializers.CharField(read_only=True, allow_null=True)
    initiales = serializers.CharField(read_only=True)
    role_global = serializers.CharField(read_only=True)
    role_libelle = serializers.CharField(read_only=True)
    role_personnalise = ProfilRolePersonnaliseSerializer(read_only=True, allow_null=True)
    is_dg = serializers.BooleanField(read_only=True)
    is_owner = serializers.BooleanField(read_only=True)
    statut = serializers.CharField(read_only=True)
    double_authentification_active = serializers.BooleanField(read_only=True)
    doit_changer_mot_de_passe = serializers.BooleanField(read_only=True)
    langue = serializers.CharField(read_only=True)
    schema = serializers.CharField(read_only=True)
    entreprise = ProfilEntrepriseSerializer(read_only=True, allow_null=True)
    habilitations = serializers.DictField(read_only=True)
    derniere_connexion = serializers.DateTimeField(read_only=True, allow_null=True)
    cree_le = serializers.DateTimeField(read_only=True, allow_null=True)
    modifie_le = serializers.DateTimeField(read_only=True, allow_null=True)


class ProfilUpdateSerializer(serializers.Serializer):
    nom = serializers.CharField(
        required=False,
        max_length=100,
        trim_whitespace=True,
    )
    prenom = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100,
        trim_whitespace=True,
    )
    telephone = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=20,
        trim_whitespace=True,
    )
    langue = serializers.ChoiceField(
        choices=[("fr", "Français"), ("en", "English")],
        required=False,
    )

    def validate_telephone(self, valeur: str) -> str:
        if not valeur:
            return ""
        valeur_nettoyee = re.sub(r"[\s\-\.]", "", valeur)
        if not re.match(r"^\+?[0-9]{8,15}$", valeur_nettoyee):
            raise serializers.ValidationError(
                _(
                    "Le numéro de téléphone doit être valide "
                    "(format international E.164, ex: +2250700000000)."
                )
            )
        return valeur_nettoyee


class ChangerMotDePasseSerializer(serializers.Serializer):
    ancien_mot_de_passe = serializers.CharField(
        write_only=True,
        required=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    nouveau_mot_de_passe = serializers.CharField(
        write_only=True,
        required=True,
        max_length=128,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    origine = serializers.ChoiceField(
        choices=[("WEB", "Web"), ("MOBILE", "Mobile")],
        default="WEB",
        required=False,
    )


class ChangerMotDePasseReponseSerializer(serializers.Serializer):
    message = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    expire_dans = serializers.IntegerField(read_only=True)


class AvatarUploadSerializer(serializers.Serializer):
    avatar = serializers.ImageField(required=True)


class AvatarReponseSerializer(serializers.Serializer):
    avatar_url = serializers.CharField(read_only=True, allow_null=True)
    message = serializers.CharField(read_only=True)
