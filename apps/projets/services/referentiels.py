"""Référentiels dynamiques du module Projets : types de projet et noms de lot.

Une liste = les entrées de la plateforme (super admin, communes à toutes les
entreprises, non supprimables ici) + celles de l'entreprise. Arbitrage du 16/10/2026.
"""

from rest_framework.exceptions import ValidationError

from apps.audit.services import journaliser
from apps.catalogue.models.referentiel import (
    CategorieReferentiel,
    ReferentielPlateforme,
    cle_comparaison,
    code_depuis_libelle,
)
from apps.core.enums import ActionAudit, ModeExecution
from apps.core.exceptions import ErreurMetier, LibelleEnDouble
from apps.projets.models import ReferentielEntreprise

__all__ = [
    "CATEGORIES_URL",
    "MODES_DE_BASE",
    "ajouter_entree",
    "code_mode_execution_valide",
    "code_type_projet_valide",
    "exiger_mode_de_base",
    "libelle_mode_execution",
    "lister_referentiel",
    "mode_base",
    "retirer_entree",
    "table_modes_execution",
]

# Le segment d'URL → la catégorie stockée.
CATEGORIES_URL = {
    "types-projet": CategorieReferentiel.TYPE_PROJET,
    "lots": CategorieReferentiel.LOT,
    "modes-execution": CategorieReferentiel.MODE_EXECUTION,
}

# Les trois modes de base : le rapport journalier raisonne sur eux seuls.
MODES_DE_BASE = tuple(ModeExecution.values)

LONGUEUR_MAX_GROUPE = 100
PLATEFORME = "PLATEFORME"
ENTREPRISE = "ENTREPRISE"


def lister_referentiel(categorie: str) -> list[dict]:
    """La liste fusionnée, plateforme d'abord. Un libellé de l'entreprise que la
    plateforme a repris depuis n'apparaît qu'une fois, sous la plateforme."""
    plateforme = [
        {"code": e.code, "libelle": e.libelle, "groupe": e.groupe, "origine": PLATEFORME}
        for e in ReferentielPlateforme.objects.filter(categorie=categorie)
    ]
    deja = {cle_comparaison(e["libelle"]) for e in plateforme} | {e["code"] for e in plateforme}
    entreprise = [
        {"code": e.code, "libelle": e.libelle, "groupe": e.groupe, "origine": ENTREPRISE}
        for e in ReferentielEntreprise.objects.filter(categorie=categorie)
        if cle_comparaison(e.libelle) not in deja and e.code not in deja
    ]
    return plateforme + entreprise


def exiger_mode_de_base(categorie: str, groupe: str) -> None:
    """Un mode d'exécution se rattache obligatoirement à l'un des trois modes de base (422)."""
    if categorie == CategorieReferentiel.MODE_EXECUTION and groupe not in MODES_DE_BASE:
        raise ErreurMetier(
            "Un mode d'exécution se rattache à un mode de base : "
            "choisissez Régie, Sous-traitance structurée ou Sous-traitance informelle.",
            details={"groupe": list(MODES_DE_BASE)},
        )


def ajouter_entree(categorie: str, libelle: str, *, groupe: str = "", auteur=None) -> dict:
    libelle = " ".join((libelle or "").split())
    if not libelle:
        raise ValidationError({"libelle": "Saisissez un libellé."})
    groupe = " ".join((groupe or "").split())
    if len(groupe) > LONGUEUR_MAX_GROUPE:
        raise ValidationError(
            {"groupe": f"Le groupe ne peut pas dépasser {LONGUEUR_MAX_GROUPE} caractères."}
        )
    exiger_mode_de_base(categorie, groupe)

    existantes = lister_referentiel(categorie)
    cle = cle_comparaison(libelle)
    doublon = next((e for e in existantes if cle_comparaison(e["libelle"]) == cle), None)
    if doublon is not None:
        raise LibelleEnDouble(libelle, doublon["libelle"])

    codes = {e["code"] for e in existantes} | set(
        ReferentielEntreprise.tous_objets.filter(categorie=categorie).values_list("code", flat=True)
    )
    base = code_depuis_libelle(libelle)
    code, rang = base, 2
    while code in codes:
        suffixe = f"_{rang}"
        code = base[: 60 - len(suffixe)] + suffixe
        rang += 1

    entree = ReferentielEntreprise.objects.create(
        categorie=categorie, code=code, libelle=libelle, groupe=groupe, cree_par=auteur
    )
    journaliser(
        action=ActionAudit.CREATION,
        type_entite="referentiel_entreprise",
        entite_id=entree.pk,
        utilisateur_id=getattr(auteur, "pk", None),
        valeur_apres={"categorie": categorie, "code": code, "libelle": libelle, "groupe": groupe},
    )
    return {"code": code, "libelle": libelle, "groupe": groupe, "origine": ENTREPRISE}


