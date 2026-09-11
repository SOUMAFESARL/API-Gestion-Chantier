"""Application « billing » — plans et abonnements, schéma `public`.

Entités MCD : Plan, Abonnement  ·  Tables MLD §4.3 et §4.4

Elles vivent dans `public` et **jamais** dans un schéma client : ce sont les
tables de l'éditeur. Un client qui pourrait lire son propre abonnement pourrait
aussi le modifier — le rôle applicatif est le même.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleBase

from .facture import Facture
from .paiement import PaiementAbonnement

__all__ = ["Abonnement", "Facture", "PaiementAbonnement", "Plan", "RelanceEssai"]

# Durée de l'essai gratuit — 14 jours en plan Maître d'Œuvre, MLD §4.4 et parcours T-025.
JOURS_ESSAI = 14


class Plan(ModeleBase):
    """Un niveau d'abonnement — MLD §4.3.

    Forfaits BTP :
    - Bâtisseur (BATISSEUR) : maîtres d'œuvre indépendants, petits chantiers.
    - Maître d'Œuvre (MAITRE_OEUVRE) : PME du BTP, plusieurs équipes et chantiers.
    - Promoteur (PROMOTEUR) : grands comptes, entreprises générales, illimité.
    """

    class Code(models.TextChoices):
        BATISSEUR = "BATISSEUR", _("Bâtisseur")
        MAITRE_OEUVRE = "MAITRE_OEUVRE", _("Maître d'Œuvre")
        PROMOTEUR = "PROMOTEUR", _("Promoteur")
        # Rétrocompatibilité :
        STARTER = "STARTER", _("Starter (Ancien)")
        PRO = "PRO", _("Pro (Ancien)")
        ENTERPRISE = "ENTERPRISE", _("Enterprise (Ancien)")

    code = models.CharField(_("code"), max_length=20, choices=Code.choices, unique=True)
    libelle = models.CharField(_("libellé"), max_length=100)

    # En **centimes** de FCFA, comme tout montant du produit — Socle §1.3.
    prix_mensuel_montant = models.BigIntegerField(
        _("prix mensuel"), null=True, blank=True, help_text=_("Centimes FCFA. NULL = non tranché.")
    )
    prix_annuel_montant = models.BigIntegerField(
        _("prix annuel"), null=True, blank=True, help_text=_("Centimes FCFA. NULL = non tranché.")
    )

    # `NULL` signifie **illimité**, jamais « zéro ». Les confondre ferait d'un
    # plan Enterprise le plus restrictif de tous.
    limite_projets = models.IntegerField(_("limite de projets"), null=True, blank=True)
    limite_utilisateurs = models.IntegerField(_("limite d'utilisateurs"), null=True, blank=True)
    limite_stockage_mo = models.IntegerField(_("limite de stockage (Mo)"), null=True, blank=True)

    acces_ia = models.BooleanField(_("accès aux fonctions IA"), default=False)

    # Des limites nouvelles sans migration : le plan est une donnée de
    # configuration, et chaque nouvelle limite ne mérite pas une colonne.
    limites_avancees = models.JSONField(_("limites avancées"), default=dict, blank=True)

    # Un plan retiré de la vente **reste lié** aux abonnements en cours : on ne
    # le supprime pas, on cesse de le proposer.
    est_actif = models.BooleanField(_("proposé à la vente"), default=True)

    class Meta:
        db_table = "plan"
        verbose_name = _("plan")
        verbose_name_plural = _("plans")
        ordering = ["prix_mensuel_montant"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(prix_mensuel_montant__gte=0)
                | models.Q(prix_mensuel_montant__isnull=True),
                name="chk_plan_prix_mensuel_positif",
            ),
            models.CheckConstraint(
                condition=models.Q(prix_annuel_montant__gte=0)
                | models.Q(prix_annuel_montant__isnull=True),
                name="chk_plan_prix_annuel_positif",
            ),
        ]

    def __str__(self) -> str:
        return self.libelle

    @property
    def tarif_connu(self) -> bool:
        """Faux tant que l'arbitrage A7 n'est pas rendu.

        La facturation le lit avant d'émettre quoi que ce soit : mieux vaut ne
        pas facturer que facturer un montant que personne n'a décidé.
        """
        return self.prix_mensuel_montant is not None


class Abonnement(ModeleBase):
    """Ce qu'une entreprise a souscrit — MLD §4.4."""

    class Statut(models.TextChoices):
        ESSAI = "ESSAI", _("Essai gratuit")
        ACTIF = "ACTIF", _("Actif")
        IMPAYE = "IMPAYE", _("Impayé")
        SUSPENDU = "SUSPENDU", _("Suspendu")
        RESILIE = "RESILIE", _("Résilié")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    entreprise = models.ForeignKey(
        "tenants.Entreprise", on_delete=models.RESTRICT, related_name="abonnements"
    )
    plan = models.ForeignKey(Plan, on_delete=models.RESTRICT, related_name="abonnements")

    date_debut = models.DateField(_("début"))
    date_fin = models.DateField(_("fin"))
    fin_essai = models.DateField(_("fin de l'essai"), null=True, blank=True)

    statut = models.CharField(
        _("statut"), max_length=20, choices=Statut.choices, default=Statut.ESSAI
    )
    renouvellement_auto = models.BooleanField(_("renouvellement automatique"), default=True)

    # --- Conservation des données après résiliation — MLD §4.4 (v1.3) --------
    lecture_seule_depuis = models.DateTimeField(_("lecture seule depuis"), null=True, blank=True)
    suppression_annoncee_le = models.DateTimeField(
        _("suppression annoncée le"), null=True, blank=True
    )
    # **La date annoncée au client, et c'est elle qui fait foi.** Stockée, jamais
    # recalculée : si elle valait `lecture_seule_depuis + 90 jours` évaluée à
    # l'exécution, une reprise de données décalant `lecture_seule_depuis` ferait
    # tomber la suppression un autre jour que celui annoncé.
    suppression_prevue_le = models.DateField(_("suppression prévue le"), null=True, blank=True)
    donnees_supprimees_le = models.DateTimeField(_("données supprimées le"), null=True, blank=True)

    class Meta:
        db_table = "abonnement"
        verbose_name = _("abonnement")
        verbose_name_plural = _("abonnements")
        ordering = ["-date_debut"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_fin__gt=models.F("date_debut")),
                name="chk_abonnement_dates",
            ),
            # Un seul abonnement vivant par entreprise. Deux essais simultanés
            # donneraient deux compteurs de jours restants, et deux réponses à
            # « quand expire mon accès ? ».
            models.UniqueConstraint(
                fields=["entreprise"],
                condition=models.Q(statut__in=["ESSAI", "ACTIF"]),
                name="uq_abonnement_actif",
            ),
            # **Aucune date de suppression sans l'annonce qui l'a précédée.**
            # La règle vivrait sinon dans un service, qu'une commande
            # d'administration contournerait sans le savoir.
            models.CheckConstraint(
                condition=models.Q(suppression_prevue_le__isnull=True)
                | models.Q(suppression_annoncee_le__isnull=False),
                name="chk_suppression_annoncee",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entreprise} — {self.plan} ({self.get_statut_display()})"

    @property
    def jours_essai_restants(self) -> int | None:
        """Ce que le bandeau d'essai affiche. `None` hors essai.

        Le compte est **calculé**, jamais stocké : une valeur figée en base
        serait fausse dès le lendemain, et personne ne la verrait vieillir.
        """
        if self.statut != self.Statut.ESSAI or self.fin_essai is None:
            return None

        from django.utils import timezone

        return max(0, (self.fin_essai - timezone.localdate()).days)


