"""Routes du découpage d'un projet en arbre (décisions v1.2 du 26/10/2026).

Les vues restent sans logique : permission, validation, appel du service, réponse. Chaque geste
sur une case vérifie la permission **dans le périmètre** (`services.perimetres.exiger`).
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogue.models import ModeleDecoupagePlateforme
from apps.core.droits import APermission
from apps.core.pagination import PaginationStandard
from apps.core.permissions import GardePermissionProjet
from apps.projets.models import Element, ModeleDecoupageEntreprise, NiveauProjet, Projet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.selectors.arbre_api import representer_arbre, representer_case, visibilite
from apps.projets.serializers.decoupage import (
    AjoutValeursSerializer,
    CreationListeSerializer,
    DeplacementSerializer,
    DetailSerializer,
    DqeApplicationSerializer,
    DqeBilanSerializer,
    DuplicationSerializer,
    ElementCreationSerializer,
    ElementModificationSerializer,
    InsertionNiveauSerializer,
    MesureSerializer,
    ModeleEnregistrementSerializer,
    MotifSerializer,
    NiveauCreationSerializer,
    NiveauModificationSerializer,
    PlanificationSerializer,
    ReferenceSerializer,
    SuspensionSerializer,
    TableauSerializer,
)
from apps.projets.services import arbre as gestes
from apps.projets.services import listes_modeles as lm
from apps.projets.services.perimetres import exiger, peut
from apps.projets.services.tableau_demarrage import (
    appliquer_tableau,
    proposer_tableau,
    verifier_tableau,
)

__all__ = [
    "ElementCloturerView",
    "ElementDeplacerView",
    "ElementDesactiverView",
    "ElementDetailView",
    "ElementDetaillerView",
    "ElementDupliquerView",
    "ElementHistoriqueView",
    "ElementMesureView",
    "ElementPlanifierView",
    "ElementReactiverView",
    "ElementRouvrirView",
    "ElementSuspendreView",
    "ListeDetailView",
    "ListeValeursView",
    "ListesView",
    "ModeleDetailView",
    "ModelePersonnaliserView",
    "ModelesView",
    "ProjetArbreView",
    "ProjetDecoupageExporterView",
    "ProjetDecoupageImporterView",
    "ProjetDecoupageView",
    "ProjetDqeAppliquerView",
    "ProjetDqeView",
    "ProjetElementsView",
    "ProjetNiveauDetailView",
    "ProjetNiveauxInsererView",
    "ProjetNiveauxView",
    "ProjetTableauVerifierView",
    "ValeurListeDetailView",
]

TAGS = ["découpage"]


def schema(**options):
    """`extend_schema` des vues du découpage : leurs réponses sont des représentations composées
    (arbre, case, verdict du tableau), décrites dans le résumé de chaque route."""
    options.setdefault("tags", TAGS)
    options.setdefault("responses", OpenApiTypes.OBJECT)
    return extend_schema(**options)


def _projet(request, view, pk, ecriture=False) -> Projet:
    projet = get_object_or_404(Projet, pk=pk)
    view.check_object_permissions(request, projet)
    if ecriture:
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(projet)
    return projet


def _element(request, pk, ecriture=False) -> Element:
    element = get_object_or_404(Element.objects.select_related("projet", "niveau", "parent"), pk=pk)
    arbre = charger_arbre(element.projet)
    if element.pk not in visibilite(arbre, request.user, request):
        raise NotFound("Cette case est introuvable.")
    if ecriture:
        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(element.projet)
    return element


def _case(request, element) -> dict:
    """La case telle que l'arbre la rend, après un geste."""
    from apps.core.droits import peut_voir_montants
    from apps.projets.selectors.arbre_api import equipes_par_case
    from apps.projets.services.sante_calculs import calculer_arbre

    arbre = charger_arbre(element.projet)
    element = arbre.par_id[element.pk]
    acces = visibilite(arbre, request.user, request)
    return representer_case(
        element,
        arbre,
        calculer_arbre(arbre),
        arbre.numerotation(),
        peut_voir_montants(request.user, request),
        equipes_par_case(arbre),
        acces.get(element.pk, "COMPLET"),
    )


