"""Vues du module « accounts ».

Utilisateurs, rôles, invitations, appareils.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import DUREE_JETON_REINITIALISATION, Invitation
from apps.accounts.serializers import (
    AccepterInvitationSerializer,
    ConnexionSerializer,
    ContenuInvitationSerializer,
    ContenuJetonSerializer,
    DeconnexionSerializer,
    DemandeReinitialisationSerializer,
    InvitationSerializer,
    JetonsSerializer,
    ProfilConnexionSerializer,
    ReinitialisationSerializer,
    RenouvellementSerializer,
    ReponseAccepterInvitationSerializer,
    VerificationInvitationSerializer,
    VerificationJetonSerializer,
)
from apps.accounts.services.authentification import (
    authentifier,
    duree_acces_en_secondes,
    emettre_jetons,
    profil_de_connexion,
)
from apps.accounts.services.deconnexion import deconnecter
from apps.accounts.services.invitations import (
    JetonInvitationExpire,
    accepter_invitation,
    creer_invitation,
    obtenir_invitation_par_jeton,
)
from apps.accounts.services.reinitialisation import demander, reinitialiser, verifier
from apps.accounts.services.renouvellement import renouveler
from apps.accounts.throttling import (
    ThrottleConnexionParEmail,
    ThrottleDemandeMdpParEmail,
    ThrottleDemandeMdpRapprochee,
)
from apps.core.enums import RoleGlobal
from apps.core.exceptions import ActionInterditeDelegue

from .role import (
    RoleDetailUpdateView,
    RoleListCreateView,
    RoleSupprimerReassignerView,
)
from .super_admin import VerifierAccesSuperAdminView

__all__ = [
    "ConnexionView",
    "DeconnexionView",
    "DemandeReinitialisationView",
    "InvitationAccepterView",
    "InvitationListCreateView",
    "InvitationVerifierView",
    "ReinitialisationView",
    "RenouvellementView",
    "RoleDetailUpdateView",
    "RoleListCreateView",
    "RoleSupprimerReassignerView",
    "UtilisateurMoiView",
    "VerificationJetonView",
    "VerifierAccesSuperAdminView",
]


class ConnexionView(APIView):
    """Connexion — `POST /api/v1/auth/token/`.

    La vue ne décide de rien : elle valide la forme, appelle le service, et
    répond. Les issues d'échec remontent en exceptions et sont mises en forme
    par le gestionnaire d'erreurs commun.

    **Seul `application/json` est accepté** — règle R-04. Un formulaire HTML
    ne sait émettre que du `form-encoded` : sans cette restriction, un site
    tiers peut poster ce formulaire depuis le navigateur de la victime et la
    connecter sur *son* compte à lui, puis récolter ce qu'elle y saisit. DRF
    répond `415` de lui-même dès que la liste des parseurs se limite à JSON.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle, ThrottleConnexionParEmail]
    throttle_scope = "connexion"

    @extend_schema(
        summary="Connexion",
        request=ConnexionSerializer,
        responses={200: JetonsSerializer},
        examples=[
            OpenApiExample(
                "Identifiants invalides — la seule réponse d'échec",
                description=(
                    "Adresse inconnue, mot de passe faux, compte bloqué, désactivé ou "
                    "jamais activé : les cinq causes produisent cette réponse, identique "
                    "octet pour octet, `trace_id` excepté (contrat §6.1)."
                ),
                value={
                    "erreur": {
                        "code": "identifiants_invalides",
                        "message": "Email ou mot de passe incorrect.",
                        "details": {},
                        "trace_id": "1929460ac2b249bfa69625880768c730",
                    }
                },
                response_only=True,
                status_codes=["401"],
            ),
        ],
    )
    def post(self, request):
        entree = ConnexionSerializer(data=request.data)
        entree.is_valid(raise_exception=True)

        utilisateur = authentifier(
            email=entree.validated_data["email"],
            mot_de_passe=entree.validated_data["mot_de_passe"],
        )
        corps = emettre_jetons(utilisateur, origine=entree.validated_data["origine"])
        corps["expire_dans"] = duree_acces_en_secondes()
        corps["utilisateur"] = profil_de_connexion(utilisateur)

        from apps.audit.services import journaliser
        from apps.core.enums import ActionAudit

        journaliser(
            action=ActionAudit.CONNEXION,
            type_entite="utilisateur",
            entite_id=utilisateur.pk,
            utilisateur_id=utilisateur.pk,
            valeur_apres={"origine": entree.validated_data["origine"]},
            adresse_ip=request.META.get("REMOTE_ADDR"),
            appareil=request.META.get("HTTP_USER_AGENT", "")[:255],
        )

        reponse = Response(corps, status=status.HTTP_200_OK)
        # R-05. Une réponse porteuse de jetons ne se met jamais en cache : ni
        # au navigateur, ni sur un intermédiaire. C'est la seule réponse de
        # l'API dont la mise en cache remettrait un jeton en circulation après
        # une déconnexion — y compris par le bouton « Précédent ».
        reponse["Cache-Control"] = "no-store"
        return reponse


