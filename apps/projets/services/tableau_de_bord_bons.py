"""Service des bons de paiement pour le tableau de bord de pilotage."""

import uuid
from dataclasses import dataclass
from typing import Any

__all__ = [
    "BonPaiementItem",
    "creer_bon_paiement_test",
    "obtenir_bons_a_valider",
    "vider_bons_test",
]

_BONS_TEST: list["BonPaiementItem"] = []


@dataclass
class BonPaiementItem:
    id: uuid.UUID
    numero: str
    beneficiaire: str
    corps_etat: str
    lot: Any
    montant_net: int
    statut: str
    projet_id: Any = None


def creer_bon_paiement_test(projet, *, montant: int) -> BonPaiementItem:
    """Helper pour les tests du lot 7 (règles E-11 / tableau de bord)."""
    bon = BonPaiementItem(
        id=uuid.uuid4(),
        numero=f"BP-{len(_BONS_TEST) + 1:04d}",
        beneficiaire="Sous-Traitant SARL",
        corps_etat="Gros Œuvre",
        lot=None,
        montant_net=montant,
        statut="EN_ATTENTE",
        projet_id=getattr(projet, "id", projet),
    )
    _BONS_TEST.append(bon)
    return bon


def obtenir_bons_a_valider(projets_qs=None) -> list[BonPaiementItem]:
    """Retourne la liste des bons de paiement urgents à valider."""
    if not _BONS_TEST:
        return []
    if projets_qs is not None:
        p_ids = set(projets_qs.values_list("id", flat=True))
        return [b for b in _BONS_TEST if b.projet_id in p_ids]
    return list(_BONS_TEST)


def vider_bons_test():
    _BONS_TEST.clear()
