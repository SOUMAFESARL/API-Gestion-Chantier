"""Messagerie de la plateforme : réglage du serveur SMTP et diagnostic d'envoi (superviseur)."""

from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform_admin.models.messagerie import ParametresMessagerie
from apps.platform_admin.permissions import EstSuperAdminPlateforme
from apps.platform_admin.services import messagerie as service
from apps.platform_admin.views.parametres import _exiger_superviseur, _journaliser


class EcritureMessagerieSerializer(serializers.Serializer):
    hote = serializers.CharField(max_length=255)
    port = serializers.IntegerField(min_value=1, max_value=65535)
    chiffrement = serializers.ChoiceField(choices=ParametresMessagerie.Chiffrement.choices)
    identifiant = serializers.CharField(max_length=254)
    # Vide ou absent : on garde le mot de passe déjà enregistré. Il n'est jamais renvoyé.
    mot_de_passe = serializers.CharField(max_length=256, required=False, allow_blank=True, write_only=True)
    expediteur = serializers.CharField(max_length=254, required=False, allow_blank=True)

    def validate_hote(self, valeur: str) -> str:
        valeur = valeur.strip()
        if "://" in valeur or "/" in valeur or " " in valeur:
            raise serializers.ValidationError("Saisissez seulement le nom du serveur, par exemple smtp.gmail.com.")
        return valeur


class TestMessagerieSerializer(serializers.Serializer):
    destinataire = serializers.EmailField()


def _lire() -> ParametresMessagerie | None:
    with schema_context(get_public_schema_name()):
        return ParametresMessagerie.objects.filter(pk=1).first()


class AdminMessagerieView(APIView):
    """`GET/PUT/DELETE /api/v1/admins/parametres/messagerie/`."""

    permission_classes = [EstSuperAdminPlateforme]

    @extend_schema(summary="Réglage de la messagerie de la plateforme", responses={200: dict})
    def get(self, request):
        return Response(service.serialiser(_lire()))

    @extend_schema(summary="Enregistrer le serveur SMTP", request=EcritureMessagerieSerializer, responses={200: dict})
    def put(self, request):
        _exiger_superviseur(request)
        serializer = EcritureMessagerieSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data

        with transaction.atomic(), schema_context(get_public_schema_name()):
            parametres = ParametresMessagerie.objects.filter(pk=1).first() or ParametresMessagerie(pk=1)
            nouveau_mot_de_passe = (donnees.get("mot_de_passe") or "").strip()
            if not nouveau_mot_de_passe and not parametres.mot_de_passe_chiffre:
                raise serializers.ValidationError(
                    {"mot_de_passe": "Le mot de passe d'application est requis la première fois."}
                )
            parametres.hote = donnees["hote"]
            parametres.port = donnees["port"]
            parametres.chiffrement = donnees["chiffrement"]
            parametres.identifiant = donnees["identifiant"].strip()
            parametres.expediteur = (donnees.get("expediteur") or "").strip()
            if nouveau_mot_de_passe:
                parametres.mot_de_passe_chiffre = service.chiffrer(nouveau_mot_de_passe)
            parametres.save()

        # Aucun secret dans le journal : seulement ce qui permet de savoir qui a changé quoi.
        _journaliser(
            request,
            "MODIFICATION_MESSAGERIE",
            {
                "hote": parametres.hote,
                "port": parametres.port,
                "chiffrement": parametres.chiffrement,
                "identifiant": parametres.identifiant,
                "mot_de_passe_modifie": bool(nouveau_mot_de_passe),
            },
        )
        return Response(service.serialiser(parametres))

    def patch(self, request):
        """Alias de `PUT` : le client HTTP du frontend n'expose que PATCH pour les écritures."""
        return self.put(request)

    @extend_schema(summary="Revenir au réglage du serveur (.env)", responses={200: dict})
    def delete(self, request):
        _exiger_superviseur(request)
        with schema_context(get_public_schema_name()):
            ParametresMessagerie.objects.filter(pk=1).delete()
        _journaliser(request, "REINITIALISATION_MESSAGERIE", {})
        return Response(service.serialiser(None), status=status.HTTP_200_OK)


class AdminMessagerieTestView(APIView):
    """`POST /api/v1/admins/parametres/messagerie/tester/` — envoie un message et dit où ça casse."""

    permission_classes = [EstSuperAdminPlateforme]

    @extend_schema(summary="Tester l'envoi d'e-mail", request=TestMessagerieSerializer, responses={200: dict})
    def post(self, request):
        _exiger_superviseur(request)
        serializer = TestMessagerieSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        destinataire = serializer.validated_data["destinataire"]

        resultat = service.diagnostiquer_envoi(destinataire)
        reglage = resultat["reglage"]
        _journaliser(
            request,
            "TEST_MESSAGERIE",
            {
                "succes": resultat["succes"],
                "etape": resultat["etape"],
                "source": reglage["source"],
                "hote": reglage["hote"],
                "port": reglage["port"],
            },
        )
        return Response(resultat)
