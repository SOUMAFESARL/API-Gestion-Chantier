from django.apps import AppConfig


class EntreprisesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.entreprises"
    verbose_name = "Entreprises clientes abonnées et cycle de vie de leur espace"

    def ready(self):
        import apps.entreprises.signals  # noqa
