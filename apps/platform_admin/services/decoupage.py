"""Listes de valeurs et modèles de découpage de la plateforme, gérés au back-office.

Décisions v1.2 du découpage, §3 et §4 : le super admin crée les listes plateforme (« Phases »,
« Lots »…) et les modèles plateforme ; chaque entreprise les lit **sans copie**, depuis les tables
de la plateforme. Une correction faite ici est donc vue partout immédiatement.

- **Ce sont des tables de plateforme** (sans `entreprise_id`) : elles n'existent qu'une fois, et
  le back-office y écrit sans entreprise active (D9).
- **Les briques sont celles du découpage** (`apps.projets.services.listes_modeles`) : ajout de
  valeurs sans doublon, enregistrement d'un gabarit vérifié par C-1 à C-4, représentation d'un
  gabarit. Ce module n'ajoute que ce qui est propre à la plateforme : retrait d'une liste, d'une
  valeur ou d'un modèle (suppression logique), actions d'activation/désactivation/duplication,
  et la trace au journal de la plateforme.
- **Protection de suppression des listes** (amendement 23/11/2026, §4.1) : une liste utilisée par
  un modèle plateforme, un modèle d'entreprise ou un projet ne peut pas être supprimée (422) ; on
  la désactive (`est_actif=False`) pour la retirer des nouvelles propositions sans casser
  l'existant.

La lecture est ouverte au SUPPORT, l'écriture réservée au SUPERVISEUR (`exiger_superviseur`,
dans les vues).
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from rest_framework.exceptions import NotFound, ValidationError

from apps.catalogue.models import (
    LigneModelePlateforme,
    ListeValeursPlateforme,
    ModeleDecoupagePlateforme,
    NiveauModelePlateforme,
    ValeurListePlateforme,
)
from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.contexte import portee_plateforme
from apps.core.exceptions import ErreurMetier, LibelleEnDouble
from apps.platform_admin.services.notifications import journaliser_plateforme
from apps.projets.models import (
    ModeleDecoupageEntreprise,
    NiveauModeleEntreprise,
    NiveauProjet,
)
from apps.projets.services import listes_modeles as lm

__all__ = [
    "activer_liste",
    "activer_modele",
    "ajouter_valeurs",
    "creer_liste",
    "desactiver_liste",
    "desactiver_modele",
    "dupliquer_modele",
    "enregistrer_modele",
    "importer_valeurs_fichier",
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


# --------------------------------------------------------------------------
# Compteurs cross-tenant (sous portée plateforme) et représentations
# --------------------------------------------------------------------------
def _compter_utilisations_listes_entreprises(liste_ids: list) -> dict:
    """Nombre total de niveaux (modèles d'entreprise + projets actifs) utilisant chaque liste."""
    if not liste_ids:
        return {}
    with portee_plateforme(motif="comptage_utilisations_listes_plateforme"):
        par_modele = dict(
            NiveauModeleEntreprise.objects.filter(
                supprime_le__isnull=True,
                modele__supprime_le__isnull=True,
                liste_plateforme_id__in=liste_ids,
            )
            .values("liste_plateforme_id")
            .annotate(total=Count("id"))
            .values_list("liste_plateforme_id", "total")
        )
        par_projet = dict(
            NiveauProjet.objects.filter(
                supprime_le__isnull=True,
                projet__supprime_le__isnull=True,
                liste_plateforme_id__in=liste_ids,
            )
            .values("liste_plateforme_id")
            .annotate(total=Count("id"))
            .values_list("liste_plateforme_id", "total")
        )
    return {lid: par_modele.get(lid, 0) + par_projet.get(lid, 0) for lid in liste_ids}


def _compter_copies_entreprises(modele_ids: list) -> dict:
    """Nombre de copies personnalisées actives (`ModeleDecoupageEntreprise`) par `origine_id`."""
    if not modele_ids:
        return {}
    with portee_plateforme(motif="comptage_copies_modeles_plateforme"):
        return dict(
            ModeleDecoupageEntreprise.objects.filter(
                supprime_le__isnull=True,
                origine_id__in=modele_ids,
            )
            .values("origine_id")
            .annotate(total=Count("id"))
            .values_list("origine_id", "total")
        )


def _modeles_et_usages_plateforme(liste) -> tuple[list[dict], int]:
    """Les modèles plateforme actifs qui citent cette liste et le nombre de niveaux concernés."""
    niveaux = getattr(liste, "_niveaux_modeles_actifs", None)
    if niveaux is None:
        niveaux = list(
            NiveauModelePlateforme.objects.filter(
                liste=liste,
                supprime_le__isnull=True,
                modele__supprime_le__isnull=True,
            ).select_related("modele")
        )
    vus = {}
    for niveau in niveaux:
        vus.setdefault(niveau.modele_id, {"id": str(niveau.modele_id), "nom": niveau.modele.nom})
    return list(vus.values()), len(niveaux)


def _liste_en_dict(liste, *, avec_valeurs: bool = True) -> dict:
    modeles, usages_plateforme = _modeles_et_usages_plateforme(liste)
    if hasattr(liste, "_nombre_utilisations_entreprises"):
        usages_entreprises = liste._nombre_utilisations_entreprises
    else:
        usages_entreprises = _compter_utilisations_listes_entreprises([liste.pk]).get(liste.pk, 0)

    if avec_valeurs:
        valeurs = lm.valeurs_de_liste(liste)
        nombre_valeurs = getattr(liste, "_nombre_valeurs", len(valeurs))
    else:
        valeurs = None
        nombre_valeurs = getattr(liste, "_nombre_valeurs", None)
        if nombre_valeurs is None:
            nombre_valeurs = ValeurListePlateforme.objects.filter(liste=liste).count()

    donnees = {
        "id": str(liste.pk),
        "libelle": liste.libelle,
        "description": liste.description,
        "ordre": liste.ordre,
        "est_actif": liste.est_actif,
        "nombre_valeurs": nombre_valeurs,
        "nombre_utilisations_plateforme": usages_plateforme,
        "nombre_utilisations_entreprises": usages_entreprises,
        "modeles": modeles,
        "modifie_le": liste.modifie_le,
    }
    if avec_valeurs:
        donnees["valeurs"] = valeurs
    return donnees


def _modele_en_dict(modele, *, avec_gabarit: bool = True) -> dict:
    if hasattr(modele, "_nombre_copies_entreprises"):
        nombre_copies = modele._nombre_copies_entreprises
    else:
        nombre_copies = _compter_copies_entreprises([modele.pk]).get(modele.pk, 0)

    if avec_gabarit:
        gabarit = lm.gabarit_du_modele(modele)
        niveaux_libelles = [n["libelle"] for n in gabarit["niveaux"]]
        nombre_lignes = getattr(modele, "_nombre_lignes", len(gabarit["lignes"]))
    else:
        niveaux = lm._niveaux_du_modele(modele)
        niveaux_libelles = [n["libelle"] for n in niveaux]
        nombre_lignes = getattr(modele, "_nombre_lignes", None)
        if nombre_lignes is None:
            nombre_lignes = modele.lignes.filter(supprime_le__isnull=True).count()

    donnees = {
        "id": str(modele.pk),
        "nom": modele.nom,
        "description": modele.description,
        "types_projet": list(modele.types_projet or []),
        "par_defaut_pour": list(modele.par_defaut_pour or []),
        "version": modele.version,
        "est_actif": modele.est_actif,
        "niveaux_libelles": niveaux_libelles,
        "nombre_lignes": nombre_lignes,
        "nombre_copies_entreprises": nombre_copies,
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
        if (autre.cle_comparaison or cle_comparaison(autre.libelle)) == cle and (
            exclure is None or autre.pk != exclure.pk
        ):
            raise LibelleEnDouble(libelle, autre.libelle)


def _correspond_recherche(texte_recherche: str, *champs: str) -> bool:
    terme = (texte_recherche or "").strip()
    if not terme:
        return True
    cle_terme = cle_comparaison(terme)
    terme_lower = terme.lower()
    for champ in champs:
        if not champ:
            continue
        if terme_lower in champ.lower():
            return True
        if cle_terme and cle_terme in cle_comparaison(champ):
            return True
    return False


# --------------------------------------------------------------------------
# Listes de valeurs
# --------------------------------------------------------------------------
def lister_listes(
    *,
    avec_valeurs: bool = True,
    est_actif: bool | None = None,
    recherche: str | None = None,
) -> list[dict]:
    qs = ListeValeursPlateforme.objects.all()
    if est_actif is not None:
        qs = qs.filter(est_actif=est_actif)
    prefetches = [
        Prefetch(
            "niveaux_modeles",
            queryset=NiveauModelePlateforme.objects.filter(
                supprime_le__isnull=True,
                modele__supprime_le__isnull=True,
            ).select_related("modele"),
            to_attr="_niveaux_modeles_actifs",
        )
    ]
    if avec_valeurs:
        prefetches.append(
            Prefetch(
                "valeurs",
                queryset=ValeurListePlateforme.objects.order_by("ordre", "libelle"),
                to_attr="_valeurs_plateforme",
            )
        )
    listes = list(
        qs.annotate(_nombre_valeurs=Count("valeurs", filter=Q(valeurs__supprime_le__isnull=True)))
        .prefetch_related(*prefetches)
        .order_by("ordre", "libelle")
    )
    if recherche and recherche.strip():
        listes = [
            item
            for item in listes
            if _correspond_recherche(recherche, item.libelle, item.description)
        ]
    usages_ent = _compter_utilisations_listes_entreprises([item.pk for item in listes])
    for item in listes:
        item._nombre_utilisations_entreprises = usages_ent.get(item.pk, 0)
    return [_liste_en_dict(liste, avec_valeurs=avec_valeurs) for liste in listes]


def lire_liste(pk) -> dict:
    return _liste_en_dict(_liste(pk))


def creer_liste(*, libelle: str, description: str = "", valeurs=None, auteur=None) -> dict:
    with transaction.atomic():
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
    """Renommer, décrire, réordonner ou activer/désactiver une liste. Les niveaux qui la citent la
    suivent : le lien passe par l'identifiant, jamais par le nom (§4.3)."""
    with transaction.atomic():
        liste = _liste(pk)
        avant = {
            "libelle": liste.libelle,
            "description": liste.description,
            "ordre": liste.ordre,
            "est_actif": liste.est_actif,
        }
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
        if "est_actif" in donnees:
            liste.est_actif = bool(donnees["est_actif"])
        liste.save()
        resultat = _liste_en_dict(liste)
    journaliser_plateforme(
        action="DECOUPAGE_LISTE_MODIFICATION",
        acteur=auteur,
        detail={
            "liste_id": str(pk),
            "avant": avant,
            "apres": {
                k: resultat[k] for k in ("libelle", "description", "ordre", "est_actif")
            },
        },
    )
    return resultat


def _basculer_statut_liste(pk, *, est_actif: bool, action_audit: str, auteur=None) -> dict:
    with transaction.atomic():
        liste = _liste(pk)
        liste.est_actif = est_actif
        liste.save(update_fields=["est_actif", "modifie_le"])
        resultat = _liste_en_dict(liste)
    journaliser_plateforme(
        action=action_audit,
        acteur=auteur,
        detail={
            "liste_id": str(liste.pk),
            "libelle": liste.libelle,
            "est_actif": est_actif,
        },
    )
    return resultat


def activer_liste(pk, *, auteur=None) -> dict:
    """Active une liste de valeurs plateforme (`est_actif=True`)."""
    return _basculer_statut_liste(
        pk, est_actif=True, action_audit="DECOUPAGE_LISTE_ACTIVATION", auteur=auteur
    )


def desactiver_liste(pk, *, auteur=None) -> dict:
    """Désactive une liste de valeurs plateforme (`est_actif=False`)."""
    return _basculer_statut_liste(
        pk, est_actif=False, action_audit="DECOUPAGE_LISTE_DESACTIVATION", auteur=auteur
    )


def retirer_liste(pk, *, auteur=None) -> None:
    """Retire une liste (suppression logique).

    Refusé (422) dès qu'un modèle plateforme, un modèle d'entreprise ou un projet actif y puise :
    l'erreur indique les compteurs d'utilisation et invite à désactiver la liste (`est_actif=False`)
    plutôt que la supprimer (amendement 23/11/2026, §4.1).
    """
    with transaction.atomic():
        liste = _liste(pk)
        modeles, usages_plateforme = _modeles_et_usages_plateforme(liste)
        with portee_plateforme(motif="verification_suppression_liste_plateforme"):
            usages_modeles_entreprise = NiveauModeleEntreprise.objects.filter(
                liste_plateforme=liste,
                supprime_le__isnull=True,
                modele__supprime_le__isnull=True,
            ).count()
            usages_projets = NiveauProjet.objects.filter(
                liste_plateforme=liste,
                supprime_le__isnull=True,
                projet__supprime_le__isnull=True,
            ).count()

        if usages_plateforme or usages_modeles_entreprise or usages_projets:
            noms = ", ".join(f"« {m['nom']} »" for m in modeles)
            precision_modeles = f" (notamment par les modèles plateforme {noms})" if noms else ""
            raise ErreurMetier(
                f"Cette liste « {liste.libelle} » est actuellement utilisée{precision_modeles} "
                f"(modèles plateforme : {usages_plateforme}, "
                f"modèles d'entreprise : {usages_modeles_entreprise}, "
                f"projets : {usages_projets}). "
                "Désactivez-la (est_actif=False) plutôt que de la supprimer.",
                details={
                    "usages_plateforme": usages_plateforme,
                    "usages_modeles_entreprise": usages_modeles_entreprise,
                    "usages_projets": usages_projets,
                    "modeles": modeles,
                },
            )
        liste.valeurs.filter(supprime_le__isnull=True).supprimer_logiquement(utilisateur=auteur)
        liste.delete(utilisateur=auteur)
    journaliser_plateforme(
        action="DECOUPAGE_LISTE_RETRAIT",
        acteur=auteur,
        detail={"liste_id": str(pk), "libelle": liste.libelle},
    )


def ajouter_valeurs(pk, *, valeurs: list[str], groupe: str = "", auteur=None) -> dict:
    """Ajout en masse ; une valeur déjà présente (sans accents, casse ni espaces) est ignorée."""
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


def importer_valeurs_fichier(pk, *, fichier, auteur=None) -> dict:
    """Import Excel/CSV de valeurs dans une liste de la plateforme."""
    liste = _liste(pk)
    resultat = lm.importer_valeurs_fichier(
        liste, fichier, par_la_plateforme=True, auteur=auteur
    )
    if resultat["ajoutees"]:
        journaliser_plateforme(
            action="DECOUPAGE_VALEURS_IMPORT",
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
    with transaction.atomic():
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
    with transaction.atomic():
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
def lister_modeles(
    *,
    recherche: str | None = None,
    type_projet: str | None = None,
    est_actif: bool | None = None,
) -> list[dict]:
    """Tous les modèles de la plateforme, actifs ou non, filtrables et sans requête N+1."""
    qs = ModeleDecoupagePlateforme.objects.all()
    if est_actif is not None:
        qs = qs.filter(est_actif=est_actif)
    modeles = list(
        qs.annotate(_nombre_lignes=Count("lignes", filter=Q(lignes__supprime_le__isnull=True)))
        .prefetch_related(
            Prefetch(
                "niveaux",
                queryset=NiveauModelePlateforme.objects.filter(supprime_le__isnull=True)
                .select_related("liste")
                .order_by("ordre"),
                to_attr="_niveaux_actifs",
            )
        )
        .order_by("nom")
    )
    if recherche and recherche.strip():
        modeles = [
            m for m in modeles if _correspond_recherche(recherche, m.nom, m.description)
        ]
    if type_projet and type_projet.strip():
        code_type = type_projet.strip()
        modeles = [m for m in modeles if code_type in (m.types_projet or [])]

    copies_par_id = _compter_copies_entreprises([m.pk for m in modeles])
    for m in modeles:
        m._nombre_copies_entreprises = copies_par_id.get(m.pk, 0)
    return [_modele_en_dict(m, avec_gabarit=False) for m in modeles]


def lire_modele(pk) -> dict:
    return _modele_en_dict(_modele(pk))


def enregistrer_modele(pk=None, *, auteur=None, **donnees) -> dict:
    """Créer (sans `pk`) ou mettre à jour un modèle (complet ou partiel).

    La version n'augmente que si le gabarit (`niveaux` ou `lignes`) a réellement changé.
    """
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
            "est_actif": resultat["est_actif"],
            "niveaux": resultat["niveaux_libelles"],
            "lignes": resultat["nombre_lignes"],
        },
    )
    return resultat


def _basculer_statut_modele(pk, *, est_actif: bool, action_audit: str, auteur=None) -> dict:
    with transaction.atomic():
        modele = _modele(pk)
        modele.est_actif = est_actif
        modele.save(update_fields=["est_actif", "modifie_le"])
        resultat = _modele_en_dict(modele)
    journaliser_plateforme(
        action=action_audit,
        acteur=auteur,
        detail={
            "modele_id": resultat["id"],
            "nom": resultat["nom"],
            "version": resultat["version"],
            "est_actif": est_actif,
        },
    )
    return resultat


def activer_modele(pk, *, auteur=None) -> dict:
    """Active un modèle de la plateforme (`est_actif=True`) sans incrémenter `version`."""
    return _basculer_statut_modele(
        pk, est_actif=True, action_audit="DECOUPAGE_MODELE_ACTIVATION", auteur=auteur
    )


def desactiver_modele(pk, *, auteur=None) -> dict:
    """Désactive un modèle de la plateforme (`est_actif=False`) sans incrémenter `version`."""
    return _basculer_statut_modele(
        pk, est_actif=False, action_audit="DECOUPAGE_MODELE_DESACTIVATION", auteur=auteur
    )


def dupliquer_modele(pk, *, auteur=None) -> dict:
    """Clone un modèle plateforme avec un nom unique (`{nom} (copie)`, `{nom} (copie 2)`…),
    `version=1`, `est_actif=True`, mêmes `description`, `types_projet`, `niveaux` et `lignes`,
    et `par_defaut_pour=[]` (pour ne pas voler le défaut de l'original)."""
    with transaction.atomic():
        source = _modele(pk)
        cles_existantes = {
            m.cle_comparaison or cle_comparaison(m.nom)
            for m in ModeleDecoupagePlateforme.objects.all()
        }
        base = source.nom.strip()
        rang = 1
        while True:
            suffixe = " (copie)" if rang == 1 else f" (copie {rang})"
            candidat = f"{base[: 150 - len(suffixe)].rstrip()}{suffixe}"
            if cle_comparaison(candidat) not in cles_existantes:
                break
            rang += 1

        copie = ModeleDecoupagePlateforme.objects.create(
            nom=candidat,
            description=source.description,
            types_projet=list(source.types_projet or []),
            par_defaut_pour=[],
            version=1,
            est_actif=True,
            cree_par=auteur,
        )
        for n in source.niveaux.filter(supprime_le__isnull=True).order_by("ordre"):
            NiveauModelePlateforme.objects.create(
                modele=copie,
                ordre=n.ordre,
                libelle=n.libelle,
                liste=n.liste,
                alerter=n.alerter,
                cree_par=auteur,
            )
        lignes_a_creer = [
            LigneModelePlateforme(
                modele=copie,
                ordre=ligne.ordre,
                valeurs=list(ligne.valeurs or []),
                cree_par=auteur,
            )
            for ligne in source.lignes.filter(supprime_le__isnull=True).order_by("ordre")
        ]
        if lignes_a_creer:
            LigneModelePlateforme.objects.bulk_create(lignes_a_creer, batch_size=1000)
        copie._nombre_copies_entreprises = 0
        resultat = _modele_en_dict(copie)

    journaliser_plateforme(
        action="DECOUPAGE_MODELE_DUPLICATION",
        acteur=auteur,
        detail={
            "modele_id": resultat["id"],
            "nom": resultat["nom"],
            "source_id": str(source.pk),
            "source_nom": source.nom,
            "version": resultat["version"],
        },
    )
    return resultat


def retirer_modele(pk, *, auteur=None) -> None:
    """Retire un modèle (suppression logique cascadée sur ses niveaux et lignes).
    Aucun projet déjà créé n'est touché (§3.11) ; les copies personnalisées des entreprises
    restent les leurs et exposent `original_supprime=True`."""
    with transaction.atomic():
        modele = _modele(pk)
        modele.niveaux.filter(supprime_le__isnull=True).supprimer_logiquement(utilisateur=auteur)
        modele.lignes.filter(supprime_le__isnull=True).supprimer_logiquement(utilisateur=auteur)
        modele.delete(utilisateur=auteur)
    journaliser_plateforme(
        action="DECOUPAGE_MODELE_RETRAIT",
        acteur=auteur,
        detail={"modele_id": str(pk), "nom": modele.nom, "version": modele.version},
    )
