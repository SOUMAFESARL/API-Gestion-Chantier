"""Contrat des alertes d'expiration affichees dans l'application."""

from rest_framework import serializers


class NotificationExpirationSerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.ChoiceField(choices=["ABONNEMENT_EXPIRATION", "ABONNEMENT_EXPIRE"])
    abonnement_id = serializers.UUIDField()
    entreprise_id = serializers.UUIDField()
    date_expiration = serializers.DateField()
    jours_restants = serializers.IntegerField(min_value=0)
    seuil = serializers.ChoiceField(choices=[7, 3, 1, 0])
    niveau = serializers.ChoiceField(choices=["AVERTISSEMENT", "URGENT"])
    message = serializers.CharField()
    lien_renouvellement = serializers.URLField()
