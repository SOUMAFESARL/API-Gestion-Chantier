"""Application « tenants » — schéma `public`.

Une ligne d'`Entreprise` = un schéma PostgreSQL. C'est la matérialisation de
la décision D1 : l'isolation entre clients n'est pas une colonne que l'on
filtre, c'est une frontière que l'on ne peut pas franchir.

Entités MCD : Entreprise, Domaine  (MCD §4.1)
Plus `DemandeInscription` — MLD §4.8, contrat d'inscription T-021.
"""

import hashlib
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_tenants.models import DomainMixin, TenantMixin

from apps.core.enums import StatutEntreprise
from apps.core.models import ModeleBase

__all__ = ["DemandeInscription", "Domaine", "Entreprise"]

# Validité du lien d'activation — MLD §4.8 et workflow T1.
DUREE_LIEN_ACTIVATION = timedelta(hours=48)


class Entreprise(TenantMixin):
    """L'entreprise BTP abonnée. Porte son schéma PostgreSQL.

    `TenantMixin` fournit `schema_name` et la création du schéma.
    Aucune donnée métier ne vit ici : elle est dans le schéma nommé par
    `schema_name`.
    """

    # Le schéma est créé dès l'enregistrement de la ligne, dans la même
    # transaction (US-014 : création transactionnelle tenant + schéma).
    auto_create_schema = True
    auto_drop_schema = False  # RG-06 : on ne détruit jamais un schéma client

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    raison_sociale = models.CharField(_("raison sociale"), max_length=200)
    nom_commercial = models.CharField(_("nom commercial"), max_length=200, blank=True)

    pays = models.CharField(
        _("pays"),
        max_length=2,
        default="CI",
        help_text=_("Code ISO. Détermine le calendrier des jours fériés applicable."),
    )
    ville = models.CharField(_("ville"), max_length=100, blank=True)
    adresse = models.TextField(_("adresse"), blank=True)

    rccm = models.CharField(_("RCCM"), max_length=50, blank=True)
    nif = models.CharField(_("NIF"), max_length=50, blank=True)
    # Les trois variantes du logo, sous forme de **clés de stockage** — pas
    # d'URL. Le service d'images produit un 24 px et un 48 px taillés pour les
    # deux densités d'écran de la barre d'application, plus le master recadré ;
    # les trois étaient calculés et deux étaient jetés, si bien que la barre
    # affichait le 48 dans un emplacement de 24 et le laissait rééchantillonner
    # au navigateur. L'URL se calcule à la lecture (`EntrepriseSerializer`) :
    # une URL S3 est signée et périme.
    logo = models.CharField(
        _("logo"),
        max_length=500,
        blank=True,
        help_text=_("Clé de stockage de la variante densité 2 — le rendu par défaut."),
    )
    # `logo_1x`, et non `logo_24` : **le nom ne dit plus la taille.**
    #
    # *Il la disait, et la taille a changé — de 24 px carrés à 32 px de haut à
    # forme libre. Une colonne qui porte une valeur dans son nom oblige à une
    # migration à chaque réglage, ou ment. C'est la leçon de `bloque_jusqu_a`.*
    logo_1x = models.CharField(_("logo, densité 1"), max_length=500, blank=True)
    logo_original = models.CharField(_("logo original"), max_length=500, blank=True)
    couleur_primaire = models.CharField(
        _("couleur primaire"),
        max_length=7,
        blank=True,
        default="#D4652A",
        help_text=_("Code hexadécimal de la couleur primaire pour le white-label."),
    )

    email_contact = models.EmailField(_("email de contact"))
    telephone_contact = models.CharField(_("téléphone de contact"), max_length=20, blank=True)

    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=StatutEntreprise.choices,
        default=StatutEntreprise.ESSAI,
        db_index=True,
    )
    date_inscription = models.DateTimeField(_("date d'inscription"), auto_now_add=True)

    class Meta:
        db_table = "entreprise_cliente"
        verbose_name = _("entreprise cliente")
        verbose_name_plural = _("entreprises clientes")
        ordering = ["raison_sociale"]
        constraints = [
            models.UniqueConstraint(
                models.functions.Lower("email_contact"),
                name="uq_entreprise_email_contact",
            )
        ]

    def save(self, *args, **kwargs):
        if self.raison_sociale:
            self.raison_sociale = " ".join(self.raison_sociale.strip().split())
        if self.email_contact:
            self.email_contact = self.email_contact.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.raison_sociale} ({self.schema_name})"


class Domaine(DomainMixin):
    """Le sous-domaine par lequel une entreprise atteint le produit.

    En développement : `soumafe.localhost`, résolu vers 127.0.0.1 par le
    navigateur, sans toucher au fichier hosts.
    """

    class Meta:
        db_table = "domaine"
        verbose_name = _("domaine")
        verbose_name_plural = _("domaines")

    def __str__(self) -> str:
        return self.domain


