"""Middleware de résolution multi-tenant hybride pour CCD Digital.

Permet à l'API de fonctionner en mode domaine unique (ex: api-chantier.soumafe.com)
tout en conservant l'isolation stricte des données par schéma PostgreSQL :
1. Jeton JWT Bearer : extrait le claim `schema` (injecté à la connexion).
2. En-tête `X-Tenant` : permet la sélection explicite d'un tenant si nécessaire.
3. Nom d'hôte (sous-domaine) : rétrocompatibilité pour les environnements de dev (ex: demo.localhost).
4. Schéma public par défaut : pour les routes anonymes (inscription, santé, documentation).
"""

import logging
import jwt
from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.db import connection
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import (
    get_public_schema_name,
    get_tenant_domain_model,
    get_tenant_model,
)

logger = logging.getLogger(__name__)


class TenantResolutionMiddleware(TenantMainMiddleware):
    """Résout le tenant et active le bon schéma PostgreSQL."""

    def process_request(self, request):
        connection.set_schema_to_public()
        tenant_model = get_tenant_model()
        public_schema_name = get_public_schema_name()

        # 0. Routes strictement publiques de la plateforme (inscription, santé, documentation).
        # Elles doivent TOUJOURS s'exécuter sur le schéma public et charger PUBLIC_SCHEMA_URLCONF,
        # même si l'appelant a un jeton Bearer ou un sous-domaine de tenant résiduel.
        if request.path.startswith(("/api/v1/inscription", "/api/health", "/api/v1/docs", "/api/v1/schema")):
            try:
                public_tenant = tenant_model.objects.get(schema_name=public_schema_name)
                request.tenant = public_tenant
                connection.set_tenant(public_tenant)
                self.setup_url_routing(request, force_public=True)
                return
            except tenant_model.DoesNotExist:
                raise self.TENANT_NOT_FOUND_EXCEPTION("Impossible de trouver le tenant public.")

        # 1. Résolution via Jeton JWT (en-tête Authorization: Bearer <token>)
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            token_str = auth_header[7:].strip()
            if token_str:
                try:
                    payload = jwt.decode(token_str, options={"verify_signature": False})
                    schema = payload.get("schema")
                    if schema and schema != public_schema_name:
                        tenant = tenant_model.objects.filter(schema_name=schema).first()
                        if tenant:
                            request.tenant = tenant
                            connection.set_tenant(request.tenant)
                            self.setup_url_routing(request)
                            return
                except Exception as exc:
                    logger.debug("Échec décodage non-vérifié JWT dans le middleware : %s", exc)

        # 2. Résolution via en-tête explicite X-Tenant
        x_tenant = request.META.get("HTTP_X_TENANT")
        if x_tenant:
            x_tenant_slug = x_tenant.strip().lower()
            if x_tenant_slug and x_tenant_slug != public_schema_name:
                tenant = tenant_model.objects.filter(schema_name=x_tenant_slug).first()
                if tenant:
                    request.tenant = tenant
                    connection.set_tenant(request.tenant)
                    self.setup_url_routing(request)
                    return

        # 3. Résolution par nom d'hôte / sous-domaine (ex: demo.localhost)
        try:
            hostname = self.hostname_from_request(request)
        except DisallowedHost:
            from django.http import HttpResponseNotFound

            return HttpResponseNotFound()

        domain_model = get_tenant_domain_model()
        try:
            tenant = self.get_tenant(domain_model, hostname)
            if tenant and tenant.schema_name != public_schema_name:
                tenant.domain_url = hostname
                request.tenant = tenant
                connection.set_tenant(request.tenant)
                self.setup_url_routing(request)
                return
        except domain_model.DoesNotExist:
            pass

        # 4. Fallback vers le schéma public (pour requêtes sans authentification ou sur domaine principal)
        try:
            public_tenant = tenant_model.objects.get(schema_name=public_schema_name)
            request.tenant = public_tenant
            connection.set_tenant(public_tenant)
            self.setup_url_routing(request, force_public=True)
        except tenant_model.DoesNotExist:
            raise self.TENANT_NOT_FOUND_EXCEPTION("Impossible de trouver le tenant public.")
