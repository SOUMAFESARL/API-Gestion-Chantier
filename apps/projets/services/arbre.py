"""Les gestes de modification de l'arbre d'un projet (décisions v1.2, §2, §10 et §12).

Le tableau sert à créer ; **la modification passe par des gestes explicites**, parce que changer
une cellule serait ambigu (renommer ou déplacer ?) : ajouter, renommer, déplacer, détailler,
insérer un niveau, désactiver, suspendre, clôturer.

**Règles de l'arbre**, vérifiées à chaque geste :

| #   | Règle                                                                            |
| A-1 | Un enfant est au niveau de son parent (récursion) ou au niveau suivant           |
| A-2 | Les enfants d'une case sont tous du même niveau                                  |
| A-5 | Une feuille commencée ne se découpe pas directement : on la « détaille »        |
| A-6 | Deux frères ne portent pas le même intitulé (sans accents, casse ni espaces)     |

**Modification tracée** (§12.2) : toute modification qui touche une case **commencée** (ajout
sous elle, déplacement, changement de montant ou de quantité prévue, désactivation, détail)
exige un motif et entre au journal d'audit.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.enums import ActionAudit
from apps.core.exceptions import ErreurConflit, ErreurMetier
from apps.projets.models import Element, MiseAJourInline, ModeMesure, NiveauProjet
from apps.projets.selectors.arbre import charger_arbre

__all__ = [
    "LIBELLE_GENERAL",
    "LIBELLE_REALISE_AVANT_DETAIL",
    "ajouter_element",
    "ajouter_niveau",
    "apercu_deplacement",
    "cloturer_feuille",
    "deplacer_element",
    "desactiver_element",
    "detailler_feuille",
    "dupliquer_branche",
    "inserer_niveau",
    "mesurer_feuille",
    "modifier_element",
    "modifier_niveau",
    "reactiver_element",
    "rouvrir_feuille",
    "supprimer_element",
    "suspendre_element",
]

LIBELLE_REALISE_AVANT_DETAIL = "Réalisé avant détail"
LIBELLE_GENERAL = "Général"


# --------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------
def _tracer(element_ou_projet, auteur, evenement: str, avant=None, apres=None, motif: str = ""):
    from apps.audit.services import journaliser

    journaliser(
        action=ActionAudit.MODIFICATION,
        type_entite="Element" if isinstance(element_ou_projet, Element) else "DecoupageProjet",
        entite_id=element_ou_projet.pk,
        utilisateur_id=getattr(auteur, "pk", None),
        valeur_avant=avant,
        valeur_apres={"evenement": evenement, "motif": motif, **(apres or {})},
    )


def _exiger_motif(motif: str, raison: str) -> str:
    propre = (motif or "").strip()
    if len(propre) < 10:
        raise ValidationError(
            {"motif": f"{raison} : un motif d'au moins 10 caractères est obligatoire."}
        )
    return propre


def _niveaux(projet) -> list[NiveauProjet]:
    return list(NiveauProjet.objects.filter(projet=projet).order_by("ordre"))


def _niveau_suivant(niveaux, niveau):
    rang = next(i for i, n in enumerate(niveaux) if n.pk == niveau.pk)
    return niveaux[rang + 1] if rang + 1 < len(niveaux) else None


def _verifier_nom_libre(projet, parent, libelle, exclure=None) -> None:
    """A-6, avec un message qui nomme le frère déjà présent."""
    cle = cle_comparaison(libelle)
    freres = Element.objects.filter(projet=projet, parent=parent, cle_comparaison=cle)
    if exclure is not None:
        freres = freres.exclude(pk=exclure.pk)
    frere = freres.first()
    if frere is not None:
        raise ErreurConflit(
            f"« {libelle} » existe déjà à cet endroit (sous le nom « {frere.libelle} »). "
            "Deux cases sœurs ne portent pas le même intitulé.",
            details={"libelle": libelle, "existant": str(frere.pk)},
        )


def _niveau_pour_enfant(arbre, niveaux, parent, niveau_demande=None) -> NiveauProjet:
    """Le niveau d'un nouvel enfant, selon A-1 et A-2."""
    if parent is None:
        racines = arbre.enfants_actifs(None)
        attendu = racines[0].niveau if racines else niveaux[0]
        if niveau_demande and niveau_demande.pk != attendu.pk:
            raise ErreurMetier(
                "Les cases du plus haut niveau sont toutes du premier niveau du gabarit (A-1)."
            )
        return attendu
    freres = arbre.enfants_actifs(parent)
    if freres:
        attendu = freres[0].niveau
        if niveau_demande and niveau_demande.pk != attendu.pk:
            raise ErreurMetier(
                f"Les enfants de « {parent.libelle} » sont tous du niveau « {attendu.libelle} » "
                "(A-2)."
            )
        return attendu
    possibles = [parent.niveau]
    suivant = _niveau_suivant(niveaux, parent.niveau)
    if suivant is not None:
        possibles.insert(0, suivant)
    if niveau_demande is None:
        return possibles[0]
    if niveau_demande.pk not in {n.pk for n in possibles}:
        raise ErreurMetier(
            "Un enfant est au niveau de son parent ou au niveau suivant : on ne saute pas de "
            "niveau (A-1)."
        )
    return niveau_demande


def _devenir_parent(parent) -> None:
    """Une feuille qui reçoit des enfants : son montant devient son enveloppe (§8, §12.3)."""
    if parent is not None and parent.montant and not parent.enveloppe:
        parent.enveloppe, parent.montant = parent.montant, None
        parent.save(update_fields=["enveloppe", "montant", "modifie_le"])


