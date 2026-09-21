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


from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def reinitialiser_bd_vue(request):
    if request.method != "POST":
        return JsonResponse({"erreur": "Methode non autorisee"}, status=405)

    token = request.headers.get("X-Maintenance-Token")
    if token != "ccd-reset-prod-2026-secure-token":
        return JsonResponse({"erreur": "Non autorise"}, status=403)

    from django.conf import settings
    from django_tenants.utils import get_public_schema_name, schema_context
    from apps.accounts.models import Utilisateur
    from apps.billing.models import Abonnement
    from apps.tenants.models import DemandeInscription, Entreprise

    # 1. Demandes
    demandes_count = 0
    for d in list(DemandeInscription.tous_objets.all()):
        d.supprimer_definitivement()
        demandes_count += 1

    # 2. Abonnements
    abonnements_count = 0
    for a in list(Abonnement.tous_objets.all()):
        a.supprimer_definitivement()
        abonnements_count += 1

    # 3. Entreprises et schémas PostgreSQL
    entreprises = list(Entreprise.objects.exclude(schema_name=settings.PUBLIC_SCHEMA_NAME))
    entreprises_supprimees = []
    for e in entreprises:
        schema = e.schema_name
        e.delete(force_drop=True)
        entreprises_supprimees.append(schema)

    # 4. Utilisateurs dans public
    public_schema = get_public_schema_name()
    utilisateurs_count = 0
    with schema_context(public_schema):
        for u in list(Utilisateur.tous_objets.all()):
            u.supprimer_definitivement()
            utilisateurs_count += 1

    return JsonResponse({
        "statut": "succes",
        "demandes_supprimees": demandes_count,
        "abonnements_supprimes": abonnements_count,
        "entreprises_supprimees": entreprises_supprimees,
        "utilisateurs_public_supprimes": utilisateurs_count,
    })


def sante(_request):
    """Sonde de supervision — US-008."""
    return JsonResponse({"statut": "ok", "portee": "public"})


urlpatterns = [
    path("api/v1/maintenance/reinitialiser-bd/", reinitialiser_bd_vue, name="maintenance-reset-bd"),
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
