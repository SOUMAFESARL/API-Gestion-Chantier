"""Pointage nominatif par équipe et rattachement des travaux aux équipes du chantier.

- **Les équipes du journal** sont toutes celles affectées aux feuilles du périmètre du rédacteur,
  y compris par héritage dans l'arbre (`equipes_par_case`), quel que soit le mode d'exécution
  (régie, sous-traitance structurée ou tâcheronnat). Leurs membres sont ceux actifs dans l'équipe
  à la date du journal (arrivés, pas encore partis).
- **Pointage nominatif unifié** : les présents et retards se cochent équipe par équipe avec les
  heures travaillées.
- **Garde-fou travaux ↔ équipes (A3)** : toute feuille ayant progressé ce jour doit désigner au
  moins une équipe affectée comptant au moins un membre coché présent avec des heures > 0. Une
  équipe sans tâche travaillée ce jour ne bloque pas la soumission.
"""

from __future__ import annotations

from datetime import date

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.core.enums import ModeExecution
from apps.projets.models import EquipeChantier, MembreEquipeChantier
from apps.projets.selectors.arbre_api import equipes_par_case
from apps.projets.services.referentiels import mode_base, table_modes_execution

__all__ = [
    "controler_equipes",
    "effectif_present",
    "equipes_du_journal",
    "equipes_par_feuille",
    "exiger_equipes",
]


def _commencee(feuille, jour: date) -> bool:
    return feuille.date_debut_prevue is None or feuille.date_debut_prevue <= jour


def equipes_par_feuille(cases) -> dict[str, list[str]]:
    """Pour chaque feuille du journal (`str(pk)`), la liste des `equipe_id` affectées."""
    _directes, effectives = equipes_par_case(cases.arbre)
    resultat: dict[str, list[str]] = {}
    for identifiant, feuille in cases.feuilles.items():
        _porteur, liste = effectives.get(feuille.pk, (None, []))
        resultat[identifiant] = [str(equipe["equipe_id"]) for equipe in liste]
    return resultat


def equipes_du_journal(cases, jour: date) -> list[dict]:
    """Les équipes affectées aux feuilles du journal, avec leurs membres à la date `jour`."""
    _directes, effectives = equipes_par_case(cases.arbre)
    table_modes = table_modes_execution()
    portees: dict[str, dict] = {}
    for identifiant, feuille in cases.feuilles.items():
        _porteur, liste = effectives.get(feuille.pk, (None, []))
        base = mode_base(cases.mode(feuille), table_modes)
        for equipe in liste:
            eid = str(equipe["equipe_id"])
            portee = portees.setdefault(
                eid, {"activites": [], "modes": set(), "modes_du_jour": set()}
            )
            portee["activites"].append(identifiant)
            portee["modes"].add(base)
            if _commencee(feuille, jour) or cases.arbre.commence(feuille):
                portee["modes_du_jour"].add(base)
    if not portees:
        return []
    membres: dict[str, list[dict]] = {}
    for membre in (
        MembreEquipeChantier.objects.filter(
            equipe_id__in=portees, date_arrivee__lte=jour, personne__est_actif=True
        )
        .filter(Q(date_depart__isnull=True) | Q(date_depart__gte=jour))
        .select_related("personne")
    ):
        membres.setdefault(str(membre.equipe_id), []).append(
            {
                "personne_id": str(membre.personne_id),
                "nom": membre.personne.nom_complet,
                "fonction": membre.fonction,
                "est_chef": membre.est_chef,
            }
        )
    equipes = []
    for equipe in EquipeChantier.objects.filter(pk__in=portees).select_related(
        "entreprise_partenaire"
    ):
        identifiant = str(equipe.pk)
        portee, liste = portees[identifiant], membres.get(identifiant, [])
        presence = bool(liste)
        equipes.append(
            {
                "equipe_id": identifiant,
                "nom": equipe.nom,
                "nature": equipe.nature,
                "entreprise": equipe.entreprise_partenaire.raison_sociale
                if equipe.entreprise_partenaire
                else "",
                "corps_etat": equipe.corps_etat,
                "activites": portee["activites"],
                "presence": presence,
                "attendue": presence and bool(portee["modes_du_jour"]),
                "qualite": presence and ModeExecution.SOUS_TRAITANCE_STRUCTUREE in portee["modes"],
                "membres": liste,
            }
        )
    return equipes