def _redevenir_feuille_si_besoin(parent) -> None:
    """Un parent qui perd son dernier enfant redevient une feuille ; son enveloppe, son montant."""
    if parent is None:
        return
    if (
        not parent.enfants.filter(est_actif=True).exists()
        and parent.enveloppe
        and not parent.montant
    ):
        parent.montant, parent.enveloppe = parent.enveloppe, None
        parent.save(update_fields=["montant", "enveloppe", "modifie_le"])


def _recalculer(projet) -> None:
    from apps.projets.services.avancement import recalculer_avancements_projet

    recalculer_avancements_projet(projet)


def _transferer_liens(ancienne_feuille, auteur) -> None:
    """Une feuille liée devient un parent : ses nouvelles feuilles reprennent ses liens."""
    from apps.projets.services.dependances import transferer_liens_aux_feuilles

    transferer_liens_aux_feuilles(ancienne_feuille, auteur=auteur)


def _retirer_liens(element, auteur, evenement: str) -> None:
    from apps.projets.services.dependances import retirer_liens_branche

    retirer_liens_branche(element, auteur=auteur, evenement=evenement)


def _reecrire_chemins(element) -> None:
    """Après un déplacement, chaque descendant reprend le chemin de son nouveau parent."""
    element.save()
    for enfant in element.enfants.all():
        _reecrire_chemins(enfant)


# --------------------------------------------------------------------------
# Ajouter, modifier
# --------------------------------------------------------------------------
CHAMPS_MESURE = {"mode_mesure", "unite", "quantite_prevue"}
CHAMPS_MONTANTS = {"montant", "enveloppe"}
CHAMPS_EXECUTION = {"mode_execution", "type_bordereau", "titulaire_id"}
CHAMPS_IDENTITE = {"libelle", "code", "ordre"}


@transaction.atomic
def ajouter_element(
    projet,
    *,
    parent=None,
    libelle: str,
    niveau=None,
    auteur=None,
    motif: str = "",
    **champs,
) -> Element:
    """Ajoute une case sous `parent` (ou à la racine), dans le respect de A-1, A-2, A-5, A-6."""
    libelle = " ".join((libelle or "").split())
    if not libelle:
        raise ValidationError({"libelle": "L'intitulé est obligatoire."})
    niveaux = _niveaux(projet)
    if not niveaux:
        raise ErreurMetier(
            "Ce projet n'a pas encore de découpage : commencez par le tableau de démarrage."
        )
    arbre = charger_arbre(projet)
    if parent is not None:
        parent = arbre.par_id[parent.pk]
        if arbre.est_feuille(parent) and arbre.commence(parent):
            raise ErreurMetier(
                f"« {parent.libelle} » est une tâche déjà commencée : pour la découper, utilisez "
                "« Détailler » (A-5).",
                details={"geste": "DETAILLER"},
            )
        if arbre.commence(parent):
            motif = _exiger_motif(motif, "Ajouter sous une case commencée")
    niveau = _niveau_pour_enfant(arbre, niveaux, parent, niveau)
    _verifier_nom_libre(projet, parent, libelle)
    ordre = champs.pop("ordre", None) or (len(arbre.enfants(parent)) + 1)
    parent_etait_feuille = parent is not None and arbre.est_feuille(parent)
    _devenir_parent(parent)
    try:
        element = Element.objects.create(
            projet=projet,
            parent=parent,
            niveau=niveau,
            libelle=libelle,
            ordre=ordre,
            cree_par=auteur,
            **champs,
        )
    except IntegrityError:
        raise ErreurConflit("Deux cases sœurs ne portent pas le même intitulé (A-6).") from None
    if parent_etait_feuille:
        _transferer_liens(parent, auteur)
    if motif:
        _tracer(element, auteur, "AJOUT_SOUS_CASE_COMMENCEE", motif=motif)
    _recalculer(projet)
    return element


