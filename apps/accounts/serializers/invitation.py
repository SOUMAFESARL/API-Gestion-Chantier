from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.models import Invitation
from apps.accounts.serializers.connexion import ProfilConnexionSerializer

__all__ = [
    "AccepterInvitationSerializer",
    "ContenuInvitationSerializer",
    "InvitationSerializer",
    "ReponseAccepterInvitationSerializer",
    "VerificationInvitationSerializer",
]


class InvitationSerializer(serializers.ModelSerializer):
    est_expiree = serializers.ReadOnlyField()
    nom = serializers.CharField(required=False, allow_blank=True, default="")
    emetteur = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "nom",
            "role_propose",
            "emetteur",
            "expire_le",
            "utilise_le",
            "statut",
            "est_expiree",
            "cree_le",
            "modifie_le",
        ]

        read_only_fields = [
            "id",
            "emetteur",
            "expire_le",
            "utilise_le",
            "statut",
            "est_expiree",
            "cree_le",
            "modifie_le",
        ]


class VerificationInvitationSerializer(serializers.Serializer):
    jeton = serializers.UUIDField(help_text=_("Jeton d'invitation reçu dans le fragment de lien"))


class ContenuInvitationSerializer(serializers.Serializer):
    email = serializers.EmailField(read_only=True)
    nom = serializers.CharField(read_only=True, allow_blank=True)
    role_propose = serializers.CharField(read_only=True)
    role_libelle = serializers.CharField(read_only=True)
    entreprise = serializers.CharField(read_only=True)
    expire_dans = serializers.IntegerField(read_only=True, help_text=_("Secondes avant expiration"))


class AccepterInvitationSerializer(serializers.Serializer):
    jeton = serializers.UUIDField()
    nom = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    prenom = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    mot_de_passe = serializers.CharField(
        write_only=True,
        max_length=128,
        trim_whitespace=False,
        style={"input_type": "password"},
    )


class ReponseAccepterInvitationSerializer(serializers.Serializer):
    message = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    expire_dans = serializers.IntegerField(read_only=True)
    utilisateur = ProfilConnexionSerializer(read_only=True)
