"""Import des quantités et des montants (DQE) sur un projet déjà découpé (§13quinquies.1).

Le fichier a **le format du tableau** (`services.import_export`) : les colonnes des niveaux du
projet, dans l'ordre, puis Unité, Quantité, Montant, Début, Fin, et une colonne facultative
« Prix unitaire » qui ne sert qu'à calculer Montant = Quantité x Prix unitaire.

**Rapprochement par chemin.** Chaque ligne désigne une case par la suite de ses intitulés,
comparés sans accents, casse ni espaces superflus :

- **ligne reconnue** (le chemin mène à une feuille) : la feuille est mise à jour selon le §11bis —
  modification tracée si elle est commencée, quantité refusée sous le réalisé, unité figée ;
- **ligne inconnue** : une nouvelle branche est proposée, rattachée à la case existante la plus
  profonde de son chemin ;
- **une feuille absente du fichier n'est jamais touchée.**

**Deux temps.** `bilan_dqe` dit ce qui serait fait — mises à jour (avant, après), nouvelles
branches, refus motivés — sans rien écrire. `appliquer_dqe` refait ce bilan sur les lignes
reçues puis applique ce qu'il accepte, **ligne par ligne** : une ligne refusée à l'application
n'empêche pas les autres, et elle est rendue avec sa raison.

**Les dates** d'une feuille encore sans dates sont planifiées (dans le cadre de ses parents) ; une
feuille déjà datée garde les siennes : elles se reprogramment dans la vue en arbre, avec motif
et justification (RG-11). Le fichier ne déclenche jamais de prolongation.

**Droits**, dans le périmètre de chaque case : `projets.chiffrer` pour l'unité, la quantité et le
montant, `projets.planifier` pour les dates, `projets.decouper` (sur la case de rattachement)
pour une nouvelle branche.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError

from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.exceptions import ErreurMetier
from apps.projets.models import Element
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services import listes_modeles as lm
from apps.projets.services.perimetres import perimetre_de

__all__ = ["appliquer_dqe", "bilan_dqe", "sans_interne"]

LONGUEUR_MIN_MOTIF = 10


class Refus(Exception):  # noqa: N818 — un refus de ligne, pas une erreur du programme
    """Une ligne écartée, avec un code stable et un message pour l'écran."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _niveaux(arbre) -> list[dict]:
    return [
        {
            "libelle": n.libelle,
            "liste": lm.reference_liste(n.liste_plateforme or n.liste_entreprise),
            "alerter": n.alerter,
        }
        for n in arbre.niveaux
    ]


def _index_par_chemin(arbre) -> dict:
    """Chemin (clés de comparaison des intitulés) → case, désactivées comprises."""
    index: dict[tuple, object] = {}

    def parcourir(parent, prefixe):
        for enfant in arbre.enfants(parent):
            chemin = (*prefixe, enfant.cle_comparaison)
            index[chemin] = enfant
            parcourir(enfant, chemin)

    parcourir(None, ())
    return index


def _texte_date(valeur) -> str | None:
    return valeur.isoformat() if isinstance(valeur, date) else valeur


def _valeur_affichee(champ, valeur, montants_visibles):
    if champ == "montant" and not montants_visibles:
        return None
    if valeur is None or isinstance(valeur, (int, bool)):
        return valeur
    if isinstance(valeur, date):
        return valeur.isoformat()
    return str(valeur)


def _champs_de_la_ligne(ligne) -> dict:
    """Unité, quantité prévue, montant et dates de la ligne, validés comme dans le tableau."""
    from apps.projets.services.tableau_demarrage import _champs_feuille

    try:
        return _champs_feuille(ligne)
    except ValidationError as erreur:
        message = erreur.detail.get("lignes") if isinstance(erreur.detail, dict) else None
        raise Refus("valeur_invalide", str(message or erreur.detail)) from None


def _exiger(perimetre, code, case, raison):
    if not perimetre.peut(code, case):
        raise Refus(
            "hors_perimetre",
            f"{raison} exige la permission « {code} » sur cette case : elle n'est pas dans "
            "votre périmètre.",
        )


