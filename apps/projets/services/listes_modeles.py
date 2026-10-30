"""Listes de valeurs et modèles de découpage, vus par une entreprise (décisions v1.2, §3 et §4).

Une entreprise voit **deux sources fusionnées** : celles de la plateforme (schéma public, lues
sans copie) et les siennes. Une liste ou un modèle se désigne donc par un couple
`{"origine": "PLATEFORME" | "ENTREPRISE", "id": "<uuid>"}`, jamais par son nom.

- Elle ajoute des valeurs aux listes plateforme et crée ses propres listes ; elle ne retire pas
  une valeur plateforme.
- Elle crée ses propres modèles et **personnalise** un modèle plateforme : la copie lui reste
  liée par identifiant, s'affiche « Nom (personnalisé) » et signale quand l'original a changé.
- Un modèle porte un **gabarit** (niveaux ordonnés, une liste au plus par niveau) et des **lignes
  types** : `{"niveaux": [{"libelle", "liste", "alerter"}], "lignes": [[...], ...]}`.

**Le back-office s'en sert aussi** (`apps.platform_admin.services.decoupage`) : appelés dans le
schéma `public`, ces services ne voient que la plateforme — une liste n'y a que ses valeurs
plateforme, et un modèle plateforme ne puise que dans des listes plateforme (§3.8).
"""

from __future__ import annotations

from django.db import connection, transaction
from django_tenants.utils import get_public_schema_name
from rest_framework.exceptions import NotFound, ValidationError

from apps.catalogue.models import (
    LigneModelePlateforme,
    ListeValeursPlateforme,
    ModeleDecoupagePlateforme,
    NiveauModelePlateforme,
    ValeurListePlateforme,
)
from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.exceptions import ErreurMetier
from apps.projets.models import (
    LigneModeleEntreprise,
    ListeValeursEntreprise,
    ModeleDecoupageEntreprise,
    NiveauModeleEntreprise,
    ValeurListeEntreprise,
)

__all__ = [
    "ENTREPRISE",
    "PLATEFORME",
    "ajouter_valeurs",
    "creer_liste",
    "enregistrer_modele",
    "enregistrer_modele_plateforme",
    "gabarit_du_modele",
    "liste_en_dict",
    "listes_disponibles",
    "modele_par_defaut",
    "modeles_disponibles",
    "personnaliser_modele",
    "resoudre_liste",
    "resoudre_modele",
    "retirer_valeur",
    "valeurs_de_liste",
]

PLATEFORME = "PLATEFORME"
ENTREPRISE = "ENTREPRISE"


def _schema_public() -> bool:
    """Le back-office travaille dans `public`, où les tables des entreprises n'existent pas."""
    return getattr(connection, "schema_name", None) == get_public_schema_name()


def nom_propre(texte: str) -> str:
    return " ".join((texte or "").split())


# --------------------------------------------------------------------------
# Listes
# --------------------------------------------------------------------------
def resoudre_liste(reference):
    """`{"origine", "id"}` → la liste (plateforme ou entreprise) ; None si la référence est vide."""
    if not reference:
        return None
    origine = (reference.get("origine") or "").upper()
    ident = reference.get("id")
    modele = ListeValeursPlateforme if origine == PLATEFORME else ListeValeursEntreprise
    if origine not in (PLATEFORME, ENTREPRISE):
        raise ValidationError({"liste": "L'origine d'une liste est PLATEFORME ou ENTREPRISE."})
    liste = modele.objects.filter(pk=ident, supprime_le__isnull=True).first()
    if liste is None:
        raise ValidationError({"liste": "Cette liste est introuvable."})
    return liste


def reference_liste(liste) -> dict | None:
    if liste is None:
        return None
    origine = PLATEFORME if isinstance(liste, ListeValeursPlateforme) else ENTREPRISE
    return {"origine": origine, "id": str(liste.pk), "libelle": liste.libelle}


