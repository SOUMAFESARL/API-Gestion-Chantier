"""Formes des requêtes d'inscription — contrat T-021 §2, §3, §4 et §5."""

from django.core.files.storage import default_storage
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

__all__ = [
    "AccuseActivationSerializer",
    "AccuseInscriptionSerializer",
    "ActivationSerializer",
    "ContenuJetonInscriptionSerializer",
    "DepotInscriptionSerializer",
    "EntrepriseSerializer",
    "RenvoiSerializer",
    "VerificationJetonInscriptionSerializer",
]

# Les neuf pays que M8 propose. **Validé contre une liste, jamais libre** — un
# code pays libre finit en `CHAR(2)` incohérent, et c'est lui qui détermine le
# calendrier des jours fériés d'un chantier.
PAYS_AUTORISES = frozenset({"CI", "SN", "CM", "BF", "ML", "TG", "BJ", "GN", "GA"})


class DepotInscriptionSerializer(serializers.Serializer):
    """`POST /inscription/` — **quatre champs, pas plus**.

    L'adresse, le RCCM, le NIF, le téléphone et le logo sont demandés **au
    wizard**, une fois la personne engagée. Les réclamer avant la première
    valeur perçue est le moyen le plus sûr de perdre le prospect.

    **Aucun `slug` dans le payload** : il est dérivé côté serveur — R-60.
    """

    # Fourni par le client — conventions A7. Absent, le serveur le génère : un
    # client qui ne le pose pas perd l'idempotence, pas l'inscription.
    id = serializers.UUIDField(required=False)
    raison_sociale = serializers.CharField(
        min_length=2,
        max_length=200,
        error_messages={
            "blank": _("Le nom de l'entreprise est requis."),
            "min_length": _("Le nom de l'entreprise est requis."),
            "required": _("Le nom de l'entreprise est requis."),
        },
    )
    pays = serializers.CharField(max_length=2)
    email = serializers.EmailField(max_length=254)
    cgu_acceptees = serializers.BooleanField()

    def validate_pays(self, valeur: str) -> str:
        code = (valeur or "").upper()
        if code not in PAYS_AUTORISES:
            raise serializers.ValidationError(_("Veuillez sélectionner un pays."))
        return code

    def validate_email(self, valeur: str) -> str:
        return valeur.strip().lower()

    def validate_cgu_acceptees(self, valeur: bool) -> bool:
        # Le refus est explicite : l'acceptation est un engagement, et une case
        # non cochée n'est pas un oubli qu'on corrige à la place de quelqu'un.
        if not valeur:
            raise serializers.ValidationError(_("Vous devez accepter les conditions."))
        return valeur


class AccuseInscriptionSerializer(serializers.Serializer):
    """La réponse `202` — et **ce qu'elle ne contient jamais**.

    Ni le slug, ni le sous-domaine, ni le fait qu'un compte existait déjà. Le
    slug renvoyé serait commode pour l'écran de confirmation, et dirait à qui
    sonde que `sotra_btp` était libre — c'est-à-dire que SOTRA BTP n'est pas
    client.
    """

    id = serializers.UUIDField()
    statut = serializers.CharField()
    email = serializers.EmailField()
    expire_dans = serializers.IntegerField()


class RenvoiSerializer(serializers.Serializer):
    """`POST /inscription/renvoyer/` — l'**identifiant**, jamais l'adresse.

    Un endpoint public qui accepte une adresse et envoie un message est une
    machine à bombarder une boîte mail. L'`id` est un UUID v4 — 122 bits — et
    n'est connu que du navigateur qui vient de soumettre le formulaire : on ne
    peut relancer que **sa propre** inscription.
    """

    id = serializers.UUIDField()


class VerificationJetonInscriptionSerializer(serializers.Serializer):
    """Le jeton voyage dans le **corps**, jamais dans le chemin — R-41."""

    jeton = serializers.CharField(max_length=64)


class ContenuJetonInscriptionSerializer(serializers.Serializer):
    """Ce que M8 écran 3 affiche : « Bienvenue SOTRA BTP ! » et l'adresse.

    **Le slug n'y est pas.** L'écran ne l'affiche pas, et le donner ouvrirait
    une seconde voie d'énumération sur un endpoint qui accepte un jeton — or un
    jeton d'inscription atterrit dans une boîte mail d'entreprise, lue par plus
    d'une personne.
    """

    raison_sociale = serializers.CharField()
    email = serializers.EmailField()
    pays = serializers.CharField()
    expire_dans = serializers.IntegerField()


