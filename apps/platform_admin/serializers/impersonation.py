"""Sérialiseurs pour l'assistance Super Admin et le journal de plateforme."""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.platform_admin.models import JournalPlateforme

__all__ = [
    "DeconnexionAssistanceRequestSerializer",
    "DeconnexionAssistanceResponseSerializer",
    "DemandeAssistanceSerializer",
    "ErreurPlateformeResponseSerializer",
    "JournalPlateformeSerializer",
    "ReponseAssistanceSerializer",
    "UtilisateurCibleSerializer",
    "VerifierAccesSuperAdminResponseSerializer",
]


class DemandeAssistanceSerializer(serializers.Serializer):
    """Validation de la demande d'ouverture d'une session d'assistance.

    R-128 & Arbitrage 2 : Le motif est obligatoire, avec au minimum 5 caractères
    pour forcer la justification de l'intervention.
    """

    motif = serializers.CharField(
        min_length=5,
        max_length=500,
        trim_whitespace=True,
        required=True,
        error_messages={
            "required": _("Le motif d'assistance est obligatoire pour toute intervention."),
            "blank": _("Le motif d'assistance ne peut pas être vide."),
            "min_length": _("Le motif doit comporter au moins 5 caractères (ex: Ticket #1234)."),
        },
    )
    utilisateur_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text=_("Identifiant de l'utilisateur cible à assister (DG par défaut si omis)."),
    )


class UtilisateurCibleSerializer(serializers.Serializer):
    """Informations sur un utilisateur d'une entreprise disponible pour assistance."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    nom = serializers.CharField()
    prenom = serializers.CharField(allow_blank=True)
    role_global = serializers.CharField()
    role_libelle = serializers.CharField()
    is_owner = serializers.BooleanField()
    is_dg = serializers.BooleanField()
    statut = serializers.CharField()


class ReponseAssistanceSerializer(serializers.Serializer):
    """Réponse renvoyée lors de l'ouverture d'une session d'assistance."""

    access = serializers.CharField()
    expire_dans = serializers.IntegerField(
        help_text=_("Durée de validité en secondes (strictement 3600s / 1 heure).")
    )
    impersonation = serializers.DictField()
    utilisateur = serializers.DictField()
    url_redirection = serializers.CharField()


class JournalPlateformeSerializer(serializers.ModelSerializer):
    """Sérialiseur du journal plateforme pour consultation Super Admin."""

    utilisateur_nom = serializers.SerializerMethodField()
    entreprise_nom = serializers.SerializerMethodField()

    class Meta:
        model = JournalPlateforme
        fields = [
            "id",
            "utilisateur_id",
            "utilisateur_nom",
            "entreprise_id",
            "entreprise_nom",
            "action",
            "detail",
            "adresse_ip",
            "appareil",
            "horodatage",
        ]
        read_only_fields = fields

    def get_utilisateur_nom(self, obj: JournalPlateforme) -> str:
        detail = obj.detail or {}
        return (
            detail.get("super_admin_nom")
            or detail.get("super_admin_email")
            or str(obj.utilisateur_id or "")
        )

    def get_entreprise_nom(self, obj: JournalPlateforme) -> str:
        detail = obj.detail or {}
        return (
            detail.get("entreprise_nom")
            or detail.get("entreprise_schema")
            or str(obj.entreprise_id or "")
        )


class VerifierAccesSuperAdminResponseSerializer(serializers.Serializer):
    """Réponse du contrôle d'accès IP à la console Super Admin."""

    statut = serializers.CharField(help_text=_("Statut d'autorisation (ex: 'autorise')."))
    ip = serializers.CharField(
        help_text=_("Adresse IP du client appelant telle qu'évaluée par l'infrastructure.")
    )
    message = serializers.CharField(help_text=_("Message descriptif de l'autorisation d'accès."))


class DeconnexionAssistanceRequestSerializer(serializers.Serializer):
    """Paramètres optionnels lors de la clôture d'une session d'assistance."""

    entreprise_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text=_("Identifiant de l'entreprise cliente concernée (pour double journalisation)."),
    )


class DeconnexionAssistanceResponseSerializer(serializers.Serializer):
    """Confirmation de clôture de la session d'assistance."""

    statut = serializers.CharField(help_text=_("Statut de la session (ex: 'deconnecte')."))
    message = serializers.CharField(
        help_text=_("Message confirmant la clôture et la fin de l'assistance.")
    )


class ErreurPlateformeDetailSerializer(serializers.Serializer):
    """Format de l'objet d'erreur interne."""

    code = serializers.CharField(
        help_text=_(
            "Code machine de l'erreur (ex: 'acces_refuse', 'ecriture_interdite_assistance')."
        )
    )
    message = serializers.CharField(help_text=_("Message explicatif de l'erreur en français."))
    trace_id = serializers.CharField(
        required=False, help_text=_("Identifiant unique de traçabilité de la requête.")
    )
    details = serializers.DictField(
        required=False, help_text=_("Détails additionnels éventuels sur l'erreur.")
    )


class ErreurPlateformeResponseSerializer(serializers.Serializer):
    """Enveloppe standard des réponses d'erreur (4xx / 5xx)."""

    erreur = ErreurPlateformeDetailSerializer(help_text=_("Détails structurés de l'erreur."))