# --------------------------------------------------------------------------
# Listes de valeurs
# --------------------------------------------------------------------------
class ListesView(APIView):
    """`GET`/`POST /api/v1/decoupage/listes/` — listes plateforme et entreprise, fusionnées."""

    def get_permissions(self):
        code = "projets.modeles_gerer" if self.request.method == "POST" else "projets.lire"
        return [IsAuthenticated(), APermission.pour(code)()]

    @schema(
        summary="Listes de valeurs (plateforme et entreprise)",
        operation_id="decoupage_listes_liste",
    )
    def get(self, request):
        avec = request.query_params.get("valeurs", "true").lower() != "false"
        return Response(lm.listes_disponibles(avec_valeurs=avec))

    @schema(summary="Créer une liste de l'entreprise", request=CreationListeSerializer)
    def post(self, request):
        donnees = CreationListeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        liste = lm.creer_liste(**donnees.validated_data)
        return Response(lm.liste_en_dict(liste), status=status.HTTP_201_CREATED)


def _liste_de_url(origine, pk):
    return lm.resoudre_liste({"origine": origine.upper(), "id": pk})


class ListeDetailView(APIView):
    """`GET /api/v1/decoupage/listes/{origine}/{id}/`."""

    permission_classes = [IsAuthenticated, APermission.pour("projets.lire")]

    @schema(summary="Une liste et ses valeurs")
    def get(self, request, origine, pk):
        return Response(lm.liste_en_dict(_liste_de_url(origine, pk)))


class ListeValeursView(APIView):
    """`POST /api/v1/decoupage/listes/{origine}/{id}/valeurs/` — ajout en masse, sans doublon.

    Une entreprise ajoute ses valeurs aux listes plateforme comme aux siennes ; elle ne retire
    pas une valeur de la plateforme.
    """

    permission_classes = [IsAuthenticated, APermission.pour("projets.modeles_gerer")]

    @schema(summary="Ajouter des valeurs à une liste", request=AjoutValeursSerializer)
    def post(self, request, origine, pk):
        donnees = AjoutValeursSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        resultat = lm.ajouter_valeurs(
            _liste_de_url(origine, pk),
            donnees.validated_data["valeurs"],
            donnees.validated_data["groupe"],
        )
        return Response(resultat, status=status.HTTP_201_CREATED)


