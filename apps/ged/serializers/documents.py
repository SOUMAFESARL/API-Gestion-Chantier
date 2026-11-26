"""Serializers d'entrée et de sortie des documents et versions GED (tâches 3.3, 3.6, 3.8, 3.11)."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.core.enums import CategorieDocument
from apps.ged.models import Document, VersionDocument
from apps.ged.permissions import (
    peut_partager_document,
    peut_supprimer_document,
    peut_voir_historique_document,
)
from apps.ged.selectors.documents import (
    extraire_liaison_principale,
    extraire_version_active,
    origine_document,
    sous_type_source_f1,
)

__all__ = [
    "AuteurGedSerializer",
    "DocumentDepotSerializer",
    "DocumentGedDetailSerializer",
    "DocumentGedSerializer",
    "DocumentModificationSerializer",
    "DocumentSuppressionSerializer",
    "NouvelleVersionSerializer",
    "SourceLiaisonSerializer",
    "VersionDocumentSerializer",
]


def _serialiser_auteur(utilisateur: Any) -> dict[str, str] | None:
    if utilisateur is None:
        return None
    nom_complet = f"{getattr(utilisateur, 'prenom', '')} {getattr(utilisateur, 'nom', '')}".strip()
    return {
        "id": str(utilisateur.pk),
        "nom_complet": nom_complet or getattr(utilisateur, "email", ""),
    }


class AuteurGedSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    nom_complet = serializers.CharField(read_only=True)


class SourceLiaisonSerializer(serializers.Serializer):
    type_source = serializers.CharField(read_only=True)
    objet_id = serializers.UUIDField(read_only=True)
    sous_type = serializers.CharField(read_only=True, allow_null=True)


class VersionDocumentSerializer(serializers.ModelSerializer):
    numero = serializers.CharField(read_only=True)
    nom_fichier = serializers.CharField(source="nom_fichier_affiche", read_only=True)
    auteur = serializers.SerializerMethodField()

    class Meta:
        model = VersionDocument
        fields = [
            "id",
            "numero_version",
            "numero",
            "nom_fichier",
            "taille",
            "mime_type",
            "hash_sha256",
            "commentaire",
            "auteur",
            "cree_le",
            "est_active",
        ]
        read_only_fields = fields

    @extend_schema_field(AuteurGedSerializer(allow_null=True))
    def get_auteur(self, obj: VersionDocument) -> dict[str, str] | None:
        return _serialiser_auteur(obj.auteur)


class DocumentGedSerializer(serializers.ModelSerializer):
    """Représentation d'un document dans le classeur GED (liste & mutations)."""

    projet_id = serializers.UUIDField(read_only=True)
    projet_nom = serializers.CharField(source="projet.nom", read_only=True)
    projet_reference = serializers.CharField(source="projet.reference", read_only=True)
    origine = serializers.SerializerMethodField()
    source_liaison = serializers.SerializerMethodField()
    version_active = serializers.SerializerMethodField()
    nombre_versions = serializers.SerializerMethodField()
    createur = serializers.SerializerMethodField()
    peut_partager = serializers.SerializerMethodField()
    peut_voir_historique = serializers.SerializerMethodField()
    peut_supprimer = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "projet_id",
            "projet_nom",
            "projet_reference",
            "categorie",
            "nom",
            "description",
            "est_reference",
            "est_automatique",
            "origine",
            "source_liaison",
            "version_active",
            "nombre_versions",
            "createur",
            "cree_le",
            "modifie_le",
            "peut_partager",
            "peut_voir_historique",
            "peut_supprimer",
        ]
        read_only_fields = fields

    def _droits_caches(self, obj: Document) -> tuple[bool, bool, bool]:
        """Met en cache les 3 flags SSOT par `(projet_id, categorie, est_automatique)`."""
        request = self.context.get("request") if self.context else None
        user = getattr(request, "user", None) if request else None
        if not user or not getattr(user, "is_authenticated", False):
            return False, False, False

        cache = self.context.setdefault("_ged_droits_cache", {})
        cle = (str(obj.projet_id), obj.categorie, bool(obj.est_automatique))
        if cle not in cache:
            p_partager, _ = peut_partager_document(user, obj, request=request)
            p_hist, _ = peut_voir_historique_document(user, document=obj, request=request)
            p_suppr, _ = peut_supprimer_document(user, obj, request=request)
            cache[cle] = (p_partager, p_hist, p_suppr)
        return cache[cle]

    def get_origine(self, obj: Document) -> str:
        return origine_document(obj)

    @extend_schema_field(SourceLiaisonSerializer(allow_null=True))
    def get_source_liaison(self, obj: Document) -> dict[str, Any] | None:
        liaison = extraire_liaison_principale(obj)
        if liaison is None:
            return None
        return {
            "type_source": liaison.type_source,
            "objet_id": str(liaison.objet_id),
            "sous_type": sous_type_source_f1(obj, liaison),
        }

    @extend_schema_field(VersionDocumentSerializer(allow_null=True))
    def get_version_active(self, obj: Document) -> dict[str, Any] | None:
        version = extraire_version_active(obj)
        if version is None:
            return None
        return VersionDocumentSerializer(version, context=self.context).data

    def get_nombre_versions(self, obj: Document) -> int:
        annote = getattr(obj, "nb_versions", None)
        if annote is not None:
            return int(annote)
        versions_ord = getattr(obj, "versions_ordonnees", None)
        if versions_ord is not None:
            return len(versions_ord)
        return obj.nombre_versions

    @extend_schema_field(AuteurGedSerializer(allow_null=True))
    def get_createur(self, obj: Document) -> dict[str, str] | None:
        return _serialiser_auteur(obj.createur)

    def get_peut_partager(self, obj: Document) -> bool:
        return self._droits_caches(obj)[0]

    def get_peut_voir_historique(self, obj: Document) -> bool:
        return self._droits_caches(obj)[1]

    def get_peut_supprimer(self, obj: Document) -> bool:
        return self._droits_caches(obj)[2]


