"""Configuration commune à tous les environnements — CCD Digital.

Aucune valeur secrète ni dépendante de l'environnement n'est écrite ici :
tout passe par le fichier `.env` à la racine du dépôt (voir `.env.example`).

Décisions appliquées, issues du dossier de conception :
  D1  isolation multi-tenant par schéma PostgreSQL (django-tenants)
  D5  montants en centimes de FCFA
  D6  stockage des horodatages en UTC, affichage en heure locale
"""

from datetime import timedelta
from pathlib import Path

from decouple import Config, RepositoryEnv, UndefinedValueError
from decouple import config as env_config

# --------------------------------------------------------------------------
# Chemins
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
RACINE_DEPOT = BASE_DIR.parent

# Recherche du .env : à la racine du projet ou dans le dossier parent
if (BASE_DIR / ".env").exists():
    _fichier_env = BASE_DIR / ".env"
elif (RACINE_DEPOT / ".env").exists():
    _fichier_env = RACINE_DEPOT / ".env"
else:
    _fichier_env = BASE_DIR / ".env"

config = Config(RepositoryEnv(_fichier_env)) if _fichier_env.exists() else env_config

FACTURATION_EMETTEUR = {
    champ: config(f"FACTURATION_{champ.upper()}", default="")
    for champ in (
        "raison_sociale", "forme_juridique", "capital", "adresse", "ville", "pays",
        "rccm", "nif", "centre_fiscal", "email", "telephone", "banque", "iban", "bic",
    )
}

# --------------------------------------------------------------------------
# Sécurité
# --------------------------------------------------------------------------
try:
    SECRET_KEY = config("DJANGO_SECRET_KEY")
except UndefinedValueError as exc:  # pragma: no cover
    raise RuntimeError(
        "DJANGO_SECRET_KEY est absent. Copiez .env.example en .env et renseignez-le (voir README)."
    ) from exc

DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)


def _liste(valeur: str) -> list[str]:
    """Transforme une variable « a,b,c » en liste."""
    return [element.strip() for element in valeur.split(",") if element.strip()]


ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="", cast=_liste)

# --------------------------------------------------------------------------
# Applications — la répartition entre les deux listes EST l'isolation.
# Une application placée dans TENANT_APPS voit ses tables créées dans chaque
# schéma client ; dans SHARED_APPS, dans le seul schéma `public`.
# Se tromper de liste, c'est exposer les données d'un client à un autre.
# --------------------------------------------------------------------------
SHARED_APPS = [
    "django_tenants",  # doit rester en premier
    "apps.tenants",  # porte le modèle de tenant
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.accounts",  # écart E1 — voir README §Écarts
    # Même raison que `accounts`, et c'est l'écart E1 qui l'impose : le journal
    # d'audit suit les utilisateurs, qui existent dans `public` **et** dans
    # chaque schéma client. Présent d'un seul côté, il laissait les actions du
    # personnel de l'éditeur sans trace — or le Socle §2.4 dit « sans
    # exception », et un registre à trous ne prouve rien en cas de litige.
    "apps.audit",
    "apps.billing",
    "apps.platform_admin",
    "apps.support",
    "apps.referentiels",
]

TENANT_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    # socle transverse
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.notifications",
    "apps.tiers",
    "apps.onboarding",
    # modules métier — niveau B
    "apps.projets",  # module 1
    "apps.chantier",  # module 2
    "apps.finance",  # module 3
    # modules métier — niveau A, squelettes en attente de leur MLD
    "apps.achats",  # module 4
    "apps.stocks",  # module 5
    "apps.rh",  # module 6
    "apps.equipements",  # module 7
    "apps.qhse",  # module 8
    "apps.contrats",  # module 9
    "apps.parties_prenantes",  # module 10
    "apps.ged",  # module 11
    "apps.pilotage",  # module 12
]

TIERCES_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
]

SHARED_APPS += TIERCES_APPS
TENANT_APPS += ["rest_framework", "django_filters"]

INSTALLED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]

# --------------------------------------------------------------------------
# Multi-tenant
# --------------------------------------------------------------------------
TENANT_MODEL = "tenants.Entreprise"
TENANT_DOMAIN_MODEL = "tenants.Domaine"
PUBLIC_SCHEMA_NAME = "public"
PUBLIC_SCHEMA_URLCONF = "config.urls_public"
DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)