class ValeurListeDetailView(APIView):
    """`DELETE /api/v1/decoupage/valeurs/{id}/` — retire une valeur ajoutée par l'entreprise."""

    permission_classes = [IsAuthenticated, APermission.pour("projets.modeles_gerer")]

    @schema(summary="Retirer une valeur ajoutée par l'entreprise", responses={204: None})
    def delete(self, request, pk):
        lm.retirer_valeur(pk, utilisateur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# Modèles de découpage
# --------------------------------------------------------------------------
class ModelesView(APIView):
    """`GET`/`POST /api/v1/decoupage/modeles/` — tous les modèles, ceux du type en tête."""

    def get_permissions(self):
        code = "projets.modeles_gerer" if self.request.method == "POST" else "projets.lire"
        return [IsAuthenticated(), APermission.pour(code)()]

    @schema(
        summary="Modèles de découpage",
        operation_id="decoupage_modeles_liste",
        parameters=[OpenApiParameter("type_projet", str, description="Met ses modèles en tête.")],
    )
    def get(self, request):
        return Response(lm.modeles_disponibles(request.query_params.get("type_projet") or None))

    @schema(summary="Enregistrer comme nouveau modèle", request=ModeleEnregistrementSerializer)
    def post(self, request):
        donnees = ModeleEnregistrementSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        modele = lm.enregistrer_modele(**donnees.validated_data)
        return Response(lm.modele_en_dict(modele), status=status.HTTP_201_CREATED)


def _modele_de_url(origine, pk):
    return lm.resoudre_modele({"origine": origine.upper(), "id": pk})


class ModeleDetailView(APIView):
    """`GET`/`PUT`/`DELETE /api/v1/decoupage/modeles/{origine}/{id}/`.

    Un modèle plateforme se lit et se personnalise ; seuls les modèles de l'entreprise se
    modifient ou se suppriment (et cela ne change aucun projet déjà créé, §3.11).
    """

    def get_permissions(self):
        code = "projets.lire" if self.request.method == "GET" else "projets.modeles_gerer"
        return [IsAuthenticated(), APermission.pour(code)()]

    def _modele_entreprise(self, origine, pk) -> ModeleDecoupageEntreprise:
        modele = _modele_de_url(origine, pk)
        if not isinstance(modele, ModeleDecoupageEntreprise):
            from apps.core.exceptions import ErreurMetier

            raise ErreurMetier(
                "Un modèle de la plateforme ne se modifie pas : personnalisez-le pour en faire "
                "une copie de l'entreprise."
            )
        return modele

    @schema(summary="Un modèle, avec son gabarit et ses lignes types")
    def get(self, request, origine, pk):
        return Response(
            lm.modele_en_dict(_modele_de_url(origine, pk), request.query_params.get("type_projet"))
        )

    @schema(summary="Mettre à jour ce modèle", request=ModeleEnregistrementSerializer)
    def put(self, request, origine, pk):
        modele = self._modele_entreprise(origine, pk)
        donnees = ModeleEnregistrementSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        modele = lm.enregistrer_modele(modele=modele, **donnees.validated_data)
        return Response(lm.modele_en_dict(modele))

    @schema(summary="Supprimer ce modèle de l'entreprise", responses={204: None})
    def delete(self, request, origine, pk):
        self._modele_entreprise(origine, pk).delete(utilisateur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ModelePersonnaliserView(APIView):
    """`POST /api/v1/decoupage/modeles/PLATEFORME/{id}/personnaliser/`."""

    permission_classes = [IsAuthenticated, APermission.pour("projets.modeles_gerer")]

    @schema(summary="Personnaliser un modèle de la plateforme", request=None)
    def post(self, request, pk):
        modele = get_object_or_404(ModeleDecoupagePlateforme, pk=pk, est_actif=True)
        copie = lm.personnaliser_modele(modele)
        return Response(lm.modele_en_dict(copie), status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------
# Tableau de démarrage et arbre d'un projet
# --------------------------------------------------------------------------
class ProjetDecoupageView(APIView):
    """`GET`/`POST /api/v1/projets/{id}/decoupage/`.

    - `GET` : le tableau pré-rempli — le modèle par défaut du type de projet, ou celui passé en
      paramètre (`modele_origine`, `modele_id`).
    - `POST` : applique le tableau. Projet sans découpage : crée le gabarit et l'arbre. Projet
      déjà découpé : ajout en masse de nouvelles branches, rapprochées par chemin.
    """

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(
        summary="Tableau de démarrage pré-rempli",
        parameters=[
            OpenApiParameter("modele_origine", str, enum=["PLATEFORME", "ENTREPRISE"]),
            OpenApiParameter("modele_id", str),
        ],
    )
    def get(self, request, pk):
        projet = _projet(request, self, pk)
        reference = None
        if request.query_params.get("modele_id"):
            ref = ReferenceSerializer(
                data={
                    "origine": request.query_params.get("modele_origine", "PLATEFORME"),
                    "id": request.query_params["modele_id"],
                }
            )
            ref.is_valid(raise_exception=True)
            reference = {**ref.validated_data, "id": str(ref.validated_data["id"])}
        return Response(proposer_tableau(projet, reference))

    @schema(summary="Appliquer le tableau de démarrage", request=TableauSerializer)
    def post(self, request, pk):
        projet = _projet(request, self, pk, ecriture=True)
        exiger(request.user, "projets.decouper", projet, request=request)
        donnees = TableauSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        resultat = appliquer_tableau(
            projet,
            niveaux=_niveaux_saisis(donnees.validated_data["niveaux"]),
            lignes=donnees.validated_data["lignes"],
            confirmer_avertissements=donnees.validated_data["confirmer_avertissements"],
            auteur=request.user,
        )
        return Response(
            {**resultat, "arbre": representer_arbre(projet, request.user, request)},
            status=status.HTTP_201_CREATED,
        )


def _niveaux_saisis(niveaux):
    return [
        {
            **n,
            "liste": {"origine": n["liste"]["origine"], "id": str(n["liste"]["id"])}
            if n.get("liste")
            else None,
        }
        for n in niveaux
    ]


class ProjetDecoupageImporterView(APIView):
    """`POST /api/v1/projets/{id}/decoupage/importer/` — un fichier Excel ou CSV devient un tableau.

    Rien n'est écrit : la réponse est le tableau (niveaux et lignes) et sa vérification ; on
    l'applique ensuite par `POST /projets/{id}/decoupage/`, à la création comme pour ajouter des
    branches à un arbre existant.
    """

    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(
        summary="Importer un fichier Excel ou CSV dans le tableau de démarrage",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"fichier": {"type": "string", "format": "binary"}},
                "required": ["fichier"],
            }
        },
    )
    def post(self, request, pk):
        from apps.projets.services.import_export import importer_tableau

        projet = _projet(request, self, pk)
        fichier = request.FILES.get("fichier")
        if fichier is None:
            raise ValidationError({"fichier": "Joignez un fichier .xlsx ou .csv."})
        return Response(importer_tableau(projet, fichier))


