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
from apps.core.enums import ActionAudit
from apps.projets.models import ReferentielEntreprise

__all__ = [
    "CATEGORIES_URL",
    "ajouter_entree",
    "code_type_projet_valide",
    "lister_referentiel",
    "retirer_entree",
]

# Le segment d'URL → la catégorie stockée.
CATEGORIES_URL = {
    "types-projet": CategorieReferentiel.TYPE_PROJET,
    "lots": CategorieReferentiel.LOT,
}

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


def ajouter_entree(categorie: str, libelle: str, *, auteur=None) -> dict:
    libelle = " ".join((libelle or "").split())
    if not libelle:
        raise ValidationError({"libelle": "Saisissez un libellé."})

    existantes = lister_referentiel(categorie)
    cle = cle_comparaison(libelle)
    if any(cle_comparaison(e["libelle"]) == cle for e in existantes):
        raise ValidationError({"libelle": "Ce libellé figure déjà dans la liste."})

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
        categorie=categorie, code=code, libelle=libelle, cree_par=auteur
    )
    journaliser(
        action=ActionAudit.CREATION,
        type_entite="referentiel_entreprise",
        entite_id=entree.pk,
        utilisateur_id=getattr(auteur, "pk", None),
        valeur_apres={"categorie": categorie, "code": code, "libelle": libelle},
    )
    return {"code": code, "libelle": libelle, "groupe": "", "origine": ENTREPRISE}


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
