"""Listes de valeurs et modèles de découpage, vus par une entreprise (décisions v1.2, §3 et §4).

Une entreprise voit **deux sources fusionnées** : celles de la plateforme (plateforme, lues
sans copie) et les siennes. Une liste ou un modèle se désigne donc par un couple
`{"origine": "PLATEFORME" | "ENTREPRISE", "id": "<uuid>"}`, jamais par son nom.

- Elle ajoute des valeurs aux listes plateforme et crée ses propres listes ; elle ne retire pas
  une valeur plateforme.
- Elle crée ses propres modèles et **personnalise** un modèle plateforme : la copie lui reste
  liée par identifiant, s'affiche « Nom (personnalisé) » et signale quand l'original a changé.
- Un modèle porte un **gabarit** (niveaux ordonnés, une liste au plus par niveau) et des **lignes
  types** : `{"niveaux": [{"libelle", "liste", "alerter"}], "lignes": [[...], ...]}`.

**Le back-office s'en sert aussi** (`apps.platform_admin.services.decoupage`) : appelés hors
entreprise, ces services ne voient que la plateforme — une liste n'y a que ses valeurs
plateforme, et un modèle plateforme ne puise que dans des listes plateforme (§3.8).
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
from apps.core.contexte import entreprise_courante_id
from apps.core.enums import ActionAudit
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
    "generer_modele_excel_liste",
    "importer_valeurs_fichier",
    "liste_en_dict",
    "listes_disponibles",
    "modele_en_dict",
    "modele_par_defaut",
    "modeles_disponibles",
    "modifier_liste_entreprise",
    "personnaliser_modele",
    "reference_liste",
    "resoudre_liste",
    "resoudre_modele",
    "retirer_liste_entreprise",
    "retirer_modele_entreprise",
    "retirer_valeur",
    "valeurs_de_liste",
]

PLATEFORME = "PLATEFORME"
ENTREPRISE = "ENTREPRISE"


def _hors_entreprise() -> bool:
    """Le back-office travaille sans entreprise active (D9) : les tables d'entreprise lui sont
    fermées, comme l'était `public` dans l'ancien modèle multi-schéma."""
    return entreprise_courante_id() is None


def nom_propre(texte: str) -> str:
    return " ".join((texte or "").split())


def _journaliser_entreprise(
    *,
    action: str,
    type_entite: str,
    entite_id,
    auteur=None,
    valeur_avant: dict | None = None,
    valeur_apres: dict | None = None,
) -> None:
    """Trace les opérations d'écriture de l'entreprise au JournalAudit (Socle Commun §2.4)."""
    if _hors_entreprise():
        return
    from apps.audit.services import journaliser

    journaliser(
        action=action,
        type_entite=type_entite,
        entite_id=entite_id,
        utilisateur_id=getattr(auteur, "pk", None),
        valeur_avant=valeur_avant,
        valeur_apres=valeur_apres,
    )


# --------------------------------------------------------------------------
# Listes
# --------------------------------------------------------------------------
def resoudre_liste(reference):
    """`{"origine", "id"}` → la liste (plateforme ou entreprise) ; None si la référence est vide.

    Une `ListeValeursPlateforme` existante non supprimée (`supprime_le__isnull=True`) reste
    acceptée même si `est_actif=False`, afin de ne jamais casser un modèle d'entreprise ou un
    projet existant lorsque le Super Admin désactive une liste.
    """
    if not reference:
        return None
    origine = (reference.get("origine") or "").upper()
    ident = reference.get("id")
    if origine == PLATEFORME:
        modele = ListeValeursPlateforme
    elif origine == ENTREPRISE:
        if _hors_entreprise():
            raise ValidationError({"liste": "Cette liste est introuvable."})
        modele = ListeValeursEntreprise
    else:
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

    Hors entreprise (back-office), seulement celles de la plateforme.
    Exploite les attributs préchargés (`_valeurs_plateforme`, `_valeurs_entreprise`) s'ils sont
    présents pour éviter toute requête N+1.
    """
    if liste is None:
        return []
    valeurs = []
    if isinstance(liste, ListeValeursPlateforme):
        vals_plat = getattr(liste, "_valeurs_plateforme", None)
        if vals_plat is None:
            vals_plat = ValeurListePlateforme.objects.filter(liste=liste).order_by(
                "ordre", "libelle"
            )
        valeurs += [_valeur_en_dict(v, PLATEFORME) for v in vals_plat]
        if _hors_entreprise():
            return valeurs
        vals_ent = getattr(liste, "_valeurs_entreprise", None)
        if vals_ent is None:
            vals_ent = ValeurListeEntreprise.objects.filter(liste_plateforme=liste).order_by(
                "ordre", "libelle"
            )
    else:
        if _hors_entreprise():
            return []
        vals_ent = getattr(liste, "_valeurs_entreprise", None)
        if vals_ent is None:
            vals_ent = ValeurListeEntreprise.objects.filter(liste_entreprise=liste).order_by(
                "ordre", "libelle"
            )
    valeurs += [_valeur_en_dict(v, ENTREPRISE) for v in vals_ent]
    return valeurs


def liste_en_dict(liste, *, avec_valeurs: bool = True) -> dict:
    donnees = {
        **reference_liste(liste),
        "description": liste.description,
        "modifiable": isinstance(liste, ListeValeursEntreprise),
    }
    if avec_valeurs:
        valeurs = valeurs_de_liste(liste)
        donnees["valeurs"] = valeurs
        donnees["nombre_valeurs"] = len(valeurs)
    elif hasattr(liste, "_nombre_valeurs"):
        donnees["nombre_valeurs"] = liste._nombre_valeurs
    return donnees