def _exiger_import_dqe(request, projet) -> None:
    """L'import DQE chiffre et ajoute des branches : il faut l'une des deux permissions quelque
    part sur le projet ; chaque ligne est ensuite vérifiée dans le périmètre de sa case."""
    from apps.projets.services.perimetres import perimetre_de

    perimetre = perimetre_de(request.user, projet, request)
    if not (
        perimetre.peut_quelque_part("projets.chiffrer")
        or perimetre.peut_quelque_part("projets.decouper")
    ):
        exiger(request.user, "projets.chiffrer", projet, request=request)


class ProjetDqeView(APIView):
    """`POST /api/v1/projets/{id}/decoupage/dqe/` — le bilan d'un import DQE, sans rien écrire.

    Un fichier (`multipart`, champ `fichier`) ou des lignes déjà lues (`JSON`, `lignes`). La
    réponse rend les lignes lues, à renvoyer telles quelles (ou filtrées) à `…/dqe/appliquer/`.
    """

    parser_classes = [MultiPartParser, JSONParser]
    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(
        summary="Bilan d'un import DQE (quantités et montants) sur un projet découpé",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"fichier": {"type": "string", "format": "binary"}},
                "required": ["fichier"],
            },
            "application/json": DqeBilanSerializer,
        },
    )
    def post(self, request, pk):
        from apps.core.droits import peut_voir_montants
        from apps.projets.services.import_dqe import bilan_dqe, sans_interne
        from apps.projets.services.import_export import lire_tableau

        projet = _projet(request, self, pk)
        _exiger_import_dqe(request, projet)
        avertissements_fichier = []
        if request.FILES.get("fichier") is not None:
            lu = lire_tableau(projet, request.FILES["fichier"])
            lignes, avertissements_fichier = lu["lignes"], lu["avertissements"]
        elif "lignes" in request.data:
            donnees = DqeBilanSerializer(data=request.data)
            donnees.is_valid(raise_exception=True)
            lignes = donnees.validated_data["lignes"]
        else:
            raise ValidationError({"fichier": "Joignez un fichier .xlsx ou .csv."})
        bilan = bilan_dqe(
            projet,
            lignes,
            utilisateur=request.user,
            request=request,
            montants_visibles=peut_voir_montants(request.user, request),
        )
        bilan["avertissements"] = [*bilan["avertissements"], *avertissements_fichier]
        return Response({"lignes": lignes, "bilan": sans_interne(bilan)})


class ProjetDqeAppliquerView(APIView):
    """`POST /api/v1/projets/{id}/decoupage/dqe/appliquer/` — applique ce que le bilan accepte.

    Le bilan est refait sur les lignes reçues ; chaque ligne s'applique seule, et une ligne
    refusée à ce moment est rendue avec sa raison sans empêcher les autres.
    """

    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(summary="Appliquer un import DQE", request=DqeApplicationSerializer)
    def post(self, request, pk):
        from apps.core.droits import peut_voir_montants
        from apps.projets.services.import_dqe import appliquer_dqe

        projet = _projet(request, self, pk, ecriture=True)
        _exiger_import_dqe(request, projet)
        donnees = DqeApplicationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        resultat = appliquer_dqe(
            projet,
            donnees.validated_data["lignes"],
            utilisateur=request.user,
            motif=donnees.validated_data["motif"],
            request=request,
            montants_visibles=peut_voir_montants(request.user, request),
        )
        return Response({**resultat, "arbre": representer_arbre(projet, request.user, request)})


