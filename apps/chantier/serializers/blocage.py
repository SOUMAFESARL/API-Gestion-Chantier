"""Serializers pour la gestion des blocages de chantier."""

from rest_framework import serializers

from apps.chantier.models import Blocage
from apps.core.enums import SeveriteBlocage, StatutBlocage


class BlocageSerializer(serializers.ModelSerializer):
    """Représentation complète d'un blocage de chantier."""

    ouvert_par_nom = serializers.SerializerMethodField()
    resolu_par_nom = serializers.SerializerMethodField()
    projet_nom = serializers.CharField(source="projet.nom", read_only=True)
    lot_libelle = serializers.CharField(source="lot.libelle", read_only=True, default=None)

    class Meta:
        model = Blocage
        fields = [
            "id",
            "projet",
            "projet_nom",
            "lot",
            "lot_libelle",
            "titre",
            "description",
            "severite",
            "statut",
            "ouvert_le",
            "resolu_le",
            "ouvert_par",
            "ouvert_par_nom",
            "resolu_par",
            "resolu_par_nom",
            "cree_le",
            "modifie_le",
        ]
        read_only_fields = [
            "id",
            "projet",
            "projet_nom",
            "lot_libelle",
            "ouvert_le",
            "resolu_le",
            "ouvert_par",
            "ouvert_par_nom",
            "resolu_par",
            "resolu_par_nom",
            "cree_le",
            "modifie_le",
        ]

    def get_ouvert_par_nom(self, obj) -> str:
        if obj.ouvert_par:
            nom = f"{obj.ouvert_par.prenom} {obj.ouvert_par.nom}".strip()
            return nom or obj.ouvert_par.email
        return ""

    def get_resolu_par_nom(self, obj) -> str:
        if obj.resolu_par:
            nom = f"{obj.resolu_par.prenom} {obj.resolu_par.nom}".strip()
            return nom or obj.resolu_par.email
        return ""


class BlocageCreateSerializer(serializers.Serializer):
    """Payload de création d'un blocage de chantier."""

    titre = serializers.CharField(max_length=200, help_text="Intitulé du blocage.")
    description = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="Description détaillée."
    )
    severite = serializers.ChoiceField(
        choices=SeveriteBlocage.choices,
        default=SeveriteBlocage.MINEUR,
        help_text="Niveau de gravité (MINEUR, MAJEUR, CRITIQUE).",
    )
    lot_id = serializers.UUIDField(
        required=False, allow_null=True, help_text="Identifiant du lot concerné (optionnel)."
    )


class BlocageUpdateSerializer(serializers.Serializer):
    """Payload de modification d'un blocage de chantier."""

    titre = serializers.CharField(required=False, max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    severite = serializers.ChoiceField(choices=SeveriteBlocage.choices, required=False)
    lot_id = serializers.UUIDField(required=False, allow_null=True)


class BlocageResolutionSerializer(serializers.Serializer):
    """Payload optionnel lors de la résolution d'un blocage."""

    commentaire = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="Commentaire de résolution."
    )
