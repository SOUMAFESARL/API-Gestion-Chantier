"""Modèle LiaisonDocument — Traçabilité des ponts automatiques (F6 MVP §4 \u0026 §8).

Relie un document GED à son objet métier source :
- F1_CONTRAT : contrat ou avenant signé joint à la fiche projet
- F2_RAPPORT : rapport quotidien validé ou photos de chantier
- F9_BRV     : bon de livraison signé ou bon de réception et validation officiel

Table d'entreprise (`ModeleEntreprise` — isolation D9).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import TypeSourceLiaison
from apps.core.models import ModeleEntreprise

TypeSourceDocument = TypeSourceLiaison


class LiaisonDocument(ModeleEntreprise):
    """Lien entre un document GED et un objet source applicatif."""

    document = models.ForeignKey(
        "ged.Document",
        on_delete=models.CASCADE,
        related_name="liaisons",
        verbose_name=_("document"),
        db_index=True,
    )
    type_source = models.CharField(
        _("type de source"),
        max_length=50,
        choices=TypeSourceLiaison.choices,
        db_index=True,
        help_text=_("Module source à l'origine du document (F1_CONTRAT, F2_RAPPORT, F9_BRV)."),
    )
    objet_id = models.UUIDField(
        _("identifiant de l'objet source"),
        db_index=True,
        help_text=_("UUID de l'entité source (contrat, rapport journalier, réception BRV...)."),
    )

    class Meta:
        db_table = "liaison_document"
        verbose_name = _("liaison de document")
        verbose_name_plural = _("liaisons de documents")
        constraints = [
            models.UniqueConstraint(
                fields=["document", "type_source", "objet_id"],
                name="uq_liaison_doc_source_obj",
            ),
        ]
        indexes = [
            models.Index(fields=["type_source", "objet_id"], name="idx_liaison_src_obj"),
        ]

    def __str__(self) -> str:
        return f"Liaison {self.type_source} ({self.objet_id}) -> {self.document.nom}"

    # -- Propriétés de commodité & compatibilité MLD ------------------------

    @property
    def type_objet(self) -> str:
        """Alias pour `type_source` (MLD §5.7)."""
        return self.type_source

    @type_objet.setter
    def type_objet(self, val: str) -> None:
        self.type_source = val

    def save(self, *args, **kwargs):
        # Propagation de l'entreprise depuis le document parent
        if not self.entreprise_id and self.document_id:
            self.entreprise_id = self.document.entreprise_id
        super().save(*args, **kwargs)