class ProjetDecoupageExporterView(APIView):
    """`GET /api/v1/projets/{id}/decoupage/exporter/?type=xlsx|csv` — l'arbre au format du
    tableau, une ligne par tâche ; le fichier se réimporte tel quel."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(
        summary="Exporter l'arbre en Excel ou CSV",
        parameters=[OpenApiParameter("type", str, enum=["xlsx", "csv"])],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        from django.http import HttpResponse

        from apps.core.droits import peut_voir_montants
        from apps.projets.services.import_export import exporter_arbre

        projet = _projet(request, self, pk)
        format_fichier = "csv" if request.query_params.get("type") == "csv" else "xlsx"
        contenu, type_mime = exporter_arbre(
            projet, format_fichier, montants_visibles=peut_voir_montants(request.user, request)
        )
        reponse = HttpResponse(contenu, content_type=type_mime)
        nom = f"decoupage-{projet.reference or projet.pk}.{format_fichier}"
        reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
        return reponse


class ProjetTableauVerifierView(APIView):
    """`POST /api/v1/projets/{id}/decoupage/verifier/` — le récapitulatif, sans rien écrire."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(summary="Vérifier le tableau (C-1 à C-7)", request=TableauSerializer)
    def post(self, request, pk):
        _projet(request, self, pk)
        donnees = TableauSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        verdict = verifier_tableau(
            _niveaux_saisis(donnees.validated_data["niveaux"]), donnees.validated_data["lignes"]
        )
        verdict.pop("_lignes", None)
        verdict.pop("lignes_retenues", None)
        return Response(verdict)


class ProjetArbreView(APIView):
    """`GET /api/v1/projets/{id}/arbre/` — l'arbre, filtré par périmètre (`?a_plat=true`)."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(
        summary="Arbre du projet",
        parameters=[
            OpenApiParameter("a_plat", bool, description="Liste à plat au lieu d'imbriquée.")
        ],
    )
    def get(self, request, pk):
        projet = _projet(request, self, pk)
        a_plat = request.query_params.get("a_plat", "false").lower() == "true"
        return Response(representer_arbre(projet, request.user, request, a_plat=a_plat))


# --------------------------------------------------------------------------
# Niveaux du gabarit
# --------------------------------------------------------------------------
def _niveau_en_dict(niveau):
    return {
        "id": str(niveau.pk),
        "ordre": niveau.ordre,
        "libelle": niveau.libelle,
        "alerter": niveau.alerter,
        "liste": lm.reference_liste(niveau.liste_plateforme or niveau.liste_entreprise),
    }


def _reference_ou_none(donnees, cle="liste"):
    valeur = donnees.get(cle)
    if not valeur:
        return valeur
    return {"origine": valeur["origine"], "id": str(valeur["id"])}


class ProjetNiveauxView(APIView):
    """`GET`/`POST /api/v1/projets/{id}/niveaux/` — ajouter un niveau à la fin (A-3)."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(summary="Niveaux du gabarit du projet")
    def get(self, request, pk):
        projet = _projet(request, self, pk)
        return Response(
            [
                _niveau_en_dict(n)
                for n in NiveauProjet.objects.filter(projet=projet).order_by("ordre")
            ]
        )

    @schema(summary="Ajouter un niveau à la fin", request=NiveauCreationSerializer)
    def post(self, request, pk):
        projet = _projet(request, self, pk, ecriture=True)
        exiger(request.user, "projets.decouper", projet, request=request)
        donnees = NiveauCreationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        niveau = gestes.ajouter_niveau(
            projet,
            libelle=donnees.validated_data["libelle"],
            liste=_reference_ou_none(donnees.validated_data),
            alerter=donnees.validated_data["alerter"],
        )
        return Response(_niveau_en_dict(niveau), status=status.HTTP_201_CREATED)


class ProjetNiveauDetailView(APIView):
    """`PATCH /api/v1/projets/{id}/niveaux/{niveau_id}/` — renommer, changer de liste, alerter."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(summary="Modifier un niveau", request=NiveauModificationSerializer)
    def patch(self, request, pk, niveau_id):
        projet = _projet(request, self, pk, ecriture=True)
        exiger(request.user, "projets.decouper", projet, request=request)
        niveau = get_object_or_404(NiveauProjet, pk=niveau_id, projet=projet)
        donnees = NiveauModificationSerializer(data=request.data, partial=True)
        donnees.is_valid(raise_exception=True)
        valides = dict(donnees.validated_data)
        if "liste" in valides:
            valides["liste"] = _reference_ou_none(valides)
        return Response(_niveau_en_dict(gestes.modifier_niveau(niveau, donnees=valides)))


class ProjetNiveauxInsererView(APIView):
    """`POST /api/v1/projets/{id}/niveaux/inserer/` — insérer un niveau dans un projet rempli."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(summary="Insérer un niveau (§12.6)", request=InsertionNiveauSerializer)
    def post(self, request, pk):
        projet = _projet(request, self, pk, ecriture=True)
        exiger(request.user, "projets.decouper", projet, request=request)
        donnees = InsertionNiveauSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        resultat = gestes.inserer_niveau(
            projet,
            position=donnees.validated_data["position"],
            libelle=donnees.validated_data["libelle"],
            liste=_reference_ou_none(donnees.validated_data),
            libelle_intermediaire=donnees.validated_data["libelle_intermediaire"],
            auteur=request.user,
        )
        return Response(
            {
                "niveau": _niveau_en_dict(resultat["niveau"]),
                "cases_intermediaires": resultat["cases_intermediaires"],
                "arbre": representer_arbre(projet, request.user, request),
            },
            status=status.HTTP_201_CREATED,
        )


