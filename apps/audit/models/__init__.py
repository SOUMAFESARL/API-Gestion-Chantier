"""Application « audit » — le journal immuable.

Entité MCD : JournalAudit  ·  Table MLD §5.3

**Le Socle Commun §2.4 est catégorique** : « Chaque action effectuée dans le
système génère automatiquement une entrée dans le journal d'audit. Sans
exception. » Et : « Aucun utilisateur — y compris l'administrateur système —
ne peut modifier ou supprimer une entrée du journal d'audit. »

C'est la table qui protège l'entreprise cliente en cas de litige contractuel :
elle dit qui a changé quoi, quand, depuis quel appareil, et **ce que valait la
donnée avant**. Un journal qu'on peut réécrire ne prouve rien.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import ActionAudit

__all__ = ["JournalAudit"]


class JournalAudit(models.Model):
    """Une action, telle qu'elle s'est produite — MLD §5.3.

    **Cette table n'hérite pas de `ModeleBase`, et c'est délibéré.**
    `ModeleBase` apporte `modifie_le` et `supprime_le` : deux colonnes qui
    n'ont aucun sens ici, puisque rien n'est jamais modifié ni supprimé
    (RG-07). Les porter laisserait croire qu'une entrée peut l'être.

    **La clé primaire est séquentielle, exception à la décision D3.** Ailleurs
    le projet utilise des UUID ; ici l'ordre d'insertion *est* une information,
    et un `BIGSERIAL` coûte huit octets là où un UUID en coûte seize — sur une
    table qui atteindra deux millions de lignes la deuxième année, la
    différence se voit.

    **L'immuabilité ne se garantit pas en Python.** Elle se pose en base :

        REVOKE UPDATE, DELETE ON journal_audit FROM app_ccd;

    Un code applicatif qui « s'interdit » de modifier une ligne n'interdit rien
    à qui ouvre une console SQL avec le même rôle.
    """

    id = models.BigAutoField(primary_key=True)

    # Nul quand l'action vient du système — une tâche planifiée, une
    # expiration, un provisionnement. Ne pas confondre avec « inconnu ».
    utilisateur_id = models.UUIDField(_("utilisateur"), null=True, blank=True, db_index=True)

    action = models.CharField(_("action"), max_length=20, choices=ActionAudit.choices)
    type_entite = models.CharField(_("type d'entité"), max_length=50)
    entite_id = models.UUIDField(_("identifiant de l'entité"), null=True, blank=True)

    valeur_avant = models.JSONField(_("valeur avant"), null=True, blank=True)
    valeur_apres = models.JSONField(_("valeur après"), null=True, blank=True)

    horodatage = models.DateTimeField(_("horodatage"), auto_now_add=True, db_index=True)
    adresse_ip = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)
    appareil = models.CharField(_("appareil"), max_length=255, blank=True)

    class Meta:
        db_table = "journal_audit"
        verbose_name = _("entrée du journal d'audit")
        verbose_name_plural = _("journal d'audit")
        ordering = ["-horodatage"]
        indexes = [
            models.Index(fields=["type_entite", "entite_id"], name="audit_entite_idx"),
            models.Index(fields=["utilisateur_id", "-horodatage"], name="audit_acteur_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.horodatage:%Y-%m-%d %H:%M} — {self.action} sur {self.type_entite}"
