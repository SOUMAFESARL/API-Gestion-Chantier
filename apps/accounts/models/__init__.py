"""Application « accounts » — comptes et droits.

Présente dans **les deux listes** d'applications (écart E1, voir README) :
  · schéma `public` : le personnel CCD Digital (super admin, support)
  · schéma tenant   : les utilisateurs de l'entreprise cliente

Entités MCD : Utilisateur, Invitation, Appareil  (MCD §5.1)
Plus `JetonReinitialisation` — contrat de réinitialisation §2.
"""

import hashlib
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.core.models import ModeleBase

from .role import Role, RoleModulePermission

__all__ = [
    "Appareil",
    "Invitation",
    "JetonReinitialisation",
    "Role",
    "RoleModulePermission",
    "Utilisateur",
]

TENTATIVES_MAX = 5  # Socle Commun §2.1 — blocage après 5 échecs consécutifs

# **Il n'y a pas de durée de blocage.** Le code en portait une — quinze minutes,
# au terme desquelles le compte se rouvrait seul — et c'était une **seconde
# sortie que le Socle §2.1 ne prévoit pas** : il dit « déblocage par email de
# réinitialisation *uniquement* », et le marque obligatoire.
#
# *L'argument de l'écart était sérieux : sur un chantier, l'accès à une boîte
# mail n'est pas acquis. Il n'a pas suffi.* Arbitrage Q1 de T-008 §6.3 : la
# durée est supprimée, et deux choses l'amortissent — le blocage n'arrive
# qu'après cinq échecs consécutifs, et `manage.py debloquer_compte` rouvre un
# compte en une seconde. Ce n'est pas une troisième porte au sens du Socle :
# c'est un geste d'exploitation, qui exige un accès au serveur.

# Validité d'un lien de réinitialisation — contrat §2.2 et workflow T2.
DUREE_JETON_REINITIALISATION = timedelta(hours=1)