def _examiner_mise_a_jour(arbre, feuille, ligne, perimetre) -> dict:
    """Ce que la ligne changerait sur une feuille existante ; lève `Refus` sinon (§11bis)."""
    from apps.projets.services.calendrier import prolongations_necessaires

    if not feuille.est_actif:
        raise Refus("case_desactivee", f"« {feuille.libelle} » est désactivée.")
    champs = _champs_de_la_ligne(ligne)
    if not arbre.est_feuille(feuille):
        if champs:
            raise Refus(
                "case_parente",
                f"« {feuille.libelle} » a des sous-tâches : la quantité et le montant se "
                "saisissent sur les tâches du bas.",
            )
        return {"changements": {}, "chiffrer": {}, "dates": None, "commencee": False}

    commencee = arbre.commence(feuille)
    changements, chiffrer = {}, {}
    for champ_ligne, champ in (
        ("unite", "unite"),
        ("quantite_prevue", "quantite_prevue"),
        ("montant", "montant"),
    ):
        if champ_ligne not in champs:
            continue
        nouvelle, actuelle = champs[champ_ligne], getattr(feuille, champ)
        if nouvelle == actuelle:
            continue
        changements[champ] = (actuelle, nouvelle)
        chiffrer[champ] = nouvelle
    if chiffrer:
        _exiger(perimetre, "projets.chiffrer", feuille, "Modifier la quantité ou le montant")
    if commencee and "unite" in chiffrer:
        raise Refus(
            "unite_figee",
            f"L'unité de « {feuille.libelle} », déjà commencée, ne change plus "
            f"({feuille.unite or 'aucune'} → {chiffrer['unite']}).",
        )
    if (
        commencee
        and chiffrer.get("quantite_prevue") is not None
        and chiffrer["quantite_prevue"] < (feuille.quantite_realisee or 0)
    ):
        raise Refus(
            "quantite_sous_realise",
            f"La quantité prévue de « {feuille.libelle} » ne descend pas sous le réalisé "
            f"({feuille.quantite_realisee}).",
        )

    dates = None
    debut = champs.get("date_debut_prevue")
    fin = champs.get("date_fin_prevue")
    if debut or fin:
        fixees = [
            (nouvelle, actuelle)
            for nouvelle, actuelle in (
                (debut, feuille.date_debut_prevue),
                (fin, feuille.date_fin_prevue),
            )
            if nouvelle and actuelle and nouvelle != actuelle
        ]
        if fixees:
            raise Refus(
                "dates_deja_fixees",
                f"Les dates de « {feuille.libelle} » sont déjà fixées : elles se reprogramment "
                "dans la vue en arbre, avec un motif.",
            )
        debut = debut or feuille.date_debut_prevue
        fin = fin or feuille.date_fin_prevue
        if (debut, fin) != (feuille.date_debut_prevue, feuille.date_fin_prevue):
            _exiger(perimetre, "projets.planifier", feuille, "Planifier les dates")
            if debut and fin and fin < debut:
                raise Refus("valeur_invalide", "La date de fin précède la date de début.")
            if prolongations_necessaires(feuille, debut, fin, arbre):
                raise Refus(
                    "dates_hors_parent",
                    f"Les dates de « {feuille.libelle} » dépassent celles d'une case parente : "
                    "planifiez-la dans la vue en arbre, qui propose la prolongation.",
                )
            dates = (debut, fin)
            if debut != feuille.date_debut_prevue:
                changements["date_debut_prevue"] = (feuille.date_debut_prevue, debut)
            if fin != feuille.date_fin_prevue:
                changements["date_fin_prevue"] = (feuille.date_fin_prevue, fin)
    return {
        "changements": changements,
        "chiffrer": chiffrer,
        "dates": dates,
        "commencee": commencee,
    }


def _examiner_nouvelle_branche(arbre, index, chemin, ligne, perimetre) -> dict:
    """La case de rattachement d'une nouvelle branche ; lève `Refus` si elle ne peut pas l'être."""
    profondeur = 0
    rattachement = None
    for i in range(len(chemin) - 1, 0, -1):
        if chemin[:i] in index:
            rattachement, profondeur = index[chemin[:i]], i
            break
    champs = _champs_de_la_ligne(ligne)
    if rattachement is not None:
        if not rattachement.est_actif or any(not a.est_actif for a in arbre.ancetres(rattachement)):
            raise Refus("case_desactivee", f"« {rattachement.libelle} » est désactivée.")
        if arbre.est_feuille(rattachement) and arbre.commence(rattachement):
            raise Refus(
                "feuille_commencee",
                f"« {rattachement.libelle} » est une tâche déjà commencée : pour la découper, "
                "utilisez « Détailler » dans la vue en arbre (A-5).",
            )
    freres = arbre.enfants_actifs(rattachement)
    niveau_attendu = arbre.niveaux[profondeur] if profondeur < len(arbre.niveaux) else None
    if freres and niveau_attendu is not None and freres[0].niveau_id != niveau_attendu.pk:
        raise Refus(
            "niveau_incompatible",
            f"Les cases sous « {rattachement.libelle if rattachement else 'le projet'} » sont du "
            f"niveau « {freres[0].niveau.libelle} » : une case d'un autre niveau ne s'y mêle pas "
            "(A-2).",
        )
    _exiger(perimetre, "projets.decouper", rattachement, "Ajouter une branche")
    if {"unite", "quantite_prevue", "montant"} & set(champs):
        _exiger(perimetre, "projets.chiffrer", rattachement, "Chiffrer une nouvelle tâche")
    if {"date_debut_prevue", "date_fin_prevue"} & set(champs):
        _exiger(perimetre, "projets.planifier", rattachement, "Dater une nouvelle tâche")
    return {
        "rattachement": rattachement,
        "cases_a_creer": len(chemin) - profondeur,
        "champs": champs,
        "devient_parent": rattachement is not None and arbre.est_feuille(rattachement),
    }


