"""Listes de valeurs et modèles de découpage de la plateforme, gérés au back-office.

Décisions v1.2 du découpage, §3 et §4 : le super admin crée les listes plateforme (« Phases »,
« Lots »…) et les modèles plateforme ; chaque entreprise les lit **sans copie**, depuis le schéma
`public`. Une correction faite ici est donc vue partout immédiatement.

- **Tout se passe dans le schéma `public`** (`schema_context`) : le back-office est servi sur le
  domaine public comme sur celui d'une entreprise (`config/urls_tenant.py`), et ces tables
  n'existent qu'une fois.
- **Les briques sont celles du découpage** (`apps.projets.services.listes_modeles`) : ajout de
  valeurs sans doublon, enregistrement d'un gabarit vérifié par C-1 à C-4, représentation d'un
  gabarit. Ce module n'ajoute que ce qui est propre à la plateforme : retrait d'une liste, d'une
  valeur ou d'un modèle (suppression logique), et la trace au journal de la plateforme.
- **Retirer ne change rien de ce qui existe** (§3.11, §4.8) : un projet ou un modèle d'entreprise
  qui cite une liste retirée la garde ; elle n'est simplement plus proposée.

La lecture est ouverte au SUPPORT, l'écriture réservée au SUPERVISEUR (`exiger_superviseur`,
dans les vues).
"""

from __future__ import annotations

from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.exceptions import NotFound, ValidationError

from apps.catalogue.models import (
    ListeValeursPlateforme,
    ModeleDecoupagePlateforme,
    NiveauModelePlateforme,
    ValeurListePlateforme,
)
from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.exceptions import ErreurMetier, LibelleEnDouble
from apps.platform_admin.services.notifications import journaliser_plateforme
from apps.projets.services import listes_modeles as lm

__all__ = [
    "ajouter_valeurs",
    "creer_liste",
    "enregistrer_modele",
    "lire_liste",
    "lire_modele",
    "lister_listes",
    "lister_modeles",
    "modifier_liste",
    "modifier_valeur",
    "retirer_liste",
    "retirer_modele",
    "retirer_valeur",
]


def _public():
    return schema_context(get_public_schema_name())


# --------------------------------------------------------------------------
# Représentations
# --------------------------------------------------------------------------
def _modeles_qui_citent(liste) -> list[dict]:
    """Les modèles plateforme (non retirés) dont un niveau puise dans cette liste."""
    niveaux = NiveauModelePlateforme.objects.filter(
        liste=liste, modele__supprime_le__isnull=True
    ).select_related("modele")
    vus = {}
    for niveau in niveaux:
        vus.setdefault(niveau.modele_id, {"id": str(niveau.modele_id), "nom": niveau.modele.nom})
    return list(vus.values())


def _liste_en_dict(liste, *, avec_valeurs: bool = True) -> dict:
    valeurs = lm.valeurs_de_liste(liste)
    donnees = {
        "id": str(liste.pk),
        "libelle": liste.libelle,
        "description": liste.description,
        "ordre": liste.ordre,
        "nombre_valeurs": len(valeurs),
        "modeles": _modeles_qui_citent(liste),
        "modifie_le": liste.modifie_le,
    }
    if avec_valeurs:
        donnees["valeurs"] = valeurs
    return donnees


def _modele_en_dict(modele, *, avec_gabarit: bool = True) -> dict:
    gabarit = lm.gabarit_du_modele(modele)
    donnees = {
        "id": str(modele.pk),
        "nom": modele.nom,
        "description": modele.description,
        "types_projet": list(modele.types_projet or []),
        "par_defaut_pour": list(modele.par_defaut_pour or []),
        "version": modele.version,
        "est_actif": modele.est_actif,
        "niveaux_libelles": [n["libelle"] for n in gabarit["niveaux"]],
        "nombre_lignes": len(gabarit["lignes"]),
        "modifie_le": modele.modifie_le,
    }
    if avec_gabarit:
        donnees.update(gabarit)
    return donnees


def _liste(pk) -> ListeValeursPlateforme:
    liste = ListeValeursPlateforme.objects.filter(pk=pk).first()
    if liste is None:
        raise NotFound("Cette liste est introuvable.")
    return liste


def _modele(pk) -> ModeleDecoupagePlateforme:
    modele = ModeleDecoupagePlateforme.objects.filter(pk=pk).first()
    if modele is None:
        raise NotFound("Ce modèle de découpage est introuvable.")
    return modele


