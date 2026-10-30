"""L'arbre d'un projet tel que l'API le rend — filtré par périmètre, montants masqués au besoin.

**Ce que chacun voit** (décisions v1.2, §13bis) :
- `projets.voir_tout` (ou tout le projet en périmètre de lecture) : tout l'arbre ;
- sinon, les branches de son périmètre, **plus le chemin qui y mène** : les ancêtres apparaissent
  avec leur intitulé et leur niveau seulement (`acces = "CHEMIN"`), sans leurs données ;
- `projets.voir_montants` reste indépendante : sans elle, montants, enveloppes et poids sont nuls.
"""

from __future__ import annotations

from apps.core.droits import peut_voir_montants
from apps.projets.models import AffectationEquipeElement
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.perimetres import perimetre_de
from apps.projets.services.sante_calculs import calculer_arbre

__all__ = ["representer_arbre", "representer_case", "visibilite"]

COMPLET = "COMPLET"
CHEMIN = "CHEMIN"


def visibilite(arbre, utilisateur, request=None) -> dict:
    """`{element_id: COMPLET | CHEMIN}` des cases visibles ; absente : invisible."""
    perimetre = perimetre_de(utilisateur, arbre.projet, request)
    # `voir_tout` donne tout le projet, quel que soit le périmètre où elle est accordée.
    if perimetre.peut_quelque_part("projets.voir_tout") or perimetre.peut("projets.lire"):
        return {e.pk: COMPLET for e in arbre.elements}
    chemins = perimetre.chemins("projets.lire") or []
    acces: dict = {}
    for element in arbre.elements:
        if any(element.chemin.startswith(c) for c in chemins):
            acces[element.pk] = COMPLET
            for ancetre in arbre.ancetres(element):
                acces.setdefault(ancetre.pk, CHEMIN)
    return acces


def _equipes_par_case(arbre) -> dict:
    """Les équipes posées sur chaque case — directement, et par héritage (la plus précise
    l'emporte : une affectation posée plus bas remplace celle d'en haut pour cette branche)."""
    directes: dict = {}
    for affectation in AffectationEquipeElement.objects.filter(
        element__projet=arbre.projet, equipe__est_actif=True
    ).select_related("equipe", "equipe__entreprise_partenaire"):
        directes.setdefault(affectation.element_id, []).append(
            {
                "affectation_id": str(affectation.pk),
                "equipe_id": str(affectation.equipe_id),
                "nom": affectation.equipe.nom,
                "nature": affectation.equipe.nature,
            }
        )
    effectives: dict = {}
    for element in arbre.elements:
        porteur = next(
            (c for c in [element, *reversed(arbre.ancetres(element))] if c.pk in directes),
            None,
        )
        if porteur is not None:
            effectives[element.pk] = (porteur, directes[porteur.pk])
    return directes, effectives