def listes_disponibles(*, avec_valeurs: bool = True) -> list[dict]:
    """Les listes actives de la plateforme suivies des listes de l'entreprise, sans N+1."""
    hors = _hors_entreprise()
    qs_plateforme = ListeValeursPlateforme.objects.filter(est_actif=True).order_by(
        "ordre", "libelle"
    )
    if avec_valeurs:
        prefetches_plat = [
            Prefetch(
                "valeurs",
                queryset=ValeurListePlateforme.objects.order_by("ordre", "libelle"),
                to_attr="_valeurs_plateforme",
            )
        ]
        if not hors:
            prefetches_plat.append(
                Prefetch(
                    "valeurs_entreprises",
                    queryset=ValeurListeEntreprise.objects.order_by("ordre", "libelle"),
                    to_attr="_valeurs_entreprise",
                )
            )
        plateforme = list(qs_plateforme.prefetch_related(*prefetches_plat))
        entreprise = (
            []
            if hors
            else list(
                ListeValeursEntreprise.objects.prefetch_related(
                    Prefetch(
                        "valeurs",
                        queryset=ValeurListeEntreprise.objects.order_by("ordre", "libelle"),
                        to_attr="_valeurs_entreprise",
                    )
                ).order_by("ordre", "libelle")
            )
        )
    else:
        plateforme = list(
            qs_plateforme.annotate(
                _nb_val_plat=Count("valeurs", filter=Q(valeurs__supprime_le__isnull=True))
            )
        )
        ajouts_par_liste = (
            {}
            if hors or not plateforme
            else dict(
                ValeurListeEntreprise.objects.filter(
                    liste_plateforme_id__in=[item.pk for item in plateforme]
                )
                .values("liste_plateforme_id")
                .annotate(n=Count("id"))
                .values_list("liste_plateforme_id", "n")
            )
        )
        for l_plat in plateforme:
            l_plat._nombre_valeurs = l_plat._nb_val_plat + ajouts_par_liste.get(l_plat.pk, 0)
        entreprise = (
            []
            if hors
            else list(
                ListeValeursEntreprise.objects.annotate(
                    _nombre_valeurs=Count("valeurs", filter=Q(valeurs__supprime_le__isnull=True))
                ).order_by("ordre", "libelle")
            )
        )
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
    a_creer = []
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
            valeur = ValeurListePlateforme(
                liste=liste,
                libelle=propre,
                groupe=groupe,
                cle_comparaison=cle,
                ordre=ordre,
                cree_par=auteur,
            )
        else:
            valeur = ValeurListeEntreprise(
                liste_entreprise=liste if isinstance(liste, ListeValeursEntreprise) else None,
                liste_plateforme=liste if isinstance(liste, ListeValeursPlateforme) else None,
                libelle=propre,
                groupe=groupe,
                cle_comparaison=cle,
                ordre=ordre,
                cree_par=auteur,
            )
        a_creer.append(valeur)
        ajoutees.append(
            {"id": str(valeur.pk), "libelle": valeur.libelle, "groupe": groupe, "ordre": ordre}
        )
    if a_creer:
        classe_valeur = ValeurListePlateforme if par_la_plateforme else ValeurListeEntreprise
        classe_valeur.objects.bulk_create(a_creer, batch_size=1000)
        if not par_la_plateforme:
            _journaliser_entreprise(
                action=ActionAudit.CREATION,
                type_entite="ValeurListeEntreprise",
                entite_id=liste.pk,
                auteur=auteur,
                valeur_apres={
                    "liste_id": str(liste.pk),
                    "libelle_liste": liste.libelle,
                    "groupe": groupe,
                    "valeurs": [v["libelle"] for v in ajoutees],
                },
            )
    return {"ajoutees": ajoutees, "ignorees": ignorees}


@transaction.atomic
def creer_liste(
    libelle: str,
    description: str = "",
    valeurs: list[str] | None = None,
    *,
    auteur=None,
):
    propre = nom_propre(libelle)
    if not propre:
        raise ValidationError({"libelle": "Le nom de la liste est obligatoire."})
    cle = cle_comparaison(propre)
    homonymes = [
        liste.libelle
        for liste in [
            *ListeValeursPlateforme.objects.all(),
            *([] if _hors_entreprise() else ListeValeursEntreprise.objects.all()),
        ]
        if (liste.cle_comparaison or cle_comparaison(liste.libelle)) == cle
    ]
    if homonymes:
        raise ErreurMetier(
            f"Une liste porte déjà ce nom : « {homonymes[0]} ».",
            details={"libelle": propre},
        )
    liste = ListeValeursEntreprise.objects.create(
        libelle=propre,
        description=description,
        cree_par=auteur,
    )
    _journaliser_entreprise(
        action=ActionAudit.CREATION,
        type_entite="ListeValeursEntreprise",
        entite_id=liste.pk,
        auteur=auteur,
        valeur_apres={"libelle": liste.libelle, "description": liste.description},
    )
    if valeurs:
        ajouter_valeurs(liste, valeurs, auteur=auteur)
    return liste


