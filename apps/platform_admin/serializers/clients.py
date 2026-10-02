"""Serializers pour la gestion des clients de la plateforme."""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class AbonnementClientSerializer(serializers.Serializer):
    """Abonnement en cours d'une entreprise cliente."""

    statut = serializers.CharField(
        help_text="Statut de l'abonnement (ESSAI, ACTIF, IMPAYE, SUSPENDU, RESILIE)."
    )
    plan_code = serializers.CharField(
        help_text="Code du forfait BTP (BATISSEUR, MAITRE_OEUVRE, PROMOTEUR...)."
    )
    reference_transaction = serializers.CharField(help_text="Référence transaction ou paiement.")
    montant_mensuel_centimes = serializers.IntegerField(help_text="Tarif mensuel en centimes FCFA.")
    date_debut = serializers.CharField(help_text="Date de début au format ISO.")
    date_fin = serializers.CharField(help_text="Date d'échéance au format ISO.")
    fin_essai = serializers.CharField(
        allow_null=True, required=False, help_text="Date de fin d'essai si applicable."
    )
    renouvellement_auto = serializers.BooleanField(
        help_text="Indique si le renouvellement automatique est activé."
    )


class ClientPlateformeSerializer(serializers.Serializer):
    """Fiche synthétique d'une entreprise cliente pour le back-office éditeur."""

    id = serializers.UUIDField(help_text="Identifiant unique de l'entreprise.")
    raison_sociale = serializers.CharField(help_text="Raison sociale de l'entreprise.")
    nom_commercial = serializers.CharField(allow_blank=True, help_text="Nom commercial usuel.")
    slug = serializers.CharField(help_text="Identifiant de sous-domaine / schéma PostgreSQL.")
    pays = serializers.CharField(help_text="Code pays ISO (CI, SN, etc.).")
    ville = serializers.CharField(allow_blank=True, help_text="Ville du siège de l'entreprise.")
    email_contact = serializers.EmailField(help_text="Email principal de contact.")
    telephone_contact = serializers.CharField(allow_blank=True, help_text="Téléphone de contact.")
    statut = serializers.CharField(
        help_text="Statut de l'entreprise (EN_ATTENTE, ACTIF, SUSPENDU, RESILIE)."
    )
    cree_le = serializers.CharField(help_text="Date d'inscription au format ISO.")
    active_le = serializers.CharField(
        allow_null=True, required=False, help_text="Date du premier accès utilisateur."
    )
    nb_utilisateurs = serializers.IntegerField(
        help_text="Nombre total d'utilisateurs actifs dans le schéma client."
    )
    nb_projets = serializers.IntegerField(
        help_text="Nombre total de chantiers créés dans le schéma client."
    )
    abonnement = AbonnementClientSerializer(help_text="Détail de l'abonnement en cours.")


class SuspendreClientRequestSerializer(serializers.Serializer):
    """Requête de suspension d'une entreprise cliente par le Super Admin."""

    motif = serializers.CharField(
        min_length=3,
        max_length=500,
        required=True,
        error_messages={
            "blank": _("Le motif de suspension est requis."),
            "required": _("Le motif de suspension est requis."),
            "min_length": _("Le motif doit comporter au moins 3 caractères."),
        },
        help_text=_("Motif explicatif de la suspension (ex: impayé récurrent, infraction CGU...)."),
    )


class ChangerPlanClientRequestSerializer(serializers.Serializer):
    """Requête de modification du forfait d'une entreprise cliente."""

    plan_code = serializers.CharField(
        required=True,
        error_messages={
            "blank": _("Le code du plan est requis."),
            "required": _("Le code du plan est requis."),
        },
        help_text=_("Code du plan cible (ex: BATISSEUR, MAITRE_OEUVRE, PROMOTEUR)."),
    )