def _valeur_en_dict(valeur, origine: str) -> dict:
    return {
        "id": str(valeur.pk),
        "libelle": valeur.libelle,
        "groupe": valeur.groupe,
        "ordre": valeur.ordre,
        "origine": origine,
    }


def valeurs_de_liste(liste) -> list[dict]:
    """Les valeurs d'une liste : celles de la plateforme puis celles ajoutées par l'entreprise.

    Dans le schéma `public` (back-office), seulement celles de la plateforme.
    """
    if liste is None:
        return []
    valeurs = []
    if isinstance(liste, ListeValeursPlateforme):
        valeurs += [
            _valeur_en_dict(v, PLATEFORME)
            for v in ValeurListePlateforme.objects.filter(liste=liste).order_by("ordre", "libelle")
        ]
        if _schema_public():
            return valeurs
        ajoutees = ValeurListeEntreprise.objects.filter(liste_plateforme=liste)
    else:
        ajoutees = ValeurListeEntreprise.objects.filter(liste_entreprise=liste)
    valeurs += [_valeur_en_dict(v, ENTREPRISE) for v in ajoutees.order_by("ordre", "libelle")]
    return valeurs


def liste_en_dict(liste, *, avec_valeurs: bool = True) -> dict:
    donnees = {
        **reference_liste(liste),
        "description": liste.description,
        "modifiable": isinstance(liste, ListeValeursEntreprise),
    }
    if avec_valeurs:
        donnees["valeurs"] = valeurs_de_liste(liste)
    return donnees


def listes_disponibles(*, avec_valeurs: bool = True) -> list[dict]:
    plateforme = ListeValeursPlateforme.objects.order_by("ordre", "libelle")
    entreprise = ListeValeursEntreprise.objects.order_by("ordre", "libelle")
    return [liste_en_dict(liste, avec_valeurs=avec_valeurs) for liste in [*plateforme, *entreprise]]


@transaction.atomic
def ajouter_valeurs(
    liste, libelles: list[str], groupe: str = "", *, par_la_plateforme: bool = False, auteur=None
) -> dict:
    """Ajout en masse, sans doublon (comparaison sans accents, casse ni espaces superflus).

    Rend les valeurs ajoutées et celles ignorées parce qu'elles existaient déjà.
    `par_la_plateforme` (back-office) : les valeurs deviennent celles de la liste plateforme,
    proposées à toutes les entreprises ; sinon ce sont des ajouts de l'entreprise.
    """
    if par_la_plateforme and not isinstance(liste, ListeValeursPlateforme):
        raise ErreurMetier("La plateforme n'ajoute des valeurs qu'à ses propres listes.")
    deja = valeurs_de_liste(liste)
    existantes = {cle_comparaison(v["libelle"]) for v in deja}
    ordre = max((v["ordre"] for v in deja), default=0)
    groupe = nom_propre(groupe)
    ajoutees, ignorees = [], []
    for libelle in libelles:
        propre = nom_propre(libelle)
        if not propre:
            continue
        cle = cle_comparaison(propre)
        if cle in existantes:
            ignorees.append(propre)
            continue
        existantes.add(cle)
        ordre += 1
        if par_la_plateforme:
            valeur = ValeurListePlateforme.objects.create(
                liste=liste, libelle=propre, groupe=groupe, ordre=ordre, cree_par=auteur
            )
        else:
            valeur = ValeurListeEntreprise.objects.create(
                liste_entreprise=liste if isinstance(liste, ListeValeursEntreprise) else None,
                liste_plateforme=liste if isinstance(liste, ListeValeursPlateforme) else None,
                libelle=propre,
                groupe=groupe,
                ordre=ordre,
                cree_par=auteur,
            )
        ajoutees.append(
            {"id": str(valeur.pk), "libelle": valeur.libelle, "groupe": groupe, "ordre": ordre}
        )
    return {"ajoutees": ajoutees, "ignorees": ignorees}


