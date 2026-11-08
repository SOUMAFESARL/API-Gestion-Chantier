"""Sérialiseurs de réponses pour le tunnel d'inscription."""

from rest_framework import serializers


class RenvoiActivationResponseSerializer(serializers.Serializer):
    """Réponse 202 confirmant le renvoi de l'email d'activation."""

    statut = serializers.CharField(help_text="Statut de la demande (EN_ATTENTE).")


class EtatProvisionnementResponseSerializer(serializers.Serializer):
    """Réponse 200 renvoyant l'avancement du déploiement de l'espace d'entreprise."""

    statut = serializers.ChoiceField(
        choices=[
            "EN_ATTENTE",
            "A_VALIDER",
            "REFUSEE",
            "ABANDONNEE",
            "PROVISIONNEMENT",
            "PRET",
            "ECHEC",
        ],
        help_text="État du provisionnement de l'espace client.",
    )
    url_connexion = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="URL absolue de première connexion (disponible uniquement lorsque statut = PRET).",
    )
    motif_refus = serializers.CharField(required=False)
