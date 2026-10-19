from django.apps import AppConfig


class ChantierConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chantier"
    verbose_name = "Journal de chantier : rapports journaliers, production, photos, blocages"

    def ready(self):
        from apps.chantier import signals  # noqa: F401