@transaction.atomic
def creer_liste(libelle: str, description: str = "", valeurs: list[str] | None = None):
    propre = " ".join((libelle or "").split())
    if not propre:
        raise ValidationError({"libelle": "Le nom de la liste est obligatoire."})
    cle = cle_comparaison(propre)
    homonymes = [
        liste.libelle
        for liste in [*ListeValeursPlateforme.objects.all(), *ListeValeursEntreprise.objects.all()]
        if cle_comparaison(liste.libelle) == cle
    ]
    if homonymes:
        raise ErreurMetier(
            f"Une liste porte déjà ce nom : « {homonymes[0]} ».",
            details={"libelle": propre},
        )
    liste = ListeValeursEntreprise.objects.create(libelle=propre, description=description)
    if valeurs:
        ajouter_valeurs(liste, valeurs)
    return liste


def retirer_valeur(valeur_id, utilisateur=None) -> None:
    """Retire une valeur ajoutée par l'entreprise. Une valeur de la plateforme ne se retire pas."""
    valeur = ValeurListeEntreprise.objects.filter(pk=valeur_id).first()
    if valeur is None:
        if ValeurListePlateforme.objects.filter(pk=valeur_id).exists():
            raise ErreurMetier("Une valeur fournie par la plateforme ne se retire pas.")
        raise NotFound("Cette valeur est introuvable.")
    # Retirer une valeur ne change aucune case déjà saisie (§4.8) : elle n'est plus proposée.
    valeur.delete(utilisateur=utilisateur)


# --------------------------------------------------------------------------
# Modèles
# --------------------------------------------------------------------------
def resoudre_modele(reference):
    origine = (reference.get("origine") or "").upper() if reference else ""
    ident = reference.get("id") if reference else None
    if origine == PLATEFORME:
        modele = ModeleDecoupagePlateforme.objects.filter(
            pk=ident, est_actif=True, supprime_le__isnull=True
        ).first()
    elif origine == ENTREPRISE:
        modele = ModeleDecoupageEntreprise.objects.filter(pk=ident).first()
    else:
        raise ValidationError({"modele": "L'origine d'un modèle est PLATEFORME ou ENTREPRISE."})
    if modele is None:
        raise NotFound("Ce modèle de découpage est introuvable.")
    return modele


def _niveaux_du_modele(modele) -> list[dict]:
    niveaux = []
    for n in modele.niveaux.filter(supprime_le__isnull=True).order_by("ordre"):
        if isinstance(modele, ModeleDecoupagePlateforme):
            liste = n.liste
        else:
            liste = n.liste_plateforme or n.liste_entreprise
        niveaux.append(
            {"libelle": n.libelle, "liste": reference_liste(liste), "alerter": n.alerter}
        )
    return niveaux


def gabarit_du_modele(modele) -> dict:
    niveaux = _niveaux_du_modele(modele)
    lignes = [
        list(ligne.valeurs) + [""] * (len(niveaux) - len(ligne.valeurs))
        for ligne in modele.lignes.filter(supprime_le__isnull=True).order_by("ordre")
    ]
    return {"niveaux": niveaux, "lignes": lignes}


def _nom_affiche(modele, noms_plateforme: set[str]) -> str:
    if isinstance(modele, ModeleDecoupagePlateforme):
        return modele.nom
    if modele.origine_id:
        return f"{modele.nom} (personnalisé)"
    if cle_comparaison(modele.nom) in noms_plateforme:
        return f"{modele.nom} (entreprise)"
    return modele.nom