@transaction.atomic
def retirer_valeur(valeur_id, utilisateur=None) -> None:
    """Retire une valeur ajoutée par l'entreprise. Une valeur de la plateforme ne se retire pas."""
    valeur = ValeurListeEntreprise.objects.filter(pk=valeur_id).first()
    if valeur is None:
        if ValeurListePlateforme.objects.filter(pk=valeur_id).exists():
            raise ErreurMetier("Une valeur fournie par la plateforme ne se retire pas.")
        raise NotFound("Cette valeur est introuvable.")
    avant = {
        "libelle": valeur.libelle,
        "groupe": valeur.groupe,
        "liste_entreprise_id": str(valeur.liste_entreprise_id)
        if valeur.liste_entreprise_id
        else None,
        "liste_plateforme_id": str(valeur.liste_plateforme_id)
        if valeur.liste_plateforme_id
        else None,
    }
    # Retirer une valeur ne change aucune case déjà saisie (§4.8) : elle n'est plus proposée.
    valeur.delete(utilisateur=utilisateur)
    _journaliser_entreprise(
        action=ActionAudit.SUPPRESSION,
        type_entite="ValeurListeEntreprise",
        entite_id=valeur.pk,
        auteur=utilisateur,
        valeur_avant=avant,
    )


@transaction.atomic
def modifier_liste_entreprise(
    liste,
    *,
    libelle: str | None = None,
    description: str | None = None,
    auteur=None,
):
    """Renommer ou décrire une liste créée par l'entreprise."""
    if not isinstance(liste, ListeValeursEntreprise):
        raise ErreurMetier("Une liste fournie par la plateforme ne se modifie pas.")
    avant = {"libelle": liste.libelle, "description": liste.description}
    if libelle is not None:
        propre = nom_propre(libelle)
        if not propre:
            raise ValidationError({"libelle": "Le nom de la liste est obligatoire."})
        cle = cle_comparaison(propre)
        homonymes = [
            autre.libelle
            for autre in [
                *ListeValeursPlateforme.objects.all(),
                *ListeValeursEntreprise.objects.all(),
            ]
            if autre.pk != liste.pk
            and (autre.cle_comparaison or cle_comparaison(autre.libelle)) == cle
        ]
        if homonymes:
            raise ErreurMetier(
                f"Une liste porte déjà ce nom : « {homonymes[0]} ».",
                details={"libelle": propre},
            )
        liste.libelle = propre
    if description is not None:
        liste.description = description
    liste.save()
    _journaliser_entreprise(
        action=ActionAudit.MODIFICATION,
        type_entite="ListeValeursEntreprise",
        entite_id=liste.pk,
        auteur=auteur,
        valeur_avant=avant,
        valeur_apres={"libelle": liste.libelle, "description": liste.description},
    )
    return liste


@transaction.atomic
def retirer_liste_entreprise(liste, utilisateur=None) -> None:
    """Retire une liste créée par l'entreprise (suppression logique)."""
    if not isinstance(liste, ListeValeursEntreprise):
        raise ErreurMetier("Une liste fournie par la plateforme ne se retire pas.")
    niveaux = NiveauModeleEntreprise.objects.filter(
        liste_entreprise=liste, modele__supprime_le__isnull=True
    ).select_related("modele")
    if niveaux.exists():
        noms = ", ".join(sorted({f"« {n.modele.nom} »" for n in niveaux}))
        raise ErreurMetier(
            f"Cette liste sert encore aux modèles {noms} : changez la liste de leurs niveaux, "
            "ou retirez ces modèles, avant de la retirer."
        )
    avant = {"libelle": liste.libelle, "description": liste.description}
    liste.valeurs.filter(supprime_le__isnull=True).supprimer_logiquement(utilisateur=utilisateur)
    liste.delete(utilisateur=utilisateur)
    _journaliser_entreprise(
        action=ActionAudit.SUPPRESSION,
        type_entite="ListeValeursEntreprise",
        entite_id=liste.pk,
        auteur=utilisateur,
        valeur_avant=avant,
    )


_ENTETES_LIBELLE = {"libelle", "libelles", "valeur", "valeurs", "nom", "intitule", "designation"}
_ENTETES_GROUPE = {
    "groupe",
    "groupes",
    "groupe (optionnel)",
    "groupe (facultatif)",
    "categorie",
    "famille",
}


@transaction.atomic
def importer_valeurs_fichier(
    liste, fichier, *, par_la_plateforme: bool = False, auteur=None
) -> dict:
    """Importe les valeurs d'une liste depuis un fichier `.xlsx` ou `.csv`
    (colonnes Libellé | Groupe)."""
    from apps.projets.services.import_export import lire_fichier

    if par_la_plateforme and not isinstance(liste, ListeValeursPlateforme):
        raise ErreurMetier("La plateforme n'ajoute des valeurs qu'à ses propres listes.")
    lignes = lire_fichier(fichier)
    if not lignes:
        raise ValidationError({"fichier": "Le fichier est vide."})

    premiere = [cle_comparaison(c) for c in lignes[0]]
    col_libelle, col_groupe = 0, 1
    debut = 0
    if any(c in _ENTETES_LIBELLE or c in _ENTETES_GROUPE for c in premiere):
        debut = 1
        col_libelle = next((i for i, c in enumerate(premiere) if c in _ENTETES_LIBELLE), 0)
        col_groupe = next(
            (i for i, c in enumerate(premiere) if c in _ENTETES_GROUPE),
            1 if col_libelle == 0 else 0,
        )

    donnees = lignes[debut:]
    if not donnees:
        raise ValidationError({"fichier": "Aucune valeur trouvée sous la ligne d'en-tête."})

    deja = valeurs_de_liste(liste)
    existantes = {cle_comparaison(v["libelle"]) for v in deja}
    ordre = max((v["ordre"] for v in deja), default=0)
    ajoutees, ignorees = [], []
    a_creer = []

    for ligne in donnees:
        libelle = nom_propre(ligne[col_libelle] if col_libelle < len(ligne) else "")
        if not libelle:
            continue
        groupe = nom_propre(
            ligne[col_groupe]
            if col_groupe is not None and col_groupe != col_libelle and col_groupe < len(ligne)
            else ""
        )[:100]
        libelle = libelle[:200]
        cle = cle_comparaison(libelle)
        if cle in existantes:
            ignorees.append(libelle)
            continue
        existantes.add(cle)
        ordre += 1
        if par_la_plateforme:
            valeur = ValeurListePlateforme(
                liste=liste,
                libelle=libelle,
                groupe=groupe,
                cle_comparaison=cle,
                ordre=ordre,
                cree_par=auteur,
            )
        else:
            valeur = ValeurListeEntreprise(
                liste_entreprise=liste if isinstance(liste, ListeValeursEntreprise) else None,
                liste_plateforme=liste if isinstance(liste, ListeValeursPlateforme) else None,
                libelle=libelle,
                groupe=groupe,
                cle_comparaison=cle,
                ordre=ordre,
                cree_par=auteur,
            )
        a_creer.append(valeur)
        ajoutees.append(
            {"id": str(valeur.pk), "libelle": valeur.libelle, "groupe": groupe, "ordre": ordre}
        )
    if a_creer:
        classe_valeur = ValeurListePlateforme if par_la_plateforme else ValeurListeEntreprise
        classe_valeur.objects.bulk_create(a_creer, batch_size=1000)
        if not par_la_plateforme:
            _journaliser_entreprise(
                action=ActionAudit.CREATION,
                type_entite="ValeurListeEntreprise",
                entite_id=liste.pk,
                auteur=auteur,
                valeur_apres={
                    "liste_id": str(liste.pk),
                    "libelle_liste": liste.libelle,
                    "evenement": "IMPORT_FICHIER",
                    "valeurs": [v["libelle"] for v in ajoutees],
                },
            )
    return {"ajoutees": ajoutees, "ignorees": ignorees}


