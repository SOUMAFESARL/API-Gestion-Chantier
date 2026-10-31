"""Le tableau de démarrage d'un projet (décisions v1.2, §5 et §6).

Une fois le projet créé avec ses informations minimales, son découpage se saisit dans **un
tableau pré-rempli** par le modèle de son type de projet. On y modifie, ajoute ou supprime des
lignes ; à l'enregistrement, l'arbre est construit et le projet bascule dans la vue en arbre,
où toute modification ultérieure passe par des gestes explicites.

- **Une ligne = une feuille.** Ses cellules suivent les niveaux du gabarit, dans l'ordre.
- **Les cellules identiques se regroupent** sous un même parent ; le même intitulé sous deux
  parents différents donne deux cases distinctes.
- **Une cellule vide en fin de ligne est permise** (sa dernière cellule remplie est la feuille) ;
  **au milieu, elle est interdite** (A-1 : on ne saute pas de niveau). Une ligne vide est ignorée.
- Une ligne peut porter, pour sa feuille, l'unité, la quantité prévue, le montant et les dates.
  Ils sont enregistrés tels quels ; le calcul d'avancement s'en servira.

Règles de cohérence (§6) — C-1 à C-4 bloquent, C-5 à C-7 avertissent :

| #   | Règle                                                          | Effet        |
| C-1 | Cellule vide au milieu d'une ligne                             | Bloquant     |
| C-2 | Ligne en double (même chemin complet)                          | Bloquant     |
| C-3 | Niveau sans libellé                                            | Bloquant     |
| C-4 | Deux niveaux au même libellé                                   | Bloquant     |
| C-5 | Valeur de la liste d'un autre niveau, pas de la sienne         | Avertissement |
| C-6 | Enfant portant le même nom que son parent                      | Avertissement |
| C-7 | Valeur hors de la liste de son niveau                          | Avertissement |

Une ligne dont la dernière case a des enfants sur d'autres lignes est « sans effet » : signalée,
ignorée (§5.7).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalogue.models import ListeValeursPlateforme
from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.enums import UniteMesure
from apps.core.exceptions import ErreurMetier
from apps.projets.models import Element, NiveauProjet
from apps.projets.services.listes_modeles import (
    gabarit_du_modele,
    modele_par_defaut,
    reference_liste,
    resoudre_liste,
    resoudre_modele,
    valeurs_de_liste,
)

__all__ = [
    "appliquer_tableau",
    "normaliser_lignes",
    "proposer_tableau",
    "verifier_tableau",
]

CHAMPS_FEUILLE = ("unite", "quantite", "montant", "date_debut", "date_fin")


# --------------------------------------------------------------------------
# Lecture des lignes
# --------------------------------------------------------------------------
def _texte(valeur) -> str:
    return " ".join(str(valeur or "").split())


def normaliser_lignes(lignes: list) -> list[dict]:
    """Accepte une ligne en liste de cellules, ou en objet `{"cellules": [...], "unite", …}`."""
    resultat = []
    for numero, brute in enumerate(lignes or [], start=1):
        if isinstance(brute, dict):
            cellules = [_texte(c) for c in brute.get("cellules") or []]
            extras = {k: brute.get(k) for k in CHAMPS_FEUILLE if brute.get(k) not in (None, "")}
        elif isinstance(brute, (list, tuple)):
            cellules = [_texte(c) for c in brute]
            extras = {}
        else:
            raise ValidationError(
                {"lignes": f"Ligne {numero} : une liste de cellules est attendue."}
            )
        resultat.append({"numero": numero, "cellules": cellules, **extras})
    return resultat


def _chemin(cellules: list[str]) -> tuple[str, ...]:
    """Les cellules jusqu'à la dernière remplie, comparées sans accents, casse ni espaces."""
    dernier = max((i for i, c in enumerate(cellules) if c), default=-1)
    return tuple(cle_comparaison(c) for c in cellules[: dernier + 1])