class RenouvellementView(APIView):
    """Renouvellement — `POST /api/v1/auth/token/refresh/`.

    **Remplace `TokenRefreshView` de SimpleJWT**, dont la rotation ne
    révoquait rien : `BLACKLIST_AFTER_ROTATION` appelle `refresh.blacklist()`
    dans un `try/except AttributeError: pass`, et la méthode n'existe pas sans
    l'application `token_blacklist` — écartée par la décision S4 de T-008.
    C'est le défaut D-1.

    La vue ne décide de rien : les cinq situations du tableau §4.2 sont
    traitées par le service.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_scope = "connexion"

    @extend_schema(
        summary="Renouvellement des jetons",
        request=RenouvellementSerializer,
        responses={200: JetonsSerializer},
        examples=[
            OpenApiExample(
                "Jeton déjà utilisé",
                value={
                    "erreur": {
                        "code": "jeton_revoque",
                        "message": "Session expirée. Reconnectez-vous.",
                        "details": {},
                        "trace_id": "1929460ac2b249bfa69625880768c730",
                    }
                },
                response_only=True,
                status_codes=["401"],
            ),
            OpenApiExample(
                "Liste noire injoignable",
                value={
                    "erreur": {
                        "code": "service_indisponible",
                        "message": "Service momentanément indisponible. Réessayez dans un instant.",
                        "details": {},
                        "trace_id": "8226fb3ec43245da98e343478595e26b",
                    }
                },
                response_only=True,
                status_codes=["503"],
            ),
        ],
    )
    def post(self, request):
        entree = RenouvellementSerializer(data=request.data)
        entree.is_valid(raise_exception=True)

        jetons = renouveler(entree.validated_data["refresh"])

        reponse = Response(jetons, status=status.HTTP_200_OK)
        # Une paire de jetons ne se met jamais en cache, ni au navigateur ni
        # sur un intermédiaire.
        reponse["Cache-Control"] = "no-store"
        return reponse


class DeconnexionView(APIView):
    """`POST /api/v1/auth/deconnexion/` — DEV-3.6.

    Révoque le jeton de renouvellement et sa session associée dans la liste noire
    Redis. L'appel est tolérant : si aucun jeton n'est fourni ou s'il est déjà expiré,
    la réponse reste 200 (la déconnexion est idempotente).
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Déconnexion — révocation côté serveur",
        request=DeconnexionSerializer,
        responses={200: None},
    )
    def post(self, request):
        entree = DeconnexionSerializer(data=request.data)
        entree.is_valid(raise_exception=True)

        refresh = entree.validated_data.get("refresh")
        deconnecter(
            refresh,
            adresse_ip=request.META.get("REMOTE_ADDR"),
            appareil=request.META.get("HTTP_USER_AGENT", "")[:255],
        )

        reponse = Response({"message": _("Déconnexion réussie.")}, status=status.HTTP_200_OK)
        reponse["Cache-Control"] = "no-store"
        return reponse


