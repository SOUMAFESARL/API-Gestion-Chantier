from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenants"
    verbose_name = "Entreprises clientes abonnées et cycle de vie de leur schéma PostgreSQL"

    def ready(self):
        try:
            import sys
            # Ne pas exécuter pendant les vérifications, tests ou migrations
            if any(cmd in sys.argv for cmd in ["check", "test", "pytest", "makemigrations", "migrate"]):
                return
            from django.core.management.color import color_style
            from apps.tenants.management.commands.provisionner_inscriptions import (
                _purger_comptes_test_temporaire,
            )

            _purger_comptes_test_temporaire(sys.stdout, color_style())
        except Exception:
            pass
