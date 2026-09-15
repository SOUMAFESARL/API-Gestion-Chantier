"""Vues API pour la météo et le référentiel des localités."""

import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projets.models import AffectationProjet, Projet
from apps.projets.referentiels.villes import lister_villes, nom_agglomeration
from apps.projets.serializers import (
    MeteoResponseSerializer,
    ReferentielVillesResponseSerializer,
)
from apps.projets.services.meteo import (
    PORTEE_CHANTIER,
    PORTEE_ENTREPRISE,
    RAISON_VILLE_ABSENTE,
    meteo_indisponible,
    obtenir_meteo,
)

# **Les rôles qui regardent l'entreprise, pas un chantier.** Direction et
# fonctions transverses : leur bureau est au siège, et c'est la météo du siège
# qui les concerne. Tous les autres rôles sont rattachés à un chantier — la
# météo qu'ils veulent est celle du leur.
#
# Ce découpage n'est pas une permission : il ne donne ni ne retire aucun accès.
# Il ne décide que d'une chose — quelle ville la barre affiche.
ROLES_VUE_SIEGE = frozenset({"AD", "DG", "DF", "RF", "RA", "RH"})


def _localiser(request, tenant) -> tuple[str, str]:
    """La ville dont montrer la météo, et d'où elle vient.

    L'ordre compte :
    1. Paramètre explicite 'ville' (prioritaire pour requêtes manuelles/tests).
    2. Direction générale et fonctions de siège (DG, AD, DF, RF, RA, RH) :
       la barre affiche UNIQUEMENT la météo de la ville du siège de l'entreprise.
       Le Directeur Général ne bascule jamais sur la météo d'un chantier dans la barre.
    3. Fiche d'un chantier (projet_id) pour les rôles opérationnels de terrain.
    4. Rôle de chantier : affectation la plus récente de l'utilisateur.
    5. À défaut : ville de l'entreprise.
    """
    ville_entreprise = (getattr(tenant, "ville", "") or "") if tenant else ""

    ville_demandee = request.query_params.get("ville")
    if ville_demandee:
        return (ville_demandee, PORTEE_CHANTIER)

    is_dg = getattr(request.user, "is_dg", False)
    role = getattr(request.user, "role_global", "") or ""
    if is_dg or role in ROLES_VUE_SIEGE:
        return (ville_entreprise, PORTEE_ENTREPRISE)

    projet_id = request.query_params.get("projet_id")
    if projet_id:
        # L'identifiant est validé **avant** la requête : un `projet_id`
        # fantaisiste dans l'adresse ferait lever le filtre sur la colonne UUID,
        # et la barre d'application n'a pas à tomber pour cela.
        try:
            uuid.UUID(str(projet_id))
        except (ValueError, AttributeError, TypeError):
            projet = None
        else:
            projet = Projet.objects.filter(pk=projet_id, supprime_le__isnull=True).first()
        if projet and projet.ville:
            return (projet.ville, PORTEE_CHANTIER)

    # Rôle de chantier : son affectation la plus récente. Quelqu'un qui suit
    # deux chantiers voit celui sur lequel il vient d'être affecté — faute de
    # mieux, et c'est assumé : la barre n'a de place que pour une ville.
    affectation = (
        AffectationProjet.objects.filter(
            utilisateur=request.user,
            supprime_le__isnull=True,
            projet__supprime_le__isnull=True,
        )
        .select_related("projet")
        .order_by("-cree_le")
        .first()
    )
    if affectation and affectation.projet.ville:
        return (affectation.projet.ville, PORTEE_CHANTIER)

    # Pas encore affecté : la ville de l'entreprise, en le disant.
    return (ville_entreprise, PORTEE_ENTREPRISE)


class MeteoProjetView(APIView):
    """La météo à afficher pour la personne connectée.

    Renvoie des **codes**, jamais des phrases : `condition`, `alerte`, `raison`
    et `portee`. Les mots sont choisis par l'écran — Socle §1.1.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = MeteoResponseSerializer

    @extend_schema(
        summary="Météo à afficher dans la barre d'application",
        description=(
            "Renvoie les conditions météorologiques en temps réel (température, intempéries, praticabilité "
            "du chantier) pour la barre d'état. Détermine la ville selon le rôle de l'utilisateur ou le projet sélectionné."
        ),
        parameters=[
            OpenApiParameter(
                name="projet_id",
                type=uuid.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Chantier dont on veut la météo. À défaut, la ville dépend du "
                    "rôle : le siège pour la direction, son chantier pour les autres."
                ),
            ),
            OpenApiParameter(
                name="ville",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Localité explicite — prioritaire sur la règle de rôle.",
            ),
        ],
        responses={200: MeteoResponseSerializer},
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        pays = (getattr(tenant, "pays", "") or "CI") if tenant else "CI"

        ville, portee = _localiser(request, tenant)

        if not (ville or "").strip():
            return Response(
                meteo_indisponible(RAISON_VILLE_ABSENTE, "", portee),
                status=status.HTTP_200_OK,
            )

        return Response(
            obtenir_meteo(ville=ville, pays=pays, portee=portee),
            status=status.HTTP_200_OK,
        )


class ReferentielVillesView(APIView):
    """Les localités d'un pays — celui de l'entreprise, sauf demande contraire.

    **Le pays par défaut est celui de l'entreprise, pas la Côte d'Ivoire.** Il a
    été choisi à l'inscription ; une entreprise sénégalaise à qui l'on propose
    Cocody et Yopougon n'a rien à en faire.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ReferentielVillesResponseSerializer

    @extend_schema(
        summary="Référentiel des localités d'un pays",
        description="Renvoie la liste officielle des communes ou localités pour les formulaires de chantiers.",
        parameters=[
            OpenApiParameter(
                name="pays",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Code pays ISO à deux lettres. À défaut, le pays de l'entreprise.",
            )
        ],
        responses={200: ReferentielVillesResponseSerializer},
    )
    def get(self, request):
        tenant = getattr(request, "tenant", None)
        demande = request.query_params.get("pays") or ""
        pays = (demande or getattr(tenant, "pays", "") or "CI").strip().upper()

        return Response(
            {
                "pays": pays,
                # Le nom du groupe, vide quand le pays n'a pas d'agglomération
                # découpée en communes. L'écran affiche alors une liste simple.
                "agglomeration": nom_agglomeration(pays),
                "localites": lister_villes(pays),
            },
            status=status.HTTP_200_OK,
        )