def controler_equipes(saisie: dict, equipes: list[dict], refuser=None) -> None:
    """Valide le pointage des équipes et les équipes rattachées aux feuilles travaillées.

    `refuser(section, ligne, motif)` : au retour du réseau, la référence fautive est écartée et
    signalée au lieu de faire échouer tout l'envoi.
    """

    def ecarter(section: str, ligne: dict, motif: str) -> None:
        if refuser is None:
            raise ValidationError({section: motif})
        refuser(section, ligne, motif)

    par_id = {e["equipe_id"]: e for e in equipes}
    gardees, presents_par_equipe = [], {}
    for ligne in saisie.get("equipes", []):
        eid = str(ligne["equipe_id"])
        ligne["equipe_id"] = eid
        equipe = par_id.get(eid)
        if equipe is None or eid in presents_par_equipe:
            ecarter(
                "equipes",
                ligne,
                "Équipe extérieure au journal ou dupliquée.",
            )
            continue
        membres = {m["personne_id"] for m in equipe["membres"]}
        presents_str = [str(p) for p in ligne.get("presents", [])]
        retards_str = [str(p) for p in ligne.get("retards", [])]
        partis = [p for p in presents_str if p not in membres]
        if partis and refuser is None:
            raise ValidationError(
                {"equipes": f"{equipe['nom']} : un présent n'est pas membre de l'équipe ce jour."}
            )
        for personne in partis:
            refuser(
                "equipes",
                {"equipe_id": eid, "personne_id": personne},
                f"{equipe['nom']} : cette personne n'est plus membre de l'équipe ce jour.",
            )
        ligne["presents"] = [p for p in presents_str if p in membres]
        ligne["retards"] = [p for p in retards_str if p in membres and p in set(ligne["presents"])]
        gardees.append(ligne)
        presents_par_equipe[eid] = set(ligne["presents"])
    saisie["equipes"] = gardees

    for ligne in saisie.get("activites", []):
        act_id = str(ligne["activite_id"])
        equipes_valides = []
        for eid_brut in ligne.get("equipe_ids", []):
            eid = str(eid_brut)
            equipe = par_id.get(eid)
            if equipe is None or act_id not in equipe["activites"]:
                ecarter(
                    "activites",
                    {"activite_id": act_id, "equipe_id": eid},
                    "Cette équipe n'est pas affectée à cette tâche.",
                )
                continue
            if eid not in equipes_valides:
                equipes_valides.append(eid)
        ligne["equipe_ids"] = equipes_valides


def exiger_equipes(
    saisie: dict,
    equipes: list[dict],
    lignes_ayant_avance: list[tuple[dict, str]],
    exiger,
) -> None:
    """À la soumission : valide les équipes pointées et impose au moins une équipe active par
    feuille ayant avancé ce jour (garde-fou A3)."""
    par_id = {e["equipe_id"]: e for e in equipes}
    pointages = {str(ligne["equipe_id"]): ligne for ligne in saisie.get("equipes", [])}

    for eid, ligne in pointages.items():
        equipe = par_id.get(eid)
        if equipe is None:
            continue
        presents = ligne.get("presents", [])
        retards = ligne.get("retards", [])
        if presents:
            exiger(
                (ligne.get("heures") or 0) > 0,
                "equipes",
                f"{equipe['nom']} : les heures travaillées (> 0) de l'équipe sont requises.",
            )
            exiger(
                not equipe["qualite"] or bool(ligne.get("qualite")),
                "equipes",
                f"{equipe['nom']} : l'appréciation de conformité est requise.",
            )
            manquants = len(equipe["membres"]) - len(presents)
            exiger(
                not (manquants > 0 or retards) or bool((ligne.get("observation") or "").strip()),
                "equipes",
                f"{equipe['nom']} : une absence ou un retard exige un motif en observation.",
            )
        elif retards:
            exiger(False, "equipes", f"{equipe['nom']} : un retard suppose un membre présent.")

    for ligne_act, libelle in lignes_ayant_avance:
        equipe_ids = [str(e) for e in ligne_act.get("equipe_ids", [])]
        exiger(
            bool(equipe_ids),
            "activites",
            f"{libelle} : rattacher au moins une équipe affectée ayant réalisé ces travaux.",
        )
        if equipe_ids:
            equipe_active = any(
                bool(pointages.get(eid, {}).get("presents"))
                and (pointages.get(eid, {}).get("heures") or 0) > 0
                for eid in equipe_ids
            )
            exiger(
                equipe_active,
                "activites",
                f"{libelle} : au moins une équipe rattachée doit compter un présent (> 0 h).",
            )


def effectif_present(saisie: dict) -> int:
    """Les présents du jour : personnes uniques cochées (+ historique catégories)."""
    categories = sum(ligne.get("presents") or 0 for ligne in saisie.get("effectifs", []))
    personnes = {str(p) for ligne in saisie.get("equipes", []) for p in ligne.get("presents", [])}
    return categories + len(personnes)
