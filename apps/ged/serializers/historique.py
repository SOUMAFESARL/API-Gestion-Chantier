"""Serializer du journal d'audit documentaire GED (tâche 3.8)."""

from rest_framework import serializers

from apps.ged.serializers.documents import AuteurGedSerializer

__all__ = ["EvenementAuditGedSerializer"]


class EvenementAuditGedSerializer(serializers.Serializer):
    """Entrée du journal des consultations, dépôts, partages et suppressions."""

    id = serializers.CharField(read_only=True)
    action = serializers.CharField(read_only=True)
    action_libelle = serializers.CharField(read_only=True)
    utilisateur = AuteurGedSerializer(read_only=True, allow_null=True)
    details = serializers.CharField(read_only=True)
    cree_le = serializers.DateTimeField(read_only=True)
    document_id = serializers.UUIDField(read_only=True, allow_null=True, required=False)
    document_nom = serializers.CharField(read_only=True, allow_blank=True, required=False)
