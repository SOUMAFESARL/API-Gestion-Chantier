from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import GardePermissionProjet
from apps.projets.models import Activite, AffectationEquipeActivite, EquipeChantier, Projet
from apps.projets.serializers.equipe import EquipeCreationSerializer, EquipeResponseSerializer
from apps.projets.services.statistiques import pourcentage_realise

ERREURS_EQUIPES = {
    401: OpenApiResponse(description="Authentification requise."),
    403: OpenApiResponse(description="Accès au projet refusé."),
    404: OpenApiResponse(description="Projet, équipe ou activité absent du projet ou supprimé."),
}


class BaseEquipeView(APIView):
    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    def projet(self, request, pk, verrou=False):
        qs = Projet.objects.select_for_update() if verrou else Projet.objects.all()
        projet = get_object_or_404(qs, pk=pk)
        self.check_object_permissions(request, projet)
        return projet


def equipes_projet(projet):
    return projet.equipes.select_related("chef_utilisateur").prefetch_related(
        "membres__utilisateur"
    )


class ProjetEquipeListCreateView(BaseEquipeView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), GardePermissionProjet.pour("projets.gerer_equipes")()]
        return [IsAuthenticated(), GardePermissionProjet.pour("projets.lire")()]

    @extend_schema(
        tags=["équipes"],
        summary="Lister les équipes du projet",
        responses={200: EquipeResponseSerializer(many=True), **ERREURS_EQUIPES},
    )
    def get(self, request, pk):
        return Response(
            EquipeResponseSerializer(
                equipes_projet(self.projet(request, pk)),
                many=True,
            ).data
        )

    @extend_schema(
        tags=["équipes"],
        summary="Constituer une équipe du chantier",
        description=(
            "Chef et membres : utilisateur_id d'un collaborateur actif affecté au projet, "
            "ou nom libre. Saisir un nom ne crée pas de compte et ne donne aucun accès. "
            "Tous les utilisateurs authentifiés ayant accès au projet peuvent constituer "
            "une équipe. Maximum 100 personnes, chef compris."
        ),
        request=EquipeCreationSerializer,
        responses={
            201: EquipeResponseSerializer,
            400: OpenApiResponse(
                description="Champs invalides, personne dupliquée ou hors projet."
            ),
            **ERREURS_EQUIPES,
        },
        examples=[
            OpenApiExample(
                "Équipe maçonnerie",
                request_only=True,
                value={
                    "nom": "Équipe Maçonnerie B",
                    "nature": "INTERNE",
                    "corps_etat": "Maçonnerie",
                    "chef": {"nom": "Chef chantier"},
                    "membres": [{"nom": "Ouvrier 1", "fonction": "OUVRIER"}],
                },
            )
        ],
    )
    @transaction.atomic
    def post(self, request, pk):
        projet = self.projet(request, pk, verrou=True)
        serializer = EquipeCreationSerializer(
            data=request.data, context={"projet": projet, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        return Response(EquipeResponseSerializer(serializer.save()).data, status=201)


class ProjetEquipeDetailView(BaseEquipeView):
    def get_permissions(self):
        if self.request.method in ("DELETE", "PUT", "PATCH"):
            return [IsAuthenticated(), GardePermissionProjet.pour("projets.gerer_equipes")()]
        return [IsAuthenticated(), GardePermissionProjet.pour("projets.lire")()]

    @extend_schema(
        tags=["équipes"],
        summary="Consulter une équipe du projet",
        responses={200: EquipeResponseSerializer, **ERREURS_EQUIPES},
    )
    def get(self, request, pk, equipe_id):
        projet = self.projet(request, pk)
        equipe = get_object_or_404(equipes_projet(projet), pk=equipe_id)
        return Response(EquipeResponseSerializer(equipe).data)

    @extend_schema(
        tags=["équipes"],
        summary="Supprimer logiquement une équipe",
        responses={204: OpenApiResponse(description="Équipe supprimée."), **ERREURS_EQUIPES},
    )
    @transaction.atomic
    def delete(self, request, pk, equipe_id):
        projet = self.projet(request, pk, verrou=True)
        equipe = get_object_or_404(EquipeChantier, projet=projet, pk=equipe_id)
        equipe.delete(utilisateur=request.user)
        return Response(status=204)


class AffectationEquipeSerializer(serializers.Serializer):
    equipe_id = serializers.UUIDField()
    activite_id = serializers.UUIDField()


class AffectationEquipeResponseSerializer(serializers.ModelSerializer):
    equipe_id = serializers.UUIDField(read_only=True)
    activite_id = serializers.UUIDField(read_only=True)
    equipe_nom = serializers.CharField(source="equipe.nom", read_only=True)
    activite_libelle = serializers.CharField(source="activite.libelle", read_only=True)
    lot_id = serializers.UUIDField(source="activite.lot_id", read_only=True)
    lot_nom = serializers.CharField(source="activite.lot.libelle", read_only=True)
    date_debut = serializers.DateField(
        source="activite.date_debut_prevue", read_only=True, allow_null=True
    )
    date_fin = serializers.DateField(
        source="activite.date_fin_prevue", read_only=True, allow_null=True
    )
    statut = serializers.CharField(source="activite.statut", read_only=True)
    effectif = serializers.SerializerMethodField()

    def get_effectif(self, obj) -> int:
        return 1 + len(obj.equipe.membres.all())

    class Meta:
        model = AffectationEquipeActivite
        fields = [
            "id",
            "equipe_id",
            "equipe_nom",
            "activite_id",
            "activite_libelle",
            "lot_id",
            "lot_nom",
            "date_debut",
            "date_fin",
            "effectif",
            "statut",
        ]
        read_only_fields = fields


class ProjetEquipeAffectationView(BaseEquipeView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), GardePermissionProjet.pour("projets.gerer_equipes")()]
        return [IsAuthenticated(), GardePermissionProjet.pour("projets.lire")()]

    @extend_schema(
        tags=["équipes"],
        summary="Lister les affectations équipe-activité",
        description="Période et statut repris de l'activité ; effectif de l'équipe, chef compris.",
        parameters=[
            OpenApiParameter("lot_id", type=str, description="UUID du lot à filtrer."),
            OpenApiParameter("equipe_id", type=str, description="UUID de l'équipe à filtrer."),
            OpenApiParameter(
                "recherche", type=str, description="Libellé de l'activité ou nom d'équipe."
            ),
        ],
        responses={
            200: AffectationEquipeResponseSerializer(many=True),
            400: OpenApiResponse(description="Filtre UUID invalide."),
            **ERREURS_EQUIPES,
        },
    )
    def get(self, request, pk):
        projet = self.projet(request, pk)
        affectations = (
            AffectationEquipeActivite.objects.filter(
                equipe__projet=projet,
                equipe__supprime_le__isnull=True,
                equipe__est_actif=True,
                activite__supprime_le__isnull=True,
                activite__est_actif=True,
                activite__lot__supprime_le__isnull=True,
                activite__lot__est_actif=True,
            )
            .select_related("equipe", "activite__lot")
            .prefetch_related("equipe__membres")
        )
        for parametre, champ in (("lot_id", "activite__lot_id"), ("equipe_id", "equipe_id")):
            if parametre in request.query_params:
                valeur = serializers.UUIDField().run_validation(request.query_params[parametre])
                affectations = affectations.filter(**{champ: valeur})
        recherche = request.query_params.get("recherche", "").strip()
        if recherche:
            affectations = affectations.filter(
                Q(activite__libelle__icontains=recherche) | Q(equipe__nom__icontains=recherche)
            )
        return Response(AffectationEquipeResponseSerializer(affectations, many=True).data)

    @extend_schema(
        tags=["équipes"],
        summary="Affecter une équipe à une activité du projet",
        description=(
            "L'équipe choisie tient l'activité sur toute sa période. "
            "Aucune date ni aucun effectif à saisir. Même projet obligatoire."
        ),
        examples=[
            OpenApiExample(
                "Affectation",
                request_only=True,
                value={
                    "activite_id": "5cf6c2ca-c43b-4768-822c-8df817fb22b0",
                    "equipe_id": "11111111-1111-4111-8111-111111111111",
                },
            )
        ],
        request=AffectationEquipeSerializer,
        responses={
            201: AffectationEquipeResponseSerializer,
            400: OpenApiResponse(description="UUID invalide, doublon ou activité déjà terminée."),
            **ERREURS_EQUIPES,
        },
    )
    @transaction.atomic
    def post(self, request, pk):
        projet = self.projet(request, pk, verrou=True)
        serializer = AffectationEquipeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        equipe = get_object_or_404(
            EquipeChantier, pk=serializer.validated_data["equipe_id"], projet=projet, est_actif=True
        )
        activite = get_object_or_404(
            Activite.objects.select_related("lot"),
            pk=serializer.validated_data["activite_id"],
            lot__projet=projet,
            est_actif=True,
            lot__est_actif=True,
            lot__supprime_le__isnull=True,
        )
        if pourcentage_realise(activite) >= 100:
            raise serializers.ValidationError({"activite_id": "Activité déjà terminée."})
        if AffectationEquipeActivite.objects.filter(equipe=equipe, activite=activite).exists():
            raise serializers.ValidationError("Équipe déjà affectée à cette activité.")
        affectation = AffectationEquipeActivite.objects.create(
            equipe=equipe,
            activite=activite,
            cree_par=request.user,
        )
        return Response(AffectationEquipeResponseSerializer(affectation).data, status=201)


class ProjetEquipeAffectationDetailView(BaseEquipeView):
    def get_permissions(self):
        if self.request.method in ("DELETE", "PUT", "PATCH"):
            return [IsAuthenticated(), GardePermissionProjet.pour("projets.gerer_equipes")()]
        return [IsAuthenticated(), GardePermissionProjet.pour("projets.lire")()]

    @extend_schema(
        tags=["équipes"],
        summary="Retirer l'affectation d'une équipe",
        responses={204: OpenApiResponse(description="Affectation retirée."), **ERREURS_EQUIPES},
    )
    @transaction.atomic
    def delete(self, request, pk, affectation_id):
        projet = self.projet(request, pk, verrou=True)
        affectation = get_object_or_404(
            AffectationEquipeActivite, pk=affectation_id, equipe__projet=projet
        )
        affectation.delete(utilisateur=request.user)
        return Response(status=204)


class StatistiquesEquipesSerializer(serializers.Serializer):
    equipes_count = serializers.IntegerField()
    effectif_mobilise = serializers.IntegerField()
    activites_affectees = serializers.IntegerField()
    activites_a_affecter = serializers.IntegerField()


class ProjetEquipeStatistiquesView(BaseEquipeView):
    @extend_schema(
        tags=["équipes"],
        summary="Statistiques des équipes et affectations",
        description=(
            "Équipes actives, effectif chef compris ; collaborateurs identifiés dédupliqués. "
            "Les activités terminées sont exclues des compteurs d'affectation."
        ),
        responses={200: StatistiquesEquipesSerializer, **ERREURS_EQUIPES},
    )
    def get(self, request, pk):
        projet = self.projet(request, pk)
        equipes = list(equipes_projet(projet).filter(est_actif=True))
        personnes = set()
        for equipe in equipes:
            personnes.add(
                ("id", equipe.chef_utilisateur_id)
                if equipe.chef_utilisateur_id
                else ("chef_libre", equipe.pk)
            )
            for membre in equipe.membres.all():
                personnes.add(
                    ("id", membre.utilisateur_id)
                    if membre.utilisateur_id
                    else ("membre_libre", membre.pk)
                )
        activites = Activite.objects.filter(
            lot__projet=projet, est_actif=True, lot__est_actif=True, lot__supprime_le__isnull=True
        )
        ouvertes = {a.pk for a in activites if pourcentage_realise(a) < 100}
        affectees = set(
            AffectationEquipeActivite.objects.filter(
                equipe__in=equipes,
                activite_id__in=ouvertes,
            ).values_list("activite_id", flat=True)
        )
        return Response(
            {
                "equipes_count": len(equipes),
                "effectif_mobilise": len(personnes),
                "activites_affectees": len(affectees),
                "activites_a_affecter": len(ouvertes - affectees),
            }
        )
