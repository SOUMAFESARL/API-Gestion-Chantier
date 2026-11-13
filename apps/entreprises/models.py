import re
import uuid

from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower, Now
from django.utils import timezone

from apps.common.models import ModeleBase


class StatutEntreprise(models.TextChoices):
    ESSAI = 'ESSAI', 'Essai'
    ACTIVE = 'ACTIVE', 'Active'
    SUSPENDUE = 'SUSPENDUE', 'Suspendue'
    RESILIEE = 'RESILIEE', 'Résiliée'


class Entreprise(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, db_default=models.Func(function='gen_random_uuid'), editable=False)
    slug = models.SlugField(max_length=63, unique=True, db_comment='Identifiant lisible (D9, R-13). Ne nomme aucun schéma.')
    raison_sociale = models.CharField(max_length=200)
    nom_commercial = models.CharField(max_length=200, blank=True, default='', db_default='')
    pays = models.CharField(max_length=2, default='CI', db_default='CI')
    ville = models.CharField(max_length=100, blank=True, default='', db_default='')
    adresse = models.TextField(blank=True, default='', db_default='')
    rccm = models.CharField(max_length=50, blank=True, default='', db_default='')
    nif = models.CharField(max_length=50, blank=True, default='', db_default='')
    logo = models.CharField(max_length=500, blank=True, default='', db_default='', db_comment='Clé de stockage variante densité 2 (rendu par défaut).')
    logo_1x = models.CharField(max_length=500, blank=True, default='', db_default='', db_comment='Clé de stockage densité 1 — le nom ne dit plus la taille.')
    logo_original = models.CharField(max_length=500, blank=True, default='', db_default='')
    couleur_primaire = models.CharField(max_length=7, default='#D4652A', db_default='#D4652A', validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$', 'Utilisez une couleur hexadécimale, par exemple #D4652A.')])
    email_contact = models.EmailField(max_length=254)
    telephone_contact = models.CharField(max_length=20, blank=True, default='', db_default='')
    statut = models.CharField(max_length=20, choices=StatutEntreprise.choices, default=StatutEntreprise.ESSAI, db_default='ESSAI')
    date_inscription = models.DateTimeField(default=timezone.now, db_default=Now(), editable=False)

    class Meta:
        db_table = 'entreprise'
        db_table_comment = "L'entreprise BTP abonnée — D9 : schéma unique."
        indexes = [models.Index(fields=['statut'], name='idx_entreprise_statut')]
        constraints = [
            models.CheckConstraint(condition=models.Q(statut__in=StatutEntreprise.values), name='chk_entreprise_statut'),
            models.UniqueConstraint(Lower('email_contact'), name='uq_entreprise_email_contact'),
        ]

    def save(self, *args, **kwargs):
        self.raison_sociale = re.sub(r'\s+', ' ', self.raison_sociale.strip())
        self.email_contact = self.email_contact.strip().lower()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.raison_sociale


class LibelleTelephoneEntreprise(models.TextChoices):
    MOBILE = 'MOBILE', 'Mobile'
    FIXE = 'FIXE', 'Fixe'
    WHATSAPP = 'WHATSAPP', 'WhatsApp'
    STANDARD = 'STANDARD', 'Standard'
    COMPTABILITE = 'COMPTABILITE', 'Comptabilité'
    AUTRE = 'AUTRE', 'Autre'


class TelephoneEntreprise(ModeleBase):
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='telephones', db_index=False)
    libelle = models.CharField(max_length=20, choices=LibelleTelephoneEntreprise.choices)
    nom = models.CharField(max_length=60, blank=True, default='', db_default='')
    numero = models.CharField(max_length=16, validators=[RegexValidator(r'^\+[1-9][0-9]{7,14}$', 'Utilisez un numéro au format E.164, par exemple +2250700000000.')])
    est_principal = models.BooleanField(default=False, db_default=False)
    ordre = models.PositiveSmallIntegerField(default=0, db_default=0)

    class Meta:
        db_table = 'telephone_entreprise'
        ordering = ['ordre', 'cree_le', 'id']
        indexes = [models.Index(fields=['entreprise'], name='idx_telephone_entreprise')]
        constraints = [
            models.CheckConstraint(condition=models.Q(libelle__in=LibelleTelephoneEntreprise.values), name='chk_telephone_libelle'),
            models.CheckConstraint(condition=models.Q(numero__regex=r'^\+[1-9][0-9]{7,14}$'), name='chk_telephone_entreprise_e164'),
            models.UniqueConstraint(fields=['entreprise'], condition=models.Q(est_principal=True, supprime_le__isnull=True), name='uq_telephone_entreprise_principal'),
            models.UniqueConstraint(fields=['entreprise', 'numero'], condition=models.Q(supprime_le__isnull=True), name='uq_telephone_entreprise_numero'),
        ]

    def __str__(self):
        return f'{self.get_libelle_display()} : {self.numero}'
