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


import hmac
from io import StringIO
from django.core.management import call_command
from django.views.decorators.csrf import csrf_exempt


def _refuser_maintenance(request):
    """Contrôle du jeton de maintenance. Renvoie une réponse d'erreur, ou None si autorisé.

    - aucun jeton configuré (`MAINTENANCE_TOKEN` vide) : 404, l'endpoint est éteint ;
    - jeton absent ou faux : 403 ;
    - comparaison à temps constant (`hmac.compare_digest`).
    """
    attendu = getattr(settings, "MAINTENANCE_TOKEN", "") or ""
    if not attendu:
        return JsonResponse({"erreur": "Ressource introuvable."}, status=404)
    fourni = request.headers.get("X-Maintenance-Token") or ""
    if not hmac.compare_digest(fourni.encode("utf-8"), attendu.encode("utf-8")):
        return JsonResponse({"erreur": "Non autorisé"}, status=403)
    return None


@csrf_exempt
def migrer_bd_vue(request):
    """Exécute les migrations sans passer par cPanel SSH."""
    refus = _refuser_maintenance(request)
    if refus is not None:
        return refus

    if request.method != "POST":
        return JsonResponse({"erreur": "Méthode non autorisée"}, status=405)

    out = StringIO()
    try:
        call_command("migrate_schemas", interactive=False, stdout=out)
        return JsonResponse({"statut": "succes", "output": out.getvalue()})
    except Exception as exc:
        return JsonResponse({"statut": "erreur", "details": str(exc)}, status=500)


@csrf_exempt
def purger_zanf_vue(request):
    """Exécute ou inspecte la purge des schémas et références 'zanf' sur commande."""
    refus = _refuser_maintenance(request)
    if refus is not None:
        return refus

    if request.method == "GET":
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, email, nom, prenom FROM public.utilisateur WHERE email ILIKE %s OR nom ILIKE %s OR prenom ILIKE %s;",
                ["%zanf%", "%zanf%", "%zanf%"],
            )
            users = [{"id": str(r[0]), "email": r[1], "nom": r[2], "prenom": r[3]} for r in cursor.fetchall()]
            cursor.execute(
                """
                SELECT id, schema_name, raison_sociale, email_contact FROM public.entreprise_cliente 
                WHERE schema_name ILIKE %s OR raison_sociale ILIKE %s OR email_contact ILIKE %s
                   OR id IN (SELECT entreprise_id FROM public.demande_inscription WHERE email ILIKE %s OR nom ILIKE %s OR prenom ILIKE %s);
                """,
                ["%zanf%", "%zanf%", "%zanf%", "%zanf%", "%zanf%", "%zanf%"],
            )
            ent = [{"id": str(r[0]), "schema_name": r[1], "raison_sociale": r[2], "email_contact": r[3]} for r in cursor.fetchall()]
            ent_schemas = [e["schema_name"] for e in ent]
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE (schema_name ILIKE %s OR schema_name = ANY(%s)) AND schema_name NOT IN ('public', 'demo');",
                ["%zanf%", ent_schemas],
            )
            schemas = [r[0] for r in cursor.fetchall()]
            cursor.execute(
                "SELECT id, email, slug_reserve, raison_sociale, statut, cree_le, modifie_le FROM public.demande_inscription WHERE email ILIKE %s OR slug_reserve ILIKE %s OR raison_sociale ILIKE %s OR nom ILIKE %s OR prenom ILIKE %s;",
                ["%zanf%", "%zanf%", "%zanf%", "%zanf%", "%zanf%"],
            )
            dem = [
                {
                    "id": str(r[0]),
                    "email": r[1],
                    "slug_reserve": r[2],
                    "raison_sociale": r[3],
                    "statut": r[4],
                    "cree_le": str(r[5]),
                    "modifie_le": str(r[6]),
                }
                for r in cursor.fetchall()
            ]

        import sys, os
        return JsonResponse({
            "statut": "ok",
            "sys_executable": sys.executable,
            "virtual_env": os.environ.get("VIRTUAL_ENV"),
            "frontend_url": getattr(settings, "FRONTEND_URL", None),
            "domaine_principal": getattr(settings, "DOMAINE_PRINCIPAL", None),
            "utilisateurs_public_zanf": users,
            "schemas_postgre_zanf": schemas,
            "entreprises_public_zanf": ent,
            "demandes_inscription_zanf": dem,
        })

    if request.method != "POST":
        return JsonResponse({"erreur": "Méthode non autorisée"}, status=405)

    out = StringIO()
    from django.core.management.color import color_style
    from apps.tenants.management.commands.provisionner_inscriptions import _purger_tout_zanf
    from django.db import connection
    try:
        _purger_tout_zanf(stdout=out, style=color_style())
        connection.commit()
        return JsonResponse({"statut": "succes", "output": out.getvalue()})
    except Exception as exc:
        return JsonResponse({"statut": "erreur", "details": str(exc)}, status=500)