# --------------------------------------------------------------------------
# Vérification (C-1 à C-7)
# --------------------------------------------------------------------------
def _cles_des_listes(niveaux: list[dict]) -> list[set[str]]:
    cles = []
    for niveau in niveaux:
        try:
            liste = resoudre_liste(niveau.get("liste"))
        except ValidationError:
            liste = None
        cles.append({cle_comparaison(v["libelle"]) for v in valeurs_de_liste(liste)})
    return cles


def verifier_tableau(niveaux: list[dict], lignes: list) -> dict:
    """Le verdict du tableau, sans rien écrire : bloquants, avertissements, aperçu.

    Rend aussi `lignes_retenues` (cellules complétées à la largeur du gabarit) : celles qui
    construiront l'arbre, lignes vides et lignes sans effet écartées.
    """
    bloquants: list[dict] = []
    avertissements: list[dict] = []
    largeur = len(niveaux)

    # C-3, C-4 : les niveaux.
    if not niveaux:
        bloquants.append({"regle": "C-3", "message": "Le gabarit doit compter au moins un niveau."})
    vus: dict[str, int] = {}
    for rang, niveau in enumerate(niveaux, start=1):
        libelle = _texte(niveau.get("libelle"))
        if not libelle:
            bloquants.append(
                {"regle": "C-3", "niveau": rang, "message": f"Le niveau {rang} n'a pas de libellé."}
            )
            continue
        cle = cle_comparaison(libelle)
        if cle in vus:
            bloquants.append(
                {
                    "regle": "C-4",
                    "niveau": rang,
                    "message": f"Les niveaux {vus[cle]} et {rang} portent le même libellé "
                    f"« {libelle} ».",
                }
            )
        vus[cle] = rang

    lignes_norm = [ligne for ligne in normaliser_lignes(lignes) if any(ligne["cellules"])]
    cles_listes = _cles_des_listes(niveaux) if niveaux else []
    chemins_vus: dict[tuple, int] = {}
    retenues: list[dict] = []
    for ligne in lignes_norm:
        cellules = ligne["cellules"][:largeur] + [""] * max(0, largeur - len(ligne["cellules"]))
        if any(c for c in ligne["cellules"][largeur:]):
            bloquants.append(
                {
                    "regle": "C-1",
                    "ligne": ligne["numero"],
                    "message": f"Ligne {ligne['numero']} : plus de cellules que de niveaux.",
                }
            )
            continue
        dernier = max(i for i, c in enumerate(cellules) if c)
        trous = [i for i in range(dernier) if not cellules[i]]
        if trous:
            bloquants.append(
                {
                    "regle": "C-1",
                    "ligne": ligne["numero"],
                    "message": f"Ligne {ligne['numero']} : la cellule du niveau "
                    f"« {_texte(niveaux[trous[0]].get('libelle'))} » est vide alors qu'un niveau "
                    "plus bas est rempli.",
                }
            )
            continue
        chemin = _chemin(cellules)
        if chemin in chemins_vus:
            bloquants.append(
                {
                    "regle": "C-2",
                    "ligne": ligne["numero"],
                    "message": f"Ligne {ligne['numero']} : même chemin que la ligne "
                    f"{chemins_vus[chemin]}.",
                }
            )
            continue
        chemins_vus[chemin] = ligne["numero"]

        for i, cellule in enumerate(cellules[: dernier + 1]):
            cle = cle_comparaison(cellule)
            if i < len(cles_listes) and cles_listes[i] and cle not in cles_listes[i]:
                autres = [j for j, cles in enumerate(cles_listes) if j != i and cle in cles]
                if autres:
                    avertissements.append(
                        {
                            "regle": "C-5",
                            "ligne": ligne["numero"],
                            "niveau": i + 1,
                            "message": f"« {cellule} » appartient à la liste du niveau "
                            f"« {_texte(niveaux[autres[0]].get('libelle'))} » : colonnes "
                            "inversées ?",
                        }
                    )
                else:
                    avertissements.append(
                        {
                            "regle": "C-7",
                            "ligne": ligne["numero"],
                            "niveau": i + 1,
                            "discret": True,
                            "message": f"« {cellule} » n'est pas dans la liste de son niveau : "
                            "coquille ?",
                        }
                    )
            if i > 0 and cle == cle_comparaison(cellules[i - 1]):
                avertissements.append(
                    {
                        "regle": "C-6",
                        "ligne": ligne["numero"],
                        "niveau": i + 1,
                        "message": f"« {cellule} » porte le même nom que son parent.",
                    }
                )
        retenues.append({**ligne, "cellules": cellules})

    # §5.7 : une ligne dont la dernière case a des enfants sur d'autres lignes est sans effet.
    chemins = [_chemin(ligne["cellules"]) for ligne in retenues]
    finales = []
    for ligne, chemin in zip(retenues, chemins, strict=True):
        parente = any(
            len(autre) > len(chemin) and autre[: len(chemin)] == chemin for autre in chemins
        )
        if parente:
            avertissements.append(
                {
                    "regle": "SANS_EFFET",
                    "ligne": ligne["numero"],
                    "message": f"Ligne {ligne['numero']} : sa dernière case a des enfants sur "
                    "d'autres lignes ; elle sera ignorée.",
                }
            )
            continue
        finales.append(ligne)

    noeuds = {
        chemin[: i + 1]
        for chemin in (_chemin(ligne["cellules"]) for ligne in finales)
        for i in range(len(chemin))
    }
    return {
        "bloquants": bloquants,
        "avertissements": avertissements,
        "apercu": {"cases": len(noeuds), "feuilles": len(finales), "niveaux": largeur},
        "lignes_retenues": [ligne["cellules"] for ligne in finales],
        "_lignes": finales,
    }