def representer_case(element, arbre, resultats, numeros, montants_visibles, equipes, acces):
    _directes, effectives = equipes
    feuille = arbre.est_feuille(element)
    base = {
        "id": str(element.pk),
        "parent_id": str(element.parent_id) if element.parent_id else None,
        "libelle": element.libelle,
        "numero": numeros.get(element.pk),
        "niveau": {
            "id": str(element.niveau_id),
            "ordre": arbre.niveau(element).ordre if arbre.niveau(element) else None,
            "libelle": arbre.niveau(element).libelle if arbre.niveau(element) else None,
        },
        "est_feuille": feuille,
        "acces": acces,
    }
    if acces != COMPLET:
        return base
    resultat = resultats.get(element.pk)
    somme_enfants = None
    if not feuille:
        # La somme des poids des enfants chiffrés, à comparer à l'enveloppe (§8).
        poids = [
            resultats[e.pk].poids
            for e in arbre.enfants_actifs(element)
            if resultats.get(e.pk) and resultats[e.pk].poids
        ]
        somme_enfants = int(sum(poids)) if poids else None
    titulaire = arbre.titulaire_id(element)
    porteur, liste_equipes = effectives.get(element.pk, (None, []))
    donnees = {
        **base,
        "code": element.code,
        "ordre": element.ordre,
        "est_actif": element.est_actif,
        "statut": element.statut,
        "suspendu": arbre.suspendu(element),
        "cloture": element.cloture,
        "commence": arbre.commence(element),
        "motif": element.motif,
        # Mesure (feuilles)
        "mode_mesure": element.mode_mesure if feuille else None,
        "unite": element.unite if feuille else None,
        "quantite_initiale": element.quantite_initiale if feuille else None,
        "quantite_prevue": element.quantite_prevue if feuille else None,
        "quantite_realisee": element.quantite_realisee if feuille else None,
        "pourcentage_declare": element.pourcentage_declare if feuille else None,
        "a_completer": bool(
            feuille
            and element.mode_mesure == "QUANTITE"
            and (not element.unite or not element.quantite_prevue)
        ),
        # Avancement (F3 sur l'arbre)
        "avancement": resultat.physique if resultat else None,
        "avancement_partiel": bool(resultat and resultat.partiel),
        "avancement_disponible": bool(resultat and resultat.physique is not None),
        # Montants (§8)
        "poids": int(resultat.poids) if resultat and resultat.poids else None,
        "montant": element.montant if feuille else None,
        "montant_initial": element.montant_initial if feuille else None,
        "enveloppe": element.enveloppe if not feuille else None,
        "somme_enfants": somme_enfants,
        "depasse_enveloppe": bool(
            not feuille
            and element.enveloppe
            and somme_enfants
            and somme_enfants > element.enveloppe
        ),
        # Dates (§11)
        "date_debut_prevue": element.date_debut_prevue,
        "date_fin_prevue": element.date_fin_prevue,
        "date_debut_baseline": element.date_debut_baseline,
        "date_fin_baseline": element.date_fin_baseline,
        "date_debut_reelle": element.date_debut_reelle,
        "date_fin_reelle": element.date_fin_reelle,
        # Exécution : propre à la case, puis effective (héritée du plus proche ancêtre)
        "mode_execution": element.mode_execution,
        "mode_execution_effectif": arbre.mode_execution(element),
        "type_bordereau": element.type_bordereau,
        "type_bordereau_effectif": arbre.type_bordereau(element),
        "titulaire_id": str(element.titulaire_id) if element.titulaire_id else None,
        "titulaire_effectif_id": str(titulaire) if titulaire else None,
        # Équipes : posées ici, ou héritées de la case la plus proche qui en porte
        "equipes": liste_equipes,
        "equipes_heritees_de": (
            str(porteur.pk) if porteur is not None and porteur.pk != element.pk else None
        ),
    }
    if not montants_visibles:
        for champ in ("poids", "montant", "montant_initial", "enveloppe", "somme_enfants"):
            donnees[champ] = None
        donnees["depasse_enveloppe"] = False
    return donnees


def representer_arbre(projet, utilisateur, request=None, *, a_plat: bool = False) -> dict:
    """L'arbre du projet, imbriqué (`enfants`) ou à plat, avec son gabarit."""
    arbre = charger_arbre(projet)
    resultats = calculer_arbre(arbre)
    numeros = arbre.numerotation()
    acces = visibilite(arbre, utilisateur, request)
    montants = peut_voir_montants(utilisateur, request)
    equipes = _equipes_par_case(arbre)

    def noeud(element):
        donnees = representer_case(
            element, arbre, resultats, numeros, montants, equipes, acces[element.pk]
        )
        if not a_plat:
            donnees["enfants"] = [noeud(e) for e in arbre.enfants(element) if e.pk in acces]
        return donnees

    if a_plat:
        ordonnes = sorted(
            arbre.elements, key=lambda e: [int(x) for x in numeros.get(e.pk, "0").split(".")]
        )
        cases = [noeud(e) for e in ordonnes if e.pk in acces]
    else:
        cases = [noeud(e) for e in arbre.racines() if e.pk in acces]

    from apps.projets.services.sante_calculs import resultat_projet

    total = resultat_projet(projet, arbre, resultats)
    return {
        "projet_id": str(projet.pk),
        "niveaux": [
            {
                "id": str(n.pk),
                "ordre": n.ordre,
                "libelle": n.libelle,
                "alerter": n.alerter,
                "liste": _reference(n),
            }
            for n in arbre.niveaux
        ],
        "avancement": total.physique,
        "avancement_disponible": total.physique is not None,
        "avancement_partiel": total.partiel,
        "voit_tout": all(v == COMPLET for v in acces.values())
        and len(acces) == len(arbre.elements),
        "cases": cases,
    }


def _reference(niveau):
    from apps.projets.services.listes_modeles import reference_liste

    return reference_liste(niveau.liste_plateforme or niveau.liste_entreprise)