def _chemin_affiche(cellules) -> list[str]:
    dernier = max((i for i, c in enumerate(cellules) if c), default=-1)
    return list(cellules[: dernier + 1])


def bilan_dqe(projet, lignes: list, *, utilisateur, request=None, montants_visibles=True) -> dict:
    """Ce que l'import ferait, sans rien écrire."""
    from apps.projets.services.tableau_demarrage import verifier_tableau

    arbre = charger_arbre(projet)
    if not arbre.niveaux or not arbre.elements:
        raise ErreurMetier(
            "Ce projet n'est pas encore découpé : importez le fichier dans le tableau de "
            "démarrage pour créer son arbre."
        )
    niveaux = _niveaux(arbre)
    verdict = verifier_tableau(niveaux, lignes)
    perimetre = perimetre_de(utilisateur, projet, request)
    index = _index_par_chemin(arbre)

    mises_a_jour, nouvelles, refus, inchangees = [], [], [], []
    for bloquant in verdict["bloquants"]:
        if "ligne" in bloquant:
            refus.append(
                {
                    "ligne": bloquant["ligne"],
                    "code": "ligne_invalide",
                    "regle": bloquant["regle"],
                    "message": bloquant["message"],
                }
            )
    for ligne in verdict["_lignes"]:
        cellules = ligne["cellules"]
        chemin_texte = _chemin_affiche(cellules)
        chemin = tuple(cle_comparaison(c) for c in chemin_texte)
        base = {"ligne": ligne["numero"], "chemin": chemin_texte}
        try:
            case = index.get(chemin)
            if case is not None:
                examen = _examiner_mise_a_jour(arbre, case, ligne, perimetre)
                if not examen["changements"]:
                    inchangees.append(ligne["numero"])
                    continue
                mises_a_jour.append(
                    {
                        **base,
                        "element_id": str(case.pk),
                        "commencee": examen["commencee"],
                        "modification_tracee": examen["commencee"]
                        and bool({"quantite_prevue", "montant"} & set(examen["chiffrer"])),
                        "changements": {
                            champ: {
                                "avant": _valeur_affichee(champ, avant, montants_visibles),
                                "apres": _valeur_affichee(champ, apres, montants_visibles),
                            }
                            for champ, (avant, apres) in examen["changements"].items()
                        },
                        "_ligne": ligne,
                        "_examen": examen,
                    }
                )
            else:
                examen = _examiner_nouvelle_branche(arbre, index, chemin, ligne, perimetre)
                rattachement = examen["rattachement"]
                nouvelles.append(
                    {
                        **base,
                        "rattachement": {
                            "id": str(rattachement.pk),
                            "libelle": rattachement.libelle,
                        }
                        if rattachement
                        else None,
                        "rattachement_devient_parent": examen["devient_parent"],
                        "cases_a_creer": examen["cases_a_creer"],
                        "feuille": {
                            champ: _valeur_affichee(champ, valeur, montants_visibles)
                            for champ, valeur in examen["champs"].items()
                        },
                        "_ligne": ligne,
                    }
                )
        except Refus as raison:
            refus.append({**base, "code": raison.code, "message": raison.message})

    refus.sort(key=lambda r: r["ligne"])
    return {
        "mises_a_jour": mises_a_jour,
        "nouvelles_branches": nouvelles,
        "refus": refus,
        "inchangees": inchangees,
        "avertissements": verdict["avertissements"],
        "motif_requis": any(m["modification_tracee"] for m in mises_a_jour),
        "resume": {
            "lignes": len(lignes),
            "mises_a_jour": len(mises_a_jour),
            "nouvelles_feuilles": len(nouvelles),
            "refus": len(refus),
            "inchangees": len(inchangees),
        },
    }