def _modele_en_dict(modele, noms_plateforme, type_projet=None, defaut=None) -> dict:
    plateforme = isinstance(modele, ModeleDecoupagePlateforme)
    niveaux = _niveaux_du_modele(modele)
    donnees = {
        "origine": PLATEFORME if plateforme else ENTREPRISE,
        "id": str(modele.pk),
        "nom": modele.nom,
        "nom_affiche": _nom_affiche(modele, noms_plateforme),
        "description": modele.description,
        "types_projet": list(modele.types_projet or []),
        "par_defaut_pour": list(modele.par_defaut_pour or []),
        "niveaux": [n["libelle"] for n in niveaux],
        "nombre_lignes": modele.lignes.filter(supprime_le__isnull=True).count(),
        "modifiable": not plateforme,
        "pour_ce_type": bool(type_projet and type_projet in (modele.types_projet or [])),
        "par_defaut": defaut is not None and defaut.pk == modele.pk,
    }
    if not plateforme:
        origine = modele.origine
        donnees["origine_plateforme_id"] = str(modele.origine_id) if modele.origine_id else None
        # La copie ne suit plus son original : elle signale seulement qu'il a changé (§3.6).
        donnees["original_modifie"] = bool(
            origine and modele.version_origine and origine.version > modele.version_origine
        )
    return donnees


def modele_par_defaut(type_projet: str | None):
    """Le modèle qui pré-remplit le tableau d'un projet de ce type.

    Celui que l'entreprise a désigné pour ce type, sinon celui de la plateforme, sinon le premier
    modèle plateforme conçu pour ce type, sinon le premier modèle plateforme.
    """
    plateforme = list(ModeleDecoupagePlateforme.objects.filter(est_actif=True).order_by("nom"))
    if type_projet:
        for modele in ModeleDecoupageEntreprise.objects.order_by("nom"):
            if type_projet in (modele.par_defaut_pour or []):
                return modele
        for modele in plateforme:
            if type_projet in (modele.par_defaut_pour or []):
                return modele
        for modele in plateforme:
            if type_projet in (modele.types_projet or []):
                return modele
    return plateforme[0] if plateforme else None


def modeles_disponibles(type_projet: str | None = None) -> list[dict]:
    """Tous les modèles, ceux du type demandé en tête (§3.9), le modèle par défaut d'abord."""
    plateforme = list(ModeleDecoupagePlateforme.objects.filter(est_actif=True).order_by("nom"))
    entreprise = list(ModeleDecoupageEntreprise.objects.select_related("origine").order_by("nom"))
    noms_plateforme = {cle_comparaison(m.nom) for m in plateforme}
    defaut = modele_par_defaut(type_projet)
    tous = [
        _modele_en_dict(m, noms_plateforme, type_projet, defaut) for m in [*plateforme, *entreprise]
    ]
    tous.sort(key=lambda d: (not d["par_defaut"], not d["pour_ce_type"], d["nom_affiche"]))
    return tous


def modele_en_dict(modele, type_projet=None) -> dict:
    noms_plateforme = {
        cle_comparaison(m.nom) for m in ModeleDecoupagePlateforme.objects.filter(est_actif=True)
    }
    donnees = _modele_en_dict(modele, noms_plateforme, type_projet, modele_par_defaut(type_projet))
    donnees.update(gabarit_du_modele(modele))
    return donnees


def _exiger_listes_plateforme(niveaux: list[dict]) -> None:
    """§3.8 : un modèle plateforme ne puise que dans des listes plateforme."""
    for rang, niveau in enumerate(niveaux, start=1):
        reference = niveau.get("liste")
        if reference and (reference.get("origine") or "").upper() != PLATEFORME:
            raise ErreurMetier(
                f"Le niveau {rang} puise dans une liste d'entreprise : un modèle de la plateforme "
                "ne puise que dans des listes de la plateforme.",
                details={"niveau": rang},
            )


