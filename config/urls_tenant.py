"""Routage de l'API — une seule table de routes pour toute la plateforme (D9).

Sous django-tenants, deux URLconf coexistaient : celle-ci pour les schémas d'entreprise, et
`config.urls_public` pour le schéma `public`. Il n'y a plus de schéma à résoudre : toutes les
routes vivent ici, et l'entreprise d'une requête est celle que désigne son jeton vérifié
(`apps.core.authentification`). Les routes de maintenance de `urls_public` y sont reprises ;
le fichier disparaît au lot 8.

Convention d'API : tout est préfixé `/api/v1/` (tâche T-005).
"""

import contextlib

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def sante(_request):
    """Sonde de supervision. Elle ne dit rien de l'entreprise : elle ne lit aucun jeton."""
    return JsonResponse({"statut": "ok"})


from config.urls_public import (  # noqa: E402
    activer_abonnement_prod_vue,
    inspecter_entreprises_prod_vue,
    migrer_bd_vue,
    supprimer_entreprise_prod_vue,
)


urlpatterns = [
    path("api/v1/maintenance/migrer-bd/", migrer_bd_vue, name="maintenance-migrer-bd"),
    path(
        "api/v1/maintenance/entreprises/",
        inspecter_entreprises_prod_vue,
        name="maintenance-inspecter-entreprises",
    ),
    path(
        "api/v1/maintenance/entreprises/supprimer/",
        supprimer_entreprise_prod_vue,
        name="maintenance-supprimer-entreprise",
    ),
    path(
        "api/v1/maintenance/abonnements/activer/",
        activer_abonnement_prod_vue,
        name="maintenance-activer-abonnement",
    ),
    path("", RedirectView.as_view(url="/api/v1/docs/", permanent=False), name="accueil"),
    path("api/health/", sante, name="sante"),
    path("api/v1/schema/", SpectacularAPIView.as_view(urlconf="config.urls_tenant"), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.referentiels.urls")),
    path("api/v1/", include("apps.onboarding.urls")),
    path("api/v1/", include("apps.tenants.urls")),
    path("api/v1/", include("apps.tenants.urls_tenant")),
    path("api/v1/", include("apps.tiers.urls")),
    path("api/v1/", include("apps.projets.urls")),
    path("api/v1/", include("apps.chantier.urls")),
    path("api/v1/chantier/", include("apps.chantier.urls_journal")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.ged.urls")),
    path("api/v1/", include("apps.pilotage.urls")),
    path("api/v1/", include("apps.platform_admin.urls")),
]


# Outils de développement, s'ils sont présents : `config/urls_dev.py` n'est pas versionné, et
# le garde `DEBUG` l'empêche d'être monté en production même s'il y arrivait par mégarde.
if settings.DEBUG:
    with contextlib.suppress(ImportError):
        from config.urls_dev import urlpatterns as routes_dev

        urlpatterns += routes_dev

# En développement ou sur cPanel sans bucket S3 (FileSystemStorage), servir les fichiers médias
_stockage_defaut = settings.STORAGES.get("default", {}).get("BACKEND", "")
if settings.DEBUG or _stockage_defaut == "django.core.files.storage.FileSystemStorage":
    from django.urls import re_path
    from django.views.static import serve

    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]

# Administration standard Django (/admin/) : désactivée par défaut, activable par réglage
if getattr(settings, "ENABLE_DJANGO_ADMIN", False):
    urlpatterns.append(path("admin/", admin.site.urls))

# Conventions d API §5 : une URL non routée sous /api/ doit répondre en JSON,
# pas en HTML. Voir apps/core/views.py.
handler404 = "apps.core.views.page_introuvable"
handler500 = "apps.core.views.erreur_serveur"