class GestionnaireUtilisateur(BaseUserManager):
    """Manager d'authentification, filtrant les comptes supprimés (RG-06).

    Un compte supprimé logiquement ne peut plus s'authentifier : c'est le
    filtrage de ce manager qui le garantit, pas un contrôle dans la vue.
    """

    def get_queryset(self):
        return super().get_queryset().filter(supprime_le__isnull=True)

    def _creer(self, email, mot_de_passe, **extra):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        email = self.normalize_email(email).lower()
        utilisateur = self.model(email=email, **extra)
        utilisateur.set_password(mot_de_passe)
        utilisateur.save(using=self._db)
        return utilisateur

    def create_user(self, email, password=None, **extra):
        extra.setdefault("statut", StatutUtilisateur.ACTIF)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._creer(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role_global", RoleGlobal.ADMIN)
        extra.setdefault("statut", StatutUtilisateur.ACTIF)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("Un super-utilisateur doit avoir is_staff et is_superuser à True.")
        return self._creer(email, password, **extra)


class Utilisateur(ModeleBase, AbstractBaseUser, PermissionsMixin):
    """Une personne qui se connecte au produit.

    Niveau 1 du contrôle d'accès (Socle Commun §2.3) : `role_global` dit ce
    que la personne a le droit de faire. Le niveau 2 — sur quels projets —
    est porté par `projets.AffectationProjet`.
    """

    email = models.EmailField(_("email"), max_length=254)
    nom = models.CharField(_("nom"), max_length=100)
    prenom = models.CharField(_("prénom"), max_length=100, blank=True)
    telephone = models.CharField(_("téléphone"), max_length=20, blank=True)
    avatar = models.ImageField(
        _("avatar"),
        upload_to="avatars/%Y/%m/",
        null=True,
        blank=True,
        help_text=_("Photo de profil de l'utilisateur (format image, max 2 Mo)."),
    )

    role_global = models.CharField(
        _("rôle global"),
        max_length=5,
        choices=RoleGlobal.choices,
        default=RoleGlobal.VISITEUR,
        db_index=True,
    )
    role_personnalise = models.ForeignKey(
        "accounts.Role",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="utilisateurs",
        verbose_name=_("rôle personnalisé"),
    )
    statut = models.CharField(
        _("statut"),
        max_length=20,
        choices=StatutUtilisateur.choices,
        default=StatutUtilisateur.INVITE,
        db_index=True,
    )

    tentatives_echouees = models.PositiveSmallIntegerField(_("tentatives échouées"), default=0)
    # `bloque_le`, et non `bloque_jusqu_a` : **quand**, pas *jusqu'à quand*.
    # Le champ change de sens, pas seulement de nom — T-008 §6.3.
    bloque_le = models.DateTimeField(_("bloqué le"), null=True, blank=True)
    double_authentification = models.BooleanField(_("double authentification"), default=False)

    # Vrai quand le mot de passe courant a été posé par quelqu'un d'autre que
    # son titulaire — réinitialisation par un administrateur, mot de passe
    # généré au provisioning. Le client le lit dans le profil renvoyé à la
    # connexion (contrat d'API §4.2) et impose le changement avant d'ouvrir
    # l'application.
    #
    # Aucun parcours ne le passe à `true` aujourd'hui : l'invitation et la
    # réinitialisation par email font toutes deux choisir le mot de passe à son
    # titulaire. Les candidats sont DEV-2 et DEV-8.
    doit_changer_mot_de_passe = models.BooleanField(
        _("doit changer son mot de passe"), default=False
    )

    langue = models.CharField(_("langue"), max_length=5, default="fr")
    is_owner = models.BooleanField(_("propriétaire / fondateur"), default=False)

    # Requis par l'administration Django.
    is_staff = models.BooleanField(_("accès à l'administration"), default=False)
    is_active = models.BooleanField(_("actif"), default=True)

    objects = GestionnaireUtilisateur()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nom"]

    class Meta:
        db_table = "utilisateur"
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")
        ordering = ["nom", "prenom"]
        constraints = [
            # Unicité **partielle** : une adresse libérée par une suppression
            # logique doit pouvoir resservir (MLD §7.2).
            models.UniqueConstraint(
                models.functions.Lower("email"),
                condition=models.Q(supprime_le__isnull=True),
                name="uq_utilisateur_email",
            )
        ]

    def __str__(self) -> str:
        return f"{self.nom} {self.prenom}".strip() or self.email

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}".strip()

    @property
    def initiales(self) -> str:
        p = self.prenom[0].upper() if self.prenom else ""
        n = self.nom[0].upper() if self.nom else ""
        return f"{p}{n}" or (self.email[0].upper() if self.email else "?")

    @property
    def avatar_url(self) -> str | None:
        if self.avatar and hasattr(self.avatar, "url"):
            return self.avatar.url
        return None

    @property
    def is_dg(self) -> bool:
        return self.role_global == RoleGlobal.DIRECTEUR_GENERAL or self.is_owner

    @property
    def est_bloque(self) -> bool:
        """Bloqué **tant que rien ne l'a débloqué** — aucune échéance.

        *Le piège que T-008 §6.3 signale : renommer le champ sans retoucher
        cette ligne aurait laissé une comparaison entre l'horodatage du blocage
        et l'heure courante — et plus aucun compte n'aurait jamais été bloqué.*
        """
        return self.bloque_le is not None

    @property
    def tentatives_restantes(self) -> int:
        """Essais qu'il reste avant le blocage. Affiché à l'écran (maquette M1)."""
        return max(0, TENTATIVES_MAX - self.tentatives_echouees)

    def clean(self):
        super().clean()
        if self.pk:
            initial = Utilisateur.tous_objets.filter(pk=self.pk).first()
            if initial and initial.is_owner:
                from django.core.exceptions import ValidationError

                if not self.is_owner:
                    raise ValidationError(_("Le statut de Propriétaire est immuable."))
                if self.statut == StatutUtilisateur.DESACTIVE:
                    raise ValidationError(
                        _("Le compte du Propriétaire ne peut pas être désactivé.")
                    )
                if self.role_global not in (RoleGlobal.DIRECTEUR_GENERAL, RoleGlobal.ADMIN):
                    raise ValidationError(
                        _("Le rôle du Propriétaire doit être Directeur Général ou Administrateur.")
                    )

    def delete(self, using=None, keep_parents=False, utilisateur=None):
        if self.is_owner:
            from django.core.exceptions import ValidationError

            raise ValidationError(
                _("Le compte du Directeur Général / Propriétaire ne peut pas être supprimé.")
            )
        super().delete(using=using, keep_parents=keep_parents, utilisateur=utilisateur)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def enregistrer_echec_connexion(self) -> None:
        """Socle Commun §2.1 — blocage après 5 échecs consécutifs.

        Le blocage pose `bloque_le` et **ne touche pas au statut** :
        `DESACTIVE` signifie « désactivé par un administrateur » (workflow T5),
        avec une tout autre sortie — la réactivation par l'admin. Confondre les
        deux ferait qu'une personne ayant mal tapé son mot de passe cinq fois
        apparaîtrait, dans la liste des utilisateurs, comme un salarié parti.
        """
        self.tentatives_echouees += 1
        champs = ["tentatives_echouees", "modifie_le"]

        if self.tentatives_echouees >= TENTATIVES_MAX:
            self.bloque_le = timezone.now()
            champs.append("bloque_le")

        self.save(update_fields=champs)

    def reinitialiser_echecs(self) -> None:
        if self.tentatives_echouees or self.bloque_le:
            self.tentatives_echouees = 0
            self.bloque_le = None
            self.save(update_fields=["tentatives_echouees", "bloque_le", "modifie_le"])