@transaction.atomic
def modifier_element(
    element: Element,
    *,
    donnees: dict,
    auteur=None,
    motif: str = "",
    evenement: str = "MODIFICATION",
    tracer_toujours: bool = False,
    recalculer: bool = True,
) -> Element:
    """Renommer, recoder, chiffrer, métrer, régler l'exécution d'une case.

    - Une **feuille** porte mode de mesure, unité, quantité prévue et montant ; un **parent**,
      une enveloppe.
    - Sur une feuille commencée : la quantité prévue ne descend pas sous le réalisé, l'unité ne
      change plus, et changer la quantité ou le montant est une modification tracée (§11bis).
    - Les dates se planifient par `planifier_element` et se reprogramment par
      `reprogrammer_date_instance` : elles ne passent pas ici.

    Un geste en masse (l'import du DQE) nomme son `evenement`, trace chaque case touchée
    (`tracer_toujours`) et ne recalcule l'avancement qu'une fois, à la fin (`recalculer`).
    """
    arbre = charger_arbre(element.projet)
    element = arbre.par_id[element.pk]
    feuille = arbre.est_feuille(element)
    commence = arbre.commence(element)
    avant = {}
    champs = ["modifie_le"]

    if "libelle" in donnees:
        libelle = " ".join((donnees["libelle"] or "").split())
        if not libelle:
            raise ValidationError({"libelle": "L'intitulé est obligatoire."})
        if libelle != element.libelle:
            _verifier_nom_libre(element.projet, element.parent, libelle, exclure=element)
            avant["libelle"] = element.libelle
            element.libelle = libelle
            champs += ["libelle", "cle_comparaison"]
    for nom in ("code", "ordre"):
        if nom in donnees and donnees[nom] != getattr(element, nom):
            avant[nom] = getattr(element, nom)
            setattr(element, nom, donnees[nom] if donnees[nom] is not None else "")
            champs.append(nom)

    mesure_ou_montant = {k for k in donnees if k in CHAMPS_MESURE | {"montant"}}
    if mesure_ou_montant and not feuille:
        raise ErreurMetier(
            "La mesure et le montant se saisissent sur les tâches du bas (les feuilles) ; un "
            "parent porte une enveloppe."
        )
    if "enveloppe" in donnees and feuille and donnees["enveloppe"] is not None:
        raise ErreurMetier("Une feuille porte un montant ; l'enveloppe est celle d'un parent.")
    if commence and feuille:
        if "unite" in donnees and donnees["unite"] != element.unite:
            raise ErreurMetier(
                "L'unité d'une tâche commencée ne change plus : "
                "détaillez-la, ou créez-en une autre."
            )
        if "mode_mesure" in donnees and donnees["mode_mesure"] != element.mode_mesure:
            raise ErreurMetier("Le mode de mesure d'une tâche commencée ne change plus.")
        quantite = donnees.get("quantite_prevue", element.quantite_prevue)
        if (
            "quantite_prevue" in donnees
            and quantite is not None
            and quantite < (element.quantite_realisee or 0)
        ):
            raise ErreurMetier(
                "La quantité prévue ne descend pas sous le réalisé : corrigez le réalisé, ou "
                "clôturez la tâche si elle est terminée."
            )
        if {"quantite_prevue", "montant"} & set(donnees):
            motif = _exiger_motif(motif, "Modifier une tâche commencée")

    for nom in (*CHAMPS_MESURE, *CHAMPS_MONTANTS, "mode_execution", "type_bordereau"):
        if nom not in donnees:
            continue
        valeur = donnees[nom]
        if valeur is None and nom in {"mode_execution", "type_bordereau", "unite"}:
            valeur = ""
        if valeur != getattr(element, nom):
            avant[nom] = _serialisable(getattr(element, nom))
            setattr(element, nom, valeur)
            champs.append(nom)
    if "titulaire_id" in donnees and donnees["titulaire_id"] != element.titulaire_id:
        avant["titulaire_id"] = _serialisable(element.titulaire_id)
        element.titulaire_id = donnees["titulaire_id"]
        champs.append("titulaire")

    if len(champs) == 1:
        return element
    element.save(update_fields=list(dict.fromkeys(champs)))
    if motif or commence or tracer_toujours:
        _tracer(
            element,
            auteur,
            evenement,
            avant=avant,
            apres={k: _serialisable(getattr(element, k)) for k in avant},
            motif=motif,
        )
    if recalculer:
        _recalculer(element.projet)
    return element


def _serialisable(valeur):
    if valeur is None or isinstance(valeur, (str, int, bool)):
        return valeur
    return str(valeur)


# --------------------------------------------------------------------------
# Déplacer (§12.4)
# --------------------------------------------------------------------------
def _verifier_destination(arbre, element, nouveau_parent, geste: str = "déplace") -> None:
    """Où une case (et sa branche) peut se poser : déplacement (§12.4) ou copie (§13quinquies.1).

    Sous un parent du niveau juste au-dessus ou du même niveau (récursion), jamais dans sa
    propre branche, ni sous une tâche commencée (A-5), ni parmi des frères d'un autre niveau
    (A-2). L'intitulé (A-6) se vérifie à part : une copie en reçoit un nouveau.
    """
    if nouveau_parent is not None and nouveau_parent.chemin.startswith(element.chemin):
        raise ErreurMetier(f"Une case ne se {geste} pas sous elle-même ni sous ses descendants.")
    if nouveau_parent is None:
        if element.niveau.ordre != 1:
            raise ErreurMetier("Seule une case du premier niveau se place à la racine (A-1).")
    else:
        ordre_parent, ordre_case = nouveau_parent.niveau.ordre, element.niveau.ordre
        if ordre_case not in (ordre_parent, ordre_parent + 1):
            raise ErreurMetier(
                f"On {geste} une case sous un parent du niveau juste au-dessus, ou du même "
                "niveau (récursion) : on ne saute pas de niveau (A-1)."
            )
        if arbre.est_feuille(nouveau_parent) and arbre.commence(nouveau_parent):
            raise ErreurMetier(
                f"« {nouveau_parent.libelle} » est une tâche commencée : "
                "détaillez-la d'abord (A-5)."
            )
    freres = [e for e in arbre.enfants_actifs(nouveau_parent) if e.pk != element.pk]
    if freres and freres[0].niveau_id != element.niveau_id:
        raise ErreurMetier(
            f"Les enfants de la destination sont du niveau « {freres[0].niveau.libelle} » : une "
            "case d'un autre niveau ne s'y mêle pas (A-2)."
        )


def _verifier_deplacement(arbre, element, nouveau_parent) -> None:
    _verifier_destination(arbre, element, nouveau_parent)
    _verifier_nom_libre(arbre.projet, nouveau_parent, element.libelle, exclure=element)


