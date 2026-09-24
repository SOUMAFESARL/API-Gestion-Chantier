"""Serializers pour l'API Paramètres Collaborateurs."""

from rest_framework import serializers

from apps.accounts.models import Role, Utilisateur
from apps.core.enums import RoleGlobal


class ProjetAssocieCollaborateurSerializer(serializers.Serializer):
    """Représentation d'un projet associé à un collaborateur."""

    id = serializers.UUIDField(help_text="Identifiant unique du projet")
    reference = serializers.CharField(help_text="Référence officielle du chantier (ex: PRJ-2026-001)")
    nom = serializers.CharField(help_text="Nom du chantier / projet")
    role_projet = serializers.CharField(help_text="Code du rôle sur le projet (ex: CP, CT, CC...)")
    role_projet_libelle = serializers.CharField(help_text="Libellé lisible du rôle sur le projet")
    statut_projet = serializers.CharField(help_text="Statut actuel du projet (ex: EN_COURS, EN_ATTENTE)")


class RolePersonnaliseCollaborateurSerializer(serializers.Serializer):
    """Informations de base sur le rôle personnalisé attribué."""

    id = serializers.UUIDField()
    code = serializers.CharField()
    libelle = serializers.CharField()


class CollaborateurResponseSerializer(serializers.Serializer):
    """Réponse unifiée représentant un collaborateur et ses chantiers associés."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    nom = serializers.CharField()
    prenom = serializers.CharField(allow_blank=True, default="")
    nom_complet = serializers.CharField()
    telephone = serializers.CharField(allow_blank=True, default="")
    role_global = serializers.CharField()
    role_global_libelle = serializers.CharField()
    role_personnalise = RolePersonnaliseCollaborateurSerializer(allow_null=True, default=None)
    statut = serializers.CharField()
    is_owner = serializers.BooleanField(default=False)
    cree_le = serializers.DateTimeField()
    projets = ProjetAssocieCollaborateurSerializer(many=True, default=[])
    lien_activation = serializers.CharField(required=False, allow_null=True, default=None)


class CollaborateurCreateSerializer(serializers.Serializer):
    """Données requises pour l'ajout d'un nouveau collaborateur."""

    email = serializers.EmailField(required=True)
    nom = serializers.CharField(max_length=100, required=True)
    prenom = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    role_global = serializers.ChoiceField(choices=RoleGlobal.choices, required=True)
    role_personnalise_id = serializers.UUIDField(required=False, allow_null=True, default=None)
