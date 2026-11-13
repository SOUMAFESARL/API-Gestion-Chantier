from django.urls import path

from .views import DepotDemandeInscriptionView, CompleterInscriptionView

urlpatterns = [
    path('v1/inscription/configurer/', CompleterInscriptionView.as_view(), name='configurer-inscription'),
    path('v1/inscription/', DepotDemandeInscriptionView.as_view(), name='depot-demande-inscription'),
]