def apercu_deplacement(element: Element, nouveau_parent: Element | None) -> dict:
    """Ce que le déplacement changerait, avant de confirmer (§12.4).

    L'avancement de l'ancien et du nouveau parent, avant et après ; l'ancien parent qui redevient
    une feuille, le nouveau qui devient un parent ; les feuilles qui changent de titulaire
    hérité ; les affectations dont le périmètre ne couvrira plus la case ; les prolongations
    qu'imposent les dates de la case.
    """
    from apps.projets.services.calendrier import prolongations_necessaires
    from apps.projets.services.sante_calculs import calculer_arbre

    arbre = charger_arbre(element.projet)
    element = arbre.par_id[element.pk]
    nouveau_parent = arbre.par_id[nouveau_parent.pk] if nouveau_parent is not None else None
    _verifier_deplacement(arbre, element, nouveau_parent)
    ancien_parent = arbre.par_id.get(element.parent_id)

    avant = calculer_arbre(arbre)
    feuilles = [f for f in [element, *arbre.descendants(element)] if arbre.est_feuille(f)]
    nouveau_devient_parent = nouveau_parent is not None and arbre.est_feuille(nouveau_parent)
    ancien_redevient_feuille = ancien_parent is not None and not [
        e for e in arbre.enfants_actifs(ancien_parent) if e.pk != element.pk
    ]
    titulaires_avant = {f.pk: arbre.titulaire_id(f) for f in feuilles}

    # Simulation en mémoire : rien n'est écrit.
    ancien_parent_id, ancien_chemin = element.parent_id, element.chemin
    arbre.enfants_de[ancien_parent_id] = [
        e for e in arbre.enfants_de[ancien_parent_id] if e.pk != element.pk
    ]
    element.parent_id = nouveau_parent.pk if nouveau_parent else None
    arbre.enfants_de[element.parent_id].append(element)
    prefixe = nouveau_parent.chemin if nouveau_parent else ""
    for case in [
        element,
        *[e for e in arbre.elements if e.chemin.startswith(ancien_chemin) and e.pk != element.pk],
    ]:
        case.chemin = prefixe + case.chemin[len(ancien_chemin) - len(f"{element.pk}/") :]
    apres = calculer_arbre(arbre)
    titulaires_apres = {f.pk: arbre.titulaire_id(f) for f in feuilles}
    prolongations = prolongations_necessaires(
        element, element.date_debut_prevue, element.date_fin_prevue, arbre
    )
    # On remet l'objet en état : il est partagé avec l'appelant.
    element.parent_id, element.chemin = ancien_parent_id, ancien_chemin

    def physique(resultats, case):
        r = resultats.get(case.pk) if case else None
        return r.physique if r else None

    from apps.projets.models import AffectationProjet

    perimetres_perdus = []
    for affectation in (
        AffectationProjet.objects.filter(
            projet=element.projet, est_actif=True, perimetres__isnull=False
        )
        .distinct()
        .select_related("utilisateur")
        .prefetch_related("perimetres")
    ):
        chemins = [p.chemin for p in affectation.perimetres.all()]
        couvrait = any(ancien_chemin.startswith(c) for c in chemins)
        couvrira = any((prefixe + f"{element.pk}/").startswith(c) for c in chemins) or any(
            c.startswith(ancien_chemin) for c in chemins
        )
        if couvrait and not couvrira:
            perimetres_perdus.append(
                {
                    "affectation_id": str(affectation.pk),
                    "utilisateur": affectation.utilisateur.nom_complet
                    if hasattr(affectation.utilisateur, "nom_complet")
                    else str(affectation.utilisateur),
                    "role_projet": affectation.role_projet,
                }
            )

    return {
        "element": {"id": str(element.pk), "libelle": element.libelle},
        "ancien_parent": {
            "id": str(ancien_parent.pk) if ancien_parent else None,
            "libelle": ancien_parent.libelle if ancien_parent else None,
            "avancement_avant": physique(avant, ancien_parent),
            "avancement_apres": physique(apres, ancien_parent),
            "redevient_feuille": ancien_redevient_feuille,
        },
        "nouveau_parent": {
            "id": str(nouveau_parent.pk) if nouveau_parent else None,
            "libelle": nouveau_parent.libelle if nouveau_parent else None,
            "avancement_avant": physique(avant, nouveau_parent),
            "avancement_apres": physique(apres, nouveau_parent),
            "devient_parent": nouveau_devient_parent,
        },
        "titulaires_changes": [
            {
                "id": str(f.pk),
                "libelle": f.libelle,
                "titulaire_avant": str(titulaires_avant[f.pk]) if titulaires_avant[f.pk] else None,
                "titulaire_apres": str(titulaires_apres[f.pk]) if titulaires_apres[f.pk] else None,
            }
            for f in feuilles
            if titulaires_avant[f.pk] != titulaires_apres[f.pk]
        ],
        "perimetres_perdus": perimetres_perdus,
        "prolongations": [p.en_dict() for p in prolongations],
        "modification_tracee": arbre.commence(element),
    }


@transaction.atomic
def deplacer_element(
    element: Element,
    nouveau_parent: Element | None,
    *,
    auteur=None,
    motif: str = "",
    prolonger: bool = False,
    autorise_a_prolonger: bool = False,
    justification: str = "",
    motif_report_id=None,
) -> Element:
    """Déplace une case et toute sa branche. Une case commencée exige un motif (§12.2) ; des
    dates qui débordent du nouveau parent exigent la confirmation de la prolongation (§11)."""
    arbre = charger_arbre(element.projet)
    element = arbre.par_id[element.pk]
    destination = arbre.par_id[nouveau_parent.pk] if nouveau_parent is not None else None
    _verifier_deplacement(arbre, element, destination)
    if arbre.commence(element):
        motif = _exiger_motif(motif, "Déplacer une case commencée")
    ancien_parent = arbre.par_id.get(element.parent_id)

    from apps.projets.services.calendrier import prolongations_necessaires

    simulation = Element(
        pk=element.pk,
        projet=element.projet,
        parent=destination,
        niveau=element.niveau,
        libelle=element.libelle,
        chemin=(destination.chemin if destination else "") + f"{element.pk}/",
    )
    if prolongations_necessaires(simulation, element.date_debut_prevue, element.date_fin_prevue):
        from apps.projets.services.reprogrammation import (
            ProlongationRequise,
            _appliquer_prolongations,
            _motif_valide,
        )

        if not prolonger:
            raise ProlongationRequise(
                details={
                    "prolongations": [
                        p.en_dict()
                        for p in prolongations_necessaires(
                            simulation, element.date_debut_prevue, element.date_fin_prevue
                        )
                    ]
                }
            )
        motif_report, justif = _motif_valide(motif_report_id, justification)
        _appliquer_prolongations(
            simulation,
            element.date_debut_prevue,
            element.date_fin_prevue,
            prolonger=True,
            autorise_a_prolonger=autorise_a_prolonger,
            motif=motif_report,
            justification=justif,
            auteur=auteur,
        )

    _devenir_parent(destination)
    element.parent = destination
    element.ordre = len(arbre.enfants_actifs(destination)) + 1
    _reecrire_chemins(element)
    _redevenir_feuille_si_besoin(ancien_parent)
    _tracer(
        element,
        auteur,
        "DEPLACEMENT",
        avant={"parent": str(ancien_parent.pk) if ancien_parent else None},
        apres={"parent": str(destination.pk) if destination else None},
        motif=motif,
    )
    _recalculer(element.projet)
    return element