def generer_modele_excel_liste() -> tuple[bytes, str]:
    """Génère le fichier `.xlsx` exemple type à remplir pour importer les valeurs d'une liste."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Valeurs à importer"

    fond_entete = PatternFill(start_color="1B3A4B", end_color="1B3A4B", fill_type="solid")
    police_entete = Font(bold=True, color="FFFFFF", size=11)
    police_exemple = Font(italic=True, color="475569", size=10)

    entetes = ["Libellé", "Groupe (optionnel)"]
    feuille.append(entetes)
    for col in range(1, len(entetes) + 1):
        cellule = feuille.cell(row=1, column=col)
        cellule.fill = fond_entete
        cellule.font = police_entete
        cellule.alignment = Alignment(vertical="center")

    exemples = [
        ["Terrassement général", "Gros œuvre"],
        ["Fondations béton armé", "Gros œuvre"],
        ["Électricité courant fort / faible", "Second œuvre"],
    ]
    for rang, ligne in enumerate(exemples, start=2):
        feuille.append(ligne)
        for col in range(1, len(ligne) + 1):
            feuille.cell(row=rang, column=col).font = police_exemple

    feuille.column_dimensions["A"].width = 42
    feuille.column_dimensions["B"].width = 32
    feuille.freeze_panes = "A2"

    aide = classeur.create_sheet(title="Mode d'emploi")
    aide.append(["Colonne", "Obligatoire", "Description"])
    for col in range(1, 4):
        cellule = aide.cell(row=1, column=col)
        cellule.fill = fond_entete
        cellule.font = police_entete
    aide.append(
        [
            "Libellé",
            "Oui",
            (
                "Le nom de la valeur proposée dans les listes déroulantes (200 caractères max). "
                "Les doublons sont ignorés automatiquement."
            ),
        ]
    )
    aide.append(
        [
            "Groupe (optionnel)",
            "Non",
            (
                "Permet de regrouper visuellement les valeurs par famille ou catégorie dans le "
                "sélecteur (100 caractères max)."
            ),
        ]
    )
    aide.column_dimensions["A"].width = 24
    aide.column_dimensions["B"].width = 16
    aide.column_dimensions["C"].width = 85

    tampon = io.BytesIO()
    classeur.save(tampon)
    return (
        tampon.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


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
        if _hors_entreprise():
            raise NotFound("Ce modèle de découpage est introuvable.")
        modele = ModeleDecoupageEntreprise.objects.filter(pk=ident).first()
    else:
        raise ValidationError({"modele": "L'origine d'un modèle est PLATEFORME ou ENTREPRISE."})
    if modele is None:
        raise NotFound("Ce modèle de découpage est introuvable.")
    return modele


def _niveaux_du_modele(modele) -> list[dict]:
    plateforme = isinstance(modele, ModeleDecoupagePlateforme)
    niveaux_qs = getattr(modele, "_niveaux_actifs", None)
    if niveaux_qs is None:
        if plateforme:
            niveaux_qs = (
                modele.niveaux.filter(supprime_le__isnull=True)
                .select_related("liste")
                .order_by("ordre")
            )
        else:
            niveaux_qs = (
                modele.niveaux.filter(supprime_le__isnull=True)
                .select_related("liste_plateforme", "liste_entreprise")
                .order_by("ordre")
            )
    niveaux = []
    for n in niveaux_qs:
        liste = n.liste if plateforme else (n.liste_plateforme or n.liste_entreprise)
        niveaux.append(
            {"libelle": n.libelle, "liste": reference_liste(liste), "alerter": n.alerter}
        )
    return niveaux


def gabarit_du_modele(modele) -> dict:
    niveaux = _niveaux_du_modele(modele)
    lignes_qs = getattr(modele, "_lignes_actives", None)
    if lignes_qs is None:
        lignes_qs = modele.lignes.filter(supprime_le__isnull=True).order_by("ordre")
    lignes = [
        list(ligne.valeurs) + [""] * max(0, len(niveaux) - len(ligne.valeurs))
        for ligne in lignes_qs
    ]
    return {"niveaux": niveaux, "lignes": lignes}


def _nom_affiche(modele, noms_plateforme: set[str]) -> str:
    if isinstance(modele, ModeleDecoupagePlateforme):
        return modele.nom
    if modele.origine_id:
        return f"{modele.nom} (personnalisé)"
    if (modele.cle_comparaison or cle_comparaison(modele.nom)) in noms_plateforme:
        return f"{modele.nom} (entreprise)"
    return modele.nom


def _modele_en_dict(modele, noms_plateforme, type_projet=None, defaut=None) -> dict:
    plateforme = isinstance(modele, ModeleDecoupagePlateforme)
    niveaux = _niveaux_du_modele(modele)
    if hasattr(modele, "_nombre_lignes"):
        nombre_lignes = modele._nombre_lignes
    else:
        nombre_lignes = modele.lignes.filter(supprime_le__isnull=True).count()
    donnees = {
        "origine": PLATEFORME if plateforme else ENTREPRISE,
        "id": str(modele.pk),
        "nom": modele.nom,
        "nom_affiche": _nom_affiche(modele, noms_plateforme),
        "description": modele.description,
        "types_projet": list(modele.types_projet or []),
        "par_defaut_pour": list(modele.par_defaut_pour or []),
        "niveaux": [n["libelle"] for n in niveaux],
        "nombre_lignes": nombre_lignes,
        "modifiable": not plateforme,
        "pour_ce_type": bool(type_projet and type_projet in (modele.types_projet or [])),
        "par_defaut": (
            defaut is not None
            and isinstance(modele, type(defaut))
            and defaut.pk == modele.pk
        ),
    }
    if not plateforme:
        origine = modele.origine
        origine_disponible = bool(origine and origine.supprime_le is None and origine.est_actif)
        donnees["est_personnalise"] = bool(modele.origine_id)
        donnees["origine_plateforme_id"] = str(modele.origine_id) if origine_disponible else None
        donnees["original_supprime"] = bool(modele.origine_id and not origine_disponible)
        # La copie ne suit plus son original : elle signale seulement qu'il a changé (§3.6).
        donnees["original_modifie"] = bool(
            origine_disponible
            and modele.version_origine
            and origine.version > modele.version_origine
        )
    else:
        donnees["est_personnalise"] = False
        donnees["origine_plateforme_id"] = None
        donnees["original_supprime"] = False
        donnees["original_modifie"] = False
    return donnees


def modele_par_defaut(
    type_projet: str | None,
    *,
    plateforme: list | None = None,
    entreprise: list | None = None,
):
    """Le modèle qui pré-remplit le tableau d'un projet de ce type (amendement 23/11/2026, §3.9).

    Priorité :
    1. Modèle `ENTREPRISE` contenant `type_projet` dans `par_defaut_pour` ;
    2. Modèle `PLATEFORME` (`est_actif=True`) contenant `type_projet` dans `par_defaut_pour` ;
    3. Modèle `PLATEFORME` (`est_actif=True`) contenant `type_projet` dans `types_projet` ;
    4. Modèle `ENTREPRISE` contenant `type_projet` dans `types_projet` ;
    5. Repli : premier modèle `PLATEFORME` (`est_actif=True`), sinon premier modèle `ENTREPRISE`.
    """
    if plateforme is None:
        plateforme = list(ModeleDecoupagePlateforme.objects.filter(est_actif=True).order_by("nom"))
    if entreprise is None:
        entreprise = (
            []
            if _hors_entreprise()
            else list(ModeleDecoupageEntreprise.objects.order_by("nom"))
        )
    if type_projet:
        for modele in entreprise:
            if type_projet in (modele.par_defaut_pour or []):
                return modele
        for modele in plateforme:
            if type_projet in (modele.par_defaut_pour or []):
                return modele
        for modele in plateforme:
            if type_projet in (modele.types_projet or []):
                return modele
        for modele in entreprise:
            if type_projet in (modele.types_projet or []):
                return modele
    if plateforme:
        return plateforme[0]
    return entreprise[0] if entreprise else None


def _requete_modeles_plateforme():
    return (
        ModeleDecoupagePlateforme.objects.filter(est_actif=True)
        .annotate(_nombre_lignes=Count("lignes", filter=Q(lignes__supprime_le__isnull=True)))
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


def _requete_modeles_entreprise():
    return (
        ModeleDecoupageEntreprise.objects.select_related("origine")
        .annotate(_nombre_lignes=Count("lignes", filter=Q(lignes__supprime_le__isnull=True)))
        .prefetch_related(
            Prefetch(
                "niveaux",
                queryset=NiveauModeleEntreprise.objects.filter(supprime_le__isnull=True)
                .select_related("liste_plateforme", "liste_entreprise")
                .order_by("ordre"),
                to_attr="_niveaux_actifs",
            )
        )
        .order_by("nom")
    )


def modeles_disponibles(type_projet: str | None = None) -> list[dict]:
    """Tous les modèles (plateforme et entreprise), ceux du type demandé en tête (§3.9),
    le modèle par défaut d'abord, puis les modèles de la plateforme avant ceux de l'entreprise."""
    plateforme = list(_requete_modeles_plateforme())
    entreprise = [] if _hors_entreprise() else list(_requete_modeles_entreprise())
    noms_plateforme = {m.cle_comparaison or cle_comparaison(m.nom) for m in plateforme}
    defaut = modele_par_defaut(type_projet, plateforme=plateforme, entreprise=entreprise)
    tous = [
        _modele_en_dict(m, noms_plateforme, type_projet, defaut)
        for m in [*plateforme, *entreprise]
    ]
    tous.sort(
        key=lambda d: (
            not d["par_defaut"],
            not d["pour_ce_type"],
            d["origine"] != PLATEFORME,
            d["nom_affiche"],
        )
    )
    return tous


def modele_en_dict(modele, type_projet=None) -> dict:
    noms_plateforme = {
        m.cle_comparaison or cle_comparaison(m.nom)
        for m in ModeleDecoupagePlateforme.objects.filter(est_actif=True)
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


def _empreinte_gabarit(niveaux: list[dict], lignes: list[list[str]]) -> tuple:
    """Empreinte structurelle normalisée d'un gabarit `(niveaux, lignes)` pour le versioning
    sélectif."""
    niveaux_norm = tuple(
        (
            nom_propre(n.get("libelle") or ""),
            str(n["liste"]["id"]) if n.get("liste") and n["liste"].get("id") else None,
            bool(n.get("alerter")),
        )
        for n in niveaux
    )
    largeur = len(niveaux_norm)
    lignes_norm = tuple(
        tuple(
            nom_propre(str(c or ""))
            for c in (list(ligne)[:largeur] + [""] * max(0, largeur - len(ligne)))
        )
        for ligne in lignes
    )
    return (niveaux_norm, lignes_norm)


def _ecrire_gabarit(
    modele,
    niveaux: list[dict],
    lignes: list[list[str]],
    *,
    auteur=None,
    verdict: dict | None = None,
) -> None:
    """Remplace les niveaux et les lignes types d'un modèle, plateforme ou entreprise.

    C-1 à C-4 bloquent l'enregistrement d'un modèle comme celui d'un projet (§6).
    """
    from apps.projets.services.tableau_demarrage import verifier_tableau

    plateforme = isinstance(modele, ModeleDecoupagePlateforme)
    if plateforme:
        _exiger_listes_plateforme(niveaux)
    if verdict is None:
        verdict = verifier_tableau(niveaux, lignes)
    if verdict["bloquants"]:
        raise ErreurMetier(
            "Le modèle comporte des erreurs à corriger avant de l'enregistrer.",
            details={"bloquants": verdict["bloquants"]},
        )
    # Les anciens niveaux et lignes sont retirés par suppression logique (Socle §3.1), avant
    # les nouveaux : l'unicité de l'ordre ne porte que sur les lignes non supprimées.
    modele.niveaux.filter(supprime_le__isnull=True).supprimer_logiquement(utilisateur=auteur)
    modele.lignes.filter(supprime_le__isnull=True).supprimer_logiquement(utilisateur=auteur)
    for ordre, niveau in enumerate(niveaux, start=1):
        liste = resoudre_liste(niveau.get("liste"))
        if plateforme:
            NiveauModelePlateforme.objects.create(
                modele=modele,
                ordre=ordre,
                libelle=nom_propre(niveau["libelle"]),
                liste=liste,
                alerter=bool(niveau.get("alerter")),
                cree_par=auteur,
            )
        else:
            NiveauModeleEntreprise.objects.create(
                modele=modele,
                ordre=ordre,
                libelle=nom_propre(niveau["libelle"]),
                liste_plateforme=liste if isinstance(liste, ListeValeursPlateforme) else None,
                liste_entreprise=liste if isinstance(liste, ListeValeursEntreprise) else None,
                alerter=bool(niveau.get("alerter")),
                cree_par=auteur,
            )
    classe_ligne = LigneModelePlateforme if plateforme else LigneModeleEntreprise
    lignes_a_creer = [
        classe_ligne(modele=modele, ordre=ordre, valeurs=cellules, cree_par=auteur)
        for ordre, cellules in enumerate(verdict["lignes_retenues"])
    ]
    if lignes_a_creer:
        classe_ligne.objects.bulk_create(lignes_a_creer, batch_size=1000)
    # Invalide les caches de préchargement éventuels sur l'instance
    for attr in ("_niveaux_actifs", "_lignes_actives", "_nombre_lignes"):
        if hasattr(modele, attr):
            delattr(modele, attr)


def _un_seul_defaut_par_type(classe, modele) -> None:
    """Un seul modèle par défaut pour un type donné, parmi les modèles de la même origine."""
    if not modele.par_defaut_pour:
        return
    for autre in classe.objects.exclude(pk=modele.pk):
        restants = [t for t in autre.par_defaut_pour or [] if t not in modele.par_defaut_pour]
        if restants != list(autre.par_defaut_pour or []):
            autre.par_defaut_pour = restants
            autre.save(update_fields=["par_defaut_pour", "modifie_le"])


def _verifier_defauts_dans_types(types_projet: list[str], par_defaut_pour: list[str]) -> None:
    """`par_defaut_pour` doit être un sous-ensemble de `types_projet`."""
    ensemble_types = set(types_projet)
    hors_types = [c for c in par_defaut_pour if c not in ensemble_types]
    if hors_types:
        raise ValidationError(
            {
                "par_defaut_pour": (
                    "Un modèle ne peut être par défaut que pour des catégories d'ouvrage auxquelles "
                    f"il est associé ({', '.join(hors_types)})."
                )
            }
        )


def _exiger_types_connus(codes: list[str]) -> None:
    """Un modèle plateforme ne cite que des catégories d'ouvrage du référentiel plateforme."""
    if not codes:
        return
    from apps.catalogue.models import CategorieReferentiel, ReferentielPlateforme

    connus = set(
        ReferentielPlateforme.objects.filter(
            categorie=CategorieReferentiel.TYPE_PROJET
        ).values_list("code", flat=True)
    )
    inconnus = sorted({c for c in codes if c not in connus})
    if inconnus:
        raise ValidationError(
            {
                "types_projet": (
                    f"Catégories d'ouvrage inconnues de la plateforme : {', '.join(inconnus)}."
                )
            }
        )