# --------------------------------------------------------------------------
# Middleware — TenantMainMiddleware doit rester en tête : il détermine le
# schéma avant que la moindre requête ne touche la base.
# --------------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.middleware_tenant.TenantResolutionMiddleware",
    "apps.core.middleware.IdentifiantRequeteMiddleware",
    # Après le middleware de tenant, qui pose `request.tenant`, et avant
    # tout le reste : une porte se ferme au plus tôt.
    "apps.core.middleware.RestrictionIPPlateformeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Verrou absolu R-128 : refuse toute mutation sous jeton d'assistance Super Admin
    "apps.platform_admin.middleware.LectureSeuleAssistanceMiddleware",
    # En dernier : il a besoin de `request.tenant`, et il ne doit refuser
    # l'écriture qu'après que tout le reste a laissé passer la requête.
    "apps.billing.middleware.LectureSeuleAbonnementMiddleware",
]

ROOT_URLCONF = "config.urls_tenant"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Base de données — le moteur django_tenants est obligatoire, c'est lui qui
# positionne le `search_path` sur le schéma du client à chaque connexion.
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": config("POSTGRES_DB", default="ccd_digital"),
        "USER": config("POSTGRES_USER", default="ccd"),
        "PASSWORD": config("POSTGRES_PASSWORD", default=""),
        "HOST": config("POSTGRES_HOST", default="localhost"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": config("POSTGRES_CONN_MAX_AGE", default=60, cast=int),
    }
}

# --------------------------------------------------------------------------
# Compatibilité SGBD : autoriser PostgreSQL >= 13.0 (notamment PostgreSQL 13.23
# sur hébergements mutualisés cPanel / CloudLinux).
# --------------------------------------------------------------------------
from django.db.backends.postgresql.features import DatabaseFeatures

DatabaseFeatures.minimum_database_version = (13,)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------
# Authentification
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.Utilisateur"

# auth.E003 exige que USERNAME_FIELD porte `unique=True`.
# Nous appliquons à la place une unicité **partielle** — unique parmi les
# comptes vivants seulement (MLD §7.2) — pour qu'une adresse libérée par une
# suppression logique puisse resservir. La garantie est plus forte, pas plus
# faible : la contrainte existe bien en base, et le manager d'authentification
# ignore les comptes supprimés. Le contrôle de Django ne sait simplement pas
# lire une contrainte conditionnelle.
SILENCED_SYSTEM_CHECKS = ["auth.E003"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},  # Socle Commun §2.1
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    # Défaut D-4 : Django n'apporte que la longueur. Le Socle §2.1 exige aussi
    # une majuscule, un chiffre et un caractère spécial — les trois coches que
    # M6 affichait sans qu'aucun contrôle serveur ne leur corresponde.
    {"NAME": "apps.core.validators.ValidateurMajuscule"},
    {"NAME": "apps.core.validators.ValidateurChiffre"},
    {"NAME": "apps.core.validators.ValidateurCaractereSpecial"},
]

# Adresse du frontend, pour composer les liens envoyés par email. Le jeton
# voyage en **fragment** (`#jeton=…`), jamais en paramètre de requête : un
# paramètre finirait dans les journaux du serveur, ce que la stratégie de
# déploiement §6 interdit — décision J5 du contrat de réinitialisation.
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")

# Domaine principal de la plateforme (Architecture Domaine Unique - Option A).
# L'API et le frontend partagent un point d'accès unifié sans sous-domaines clients.
DOMAINE_PRINCIPAL = config("DOMAINE_PRINCIPAL", default="localhost")

# --------------------------------------------------------------------------
# Emails & Configuration SMTP (Gmail / Fournisseur SMTP)
# --------------------------------------------------------------------------
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_SSL_CERT_VERIFY = config("EMAIL_SSL_CERT_VERIFY", default=True, cast=bool)

# Supporte indifféremment SYSTEM_SMTP_USER / SYSTEM_SMTP_PASS ou EMAIL_HOST_USER / EMAIL_HOST_PASSWORD
EMAIL_HOST_USER = config(
    "SYSTEM_SMTP_USER",
    default=config("EMAIL_HOST_USER", default=""),
)
EMAIL_HOST_PASSWORD = config(
    "SYSTEM_SMTP_PASS",
    default=config("EMAIL_HOST_PASSWORD", default=""),
)

DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default=f"CCD Digital <{EMAIL_HOST_USER}>"
    if EMAIL_HOST_USER
    else "ne-pas-repondre@ccd-digital.ci",
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Le contact commercial, cité dans l'email d'espace suspendu.
EMAIL_COMMERCIAL = config("EMAIL_COMMERCIAL", default="commercial@ccd-digital.ci")
TELEPHONE_COMMERCIAL = config("TELEPHONE_COMMERCIAL", default="+225 27 00 00 00 00")

