"""API du journal complet, sous /api/v1/chantier/."""

from copy import deepcopy
from datetime import timedelta

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chantier.models import AlerteJournal
from apps.chantier.permissions import (
    PeutConsulterRapports,
    PeutRedigerRapports,
    PeutValiderRapports,
)
from apps.chantier.selectors.journal import (
    document,
    existant,
    filtre_journaux,
    journal_periode,
    journaux_visibles,
    pour_auteur,
    preparation,
    projets_visibles,
    reference,
)
from apps.chantier.serializers.journal import (
    AlerteJournalSerializer,
    FiltresJournalSerializer,
    RejetJournalSerializer,
    SaisieJournalSerializer,
    SignatureJournalSerializer,
)
from apps.chantier.services.journal import (
    alerter_journal,
    aujourdhui,
    creer_journal,
    modifier_journal,
    rejeter_journal,
    signer_journal,
    soumettre_journal,
    statut_journal,
    supprimer_brouillon,
)
from apps.core.exceptions import ErreurConflit


def filtres(request):
    serializer = FiltresJournalSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def charger_journal(request, pk):
    return get_object_or_404(pour_auteur(journaux_visibles(request), request.user), rapport_id=pk)


def charge_autorisee(request, charge):
    """Masque les tarifs dans le document, la saisie et les reprises (E-11)."""
    from apps.core.droits import peut_voir_montants

    if peut_voir_montants(request.user, request):
        return charge
    charge = deepcopy(charge)

    def masquer(valeur):
        if isinstance(valeur, dict):
            for cle, contenu in valeur.items():
                if cle == "prix_unitaire":
                    valeur[cle] = None
                else:
                    masquer(contenu)
        elif isinstance(valeur, list):
            for contenu in valeur:
                masquer(contenu)

    masquer(charge)
    return charge


class JournalRapportsView(APIView):
    def get_permissions(self):
        return [
            IsAuthenticated(),
            PeutRedigerRapports() if self.request.method == "POST" else PeutConsulterRapports(),
        ]

    @extend_schema(
        tags=["Journal de chantier"],
        parameters=[FiltresJournalSerializer],
        responses=OpenApiTypes.OBJECT,
        summary="Lister les rapports du journal",
        operation_id="journal_rapports_liste",
    )
    def get(self, request):
        qs = filtre_journaux(
            pour_auteur(journaux_visibles(request), request.user), filtres(request), request.user
        )
        qs = qs.defer("saisie", "photographie").prefetch_related(None)
        return Response(
            {
                "aujourdhui": aujourdhui().isoformat(),
                "resultats": [
                    {
                        "id": str(j.rapport_id),
                        "date": j.rapport.date_rapport.isoformat(),
                        "statut": statut_journal(j),
                        "enregistre_le": j.modifie_le.isoformat(),
                    }
                    for j in qs
                ],
            }
        )

    @extend_schema(
        tags=["Journal de chantier"],
        request=SaisieJournalSerializer,
        responses={201: OpenApiTypes.OBJECT},
        summary="Créer le brouillon complet d'un chantier",
    )
    def post(self, request):
        # Valider UUID et date avant toute requête ORM pour éviter une erreur 500.
        serializer = SaisieJournalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        projet = get_object_or_404(
            projets_visibles(request), pk=serializer.validated_data["projet_id"]
        )
        self.check_object_permissions(request, projet)
        journal = creer_journal(
            projet=projet,
            utilisateur=request.user,
            jour=serializer.validated_data["date"],
            data=request.data,
        )
        return Response(
            charge_autorisee(request, existant(journal)), status=status.HTTP_201_CREATED
        )