# --------------------------------------------------------------------------
# Dupliquer une branche (§13quinquies.1)
# --------------------------------------------------------------------------
#: Ce que la copie reprend : la structure, les unités, les quantités, les montants, le mode et
#: le titulaire. Ni mesures, ni dates, ni baselines, ni affectations, ni équipes.
CHAMPS_COPIES = (
    "niveau_id",
    "mode_mesure",
    "unite",
    "quantite_prevue",
    "montant",
    "enveloppe",
    "mode_execution",
    "type_bordereau",
    "titulaire_id",
)
SUFFIXE_COPIE = "copie"


def intitule_de_copie(projet, parent, libelle: str) -> str:
    """« Murs RDC (copie) », puis « Murs RDC (copie 2) »… : le premier intitulé libre (A-6)."""
    pris = set(
        Element.objects.filter(projet=projet, parent=parent).values_list(
            "cle_comparaison", flat=True
        )
    )
    rang = 1
    while True:
        suffixe = f" ({SUFFIXE_COPIE})" if rang == 1 else f" ({SUFFIXE_COPIE} {rang})"
        candidat = libelle[: 200 - len(suffixe)] + suffixe
        if cle_comparaison(candidat) not in pris:
            return candidat
        rang += 1


@transaction.atomic
def dupliquer_branche(
    element: Element,
    *,
    destination: Element | None,
    libelle: str = "",
    auteur=None,
    motif: str = "",
) -> tuple[Element, int]:
    """Copie une case et sa branche active sous `destination` ; rend la copie et le nombre de
    cases créées.

    La copie se pose sous un parent autorisé, comme un déplacement (§12.4), et reçoit un
    intitulé unique parmi ses frères (A-6) : celui demandé, sinon « … (copie) ». Le code libre
    n'est pas repris (il numérote une ligne du bordereau du client) ; les cases désactivées ne
    sont pas copiées. Poser la copie sous une case commencée est une modification tracée.
    """
    arbre = charger_arbre(element.projet)
    element = arbre.par_id[element.pk]
    if not element.est_actif:
        raise ErreurMetier("Une case désactivée ne se duplique pas : réactivez-la d'abord.")
    destination = arbre.par_id[destination.pk] if destination is not None else None
    _verifier_destination(arbre, element, destination, geste="copie")
    if destination is not None and arbre.commence(destination):
        motif = _exiger_motif(motif, "Ajouter sous une case commencée")
    libelle = " ".join((libelle or "").split())
    if libelle:
        _verifier_nom_libre(element.projet, destination, libelle)
    else:
        libelle = intitule_de_copie(element.projet, destination, element.libelle)

    destination_etait_feuille = destination is not None and arbre.est_feuille(destination)
    _devenir_parent(destination)
    compte = 0

    def copier(source, parent, intitule, ordre):
        nonlocal compte
        copie = Element.objects.create(
            projet=source.projet,
            parent=parent,
            libelle=intitule,
            ordre=ordre,
            cree_par=auteur,
            **{champ: getattr(source, champ) for champ in CHAMPS_COPIES},
        )
        compte += 1
        for rang, enfant in enumerate(arbre.enfants_actifs(source), start=1):
            copier(enfant, copie, enfant.libelle, rang)
        return copie

    try:
        racine = copier(element, destination, libelle, len(arbre.enfants(destination)) + 1)
    except IntegrityError:
        raise ErreurConflit("Deux cases sœurs ne portent pas le même intitulé (A-6).") from None
    if destination_etait_feuille:
        _transferer_liens(destination, auteur)
    _tracer(
        racine,
        auteur,
        "DUPLICATION",
        apres={"source": str(element.pk), "cases_copiees": compte},
        motif=motif,
    )
    _tracer(
        element,
        auteur,
        "DUPLIQUEE",
        apres={"copie": str(racine.pk), "cases_copiees": compte},
        motif=motif,
    )
    _recalculer(element.projet)
    return racine, compte