def sans_interne(bilan: dict) -> dict:
    """Le bilan tel que l'API le rend : sans les champs de travail (`_ligne`, `_examen`)."""
    return {
        **bilan,
        "mises_a_jour": [
            {k: v for k, v in m.items() if not k.startswith("_")} for m in bilan["mises_a_jour"]
        ],
        "nouvelles_branches": [
            {k: v for k, v in n.items() if not k.startswith("_")}
            for n in bilan["nouvelles_branches"]
        ],
    }


def _message(erreur: APIException) -> str:
    detail = erreur.detail
    if isinstance(detail, dict):
        return " ".join(str(v[0] if isinstance(v, list) and v else v) for v in detail.values())
    if isinstance(detail, list):
        return " ".join(str(v) for v in detail)
    return str(detail)


@transaction.atomic
def appliquer_dqe(
    projet,
    lignes: list,
    *,
    utilisateur,
    motif: str = "",
    request=None,
    montants_visibles: bool = True,
) -> dict:
    """Refait le bilan sur les lignes reçues, puis applique ce qu'il accepte, ligne par ligne."""
    from apps.projets.services import arbre as gestes
    from apps.projets.services.reprogrammation import planifier_element
    from apps.projets.services.tableau_demarrage import appliquer_tableau

    bilan = bilan_dqe(
        projet,
        lignes,
        utilisateur=utilisateur,
        request=request,
        montants_visibles=montants_visibles,
    )
    motif = (motif or "").strip()
    if bilan["motif_requis"] and len(motif) < LONGUEUR_MIN_MOTIF:
        raise ValidationError(
            {
                "motif": "L'import modifie des tâches déjà commencées : un motif d'au moins "
                f"{LONGUEUR_MIN_MOTIF} caractères est obligatoire."
            }
        )
    refus = list(bilan["refus"])
    appliquees = []
    for maj in bilan["mises_a_jour"]:
        examen = maj["_examen"]
        try:
            with transaction.atomic():
                # Relue à chaque ligne : la planification enregistre la case entière, elle doit
                # porter la quantité et le montant que la ligne vient de changer.
                feuille = Element.objects.get(pk=maj["element_id"])
                if examen["chiffrer"]:
                    feuille = gestes.modifier_element(
                        feuille,
                        donnees=examen["chiffrer"],
                        auteur=utilisateur,
                        motif=motif,
                        evenement="IMPORT_DQE",
                        tracer_toujours=True,
                        recalculer=False,
                    )
                if examen["dates"]:
                    debut, fin = examen["dates"]
                    planifier_element(feuille, date_debut=debut, date_fin=fin, auteur=utilisateur)
            appliquees.append(maj["ligne"])
        except APIException as erreur:
            refus.append(
                {
                    "ligne": maj["ligne"],
                    "chemin": maj["chemin"],
                    "code": getattr(erreur, "code_metier", None) or "refusee",
                    "message": _message(erreur),
                }
            )

    cases_creees = 0
    branches = [n["_ligne"] for n in bilan["nouvelles_branches"]]
    if branches:
        try:
            with transaction.atomic():
                resultat = appliquer_tableau(
                    projet,
                    niveaux=_niveaux(charger_arbre(projet)),
                    lignes=[
                        {k: v for k, v in ligne.items() if k != "numero"} for ligne in branches
                    ],
                    confirmer_avertissements=True,
                    auteur=utilisateur,
                )
            cases_creees = resultat["cases_creees"]
        except APIException as erreur:
            for nouvelle in bilan["nouvelles_branches"]:
                refus.append(
                    {
                        "ligne": nouvelle["ligne"],
                        "chemin": nouvelle["chemin"],
                        "code": getattr(erreur, "code_metier", None) or "refusee",
                        "message": _message(erreur),
                    }
                )
            branches = []

    from apps.projets.services.avancement import recalculer_avancements_projet

    recalculer_avancements_projet(projet)
    gestes._tracer(
        projet,
        utilisateur,
        "IMPORT_DQE",
        apres={
            "mises_a_jour": len(appliquees),
            "nouvelles_feuilles": len(branches),
            "cases_creees": cases_creees,
            "refus": len(refus),
        },
        motif=motif,
    )
    refus.sort(key=lambda r: r["ligne"])
    return {
        "mises_a_jour": appliquees,
        "nouvelles_feuilles": [n["ligne"] for n in bilan["nouvelles_branches"]] if branches else [],
        "cases_creees": cases_creees,
        "refus": refus,
        "inchangees": bilan["inchangees"],
        "resume": {
            "mises_a_jour": len(appliquees),
            "nouvelles_feuilles": len(branches),
            "cases_creees": cases_creees,
            "refus": len(refus),
            "inchangees": len(bilan["inchangees"]),
        },
    }