# --------------------------------------------------------------------------
# Proposition (pré-remplissage) et application
# --------------------------------------------------------------------------
def proposer_tableau(projet, modele_reference=None) -> dict:
    """Le tableau pré-rempli : le modèle choisi, sinon le modèle par défaut du type de projet."""
    from apps.projets.services.listes_modeles import ENTREPRISE, PLATEFORME

    modele = (
        resoudre_modele(modele_reference)
        if modele_reference
        else modele_par_defaut(projet.type_projet)
    )
    if modele is None:
        return {"modele": None, "niveaux": [], "lignes": []}
    gabarit = gabarit_du_modele(modele)
    origine = ENTREPRISE if modele.__class__.__name__ == "ModeleDecoupageEntreprise" else PLATEFORME
    return {
        "modele": {"origine": origine, "id": str(modele.pk), "nom": modele.nom},
        **gabarit,
    }


def _decimal(valeur, champ, numero):
    if valeur in (None, ""):
        return None
    try:
        resultat = Decimal(str(valeur))
    except (InvalidOperation, ValueError):
        raise ValidationError({"lignes": f"Ligne {numero} : {champ} invalide."}) from None
    if resultat < 0:
        raise ValidationError({"lignes": f"Ligne {numero} : {champ} négatif."})
    return resultat


def _date(valeur, champ, numero):
    if valeur in (None, ""):
        return None
    if isinstance(valeur, date):
        return valeur
    try:
        return date.fromisoformat(str(valeur))
    except ValueError:
        raise ValidationError(
            {"lignes": f"Ligne {numero} : {champ} invalide (AAAA-MM-JJ)."}
        ) from None