# --------------------------------------------------------------------------
# Détailler une feuille (§12.5)
# --------------------------------------------------------------------------
@transaction.atomic
def detailler_feuille(
    feuille: Element,
    *,
    enfants: list[dict],
    niveau=None,
    auteur=None,
    motif: str = "",
) -> list[Element]:
    """La feuille devient un parent ; ses nouveaux enfants la détaillent.

    **Feuille commencée** : un premier enfant, « Réalisé avant détail », reçoit ses mesures, est
    clôturé à 100 % et reçoit un montant égal à ce qui a été réalisé (montant x avancement). Le
    montant d'origine devient l'**enveloppe** du parent, à répartir sur les nouveaux enfants :
    l'avancement du parent est **identique avant et après** (4 M acquis sur 10 M = 40 %).
    """
    from apps.projets.services.sante_calculs import calculer_avancement_physique_feuille

    arbre = charger_arbre(feuille.projet)
    feuille = arbre.par_id[feuille.pk]
    if not arbre.est_feuille(feuille):
        raise ErreurMetier("Seule une tâche du bas (une feuille) se détaille.")
    if not enfants:
        raise ValidationError({"enfants": "Indiquez au moins une nouvelle tâche."})
    niveaux = _niveaux(feuille.projet)
    niveau = _niveau_pour_enfant(arbre, niveaux, feuille, niveau)
    commencee = arbre.commence(feuille)
    if commencee:
        motif = _exiger_motif(motif, "Détailler une tâche commencée")

    noms = [" ".join((e.get("libelle") or "").split()) for e in enfants]
    if commencee:
        noms_cles = [cle_comparaison(n) for n in noms]
        if cle_comparaison(LIBELLE_REALISE_AVANT_DETAIL) in noms_cles:
            raise ValidationError(
                {"enfants": f"« {LIBELLE_REALISE_AVANT_DETAIL} » est créé automatiquement."}
            )
    if any(not n for n in noms):
        raise ValidationError({"enfants": "Chaque nouvelle tâche a un intitulé."})
    if len({cle_comparaison(n) for n in noms}) != len(noms):
        raise ConflitIntitule()

    crees = []
    avant = {
        "montant": feuille.montant,
        "quantite_prevue": _serialisable(feuille.quantite_prevue),
        "quantite_realisee": _serialisable(feuille.quantite_realisee),
    }
    if commencee:
        physique = Decimal(str(calculer_avancement_physique_feuille(feuille)))
        montant_realise = (
            int((Decimal(feuille.montant) * physique / 100).quantize(Decimal("1"), ROUND_HALF_UP))
            if feuille.montant
            else None
        )
        realise = Element.objects.create(
            projet=feuille.projet,
            parent=feuille,
            niveau=niveau,
            libelle=LIBELLE_REALISE_AVANT_DETAIL,
            ordre=1,
            mode_mesure=feuille.mode_mesure,
            unite=feuille.unite,
            quantite_prevue=feuille.quantite_realisee
            if feuille.mode_mesure == ModeMesure.QUANTITE
            else None,
            quantite_realisee=feuille.quantite_realisee or 0,
            pourcentage_declare=Decimal("100")
            if feuille.mode_mesure == ModeMesure.POURCENTAGE
            else None,
            montant=montant_realise,
            date_debut_prevue=feuille.date_debut_prevue,
            date_fin_prevue=feuille.date_fin_prevue,
            cloture=True,
            cloture_le=timezone.now(),
            cree_par=auteur,
        )
        crees.append(realise)
    # Le montant d'origine devient l'enveloppe du nouveau parent.
    feuille.enveloppe = feuille.montant if feuille.montant else feuille.enveloppe
    feuille.montant = None
    feuille.quantite_prevue = None
    feuille.quantite_realisee = 0
    feuille.pourcentage_declare = None
    feuille.cloture = False
    feuille.save()
    for rang, (donnees, nom) in enumerate(zip(enfants, noms, strict=True), start=len(crees) + 1):
        champs = {k: v for k, v in donnees.items() if k in CHAMPS_MESURE | {"montant", "code"}}
        crees.append(
            Element.objects.create(
                projet=feuille.projet,
                parent=feuille,
                niveau=niveau,
                libelle=nom,
                ordre=rang,
                date_debut_prevue=donnees.get("date_debut_prevue") or feuille.date_debut_prevue,
                date_fin_prevue=donnees.get("date_fin_prevue") or feuille.date_fin_prevue,
                cree_par=auteur,
                **champs,
            )
        )
    # Les sous-tâches héritent des prédécesseurs de la feuille ; ses successeurs les attendent
    # toutes (§13quinquies.5).
    _transferer_liens(feuille, auteur)
    _tracer(
        feuille,
        auteur,
        "DETAIL",
        avant=avant,
        apres={"enfants": [str(e.pk) for e in crees], "enveloppe": feuille.enveloppe},
        motif=motif,
    )
    _recalculer(feuille.projet)
    return crees


class ConflitIntitule(ErreurConflit):
    default_detail = "Deux nouvelles tâches sœurs ne portent pas le même intitulé (A-6)."


# --------------------------------------------------------------------------
# Niveaux du gabarit (§2, A-3, §12.6)
# --------------------------------------------------------------------------
def _verifier_libelle_niveau(projet, libelle, exclure=None) -> str:
    libelle = " ".join((libelle or "").split())
    if not libelle:
        raise ValidationError({"libelle": "Le libellé du niveau est obligatoire (C-3)."})
    for n in _niveaux(projet):
        if (exclure is None or n.pk != exclure.pk) and cle_comparaison(
            n.libelle
        ) == cle_comparaison(libelle):
            raise ErreurConflit(
                f"Le niveau « {n.libelle} » existe déjà : deux niveaux ne portent pas le même "
                "libellé (C-4)."
            )
    return libelle


@transaction.atomic
def modifier_niveau(niveau: NiveauProjet, *, donnees: dict) -> NiveauProjet:
    """Renommer un niveau est toujours permis (A-3) ; changer sa liste ne modifie aucune case
    déjà saisie (§4.8) ; « alerter à ce niveau » se coche ou se décoche."""
    from apps.catalogue.models import ListeValeursPlateforme
    from apps.projets.services.listes_modeles import resoudre_liste

    champs = ["modifie_le"]
    if "libelle" in donnees:
        niveau.libelle = _verifier_libelle_niveau(niveau.projet, donnees["libelle"], exclure=niveau)
        champs.append("libelle")
    if "liste" in donnees:
        liste = resoudre_liste(donnees["liste"])
        niveau.liste_plateforme = liste if isinstance(liste, ListeValeursPlateforme) else None
        niveau.liste_entreprise = (
            None if liste is None or isinstance(liste, ListeValeursPlateforme) else liste
        )
        champs += ["liste_plateforme", "liste_entreprise"]
    if "alerter" in donnees:
        niveau.alerter = bool(donnees["alerter"])
        champs.append("alerter")
    niveau.save(update_fields=champs)
    return niveau


