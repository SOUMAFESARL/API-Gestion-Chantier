"""Vues API pour la gestion des collaborateurs dans les paramètres (/api/v1/parametres/collaborateurs/)."""

from collections import defaultdict
import logging

from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Invitation, Role, Utilisateur
from apps.accounts.serializers.collaborateur import (
    CollaborateurCreateSerializer,
    CollaborateurResponseSerializer,
    CollaborateurRattacherRoleSerializer,
)
from apps.accounts.services.invitations import creer_invitation
from apps.accounts.services import (
    desactiver_collaborateur_plateforme,
    rattacher_collaborateur_a_role,
)
from apps.billing.services.quota import verifier_quota_avant_invitation
from apps.core.enums import RoleGlobal, RoleProjet, StatutUtilisateur
from apps.core.exceptions import ActionInterditeDelegue, ActionReserveeDg
from apps.projets.models import AffectationProjet, Projet

from django.core.exceptions import ValidationError as DjangoValidationError

logger = logging.getLogger(__name__)

__all__ = [
    "ParametresCollaborateurDetailView",
    "ParametresCollaborateurListCreateView",
    "ParametresCollaborateurReactiverView",
    "ParametresCollaborateurSuspendreView",
]


def _autoriser_parametres_collaborateurs(user, request=None):
    """Autorise administration.collaborateurs_gerer pour les modifications de collaborateurs."""
    if not user or not user.is_authenticated:
        raise ActionReserveeDg()
    from apps.core.droits import a_permission
    if not a_permission(user, "administration.collaborateurs_gerer", request=request):
        raise ActionReserveeDg()


