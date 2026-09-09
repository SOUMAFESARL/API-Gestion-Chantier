"""Le journal d'audit ne fait jamais échouer l'action qu'il décrit.

**C'est une promesse écrite dans `journaliser`, et elle était fausse.** Le
service attrapait bien `DatabaseError` — mais sous PostgreSQL, une instruction
en échec avorte la transaction entière : l'appelant mourait sur sa requête
suivante, avec un `TransactionManagementError` sans rapport visible avec le
journal.

*Découvert le 03/09/2026 en branchant le wizard : un code d'action de 28
caractères sur une colonne de 20.* Le défaut ne tenait pas au code d'action —
celui-là s'est corrigé en une ligne — mais au fait qu'**une écriture d'audit en
échec emportait l'opération métier**, ce que ce service existe précisément pour
éviter.

Le test ci-dessous est celui qui manquait : il **provoque** l'échec, au lieu de
vérifier que le `try` est là.
"""

import pytest
from django_tenants.utils import schema_context

from apps.audit.models import JournalAudit
from apps.audit.services import journaliser
from apps.core.enums import ActionAudit

SCHEMA = "demo"


@pytest.mark.django_db
def test_une_ecriture_daudit_en_echec_ne_casse_pas_la_transaction_appelante():
    """L'appelant doit pouvoir continuer à écrire après un audit refusé.

    `action` est un `varchar(20)` : trente caractères le font échouer côté
    base, ce qu'aucune validation Python n'intercepte — `create()` n'appelle
    pas `full_clean()`.
    """
    with schema_context(SCHEMA):
        assert journaliser(action="A" * 30, type_entite="Essai") is None

        # La requête qui mourait avant le point de sauvegarde.
        entree = journaliser(action=ActionAudit.VALIDATION, type_entite="Essai")
        assert entree is not None
        assert JournalAudit.objects.filter(pk=entree.pk).exists()


@pytest.mark.django_db
def test_une_entree_valide_est_bien_ecrite():
    with schema_context(SCHEMA):
        entree = journaliser(
            action=ActionAudit.CONNEXION,
            type_entite="Utilisateur",
            valeur_apres={"resultat": "ok"},
        )
        assert entree is not None
        assert entree.action == ActionAudit.CONNEXION
        assert entree.valeur_apres == {"resultat": "ok"}
