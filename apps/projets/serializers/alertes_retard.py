"""Serializers pour les alertes de retard (SFD F3 §5.4, §10 et Erratum E-3)."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.projets.models import AlerteRetard

__all__ = [
    "AlerteElementSerializer",
    "AlerteProjetSerializer",
    "AlerteRetardResolutionSerializer",
    "AlerteRetardSerializer",
]


class AlerteProjetSerializer(serializers.Serializer):
    """Projet concerné par l'alerte."""

    id = serializers.UUIDField(help_text="Identifiant UUID du projet.")
    reference = serializers.CharField(help_text="Référence du projet.")
    nom = serializers.CharField(help_text="Nom du projet.")


class AlerteElementSerializer(serializers.Serializer):
    """Case de l'arbre concernée par l'alerte (ou null pour une alerte de niveau projet)."""

    id = serializers.UUIDField(help_text="Identifiant UUID de la case.")
    code = serializers.CharField(help_text="Code libre de la case (peut être vide).")
    libelle = serializers.CharField(help_text="Intitulé de la case.")
    niveau = serializers.CharField(source="niveau.libelle", help_text="Libellé de son niveau.")

    def to_representation(self, instance):
        if instance is None:
            return None
        return super().to_representation(instance)


class AlerteRetardSerializer(serializers.ModelSerializer):
    """Représentation détaillée d'une alerte de retard."""

    projet = AlerteProjetSerializer(read_only=True)
    element = AlerteElementSerializer(read_only=True, allow_null=True)
    resolue_par = serializers.SerializerMethodField(help_text="Nom complet du résoluteur ou null.")

    class Meta:
        model = AlerteRetard
        fields = [
            "id",
            "projet",
            "element",
            "niveau",
            "delta_pts",
            "indice_sante",
            "date_detection",
            "statut",
            "causes",
            "actions_recommandees",
            "commentaire_resolution",
            "resolue_par",
            "resolue_le",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_resolue_par(self, obj: AlerteRetard) -> str | None:
        if not obj.resolue_par:
            return None
        nom = f"{obj.resolue_par.prenom} {obj.resolue_par.nom}".strip()
        return nom or obj.resolue_par.nom or obj.resolue_par.email or None


class AlerteRetardResolutionSerializer(serializers.Serializer):
    """Corps de requête pour la résolution d'une alerte de retard."""

    commentaire_resolution = serializers.CharField(
        required=True,
        trim_whitespace=True,
        help_text="Commentaire de résolution obligatoire (au moins 10 caractères).",
    )

    def validate_commentaire_resolution(self, value: str) -> str:
        propre = (value or "").strip()
        if len(propre) < 10:
            raise serializers.ValidationError(
                "Le commentaire de résolution doit comporter au moins 10 caractères."
            )
        return propre
