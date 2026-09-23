"""Sérialiseurs d'authentification Super Admin — Plateforme CCD Digital."""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

__all__ = [
    "ConnexionAdminSerializer",
    "DeconnexionAdminResponseSerializer",
    "DeconnexionAdminSerializer",
    "ProfilAdminSerializer",
    "ReponseConnexionAdminSerializer",
]

LONGUEUR_MAX_MOT_DE_PASSE = 128


class ConnexionAdminSerializer(serializers.Serializer):
    """Validation des identifiants de connexion Super Admin."""

    email = serializers.EmailField(
        required=True,
        error_messages={
            "required": _("L'adresse email est obligatoire."),
            "invalid": _("Adresse email invalide."),
        },
    )
    mot_de_passe = serializers.CharField(
        write_only=True,
        required=True,
        max_length=LONGUEUR_MAX_MOT_DE_PASSE,
        trim_whitespace=False,
        style={"input_type": "password"},
        error_messages={
            "required": _("Le mot de passe est obligatoire."),
            "max_length": _("Ce champ ne peut dépasser %(max)d caractères.")
            % {"max": LONGUEUR_MAX_MOT_DE_PASSE},
        },
    )
    origine = serializers.ChoiceField(
        choices=[("WEB", _("Web")), ("MOBILE", _("Mobile"))],
        default="WEB",
        required=False,
    )

    def validate_email(self, valeur: str) -> str:
        return valeur.strip().lower()


class ProfilAdminSerializer(serializers.Serializer):
    """Profil Super Admin renvoyé à la connexion."""

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    nom = serializers.CharField(read_only=True)
    prenom = serializers.CharField(read_only=True)
    role_global = serializers.CharField(read_only=True)
    role_libelle = serializers.CharField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)
    langue = serializers.CharField(read_only=True)
    schema = serializers.CharField(read_only=True)


class ReponseConnexionAdminSerializer(serializers.Serializer):
    """Réponse d'une connexion Super Admin réussie."""

    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    expire_dans = serializers.IntegerField(read_only=True)
    utilisateur = ProfilAdminSerializer(read_only=True)


class DeconnexionAdminSerializer(serializers.Serializer):
    """Requête de déconnexion Super Admin."""

    refresh = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text=_("Jeton de renouvellement Super Admin à révoquer."),
    )


class DeconnexionAdminResponseSerializer(serializers.Serializer):
    """Réponse de déconnexion Super Admin."""

    message = serializers.CharField(read_only=True)