class DocumentGedDetailSerializer(DocumentGedSerializer):
    """Détail d'un document GED enrichi de toutes ses versions (`numero_version DESC`)."""

    versions = serializers.SerializerMethodField()

    class Meta(DocumentGedSerializer.Meta):
        fields = [*DocumentGedSerializer.Meta.fields, "versions"]
        read_only_fields = fields

    @extend_schema_field(VersionDocumentSerializer(many=True))
    def get_versions(self, obj: Document) -> list[dict[str, Any]]:
        versions = getattr(obj, "versions_ordonnees", None)
        if versions is None:
            versions = list(
                obj.versions.select_related("auteur")
                .filter(supprime_le__isnull=True)
                .order_by("-numero_version")
            )
        return VersionDocumentSerializer(versions, many=True, context=self.context).data


# ---------------------------------------------------------------------------
# Serializers d'entrée (validation stricte)
# ---------------------------------------------------------------------------
@extend_schema_field(OpenApiTypes.BINARY)
class _FichierBinaireField(serializers.FileField):
    """Champ fichier binaire documenté en OpenAPI."""


class DocumentDepotSerializer(serializers.Serializer):
    """Entrée `multipart/form-data` pour `POST /api/v1/ged/documents/`."""

    projet = serializers.UUIDField(required=True)
    categorie = serializers.ChoiceField(choices=CategorieDocument.choices, required=True)
    nom = serializers.CharField(
        max_length=255, required=True, allow_blank=False, trim_whitespace=True
    )
    description = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default=""
    )
    commentaire = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    est_reference = serializers.BooleanField(required=False, default=False)
    fichier = _FichierBinaireField(required=True, allow_null=False)

    def to_internal_value(self, data):
        if hasattr(data, "get") and "categorie" in data and isinstance(data.get("categorie"), str):
            copie = data.copy() if hasattr(data, "copy") else dict(data)
            copie["categorie"] = copie["categorie"].strip().upper()
            data = copie
        return super().to_internal_value(data)


class DocumentModificationSerializer(serializers.Serializer):
    """Entrée JSON pour `PATCH /api/v1/ged/documents/{id}/`."""

    est_reference = serializers.BooleanField(required=False)
    nom = serializers.CharField(
        max_length=255, required=False, allow_blank=False, trim_whitespace=True
    )
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class DocumentSuppressionSerializer(serializers.Serializer):
    """Corps JSON facultatif pour `DELETE /api/v1/ged/documents/{id}/`."""

    motif = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class NouvelleVersionSerializer(serializers.Serializer):
    """Entrée `multipart/form-data` pour `POST /api/v1/ged/documents/{id}/versions/`."""

    fichier = _FichierBinaireField(required=True, allow_null=False)
    commentaire = serializers.CharField(
        max_length=500,
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        error_messages={
            "required": _("La note de révision est obligatoire."),
            "blank": _("La note de révision est obligatoire."),
        },
    )
    est_reference = serializers.BooleanField(required=False, allow_null=True, default=None)