class RelanceEssai(ModeleBase):
    """Une relance d'essai envoyée — et une seule par seuil.

    **Sans cette table, une tâche rejouée le même jour renvoie le même message.**
    Le parcours de l'essai gratuit §2.4 le pose : la sélection porte sur une
    date exacte, et rien n'empêche la tâche de tourner deux fois. Un client qui
    reçoit deux fois « il vous reste 3 jours » n'y voit pas un incident
    technique : il y voit un produit qui insiste.

    La contrainte d'unicité est ce qui tient la promesse. La mettre dans le
    service l'aurait laissée contournable par une commande d'administration.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    abonnement = models.ForeignKey(
        Abonnement, on_delete=models.CASCADE, related_name="relances_essai"
    )
    # 7, 3, 1 ou 0 — le nombre de jours restants au moment de l'envoi.
    seuil = models.PositiveSmallIntegerField(_("seuil en jours"))
    destinataires = models.PositiveSmallIntegerField(_("destinataires"), default=0)

    class Meta:
        db_table = "relance_essai"
        verbose_name = _("relance d'essai")
        verbose_name_plural = _("relances d'essai")
        ordering = ["-cree_le"]
        constraints = [
            models.UniqueConstraint(fields=["abonnement", "seuil"], name="uq_relance_essai_seuil"),
        ]

    def __str__(self) -> str:
        return f"{self.abonnement} — J-{self.seuil}"
