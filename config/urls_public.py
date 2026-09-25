"""Routage du schéma `public`.

Ce que l'on atteint ici : l'inscription d'une nouvelle entreprise, la
facturation, l'administration de la plateforme. **Aucune donnée métier
d'un client n'est accessible par ces routes.**
"""

import contextlib

from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def sante(_request):
    """Sonde de supervision — US-008."""
    return JsonResponse({"statut": "ok", "portee": "public"})


from io import StringIO
from django.core.management import call_command
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def migrer_bd_vue(request):
    """Exécute les migrations sans passer par cPanel SSH."""
    if request.method != "POST":
        return JsonResponse({"erreur": "Méthode non autorisée"}, status=405)

    token = request.headers.get("X-Maintenance-Token")
    if token != "ccd-migration-prod-2026-secure-token":
        return JsonResponse({"erreur": "Non autorisé"}, status=403)

    out = StringIO()
    try:
        call_command("migrate_schemas", interactive=False, stdout=out)
        return JsonResponse({"statut": "succes", "output": out.getvalue()})
    except Exception as exc:
        return JsonResponse({"statut": "erreur", "details": str(exc)}, status=500)


urlpatterns = [
    path("api/v1/maintenance/migrer-bd/", migrer_bd_vue, name="maintenance-migrer-bd"),
    path("", RedirectView.as_view(url="/api/v1/docs/", permanent=False), name="accueil"),
    path("admin/dashboard/", RedirectView.as_view(url="/admin/", permanent=False), name="admin-dashboard"),
    path("admin/", admin.site.urls),
    path("api/health/", sante, name="sante-publique"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="docs",
    ),
    # L'inscription d'une entreprise — cinq endpoints, contrat T-021. Ils
    # vivent ici dans le schéma `public` avant la création du schéma tenant dédié.
    path("api/v1/", include("apps.tenants.urls")),
    # L'authentification du **personnel de l'éditeur**. La même vue que celle
    # des clients, et c'est le propre de l'écart E1 : `utilisateur` existe dans
    # les deux territoires, et c'est le schéma qui dit de qui il s'agit. Un
    # compte de `public` n'apparaît dans aucune liste de collaborateurs, ne
    # consomme aucun siège de quota et n'a aucune affectation de projet.
    #
    # La porte est restreinte par adresse IP — `RestrictionIPPlateformeMiddleware`.
    path("api/v1/", include("apps.accounts.urls")),
    # Les règles de mot de passe sont servies aux deux territoires : l'écran
    # d'activation les demande avant qu'aucun tenant n'existe.
    path("api/v1/", include("apps.referentiels.urls")),
    # Plans, abonnements, factures et webhooks de paiement CinetPay
    path("api/v1/", include("apps.billing.urls")),
    # Administration plateforme et assistance Super Admin (impersonification)
    path("api/v1/", include("apps.platform_admin.urls")),
]

# --- Outils de développement, s'ils sont présents ---------------------------
# `config/urls_dev.py` n'est **pas versionné** : il n'existe que sur un poste de
# développement. L'import échoue donc sur un dépôt cloné, et ce bloc n'ajoute
# alors aucune route — c'est ce qui permet de le committer sans rien exposer.
#
# Le garde `DEBUG` est la seconde barrière : même si le fichier arrivait par
# mégarde en production, il ne serait pas monté.
if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    with contextlib.suppress(ImportError):
        from config.urls_dev import urlpatterns as routes_dev

        urlpatterns += routes_dev

# Conventions d API §5 : une URL non routée sous /api/ doit répondre en JSON,
# pas en HTML. Voir apps/core/views.py.
handler404 = "apps.core.views.page_introuvable"
handler500 = "apps.core.views.erreur_serveur"