def _ecrire_gabarit(modele, niveaux: list[dict], lignes: list[list[str]]) -> None:
    """Remplace les niveaux et les lignes types d'un modèle, plateforme ou entreprise.

    C-1 à C-4 bloquent l'enregistrement d'un modèle comme celui d'un projet (§6).
    """
    from apps.projets.services.tableau_demarrage import verifier_tableau

    plateforme = isinstance(modele, ModeleDecoupagePlateforme)
    if plateforme:
        _exiger_listes_plateforme(niveaux)
    verdict = verifier_tableau(niveaux, lignes)
    if verdict["bloquants"]:
        raise ErreurMetier(
            "Le modèle comporte des erreurs à corriger avant de l'enregistrer.",
            details={"bloquants": verdict["bloquants"]},
        )
    # Les anciens niveaux et lignes sont retirés par suppression logique (Socle §3.1), avant
    # les nouveaux : l'unicité de l'ordre ne porte que sur les lignes non supprimées.
    modele.niveaux.all().supprimer_logiquement()
    modele.lignes.all().supprimer_logiquement()
    for ordre, niveau in enumerate(niveaux, start=1):
        liste = resoudre_liste(niveau.get("liste"))
        if plateforme:
            NiveauModelePlateforme.objects.create(
                modele=modele,
                ordre=ordre,
                libelle=nom_propre(niveau["libelle"]),
                liste=liste,
                alerter=bool(niveau.get("alerter")),
            )
        else:
            NiveauModeleEntreprise.objects.create(
                modele=modele,
                ordre=ordre,
                libelle=nom_propre(niveau["libelle"]),
                liste_plateforme=liste if isinstance(liste, ListeValeursPlateforme) else None,
                liste_entreprise=liste if isinstance(liste, ListeValeursEntreprise) else None,
                alerter=bool(niveau.get("alerter")),
            )
    classe_ligne = LigneModelePlateforme if plateforme else LigneModeleEntreprise
    for ordre, cellules in enumerate(verdict["lignes_retenues"]):
        classe_ligne.objects.create(modele=modele, ordre=ordre, valeurs=cellules)


def _un_seul_defaut_par_type(classe, modele) -> None:
    """Un seul modèle par défaut pour un type donné, parmi les modèles de la même origine."""
    if not modele.par_defaut_pour:
        return
    for autre in classe.objects.exclude(pk=modele.pk):
        restants = [t for t in autre.par_defaut_pour or [] if t not in modele.par_defaut_pour]
        if restants != list(autre.par_defaut_pour or []):
            autre.par_defaut_pour = restants
            autre.save(update_fields=["par_defaut_pour", "modifie_le"])


@transaction.atomic
def enregistrer_modele(
    *,
    modele: ModeleDecoupageEntreprise | None = None,
    nom: str,
    description: str = "",
    types_projet: list[str] | None = None,
    par_defaut_pour: list[str] | None = None,
    niveaux: list[dict],
    lignes: list,
) -> ModeleDecoupageEntreprise:
    """« Enregistrer comme nouveau modèle » ou « Mettre à jour ce modèle » (§3.10)."""
    nom = " ".join((nom or "").split())
    if not nom:
        raise ValidationError({"nom": "Le nom du modèle est obligatoire."})
    homonyme = ModeleDecoupageEntreprise.objects.filter(nom__iexact=nom)
    if modele is not None:
        homonyme = homonyme.exclude(pk=modele.pk)
    if homonyme.exists():
        raise ErreurMetier(f"Un modèle de l'entreprise porte déjà le nom « {nom} ».")
    if modele is None:
        modele = ModeleDecoupageEntreprise(nom=nom)
    modele.nom = nom
    modele.description = description
    modele.types_projet = list(types_projet or [])
    modele.par_defaut_pour = list(par_defaut_pour or [])
    modele.save()
    _un_seul_defaut_par_type(ModeleDecoupageEntreprise, modele)
    from apps.projets.services.tableau_demarrage import normaliser_lignes

    _ecrire_gabarit(modele, niveaux, [ligne["cellules"] for ligne in normaliser_lignes(lignes)])
    return modele