def retirer_entree(categorie: str, code: str, *, auteur=None) -> None:
    if ReferentielPlateforme.objects.filter(categorie=categorie, code=code).exists():
        raise ValidationError(
            {"detail": "Cette entrée est définie par la plateforme : elle ne se retire pas ici."}
        )
    entree = ReferentielEntreprise.objects.filter(categorie=categorie, code=code).first()
    if entree is None:
        raise ValidationError({"detail": "Entrée introuvable : rechargez la page."})
    entree.delete(utilisateur=auteur)  # suppression logique (ModeleBase)
    journaliser(
        action=ActionAudit.SUPPRESSION,
        type_entite="referentiel_entreprise",
        entite_id=entree.pk,
        utilisateur_id=getattr(auteur, "pk", None),
        valeur_avant={"categorie": categorie, "code": code, "libelle": entree.libelle},
    )


def code_type_projet_valide(code: str) -> bool:
    """Un code de la liste, ou déjà porté par un projet (entrée retirée depuis)."""
    from apps.projets.models import Projet

    if any(e["code"] == code for e in lister_referentiel(CategorieReferentiel.TYPE_PROJET)):
        return True
    return Projet.tous_objets.filter(type_projet=code).exists()


def _base_du_groupe(groupe: str) -> str:
    return groupe if groupe in MODES_DE_BASE else ModeExecution.REGIE.value


def table_modes_execution(cache: dict | None = None) -> dict[str, tuple[str, str, bool]]:
    """code → (mode de base, libellé, actif) pour tout le référentiel, en quatre requêtes.

    À calculer une fois par requête et à passer aux appels en boucle : `cache` (par exemple le
    contexte d'un serializer) mémorise la table pour la durée de la requête. Les trois modes de
    base se rattachent toujours à eux-mêmes.

    Les entrées retirées (suppression logique) restent résolues, marquées `actif = False` : un lot
    qui porte encore leur code garde son mode de base et son libellé. Une entrée active l'emporte
    toujours ; parmi les retirées, la plus récente.
    """
    if cache is not None and "table_modes_execution" in cache:
        return cache["table_modes_execution"]
    categorie = CategorieReferentiel.MODE_EXECUTION
    table = {
        e["code"]: (_base_du_groupe(e["groupe"]), e["libelle"], True)
        for e in lister_referentiel(categorie)
    }
    for modele in (ReferentielEntreprise, ReferentielPlateforme):
        retirees = modele.tous_objets.filter(
            categorie=categorie, supprime_le__isnull=False
        ).order_by("-supprime_le")
        for e in retirees:
            table.setdefault(e.code, (_base_du_groupe(e.groupe), e.libelle, False))
    for mode in ModeExecution:
        table[mode.value] = (mode.value, table.get(mode.value, (None, mode.label))[1], True)
    if cache is not None:
        cache["table_modes_execution"] = table
    return table


def mode_base(code: str, table: dict | None = None) -> str:
    """Le mode de base d'un code : son `groupe`, même si l'entrée est retirée ; REGIE si inconnu."""
    if table is None:
        table = table_modes_execution()
    return table.get(code, (ModeExecution.REGIE.value, "", False))[0]


def libelle_mode_execution(code: str, table: dict | None = None) -> str:
    if table is None:
        table = table_modes_execution()
    return table.get(code, (None, code, False))[1] or code


def code_mode_execution_valide(code: str, table: dict | None = None) -> bool:
    """Un code actif du référentiel fusionné, ou déjà porté par un lot (entrée retirée depuis)."""
    from apps.projets.models import Lot

    if table is None:
        table = table_modes_execution()
    if code in table and table[code][2]:
        return True
    return Lot.tous_objets.filter(mode_execution=code).exists()
