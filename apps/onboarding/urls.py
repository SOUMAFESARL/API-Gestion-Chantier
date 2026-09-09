"""Routes de la configuration initiale — schéma tenant uniquement.

Le code d'étape voyage en `<str:code>` et **n'est pas validé par l'URL** : un
code inconnu doit répondre `400 validation` avec le catalogue en `details`, pas
un `404` muet qui laisse le client deviner s'il s'est trompé de code ou de
route.
"""

from django.urls import path

from apps.onboarding.views import (
    ConfigurationView,
    FranchirEtapeView,
    PasserEtapeView,
    RecapitulatifView,
    TerminerView,
)

app_name = "onboarding"

urlpatterns = [
    path("configuration/", ConfigurationView.as_view(), name="configuration"),
    path(
        "configuration/etapes/<str:code>/valider/",
        FranchirEtapeView.as_view(),
        name="configuration-etape-valider",
    ),
    path(
        "configuration/etapes/<str:code>/passer/",
        PasserEtapeView.as_view(),
        name="configuration-etape-passer",
    ),
    path(
        "configuration/recapitulatif/",
        RecapitulatifView.as_view(),
        name="configuration-recapitulatif",
    ),
    path("configuration/terminer/", TerminerView.as_view(), name="configuration-terminer"),
]
