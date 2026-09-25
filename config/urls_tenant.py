"""Routage des schémas de tenant — tout le métier BTP.

Le middleware `TenantResolutionMiddleware` a déjà déterminé le schéma du tenant
(via le claim `schema` du token JWT Bearer, ou l'en-tête `X-Tenant`) avant que
ces vues soient atteintes. Une route déclarée ici ne peut voir que les données
de l'entreprise appelante.

Convention d'API : tout est préfixé `/api/v1/` (tâche T-005).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def sante(request):
    """Sonde de supervision — renvoie le schéma effectivement résolu."""
    return JsonResponse(
        {
            "statut": "ok",
            "portee": "tenant",
            "schema": getattr(request.tenant, "schema_name", None),
        }
    )


from config.urls_public import migrer_bd_vue


urlpatterns = [
    path("api/v1/maintenance/migrer-bd/", migrer_bd_vue, name="maintenance-migrer-bd-tenant"),
    path("", RedirectView.as_view(url="/api/v1/docs/", permanent=False), name="accueil"),
    path("admin/", admin.site.urls),
    path("api/health/", sante, name="sante-tenant"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.referentiels.urls")),
    path("api/v1/", include("apps.onboarding.urls")),
    path("api/v1/", include("apps.tenants.urls")),
    path("api/v1/", include("apps.tenants.urls_tenant")),
    path("api/v1/", include("apps.tiers.urls")),
    path("api/v1/", include("apps.projets.urls")),
    path("api/v1/", include("apps.chantier.urls")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.finance.urls")),
    path("api/v1/", include("apps.platform_admin.urls")),
]

# En développement ou sur cPanel sans bucket S3 (FileSystemStorage), servir les fichiers médias
_stockage_defaut = settings.STORAGES.get("default", {}).get("BACKEND", "")
if settings.DEBUG or _stockage_defaut == "django.core.files.storage.FileSystemStorage":
    from django.urls import re_path
    from django.views.static import serve

    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]

# Conventions d API §5 : une URL non routée sous /api/ doit répondre en JSON,
# pas en HTML. Voir apps/core/views.py.
handler404 = "apps.core.views.page_introuvable"
handler500 = "apps.core.views.erreur_serveur"