class ParametresCollaborateurListCreateView(APIView):
    """`GET` et `POST /api/v1/parametres/collaborateurs/`.

    - `GET` : Liste unifiée de tous les collaborateurs (actifs et invités) avec leurs chantiers associés.
    - `POST` : Ajout d'un nouveau collaborateur via le workflow d'invitation SaaS.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Lister tous les collaborateurs et leurs projets associés",
        description=(
            "Renvoie la liste complète des collaborateurs (comptes actifs et invitations en cours), "
            "avec pour chacun l'ensemble des chantiers auxquels ils sont affectés ou rattachés comme chef de projet."
        ),
        responses={200: CollaborateurResponseSerializer(many=True)},
    )
    def get(self, request):
        from apps.core.droits import a_permission

        if not a_permission(request.user, "administration.collaborateurs_voir", request=request):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(_("Vos habilitations ne vous permettent pas d'effectuer cette action."))

        projets_visibles_ids = None

        # 1. Tous les utilisateurs du tenant
        utilisateurs = list(
            Utilisateur.objects.filter(supprime_le__isnull=True)
            .select_related("role")
            .order_by("-is_owner", "nom", "prenom")
        )

        # 2. Indexation en mémoire des projets associés pour éviter tout N+1
        projets_par_utilisateur = defaultdict(dict)
        labels_role_projet = dict(RoleProjet.choices)

        # Projets où l'utilisateur est chef de projet direct
        projets_cps = Projet.objects.filter(supprime_le__isnull=True).values(
            "id", "reference", "nom", "statut", "chef_projet_id"
        )
        for p in projets_cps:
            cp_id = p["chef_projet_id"]
            if cp_id:
                projets_par_utilisateur[cp_id][str(p["id"])] = {
                    "id": p["id"],
                    "reference": p["reference"],
                    "nom": p["nom"],
                    "role_projet": "CP",
                    "role_projet_libelle": "Chef de projet",
                    "statut_projet": p["statut"],
                }

        # Affectations actives aux chantiers
        affectations = (
            AffectationProjet.objects.filter(est_actif=True, projet__supprime_le__isnull=True)
            .select_related("projet")
            .values(
                "utilisateur_id",
                "projet_id",
                "projet__reference",
                "projet__nom",
                "projet__statut",
                "role_projet",
            )
        )
        for aff in affectations:
            u_id = aff["utilisateur_id"]
            p_id_str = str(aff["projet_id"])
            role_code = aff["role_projet"]
            # Si déjà présent comme CP, conserver ou enrichir
            projets_par_utilisateur[u_id][p_id_str] = {
                "id": aff["projet_id"],
                "reference": aff["projet__reference"],
                "nom": aff["projet__nom"],
                "role_projet": role_code,
                "role_projet_libelle": labels_role_projet.get(role_code, role_code),
                "statut_projet": aff["projet__statut"],
            }

        resultats = []
        emails_utilisateurs = set()

        for u in utilisateurs:
            emails_utilisateurs.add(u.email.lower())
            rp_data = None
            if u.role_personnalise:
                rp_data = {
                    "id": u.role_personnalise.id,
                    "code": u.role_personnalise.code,
                    "libelle": u.role_personnalise.libelle,
                }

            user_projets = list(projets_par_utilisateur[u.id].values())
            if projets_visibles_ids is not None:
                user_projets = [p for p in user_projets if str(p["id"]) in projets_visibles_ids]

            avatar_url = None
            if u.avatar and hasattr(u.avatar, "url"):
                try:
                    avatar_url = request.build_absolute_uri(u.avatar.url) if request else u.avatar.url
                except Exception:
                    avatar_url = u.avatar.url

            resultats.append(
                {
                    "id": u.id,
                    "email": u.email,
                    "nom": u.nom,
                    "prenom": u.prenom,
                    "nom_complet": f"{u.prenom} {u.nom}".strip() or u.nom or u.email,
                    "telephone": u.telephone,
                    "role_global": u.role_global,
                    "role_global_libelle": u.get_role_global_display(),
                    "role_personnalise": rp_data,
                    "statut": u.statut,
                    "is_owner": u.is_owner,
                    "cree_le": u.cree_le,
                    "projets": user_projets,
                    "lien_activation": None,
                    "avatar_url": avatar_url,
                    "derniere_connexion": getattr(u, "derniere_connexion", getattr(u, "last_login", None)),
                }
            )

        # 3. Invitations en cours dont le compte n'a pas encore été matérialisé
        invitations = Invitation.objects.filter(
            statut=Invitation.Statut.ENVOYEE,
            expire_le__gt=timezone.now(),
        ).order_by("-cree_le")

        for inv in invitations:
            if inv.email.lower() not in emails_utilisateurs:
                emails_utilisateurs.add(inv.email.lower())
                resultats.append(
                    {
                        "id": inv.id,
                        "email": inv.email,
                        "nom": inv.nom,
                        "prenom": "",
                        "nom_complet": inv.nom or inv.email,
                        "telephone": "",
                        "role_global": inv.role_propose,
                        "role_global_libelle": inv.get_role_propose_display(),
                        "role_personnalise": None,
                        "statut": "INVITE",
                        "is_owner": False,
                        "cree_le": inv.cree_le,
                        "projets": [],
                        "lien_activation": None,
                        "avatar_url": None,
                        "derniere_connexion": None,
                    }
                )

        serializer = CollaborateurResponseSerializer(resultats, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Ajouter un collaborateur (invitation SaaS)",
        description=(
            "Crée un nouveau profil collaborateur avec statut 'INVITE' et envoie une invitation "
            "par email pour lui permettre de définir son mot de passe et activer son compte."
        ),
        request=CollaborateurCreateSerializer,
        responses={201: CollaborateurResponseSerializer},
    )
    def post(self, request):
        _autoriser_parametres_collaborateurs(request.user, request=request)

        serializer = CollaborateurCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        nom = serializer.validated_data["nom"].strip()
        prenom = serializer.validated_data.get("prenom", "").strip()
        telephone = serializer.validated_data.get("telephone", "").strip()
        role_global = serializer.validated_data.get("role_global")
        role_personnalise_id = serializer.validated_data.get("role_personnalise_id")

        # Règle d'immutabilité absolue du DG : Unique au créateur du tenant
        if role_global in (RoleGlobal.DIRECTEUR_GENERAL, "DG"):
            return Response(
                {
                    "erreur": {
                        "code": "role_dg_non_attribuable",
                        "message": "Le rôle de Directeur Général est unique et immuable ; il ne peut pas être attribué.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        role_cible = None
        if role_personnalise_id:
            role_cible = Role.objects.filter(
                id=role_personnalise_id, supprime_le__isnull=True
            ).first()
            if not role_cible:
                raise ValidationError(
                    {"role_personnalise_id": _("Rôle personnalisé introuvable.")}
                )
        elif role_global:
            mapped = "BAI" if role_global == "MOA" else ("VI" if role_global == "MOE" else role_global)
            role_cible = Role.objects.filter(code=mapped, supprime_le__isnull=True).first()

        from apps.core.droits import est_dg
        # Règle B-09 : Seul le DG peut inviter ou nommer un DG
        if not est_dg(request.user) and (role_global in (RoleGlobal.DIRECTEUR_GENERAL, "DG") or (role_cible and role_cible.code in (RoleGlobal.DIRECTEUR_GENERAL, "DG"))):
            raise ActionReserveeDg(_("Seul le Directeur Général peut attribuer le rôle Directeur Général."))

        # Règle R-DEMO-01 / B-06 : Seul le DG ou le Propriétaire peut inviter/créer un ADMIN
        est_creation_admin = (
            role_global in (RoleGlobal.ADMIN, "AD")
            or (role_cible and role_cible.code in (RoleGlobal.ADMIN, "AD"))
        )
        if est_creation_admin and not est_dg(request.user):
            raise ActionInterditeDelegue()

        # Règle B-09 : L'AD n'attribue qu'un rôle dont il détient toutes les permissions
        if not est_dg(request.user) and role_cible:
            from apps.core.droits import permissions_du_role, permissions_effectives
            perms_ad = permissions_effectives(request.user, request=request)
            perms_role = permissions_du_role(role_cible)
            if not perms_role.issubset(perms_ad):
                return Response(
                    {"detail": _("Vous ne pouvez attribuer qu'un rôle dont vous possédez toutes les permissions (B-09).")},
                    status=status.HTTP_403_FORBIDDEN,
                )


        email_clean = email.strip().lower()

        # Règle C-03 & L8-1 : Vérification globale dans le Registre Global
        from django_tenants.utils import schema_context
        from apps.tenants.models import Entreprise, RegistreEmail

        email_pris = False
        with schema_context("public"):
            email_pris = RegistreEmail.objects.filter(email=email_clean).exists()

        existant = Utilisateur.objects.filter(
            email__iexact=email_clean,
            supprime_le__isnull=True,
        ).first()

        if not email_pris and existant and existant.statut == StatutUtilisateur.ACTIF:
            email_pris = True

        if email_pris:
            return Response(
                {
                    "erreur": {
                        "code": "email_deja_utilise",
                        "message": "Cette adresse email est déjà utilisée.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Vérification du quota du plan avant émission
        verifier_quota_avant_invitation()

        with transaction.atomic():
            if existant:
                collaborateur = existant
                collaborateur.nom = nom
                collaborateur.prenom = prenom
                if telephone:
                    collaborateur.telephone = telephone
                collaborateur.role = role_cible
                collaborateur.role_global = role_cible.code if role_cible else (role_global or "VISITEUR")
                collaborateur.statut = StatutUtilisateur.INVITE
                collaborateur.save()
            else:
                collaborateur = Utilisateur(
                    email=email_clean,
                    nom=nom,
                    prenom=prenom,
                    telephone=telephone,
                    role=role_cible,
                    role_global=role_cible.code if role_cible else (role_global or "VISITEUR"),
                    statut=StatutUtilisateur.INVITE,
                    is_active=True,
                )
                collaborateur.set_unusable_password()
                collaborateur.save()

            invitation = creer_invitation(
                email=email_clean,
                role_propose=role_cible.code if role_cible else (role_global or "VISITEUR"),
                nom=f"{prenom} {nom}".strip(),
                emetteur=request.user,
                hote=request.get_host(),
                verifier_quota=False,
            )

            with schema_context("public"):
                entreprise_obj = Entreprise.objects.filter(schema_name=request.tenant.schema_name).first()
                if entreprise_obj:
                    RegistreEmail.objects.get_or_create(
                        email=email_clean,
                        defaults={"entreprise": entreprise_obj},
                    )

        jeton = getattr(invitation, "jeton_clair", None)
        lien_activation = f"/invitation#jeton={jeton}" if jeton else None

        rp_data = None
        if collaborateur.role_personnalise:
            rp_data = {
                "id": collaborateur.role_personnalise.id,
                "code": collaborateur.role_personnalise.code,
                "libelle": collaborateur.role_personnalise.libelle,
            }

        reponse_data = {
            "id": collaborateur.id,
            "email": collaborateur.email,
            "nom": collaborateur.nom,
            "prenom": collaborateur.prenom,
            "nom_complet": f"{collaborateur.prenom} {collaborateur.nom}".strip() or collaborateur.nom,
            "telephone": collaborateur.telephone,
            "role_global": collaborateur.role_global,
            "role_global_libelle": collaborateur.get_role_global_display(),
            "role_personnalise": rp_data,
            "statut": collaborateur.statut,
            "is_owner": collaborateur.is_owner,
            "cree_le": collaborateur.cree_le,
            "projets": [],
            "lien_activation": lien_activation,
            "avatar_url": None,
            "derniere_connexion": None,
        }

        serializer_rep = CollaborateurResponseSerializer(reponse_data)
        return Response(serializer_rep.data, status=status.HTTP_201_CREATED)

def _obtenir_projets_collaborateur(collaborateur):
    """Charge les chantiers associés à un collaborateur (CP ou affectation active)."""
    projets_dict = {}
    labels_role_projet = dict(RoleProjet.choices)

    for p in Projet.objects.filter(chef_projet=collaborateur, supprime_le__isnull=True):
        projets_dict[str(p.id)] = {
            "id": p.id,
            "reference": p.reference,
            "nom": p.nom,
            "role_projet": "CP",
            "role_projet_libelle": "Chef de projet",
            "statut_projet": p.statut,
        }

    for aff in AffectationProjet.objects.filter(
        utilisateur=collaborateur,
        est_actif=True,
        projet__supprime_le__isnull=True,
    ).select_related("projet"):
        projets_dict[str(aff.projet_id)] = {
            "id": aff.projet_id,
            "reference": aff.projet.reference,
            "nom": aff.projet.nom,
            "role_projet": aff.role_projet,
            "role_projet_libelle": labels_role_projet.get(aff.role_projet, aff.role_projet),
            "statut_projet": aff.projet.statut,
        }

    return list(projets_dict.values())


class ParametresCollaborateurDetailView(APIView):
    """`GET`, `PATCH`, `POST` et `DELETE /api/v1/invitations/{id}/` (ou `/parametres/collaborateurs/{id}/`).

    - `GET` : Détail complet du collaborateur avec ses projets associés.
    - `PATCH` / `POST` : Modification du rôle ou rattachement à un rôle personnalisé.
    - `DELETE` : Retrait de toute la plateforme (départ entreprise, révocation sessions et chantiers).
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Détail d'un collaborateur",
        responses={200: CollaborateurResponseSerializer},
    )
    def get(self, request, pk):
        from apps.core.droits import a_permission

        collaborateur = get_object_or_404(
            Utilisateur.tous_objets,
            pk=pk,
            supprime_le__isnull=True,
        )

        if collaborateur.pk != request.user.pk and not a_permission(
            request.user, "administration.collaborateurs_voir", request=request
        ):
            raise ActionReserveeDg()

        rp_data = None
        if collaborateur.role_personnalise:
            rp_data = {
                "id": collaborateur.role_personnalise.id,
                "code": collaborateur.role_personnalise.code,
                "libelle": collaborateur.role_personnalise.libelle,
            }

        avatar_url = None
        if collaborateur.avatar and hasattr(collaborateur.avatar, "url"):
            try:
                avatar_url = request.build_absolute_uri(collaborateur.avatar.url) if request else collaborateur.avatar.url
            except Exception:
                avatar_url = collaborateur.avatar.url

        reponse_data = {
            "id": collaborateur.id,
            "email": collaborateur.email,
            "nom": collaborateur.nom,
            "prenom": collaborateur.prenom,
            "nom_complet": collaborateur.nom_complet,
            "telephone": collaborateur.telephone,
            "role_global": collaborateur.role_global,
            "role_global_libelle": collaborateur.get_role_global_display(),
            "role_personnalise": rp_data,
            "statut": collaborateur.statut,
            "is_owner": collaborateur.is_owner,
            "cree_le": collaborateur.cree_le,
            "projets": _obtenir_projets_collaborateur(collaborateur),
            "lien_activation": None,
            "avatar_url": avatar_url,
            "derniere_connexion": getattr(collaborateur, "derniere_connexion", getattr(collaborateur, "last_login", None)),
        }

        return Response(
            CollaborateurResponseSerializer(reponse_data).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Rattacher un rôle à un collaborateur ou modifier ses informations",
        request=CollaborateurRattacherRoleSerializer,
        responses={200: CollaborateurResponseSerializer},
    )
    def patch(self, request, pk):
        _autoriser_parametres_collaborateurs(request.user, request=request)

        collaborateur = get_object_or_404(
            Utilisateur.tous_objets,
            pk=pk,
            supprime_le__isnull=True,
        )

        from apps.core.droits import est_dg
        # Règle B-06 : Un AD ne peut ni modifier le rôle d'un autre AD ni son propre rôle (403)
        is_cible_ad = (
            collaborateur.role_global in (RoleGlobal.ADMIN, "AD")
            or (collaborateur.role and collaborateur.role.code in (RoleGlobal.ADMIN, "AD"))
        )
        if not est_dg(request.user) and (is_cible_ad or collaborateur.pk == request.user.pk):
            return Response(
                {"detail": _("Seul le Directeur Général a autorité pour gérer les administrateurs.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Règle B-09 : L'AD ne peut pas attribuer DG ou AD
        role_demande = request.data.get("role_global")
        if not est_dg(request.user) and role_demande in (RoleGlobal.DIRECTEUR_GENERAL, "DG", RoleGlobal.ADMIN, "AD"):
            return Response(
                {"detail": _("Seul le Directeur Général peut attribuer ces rôles.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CollaborateurRattacherRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        role_instance = serializer.validated_data.get("role_instance")
        role_global = serializer.validated_data.get("role_global")

        # Règle d'immutabilité absolue du DG : Unique au créateur du tenant
        if est_dg(collaborateur):
            if role_global or role_instance:
                return Response(
                    {
                        "erreur": {
                            "code": "role_dg_immuable",
                            "message": "Le rôle du Directeur Général / Propriétaire est immuable.",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Règle R-DEMO-01 : Seul le DG ou Propriétaire peut attribuer le rôle ADMIN
        est_attribution_admin = (
            role_global in (RoleGlobal.ADMIN, "AD")
            or (role_instance and role_instance.code in (RoleGlobal.ADMIN, "AD"))
        )
        if est_attribution_admin and not est_dg(request.user):
            raise ActionInterditeDelegue()

        # Règle B-09 : L'AD n'attribue qu'un rôle dont il détient toutes les permissions
        role_cible = role_instance
        if not role_cible and role_global:
            mapped = "BAI" if role_global == "MOA" else ("VI" if role_global == "MOE" else role_global)
            role_cible = Role.objects.filter(code=mapped, supprime_le__isnull=True).first()

        if not est_dg(request.user) and role_cible:
            from apps.core.droits import permissions_du_role, permissions_effectives
            perms_ad = permissions_effectives(request.user, request=request)
            perms_role = permissions_du_role(role_cible)
            if not perms_role.issubset(perms_ad):
                return Response(
                    {"detail": _("Vous ne pouvez attribuer qu'un rôle dont vous possédez toutes les permissions (B-09).")},
                    status=status.HTTP_403_FORBIDDEN,
                )


        try:
            collaborateur = rattacher_collaborateur_a_role(
                collaborateur=collaborateur,
                role=role_instance,
                role_global=role_global,
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        # Recharger les données complètes pour la réponse
        rp_data = None
        if collaborateur.role_personnalise:
            rp_data = {
                "id": collaborateur.role_personnalise.id,
                "code": collaborateur.role_personnalise.code,
                "libelle": collaborateur.role_personnalise.libelle,
            }

        avatar_url = None
        if collaborateur.avatar and hasattr(collaborateur.avatar, "url"):
            try:
                avatar_url = request.build_absolute_uri(collaborateur.avatar.url) if request else collaborateur.avatar.url
            except Exception:
                avatar_url = collaborateur.avatar.url

        reponse_data = {
            "id": collaborateur.id,
            "email": collaborateur.email,
            "nom": collaborateur.nom,
            "prenom": collaborateur.prenom,
            "nom_complet": collaborateur.nom_complet,
            "telephone": collaborateur.telephone,
            "role_global": collaborateur.role_global,
            "role_global_libelle": collaborateur.get_role_global_display(),
            "role_personnalise": rp_data,
            "statut": collaborateur.statut,
            "is_owner": collaborateur.is_owner,
            "cree_le": collaborateur.cree_le,
            "projets": _obtenir_projets_collaborateur(collaborateur),
            "lien_activation": None,
            "avatar_url": avatar_url,
            "derniere_connexion": getattr(collaborateur, "derniere_connexion", getattr(collaborateur, "last_login", None)),
        }

        return Response(
            CollaborateurResponseSerializer(reponse_data).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Modifier un collaborateur (alias du PATCH)",
        request=CollaborateurRattacherRoleSerializer,
        responses={200: CollaborateurResponseSerializer},
    )
    def post(self, request, pk):
        return self.patch(request, pk)

    @extend_schema(
        summary="Retirer un collaborateur de toute la plateforme (départ entreprise)",
        description="Désactive le compte, révoque tous les accès et clôture toutes les affectations de chantiers.",
        responses={200: dict},
    )
    def delete(self, request, pk):
        _autoriser_parametres_collaborateurs(request.user, request=request)

        collaborateur = get_object_or_404(
            Utilisateur.tous_objets,
            pk=pk,
            supprime_le__isnull=True,
        )

        from apps.core.droits import est_dg
        if est_dg(collaborateur):
            return Response(
                {
                    "erreur": {
                        "code": "suppression_dg_interdite",
                        "message": "Le Directeur Général / Propriétaire ne peut pas être désactivé ni supprimé.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Règle B-06 : Un AD ne peut ni supprimer un autre AD ni lui-même (403)
        is_cible_ad = (
            collaborateur.role_global in (RoleGlobal.ADMIN, "AD")
            or (collaborateur.role and collaborateur.role.code in (RoleGlobal.ADMIN, "AD"))
        )
        if not est_dg(request.user) and (is_cible_ad or collaborateur.pk == request.user.pk):
            return Response(
                {
                    "erreur": {
                        "code": "suppression_ad_interdite",
                        "message": "Seul le Directeur Général a autorité pour supprimer un administrateur.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )


        try:
            resultat = desactiver_collaborateur_plateforme(
                collaborateur=collaborateur,
                auteur=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise ValidationError({"detail": msg}) from exc

        return Response(resultat, status=status.HTTP_200_OK)


class ParametresCollaborateurSuspendreView(APIView):
    """`POST /api/v1/parametres/collaborateurs/{id}/suspendre/` — Suspendre un collaborateur."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Suspendre un collaborateur",
        request=None,
        description="Coupe l'accès d'un compte actif sans effacer ses données ni ses affectations.",
        responses={200: CollaborateurResponseSerializer},
    )
    def post(self, request, pk):
        _autoriser_parametres_collaborateurs(request.user, request=request)

        collaborateur = get_object_or_404(
            Utilisateur.tous_objets,
            pk=pk,
            supprime_le__isnull=True,
        )

        from apps.core.droits import est_dg
        if est_dg(collaborateur):
            return Response(
                {"detail": _("Le compte du Directeur Général / Propriétaire ne peut pas être suspendu.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Règle B-06 : Un AD ne peut ni suspendre un autre AD ni son propre compte (403)
        is_cible_ad = (
            collaborateur.role_global in (RoleGlobal.ADMIN, "AD")
            or (collaborateur.role and collaborateur.role.code in (RoleGlobal.ADMIN, "AD"))
        )
        if not est_dg(request.user) and (is_cible_ad or collaborateur.pk == request.user.pk):
            return Response(
                {"detail": _("Seul le Directeur Général a autorité pour suspendre un administrateur ou son propre compte.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        if collaborateur.pk == request.user.pk:
            return Response(
                {"detail": _("Vous ne pouvez pas suspendre votre propre compte.")},
                status=status.HTTP_400_BAD_REQUEST,
            )


        if collaborateur.statut == StatutUtilisateur.DESACTIVE:
            return Response(
                {"detail": _("Ce collaborateur est déjà suspendu / désactivé.")},
                status=status.HTTP_409_CONFLICT,
            )

        collaborateur.statut = StatutUtilisateur.DESACTIVE
        collaborateur.is_active = False
        collaborateur.save(update_fields=["statut", "is_active"])

        avatar_url = None
        if collaborateur.avatar and hasattr(collaborateur.avatar, "url"):
            try:
                avatar_url = request.build_absolute_uri(collaborateur.avatar.url) if request else collaborateur.avatar.url
            except Exception:
                avatar_url = collaborateur.avatar.url

        rp_data = None
        if collaborateur.role_personnalise:
            rp_data = {
                "id": collaborateur.role_personnalise.id,
                "code": collaborateur.role_personnalise.code,
                "libelle": collaborateur.role_personnalise.libelle,
            }

        reponse_data = {
            "id": collaborateur.id,
            "email": collaborateur.email,
            "nom": collaborateur.nom,
            "prenom": collaborateur.prenom,
            "nom_complet": collaborateur.nom_complet,
            "telephone": collaborateur.telephone,
            "role_global": collaborateur.role_global,
            "role_global_libelle": collaborateur.get_role_global_display(),
            "role_personnalise": rp_data,
            "statut": collaborateur.statut,
            "is_owner": collaborateur.is_owner,
            "cree_le": collaborateur.cree_le,
            "projets": _obtenir_projets_collaborateur(collaborateur),
            "lien_activation": None,
            "avatar_url": avatar_url,
            "derniere_connexion": getattr(collaborateur, "derniere_connexion", getattr(collaborateur, "last_login", None)),
        }
        return Response(CollaborateurResponseSerializer(reponse_data).data, status=status.HTTP_200_OK)


class ParametresCollaborateurReactiverView(APIView):
    """`POST /api/v1/parametres/collaborateurs/{id}/reactiver/` — Réactiver un collaborateur."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="Réactiver un collaborateur",
        request=None,
        description="Rétablit l'accès d'un compte collaborateur précédemment suspendu.",
        responses={200: CollaborateurResponseSerializer},
    )
    def post(self, request, pk):
        _autoriser_parametres_collaborateurs(request.user, request=request)

        collaborateur = get_object_or_404(
            Utilisateur.tous_objets,
            pk=pk,
            supprime_le__isnull=True,
        )

        from apps.core.droits import est_dg
        # Règle B-06 : Un AD ne peut ni réactiver un autre AD ni son propre compte (403)
        is_cible_ad = (
            collaborateur.role_global in (RoleGlobal.ADMIN, "AD")
            or (collaborateur.role and collaborateur.role.code in (RoleGlobal.ADMIN, "AD"))
        )
        if not est_dg(request.user) and (is_cible_ad or collaborateur.pk == request.user.pk):
            return Response(
                {"detail": _("Seul le Directeur Général a autorité pour réactiver un administrateur.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        if collaborateur.statut == StatutUtilisateur.ACTIF:

            return Response(
                {"detail": _("Ce collaborateur est déjà actif.")},
                status=status.HTTP_409_CONFLICT,
            )

        collaborateur.statut = StatutUtilisateur.ACTIF
        collaborateur.is_active = True
        collaborateur.save(update_fields=["statut", "is_active"])

        avatar_url = None
        if collaborateur.avatar and hasattr(collaborateur.avatar, "url"):
            try:
                avatar_url = request.build_absolute_uri(collaborateur.avatar.url) if request else collaborateur.avatar.url
            except Exception:
                avatar_url = collaborateur.avatar.url

        rp_data = None
        if collaborateur.role_personnalise:
            rp_data = {
                "id": collaborateur.role_personnalise.id,
                "code": collaborateur.role_personnalise.code,
                "libelle": collaborateur.role_personnalise.libelle,
            }

        reponse_data = {
            "id": collaborateur.id,
            "email": collaborateur.email,
            "nom": collaborateur.nom,
            "prenom": collaborateur.prenom,
            "nom_complet": collaborateur.nom_complet,
            "telephone": collaborateur.telephone,
            "role_global": collaborateur.role_global,
            "role_global_libelle": collaborateur.get_role_global_display(),
            "role_personnalise": rp_data,
            "statut": collaborateur.statut,
            "is_owner": collaborateur.is_owner,
            "cree_le": collaborateur.cree_le,
            "projets": _obtenir_projets_collaborateur(collaborateur),
            "lien_activation": None,
            "avatar_url": avatar_url,
            "derniere_connexion": getattr(collaborateur, "derniere_connexion", getattr(collaborateur, "last_login", None)),
        }
        return Response(CollaborateurResponseSerializer(reponse_data).data, status=status.HTTP_200_OK)