def _exiger_types_connus_entreprise(codes: list[str]) -> None:
    """Un modèle d'entreprise ne cite que des catégories d'ouvrage connues (plateforme ou entreprise)."""
    if not codes:
        return
    from apps.catalogue.models import CategorieReferentiel, ReferentielPlateforme
    from apps.projets.models import ReferentielEntreprise

    connus = set(
        ReferentielPlateforme.objects.filter(
            categorie=CategorieReferentiel.TYPE_PROJET
        ).values_list("code", flat=True)
    )
    if not _hors_entreprise():
        connus |= set(
            ReferentielEntreprise.objects.filter(
                categorie=CategorieReferentiel.TYPE_PROJET
            ).values_list("code", flat=True)
        )
    inconnus = sorted({c for c in codes if c not in connus})
    if inconnus:
        raise ValidationError(
            {"types_projet": f"Catégories d'ouvrage inconnues : {', '.join(inconnus)}."}
        )


@transaction.atomic
def enregistrer_modele(
    *,
    modele: ModeleDecoupageEntreprise | None = None,
    nom: str | None = None,
    description: str | None = None,
    types_projet: list[str] | None = None,
    par_defaut_pour: list[str] | None = None,
    niveaux: list[dict] | None = None,
    lignes: list | None = None,
    auteur=None,
) -> ModeleDecoupageEntreprise:
    """« Enregistrer comme nouveau modèle » ou « Mettre à jour ce modèle » (§3.10).

    Supporte aussi la mise à jour partielle (`PATCH`) lorsqu'un `modele` existant est fourni.
    """
    est_creation = modele is None
    avant = (
        None
        if est_creation
        else {
            "nom": modele.nom,
            "description": modele.description,
            "types_projet": list(modele.types_projet or []),
            "par_defaut_pour": list(modele.par_defaut_pour or []),
        }
    )
    nom_effectif = nom_propre(nom if nom is not None else (modele.nom if modele else ""))
    if not nom_effectif:
        raise ValidationError({"nom": "Le nom du modèle est obligatoire."})
    cle = cle_comparaison(nom_effectif)
    if modele is None or modele.origine_id is None:
        qs_homonyme = ModeleDecoupageEntreprise.objects.filter(
            cle_comparaison=cle, origine__isnull=True
        )
    else:
        qs_homonyme = ModeleDecoupageEntreprise.objects.filter(
            cle_comparaison=cle, origine__isnull=False
        )
    if modele is not None:
        qs_homonyme = qs_homonyme.exclude(pk=modele.pk)
    homonyme = qs_homonyme.first()
    if homonyme is not None:
        raise ErreurMetier(
            f"Un modèle de l'entreprise porte déjà le nom « {homonyme.nom} ».",
            details={"nom": nom_effectif},
        )

    types_effectifs = (
        list(dict.fromkeys(types_projet))
        if types_projet is not None
        else (list(modele.types_projet or []) if modele is not None else [])
    )
    defauts_effectifs = (
        list(dict.fromkeys(par_defaut_pour))
        if par_defaut_pour is not None
        else (list(modele.par_defaut_pour or []) if modele is not None else [])
    )
    _verifier_defauts_dans_types(types_effectifs, defauts_effectifs)
    _exiger_types_connus_entreprise([*types_effectifs, *defauts_effectifs])

    description_effective = (
        description
        if description is not None
        else (modele.description if modele is not None else "")
    )
    if modele is None:
        modele = ModeleDecoupageEntreprise(nom=nom_effectif, cree_par=auteur)
    modele.nom = nom_effectif
    modele.description = description_effective
    modele.types_projet = types_effectifs
    modele.par_defaut_pour = defauts_effectifs
    modele.save()
    _un_seul_defaut_par_type(ModeleDecoupageEntreprise, modele)

    if est_creation or niveaux is not None or lignes is not None:
        from apps.projets.services.tableau_demarrage import normaliser_lignes

        actuel = (
            gabarit_du_modele(modele)
            if not est_creation and (niveaux is None or lignes is None)
            else {"niveaux": [], "lignes": []}
        )
        niveaux_effectifs = niveaux if niveaux is not None else actuel["niveaux"]
        lignes_brutes = lignes if lignes is not None else actuel["lignes"]
        _ecrire_gabarit(
            modele,
            niveaux_effectifs,
            [ligne["cellules"] for ligne in normaliser_lignes(lignes_brutes)],
            auteur=auteur,
        )

    _journaliser_entreprise(
        action=ActionAudit.CREATION if est_creation else ActionAudit.MODIFICATION,
        type_entite="ModeleDecoupageEntreprise",
        entite_id=modele.pk,
        auteur=auteur,
        valeur_avant=avant,
        valeur_apres={
            "nom": modele.nom,
            "description": modele.description,
            "types_projet": modele.types_projet,
            "par_defaut_pour": modele.par_defaut_pour,
        },
    )
    return modele


