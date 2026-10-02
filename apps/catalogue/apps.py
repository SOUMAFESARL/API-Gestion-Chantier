from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CatalogueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalogue"
    verbose_name = _("Catalogue souverain des modules et permissions de la plateforme")
