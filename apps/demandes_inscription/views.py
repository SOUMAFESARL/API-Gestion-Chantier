import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from apps.config_smtp.services import send_mail
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import APIException

from .models import DemandeInscription
from .services import activer_demande
from .serializers import DemandeInscriptionSerializer, DepotDemandeInscriptionSerializer, CompleterInscriptionSerializer


class DemandeInscriptionViewSet(ModelViewSet):
    queryset = DemandeInscription.objects.select_related('entreprise').order_by('-cree_le', 'id')
    serializer_class = DemandeInscriptionSerializer
    permission_classes = [IsAdminUser]


@extend_schema(
    tags=['Inscription'],
    summary="Demander l'inscription d'une entreprise",
    description="Accessible sans authentification. Fournir uniquement raison_sociale, pays et email. Un email contient le lien de complétion à usage unique (expiration par défaut : 48 heures). Le slug et le jeton sont générés par le serveur. Aucun compte ni entreprise n'est créé à cette étape.",
    request=DepotDemandeInscriptionSerializer,
    responses={
        201: DepotDemandeInscriptionSerializer,
        400: OpenApiResponse(description='Données invalides ou email déjà réservé/utilisé.'),
        500: OpenApiResponse(description="Échec de l'envoi du mail : la demande est annulée."),
    },
    examples=[OpenApiExample('Demande initiale', value={
        'raison_sociale': 'BTP Exemple', 'pays': 'CI', 'email': 'contact@example.com',
    }, request_only=True)],
)
class DepotDemandeInscriptionView(CreateAPIView):
    serializer_class = DepotDemandeInscriptionSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                token = secrets.token_urlsafe(32)
                demande = serializer.save(
                    empreinte=hashlib.sha256(token.encode()).hexdigest(),
                    expire_le=timezone.now() + timedelta(hours=settings.DEMANDE_INSCRIPTION_EXPIRATION_HEURES),
                )
                base_url = settings.INSCRIPTION_COMPLETION_URL or self.request.build_absolute_uri(reverse('configurer-inscription'))
                url = base_url + ('&' if '?' in base_url else '?') + urlencode({'token': token})
                context = {
                    'raison_sociale': demande.raison_sociale,
                    'activation_url': url,
                    'expiration_heures': settings.DEMANDE_INSCRIPTION_EXPIRATION_HEURES,
                }
                try:
                    send_mail(
                        'Activez votre espace — CCD Digital',
                        render_to_string('demandes_inscription/emails/activation.txt', context),
                        settings.DEFAULT_FROM_EMAIL, [demande.email], fail_silently=False,
                        html_message=render_to_string('demandes_inscription/emails/activation.html', context),
                    )
                except Exception as exc:
                    raise APIException("L'envoi du mail a échoué. Veuillez réessayer.") from exc
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.__cause__, 'diag', None), 'constraint_name', None)
            if constraint in {'uq_demande_slug', 'uq_demande_email_attente'}:
                raise serializers.ValidationError('Une demande en cours réserve déjà cet email ou cet identifiant.') from exc
            raise


@extend_schema(tags=['Inscription'])
class CompleterInscriptionView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_demande(self, token, lock=False):
        if not isinstance(token, str) or not token or len(token) > 128:
            raise serializers.ValidationError({'token': 'Lien invalide ou expiré.'})
        queryset = DemandeInscription.objects.all()
        if lock:
            queryset = queryset.select_for_update()
        demande = queryset.filter(empreinte=hashlib.sha256(token.encode()).hexdigest()).first()
        if not demande or demande.statut != 'EN_ATTENTE' or demande.utilise_le or demande.supprime_le or demande.expire_le <= timezone.now():
            raise serializers.ValidationError({'token': 'Lien invalide ou expiré.'})
        return demande

    @extend_schema(
        summary="Vérifier le lien de complétion",
        description="Vérifie le jeton reçu par email et renvoie la demande. Cette consultation ne consomme pas le jeton.",
        parameters=[OpenApiParameter(name='token', type=str, location=OpenApiParameter.QUERY, required=True, description='Jeton sécurisé reçu par email.')],
        responses={200: DepotDemandeInscriptionSerializer, 400: OpenApiResponse(description='Lien invalide, expiré ou déjà utilisé.')},
    )
    def get(self, request):
        demande = self.get_demande(request.query_params.get('token'))
        return Response(DepotDemandeInscriptionSerializer(demande).data)

    @extend_schema(
        summary="Compléter l'inscription",
        description="Fournir le jeton reçu par email, les informations personnelles et accepter les CGU. Le mot de passe est haché. Le jeton est consommé et la demande devient ACTIVEE et une entreprise en statut ESSAI est cr??e. Aucun mot de passe ni jeton n'est renvoyé.",
        request=CompleterInscriptionSerializer,
        responses={200: DepotDemandeInscriptionSerializer, 400: OpenApiResponse(description='Données invalides, CGU non acceptées, mot de passe trop faible ou lien invalide/expiré/utilisé.')},
        examples=[OpenApiExample('Complétion', value={
            'token': 'jeton-recu-par-email', 'nom': 'Kone', 'prenom': 'Awa',
            'password': 'Chantier!9Secret246', 'cgu_version': '1.0', 'cgu_acceptees': True,
        }, request_only=True)],
    )
    def post(self, request):
        with transaction.atomic():
            demande = self.get_demande(request.data.get('token'), lock=True)
            serializer = CompleterInscriptionSerializer(data=request.data, context={'demande': demande})
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            for field in ['nom', 'prenom', 'password', 'cgu_version']:
                setattr(demande, field, data[field])
            demande.cgu_acceptees_le = timezone.now()
            demande.cgu_adresse_ip = request.META.get('REMOTE_ADDR') or None
            demande.utilise_le = timezone.now()
            activer_demande(demande)
        return Response(DepotDemandeInscriptionSerializer(demande).data)