class DemandeInscription(ModeleBase):
    """Une entreprise **qui n'existe pas encore** — MLD §4.8.

    Entre le formulaire public et le clic sur le lien d'activation, **aucun
    schéma n'est créé** et aucune donnée client n'est enregistrée ailleurs
    qu'ici. C'est ce que promet l'écran du lien expiré : « aucun espace n'a été
    créé, vous pouvez recommencer avec la même adresse ».

    **L'identifiant vient du client** (conventions A7). Un double-clic sur
    « Créer mon compte » rejoue la même requête et ne crée pas deux demandes.
    """

    class Statut(models.TextChoices):
        """Le cycle de vie d'une demande.

        **Le MLD §4.8 n'en liste que trois** — `EN_ATTENTE`, `ACTIVEE`,
        `ABANDONNEE`. Le contrat d'inscription §5 en exige un quatrième :
        l'effet 3 de l'activation fait passer la demande à `PROVISIONNEMENT`,
        et §7.1 doit pouvoir répondre `ECHEC` à la sonde de l'écran d'attente.

        Les deux documents divergent, et c'est le contrat qui décrit le
        parcours réel : sans état intermédiaire, une demande activée dont le
        provisionnement échoue serait indiscernable d'une demande jamais
        ouverte. **Le MLD est à mettre à jour** — écart reporté.
        """

        EN_ATTENTE = "EN_ATTENTE", _("En attente d'activation")
        A_VALIDER = "A_VALIDER", _("En attente de validation du super admin")
        REFUSEE = "REFUSEE", _("Refusee")
        PROVISIONNEMENT = "PROVISIONNEMENT", _("Provisionnement en cours")
        ACTIVEE = "ACTIVEE", _("Activée")
        ECHEC = "ECHEC", _("Provisionnement en échec")
        ABANDONNEE = "ABANDONNEE", _("Abandonnée")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    raison_sociale = models.CharField(_("raison sociale"), max_length=200)
    pays = models.CharField(_("pays"), max_length=2)
    email = models.EmailField(_("email"), max_length=254)

    # 40 et non 63 : un identifiant PostgreSQL se tronque à 63 **octets**, et
    # une raison sociale accentuée en consomme deux par lettre — T-020 §2.5.
    slug_reserve = models.CharField(_("slug réservé"), max_length=40)

    # Le jeton de 48 h ne vit qu'en mémoire, le temps de composer l'email.
    empreinte = models.CharField(_("empreinte"), max_length=64, unique=True, db_index=True)
    expire_le = models.DateTimeField(_("expire le"))
    utilise_le = models.DateTimeField(_("utilisée le"), null=True, blank=True)

    statut = models.CharField(
        _("statut"), max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE
    )

    nom = models.CharField(_("nom"), max_length=100, blank=True)
    prenom = models.CharField(_("prénom"), max_length=100, blank=True)

    # **La colonne qu'on aimerait ne pas avoir** — MLD §4.8. Le mot de passe est
    # saisi dans `public`, alors que le compte qui le portera vivra dans un
    # schéma qui n'existe pas encore. Il est **haché**, vidé dès le
    # provisionnement, et **jamais transporté dans un message Celery** : un
    # message traverse Redis, s'y attarde et s'affiche en supervision.
    mot_de_passe_transitoire = models.CharField(
        _("mot de passe transitoire"), max_length=128, blank=True
    )
    decision_par = models.UUIDField(null=True, blank=True)
    decision_le = models.DateTimeField(null=True, blank=True)
    motif_refus = models.TextField(blank=True)

    cgu_version = models.CharField(_("version des CGU"), max_length=20)
    cgu_acceptees_le = models.DateTimeField(_("CGU acceptées le"))
    cgu_adresse_ip = models.GenericIPAddressField(_("IP d'acceptation"), null=True, blank=True)

    entreprise = models.ForeignKey(
        "tenants.Entreprise",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="demandes",
    )

    class Meta:
        db_table = "demande_inscription"
        verbose_name = _("demande d'inscription")
        verbose_name_plural = _("demandes d'inscription")
        ordering = ["-cree_le"]
        constraints = [
            # La réservation du slug ne vaut **que le temps de l'attente** :
            # une demande abandonnée ne doit pas confisquer un nom pour
            # toujours — MLD §4.8.
            models.UniqueConstraint(
                fields=["slug_reserve"],
                condition=models.Q(statut__in=["EN_ATTENTE", "A_VALIDER", "PROVISIONNEMENT"]),
                name="uq_demande_slug",
            ),
            # Deux demandes avec le même email ne peuvent
            # pas être simultanément en attente d'activation.
            models.UniqueConstraint(
                models.functions.Lower("email"),
                condition=models.Q(statut__in=["EN_ATTENTE", "A_VALIDER", "PROVISIONNEMENT"]),
                name="uq_demande_email_attente",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.raison_sociale:
            self.raison_sociale = " ".join(self.raison_sociale.strip().split())
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.raison_sociale} <{self.email}> — {self.get_statut_display()}"

    @property
    def est_utilisable(self) -> bool:
        return (
            self.utilise_le is None
            and self.statut == self.Statut.EN_ATTENTE
            and self.expire_le > timezone.now()
        )

    @staticmethod
    def empreinte_de(jeton) -> str:
        """SHA-256 hexadécimal — la seule forme qui entre en base."""
        return hashlib.sha256(str(jeton).encode()).hexdigest()
