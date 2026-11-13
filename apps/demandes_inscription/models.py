import re

from django.db import models
from django.db.models.functions import Lower

from apps.common.models import ModeleBase


class StatutDemandeInscription(models.TextChoices):
    EN_ATTENTE = 'EN_ATTENTE', 'En attente'
    A_VALIDER = 'A_VALIDER', 'À valider'
    REFUSEE = 'REFUSEE', 'Refusée'
    PROVISIONNEMENT = 'PROVISIONNEMENT', 'Provisionnement'
    ACTIVEE = 'ACTIVEE', 'Activée'
    ECHEC = 'ECHEC', 'Échec'
    ABANDONNEE = 'ABANDONNEE', 'Abandonnée'


STATUTS_RESERVES = ('EN_ATTENTE', 'A_VALIDER', 'PROVISIONNEMENT')


class DemandeInscription(ModeleBase):
    raison_sociale = models.CharField(max_length=200)
    pays = models.CharField(max_length=2)
    email = models.EmailField(max_length=254)
    slug_reserve = models.SlugField(max_length=40, allow_unicode=True, db_comment='40 et non 63 : limite PostgreSQL en octets + accents (T-020 §2.5).')
    empreinte = models.CharField(max_length=64, unique=True)
    expire_le = models.DateTimeField()
    utilise_le = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=StatutDemandeInscription.choices, default=StatutDemandeInscription.EN_ATTENTE, db_default='EN_ATTENTE')
    nom = models.CharField(max_length=100, blank=True, default='', db_default='')
    prenom = models.CharField(max_length=100, blank=True, default='', db_default='')
    password = models.CharField(max_length=128, blank=True, default='', db_default='', db_comment='Haché, vidé au provisionnement, jamais transporté dans un message Celery.')
    decision_par = models.UUIDField(null=True, blank=True)
    decision_le = models.DateTimeField(null=True, blank=True)
    motif_refus = models.TextField(blank=True, default='', db_default='')
    cgu_version = models.CharField(max_length=20, blank=True, default='', db_default='')
    cgu_acceptees_le = models.DateTimeField(null=True, blank=True)
    cgu_adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    entreprise = models.ForeignKey('entreprises.Entreprise', on_delete=models.RESTRICT, null=True, blank=True, related_name='demandes_inscription')

    class Meta:
        db_table = 'demande_inscription'
        db_table_comment = 'Entreprise pas encore créée — MLD §4.8. Aucun schéma créé avant activation.'
        indexes = [models.Index(fields=['-cree_le'], name='idx_demande_cree_le')]
        constraints = [
            models.CheckConstraint(condition=models.Q(statut__in=StatutDemandeInscription.values), name='chk_demande_statut'),
            models.UniqueConstraint(fields=['slug_reserve'], condition=models.Q(statut__in=STATUTS_RESERVES), name='uq_demande_slug'),
            models.UniqueConstraint(Lower('email'), condition=models.Q(statut__in=STATUTS_RESERVES), name='uq_demande_email_attente'),
        ]

    def save(self, *args, **kwargs):
        self.raison_sociale = re.sub(r'\s+', ' ', self.raison_sociale.strip())
        self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.raison_sociale