# Adresses autorisées à atteindre l'authentification du schéma `public` — la
# porte du personnel de l'éditeur. Matrice des rôles §1.1.
#
# **Vide et hors développement, elle interdit tout.** La valeur par défaut d'une
# porte d'administration doit être fermée : un déploiement qui oublie ce réglage
# s'en aperçoit à la première connexion, ce qui vaut mieux que de ne jamais s'en
# apercevoir.
SUPER_ADMIN_IPS = [
    ip.strip() for ip in config("SUPER_ADMIN_IPS", default="").split(",") if ip.strip()
]

# Socle Commun §2.1 — bcrypt en premier.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.PaginationStandard",
    "PAGE_SIZE": 20,  # Socle Commun — 20 par page
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "EXCEPTION_HANDLER": "apps.core.exceptions.gestionnaire_erreurs",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/min",
        "user": "1000/min",
        # La connexion porte deux compteurs, pour deux menaces distinctes.
        # Par IP : protège la plateforme d'un balayage — un mot de passe
        # courant essayé sur des milliers d'adresses ne bloque aucun compte,
        # puisqu'il ne s'acharne sur aucun.
        "connexion": "30/min",
        # Par adresse : protège **un** compte d'un essaimage — le même email
        # tenté depuis cent IP passe sous le compteur précédent sans le faire
        # sonner. Voir apps/accounts/throttling.py.
        "connexion_email": "10/min",
        # Réinitialisation du mot de passe — contrat §3.4, §5.3 et §5bis.
        # Par IP : empêche le balayage d'adresses.
        "mdp_demande": "5/hour",
        # Par adresse : empêche le harcèlement d'un tiers par email. Le même
        # `429` est renvoyé que l'adresse existe ou non — une limite qui ne se
        # déclencherait que sur les comptes réels serait un oracle de plus.
        "mdp_demande_email": "3/hour",
        # Une demande par cinq minutes : c'est le délai que le bouton
        # « Renvoyer l'email » de M6 doit respecter à l'écran.
        "mdp_demande_rapprochee": "1/5min",
        # Un jeton ne se devine pas par balayage.
        "mdp_reinitialiser": "10/hour",
        "mdp_verifier": "20/hour",
        # Inscription — contrat T-021 §8. Le dépôt est le plus exposé : c'est
        # un formulaire public qui déclenche un email.
        "inscription": "10/hour",
        "inscription_renvoi": "5/hour",
        "inscription_verifier": "30/hour",
        "inscription_activer": "10/hour",
        # La sonde est interrogée toutes les 2 s pendant 2 minutes : 60 appels
        # par activation, et il peut y en avoir plusieurs par poste.
        "inscription_etat": "300/hour",
        # Invitations collaborateurs
        "invitation_verifier": "30/hour",
        "invitation_accepter": "10/hour",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "CCD Digital — API Gestion de Chantier BTP",
    "DESCRIPTION": (
        "# Guide d'intégration Frontend — API CCD Digital\n\n"
        "Bienvenue sur la documentation interactive de l'API de gestion "
        "de chantiers BTP **CCD Digital**.\n\n"
        "### 1. Architecture Multi-Tenancy à Domaine Unique (Option A)\n"
        "- **Point d'accès unifié** : Toutes les requêtes (publiques et tenant) "
        "sont adressées au même domaine d'API (ex: `https://api.ccd-digital.ci` ou `http://localhost:8000`).\n"
        "- **Résolution automatique par JWT** : Pour les routes protégées des tenants "
        "(chantiers, finances, tiers, utilisateurs, etc.), le middleware résout automatiquement le schéma PostgreSQL "
        "de l'entreprise à partir du claim `schema` dans le jeton JWT Bearer, ou via l'en-tête `X-Tenant`.\n"
        "- **Routes Publiques** : L'inscription (`/api/v1/inscription/`), l'authentification "
        "(`/api/v1/auth/token/`), la santé (`/api/health/`) et les forfaits (`/api/v1/plans/`) "
        "s'exécutent sur le schéma public sans sous-domaine.\n\n"
        "### 2. Authentification JWT\n"
        "- Pour les routes protégées, transmettre le jeton d'accès dans l'en-tête HTTP : "
        "`Authorization: Bearer <access_token>`.\n"
        "- Durée de validité du jeton d'accès : **15 minutes**.\n"
        "- Le rafraîchissement s'effectue via `POST /api/v1/auth/token/refresh/` avec le "
        "jeton de renouvellement (valide 8 heures).\n"
        "- La déconnexion `POST /api/v1/auth/deconnexion/` révoque instantanément les jetons "
        "côté serveur dans le cache Redis.\n\n"
        "### 3. Conventions de Réponses et Gestion des Erreurs\n"
        "- Toutes les ressources renvoient du JSON strict (`Content-Type: application/json`).\n"
        "- Format standard des erreurs (4xx / 5xx) :\n"
        "```json\n"
        "{\n"
        '  "code": "permission_refusee",\n'
        '  "message": "Explication claire en français",\n'
        '  "details": {}\n'
        "}\n"
        "```\n"
        "- **Pagination** : Les endpoints de listing paginés renvoient un objet avec "
        "`{ count, next, previous, results }` (20 éléments par page).\n"
        "- **Devise** : Les montants monétaires stockés en base sont exprimés en centimes FCFA. "
        "Les serializers fournissent les méthodes de conversion `*_fcfa` en unités FCFA entières.\n"
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "StatutRapportEnum": "apps.core.enums.StatutRapport",
        "PlanCodeEnum": "apps.billing.models.Plan.Code",
        "RoleGlobalEnum": "apps.core.enums.RoleGlobal",
        "RoleTiersChoixEnum": "apps.core.enums.RoleTiersChoix",
    },
}

