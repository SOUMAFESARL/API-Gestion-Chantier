"""Sérialiseurs de réponses pour le tunnel d'inscription."""

from rest_framework import serializers


class DepotInscriptionResponseSerializer(serializers.Serializer):
    """Réponse 202 confirmant la réception de la demande d'inscription."""

    id = serializers.UUIDField(help_text="Identifiant unique de la demande d'inscription.")
    statut = serializers.CharField(help_text="Statut initial de la demande (ex: EN_ATTENTE).")
    email = serializers.EmailField(
        help_text="Adresse email professionnelle destinataire du lien d'activation."
    )
    expire_dans = serializers.IntegerField(
        help_text="Durée de validité du lien en secondes (ex: 172800 pour 48h)."
    )


class RenvoiActivationResponseSerializer(serializers.Serializer):
    """Réponse 202 confirmant le renvoi de l'email d'activation."""

    statut = serializers.CharField(help_text="Statut de la demande (EN_ATTENTE).")


class VerificationJetonInscriptionResponseSerializer(serializers.Serializer):
    """Réponse 200 lors du contrôle préalable du jeton d'activation."""

    raison_sociale = serializers.CharField(
        help_text="Nom de l'entreprise tel que renseigné au dépôt."
    )
    email = serializers.EmailField(help_text="Email du futur administrateur principal.")
    pays = serializers.CharField(help_text="Code pays ISO-3166-1 alpha-2 (ex: CI).")
    expire_dans = serializers.IntegerField(
        help_text="Nombre de secondes restantes avant expiration du jeton."
    )


class ActivationResponseSerializer(serializers.Serializer):
    """Réponse 202 confirmant la prise en compte de l'activation et le démarrage du provisionnement."""

    suivi = serializers.UUIDField(
        help_text="Identifiant de suivi de la tâche asynchrone de provisionnement."
    )
    statut = serializers.CharField(
        help_text="A_VALIDER : email verifie, validation super admin requise."
    )


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
        help_text="État du provisionnement du schéma tenant et de l'espace client.",
    )
    url_connexion = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="URL absolue de première connexion (disponible uniquement lorsque statut = PRET).",
    )
    motif_refus = serializers.CharField(required=False)