class JournalPreparationView(APIView):
    permission_classes = [IsAuthenticated, PeutConsulterRapports]

    @extend_schema(
        tags=["Journal de chantier"],
        parameters=[FiltresJournalSerializer],
        responses=OpenApiTypes.OBJECT,
        summary="Préparer la saisie : lots, activités, reprises et brouillon",
    )
    def get(self, request):
        params = filtres(request)
        if "projet" not in params or "date" not in params:
            raise ValidationError("projet et date sont requis.")
        projet = get_object_or_404(projets_visibles(request), pk=params["projet"])
        self.check_object_permissions(request, projet)
        qs = journaux_visibles(request).filter(rapport__projet=projet)
        journal = qs.filter(rapport__date_rapport=params["date"]).first()
        if (
            journal
            and journal.rapport.statut == "BROUILLON"
            and journal.rapport.auteur_id != request.user.id
        ):
            raise ErreurConflit(
                "Un autre auteur a déjà commencé le rapport de ce chantier pour ce jour."
            )
        precedent = (
            pour_auteur(qs, request.user)
            .filter(rapport__date_rapport__lt=params["date"])
            .order_by("-rapport__date_rapport")
            .first()
        )
        return Response(
            charge_autorisee(
                request, preparation(projet, params["date"], journal=journal, precedent=precedent)
            )
        )


