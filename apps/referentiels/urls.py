from django.urls import path

from apps.referentiels.views import EnumerationsView, ReglesMotDePasseView

app_name = "referentiels"

urlpatterns = [
    path("referentiels/enumerations/", EnumerationsView.as_view(), name="enumerations"),
    # Les règles de complexité, servies une fois — contrat §6.3. Le client
    # allume ses coches à partir de cette liste ; le serveur reste juge.
    path(
        "referentiels/regles-mot-de-passe/",
        ReglesMotDePasseView.as_view(),
        name="regles-mot-de-passe",
    ),
]
