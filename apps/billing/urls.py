from django.urls import path

from apps.billing.views import AbonnementView

app_name = "billing"

urlpatterns = [
    path("abonnement/", AbonnementView.as_view(), name="abonnement"),
]