class Invitation(ModeleBase):
    """Un compte créé mais pas encore activé — workflow T1, lien valable 72 h (MLD §5.2)."""

    class Statut(models.TextChoices):
        ENVOYEE = "ENVOYEE", _("Envoyée")
        ACCEPTEE = "ACCEPTEE", _("Acceptée")
        EXPIREE = "EXPIREE", _("Expirée")
        REVOQUEE = "REVOQUEE", _("Révoquée")

    email = models.EmailField(_("email"), max_length=254)
    nom = models.CharField(_("nom"), max_length=100, blank=True, default="")
    role_propose = models.CharField(_("rôle proposé"), max_length=5, choices=RoleGlobal.choices)
    empreinte = models.CharField(_("empreinte"), max_length=64, unique=True, db_index=True)
    emetteur = models.ForeignKey(
        Utilisateur,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="invitations_emises",
        verbose_name=_("émetteur"),
    )
    expire_le = models.DateTimeField(_("expire le"))
    utilise_le = models.DateTimeField(_("utilisé le"), null=True, blank=True)
    statut = models.CharField(
        _("statut"), max_length=20, choices=Statut.choices, default=Statut.ENVOYEE
    )

    class Meta:
        db_table = "invitation"
        verbose_name = _("invitation")
        verbose_name_plural = _("invitations")
        ordering = ["-cree_le"]

    def __str__(self) -> str:
        return f"{self.email} ({self.nom or 'sans nom'}) — {self.get_statut_display()}"

    @property
    def est_expiree(self) -> bool:
        return self.expire_le <= timezone.now()

    @property
    def est_utilisable(self) -> bool:
        return (
            self.utilise_le is None and self.statut == self.Statut.ENVOYEE and not self.est_expiree
        )

    @staticmethod
    def empreinte_de(jeton) -> str:
        """SHA-256 hexadécimal — la seule forme qui entre en base (décision R-40, MLD §5.2)."""
        return hashlib.sha256(str(jeton).encode()).hexdigest()