@transaction.atomic
def ajouter_niveau(projet, *, libelle: str, liste=None, alerter: bool = False) -> NiveauProjet:
    """Ajouter un niveau à la fin est toujours permis (A-3)."""
    from apps.catalogue.models import ListeValeursPlateforme
    from apps.projets.services.listes_modeles import resoudre_liste

    libelle = _verifier_libelle_niveau(projet, libelle)
    liste = resoudre_liste(liste)
    ordre = len(_niveaux(projet)) + 1
    return NiveauProjet.objects.create(
        projet=projet,
        ordre=ordre,
        libelle=libelle,
        liste_plateforme=liste if isinstance(liste, ListeValeursPlateforme) else None,
        liste_entreprise=None
        if liste is None or isinstance(liste, ListeValeursPlateforme)
        else liste,
        alerter=alerter,
    )


@transaction.atomic
def inserer_niveau(
    projet,
    *,
    position: int,
    libelle: str,
    liste=None,
    libelle_intermediaire: str = LIBELLE_GENERAL,
    auteur=None,
) -> dict:
    """Insère un niveau au milieu d'un projet rempli (§12.6).

    Sous chaque case du niveau au-dessus qui a des enfants, une case intermédiaire (« Général »
    par défaut) est créée au nouveau niveau, et les anciens enfants passent dessous. L'arbre
    reste valide à chaque instant ; on renomme ou on scinde ensuite.
    """
    from apps.catalogue.models import ListeValeursPlateforme
    from apps.projets.services.listes_modeles import resoudre_liste

    niveaux = _niveaux(projet)
    if not 1 <= position <= len(niveaux) + 1:
        raise ValidationError({"position": f"La position va de 1 à {len(niveaux) + 1}."})
    libelle = _verifier_libelle_niveau(projet, libelle)
    liste = resoudre_liste(liste)
    intermediaire = " ".join((libelle_intermediaire or LIBELLE_GENERAL).split())

    # Décaler les niveaux suivants (en deux temps : la contrainte d'unicité porte sur l'ordre).
    suivants = [n for n in niveaux if n.ordre >= position]
    for n in suivants:
        n.ordre += 1000
        n.save(update_fields=["ordre"])
    for n in suivants:
        n.ordre -= 999
        n.save(update_fields=["ordre"])
    nouveau = NiveauProjet.objects.create(
        projet=projet,
        ordre=position,
        libelle=libelle,
        liste_plateforme=liste if isinstance(liste, ListeValeursPlateforme) else None,
        liste_entreprise=None
        if liste is None or isinstance(liste, ListeValeursPlateforme)
        else liste,
    )

    arbre = charger_arbre(projet)
    crees = 0
    if position == 1:
        parents = [None]
    else:
        au_dessus = niveaux[position - 2]
        parents = [e for e in arbre.elements if e.niveau_id == au_dessus.pk]
    for parent in parents:
        enfants = [
            e for e in arbre.enfants(parent) if e.niveau.ordre >= position + 1 or parent is None
        ]
        # A-2 : un parent au-dessus n'a que des enfants d'un même niveau ; la récursion sur son
        # propre niveau reste en place.
        enfants = [e for e in enfants if parent is None or e.niveau_id != parent.niveau_id]
        if not enfants:
            continue
        case = Element.objects.create(
            projet=projet,
            parent=parent,
            niveau=nouveau,
            libelle=intermediaire,
            ordre=1,
            cree_par=auteur,
        )
        crees += 1
        for enfant in enfants:
            enfant.parent = case
            _reecrire_chemins(enfant)
    _tracer(
        projet,
        auteur,
        "INSERTION_NIVEAU",
        apres={"niveau": libelle, "position": position, "cases_intermediaires": crees},
    )
    _recalculer(projet)
    return {"niveau": nouveau, "cases_intermediaires": crees}


# --------------------------------------------------------------------------
# Supprimer, désactiver, suspendre (§10)
# --------------------------------------------------------------------------
@transaction.atomic
def supprimer_element(element: Element, *, auteur=None) -> None:
    """Une case sans mesure en dessous se supprime avec sa branche ; une case commencée se
    désactive (motif obligatoire), elle ne se supprime pas."""
    arbre = charger_arbre(element.projet)
    element = arbre.par_id[element.pk]
    if arbre.commence(element):
        raise ErreurMetier(
            "Cette case porte déjà des mesures : désactivez-la plutôt (elle sort des calculs et "
            "garde son historique).",
            details={"geste": "DESACTIVER"},
        )
    parent = arbre.par_id.get(element.parent_id)
    _retirer_liens(element, auteur, "LIENS_RETIRES_SUPPRESSION")
    for case in sorted(
        [element, *arbre.descendants(element)], key=lambda c: c.profondeur, reverse=True
    ):
        case.delete(utilisateur=auteur)
    _redevenir_feuille_si_besoin(parent)
    _tracer(element, auteur, "SUPPRESSION", avant={"libelle": element.libelle})
    _recalculer(element.projet)


