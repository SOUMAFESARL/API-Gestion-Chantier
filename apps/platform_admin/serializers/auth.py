"""Sérialiseurs d'authentification Super Admin — Plateforme CCD Digital."""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

__all__ = [
    "ConnexionAdminSerializer",
    "ContenuJetonAdminSerializer",
    "DeconnexionAdminResponseSerializer",
    "DeconnexionAdminSerializer",
    "DemandeReinitialisationAdminSerializer",
    "ProfilAdminSerializer",
    "ReinitialisationAdminSerializer",
    "ReponseConnexionAdminSerializer",
    "ReponseDemandeReinitialisationAdminSerializer",
    "ReponseReinitialisationAdminSerializer",
    "VerificationJetonAdminSerializer",
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


class DemandeReinitialisationAdminSerializer(serializers.Serializer):
    """Validation de l'email pour demande de réinitialisation Super Admin."""

    email = serializers.EmailField(
        required=True,
        error_messages={
            "required": _("L'adresse email est obligatoire."),
            "invalid": _("Adresse email invalide."),
        },
    )

    def validate_email(self, valeur: str) -> str:
        return valeur.strip().lower()


class ReponseDemandeReinitialisationAdminSerializer(serializers.Serializer):
    """Réponse 202 Accepted pour la demande Super Admin."""

    message = serializers.CharField(read_only=True)
    expire_dans = serializers.IntegerField(read_only=True)


class VerificationJetonAdminSerializer(serializers.Serializer):
    """Validation du jeton de réinitialisation Super Admin."""

    jeton = serializers.CharField(
        required=True,
        max_length=64,
        error_messages={
            "required": _("Le jeton de réinitialisation est obligatoire."),
        },
    )


class ContenuJetonAdminSerializer(serializers.Serializer):
    """Contenu vérifié d'un jeton Super Admin (non consommé)."""

    email = serializers.EmailField(read_only=True)
    motif = serializers.CharField(read_only=True)
    expire_dans = serializers.IntegerField(read_only=True)
    url_connexion = serializers.CharField(read_only=True)


class ReinitialisationAdminSerializer(serializers.Serializer):
    """Validation du jeton et du nouveau mot de passe Super Admin."""

    jeton = serializers.CharField(
        required=True,
        max_length=64,
        error_messages={
            "required": _("Le jeton de réinitialisation est obligatoire."),
        },
    )
    mot_de_passe = serializers.CharField(
        required=True,
        write_only=True,
        max_length=LONGUEUR_MAX_MOT_DE_PASSE,
        trim_whitespace=False,
        style={"input_type": "password"},
        error_messages={
            "required": _("Le nouveau mot de passe est obligatoire."),
            "max_length": _("Ce champ ne peut dépasser %(max)d caractères.")
            % {"max": LONGUEUR_MAX_MOT_DE_PASSE},
        },
    )


class ReponseReinitialisationAdminSerializer(serializers.Serializer):
    """Réponse de réinitialisation réussie."""

    message = serializers.CharField(read_only=True)
