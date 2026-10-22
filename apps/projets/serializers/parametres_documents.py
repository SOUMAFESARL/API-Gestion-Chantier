"""Serializers du réglage de l'en-tête et du pied des documents."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.projets.models.parametres_documents import CODES_MENTIONS, ParametresDocuments

__all__ = [
    "DocumentsEnteteSerializer",
    "DocumentsPiedSerializer",
    "DocumentsReponseSerializer",
    "ParametresDocumentsSerializer",
]


class ChampCodesMentions(serializers.ListField):
    """Liste ordonnée de codes de mentions : un code inconnu ou répété est refusé (400)."""

    child = serializers.CharField()

    def to_internal_value(self, data):
        codes = super().to_internal_value(data)
        inconnus = [code for code in codes if code not in CODES_MENTIONS]
        if inconnus:
            raise serializers.ValidationError(
                _("Code de mention inconnu : %(codes)s. Codes admis : %(admis)s.")
                % {"codes": ", ".join(inconnus), "admis": ", ".join(CODES_MENTIONS)}
            )
        if len(set(codes)) != len(codes):
            raise serializers.ValidationError(_("Une mention ne peut figurer qu'une fois."))
        return codes


class ParametresDocumentsSerializer(serializers.ModelSerializer):
    """Le réglage tel qu'il est stocké — lecture et modification partielle."""

    entete_mentions = ChampCodesMentions(required=False)
    pied_mentions = ChampCodesMentions(required=False)
    entete_texte_libre = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )
    pied_texte_libre = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )

    class Meta:
        model = ParametresDocuments
        fields = [
            "entete_afficher_logo",
            "entete_mentions",
            "entete_texte_libre",
            "pied_mentions",
            "pied_texte_libre",
        ]


class DocumentsEnteteSerializer(serializers.Serializer):
    logo_url = serializers.CharField(allow_null=True)
    lignes = serializers.ListField(child=serializers.CharField())


class DocumentsPiedSerializer(serializers.Serializer):
    lignes = serializers.ListField(child=serializers.CharField())


class DocumentsReponseSerializer(serializers.Serializer):
    """Réponse de `GET` et `PATCH /api/v1/entreprise/documents/`."""

    reglage = ParametresDocumentsSerializer()
    entete = DocumentsEnteteSerializer()
    pied = DocumentsPiedSerializer()