@transaction.atomic
def enregistrer_modele_plateforme(
    *,
    modele: ModeleDecoupagePlateforme | None = None,
    nom: str,
    description: str = "",
    types_projet: list[str] | None = None,
    par_defaut_pour: list[str] | None = None,
    niveaux: list[dict],
    lignes: list,
    est_actif: bool = True,
    auteur=None,
) -> ModeleDecoupagePlateforme:
    """Créer ou mettre à jour un modèle de la plateforme (back-office, schéma `public`).

    Chaque mise à jour **incrémente la version** : les copies personnalisées des entreprises
    savent ainsi signaler que leur original a changé, sans rien appliquer (§3.6). Aucun projet
    déjà créé n'est touché (§3.11).
    """
    nom = nom_propre(nom)
    if not nom:
        raise ValidationError({"nom": "Le nom du modèle est obligatoire."})
    cle = cle_comparaison(nom)
    homonyme = next(
        (
            m
            for m in ModeleDecoupagePlateforme.objects.all()
            if cle_comparaison(m.nom) == cle and (modele is None or m.pk != modele.pk)
        ),
        None,
    )
    if homonyme is not None:
        raise ErreurMetier(f"Un modèle de la plateforme porte déjà le nom « {homonyme.nom} ».")
    types_projet = list(dict.fromkeys(types_projet or []))
    par_defaut_pour = list(dict.fromkeys(par_defaut_pour or []))
    _exiger_types_connus([*types_projet, *par_defaut_pour])
    if modele is None:
        modele = ModeleDecoupagePlateforme(nom=nom, cree_par=auteur)
    else:
        modele.version += 1
    modele.nom = nom
    modele.description = description
    modele.types_projet = types_projet
    modele.par_defaut_pour = par_defaut_pour
    modele.est_actif = est_actif
    modele.save()
    _un_seul_defaut_par_type(ModeleDecoupagePlateforme, modele)
    from apps.projets.services.tableau_demarrage import normaliser_lignes

    _ecrire_gabarit(modele, niveaux, [ligne["cellules"] for ligne in normaliser_lignes(lignes)])
    return modele


def _exiger_types_connus(codes: list[str]) -> None:
    """Un modèle plateforme ne cite que des types de projet du référentiel plateforme."""
    from apps.catalogue.models import CategorieReferentiel, ReferentielPlateforme

    connus = set(
        ReferentielPlateforme.objects.filter(
            categorie=CategorieReferentiel.TYPE_PROJET
        ).values_list("code", flat=True)
    )
    inconnus = sorted({c for c in codes if c not in connus})
    if inconnus:
        raise ValidationError(
            {"types_projet": f"Types de projet inconnus de la plateforme : {', '.join(inconnus)}."}
        )


@transaction.atomic
def personnaliser_modele(modele_plateforme: ModeleDecoupagePlateforme) -> ModeleDecoupageEntreprise:
    """Crée la copie personnalisée d'un modèle plateforme, liée à lui par identifiant (§3.5).

    Deux modèles d'une même origine ne portent pas le même nom (§3.7) : une seconde
    personnalisation renvoie vers la copie existante.
    """
    existante = ModeleDecoupageEntreprise.objects.filter(origine=modele_plateforme).first()
    if existante is not None:
        raise ErreurMetier(
            "Ce modèle est déjà personnalisé : modifiez la copie existante.",
            details={"modele": {"origine": ENTREPRISE, "id": str(existante.pk)}},
        )
    gabarit = gabarit_du_modele(modele_plateforme)
    copie = ModeleDecoupageEntreprise.objects.create(
        nom=modele_plateforme.nom,
        description=modele_plateforme.description,
        types_projet=list(modele_plateforme.types_projet or []),
        origine=modele_plateforme,
        version_origine=modele_plateforme.version,
    )
    _ecrire_gabarit(copie, gabarit["niveaux"], gabarit["lignes"])
    return copie
