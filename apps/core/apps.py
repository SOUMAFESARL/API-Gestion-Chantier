from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Socle technique : modèle de base, suppression logique, permissions, formats"

    def ready(self):
        from apps.core import checks  # noqa: F401 — enregistre les vérifications système
