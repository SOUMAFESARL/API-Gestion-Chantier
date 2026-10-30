"""Lecture de l'arbre d'un projet — une requête, puis tout en mémoire.

Un projet compte quelques centaines de cases au plus. Les charger toutes en une requête, puis
répondre en mémoire aux questions de structure (enfants, feuilles, ancêtres, héritage), coûte
moins cher et reste plus simple que d'interroger la base case par case.

**Aucune règle ne lit un libellé de niveau** (décisions v1.2, §1) : ce qui varie dépend de la
position (feuille ou parent) ou d'un réglage explicite (`NiveauProjet.alerter`).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from apps.projets.models import Element, NiveauProjet

__all__ = ["Arbre", "charger_arbre"]


@dataclass
class Arbre:
    projet: object
    elements: list[Element]
    niveaux: list[NiveauProjet]
    par_id: dict = field(default_factory=dict)
    enfants_de: dict = field(default_factory=lambda: defaultdict(list))
    actifs_seulement: bool = True

    def __post_init__(self):
        self.par_id = {e.pk: e for e in self.elements}
        self.enfants_de = defaultdict(list)
        for e in self.elements:
            self.enfants_de[e.parent_id].append(e)
        for liste in self.enfants_de.values():
            liste.sort(key=lambda x: (x.ordre, x.cree_le))
        self._niveaux = {n.pk: n for n in self.niveaux}

    # --- Structure ------------------------------------------------------------------------
    def racines(self) -> list[Element]:
        return self.enfants_de.get(None, [])

    def enfants(self, element) -> list[Element]:
        return self.enfants_de.get(getattr(element, "pk", element), [])

    def enfants_actifs(self, element) -> list[Element]:
        return [e for e in self.enfants(element) if e.est_actif]

    def est_feuille(self, element) -> bool:
        """Une feuille n'a aucun enfant actif : désactiver le dernier en refait une feuille."""
        return not self.enfants_actifs(element)

    def feuilles(self, actives=True) -> list[Element]:
        return [e for e in self.elements if (e.est_actif or not actives) and self.est_feuille(e)]

    def ancetres(self, element) -> list[Element]:
        """Du plus haut au parent direct."""
        return [self.par_id[i] for i in _ids(element.ancetres_ids) if i in self.par_id]

    def descendants(self, element) -> list[Element]:
        return [
            e for e in self.elements if e.pk != element.pk and e.chemin.startswith(element.chemin)
        ]

    def groupe(self, feuille) -> Element:
        """La case qui regroupe une feuille dans le journal : son parent, ou elle-même."""
        return self.par_id.get(feuille.parent_id) or feuille

    def niveau(self, element) -> NiveauProjet | None:
        return self._niveaux.get(element.niveau_id)

    def chemin_libelles(self, element) -> list[str]:
        return [a.libelle for a in self.ancetres(element)] + [element.libelle]

    def numerotation(self) -> dict:
        """1, 1.2, 1.2.3 : un affichage recalculé, jamais un identifiant (A-4)."""
        numeros = {}

        def parcourir(parent, prefixe):
            for rang, enfant in enumerate(self.enfants(parent), start=1):
                numero = f"{prefixe}{rang}"
                numeros[enfant.pk] = numero
                parcourir(enfant, f"{numero}.")

        parcourir(None, "")
        return numeros

    # --- Héritage : le plus proche ancêtre qui le définit l'emporte ------------------------
    def _herite(self, element, champ):
        for case in [element, *reversed(self.ancetres(element))]:
            valeur = getattr(case, champ)
            if valeur:
                return valeur
        return None

    def mode_execution(self, element) -> str:
        return self._herite(element, "mode_execution") or ""

    def type_bordereau(self, element) -> str:
        return self._herite(element, "type_bordereau") or ""

    def titulaire_id(self, element):
        return self._herite(element, "titulaire_id")

    # --- État -----------------------------------------------------------------------------
    def commence(self, element) -> bool:
        """Au moins une feuille en dessous porte une mesure (§1)."""
        cases = [element, *self.descendants(element)]
        return any(_porte_une_mesure(c) for c in cases if self.est_feuille(c))

    def suspendu(self, element) -> bool:
        return element.suspendu or any(a.suspendu for a in self.ancetres(element))

    def niveaux_alerte(self) -> list[Element]:
        """Les cases des niveaux cochés « alerter à ce niveau »."""
        cochés = {n.pk for n in self.niveaux if n.alerter}
        return [e for e in self.elements if e.est_actif and e.niveau_id in cochés]


def _ids(chaine_ids):
    import uuid

    resultat = []
    for i in chaine_ids:
        try:
            resultat.append(uuid.UUID(str(i)))
        except ValueError:
            continue
    return resultat


def _porte_une_mesure(feuille) -> bool:
    return bool(
        feuille.cloture
        or (feuille.quantite_realisee or 0) > 0
        or (feuille.pourcentage_declare or 0) > 0
    )


def charger_arbre(projet, *, actifs_seulement: bool = False) -> Arbre:
    """L'arbre du projet. Par défaut avec les cases désactivées : elles gardent leur place."""
    qs = Element.objects.filter(projet=projet)
    if actifs_seulement:
        qs = qs.filter(est_actif=True)
    niveaux = list(NiveauProjet.objects.filter(projet=projet).order_by("ordre"))
    return Arbre(
        projet=projet,
        elements=list(qs.order_by("profondeur", "ordre", "cree_le")),
        niveaux=niveaux,
        actifs_seulement=actifs_seulement,
    )