class Appareil(ModeleBase):
    """Un téléphone ou un navigateur connu de l'utilisateur.

    Porte le jeton FCM utilisé pour les notifications push (US-056).
    """

    class Type(models.TextChoices):
        WEB = "WEB", _("Navigateur web")
        ANDROID = "ANDROID", _("Android")
        IOS = "IOS", _("iOS")

    utilisateur = models.ForeignKey(
        Utilisateur, on_delete=models.RESTRICT, related_name="appareils"
    )
    type_appareil = models.CharField(_("type"), max_length=20, choices=Type.choices)
    jeton_push = models.CharField(_("jeton push FCM"), max_length=255, blank=True)
    identifiant_materiel = models.CharField(_("identifiant matériel"), max_length=100, blank=True)
    derniere_activite = models.DateTimeField(_("dernière activité"), null=True, blank=True)

    class Meta:
        db_table = "appareil"
        verbose_name = _("appareil")
        verbose_name_plural = _("appareils")
        ordering = ["-derniere_activite"]

    def __str__(self) -> str:
        return f"{self.get_type_appareil_display()} — {self.utilisateur}"


class JetonReinitialisation(ModeleBase):
    """Un lien de réinitialisation de mot de passe — contrat §2.

    **Ce qui est stocké est l'empreinte, jamais le jeton** (décision J2). Un
    jeton de réinitialisation vaut un mot de passe pendant une heure : une table
    qui les contient en clair est une table de mots de passe. Le jeton n'existe
    qu'en mémoire, le temps de composer l'email — il n'est ni journalisé, ni
    renvoyé dans une réponse, ni conservé.

    **Le jeton est stocké et non calculé** (décision J1). Le générateur sans
    état de Django ne sait ni marquer un jeton « consommé », ni invalider le
    précédent quand M6 propose « Renvoyer l'email », ni alimenter le journal
    d'audit qu'impose le Socle §2.4.

    **La table vit dans le schéma du client** (décision J3) : elle porte une clé
    étrangère vers `utilisateur`, qui n'existe pas dans `public` pour les
    comptes d'un tenant. C'est la raison qui avait déjà écarté les tables de
    liste noire de SimpleJWT.
    """

    class Motif(models.TextChoices):
        OUBLI = "OUBLI", _("Mot de passe oublié")
        BLOCAGE = "BLOCAGE", _("Compte bloqué")

    utilisateur = models.ForeignKey(
        Utilisateur, on_delete=models.RESTRICT, related_name="jetons_reinitialisation"
    )
    empreinte = models.CharField(_("empreinte"), max_length=64, unique=True, db_index=True)
    motif = models.CharField(_("motif"), max_length=20, choices=Motif.choices)
    expire_le = models.DateTimeField(_("expire le"))
    utilise_le = models.DateTimeField(_("utilisé le"), null=True, blank=True)
    invalide_le = models.DateTimeField(_("invalidé le"), null=True, blank=True)
    ip_demande = models.GenericIPAddressField(_("IP de la demande"), null=True, blank=True)

    class Meta:
        db_table = "jeton_reinitialisation"
        verbose_name = _("jeton de réinitialisation")
        verbose_name_plural = _("jetons de réinitialisation")
        ordering = ["-cree_le"]

    def __str__(self) -> str:
        return f"{self.utilisateur.email} — {self.get_motif_display()}"

    @property
    def est_utilisable(self) -> bool:
        """**Trois causes d'inutilisabilité, un seul point de décision.**

        Les répartir dans les vues garantirait qu'un des trois cas serait
        oublié quelque part.
        """
        return (
            self.utilise_le is None and self.invalide_le is None and self.expire_le > timezone.now()
        )

    @staticmethod
    def empreinte_de(jeton) -> str:
        """SHA-256 hexadécimal — la seule forme qui entre en base.

        La recherche se fait par empreinte : en temps constant sur un index
        unique, sans balayage, et sans qu'une fuite de la table ne donne un
        seul jeton utilisable.
        """
        return hashlib.sha256(str(jeton).encode()).hexdigest()
