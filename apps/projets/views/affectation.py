"""Vues API pour la gestion de l'équipe de chantier / affectations (US-04 / E-05 / C-05)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Utilisateur
from apps.audit.services import journaliser
from apps.core.enums import ActionAudit, StatutUtilisateur
from apps.core.exceptions import RequeteRefusee
from apps.core.ip_restriction import extraire_ip_client
from apps.core.permissions import GardePermissionProjet, obtenir_portee_role
from apps.projets.models import AffectationProjet, Projet
from apps.projets.permissions import PeutRetirerDuProjet
from apps.projets.serializers.affectation import (
    AffectationProjetCreateSerializer,
    AffectationProjetResponseSerializer,
    AffectationProjetUpdateSerializer,
)
from apps.projets.services.affectations import (
    affecter_collaborateur_projet,
    est_chef_projet,
    lister_affectations_projet,
    modifier_affectation_projet,
    revoquer_affectation_projet,
    verifier_peut_gerer_chef_projet,
)

__all__ = [
    "CollaborateursAffectablesView",
    "ProjetAffectationDetailView",
    "ProjetAffectationListCreateView",
    "ProjetChefChantierView",
    "ProjetRemplacerView",
]


def _booleen_drf(valeur) -> bool | None:
    """Le booléen tel que le lira le serializer (`"no"`, `"off"`… compris), sinon `None`.

    La garde du chef de projet lit la requête brute : si elle reconnaissait moins
    d'écritures que DRF, `{"est_actif": "no"}` passerait à côté d'elle.
    """
    if valeur is None:
        return None
    try:
        return serializers.BooleanField().to_internal_value(valeur)
    except serializers.ValidationError:
        return None  # le serializer répondra 400


class ProjetAffectationListCreateView(APIView):
    """`GET` et `POST /api/v1/projets/{projet_id}/affectations/`."""

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [
                IsAuthenticated(),
                GardePermissionProjet.pour("projets.affecter_membres")(),
            ]
        return [
            IsAuthenticated(),
            GardePermissionProjet.pour("projets.lire")(),
        ]

    @extend_schema(
        summary="Lister les membres de l'équipe du chantier",
        description=(
            "Renvoie tous les collaborateurs affectés au projet avec leurs rôles et statuts."
        ),
        responses={200: AffectationProjetResponseSerializer(many=True)},
    )
    def get(self, request, projet_id):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        actifs_seulement = request.query_params.get("actifs_seulement", "false").lower() == "true"
        qs = lister_affectations_projet(projet, actifs_seulement=actifs_seulement)
        serializer = AffectationProjetResponseSerializer(
            qs, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Affecter un collaborateur au chantier",
        description=(
            "Associe un collaborateur à ce projet avec un rôle spécifique "
            "(CT, CC, Consultant lecture, MOE, MOA, etc.)."
        ),
        request=AffectationProjetCreateSerializer,
        responses={201: AffectationProjetResponseSerializer},
    )
    def post(self, request, projet_id):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(projet)

        serializer = AffectationProjetCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        utilisateur = serializer.validated_data["utilisateur_instance"]
        role_projet = serializer.validated_data["role_projet"]
        # Nommer un chef de projet — ou réécrire l'affectation de celui qui l'est — est réservé
        # à la direction. La ligne existante compte : une réaffectation la réactive et en
        # change le rôle.
        existante = AffectationProjet.tous_objets.filter(
            projet=projet, utilisateur=utilisateur
        ).first()
        remplace_un_cp = bool(
            existante
            and existante.est_actif
            and existante.supprime_le is None
            and est_chef_projet(existante.role_projet)
        )
        if est_chef_projet(role_projet) or remplace_un_cp:
            verifier_peut_gerer_chef_projet(request.user, request=request)

        try:
            affectation = affecter_collaborateur_projet(
                projet=projet,
                utilisateur=utilisateur,
                role_projet=role_projet,
                date_debut=serializer.validated_data.get("date_debut"),
                date_fin=serializer.validated_data.get("date_fin"),
                perimetres_ids=serializer.validated_data.get("perimetres_ids") or [],
                fonction_membre=serializer.validated_data.get("fonction_membre", ""),
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise RequeteRefusee(msg) from exc

        return Response(
            AffectationProjetResponseSerializer(affectation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProjetAffectationDetailView(APIView):
    """`GET`, `PATCH` et `DELETE /api/v1/projets/{projet_id}/affectations/{pk}/`.

    Effacement physique par défaut sur DELETE (décision du 15/10/2026, B4) :
    Contrairement à la règle générale de suppression logique du Socle Commun,
    le retrait d'un collaborateur d'un projet supprime physiquement la ligne
    d'affectation par défaut (?hard=true implicite). Ce choix libère la
    contrainte d'unicité `uq_affectation_utilisateur_projet` et permet de
    réaffecter ultérieurement la même personne au projet. Passer ?hard=false
    conserve l'ancien comportement de désactivation / révocation logique.
    """

    parser_classes = [JSONParser]

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT"):
            return [
                IsAuthenticated(),
                GardePermissionProjet.pour("projets.affecter_membres")(),
            ]
        if self.request.method == "DELETE":
            return [
                IsAuthenticated(),
                PeutRetirerDuProjet(),
            ]
        return [
            IsAuthenticated(),
            GardePermissionProjet.pour("projets.lire")(),
        ]

    @extend_schema(
        summary="Détail d'une affectation de chantier",
        responses={200: AffectationProjetResponseSerializer},
    )
    def get(self, request, projet_id, pk):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        affectation = get_object_or_404(
            AffectationProjet.objects.select_related("utilisateur").prefetch_related(
                "perimetres"
            ),
            pk=pk,
            projet=projet,
            supprime_le__isnull=True,
        )
        return Response(
            AffectationProjetResponseSerializer(affectation, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Modifier une affectation ou désactiver un collaborateur",
        request=AffectationProjetUpdateSerializer,
        responses={200: AffectationProjetResponseSerializer},
    )
    def patch(self, request, projet_id, pk):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(projet)

        affectation = get_object_or_404(
            AffectationProjet.objects.select_related("utilisateur").prefetch_related(
                "perimetres"
            ),
            pk=pk,
            projet=projet,
            supprime_le__isnull=True,
        )

        # Désactiver, rétrograder, réactiver ou nommer un chef de projet : la direction seule.
        # Les dates ou le périmètre du chef de projet restent modifiables par qui affecte.
        # Le contrôle lit la requête brute et passe **avant** la validation : sinon une
        # rétrogradation par un non-dirigeant recevrait un 400 de cohérence de rôle, et non le 403.
        brut = request.data if isinstance(request.data, dict) else {}
        role_demande = brut.get("role_projet")
        nouveau_role = role_demande.strip().upper() if isinstance(role_demande, str) else None
        actif_demande = _booleen_drf(brut.get("est_actif"))
        if est_chef_projet(affectation.role_projet):
            desactive = actif_demande is False
            reactive = actif_demande is True and not affectation.est_actif
            retrograde = nouveau_role is not None and not est_chef_projet(nouveau_role)
            touche_au_cp = desactive or reactive or retrograde
        else:
            touche_au_cp = est_chef_projet(nouveau_role)
        if touche_au_cp:
            verifier_peut_gerer_chef_projet(request.user, request=request)

        serializer = AffectationProjetUpdateSerializer(
            instance=affectation, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)

        try:
            affectation = modifier_affectation_projet(
                affectation=affectation,
                donnees=serializer.validated_data,
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise RequeteRefusee(msg) from exc

        return Response(
            AffectationProjetResponseSerializer(affectation, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Révoquer ou supprimer une affectation de chantier",
        responses={204: None},
    )
    def delete(self, request, projet_id, pk):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(projet)

        affectation = get_object_or_404(
            AffectationProjet.objects.select_related("utilisateur"),
            pk=pk,
            projet=projet,
            supprime_le__isnull=True,
        )

        if affectation.utilisateur_id == request.user.id:
            raise PermissionDenied("Vous ne pouvez pas vous retirer vous-même d'un projet.")

        if est_chef_projet(affectation.role_projet):
            verifier_peut_gerer_chef_projet(request.user, request=request)

        hard_param = request.query_params.get("hard", "true").lower()
        suppression_physique = hard_param != "false"

        # L'instantané d'avant est pris maintenant : après un effacement physique, la ligne
        # n'existe plus. La trace, elle, ne s'écrit qu'**après** un retrait réussi — sinon un
        # refus du service laisserait au journal une suppression qui n'a pas eu lieu.
        avant = {
            "projet_id": str(projet.pk),
            "projet_reference": projet.reference,
            "utilisateur_id": str(affectation.utilisateur_id),
            "utilisateur_email": getattr(affectation.utilisateur, "email", ""),
            "role_projet": affectation.role_projet,
            "perimetres_ids": [str(e.pk) for e in affectation.perimetres.all()],
            "fonction_membre": affectation.fonction_membre,
        }
        identifiant = affectation.pk

        try:
            revoquer_affectation_projet(
                affectation=affectation,
                suppression_physique=suppression_physique,
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise RequeteRefusee(msg) from exc

        journaliser(
            action=ActionAudit.SUPPRESSION,
            type_entite="affectation_projet",
            entite_id=identifiant,
            utilisateur_id=request.user.pk,
            valeur_avant=avant,
            valeur_apres={"physique": suppression_physique},
            adresse_ip=extraire_ip_client(request),
            appareil=request.headers.get("User-Agent", "")[:255],
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class CollaborateursAffectablesView(APIView):
    """`GET /api/v1/projets/{projet_id}/collaborateurs-affectables/` (L5-1 / C-05 puce 2)."""

    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.affecter_membres"),
    ]

    @extend_schema(
        summary="Liste réduite des collaborateurs affectables au chantier",
        description=(
            "Retourne la liste des collaborateurs actifs dont le rôle est à portée PROJET. "
            "Champs limités à id, nom, role. Exclut toute information personnelle "
            "(email, téléphone) et les rôles de portée ENTREPRISE (DG, AD, DO)."
        ),
        responses={200: serializers.ListSerializer(child=serializers.DictField())},
    )
    def get(self, request, projet_id):
        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)

        candidats = (
            Utilisateur.objects.filter(
                is_active=True,
                statut=StatutUtilisateur.ACTIF,
                supprime_le__isnull=True,
            )
            .select_related("role")
            .order_by("nom", "prenom")
        )

        resultats = []
        for u in candidats:
            portee = obtenir_portee_role(u)
            if portee == "ENTREPRISE":
                continue

            role_libelle = u.role.libelle if u.role else (u.role_global or "")
            nom_complet = f"{u.prenom} {u.nom}".strip() or u.nom
            resultats.append(
                {
                    "id": u.id,
                    "nom": nom_complet,
                    "role": role_libelle,
                    # Le code (CP, CT, CC…) : le formulaire ne propose pour une place que
                    # les personnes qui ont ce rôle sur la plateforme.
                    "role_code": ((u.role.code if u.role else u.role_global) or "").upper(),
                }
            )

        return Response(resultats, status=status.HTTP_200_OK)


class RemplacementSerializer(serializers.Serializer):
    role_projet = serializers.CharField(max_length=50)
    utilisateur_id = serializers.UUIDField(help_text="Le nouveau titulaire du rôle.")
    affectation_remplacee_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Qui est remplacé. Inutile pour un rôle unique : c'est son titulaire.",
    )
    perimetres_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        help_text="Vide : tout le projet.",
    )
    date_changement = serializers.DateField(required=False, allow_null=True)


def _nouveau_titulaire(utilisateur_id) -> Utilisateur:
    utilisateur = Utilisateur.objects.filter(
        pk=utilisateur_id,
        supprime_le__isnull=True,
        is_active=True,
        statut=StatutUtilisateur.ACTIF,
    ).first()
    if utilisateur is None:
        raise RequeteRefusee("Collaborateur introuvable, inactif ou suspendu.")
    if obtenir_portee_role(utilisateur) == "ENTREPRISE":
        raise RequeteRefusee(
            "Un collaborateur à portée ENTREPRISE ne peut pas être affecté à un projet."
        )
    return utilisateur


def _reponse_remplacement(request, resultat) -> dict:
    ancien = resultat["ancien"]
    return {
        "titulaire": AffectationProjetResponseSerializer(
            resultat["nouveau"], context={"request": request}
        ).data,
        "remplace": (
            AffectationProjetResponseSerializer(ancien, context={"request": request}).data
            if ancien
            else None
        ),
    }


class RemplacementReponseSerializer(serializers.Serializer):
    titulaire = AffectationProjetResponseSerializer()
    remplace = AffectationProjetResponseSerializer(allow_null=True)


class ProjetRemplacerView(APIView):
    """`POST /api/v1/projets/{projet_id}/affectations/remplacer/` — remplacer un titulaire.

    L'ancien perd sa fonction ce jour (son affectation est close et reste dans l'historique), le
    nouveau est affecté avec le même rôle, en une seule fois (30/10/2026). C'est le seul moyen
    de changer de titulaire d'un rôle « unique par projet ». Exige `projets.affecter_membres` ;
    le chef de projet reste protégé (DG et rôles de portée Entreprise).
    """

    parser_classes = [JSONParser]
    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.affecter_membres"),
    ]

    @extend_schema(
        summary="Remplacer la personne qui tient un rôle sur le projet",
        tags=["affectations"],
        request=RemplacementSerializer,
        responses={200: RemplacementReponseSerializer},
    )
    def post(self, request, projet_id):
        from apps.projets.services.affectations import (
            est_chef_projet,
            remplacer_titulaire,
            verifier_peut_gerer_chef_projet,
        )
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        verifier_statut_projet_pour_ecriture(projet)
        serializer = RemplacementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        if est_chef_projet(v["role_projet"]):
            verifier_peut_gerer_chef_projet(request.user, request=request)
        try:
            resultat = remplacer_titulaire(
                projet=projet,
                role_projet=v["role_projet"],
                utilisateur=_nouveau_titulaire(v["utilisateur_id"]),
                affectation_remplacee_id=v["affectation_remplacee_id"],
                perimetres_ids=v.get("perimetres_ids") or [],
                date_changement=v.get("date_changement"),
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise RequeteRefusee(msg) from exc
        return Response(_reponse_remplacement(request, resultat), status=status.HTTP_200_OK)


class ChangerChefChantierSerializer(serializers.Serializer):
    utilisateur_id = serializers.UUIDField()
    perimetres_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        help_text="Vide : tout le projet (le cas courant d'un chef de chantier unique).",
    )
    date_changement = serializers.DateField(required=False, allow_null=True)


class ProjetChefChantierView(APIView):
    """`POST /api/v1/projets/{projet_id}/chef-chantier/` — changer de chef de chantier.

    Le remplacement (`affectations/remplacer/`) appliqué au rôle CC, gardé pour les écrans qui
    l'appellent déjà. Il exige `projets.affecter_membres`.
    """

    parser_classes = [JSONParser]
    permission_classes = [
        IsAuthenticated,
        GardePermissionProjet.pour("projets.affecter_membres"),
    ]

    @extend_schema(
        summary="Changer le chef de chantier du projet",
        tags=["affectations"],
        request=ChangerChefChantierSerializer,
        responses={200: AffectationProjetResponseSerializer},
    )
    def post(self, request, projet_id):
        from apps.projets.services.affectations import changer_chef_chantier
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)
        self.check_object_permissions(request, projet)
        verifier_statut_projet_pour_ecriture(projet)
        serializer = ChangerChefChantierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resultat = changer_chef_chantier(
                projet=projet,
                utilisateur=_nouveau_titulaire(serializer.validated_data["utilisateur_id"]),
                perimetres_ids=serializer.validated_data.get("perimetres_ids") or [],
                date_changement=serializer.validated_data.get("date_changement"),
                modifie_par=request.user,
            )
        except DjangoValidationError as exc:
            msg = str(exc.message if hasattr(exc, "message") else exc)
            raise RequeteRefusee(msg) from exc
        donnees = AffectationProjetResponseSerializer(
            resultat["nouveau"], context={"request": request}
        ).data
        ancien = resultat["ancien"]
        return Response(
            {
                "chef_chantier": donnees,
                "ancien_chef_chantier": (
                    AffectationProjetResponseSerializer(ancien, context={"request": request}).data
                    if ancien
                    else None
                ),
            },
            status=status.HTTP_200_OK,
        )