# Socle Commun §2.2 — 15 min pour l'accès, 8 h pour le renouvellement web.
# Le cas mobile (24 h) est traité par une vue dédiée, pas par ce réglage global.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=8),
    # Ces deux réglages sont volontairement à False : la rotation n'est plus
    # faite par SimpleJWT mais par `apps.accounts.services.renouvellement`,
    # avec la liste noire du cache (T-008 §3, décision S4).
    #
    # Les laisser à True serait exactement le défaut D-1 : `TokenRefreshView`
    # appelle `refresh.blacklist()` dans un `try/except AttributeError: pass`,
    # la méthode n'existe pas sans l'application `token_blacklist`, et deux
    # réglages parfaitement lisibles ne révoquent rien du tout.
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# À n'activer que si l'API doit volontairement être consommable depuis toute
# origine web. Les permissions applicatives restent contrôlées par le JWT.
from corsheaders.defaults import default_headers

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=_liste)

for _origine in [
    FRONTEND_URL.rstrip("/"),
    "https://app-chantier.soumafe.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]:
    if _origine and _origine not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_origine)

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.soumafe\.com$",
    r"^http://localhost:\d+$",
    r"^http://127\.0\.0\.1:\d+$",
]

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-request-id",
    "x-tenant",
]
CORS_EXPOSE_HEADERS = [
    "x-request-id",
]

# --------------------------------------------------------------------------
# Internationalisation — décision D6 : on stocke en UTC, sans exception.
# --------------------------------------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

FUSEAU_AFFICHAGE = config("FUSEAU_AFFICHAGE", default="Africa/Abidjan")
DEVISE = "XOF"  # FCFA BCEAO — seule devise du MVP (Socle §1.3)

# --------------------------------------------------------------------------
# Fichiers
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Barre initiale obligatoire : `default_storage.url()` la reprend telle quelle.
# Sans elle, la vignette d'un logo servie depuis `/tableau-de-bord` était
# résolue en `/tableau-de-bord/media/...` — une URL relative dans une
# application dont toutes les pages sont à des profondeurs différentes.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

TAILLE_MAX_FICHIER_MO = 50  # US-006 : refus 413 au-delà
PHOTOS_MAX_PAR_RAPPORT = 5  # RG-14

# --------------------------------------------------------------------------
# Cache et tâches asynchrones
# --------------------------------------------------------------------------
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TIMEZONE = FUSEAU_AFFICHAGE  # l'alerte de 17 h 30 est une heure locale
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = config("CELERY_TASK_EAGER_PROPAGATES", default=True, cast=bool)

# --------------------------------------------------------------------------
# Journalisation
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
}

# --------------------------------------------------------------------------
# CinetPay — Passerelle de paiement (Orange Money, Wave, MTN MoMo, Carte)
# --------------------------------------------------------------------------
CINETPAY_API_KEY = config("CINETPAY_API_KEY", default="")
CINETPAY_SITE_ID = config("CINETPAY_SITE_ID", default="")
CINETPAY_SECRET_KEY = config("CINETPAY_SECRET_KEY", default="")
CINETPAY_NOTIFY_URL = config("CINETPAY_NOTIFY_URL", default="")
CINETPAY_CHECKOUT_URL = config(
    "CINETPAY_CHECKOUT_URL", default="https://api-checkout.cinetpay.com/v2/payment"
)
CINETPAY_CHECK_URL = config(
    "CINETPAY_CHECK_URL", default="https://api-checkout.cinetpay.com/v2/payment/check"
)