@csrf_exempt
def inspecter_entreprises_prod_vue(request):
    """Inspection sécurisée des entreprises et directeurs généraux en production."""
    refus = _refuser_maintenance(request)
    if refus is not None:
        return refus

    if request.method != "GET":
        return JsonResponse({"erreur": "Méthode non autorisée"}, status=405)

    from apps.tenants.services.nettoyage import lister_entreprises_avec_directeurs
    try:
        donnees = lister_entreprises_avec_directeurs()
        return JsonResponse({"statut": "ok", **donnees})
    except Exception as exc:
        return JsonResponse({"statut": "erreur", "details": str(exc)}, status=500)


@csrf_exempt
def supprimer_entreprise_prod_vue(request):
    """Suppression propre et atomique d'une entreprise (schéma + dépendances public)."""
    refus = _refuser_maintenance(request)
    if refus is not None:
        return refus

    if request.method != "POST":
        return JsonResponse({"erreur": "Méthode non autorisée"}, status=405)

    import json
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    identifiant = (
        payload.get("schema_name")
        or payload.get("entreprise_id")
        or payload.get("identifiant")
    )
    if not identifiant:
        return JsonResponse(
            {"erreur": "Identifiant requis (précisez 'schema_name' ou 'entreprise_id')."},
            status=400,
        )

    from apps.tenants.services.nettoyage import supprimer_entreprise_proprement
    try:
        rapport = supprimer_entreprise_proprement(identifiant)
        from django.db import connection
        connection.commit()
        return JsonResponse({"statut": "succes", "rapport": rapport})
    except ValueError as exc:
        return JsonResponse({"statut": "erreur", "message": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"statut": "erreur", "details": str(exc)}, status=500)


@csrf_exempt
def activer_abonnement_prod_vue(request):
    """Activation ou renouvellement souverain d'un abonnement entreprise en production."""
    refus = _refuser_maintenance(request)
    if refus is not None:
        return refus

    if request.method != "POST":
        return JsonResponse({"erreur": "Méthode non autorisée"}, status=405)

    import json

    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        body = {}

    identifiant = (
        body.get("identifiant")
        or body.get("schema_name")
        or body.get("email")
        or request.GET.get("identifiant")
    )
    if not identifiant:
        return JsonResponse(
            {"erreur": "Identifiant requis ('identifiant', 'schema_name' ou 'email')."},
            status=400,
        )

    plan_code = body.get("plan_code") or request.GET.get("plan_code") or "MAITRE_OEUVRE"
    duree_jours = int(body.get("duree_jours") or request.GET.get("duree_jours") or 365)

    from apps.tenants.services.nettoyage import activer_ou_renouveler_abonnement

    try:
        rapport = activer_ou_renouveler_abonnement(identifiant, plan_code, duree_jours)
        return JsonResponse({"statut": "succes", "rapport": rapport})
    except ValueError as exc:
        return JsonResponse({"statut": "erreur", "message": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"statut": "erreur", "details": str(exc)}, status=500)


urlpatterns = [
    path("api/v1/maintenance/migrer-bd/", migrer_bd_vue, name="maintenance-migrer-bd"),
    path("api/v1/maintenance/purger-zanf/", purger_zanf_vue, name="maintenance-purger-zanf"),
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
    path("api/health/", sante, name="sante-publique"),
    path("api/v1/schema/", SpectacularAPIView.as_view(urlconf="config.urls_tenant"), name="schema"),
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
    # La porte d'authentification plateforme (accès ouvert sans restriction d'adresse IP).
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
    with contextlib.suppress(ImportError):
        from config.urls_dev import urlpatterns as routes_dev

        urlpatterns += routes_dev

# Servir les fichiers médias si FileSystemStorage est actif (ex: cPanel sans S3 configuré)
_stockage_defaut = settings.STORAGES.get("default", {}).get("BACKEND", "")
if settings.DEBUG or _stockage_defaut == "django.core.files.storage.FileSystemStorage":
    from django.urls import re_path
    from django.views.static import serve

    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]

# Administration standard Django (/admin/) : désactivée par défaut, activable par réglage
if getattr(settings, "ENABLE_DJANGO_ADMIN", False):
    urlpatterns += [
        path(
            "admin/dashboard/",
            RedirectView.as_view(url="/admin/", permanent=False),
            name="admin-dashboard",
        ),
        path("admin/", admin.site.urls),
    ]

# Conventions d API §5 : une URL non routée sous /api/ doit répondre en JSON,
# pas en HTML. Voir apps/core/views.py.
handler404 = "apps.core.views.page_introuvable"
handler500 = "apps.core.views.erreur_serveur"