def _champs_feuille(ligne: dict) -> dict:
    numero = ligne["numero"]
    champs = {}
    unite = ligne.get("unite")
    if unite:
        if unite not in UniteMesure.values:
            raise ValidationError(
                {"lignes": f"Ligne {numero} : unité inconnue ({', '.join(UniteMesure.values)})."}
            )
        champs["unite"] = unite
    quantite = _decimal(ligne.get("quantite"), "quantité", numero)
    if quantite is not None:
        champs["quantite_prevue"] = quantite
    montant = _decimal(ligne.get("montant"), "montant", numero)
    if montant is not None:
        champs["montant"] = int(montant)
    debut = _date(ligne.get("date_debut"), "date de début", numero)
    fin = _date(ligne.get("date_fin"), "date de fin", numero)
    if debut and fin and fin < debut:
        raise ValidationError({"lignes": f"Ligne {numero} : la fin précède le début."})
    if debut:
        champs["date_debut_prevue"] = debut
    if fin:
        champs["date_fin_prevue"] = fin
    return champs


def _niveaux_identiques(projet, niveaux: list[dict]) -> bool:
    existants = list(NiveauProjet.objects.filter(projet=projet).order_by("ordre"))
    return [cle_comparaison(n.libelle) for n in existants] == [
        cle_comparaison(_texte(n.get("libelle"))) for n in niveaux
    ]