# ---------------------------------------------------------------------------
# Réinitialisation du mot de passe — contrat §3, §5 et §5bis
# ---------------------------------------------------------------------------
class DemandeReinitialisationView(APIView):
    """`POST /api/v1/auth/mot-de-passe/demande/`.

    **`202`, toujours — que l'adresse existe ou non.** C'est ce que la maquette
    M6 écrit elle-même à l'écran 2 : « pour des raisons de sécurité, nous ne
    confirmons pas si un compte existe ou non ». Répondre autrement ferait de
    ce formulaire public un annuaire des clients de l'éditeur.

    `202` plutôt que `200` : la requête est **acceptée**, l'envoi est
    asynchrone, et rien ne garantit qu'un email partira — il ne partira pas si
    l'adresse est inconnue. `200` affirmerait un traitement accompli.

    **Deux compteurs par adresse, et une raison peu évidente.** Celui de trois
    par heure ne protège pas le système, il protège une personne : sans lui,
    n'importe qui peut faire pleuvoir des emails de réinitialisation dans la
    boîte d'un directeur, sans compte et sans trace.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [
        ScopedRateThrottle,
        ThrottleDemandeMdpParEmail,
        ThrottleDemandeMdpRapprochee,
    ]
    throttle_scope = "mdp_demande"

    @extend_schema(
        summary="Demander un lien de réinitialisation",
        request=DemandeReinitialisationSerializer,
        responses={202: None},
    )
    def post(self, request):
        serializer = DemandeReinitialisationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        demander(
            serializer.validated_data["email"],
            ip=request.META.get("REMOTE_ADDR"),
        )

        return Response(
            {
                "message": _("Si cette adresse est enregistrée, un email vient d'être envoyé."),
                "expire_dans": int(DUREE_JETON_REINITIALISATION.total_seconds()),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class VerificationJetonView(APIView):
    """`POST /api/v1/auth/mot-de-passe/verifier/`.

    **Le jeton est lu, jamais consommé** — règle R-32. Certaines passerelles de
    sécurité de messagerie suivent les URL d'un email avant de le remettre : un
    jeton marqué « utilisé » à la vérification serait brûlé par l'antivirus
    avant que son destinataire ne clique.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mdp_verifier"

    @extend_schema(
        summary="Vérifier un lien de réinitialisation",
        request=VerificationJetonSerializer,
        responses={200: ContenuJetonSerializer},
    )
    def post(self, request):
        serializer = VerificationJetonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        jeton = verifier(serializer.validated_data["jeton"])
        reste = int((jeton.expire_le - timezone.now()).total_seconds())

        domaine_tenant = None
        url_connexion = None
        from django.conf import settings
        from django.db import connection
        from django_tenants.utils import get_public_schema_name
        from apps.tenants.models import Entreprise

        schema_nom = getattr(jeton, "_schema_name", getattr(connection, "schema_name", "public"))
        if schema_nom and schema_nom != get_public_schema_name():
            entreprise = Entreprise.objects.filter(schema_name=schema_nom).first()
            if entreprise:
                dom = entreprise.domains.filter(is_primary=True).first()
                if dom:
                    domaine_tenant = dom.domain
                    protocole = "https" if not settings.DEBUG else "http"
                    port = ":3000" if settings.DEBUG else ""
                    url_connexion = f"{protocole}://{dom.domain}{port}/connexion"

        base_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
        if not url_connexion and base_url:
            url_connexion = f"{base_url}/connexion"

        return Response(
            {
                "email": jeton.utilisateur.email,
                "motif": jeton.motif,
                "expire_dans": max(0, reste),
                "domaine": domaine_tenant,
                "url_connexion": url_connexion,
            }
        )