@transaction.atomic
def retirer_modele_entreprise(
    modele: ModeleDecoupageEntreprise,
    *,
    utilisateur=None,
) -> None:
    """Supprime logiquement un modèle de l'entreprise et ses niveaux et lignes actifs."""
    avant = {
        "nom": modele.nom,
        "origine_id": str(modele.origine_id) if modele.origine_id else None,
    }
    modele.niveaux.filter(supprime_le__isnull=True).supprimer_logiquement(utilisateur=utilisateur)
    modele.lignes.filter(supprime_le__isnull=True).supprimer_logiquement(utilisateur=utilisateur)
    modele.delete(utilisateur=utilisateur)
    _journaliser_entreprise(
        action=ActionAudit.SUPPRESSION,
        type_entite="ModeleDecoupageEntreprise",
        entite_id=modele.pk,
        auteur=utilisateur,
        valeur_avant=avant,
    )


@transaction.atomic
def enregistrer_modele_plateforme(
    *,
    modele: ModeleDecoupagePlateforme | None = None,
    nom: str | None = None,
    description: str | None = None,
    types_projet: list[str] | None = None,
    par_defaut_pour: list[str] | None = None,
    niveaux: list[dict] | None = None,
    lignes: list | None = None,
    est_actif: bool | None = None,
    auteur=None,
) -> ModeleDecoupagePlateforme:
    """Créer ou mettre à jour un modèle de la plateforme (back-office).

    **Versioning sélectif** (§3.6, amendement 23/11/2026) : `modele.version` n'augmente que si le
    gabarit (`niveaux` ou `lignes`) a réellement changé, jamais sur une modification de seules
    métadonnées (`nom`, `description`, `types_projet`, `par_defaut_pour`, `est_actif`).
    Aucun projet déjà créé n'est touché (§3.11).
    """
    from apps.projets.services.tableau_demarrage import normaliser_lignes, verifier_tableau

    est_creation = modele is None
    nom_effectif = nom_propre(nom if nom is not None else (modele.nom if modele else ""))
    if not nom_effectif:
        raise ValidationError({"nom": "Le nom du modèle est obligatoire."})
    cle = cle_comparaison(nom_effectif)
    homonyme = next(
        (
            m
            for m in ModeleDecoupagePlateforme.objects.all()
            if (m.cle_comparaison or cle_comparaison(m.nom)) == cle
            and (modele is None or m.pk != modele.pk)
        ),
        None,
    )
    if homonyme is not None:
        raise ErreurMetier(f"Un modèle de la plateforme porte déjà le nom « {homonyme.nom} ».")

    types_effectifs = (
        list(dict.fromkeys(types_projet))
        if types_projet is not None
        else (list(modele.types_projet or []) if modele is not None else [])
    )
    defauts_effectifs = (
        list(dict.fromkeys(par_defaut_pour))
        if par_defaut_pour is not None
        else (list(modele.par_defaut_pour or []) if modele is not None else [])
    )
    _verifier_defauts_dans_types(types_effectifs, defauts_effectifs)
    _exiger_types_connus([*types_effectifs, *defauts_effectifs])

    description_effective = (
        description
        if description is not None
        else (modele.description if modele is not None else "")
    )
    est_actif_effectif = (
        bool(est_actif)
        if est_actif is not None
        else (modele.est_actif if modele is not None else True)
    )

    gabarit_fourni = est_creation or niveaux is not None or lignes is not None
    verdict = None
    niveaux_effectifs: list[dict] = []
    lignes_normalisees: list[list[str]] = []
    gabarit_modifie = False

    if gabarit_fourni:
        actuel = gabarit_du_modele(modele) if not est_creation else {"niveaux": [], "lignes": []}
        niveaux_effectifs = niveaux if niveaux is not None else actuel["niveaux"]
        lignes_brutes = lignes if lignes is not None else actuel["lignes"]
        lignes_normalisees = [ligne["cellules"] for ligne in normaliser_lignes(lignes_brutes)]
        _exiger_listes_plateforme(niveaux_effectifs)
        verdict = verifier_tableau(niveaux_effectifs, lignes_normalisees)
        if verdict["bloquants"]:
            raise ErreurMetier(
                "Le modèle comporte des erreurs à corriger avant de l'enregistrer.",
                details={"bloquants": verdict["bloquants"]},
            )
        if not est_creation:
            empreinte_avant = _empreinte_gabarit(actuel["niveaux"], actuel["lignes"])
            empreinte_apres = _empreinte_gabarit(niveaux_effectifs, verdict["lignes_retenues"])
            gabarit_modifie = empreinte_apres != empreinte_avant

    if est_creation:
        modele = ModeleDecoupagePlateforme(nom=nom_effectif, cree_par=auteur)
    elif gabarit_modifie:
        modele.version += 1

    modele.nom = nom_effectif
    modele.description = description_effective
    modele.types_projet = types_effectifs
    modele.par_defaut_pour = defauts_effectifs
    modele.est_actif = est_actif_effectif
    modele.save()
    _un_seul_defaut_par_type(ModeleDecoupagePlateforme, modele)

    if est_creation or gabarit_modifie:
        _ecrire_gabarit(
            modele,
            niveaux_effectifs,
            lignes_normalisees,
            auteur=auteur,
            verdict=verdict,
        )
    return modele


@transaction.atomic
def personnaliser_modele(
    modele_plateforme: ModeleDecoupagePlateforme,
    *,
    auteur=None,
) -> ModeleDecoupageEntreprise:
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
        cree_par=auteur,
    )
    _ecrire_gabarit(copie, gabarit["niveaux"], gabarit["lignes"], auteur=auteur)
    _journaliser_entreprise(
        action=ActionAudit.CREATION,
        type_entite="ModeleDecoupageEntreprise",
        entite_id=copie.pk,
        auteur=auteur,
        valeur_apres={
            "nom": copie.nom,
            "origine_plateforme_id": str(modele_plateforme.pk),
            "version_origine": modele_plateforme.version,
        },
    )
    return copie
