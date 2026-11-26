"""Serializers des liens de partage externe temporaire 72 h (tâche 3.9)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.ged.models import PartageDocument
from apps.ged.serializers.documents import AuteurGedSerializer, _serialiser_auteur

__all__ = [
    "DocumentPartagePublicSerializer",
    "PartageCreationSerializer",
    "PartageDocumentSerializer",
]


class PartageCreationSerializer(serializers.Serializer):
    """Entrée JSON facultative pour `POST /api/v1/ged/documents/{id}/partages/`."""

    destinataire = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default="", trim_whitespace=True
    )
    note = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default="", trim_whitespace=True
    )


class PartageDocumentSerializer(serializers.ModelSerializer):
    """Représentation interne d'un lien de partage externe 72 h."""

    url_publique = serializers.CharField(read_only=True)
    cree_par = serializers.SerializerMethodField()

    class Meta:
        model = PartageDocument
        fields = [
            "id",
            "jeton",
            "url_publique",
            "destinataire",
            "note",
            "cree_par",
            "cree_le",
            "expire_le",
            "revoque",
            "consultations",
        ]
        read_only_fields = fields

    @extend_schema_field(AuteurGedSerializer(allow_null=True))
    def get_cree_par(self, obj: PartageDocument) -> dict[str, str] | None:
        return _serialiser_auteur(obj.cree_par)


class _DocumentResumePublicSerializer(serializers.Serializer):
    nom = serializers.CharField(read_only=True)
    categorie = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True)
    nom_fichier = serializers.CharField(read_only=True)
    taille = serializers.IntegerField(read_only=True)
    mime_type = serializers.CharField(read_only=True)
    hash_sha256 = serializers.CharField(read_only=True)
    depose_le = serializers.DateTimeField(read_only=True)


class DocumentPartagePublicSerializer(serializers.Serializer):
    """Représentation publique anonyme (`GET /api/v1/public/partages/{jeton}/`)."""

    jeton = serializers.CharField(read_only=True)
    expire_le = serializers.DateTimeField(read_only=True)
    destinataire = serializers.CharField(read_only=True)
    note = serializers.CharField(read_only=True)
    entreprise_nom = serializers.CharField(read_only=True)
    projet_nom = serializers.CharField(read_only=True)
    projet_reference = serializers.CharField(read_only=True)
    document = _DocumentResumePublicSerializer(read_only=True)
