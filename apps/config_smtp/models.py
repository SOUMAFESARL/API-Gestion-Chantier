from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import ModeleBase


class ConfigSMTP(ModeleBase):
    nom = models.CharField(max_length=100)
    hote = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=587, db_default=587, validators=[MinValueValidator(1), MaxValueValidator(65535)])
    utilisateur = models.CharField(max_length=254, blank=True, default='', db_default='')
    mot_de_passe = models.CharField(max_length=500, blank=True, default='', db_default='')
    email_expediteur = models.EmailField(max_length=254)
    nom_expediteur = models.CharField(max_length=100, blank=True, default='', db_default='')
    utiliser_tls = models.BooleanField(default=True, db_default=True)
    utiliser_ssl = models.BooleanField(default=False, db_default=False)
    delai_connexion = models.PositiveIntegerField(default=15, db_default=15, validators=[MinValueValidator(1)])
    est_active = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'config_smtp'
        verbose_name = 'Configuration SMTP'
        verbose_name_plural = 'Configurations SMTP'
        constraints = [
            models.CheckConstraint(condition=~models.Q(utiliser_tls=True, utiliser_ssl=True), name='chk_smtp_tls_ssl'),
            models.CheckConstraint(condition=models.Q(port__gte=1, port__lte=65535), name='chk_smtp_port'),
            models.CheckConstraint(condition=models.Q(delai_connexion__gte=1), name='chk_smtp_delai'),
            models.UniqueConstraint(fields=['est_active'], condition=models.Q(est_active=True, supprime_le__isnull=True), name='uq_smtp_configuration_active'),
        ]

    def __str__(self):
        return self.nom
