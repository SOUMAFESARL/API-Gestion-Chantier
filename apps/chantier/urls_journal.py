"""Les anciennes URL /rapports/ restent disponibles sans changement de contrat."""

from django.urls import path

from apps.chantier.views.journal import (
    JournalAlertesView,
    JournalApprouverView,
    JournalDraftView,
    JournalNotificationsView,
    JournalPreparationView,
    JournalRapportDetailView,
    JournalRapportsView,
    JournalRejeterView,
    JournalSoumettreView,
    JournalValiderView,
    JournalView,
)

app_name = "journal_chantier"
urlpatterns = [
    path("alertes/", JournalNotificationsView.as_view(), name="notifications"),
    path("journal/", JournalView.as_view(), name="journal"),
    path("rapports/", JournalRapportsView.as_view(), name="rapports"),
    path("rapports/preparation/", JournalPreparationView.as_view(), name="preparation"),
    path("rapports/<uuid:pk>/", JournalRapportDetailView.as_view(), name="detail"),
    path("rapports/<uuid:pk>/draft/", JournalDraftView.as_view(), name="draft"),
    path("rapports/<uuid:pk>/soumettre/", JournalSoumettreView.as_view(), name="soumettre"),
    path("rapports/<uuid:pk>/valider/", JournalValiderView.as_view(), name="valider"),
    path("rapports/<uuid:pk>/approuver/", JournalApprouverView.as_view(), name="approuver"),
    path("rapports/<uuid:pk>/rejeter/", JournalRejeterView.as_view(), name="rejeter"),
    path("rapports/<uuid:pk>/alertes/", JournalAlertesView.as_view(), name="alertes"),
]
