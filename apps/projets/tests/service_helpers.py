"""Exercise the internal orchestration serializer, not the public CRUD endpoint.

Legacy lots/team/invitation workflows remain available to internal callers.
HTTP permissions and the restricted form are tested separately.
"""

from dataclasses import dataclass

from django_tenants.utils import schema_context
from rest_framework.exceptions import APIException
from rest_framework.test import APIRequestFactory

from apps.core.exceptions import gestionnaire_erreurs
from apps.projets.models import Projet
from apps.projets.serializers import ProjetCreationSerializer, ProjetSerializer


@dataclass
class ResultatService:
    data: dict
    status_code: int

    def json(self):
        return self.data


def creer_projet_via_service(client, path, data, **kwargs):
    assert path == "/api/v1/projets/"
    request = APIRequestFactory().post(path, data, format="json", HTTP_HOST="demo.localhost")
    request.user = client.utilisateur_service
    with schema_context("demo"):
        try:
            serializer = ProjetCreationSerializer(data=data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            projet = serializer.save()
            return ResultatService(ProjetSerializer(projet).data, 201)
        except APIException as exc:
            response = gestionnaire_erreurs(exc, {"request": request})
            return ResultatService(response.data, response.status_code)


def modifier_projet_via_service(client, path, data, **kwargs):
    """Check internal update invariants without reintroducing the old public contract."""
    request = APIRequestFactory().patch(path, data, format="json")
    request.user = client.utilisateur_service
    with schema_context("demo"):
        try:
            projet = Projet.objects.get(pk=path.rstrip("/").split("/")[-1])
            serializer = ProjetCreationSerializer(
                projet, data=data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            projet = serializer.save()
            return ResultatService(ProjetSerializer(projet).data, 200)
        except APIException as exc:
            response = gestionnaire_erreurs(exc, {"request": request})
            return ResultatService(response.data, response.status_code)