class ActivationSerializer(serializers.Serializer):
    """`POST /inscription/activer/` — le geste de M8 écran 3.

    La complexité du mot de passe est jugée par `validate_password` dans le
    service : les validateurs du Socle §2.1 y sont, et c'est le même passage
    que la réinitialisation. Un seul endroit à modifier.
    """

    jeton = serializers.CharField(max_length=64)
    nom = serializers.CharField(min_length=1, max_length=100)
    prenom = serializers.CharField(max_length=100, allow_blank=True, required=False, default="")
    mot_de_passe = serializers.CharField(max_length=128, write_only=True)


class AccuseActivationSerializer(serializers.Serializer):
    """`202` et un identifiant de suivi — l'écran d'attente s'en sert."""

    suivi = serializers.UUIDField()
    statut = serializers.CharField()


class EntrepriseSerializer(serializers.Serializer):
    """Lecture et mise à jour du profil de l'entreprise cliente — Étape 1 du Wizard."""

    id = serializers.UUIDField(read_only=True)
    raison_sociale = serializers.CharField(max_length=200, required=False)
    nom_commercial = serializers.CharField(max_length=200, required=False, allow_blank=True)
    # Le pays est **en lecture seule** : choisi à l'inscription, il détermine
    # le calendrier des jours fériés et gouverne la liste des villes proposées
    # à l'étape 1. Le rendre modifiable ici, c'est permettre de changer de pays
    # après avoir saisi des chantiers — et de garder leurs villes.
    pays = serializers.CharField(max_length=2, read_only=True)
    ville = serializers.CharField(max_length=100, required=False, allow_blank=True)
    adresse = serializers.CharField(required=False, allow_blank=True)
    rccm = serializers.CharField(max_length=50, required=False, allow_blank=True)
    nif = serializers.CharField(max_length=50, required=False, allow_blank=True)
    # Le logo se lit en **trois URL** et s'écrit par le fichier seul.
    #
    # La base ne garde que des clés de stockage : en production le backend est
    # S3 avec URL signées, et une URL signée persistée est un lien qui meurt.
    # Les trois variantes existaient déjà sur le disque — le service les
    # produisait à chaque envoi — mais aucune n'était adressable : la barre
    # d'application recevait le 48 px, l'affichait dans 24 px, et laissait le
    # navigateur refaire lui-même la réduction que le serveur avait faite en
    # lumière linéaire. `srcset` a maintenant de quoi choisir.
    logo = serializers.SerializerMethodField()
    logo_1x = serializers.SerializerMethodField()
    logo_original = serializers.SerializerMethodField()
    couleur_primaire = serializers.CharField(max_length=7, required=False, allow_blank=True)
    fichier_logo = serializers.ImageField(required=False, write_only=True)
    # `logo: ""` effaçait le logo tant que le champ était inscriptible. Il ne
    # l'est plus : l'intention se déclare, au lieu de se déduire d'une chaîne
    # vide qu'un formulaire peut envoyer sans le vouloir.
    retirer_logo = serializers.BooleanField(required=False, write_only=True, default=False)
    email_contact = serializers.EmailField(required=False, allow_blank=True)
    telephone_contact = serializers.CharField(max_length=20, required=False, allow_blank=True)
    statut = serializers.CharField(read_only=True)

    def _url(self, cle: str) -> str:
        """Clé de stockage -> URL absolue.

        Absolue parce que le frontend et l'API ne partagent pas l'origine en
        développement (3000 contre 8000). Le frontend reconstruisait cette
        adresse de son côté, en relisant une variable d'environnement que
        `client.ts` documente comme épinglant le build sur un seul client :
        c'est au serveur de dire où sont ses fichiers.
        """
        if not cle:
            return ""
        url = default_storage.url(cle)
        requete = self.context.get("request")
        return requete.build_absolute_uri(url) if requete is not None else url

    def get_logo(self, obj) -> str:
        return self._url(getattr(obj, "logo", "") or "")

    def get_logo_1x(self, obj) -> str:
        return self._url(getattr(obj, "logo_1x", "") or "")

    def get_logo_original(self, obj) -> str:
        return self._url(getattr(obj, "logo_original", "") or "")