@transaction.atomic
def desactiver_element(element: Element, *, auteur=None, motif: str = "") -> Element:
    motif = _exiger_motif(motif, "Désactiver une case")
    element.est_actif = False
    element.motif = motif
    element.save(update_fields=["est_actif", "motif", "modifie_le"])
    # Une case désactivée sort des calculs : les liens de sa branche sont retirés (tracé).
    _retirer_liens(element, auteur, "LIENS_RETIRES_DESACTIVATION")
    parent = element.parent
    _redevenir_feuille_si_besoin(parent)
    _tracer(element, auteur, "DESACTIVATION", motif=motif)
    _recalculer(element.projet)
    return element


@transaction.atomic
def reactiver_element(element: Element, *, auteur=None) -> Element:
    _verifier_nom_libre(element.projet, element.parent, element.libelle, exclure=element)
    element.est_actif = True
    element.save(update_fields=["est_actif", "modifie_le"])
    _devenir_parent(element.parent)
    _tracer(element, auteur, "REACTIVATION")
    _recalculer(element.projet)
    return element


@transaction.atomic
def suspendre_element(element: Element, *, suspendu: bool, auteur=None, motif: str = "") -> Element:
    """Suspendre se fait sur n'importe quelle case et descend vers tous ses descendants (§10)."""
    if suspendu:
        motif = _exiger_motif(motif, "Suspendre une case")
    element.suspendu = suspendu
    element.save(update_fields=["suspendu", "modifie_le"])
    _tracer(element, auteur, "SUSPENSION" if suspendu else "REPRISE", motif=motif)
    from apps.projets.services.machine_etats import evaluer_statuts_arbre

    evaluer_statuts_arbre(element.projet)
    return element


# --------------------------------------------------------------------------
# Mesure hors journal, clôture (§9, §10)
# --------------------------------------------------------------------------
@transaction.atomic
def mesurer_feuille(
    feuille: Element,
    *,
    auteur,
    commentaire: str,
    quantite_realisee=None,
    pourcentage_declare=None,
    atteint: bool | None = None,
) -> Element:
    """Mise à jour tracée de la mesure d'une feuille, hors du journal (`projets.mesurer`)."""
    from apps.projets.services.sante_calculs import calculer_avancement_physique_feuille

    arbre = charger_arbre(feuille.projet)
    feuille = arbre.par_id[feuille.pk]
    if not arbre.est_feuille(feuille):
        raise ErreurMetier("La mesure se saisit sur les tâches du bas (les feuilles).")
    if not (commentaire or "").strip():
        raise ValidationError({"commentaire": "Un commentaire explique la mise à jour."})
    avant_q = feuille.quantite_realisee or Decimal("0")
    avant_av = Decimal(str(calculer_avancement_physique_feuille(feuille)))
    if feuille.mode_mesure == ModeMesure.QUANTITE:
        if quantite_realisee is None:
            raise ValidationError({"quantite_realisee": "La quantité réalisée est requise."})
        if not feuille.unite or not feuille.quantite_prevue:
            raise ErreurMetier("Renseignez d'abord l'unité et la quantité prévue de cette tâche.")
        feuille.quantite_realisee = Decimal(str(quantite_realisee))
    elif feuille.mode_mesure == ModeMesure.POURCENTAGE:
        if pourcentage_declare is None:
            raise ValidationError({"pourcentage_declare": "Le pourcentage déclaré est requis."})
        feuille.pourcentage_declare = Decimal(str(pourcentage_declare))
    else:
        if atteint is None:
            raise ValidationError({"atteint": "Indiquez si le jalon est atteint."})
        feuille.cloture = bool(atteint)
        feuille.cloture_le = timezone.now() if atteint else None
    feuille.save()
    MiseAJourInline.objects.create(
        element=feuille,
        auteur=auteur,
        quantite_avant=avant_q,
        quantite_apres=feuille.quantite_realisee or Decimal("0"),
        avancement_avant=avant_av,
        avancement_apres=Decimal(str(calculer_avancement_physique_feuille(feuille))),
        commentaire=commentaire.strip(),
    )
    from apps.projets.services.avancement import recalculer_apres_quantites

    recalculer_apres_quantites(
        [feuille],
        projet=feuille.projet,
        declencheur_type="MESURE_HORS_JOURNAL",
        declencheur_id=feuille.pk,
    )
    return feuille


@transaction.atomic
def cloturer_feuille(feuille: Element, *, auteur=None) -> Element:
    """Clôturer ne se fait que sur une feuille, et la met à 100 %. Pas de clôture en cascade."""
    arbre = charger_arbre(feuille.projet)
    if not arbre.est_feuille(arbre.par_id[feuille.pk]):
        raise ErreurMetier("Seule une tâche du bas (une feuille) se clôture.")
    feuille.cloture = True
    feuille.cloture_le = timezone.now()
    feuille.save(update_fields=["cloture", "cloture_le", "modifie_le"])
    _tracer(feuille, auteur, "CLOTURE")
    from apps.projets.services.avancement import recalculer_apres_quantites

    recalculer_apres_quantites(
        [feuille], projet=feuille.projet, declencheur_type="CLOTURE", declencheur_id=feuille.pk
    )
    return feuille


@transaction.atomic
def rouvrir_feuille(feuille: Element, *, auteur=None, motif: str = "") -> Element:
    motif = _exiger_motif(motif, "Rouvrir une tâche clôturée")
    feuille.cloture = False
    feuille.cloture_le = None
    feuille.save(update_fields=["cloture", "cloture_le", "modifie_le"])
    _tracer(feuille, auteur, "REOUVERTURE", motif=motif)
    from apps.projets.services.avancement import recalculer_apres_quantites

    recalculer_apres_quantites(
        [feuille], projet=feuille.projet, declencheur_type="REOUVERTURE", declencheur_id=feuille.pk
    )
    return feuille
