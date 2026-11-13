from rest_framework.permissions import IsAdminUser
from rest_framework.viewsets import ModelViewSet

from .models import Entreprise
from .serializers import EntrepriseSerializer


class EntrepriseViewSet(ModelViewSet):
    queryset = Entreprise.objects.order_by('raison_sociale', 'id')
    serializer_class = EntrepriseSerializer
    permission_classes = [IsAdminUser]