# --------------------------------------------------------------------------
# Cases de l'arbre
# --------------------------------------------------------------------------
CHAMPS_CHIFFRER = {"mode_mesure", "unite", "quantite_prevue", "montant", "enveloppe"}


class ProjetElementsView(APIView):
    """`POST /api/v1/projets/{id}/elements/` — ajouter une case (sous un parent, ou à la racine)."""

    permission_classes = [IsAuthenticated, GardePermissionProjet.pour("projets.lire")]

    @schema(summary="Ajouter une case", request=ElementCreationSerializer)
    def post(self, request, pk):
        projet = _projet(request, self, pk, ecriture=True)
        donnees = ElementCreationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        valides = dict(donnees.validated_data)
        parent = None
        if valides.pop("parent_id"):
            parent = get_object_or_404(
                Element, pk=donnees.validated_data["parent_id"], projet=projet
            )
        exiger(request.user, "projets.decouper", projet, parent, request=request)
        if CHAMPS_CHIFFRER & set(valides):
            exiger(request.user, "projets.chiffrer", projet, parent, request=request)
        if {"date_debut_prevue", "date_fin_prevue"} & set(valides):
            exiger(request.user, "projets.planifier", projet, parent, request=request)
        niveau = None
        if valides.get("niveau_id"):
            niveau = get_object_or_404(NiveauProjet, pk=valides["niveau_id"], projet=projet)
        valides.pop("niveau_id", None)
        dates = {
            k: valides.pop(k) for k in ("date_debut_prevue", "date_fin_prevue") if k in valides
        }
        element = gestes.ajouter_element(
            projet,
            parent=parent,
            niveau=niveau,
            auteur=request.user,
            motif=valides.pop("motif", ""),
            **valides,
        )
        if dates:
            from apps.projets.services.reprogrammation import planifier_element

            planifier_element(
                element,
                date_debut=dates.get("date_debut_prevue"),
                date_fin=dates.get("date_fin_prevue"),
                auteur=request.user,
            )
        return Response(_case(request, element), status=status.HTTP_201_CREATED)


