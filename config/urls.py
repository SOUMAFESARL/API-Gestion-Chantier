"""Routage de l'API — une seule table de routes pour toute la plateforme (D9).

L'entreprise d'une requête est celle que désigne son jeton vérifié
(`apps.core.authentification`), jamais l'hôte ni un en-tête.

Convention d'API : tout est préfixé `/api/v1/` (tâche T-005).
"""

import contextlib
import hashlib
import hmac
import json
from io import StringIO

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def sante(_request):
    """Sonde de supervision. Elle ne dit rien de l'entreprise : elle ne lit aucun jeton."""
    return JsonResponse({"statut": "ok"})


# --------------------------------------------------------------------------
# Routes de maintenance — protégées par `MAINTENANCE_TOKEN_SHA256`, éteintes sans lui.
# --------------------------------------------------------------------------


def _refuser_maintenance(request):
    """Contrôle du jeton de maintenance. Renvoie une réponse d'erreur, ou None si autorisé.

    - aucune empreinte configurée (`MAINTENANCE_TOKEN_SHA256` vide) : 404, l'endpoint est éteint ;
    - jeton absent ou faux : 403 ;
    - on compare des **empreintes**, à temps constant : le serveur ne détient jamais le jeton.
    """
    attendu = getattr(settings, "MAINTENANCE_TOKEN_SHA256", "") or ""
    if not attendu:
        return JsonResponse({"erreur": "Ressource introuvable."}, status=404)
    fourni = request.headers.get("X-Maintenance-Token") or ""
    empreinte = hashlib.sha256(fourni.encode("utf-8")).hexdigest()
    if not fourni or not hmac.compare_digest(empreinte, attendu):
        return JsonResponse({"erreur": "Non autorisé"}, status=403)
    return None


def _refuser_destructif(request):
    """Comme `_refuser_maintenance`, et en plus fermé sans `MAINTENANCE_DESTRUCTIF`.

    Le 404 vient **avant** le contrôle du jeton : un endpoint fermé ne dit pas qu'il existe.
    """
    if not getattr(settings, "MAINTENANCE_DESTRUCTIF", False):
        return JsonResponse({"erreur": "Ressource introuvable."}, status=404)
    return _refuser_maintenance(request)


_TABLES_VERIF_PROPRIETAIRE = (
    "semaine_type",
    "projet",
    "avenant",
    "historique_date",
    "liste_valeurs_entreprise",
    "catalogue_liste_valeurs_plateforme",
)


def _activer_role_proprietaire(out: StringIO) -> bool:
    """Bascule la session SQL vers le propriétaire des tables si `current_user` en est membre."""
    try:
        with connection.cursor() as curseur:
            curseur.execute(
                """
                SELECT current_user,
                       t.tableowner,
                       pg_has_role(current_user, t.tableowner, 'MEMBER')
                FROM pg_tables t
                WHERE t.schemaname = current_schema()
                  AND t.tablename = ANY(%s)
                  AND t.tableowner <> current_user
                """,
                [list(_TABLES_VERIF_PROPRIETAIRE)],
            )
            lignes = curseur.fetchall()
            eligibles = sorted({owner for _, owner, membre in lignes if owner and membre})
            if not eligibles:
                return False
            cible = eligibles[0].replace('"', '""')
            curseur.execute(f'SET ROLE "{cible}"')
            out.write(f"Rôle PostgreSQL basculé vers « {eligibles[0]} ».\n")
            return True
    except DatabaseError:
        with contextlib.suppress(Exception):
            connection.rollback()
        return False


def _diagnostic_proprietaires() -> str:
    """Expose le rôle connecté et les propriétaires SQL en cas d'erreur de migration."""
    try:
        with contextlib.suppress(Exception):
            connection.rollback()
        with connection.cursor() as curseur:
            curseur.execute("SELECT current_user, session_user")
            courant, session = curseur.fetchone()
            curseur.execute(
                """
                SELECT t.tablename,
                       t.tableowner,
                       pg_has_role(current_user, t.tableowner, 'MEMBER')
                FROM pg_tables t
                WHERE t.schemaname = current_schema()
                  AND t.tablename = ANY(%s)
                ORDER BY t.tablename
                """,
                [list(_TABLES_VERIF_PROPRIETAIRE)],
            )
            tables = curseur.fetchall()
            curseur.execute(
                """
                SELECT r.rolname
                FROM pg_auth_members m
                JOIN pg_roles r ON r.oid = m.roleid
                JOIN pg_roles u ON u.oid = m.member
                WHERE u.rolname = current_user
                ORDER BY r.rolname
                """
            )
            membres = [ligne[0] for ligne in curseur.fetchall()]
        resume_tables = ", ".join(
            f"{nom}:{owner}(membre={bool(membre)})" for nom, owner, membre in tables
        )
        return (
            f"current_user={courant}; session_user={session}; "
            f"roles_membres={membres}; tables=[{resume_tables}]"
        )
    except Exception as exc:
        return f"diagnostic_sql_indisponible={exc}"