def _refuser_homonyme(libelle: str, exclure=None) -> None:
    cle = cle_comparaison(libelle)
    for autre in ListeValeursPlateforme.objects.all():
        if cle_comparaison(autre.libelle) == cle and (exclure is None or autre.pk != exclure.pk):
            raise LibelleEnDouble(libelle, autre.libelle)


# --------------------------------------------------------------------------
# Listes de valeurs
# --------------------------------------------------------------------------
def lister_listes(*, avec_valeurs: bool = True) -> list[dict]:
    with _public():
        return [
            _liste_en_dict(liste, avec_valeurs=avec_valeurs)
            for liste in ListeValeursPlateforme.objects.order_by("ordre", "libelle")
        ]


def lire_liste(pk) -> dict:
    with _public():
        return _liste_en_dict(_liste(pk))


def creer_liste(*, libelle: str, description: str = "", valeurs=None, auteur=None) -> dict:
    with _public(), transaction.atomic():
        libelle = lm.nom_propre(libelle)
        if not libelle:
            raise ValidationError({"libelle": "Le nom de la liste est obligatoire."})
        _refuser_homonyme(libelle)
        derniere = ListeValeursPlateforme.objects.order_by("-ordre").first()
        liste = ListeValeursPlateforme.objects.create(
            libelle=libelle,
            description=description or "",
            ordre=(derniere.ordre + 1) if derniere else 0,
            cree_par=auteur,
        )
        if valeurs:
            lm.ajouter_valeurs(liste, valeurs, par_la_plateforme=True, auteur=auteur)
        donnees = _liste_en_dict(liste)
    journaliser_plateforme(
        action="DECOUPAGE_LISTE_CREATION",
        acteur=auteur,
        detail={
            "liste_id": donnees["id"],
            "libelle": libelle,
            "valeurs": donnees["nombre_valeurs"],
        },
    )
    return donnees


def modifier_liste(pk, *, donnees: dict, auteur=None) -> dict:
    """Renommer, décrire ou réordonner une liste. Les niveaux qui la citent la suivent : le lien
    passe par l'identifiant, jamais par le nom (§4.3)."""
    with _public(), transaction.atomic():
        liste = _liste(pk)
        avant = {"libelle": liste.libelle, "description": liste.description, "ordre": liste.ordre}
        if "libelle" in donnees:
            libelle = lm.nom_propre(donnees["libelle"])
            if not libelle:
                raise ValidationError({"libelle": "Le nom de la liste est obligatoire."})
            _refuser_homonyme(libelle, exclure=liste)
            liste.libelle = libelle
        if "description" in donnees:
            liste.description = donnees["description"] or ""
        if "ordre" in donnees:
            liste.ordre = donnees["ordre"]
        liste.save()
        resultat = _liste_en_dict(liste)
    journaliser_plateforme(
        action="DECOUPAGE_LISTE_MODIFICATION",
        acteur=auteur,
        detail={
            "liste_id": str(pk),
            "avant": avant,
            "apres": {k: resultat[k] for k in ("libelle", "description", "ordre")},
        },
    )
    return resultat


def retirer_liste(pk, *, auteur=None) -> None:
    """Retire une liste (suppression logique).

    Refusé tant qu'un modèle de la plateforme y puise : il faut d'abord changer la liste de ce
    niveau ou retirer le modèle. Les entreprises qui la citent (niveaux de projets, modèles
    personnalisés) la gardent ; elle n'est plus proposée (§3.11, §4.8).
    """
    with _public(), transaction.atomic():
        liste = _liste(pk)
        modeles = _modeles_qui_citent(liste)
        if modeles:
            noms = ", ".join(f"« {m['nom']} »" for m in modeles)
            raise ErreurMetier(
                f"Cette liste sert encore aux modèles {noms} : changez la liste de leurs niveaux, "
                "ou retirez ces modèles, avant de la retirer.",
                details={"modeles": modeles},
            )
        liste.delete(utilisateur=auteur)
    journaliser_plateforme(
        action="DECOUPAGE_LISTE_RETRAIT",
        acteur=auteur,
        detail={"liste_id": str(pk), "libelle": liste.libelle},
    )


def ajouter_valeurs(pk, *, valeurs: list[str], groupe: str = "", auteur=None) -> dict:
    """Ajout en masse ; une valeur déjà présente (sans accents, casse ni espaces) est ignorée."""
    with _public():
        liste = _liste(pk)
        resultat = lm.ajouter_valeurs(liste, valeurs, groupe, par_la_plateforme=True, auteur=auteur)
    if resultat["ajoutees"]:
        journaliser_plateforme(
            action="DECOUPAGE_VALEURS_AJOUT",
            acteur=auteur,
            detail={
                "liste_id": str(pk),
                "libelle": liste.libelle,
                "valeurs": [v["libelle"] for v in resultat["ajoutees"]],
            },
        )
    return resultat


