"""Le relevé quotidien de l'avancement, pour la courbe en S (décision du 30/10/2026).

Chaque nuit, la plateforme note l'avancement physique et temporel du projet et des cases suivies
(niveaux cochés « alerter », à défaut les racines). La courbe du réel se lit dans ces relevés ;
celle du prévu se calcule à partir des dates et des montants.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import PourcentageField
from apps.core.models import ModeleBase

__all__ = ["PointAvancement"]


class PointAvancement(ModeleBase):
    projet = models.ForeignKey(
        "projets.Projet", on_delete=models.CASCADE, related_name="points_avancement"
    )
    # Vide : le projet entier.
    element = models.ForeignKey(
        "projets.Element",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="points_avancement",
    )
    jour = models.DateField(_("jour"))
    physique = PourcentageField(_("avancement physique (%)"), null=True, blank=True)
    temporel = PourcentageField(_("avancement temporel (%)"), null=True, blank=True)

    class Meta:
        db_table = "point_avancement"
        ordering = ["projet", "element", "jour"]
        constraints = [
            models.UniqueConstraint(
                fields=["projet", "jour"],
                condition=models.Q(element__isnull=True),
                name="uq_point_avancement_projet_jour",
            ),
            models.UniqueConstraint(
                fields=["element", "jour"],
                condition=models.Q(element__isnull=False),
                name="uq_point_avancement_element_jour",
            ),
        ]
