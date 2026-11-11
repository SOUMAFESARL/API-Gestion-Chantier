"""Vues de l'inscription — contrat T-021.

**Les cinq endpoints vivent sur le domaine de la plateforme**,
et jamais sur un sous-domaine client : au moment de l'inscription, le client n'a
pas encore de sous-domaine.

Les vues ne décident de rien : elles valident la forme, appellent le service, et
répondent. Les issues d'échec remontent en exceptions, mises en forme par le
gestionnaire d'erreurs commun.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ValidationDjango
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.entreprises.selectors import entreprise_courante
from apps.core.exceptions import RequeteRefusee
from apps.core.ip_restriction import extraire_ip_client
from apps.entreprises.models import DUREE_LIEN_ACTIVATION, DemandeInscription
from apps.entreprises.serializers import (
    AccuseActivationSerializer,
    AccuseInscriptionSerializer,
    ActivationSerializer,
    ContenuJetonInscriptionSerializer,
    DepotInscriptionSerializer,
    EntrepriseSerializer,
    EtatProvisionnementResponseSerializer,
    RenvoiActivationResponseSerializer,
    RenvoiSerializer,
    VerificationJetonInscriptionSerializer,
)
from apps.entreprises.services.inscription import activer, deposer, renvoyer, verifier
from apps.entreprises.services.telephones import (
    definir_telephone_principal,
    remplacer_telephones,
)

__all__ = [
    "ActivationView",
    "ConfigurationEntrepriseView",
    "DepotInscriptionView",
    "EntrepriseView",
    "EtatProvisionnementView",
    "RenvoiActivationView",
    "VerificationJetonInscriptionView",
]



def _reste(demande: DemandeInscription) -> int:
    return max(0, int((demande.expire_le - timezone.now()).total_seconds()))


class DepotInscriptionView(APIView):
    """`POST /api/v1/inscription/` — déposer une demande.

    **`202`, toujours.** `201 Created` signifierait « la ressource existe, la
    voici » ; or rien n'a été créé du point de vue du client — ni entreprise,
    ni schéma, ni compte, seulement une demande qui expirera en 48 h si
    personne ne lit l'email. C'est aussi la seule réponse qui reste vraie dans
    les cinq branches du §2.4, et donc la seule qui n'énumère pas.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription"
    serializer_class = DepotInscriptionSerializer

    @extend_schema(
        summary="Déposer une demande d'inscription",
        description="Enregistre la demande d'inscription d'une nouvelle entreprise et déclenche l'envoi d'un email contenant le lien d'activation.",
        request=DepotInscriptionSerializer,
        responses={202: AccuseInscriptionSerializer, 400: dict},
    )
    def post(self, request):
        serializer = DepotInscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data

        demande = deposer(
            identifiant=donnees.get("id"),
            raison_sociale=donnees["raison_sociale"],
            pays=donnees["pays"],
            email=donnees["email"],
            ip=request.META.get("REMOTE_ADDR"),
        )

        return Response(
            {
                "id": str(demande.pk),
                "statut": DemandeInscription.Statut.EN_ATTENTE,
                "email": demande.email,
                "expire_dans": int(DUREE_LIEN_ACTIVATION.total_seconds()),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class RenvoiActivationView(APIView):
    """`POST /api/v1/inscription/renvoyer/` — nouveau jeton, ancien invalidé.

    Un identifiant inconnu reçoit **le même `202`**, sans email.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription_renvoi"
    serializer_class = RenvoiSerializer

    @extend_schema(
        summary="Renvoyer l'email d'activation",
        description="Génère un nouveau jeton d'activation et réexpédie l'email tout en invalidant le précédent.",
        request=RenvoiSerializer,
        responses={202: RenvoiActivationResponseSerializer, 400: dict},
    )
    def post(self, request):
        serializer = RenvoiSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        renvoyer(serializer.validated_data["id"])
        return Response({"statut": "EN_ATTENTE"}, status=status.HTTP_202_ACCEPTED)


class VerificationJetonInscriptionView(APIView):
    """`POST /api/v1/inscription/verifier/` — **sans consommer** le jeton (R-83)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription_verifier"
    serializer_class = VerificationJetonInscriptionSerializer

    @extend_schema(
        summary="Lire le contenu d'un jeton d'activation",
        description="Vérifie la validité d'un jeton reçu par email et renvoie les informations pré-remplies sans le consommer.",
        request=VerificationJetonInscriptionSerializer,
        responses={200: ContenuJetonInscriptionSerializer, 400: dict, 410: dict},
    )
    def post(self, request):
        serializer = VerificationJetonInscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        demande = verifier(serializer.validated_data["jeton"])
        return Response(
            {
                "raison_sociale": demande.raison_sociale,
                "email": demande.email,
                "pays": demande.pays,
                "expire_dans": _reste(demande),
            }
        )


class ActivationView(APIView):
    """Verifie l'email avant la decision du super admin."""

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription_activer"
    serializer_class = ActivationSerializer

    @extend_schema(
        summary="Activer un espace et lancer le provisionnement",
        description=(
            "Consomme le jeton et crée l'espace dans la même transaction : entreprise, "
            "compte du dirigeant, rôles, abonnement d'essai. `statut` vaut `PRET` ; la sonde "
            "`etat/{suivi}/` le confirme dès son premier appel."
        ),
        request=ActivationSerializer,
        responses={202: AccuseActivationSerializer, 400: dict},
    )
    def post(self, request):
        serializer = ActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data

        # La complexité est jugée **avant** de consommer le jeton : un mot de
        # passe refusé ne doit pas coûter le lien à celui qui le corrige.
        try:
            validate_password(donnees["mot_de_passe"])
        except ValidationDjango as erreur:
            raise erreur

        demande = activer(
            donnees["jeton"],
            nom=donnees["nom"],
            prenom=donnees.get("prenom", ""),
            mot_de_passe=donnees["mot_de_passe"],
        )

        # 202 et `suivi` restent ceux du contrat : l'écran d'attente sonde `etat/{suivi}/`, qui
        # répond `PRET` dès le premier appel.
        return Response(
            {"suivi": str(demande.pk), "statut": "PRET"},
            status=status.HTTP_202_ACCEPTED,
        )


@method_decorator(never_cache, name="dispatch")
class EtatProvisionnementView(APIView):
    """`GET /api/v1/inscription/etat/{suivi}/` — la sonde de l'écran d'attente.

    **`ECHEC` répond `200`, et ce n'est pas une négligence.** La requête a
    réussi : elle demandait un état, elle l'a obtenu. Un `500` dirait que la
    *sonde* est en panne, et le client réessaierait indéfiniment un endpoint
    qu'il croit cassé. Le statut HTTP décrit le sort de la requête ; le champ
    `statut` décrit le sort du provisionnement — les confondre rend les deux
    illisibles.

    **`url_connexion` est le seul endroit où le slug apparaît**, et seulement
    après consommation du jeton : pour quelqu'un qui a prouvé qu'il lit la
    boîte mail.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inscription_etat"
    serializer_class = EtatProvisionnementResponseSerializer

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Surrogate-Control"] = "no-store"
        return response

    @extend_schema(
        summary="Suivre le provisionnement",
        description="État de la demande d'inscription après activation.",
        responses={200: EtatProvisionnementResponseSerializer, 404: dict},
    )
    def get(self, request, suivi):
        demande = DemandeInscription.objects.filter(pk=suivi).first()
        if demande is None:
            return Response(
                {"erreur": {"code": "introuvable", "message": _("Suivi inconnu."), "details": {}}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if demande.statut == DemandeInscription.Statut.ACTIVEE and demande.entreprise_id:
            from django.conf import settings

            origine = request.headers.get("Origin") or request.headers.get("Referer") or ""
            if "localhost" in origine or "127.0.0.1" in origine:
                import urllib.parse
                parsed = urllib.parse.urlparse(origine)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
            else:
                base_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")

            url_connexion = f"{base_url}/connexion"

            return Response(
                {"statut": "PRET", "url_connexion": url_connexion}
            )

        if demande.statut == DemandeInscription.Statut.ECHEC:
            return Response({"statut": "ECHEC"})

        if demande.statut == DemandeInscription.Statut.REFUSEE:
            return Response({"statut": "REFUSEE", "motif_refus": demande.motif_refus})
        if demande.statut in {
            DemandeInscription.Statut.EN_ATTENTE,
            DemandeInscription.Statut.A_VALIDER,
            DemandeInscription.Statut.ABANDONNEE,
        }:
            return Response({"statut": demande.statut})

        # `PROVISIONNEMENT` ne dure plus que le temps de la transaction d'activation (D9, R-12) :
        # une demande qui y resterait viendrait d'avant la bascule, sans espace à construire.
        return Response({"statut": "PROVISIONNEMENT"})


def _rafraichir_couleur_logo_si_defaut(entreprise) -> None:
    """Extrait la couleur dominante d'un logo déjà enregistré si `couleur_primaire` est restée au défaut."""
    if not entreprise or not getattr(entreprise, "logo", ""):
        return
    couleur_actuelle = (getattr(entreprise, "couleur_primaire", "") or "").strip().upper()
    if couleur_actuelle and couleur_actuelle != "#D4652A":
        return
    try:
        from django.core.files.storage import default_storage
        from PIL import Image
        import numpy as np
        from apps.entreprises.services.images import extraire_couleur_dominante_cielab

        cle = entreprise.logo or entreprise.logo_original
        if not cle or not default_storage.exists(cle):
            return
        with default_storage.open(cle, "rb") as flux:
            im = Image.open(flux).convert("RGBA")
            rgba = np.asarray(im, dtype=np.float32) / np.float32(255.0)
        analyse = extraire_couleur_dominante_cielab(rgba)
        dominante = (analyse.get("dominant_color") or "#F97316").upper()
        if dominante == "#D4652A":
            dominante = "#D4652B"
        entreprise.couleur_primaire = dominante
        entreprise.save(update_fields=["couleur_primaire"])
    except Exception:
        pass


def _sauvegarder_entreprise(entreprise, request) -> Response:
    if entreprise is None:
        raise RequeteRefusee(_("Aucune entreprise active."))

    serializer = EntrepriseSerializer(
        instance=entreprise,
        data=request.data,
        partial=True,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    donnees = dict(serializer.validated_data)
    fichier_logo = donnees.pop("fichier_logo", None)
    retirer_logo = donnees.pop("retirer_logo", False)
    telephones = donnees.pop("telephones", None)
    telephone_contact_envoye = donnees.pop("telephone_contact", None)
    fond_retire = None

    with transaction.atomic():
        if fichier_logo:
            from apps.entreprises.services.images import traiter_logo_entreprise

            resultat_logo = traiter_logo_entreprise(
                fichier_ou_flux=fichier_logo,
                slug_entreprise=entreprise.slug,
                nom_origine=fichier_logo.name,
            )
            # Les trois variantes sont conservées. Le 24 px et le 48 px sont
            # taillés pour les deux densités d'écran de la barre ; l'original
            # recadré sert aux documents. Le service les produisait déjà tous
            # les trois — seul le 48 était retenu.
            entreprise.logo = resultat_logo["cle_2x"]
            entreprise.logo_1x = resultat_logo["cle_1x"]
            entreprise.logo_original = resultat_logo["cle_original"]
            fond_retire = resultat_logo["fond_retire"]
            donnees["couleur_primaire"] = resultat_logo["dominant_color"]

        elif retirer_logo:
            entreprise.logo = ""
            entreprise.logo_1x = ""
            entreprise.logo_original = ""
            donnees["couleur_primaire"] = ""

        for champ, valeur in donnees.items():
            setattr(entreprise, champ, valeur)

        entreprise.save()

        auteur_id = (
            request.user.pk
            if getattr(request, "user", None) and request.user.is_authenticated
            else None
        )
        ip_client = extraire_ip_client(request)
        appareil = request.META.get("HTTP_USER_AGENT", "")[:255]

        if telephones is not None:
            remplacer_telephones(
                entreprise,
                telephones,
                auteur_id=auteur_id,
                adresse_ip=ip_client,
                appareil=appareil,
            )
        elif telephone_contact_envoye is not None:
            definir_telephone_principal(
                entreprise,
                telephone_contact_envoye,
                auteur_id=auteur_id,
                adresse_ip=ip_client,
                appareil=appareil,
            )

    retour = EntrepriseSerializer(entreprise, context={"request": request})
    corps = dict(retour.data)
    if fond_retire is not None:
        # Transitoire, jamais stocké : l'information n'a de sens qu'au
        # retour de l'envoi. Elle permet à l'écran de dire « le fond de
        # votre logo n'a pas pu être détouré » au lieu de laisser
        # découvrir un rectangle blanc dans la barre, trois écrans plus loin.
        corps["fond_retire"] = fond_retire
    return Response(corps, status=status.HTTP_200_OK)


class EntrepriseView(APIView):
    """`GET`, `PATCH` et `POST /api/v1/entreprise/` — Étape 1 du Wizard & Paramètres."""

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method in ("POST", "PATCH", "PUT"):
            from apps.core.droits import APermission
            return [IsAuthenticated(), APermission.pour("administration.entreprise_modifier")()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Lire les informations de l'entreprise cliente",
        responses={200: EntrepriseSerializer},
    )
    def get(self, request):
        entreprise = entreprise_courante()
        if entreprise is None:
            raise RequeteRefusee(_("Aucune entreprise active."))
        _rafraichir_couleur_logo_si_defaut(entreprise)
        serializer = EntrepriseSerializer(entreprise, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Modifier les informations de l'entreprise cliente (PATCH)",
        request=EntrepriseSerializer,
        responses={200: EntrepriseSerializer},
    )
    def patch(self, request):
        entreprise = entreprise_courante()
        return _sauvegarder_entreprise(entreprise, request)

    @extend_schema(
        summary="Modifier les informations de l'entreprise cliente (POST)",
        request=EntrepriseSerializer,
        responses={200: EntrepriseSerializer},
    )
    def post(self, request):
        entreprise = entreprise_courante()
        return _sauvegarder_entreprise(entreprise, request)


class ConfigurationEntrepriseView(APIView):
    """`GET` et `POST /api/v1/parametres/configuration/` — Configuration d'entreprise dans les paramètres."""

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method in ("POST", "PATCH", "PUT"):
            from apps.core.droits import APermission
            return [IsAuthenticated(), APermission.pour("administration.entreprise_modifier")()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Lire la configuration de l'entreprise (Paramètres)",
        responses={200: EntrepriseSerializer},
    )
    def get(self, request):
        entreprise = entreprise_courante()
        if entreprise is None:
            raise RequeteRefusee(_("Aucune entreprise active."))
        _rafraichir_couleur_logo_si_defaut(entreprise)
        serializer = EntrepriseSerializer(entreprise, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Enregistrer la configuration de l'entreprise (Paramètres)",
        request=EntrepriseSerializer,
        responses={200: EntrepriseSerializer},
    )
    def post(self, request):
        entreprise = entreprise_courante()
        return _sauvegarder_entreprise(entreprise, request)

    @extend_schema(
        summary="Modifier la configuration de l'entreprise (Paramètres - PATCH)",
        request=EntrepriseSerializer,
        responses={200: EntrepriseSerializer},
    )
    def patch(self, request):
        entreprise = entreprise_courante()
        return _sauvegarder_entreprise(entreprise, request)