class ReinitialisationView(APIView):
    """`POST /api/v1/auth/mot-de-passe/reinitialiser/`.

    Enregistre le mot de passe, lève le blocage, consomme le jeton et **ferme
    toutes les sessions** — c'est ce que M6 promet à l'écran 4.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mdp_reinitialiser"

    @extend_schema(
        summary="Enregistrer un nouveau mot de passe",
        request=ReinitialisationSerializer,
        responses={200: None},
    )
    def post(self, request):
        serializer = ReinitialisationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reinitialiser(
            serializer.validated_data["jeton"],
            serializer.validated_data["mot_de_passe"],
            ip=request.META.get("REMOTE_ADDR"),
            appareil=request.META.get("HTTP_USER_AGENT", "")[:255],
        )

        return Response(
            {
                "message": _(
                    "Votre mot de passe a été enregistré. Toutes vos sessions ont été fermées."
                )
            }
        )


class InvitationListCreateView(APIView):
    """`GET` et `POST /api/v1/invitations/` — Inviter des collaborateurs (Étape 3 & Paramètres)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister les invitations",
        responses={200: InvitationSerializer(many=True)},
    )
    def get(self, request):
        invitations = Invitation.objects.all().order_by("-cree_le")
        serializer = InvitationSerializer(invitations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Créer et envoyer une invitation",
        request=InvitationSerializer,
        responses={201: InvitationSerializer},
    )
    def post(self, request):
        serializer = InvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        role_propose = serializer.validated_data["role_propose"]
        nom = serializer.validated_data.get("nom", "")
        emetteur = request.user if request.user and request.user.is_authenticated else None
        hote = request.get_host()

        # Règle d'immutabilité absolue du DG : Unique au créateur du tenant, non attribuable
        if role_propose == RoleGlobal.DIRECTEUR_GENERAL:
            return Response(
                {
                    "erreur": {
                        "code": "role_dg_non_attribuable",
                        "message": "Le rôle de Directeur Général est unique et immuable ; il ne peut pas être attribué.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Règle R-DEMO-01 : Seul le DG ou le Propriétaire peut inviter un ADMIN.
        if role_propose == RoleGlobal.ADMIN and (
            not emetteur
            or not (getattr(emetteur, "is_dg", False) or getattr(emetteur, "is_owner", False))
        ):
            raise ActionInterditeDelegue()

        invitation = creer_invitation(
            email=email,
            role_propose=role_propose,
            nom=nom,
            emetteur=emetteur,
            hote=hote,
        )
        retour = InvitationSerializer(invitation)
        return Response(retour.data, status=status.HTTP_201_CREATED)


class InvitationVerifierView(APIView):
    """`POST /api/v1/invitations/verifier/`.

    Vérifie la validité d'un jeton d'invitation sans le consommer (MLD §5.2).
    Renvoie les informations nécessaires à l'affichage de l'écran d'accueil.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_verifier"

    @extend_schema(
        summary="Vérifier un jeton d'invitation",
        request=VerificationInvitationSerializer,
        responses={200: ContenuInvitationSerializer},
    )
    def post(self, request):
        serializer = VerificationInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        jeton = serializer.validated_data["jeton"]
        invitation = obtenir_invitation_par_jeton(jeton)

        if not invitation or not invitation.est_utilisable:
            if invitation and invitation.est_expiree:
                invitation.statut = Invitation.Statut.EXPIREE
                invitation.save(update_fields=["statut", "modifie_le"])
            raise JetonInvitationExpire()

        reste = max(0, int((invitation.expire_le - timezone.now()).total_seconds()))

        from django.db import connection

        nom_entreprise = "CCD Digital"
        if hasattr(connection, "tenant") and getattr(connection.tenant, "raison_sociale", None):
            nom_entreprise = connection.tenant.raison_sociale

        data = {
            "email": invitation.email,
            "nom": invitation.nom,
            "role_propose": invitation.role_propose,
            "role_libelle": invitation.get_role_propose_display(),
            "entreprise": nom_entreprise,
            "expire_dans": reste,
        }
        return Response(data, status=status.HTTP_200_OK)


class InvitationAccepterView(APIView):
    """`POST /api/v1/invitations/accepter/`.

    Valide le mot de passe, active le compte utilisateur avec accès complet,
    consomme le jeton d'invitation et émet directement la session JWT.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_accepter"

    @extend_schema(
        summary="Accepter une invitation et activer le compte",
        request=AccepterInvitationSerializer,
        responses={200: ReponseAccepterInvitationSerializer},
    )
    def post(self, request):
        serializer = AccepterInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resultat = accepter_invitation(
            serializer.validated_data["jeton"],
            nom=serializer.validated_data.get("nom", ""),
            prenom=serializer.validated_data.get("prenom", ""),
            mot_de_passe=serializer.validated_data["mot_de_passe"],
            ip=request.META.get("REMOTE_ADDR"),
            appareil=request.META.get("HTTP_USER_AGENT", "")[:255],
        )

        tokens = resultat["tokens"]
        reponse = Response(
            {
                "message": _("Votre compte a été activé avec succès."),
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "expire_dans": duree_acces_en_secondes(),
                "utilisateur": resultat["profil"],
            },
            status=status.HTTP_200_OK,
        )
        reponse["Cache-Control"] = "no-store"
        return reponse


class UtilisateurMoiView(APIView):
    """Profil de l'utilisateur connecté — contrat d'API §1.1."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Profil de l'utilisateur connecté",
        responses={200: ProfilConnexionSerializer},
    )
    def get(self, request):
        utilisateur = request.user
        profil = profil_de_connexion(utilisateur)
        return Response(profil, status=status.HTTP_200_OK)