class JournalRapportDetailView(APIView):
    def get_permissions(self):
        return [
            IsAuthenticated(),
            PeutConsulterRapports()
            if self.request.method in ("GET", "HEAD", "OPTIONS")
            else PeutRedigerRapports(),
        ]

    @extend_schema(
        tags=["Journal de chantier"],
        responses=OpenApiTypes.OBJECT,
        summary="Lire toutes les rubriques du rapport",
        operation_id="journal_rapport_detail",
    )
    def get(self, request, pk):
        journal = charger_journal(request, pk)
        self.check_object_permissions(request, journal.rapport)
        return Response(charge_autorisee(request, document(journal)))

    @extend_schema(
        tags=["Journal de chantier"],
        request=SaisieJournalSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Modifier partiellement un brouillon ou un rapport rejeté",
    )
    def patch(self, request, pk):
        journal = charger_journal(request, pk)
        self.check_object_permissions(request, journal.rapport)
        journal = modifier_journal(journal=journal, utilisateur=request.user, data=request.data)
        return Response(charge_autorisee(request, existant(journal)))

    @extend_schema(
        tags=["Journal de chantier"],
        responses={204: None},
        summary="Supprimer logiquement un brouillon de l'auteur",
    )
    def delete(self, request, pk):
        journal = charger_journal(request, pk)
        self.check_object_permissions(request, journal.rapport)
        supprimer_brouillon(journal=journal, utilisateur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class JournalDraftView(APIView):
    permission_classes = [IsAuthenticated, PeutRedigerRapports]

    @extend_schema(
        tags=["Journal de chantier"],
        request=SaisieJournalSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Autosauvegarder le brouillon (PATCH)",
    )
    def patch(self, request, pk):
        journal = charger_journal(request, pk)
        self.check_object_permissions(request, journal.rapport)
        journal = modifier_journal(journal=journal, utilisateur=request.user, data=request.data)
        return Response(charge_autorisee(request, existant(journal)))


class JournalSoumettreView(APIView):
    permission_classes = [IsAuthenticated, PeutRedigerRapports]

    @extend_schema(
        tags=["Journal de chantier"],
        request=SaisieJournalSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Enregistrer et soumettre atomiquement le rapport",
    )
    def post(self, request, pk):
        journal = charger_journal(request, pk)
        self.check_object_permissions(request, journal.rapport)
        journal = soumettre_journal(journal=journal, utilisateur=request.user, data=request.data)
        return Response({"id": str(journal.rapport_id), "reference": reference(journal)})


class JournalValiderView(APIView):
    permission_classes = [IsAuthenticated, PeutValiderRapports]
    etape = "CT"

    @extend_schema(
        tags=["Journal de chantier"],
        request=SignatureJournalSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Signer le rapport au niveau CT",
    )
    def post(self, request, pk):
        journal = charger_journal(request, pk)
        self.check_object_permissions(request, journal.rapport)
        serializer = SignatureJournalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        journal = signer_journal(
            journal=journal,
            utilisateur=request.user,
            etape=self.etape,
            commentaire=serializer.validated_data["commentaire"],
        )
        return Response(charge_autorisee(request, document(journal)))


class JournalApprouverView(JournalValiderView):
    etape = "CP"
    # Le gabarit CP dispose de chantier.rediger (niveau 2), pas de
    # chantier.valider (niveau CT). Le service exige en plus le vrai CP du
    # projet et une signature CT existante ; le droit de rédaction seul
    # n'autorise donc jamais l'approbation.
    permission_classes = [IsAuthenticated, PeutRedigerRapports]

    @extend_schema(
        tags=["Journal de chantier"],
        request=SignatureJournalSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Approuver le rapport au niveau CP après signature CT",
    )
    def post(self, request, pk):
        return super().post(request, pk)


class JournalRejeterView(APIView):
    permission_classes = [IsAuthenticated, PeutValiderRapports | PeutRedigerRapports]

    @extend_schema(
        tags=["Journal de chantier"],
        request=RejetJournalSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Rejeter au niveau attendu du circuit avec motif",
    )
    def post(self, request, pk):
        journal = charger_journal(request, pk)
        self.check_object_permissions(request, journal.rapport)
        serializer = RejetJournalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        journal = rejeter_journal(
            journal=journal, utilisateur=request.user, motif=serializer.validated_data["motif"]
        )
        return Response(charge_autorisee(request, document(journal)))


class JournalAlertesView(APIView):
    permission_classes = [IsAuthenticated, PeutRedigerRapports]

    @extend_schema(
        tags=["Journal de chantier"],
        request=AlerteJournalSerializer,
        responses=OpenApiTypes.OBJECT,
        summary="Enregistrer une alerte interne dédupliquée pour CT et CP",
    )
    def post(self, request, pk):
        journal = charger_journal(request, pk)
        self.check_object_permissions(request, journal.rapport)
        serializer = AlerteJournalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alerte = alerter_journal(
            journal=journal, utilisateur=request.user, data=serializer.validated_data
        )
        return Response({"envoyee_le": alerte.cree_le.isoformat(), "canal": "INTERNE"})


class JournalNotificationsView(APIView):
    permission_classes = [IsAuthenticated, PeutConsulterRapports]

    @extend_schema(
        tags=["Journal de chantier"],
        responses=OpenApiTypes.OBJECT,
        summary="Lire les alertes internes adressées à l'utilisateur",
    )
    def get(self, request):
        from apps.core.pagination import PaginationStandard

        qs = (
            AlerteJournal.objects.filter(
                destinataires=request.user,
                journal_id__in=journaux_visibles(request).values("id"),
            )
            .select_related("journal")
            .order_by("-cree_le")
        )
        pagination = PaginationStandard()
        page = pagination.paginate_queryset(qs, request, view=self)
        return pagination.get_paginated_response(
            [
                {
                    "id": str(alerte.id),
                    "rapport_id": str(alerte.journal.rapport_id),
                    "cle": alerte.cle,
                    "type": alerte.type,
                    "description": alerte.description,
                    "envoyee_le": alerte.cree_le.isoformat(),
                }
                for alerte in page
            ]
        )


class JournalView(APIView):
    permission_classes = [IsAuthenticated, PeutConsulterRapports]

    @extend_schema(
        tags=["Journal de chantier"],
        parameters=[FiltresJournalSerializer],
        responses=OpenApiTypes.OBJECT,
        summary="Lire le journal, historique et rapports manquants",
    )
    def get(self, request):
        params = filtres(request)
        debut = params.get("date_debut", aujourdhui() - timedelta(days=62))
        fin = params.get("date_fin", aujourdhui())
        if (fin - debut).days > 366 or fin < debut:
            raise ValidationError("La période doit durer au plus 366 jours, avec fin >= début.")
        if params.get("projet"):
            projet = get_object_or_404(projets_visibles(request), pk=params["projet"])
            self.check_object_permissions(request, projet)
        from django.utils import timezone

        return Response(
            {
                "aujourdhui": aujourdhui().isoformat(),
                "lu_le": timezone.now().isoformat(),
                "resultats": journal_periode(request, debut, fin, projet_id=params.get("projet")),
            }
        )