@csrf_exempt
def migrer_bd_vue(request):
    """Exécute les migrations, le seed plateforme idempotent et les synchronisations, sans SSH."""
    refus = _refuser_maintenance(request)
    if refus is not None:
        return refus

    if request.method != "POST":
        return JsonResponse({"erreur": "Méthode non autorisée"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}") if request.body else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    from apps.core.services.initialisation import ensemencer_base_plateforme

    out = StringIO()
    erreurs = StringIO()
    role_active = False
    try:
        role_active = _activer_role_proprietaire(out)
        call_command("migrate", interactive=False, stdout=out, stderr=erreurs)
        call_command("verifier_isolation", stdout=out, stderr=erreurs)
        ensemencer_base_plateforme(
            out,
            stderr=erreurs,
            super_admin_email=payload.get("super_admin_email"),
            super_admin_mot_de_passe=payload.get("super_admin_mot_de_passe"),
        )
        with contextlib.suppress(Exception):
            cache.clear()
        return JsonResponse({"statut": "succes", "output": out.getvalue()})
    except Exception as exc:
        diag_roles = _diagnostic_proprietaires()
        diagnostic = "\n".join(
            part for part in (erreurs.getvalue().strip(), diag_roles) if part
        )
        return JsonResponse(
            {
                "statut": "erreur",
                "details": str(exc),
                "diagnostic": diagnostic,
                "output": out.getvalue(),
            },
            status=500,
        )
    finally:
        if role_active:
            with contextlib.suppress(Exception):
                connection.rollback()
            with contextlib.suppress(Exception), connection.cursor() as curseur:
                curseur.execute("RESET ROLE")


@csrf_exempt
def inspecter_entreprises_prod_vue(request):
    """Inspection sécurisée des entreprises et directeurs généraux en production."""
    refus = _refuser_maintenance(request)
    if refus is not None:
        return refus

    if request.method != "GET":
        return JsonResponse({"erreur": "Méthode non autorisée"}, status=405)

    from apps.entreprises.services.nettoyage import lister_entreprises_avec_directeurs
    try:
        donnees = lister_entreprises_avec_directeurs()
        return JsonResponse({"statut": "ok", **donnees})
    except Exception as exc:
        return JsonResponse({"statut": "erreur", "details": str(exc)}, status=500)


@csrf_exempt
def supprimer_entreprise_prod_vue(request):
    """Suppression définitive d'une entreprise et de toutes ses lignes (`supprimer_definitivement`)."""
    refus = _refuser_destructif(request)
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
        payload.get("slug")
        or payload.get("entreprise_id")
        or payload.get("identifiant")
    )
    if not identifiant:
        return JsonResponse(
            {"erreur": "Identifiant requis (précisez 'slug' ou 'entreprise_id')."},
            status=400,
        )

    from apps.entreprises.services.nettoyage import supprimer_entreprise_proprement
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
        or body.get("slug")
        or body.get("email")
        or request.GET.get("identifiant")
    )
    if not identifiant:
        return JsonResponse(
            {"erreur": "Identifiant requis ('identifiant', 'slug' ou 'email')."},
            status=400,
        )

    plan_code = body.get("plan_code") or request.GET.get("plan_code") or "MAITRE_OEUVRE"
    duree_jours = int(body.get("duree_jours") or request.GET.get("duree_jours") or 365)

    from apps.entreprises.services.nettoyage import activer_ou_renouveler_abonnement

    try:
        rapport = activer_ou_renouveler_abonnement(identifiant, plan_code, duree_jours)
        return JsonResponse({"statut": "succes", "rapport": rapport})
    except ValueError as exc:
        return JsonResponse({"statut": "erreur", "message": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"statut": "erreur", "details": str(exc)}, status=500)




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
    path("api/v1/schema/", SpectacularAPIView.as_view(urlconf="config.urls"), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.referentiels.urls")),
    path("api/v1/", include("apps.onboarding.urls")),
    path("api/v1/", include("apps.entreprises.urls")),
    path("api/v1/", include("apps.entreprises.urls_profil")),
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

# Conventions d API §5 : une URL non routée sous /api/ doit répondre en JSON,
# pas en HTML. Voir apps/core/views.py.
handler404 = "apps.core.views.page_introuvable"
handler500 = "apps.core.views.erreur_serveur"
