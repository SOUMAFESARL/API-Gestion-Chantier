"""Routes des équipes de chantier et du registre de main-d'œuvre.

Gérer les équipes exige `projets.gerer_equipes` (par défaut : chef de projet et conducteur de
travaux) ; le registre de main-d'œuvre, `projets.main_oeuvre_gerer` (mêmes défauts). Les
écritures rendent `avertissements` : ce qui mérite l'attention sans rien refuser.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.droits import APermission
from apps.core.permissions import GardePermissionProjet
from apps.projets.models import (
    AffectationEquipeElement,
    Element,
    EquipeChantier,
    MembreEquipeChantier,
    PersonneMainOeuvre,
    Projet,
)
from apps.projets.serializers.equipe import (
    AffectationEquipeCreationSerializer,
    AffectationEquipeSerializer,
    EquipeCreationSerializer,
    EquipeModificationSerializer,
    EquipeSerializer,
    MembreCreationSerializer,
    MembreModificationSerializer,
    MembreSerializer,
    PersonneCreationSerializer,
    PersonneModificationSerializer,
    PersonneSerializer,
)
from apps.projets.services import equipes as service
from apps.projets.services import main_oeuvre

__all__ = [
    "MainOeuvreDetailView",
    "MainOeuvreListCreateView",
    "ProjetEquipeAffectationDetailView",
    "ProjetEquipeAffectationView",
    "ProjetEquipeDetailView",
    "ProjetEquipeListCreateView",
    "ProjetEquipeMembreDetailView",
    "ProjetEquipeMembreListCreateView",
    "ProjetEquipeStatistiquesView",
]

TAGS = ["équipes"]
ERREURS_EQUIPES = {
    401: OpenApiResponse(description="Authentification requise."),
    403: OpenApiResponse(description="Accès au projet refusé."),
    404: OpenApiResponse(description="Projet, équipe ou case absent du projet ou supprimé."),
}


class BaseEquipeView(APIView):
    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsAuthenticated(), GardePermissionProjet.pour("projets.gerer_equipes")()]
        return [IsAuthenticated(), GardePermissionProjet.pour("projets.lire")()]

    def projet(self, request, pk, verrou=False):
        qs = Projet.objects.select_for_update() if verrou else Projet.objects.all()
        projet = get_object_or_404(qs, pk=pk)
        self.check_object_permissions(request, projet)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

            verifier_statut_projet_pour_ecriture(projet)
        return projet


def equipes_projet(projet):
    return projet.equipes.select_related("entreprise_partenaire").prefetch_related(
        "membres__personne__entreprise_partenaire",
        "affectations_elements__element__niveau",
    )


def _reponse_equipe(equipe, avertissements=None, statut=200, historique=False):
    equipe = equipes_projet(equipe.projet).get(pk=equipe.pk)
    return Response(
        {
            **EquipeSerializer(equipe, context={"historique": historique}).data,
            "avertissements": avertissements or [],
        },
        status=statut,
    )


class ProjetEquipeListCreateView(BaseEquipeView):
    """`GET`/`POST /api/v1/projets/{id}/equipes/`."""

    @extend_schema(
        tags=TAGS,
        summary="Lister les équipes du projet",
        parameters=[
            OpenApiParameter("historique", bool, description="Inclure les membres partis.")
        ],
        responses={200: EquipeSerializer(many=True), **ERREURS_EQUIPES},
    )
    def get(self, request, pk):
        historique = request.query_params.get("historique", "false").lower() == "true"
        return Response(
            EquipeSerializer(
                equipes_projet(self.projet(request, pk)),
                many=True,
                context={"historique": historique},
            ).data
        )

    @extend_schema(
        tags=TAGS,
        summary="Créer une équipe",
        description=(
            "Rattachée à notre entreprise (`entreprise_partenaire_id` vide) ou à un partenaire "
            "(sous-traitant, tâcheron, prestataire). Les membres viennent du registre de "
            "main-d'œuvre ; un seul chef, de la même entreprise que l'équipe."
        ),
        request=EquipeCreationSerializer,
        responses={201: EquipeSerializer, **ERREURS_EQUIPES},
    )
    @transaction.atomic
    def post(self, request, pk):
        projet = self.projet(request, pk, verrou=True)
        donnees = EquipeCreationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        v = donnees.validated_data
        equipe, avertissements = service.creer_equipe(
            projet,
            nom=v["nom"],
            corps_etat=v["corps_etat"],
            entreprise_partenaire=v["entreprise_partenaire_id"],
            membres=[dict(m) for m in v["membres"]],
            createur=request.user,
        )
        return _reponse_equipe(equipe, avertissements, statut=status.HTTP_201_CREATED)


class ProjetEquipeDetailView(BaseEquipeView):
    """`GET`/`PATCH`/`DELETE /api/v1/projets/{id}/equipes/{equipe_id}/`."""

    @extend_schema(tags=TAGS, summary="Consulter une équipe", responses={200: EquipeSerializer})
    def get(self, request, pk, equipe_id):
        projet = self.projet(request, pk)
        equipe = get_object_or_404(equipes_projet(projet), pk=equipe_id)
        historique = request.query_params.get("historique", "true").lower() == "true"
        return Response(EquipeSerializer(equipe, context={"historique": historique}).data)

    @extend_schema(
        tags=TAGS,
        summary="Modifier une équipe",
        request=EquipeModificationSerializer,
        responses={200: EquipeSerializer},
    )
    def patch(self, request, pk, equipe_id):
        projet = self.projet(request, pk)
        equipe = get_object_or_404(EquipeChantier, projet=projet, pk=equipe_id)
        donnees = EquipeModificationSerializer(data=request.data, partial=True)
        donnees.is_valid(raise_exception=True)
        valides = dict(donnees.validated_data)
        if "entreprise_partenaire_id" in valides:
            valides["entreprise_partenaire"] = valides.pop("entreprise_partenaire_id")
        equipe, avertissements = service.modifier_equipe(equipe, donnees=valides)
        return _reponse_equipe(equipe, avertissements)

    @extend_schema(tags=TAGS, summary="Supprimer une équipe", responses={204: None})
    @transaction.atomic
    def delete(self, request, pk, equipe_id):
        projet = self.projet(request, pk, verrou=True)
        equipe = get_object_or_404(EquipeChantier, projet=projet, pk=equipe_id)
        for affectation in equipe.affectations_elements.all():
            affectation.delete(utilisateur=request.user)
        equipe.delete(utilisateur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjetEquipeMembreListCreateView(BaseEquipeView):
    """`POST /api/v1/projets/{id}/equipes/{equipe_id}/membres/` — ajouter un membre du registre."""

    @extend_schema(
        tags=TAGS,
        summary="Ajouter un membre",
        description=(
            "La personne vient du registre de main-d'œuvre. Une personne déjà dans une autre "
            "équipe le même jour est acceptée, avec un avertissement."
        ),
        request=MembreCreationSerializer,
        responses={201: MembreSerializer, **ERREURS_EQUIPES},
    )
    def post(self, request, pk, equipe_id):
        projet = self.projet(request, pk)
        equipe = get_object_or_404(EquipeChantier, projet=projet, pk=equipe_id)
        donnees = MembreCreationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        membre, avertissements = service.ajouter_membre(
            equipe, createur=request.user, **donnees.validated_data
        )
        return Response(
            {**MembreSerializer(membre).data, "avertissements": avertissements},
            status=status.HTTP_201_CREATED,
        )


class ProjetEquipeMembreDetailView(BaseEquipeView):
    """`PATCH`/`DELETE /api/v1/projets/{id}/equipes/{equipe_id}/membres/{membre_id}/`.

    `DELETE` enregistre un départ daté (`?date_depart=AAAA-MM-JJ`, aujourd'hui par défaut) ;
    `?supprimer=true` efface une erreur de saisie.
    """

    def _membre(self, request, pk, equipe_id, membre_id):
        projet = self.projet(request, pk)
        equipe = get_object_or_404(EquipeChantier, projet=projet, pk=equipe_id)
        return get_object_or_404(
            MembreEquipeChantier.objects.select_related("personne", "equipe"),
            pk=membre_id,
            equipe=equipe,
        )

    @extend_schema(
        tags=TAGS,
        summary="Modifier un membre (fonction, chef, arrivée, départ)",
        request=MembreModificationSerializer,
        responses={200: MembreSerializer},
    )
    def patch(self, request, pk, equipe_id, membre_id):
        membre = self._membre(request, pk, equipe_id, membre_id)
        donnees = MembreModificationSerializer(data=request.data, partial=True)
        donnees.is_valid(raise_exception=True)
        membre, avertissements = service.modifier_membre(
            membre, donnees=dict(donnees.validated_data)
        )
        return Response({**MembreSerializer(membre).data, "avertissements": avertissements})

    @extend_schema(
        tags=TAGS,
        summary="Enregistrer le départ d'un membre",
        parameters=[
            OpenApiParameter(
                "date_depart", str, description="AAAA-MM-JJ ; aujourd'hui par défaut."
            ),
            OpenApiParameter("supprimer", bool, description="Efface une erreur de saisie."),
        ],
        responses={204: None},
    )
    def delete(self, request, pk, equipe_id, membre_id):
        membre = self._membre(request, pk, equipe_id, membre_id)
        date_depart = None
        if request.query_params.get("date_depart"):
            date_depart = serializers.DateField().run_validation(
                request.query_params["date_depart"]
            )
        service.retirer_membre(
            membre,
            date_depart=date_depart,
            supprimer=request.query_params.get("supprimer", "false").lower() == "true",
            utilisateur=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjetEquipeAffectationView(BaseEquipeView):
    """`GET`/`POST /api/v1/projets/{id}/equipes/affectations/` — poser une équipe sur une case.

    Une équipe posée sur une case vaut pour tout le sous-arbre ; une case reçoit plusieurs
    équipes ; une affectation plus bas remplace celle d'en haut pour sa branche.
    """

    @extend_schema(
        tags=TAGS,
        summary="Affectations des équipes",
        responses={200: AffectationEquipeSerializer(many=True)},
    )
    def get(self, request, pk):
        projet = self.projet(request, pk)
        affectations = AffectationEquipeElement.objects.filter(
            equipe__projet=projet
        ).select_related("element__niveau")
        return Response(AffectationEquipeSerializer(affectations, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Affecter une équipe à une case",
        request=AffectationEquipeCreationSerializer,
        responses={201: AffectationEquipeSerializer},
    )
    def post(self, request, pk):
        projet = self.projet(request, pk)
        donnees = AffectationEquipeCreationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        equipe = get_object_or_404(
            EquipeChantier, pk=donnees.validated_data["equipe_id"], projet=projet
        )
        element = get_object_or_404(Element, pk=donnees.validated_data["element_id"], projet=projet)
        from apps.projets.services.perimetres import exiger

        exiger(request.user, "projets.gerer_equipes", projet, element, request=request)
        affectation, avertissements = service.affecter_equipe(
            equipe, element, createur=request.user
        )
        return Response(
            {**AffectationEquipeSerializer(affectation).data, "avertissements": avertissements},
            status=status.HTTP_201_CREATED,
        )


class ProjetEquipeAffectationDetailView(BaseEquipeView):
    """`DELETE /api/v1/projets/{id}/equipes/affectations/{affectation_id}/`."""

    @extend_schema(tags=TAGS, summary="Retirer une équipe d'une case", responses={204: None})
    def delete(self, request, pk, affectation_id):
        projet = self.projet(request, pk)
        affectation = get_object_or_404(
            AffectationEquipeElement, pk=affectation_id, equipe__projet=projet
        )
        service.retirer_affectation_equipe(affectation, utilisateur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StatistiquesEquipesSerializer(serializers.Serializer):
    equipes_count = serializers.IntegerField()
    effectif_mobilise = serializers.IntegerField()
    feuilles_couvertes = serializers.IntegerField()
    feuilles_a_couvrir = serializers.IntegerField()


class ProjetEquipeStatistiquesView(BaseEquipeView):
    """`GET /api/v1/projets/{id}/equipes/statistiques/`."""

    @extend_schema(
        tags=TAGS,
        summary="Statistiques des équipes",
        description=(
            "Équipes actives ; effectif présent (membres sans départ, personnes dédupliquées) ; "
            "tâches ouvertes couvertes par une équipe, directement ou par héritage."
        ),
        responses={200: StatistiquesEquipesSerializer, **ERREURS_EQUIPES},
    )
    def get(self, request, pk):
        from apps.projets.selectors.arbre import charger_arbre
        from apps.projets.services.sante_calculs import calculer_avancement_physique_feuille

        projet = self.projet(request, pk)
        equipes = list(equipes_projet(projet).filter(est_actif=True))
        personnes = {
            m.personne_id
            for e in equipes
            for m in e.membres.all()
            if m.supprime_le is None and m.date_depart is None
        }
        arbre = charger_arbre(projet)
        couvertes_chemins = [
            a.element.chemin
            for e in equipes
            for a in e.affectations_elements.all()
            if a.supprime_le is None
        ]
        ouvertes = [f for f in arbre.feuilles() if calculer_avancement_physique_feuille(f) < 100]
        couvertes = [f for f in ouvertes if any(f.chemin.startswith(c) for c in couvertes_chemins)]
        return Response(
            {
                "equipes_count": len(equipes),
                "effectif_mobilise": len(personnes),
                "feuilles_couvertes": len(couvertes),
                "feuilles_a_couvrir": len(ouvertes) - len(couvertes),
            }
        )


# --------------------------------------------------------------------------
# Registre de main-d'œuvre
# --------------------------------------------------------------------------
class MainOeuvreListCreateView(APIView):
    """`GET`/`POST /api/v1/main-oeuvre/` — le registre de l'entreprise."""

    def get_permissions(self):
        code = "projets.main_oeuvre_gerer" if self.request.method == "POST" else "projets.lire"
        return [IsAuthenticated(), APermission.pour(code)()]

    @extend_schema(
        tags=TAGS,
        summary="Registre de main-d'œuvre",
        parameters=[
            OpenApiParameter("recherche", str),
            OpenApiParameter(
                "entreprise", str, description="« INTERNE » ou l'identifiant d'un partenaire."
            ),
            OpenApiParameter("inactives", bool),
        ],
        responses={200: PersonneSerializer(many=True)},
    )
    def get(self, request):
        personnes = main_oeuvre.lister_personnes(
            recherche=request.query_params.get("recherche", "").strip(),
            entreprise=request.query_params.get("entreprise", "").strip(),
            actives=request.query_params.get("inactives", "false").lower() != "true",
        )
        return Response(PersonneSerializer(personnes, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Ajouter une personne au registre",
        description="Nom et prénom obligatoires, téléphone facultatif.",
        request=PersonneCreationSerializer,
        responses={201: PersonneSerializer},
    )
    def post(self, request):
        from apps.accounts.models import Utilisateur

        donnees = PersonneCreationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        v = dict(donnees.validated_data)
        utilisateur = None
        if v.pop("utilisateur_id", None):
            utilisateur = get_object_or_404(
                Utilisateur, pk=donnees.validated_data["utilisateur_id"], supprime_le__isnull=True
            )
        personne = main_oeuvre.creer_personne(
            entreprise_partenaire=v.pop("entreprise_partenaire_id"),
            utilisateur=utilisateur,
            createur=request.user,
            **v,
        )
        return Response(PersonneSerializer(personne).data, status=status.HTTP_201_CREATED)


class MainOeuvreDetailView(APIView):
    """`GET`/`PATCH`/`DELETE /api/v1/main-oeuvre/{id}/`."""

    def get_permissions(self):
        code = "projets.lire" if self.request.method == "GET" else "projets.main_oeuvre_gerer"
        return [IsAuthenticated(), APermission.pour(code)()]

    @extend_schema(
        tags=TAGS, summary="Une personne du registre", responses={200: PersonneSerializer}
    )
    def get(self, request, pk):
        return Response(PersonneSerializer(get_object_or_404(PersonneMainOeuvre, pk=pk)).data)

    @extend_schema(
        tags=TAGS,
        summary="Modifier une personne du registre",
        request=PersonneModificationSerializer,
        responses={200: PersonneSerializer},
    )
    def patch(self, request, pk):
        personne = get_object_or_404(PersonneMainOeuvre, pk=pk)
        donnees = PersonneModificationSerializer(data=request.data, partial=True)
        donnees.is_valid(raise_exception=True)
        valides = dict(donnees.validated_data)
        if "entreprise_partenaire_id" in valides:
            valides["entreprise_partenaire"] = valides.pop("entreprise_partenaire_id")
        return Response(
            PersonneSerializer(main_oeuvre.modifier_personne(personne, donnees=valides)).data
        )

    @extend_schema(
        tags=TAGS,
        summary="Retirer une personne du registre",
        description="Désactivée si elle a déjà fait partie d'une équipe, supprimée sinon.",
        responses={204: None},
    )
    def delete(self, request, pk):
        main_oeuvre.retirer_personne(
            get_object_or_404(PersonneMainOeuvre, pk=pk), utilisateur=request.user
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
