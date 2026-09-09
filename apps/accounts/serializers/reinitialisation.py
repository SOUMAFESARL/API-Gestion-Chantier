"""Formes des requêtes de réinitialisation — contrat §3.1, §5.1 et §5bis."""

from rest_framework import serializers


class DemandeReinitialisationSerializer(serializers.Serializer):
    """`POST /auth/mot-de-passe/demande/` — une adresse, rien d'autre."""

    email = serializers.EmailField(max_length=254)

    def validate_email(self, valeur: str) -> str:
        # Normalisation imposée par le contrat : espaces retirés, minuscules.
        # Elle vaut aussi pour le compteur par adresse, qui doit voir la même
        # clé que l'utilisateur tape « Chef@BTP.ci » ou « chef@btp.ci ».
        return valeur.strip().lower()


class VerificationJetonSerializer(serializers.Serializer):
    """`POST /auth/mot-de-passe/verifier/`.

    Le jeton voyage dans le **corps**, jamais dans le chemin ni en paramètre :
    un chemin et une requête finissent tous deux dans les journaux du serveur.
    """

    jeton = serializers.CharField(max_length=64)


class ContenuJetonSerializer(serializers.Serializer):
    """Ce que la vérification renvoie — sans jamais rien dire du mot de passe."""

    email = serializers.EmailField()
    motif = serializers.CharField()
    expire_dans = serializers.IntegerField()
    domaine = serializers.CharField(required=False, allow_null=True)
    url_connexion = serializers.CharField(required=False, allow_null=True)


class ReinitialisationSerializer(serializers.Serializer):
    """`POST /auth/mot-de-passe/reinitialiser/`.

    **Pas de champ `confirmation`.** La double saisie de M6 est une
    vérification d'interface (contrat §5.1) : le serveur reçoit une seule
    valeur, et il n'a rien à comparer.

    La complexité n'est pas contrôlée ici mais par `validate_password` dans le
    service, qui porte les validateurs du Socle §2.1 — un seul endroit, celui
    que traversent aussi la création de compte et l'activation.
    """

    jeton = serializers.CharField(max_length=64)
    mot_de_passe = serializers.CharField(max_length=128, write_only=True)