@transaction.atomic
def appliquer_tableau(
    projet,
    *,
    niveaux: list[dict],
    lignes: list,
    confirmer_avertissements: bool = False,
    auteur=None,
) -> dict:
    """Construit l'arbre depuis le tableau.

    - **Projet sans découpage** : le gabarit du tableau devient celui du projet, et l'arbre est
      créé en entier.
    - **Projet déjà découpé** : c'est l'**ajout en masse** de nouvelles branches (§12.1). Le
      gabarit doit être celui du projet ; chaque ligne est rapprochée par chemin, seules les
      cases nouvelles sont créées. On ne découpe pas ainsi une feuille commencée (A-5).

    Les bloquants refusent tout ; les avertissements exigent `confirmer_avertissements`.
    """
    verdict = verifier_tableau(niveaux, lignes)
    if verdict["bloquants"]:
        raise ErreurMetier(
            "Le tableau comporte des erreurs à corriger.",
            details={
                "bloquants": verdict["bloquants"],
                "avertissements": verdict["avertissements"],
            },
        )
    if verdict["avertissements"] and not confirmer_avertissements:
        raise ErreurMetier(
            "Le tableau comporte des avertissements : corrigez-les, ou confirmez pour créer "
            "quand même.",
            details={"avertissements": verdict["avertissements"], "confirmation_requise": True},
        )

    from apps.projets.selectors.arbre import charger_arbre

    deja_decoupe = Element.objects.filter(projet=projet).exists()
    if deja_decoupe:
        if not _niveaux_identiques(projet, niveaux):
            raise ErreurMetier(
                "Le projet est déjà découpé : un ajout en masse reprend exactement ses niveaux. "
                "Pour changer le gabarit, renommez ou insérez un niveau dans la vue en arbre."
            )
        niveaux_projet = list(NiveauProjet.objects.filter(projet=projet).order_by("ordre"))
    else:
        NiveauProjet.objects.filter(projet=projet).delete()
        niveaux_projet = []
        for ordre, niveau in enumerate(niveaux, start=1):
            liste = resoudre_liste(niveau.get("liste"))
            niveaux_projet.append(
                NiveauProjet.objects.create(
                    projet=projet,
                    ordre=ordre,
                    libelle=_texte(niveau.get("libelle")),
                    liste_plateforme=liste if isinstance(liste, ListeValeursPlateforme) else None,
                    liste_entreprise=None
                    if liste is None or isinstance(liste, ListeValeursPlateforme)
                    else liste,
                    alerter=bool(niveau.get("alerter")),
                )
            )
        # Sans niveau coché « alerter », celui qui précède le dernier joue ce rôle (le lot d'hier).
        if not any(n.alerter for n in niveaux_projet) and niveaux_projet:
            cible = niveaux_projet[-2] if len(niveaux_projet) > 1 else niveaux_projet[0]
            cible.alerter = True
            cible.save(update_fields=["alerter", "modifie_le"])

    arbre = charger_arbre(projet)
    par_chemin: dict[tuple, Element] = {}

    def indexer(parent, prefixe):
        for enfant in arbre.enfants(parent):
            chemin = (*prefixe, enfant.cle_comparaison)
            par_chemin[chemin] = enfant
            indexer(enfant, chemin)

    indexer(None, ())
    ordres: dict = {}
    crees = 0
    ignorees = []
    devenues_parents: dict = {}
    for ligne in verdict["_lignes"]:
        cellules = ligne["cellules"]
        dernier = max(i for i, c in enumerate(cellules) if c)
        parent = None
        prefixe: tuple = ()
        for i in range(dernier + 1):
            chemin = (*prefixe, cle_comparaison(cellules[i]))
            element = par_chemin.get(chemin)
            est_feuille = i == dernier
            if element is None:
                if parent is not None and arbre.est_feuille(parent) and arbre.commence(parent):
                    raise ErreurMetier(
                        f"Ligne {ligne['numero']} : « {parent.libelle} » est une tâche déjà "
                        "commencée ; pour la découper, utilisez « Détailler » (A-5)."
                    )
                cle_parent = parent.pk if parent else None
                if cle_parent not in ordres:
                    ordres[cle_parent] = len(arbre.enfants(parent))
                ordres[cle_parent] += 1
                champs = _champs_feuille(ligne) if est_feuille else {}
                if parent is not None and arbre.est_feuille(parent):
                    devenues_parents[parent.pk] = parent
                if parent is not None and arbre.est_feuille(parent) and parent.montant:
                    # Une feuille qui reçoit des enfants : son montant devient son enveloppe (§8).
                    parent.enveloppe, parent.montant = parent.montant, None
                    parent.save(update_fields=["enveloppe", "montant", "modifie_le"])
                element = Element.objects.create(
                    projet=projet,
                    parent=parent,
                    niveau=niveaux_projet[i],
                    libelle=cellules[i],
                    ordre=ordres[cle_parent],
                    cree_par=auteur,
                    **champs,
                )
                arbre.elements.append(element)
                arbre.par_id[element.pk] = element
                arbre.enfants_de[cle_parent].append(element)
                par_chemin[chemin] = element
                crees += 1
            elif est_feuille:
                ignorees.append(ligne["numero"])
            parent = element
            prefixe = chemin

    if devenues_parents:
        # Une feuille liée qui reçoit des sous-tâches leur passe ses dépendances (§13quinquies.5).
        from apps.projets.services.dependances import transferer_liens_aux_feuilles

        for ancienne_feuille in devenues_parents.values():
            transferer_liens_aux_feuilles(ancienne_feuille, auteur=auteur)

    from apps.projets.services.avancement import recalculer_avancements_projet

    recalculer_avancements_projet(projet)
    if auteur is not None:
        from apps.audit.services import journaliser
        from apps.core.enums import ActionAudit

        journaliser(
            action=ActionAudit.CREATION if not deja_decoupe else ActionAudit.MODIFICATION,
            type_entite="DecoupageProjet",
            entite_id=projet.pk,
            utilisateur_id=auteur.pk,
            valeur_apres={
                "evenement": "AJOUT_EN_MASSE" if deja_decoupe else "TABLEAU_DE_DEMARRAGE",
                "cases_creees": crees,
                "niveaux": [n.libelle for n in niveaux_projet],
            },
        )
    return {
        "cases_creees": crees,
        "lignes_deja_presentes": ignorees,
        "avertissements": verdict["avertissements"],
        "niveaux": [
            {
                "id": str(n.pk),
                "ordre": n.ordre,
                "libelle": n.libelle,
                "liste": reference_liste(n.liste_plateforme or n.liste_entreprise),
                "alerter": n.alerter,
            }
            for n in niveaux_projet
        ],
    }
