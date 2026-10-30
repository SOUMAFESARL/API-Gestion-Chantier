"""Le journal connaît les équipes (décision du 30/10/2026, point 6).

- **Les équipes du journal** sont celles affectées aux tâches du rédacteur, y compris par
  héritage (l'affectation la plus précise l'emporte). Leurs membres sont ceux de l'équipe à la
  date du journal (arrivés, pas encore partis).
- **Les présents se cochent équipe par équipe**, avec les heures de l'équipe : ils remplacent les
  effectifs par catégorie. Une équipe est **attendue** quand elle tient une tâche en régie ou en
  sous-traitance structurée commencée à cette date ; sa ligne est alors requise. Pour une tâche
  en sous-traitance structurée, la ligne de l'équipe partenaire remplace « présence du
  sous-traitant », qualité comprise.
- **La production par ouvrier** reste réservée aux tâches suivies à la production (tâcherons) :
  l'ouvrier se choisit parmi les membres de l'équipe de la tâche.
- **Transition** : une tâche sans équipe garnie de membres garde l'ancienne saisie (effectifs
  par catégorie, présence du sous-traitant, intervenant en texte libre).

Ajouter une personne au registre de main-d'œuvre exige toujours sa permission : le journal ne
l'ouvre pas (décision 6.4).
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
    "cle_production",
    "controler_equipes",
    "effectif_present",
    "equipes_du_journal",
    "exiger_equipes",
    "feuilles_sans_equipe",
]

#: Les modes dont les tâches font cocher la présence de leurs équipes.
MODES_PRESENCE = (ModeExecution.REGIE, ModeExecution.SOUS_TRAITANCE_STRUCTUREE)


def _commencee(feuille, jour) -> bool:
    return feuille.date_debut_prevue is None or feuille.date_debut_prevue <= jour


def equipes_du_journal(cases, jour: date) -> list[dict]:
    """Les équipes des tâches du journal, avec leurs membres à la date `jour`."""
    _directes, effectives = equipes_par_case(cases.arbre)
    table_modes = table_modes_execution()
    portees: dict[str, dict] = {}
    for identifiant, feuille in cases.feuilles.items():
        _porteur, liste = effectives.get(feuille.pk, (None, []))
        base = mode_base(cases.mode(feuille), table_modes)
        for equipe in liste:
            portee = portees.setdefault(
                equipe["equipe_id"], {"activites": [], "modes": set(), "modes_du_jour": set()}
            )
            portee["activites"].append(identifiant)
            portee["modes"].add(base)
            if _commencee(feuille, jour):
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
        presence = bool(liste) and bool(portee["modes"] & set(MODES_PRESENCE))
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
                # La présence de l'équipe se coche dans le journal.
                "presence": presence,
                # Sa ligne est requise : elle tient une tâche commencée à cette date.
                "attendue": presence and bool(portee["modes_du_jour"] & set(MODES_PRESENCE)),
                # Une tâche en sous-traitance structurée : la qualité est notée.
                "qualite": presence and ModeExecution.SOUS_TRAITANCE_STRUCTUREE in portee["modes"],
                "membres": liste,
            }
        )
    return equipes


def feuilles_sans_equipe(cases, equipes, mode) -> bool:
    """Une tâche de ce mode n'a aucune équipe garnie de membres : l'ancienne saisie demeure."""
    table_modes = table_modes_execution()
    couvertes = {a for e in equipes if e["membres"] for a in e["activites"]}
    return any(
        identifiant not in couvertes and mode_base(cases.mode(feuille), table_modes) == mode
        for identifiant, feuille in cases.feuilles.items()
    )


def cle_production(ligne) -> tuple:
    """Une ligne de production par tâche et par ouvrier (ou par intervenant nommé)."""
    return (ligne["activite_id"], ligne.get("personne_id") or ligne.get("intervenant", ""))


def controler_equipes(saisie, equipes, refuser=None) -> None:
    """La forme des lignes d'équipe et de production ; complète le nom des ouvriers choisis.

    `refuser(section, ligne, motif)` : au retour du réseau, la ligne fautive est écartée et
    signalée au lieu de faire échouer tout l'envoi ; un présent qui a quitté l'équipe est retiré
    de sa ligne.
    """

    def ecarter(section, ligne, motif) -> None:
        if refuser is None:
            raise ValidationError({section: motif})
        refuser(section, ligne, motif)

    par_id = {e["equipe_id"]: e for e in equipes}
    gardees, presents_par_equipe = [], {}
    for ligne in saisie["equipes"]:
        equipe = par_id.get(ligne["equipe_id"])
        if equipe is None or not equipe["presence"] or ligne["equipe_id"] in presents_par_equipe:
            ecarter(
                "equipes",
                ligne,
                "Équipe extérieure au journal, sans présence à cocher ou dupliquée.",
            )
            continue
        membres = {m["personne_id"] for m in equipe["membres"]}
        partis = [p for p in ligne["presents"] if p not in membres]
        if partis and refuser is None:
            raise ValidationError(
                {"equipes": f"{equipe['nom']} : un présent n'est pas membre de l'équipe ce jour."}
            )
        for personne in partis:
            refuser(
                "equipes",
                {"equipe_id": ligne["equipe_id"], "personne_id": personne},
                f"{equipe['nom']} : cette personne n'est plus membre de l'équipe ce jour.",
            )
        ligne["presents"] = [p for p in ligne["presents"] if p in membres]
        ligne["retards"] = [p for p in ligne["retards"] if p in membres]
        gardees.append(ligne)
        presents_par_equipe[ligne["equipe_id"]] = set(ligne["presents"])
    saisie["equipes"] = gardees
    gardees = []
    for ligne in saisie["production"]:
        garnies = [e for e in equipes if ligne["activite_id"] in e["activites"] and e["membres"]]
        if not garnies:
            if ligne["personne_id"]:
                ecarter("production", ligne, "Cette tâche n'a pas d'équipe affectée.")
            else:
                gardees.append(ligne)
            continue
        if not ligne["personne_id"]:
            ecarter(
                "production", ligne, "Choisir l'ouvrier parmi les membres de l'équipe de la tâche."
            )
            continue
        equipe, membre = next(
            (
                (e, m)
                for e in garnies
                for m in e["membres"]
                if m["personne_id"] == ligne["personne_id"]
            ),
            (None, None),
        )
        if membre is None:
            ecarter(
                "production", ligne, "L'ouvrier n'est pas membre de l'équipe de la tâche ce jour."
            )
            continue
        presents = presents_par_equipe.get(equipe["equipe_id"])
        if presents is not None and ligne["personne_id"] not in presents:
            ecarter("production", ligne, f"{membre['nom']} n'est pas coché présent.")
            continue
        ligne["intervenant"] = membre["nom"]
        gardees.append(ligne)
    saisie["production"] = gardees


def exiger_equipes(saisie, equipes, exiger) -> None:
    """À la soumission : une ligne par équipe attendue ; une absence ou un retard se motive."""
    lignes = {ligne["equipe_id"]: ligne for ligne in saisie["equipes"]}
    for equipe in equipes:
        ligne = lignes.get(equipe["equipe_id"])
        if ligne is None:
            exiger(not equipe["attendue"], "equipes", f"{equipe['nom']} : présence à cocher.")
            continue
        manquants = len(equipe["membres"]) - len(ligne["presents"])
        exiger(
            not (manquants or ligne["retards"]) or bool(ligne["observation"].strip()),
            "equipes",
            f"{equipe['nom']} : une absence ou un retard exige un motif.",
        )
        exiger(
            not ligne["presents"] or ligne["heures"] is not None,
            "equipes",
            f"{equipe['nom']} : les heures de l'équipe sont requises.",
        )
        exiger(
            not (equipe["qualite"] and ligne["presents"]) or bool(ligne["qualite"]),
            "equipes",
            f"{equipe['nom']} : la qualité du travail est requise.",
        )


def effectif_present(saisie) -> int:
    """Les présents du jour : les effectifs par catégorie, plus les personnes cochées
    (une personne membre de deux équipes ne compte qu'une fois)."""
    categories = sum(ligne["presents"] or 0 for ligne in saisie.get("effectifs", []))
    personnes = {p for ligne in saisie.get("equipes", []) for p in ligne["presents"]}
    return categories + len(personnes)
