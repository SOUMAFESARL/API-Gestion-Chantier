from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

__all__ = [
    "ConnexionSerializer",
    "DeconnexionSerializer",
    "JetonsSerializer",
    "ProfilConnexionSerializer",
    "RenouvellementSerializer",
]

# Contrat §5 — au-delà, `mot_de_passe` est refusé en `400`, sans vérification.
# Sans borne, une chaîne d'un mégaoctet fait travailler bcrypt pendant tout ce
# temps : c'est un déni de service à coût nul pour l'appelant.
LONGUEUR_MAX_MOT_DE_PASSE = 128


class ConnexionSerializer(serializers.Serializer):
    """Forme de la requête de connexion — rien de plus.

    L'authentification elle-même vit dans
    `apps.accounts.services.authentification` : c'est une règle de gestion, et
    un serializer valide une forme, il ne décide pas d'un accès. La même règle
    devra servir au renouvellement de jeton et à l'application mobile.
    """

    email = serializers.EmailField()
    mot_de_passe = serializers.CharField(
        write_only=True,
        max_length=LONGUEUR_MAX_MOT_DE_PASSE,
        trim_whitespace=False,  # un espace final fait partie du mot de passe
        style={"input_type": "password"},
        error_messages={
            "max_length": _("Ce champ ne peut dépasser %(max)d caractères.")
            % {"max": LONGUEUR_MAX_MOT_DE_PASSE},
        },
    )
    origine = serializers.ChoiceField(
        choices=[("WEB", _("Web")), ("MOBILE", _("Mobile"))],
        default="WEB",
        help_text=_(
            "Détermine la durée du jeton de renouvellement : "
            "8 h sur le web, 24 h sur mobile (Socle Commun §2.2)."
        ),
    )

    def validate_email(self, valeur: str) -> str:
        return valeur.strip().lower()


class ProfilConnexionSerializer(serializers.Serializer):
    """Profil compact renvoyé avec les jetons — contrat §4.4 & §1.1."""

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    nom = serializers.CharField(read_only=True)
    prenom = serializers.CharField(read_only=True)
    role_global = serializers.CharField(read_only=True)
    is_dg = serializers.BooleanField(read_only=True)
    is_owner = serializers.BooleanField(read_only=True)
    langue = serializers.CharField(read_only=True)
    doit_changer_mot_de_passe = serializers.BooleanField(read_only=True)


class JetonsSerializer(serializers.Serializer):
    """Réponse d'une connexion réussie — contrat §4.2.

    `refresh` quittera le corps pour un cookie `httpOnly` quand `origine` vaut
    `WEB` (écart 8 du §14, chantier DEV-1.6). Il y est encore aujourd'hui.
    """

    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    expire_dans = serializers.IntegerField(read_only=True)
    utilisateur = ProfilConnexionSerializer(read_only=True)


class RenouvellementSerializer(serializers.Serializer):
    """Forme de la requête de renouvellement.

    Le nom du champ, `refresh`, est celui de SimpleJWT : le client l'envoie
    déjà sous ce nom, et le renommer casserait le web et le mobile pour un
    gain de cohérence nul — c'est un jeton, pas une ressource métier.
    """

    refresh = serializers.CharField(write_only=True)


class DeconnexionSerializer(serializers.Serializer):
    """Forme de la requête de déconnexion — DEV-3.6."""

    refresh = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text=_("Jeton de renouvellement à révoquer."),
    )