class ElementDetailView(APIView):
    """`GET`/`PATCH`/`DELETE /api/v1/elements/{id}/`."""

    permission_classes = [IsAuthenticated]

    @schema(summary="Une case de l'arbre")
    def get(self, request, pk):
        return Response(_case(request, _element(request, pk)))

    @schema(
        summary="Renommer, chiffrer, métrer, régler l'exécution",
        request=ElementModificationSerializer,
    )
    def patch(self, request, pk):
        element = _element(request, pk, ecriture=True)
        donnees = ElementModificationSerializer(data=request.data, partial=True)
        donnees.is_valid(raise_exception=True)
        valides = dict(donnees.validated_data)
        motif = valides.pop("motif", "")
        if set(valides) - CHAMPS_CHIFFRER:
            exiger(request.user, "projets.decouper", element.projet, element, request=request)
        if CHAMPS_CHIFFRER & set(valides):
            exiger(request.user, "projets.chiffrer", element.projet, element, request=request)
        element = gestes.modifier_element(
            element, donnees=valides, auteur=request.user, motif=motif
        )
        return Response(_case(request, element))

    @schema(summary="Supprimer une case sans mesure (et sa branche)", responses={204: None})
    def delete(self, request, pk):
        element = _element(request, pk, ecriture=True)
        exiger(request.user, "projets.decouper", element.projet, element, request=request)
        gestes.supprimer_element(element, auteur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ElementPlanifierView(APIView):
    """`POST /api/v1/elements/{id}/planifier/` — première saisie des dates (§11).

    Une case déjà datée se reprogramme (`POST /api/v1/elements/{id}/reprogrammer/`, motif et
    justification obligatoires). Des dates qui débordent du parent répondent
    `prolongation_requise` avec la liste des cases à prolonger ; on confirme par `prolonger`.
    """

    permission_classes = [IsAuthenticated]

    @schema(summary="Planifier les dates d'une case", request=PlanificationSerializer)
    def post(self, request, pk):
        from apps.core.exceptions import ErreurMetier
        from apps.projets.services.reprogrammation import planifier_element

        element = _element(request, pk, ecriture=True)
        exiger(request.user, "projets.planifier", element.projet, element, request=request)
        donnees = PlanificationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        if element.date_debut_prevue and element.date_fin_prevue:
            raise ErreurMetier(
                "Les dates de cette case sont déjà fixées : reprogrammez-les, avec un motif."
            )
        v = donnees.validated_data
        resultat = planifier_element(
            element,
            date_debut=v["date_debut_prevue"],
            date_fin=v["date_fin_prevue"],
            prolonger=v["prolonger"],
            autorise_a_prolonger=peut(
                request.user, "projets.prolonger", element.projet, element, request
            ),
            motif_id=v.get("motif_id"),
            justification=v["justification"],
            auteur=request.user,
        )
        return Response(
            {"case": _case(request, element), "prolongations": resultat["prolongations"]}
        )


class ElementDeplacerView(APIView):
    """`POST /api/v1/elements/{id}/deplacer/` — aperçu des effets (`apercu`), puis confirmation."""

    permission_classes = [IsAuthenticated]

    @schema(summary="Déplacer une case (§12.4)", request=DeplacementSerializer)
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        donnees = DeplacementSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        v = donnees.validated_data
        destination = None
        if v["nouveau_parent_id"]:
            destination = get_object_or_404(
                Element, pk=v["nouveau_parent_id"], projet=element.projet
            )
        exiger(request.user, "projets.decouper", element.projet, element, request=request)
        exiger(request.user, "projets.decouper", element.projet, destination, request=request)
        if v["apercu"]:
            return Response(gestes.apercu_deplacement(element, destination))
        element = gestes.deplacer_element(
            element,
            destination,
            auteur=request.user,
            motif=v["motif"],
            prolonger=v["prolonger"],
            autorise_a_prolonger=peut(
                request.user, "projets.prolonger", element.projet, element, request
            ),
            justification=v["justification"],
            motif_report_id=v.get("motif_id"),
        )
        return Response(_case(request, element))


class ElementDupliquerView(APIView):
    """`POST /api/v1/elements/{id}/dupliquer/` — copier une branche (§13quinquies.1)."""

    permission_classes = [IsAuthenticated]

    @schema(summary="Dupliquer une case et sa branche", request=DuplicationSerializer)
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        donnees = DuplicationSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        v = donnees.validated_data
        if "parent_id" in v:
            destination = (
                get_object_or_404(Element, pk=v["parent_id"], projet=element.projet)
                if v["parent_id"]
                else None
            )
        else:
            destination = element.parent
        exiger(request.user, "projets.decouper", element.projet, element, request=request)
        exiger(request.user, "projets.decouper", element.projet, destination, request=request)
        copie, nombre = gestes.dupliquer_branche(
            element,
            destination=destination,
            libelle=v["libelle"],
            auteur=request.user,
            motif=v["motif"],
        )
        return Response(
            {"case": _case(request, copie), "cases_copiees": nombre},
            status=status.HTTP_201_CREATED,
        )


class ElementHistoriqueView(APIView):
    """`GET /api/v1/elements/{id}/historique/` — les modifications d'une case, paginées.

    Lues dans le journal d'audit : qui, quand, quel geste, le motif, avant et après.
    """

    permission_classes = [IsAuthenticated]

    @schema(
        summary="Historique des modifications d'une case",
        parameters=[
            OpenApiParameter("page", int),
            OpenApiParameter("taille_page", int, description="20 par défaut, 100 au plus."),
        ],
    )
    def get(self, request, pk):
        from apps.core.droits import peut_voir_montants
        from apps.projets.selectors.historique import entrees_de_case, representer_entrees

        element = _element(request, pk)
        if element.pk not in _cases_completes(request, element):
            raise PermissionDenied(
                "Vous ne voyez que l'intitulé de cette case : son historique est hors de votre "
                "périmètre."
            )
        pagination = PaginationStandard()
        page = pagination.paginate_queryset(entrees_de_case(element), request, view=self)
        return pagination.get_paginated_response(
            representer_entrees(page, montants_visibles=peut_voir_montants(request.user, request))
        )


def _cases_completes(request, element) -> set:
    """Les cases que la personne voit en entier (pas seulement par le chemin qui y mène)."""
    from apps.projets.selectors.arbre_api import COMPLET

    acces = visibilite(charger_arbre(element.projet), request.user, request)
    return {pk for pk, niveau in acces.items() if niveau == COMPLET}


class ElementDetaillerView(APIView):
    """`POST /api/v1/elements/{id}/detailler/` — une feuille devient un parent (§12.5)."""

    permission_classes = [IsAuthenticated]

    @schema(summary="Détailler une feuille", request=DetailSerializer)
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        exiger(request.user, "projets.decouper", element.projet, element, request=request)
        donnees = DetailSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        niveau = None
        if donnees.validated_data["niveau_id"]:
            niveau = get_object_or_404(
                NiveauProjet, pk=donnees.validated_data["niveau_id"], projet=element.projet
            )
        enfants = gestes.detailler_feuille(
            element,
            enfants=[dict(e) for e in donnees.validated_data["enfants"]],
            niveau=niveau,
            auteur=request.user,
            motif=donnees.validated_data["motif"],
        )
        return Response(
            {"case": _case(request, element), "enfants": [str(e.pk) for e in enfants]},
            status=status.HTTP_201_CREATED,
        )


class ElementDesactiverView(APIView):
    """`POST /api/v1/elements/{id}/desactiver/` — sort des calculs, garde son historique."""

    permission_classes = [IsAuthenticated]

    @schema(summary="Désactiver une case", request=MotifSerializer)
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        exiger(request.user, "projets.decouper", element.projet, element, request=request)
        donnees = MotifSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        element = gestes.desactiver_element(
            element, auteur=request.user, motif=donnees.validated_data["motif"]
        )
        return Response(_case(request, element))


class ElementReactiverView(APIView):
    permission_classes = [IsAuthenticated]

    @schema(summary="Réactiver une case", request=None)
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        exiger(request.user, "projets.decouper", element.projet, element, request=request)
        return Response(_case(request, gestes.reactiver_element(element, auteur=request.user)))


class ElementSuspendreView(APIView):
    """`POST /api/v1/elements/{id}/suspension/` — suspendre ou reprendre toute la branche."""

    permission_classes = [IsAuthenticated]

    @schema(summary="Suspendre ou reprendre une case", request=SuspensionSerializer)
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        exiger(request.user, "projets.planifier", element.projet, element, request=request)
        donnees = SuspensionSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        element = gestes.suspendre_element(
            element,
            suspendu=donnees.validated_data["suspendu"],
            auteur=request.user,
            motif=donnees.validated_data["motif"],
        )
        return Response(_case(request, element))


class ElementMesureView(APIView):
    """`POST /api/v1/elements/{id}/mesure/` — mise à jour tracée hors du journal."""

    permission_classes = [IsAuthenticated]

    @schema(summary="Mesurer une feuille hors du journal", request=MesureSerializer)
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        exiger(request.user, "projets.mesurer", element.projet, element, request=request)
        donnees = MesureSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        element = gestes.mesurer_feuille(element, auteur=request.user, **donnees.validated_data)
        return Response(_case(request, element))


class ElementCloturerView(APIView):
    permission_classes = [IsAuthenticated]

    @schema(summary="Clôturer une feuille (100 %)", request=None)
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        exiger(request.user, "projets.mesurer", element.projet, element, request=request)
        return Response(_case(request, gestes.cloturer_feuille(element, auteur=request.user)))


class ElementRouvrirView(APIView):
    permission_classes = [IsAuthenticated]

    @schema(summary="Rouvrir une feuille clôturée", request=MotifSerializer)
    def post(self, request, pk):
        element = _element(request, pk, ecriture=True)
        exiger(request.user, "projets.mesurer", element.projet, element, request=request)
        donnees = MotifSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        element = gestes.rouvrir_feuille(
            element, auteur=request.user, motif=donnees.validated_data["motif"]
        )
        return Response(_case(request, element))