def _valeur(pk) -> ValeurListePlateforme:
    valeur = ValeurListePlateforme.objects.filter(pk=pk).select_related("liste").first()
    if valeur is None:
        raise NotFound("Cette valeur est introuvable.")
    return valeur


def modifier_valeur(pk, *, donnees: dict, auteur=None) -> dict:
    """Corriger une valeur. Les cases déjà saisies ne changent pas : une valeur choisie dans une
    liste est recopiée dans l'intitulé de la case (§4.6, §4.8)."""
    with _public(), transaction.atomic():
        valeur = _valeur(pk)
        avant = {"libelle": valeur.libelle, "groupe": valeur.groupe, "ordre": valeur.ordre}
        if "libelle" in donnees:
            libelle = lm.nom_propre(donnees["libelle"])
            if not libelle:
                raise ValidationError({"libelle": "Le libellé de la valeur est obligatoire."})
            cle = cle_comparaison(libelle)
            doublon = (
                ValeurListePlateforme.objects.filter(liste=valeur.liste, cle_comparaison=cle)
                .exclude(pk=valeur.pk)
                .first()
            )
            if doublon is not None:
                raise LibelleEnDouble(libelle, doublon.libelle)
            valeur.libelle = libelle
        if "groupe" in donnees:
            valeur.groupe = lm.nom_propre(donnees["groupe"])
        if "ordre" in donnees:
            valeur.ordre = donnees["ordre"]
        valeur.save()
        resultat = {
            "id": str(valeur.pk),
            "liste_id": str(valeur.liste_id),
            "libelle": valeur.libelle,
            "groupe": valeur.groupe,
            "ordre": valeur.ordre,
            "origine": lm.PLATEFORME,
        }
    journaliser_plateforme(
        action="DECOUPAGE_VALEUR_MODIFICATION",
        acteur=auteur,
        detail={"valeur_id": str(pk), "avant": avant, "apres": resultat},
    )
    return resultat


def retirer_valeur(pk, *, auteur=None) -> None:
    """Retire une valeur de la plateforme (suppression logique) : elle n'est plus proposée."""
    with _public(), transaction.atomic():
        valeur = _valeur(pk)
        valeur.delete(utilisateur=auteur)
    journaliser_plateforme(
        action="DECOUPAGE_VALEUR_RETRAIT",
        acteur=auteur,
        detail={"valeur_id": str(pk), "liste_id": str(valeur.liste_id), "libelle": valeur.libelle},
    )


# --------------------------------------------------------------------------
# Modèles de découpage
# --------------------------------------------------------------------------
def lister_modeles() -> list[dict]:
    """Tous les modèles de la plateforme, actifs ou non (un modèle inactif n'est plus proposé
    aux entreprises, mais se garde au back-office)."""
    with _public():
        return [
            _modele_en_dict(m, avec_gabarit=False)
            for m in ModeleDecoupagePlateforme.objects.order_by("nom")
        ]


def lire_modele(pk) -> dict:
    with _public():
        return _modele_en_dict(_modele(pk))


def enregistrer_modele(pk=None, *, auteur=None, **donnees) -> dict:
    """Créer (sans `pk`) ou mettre à jour un modèle ; la version augmente à chaque mise à jour."""
    with _public():
        modele = _modele(pk) if pk is not None else None
        version_avant = modele.version if modele else None
        modele = lm.enregistrer_modele_plateforme(modele=modele, auteur=auteur, **donnees)
        resultat = _modele_en_dict(modele)
    journaliser_plateforme(
        action="DECOUPAGE_MODELE_CREATION" if pk is None else "DECOUPAGE_MODELE_MODIFICATION",
        acteur=auteur,
        detail={
            "modele_id": resultat["id"],
            "nom": resultat["nom"],
            "version_avant": version_avant,
            "version": resultat["version"],
            "niveaux": resultat["niveaux_libelles"],
            "lignes": resultat["nombre_lignes"],
        },
    )
    return resultat


def retirer_modele(pk, *, auteur=None) -> None:
    """Retire un modèle (suppression logique). Aucun projet déjà créé n'est touché (§3.11) ; les
    copies personnalisées des entreprises restent les leurs."""
    with _public(), transaction.atomic():
        modele = _modele(pk)
        modele.delete(utilisateur=auteur)
    journaliser_plateforme(
        action="DECOUPAGE_MODELE_RETRAIT",
        acteur=auteur,
        detail={"modele_id": str(pk), "nom": modele.nom, "version": modele.version},
    )
