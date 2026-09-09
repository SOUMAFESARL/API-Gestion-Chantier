from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.finance"
    verbose_name = "Budgets, bons de paiement, signatures, soldes intervenants, rejets de travaux"
