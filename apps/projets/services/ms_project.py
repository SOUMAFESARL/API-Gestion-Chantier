"""Analyse et import de plannings Microsoft Project (.xml) — Tâches 2.18 / 2.19.

Le format XML Microsoft Project (MSPDI) expose un arbre de tâches hiérarchisées par
`OutlineLevel`, des dates ISO 8601, des durées ISO (`PT...`), des jalons (`Milestone=1`)
et des dépendances `<PredecessorLink>`.

Règles métier appliquées :
- **Verrou strict de démarrage** (`etat_import_ms_project`) : dès qu'au moins une trace
  d'exécution existe sur le découpage du projet (avancement, statut différent de PLANIFIE,
  clôture, date réelle, mise à jour inline, blocage sur tâche, rapport journalier, avenant
  sur tâche, affectation d'équipe ou donnée de stock liée à une tâche), l'import est bloqué.
- **Remplacement explicite** : si un découpage existe sans exécution démarrée, l'import exige
  `confirmer_remplacement=True` et supprime **logiquement** (`supprimer_logiquement`) les
  anciennes dépendances, cases et niveaux dans cet ordre.
- **Sécurité XML (anti-XXE)** : toute déclaration `<!DOCTYPE` ou `<!ENTITY` est rejetée
  avant l'analyse `xml.etree.ElementTree`, sans dépendance tierce.
- **Dépendances** : seuls les liens Fin→Début (`Type=1` ou absent) entre deux feuilles sans
  cycle sont retenus ; tout lien écarté est expliqué dans `avertissements`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.enums import ActionAudit, StatutActivite
from apps.core.exceptions import ErreurMetier
from apps.projets.models import (
    AffectationEquipeElement,
    AffectationProjet,
    AlerteRetard,
    Avenant,
    Dependance,
    Element,
    MiseAJourInline,
    ModeMesure,
    NiveauProjet,
    PointAvancement,
    Projet,
)
from apps.projets.services.dates_derivees import recalculer_dates_derivees
from apps.projets.services.tableau_demarrage import proposer_tableau

__all__ = [
    "TAILLE_MAX",
    "TAILLE_MAX_MO",
    "ImportMsProjectBloque",
    "RemplacementDecoupageRequis",
    "analyser_ms_project",
    "etat_import_ms_project",
    "importer_ms_project",
]

TAILLE_MAX_MO = 20
TAILLE_MAX = TAILLE_MAX_MO * 1024 * 1024
LONGUEUR_MAX_LIBELLE = 200
LONGUEUR_MAX_CODE = 30
LONGUEUR_MAX_NIVEAU = 60

TYPES_LIENS_MS_PROJECT = {
    "0": "FF",
    "1": "FS",
    "2": "SF",
    "3": "SS",
}

_RE_XXE_BYTES = re.compile(rb"<!\s*(?:doctype|entity)\b", re.IGNORECASE)
_RE_XXE_TEXTE = re.compile(r"<!\s*(?:doctype|entity)\b", re.IGNORECASE)
_RE_DATE_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_RE_DUREE_ISO = re.compile(
    r"^P(?:(?P<jours>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<heures>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<secondes>\d+(?:\.\d+)?)S)?)?$",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Exceptions métier
# --------------------------------------------------------------------------
class ImportMsProjectBloque(ErreurMetier):
    """L'exécution du projet a déjà démarré : l'import MS Project est interdit."""

    code_metier = "import_ms_project_bloque"
    default_detail = _(
        "Impossible d'importer un planning MS Project : l'exécution de ce projet a déjà démarré."
    )


class RemplacementDecoupageRequis(ErreurMetier):
    """Un découpage non démarré existe déjà : confirmation explicite requise."""

    code_metier = "remplacement_decoupage_requis"
    default_detail = _(
        "Ce projet possède déjà un découpage. Confirmez son remplacement pour importer ce "
        "planning MS Project."
    )


# --------------------------------------------------------------------------
# État d'éligibilité à l'import
# --------------------------------------------------------------------------
def _stock_lie_aux_elements(projet: Projet, element_ids) -> bool:
    """Vérifie la présence d'opérations ou seuils de stock rattachés aux éléments du projet."""
    try:
        from apps.stock.models import (
            BonCommande,
            DemandeApprovisionnement,
            MouvementStock,
            SessionInventaire,
            SeuilStockLot,
        )
    except ImportError:
        return False

    return bool(
        BonCommande.objects.filter(projet=projet, lot_id__in=element_ids).exists()
        or DemandeApprovisionnement.objects.filter(projet=projet, lot_id__in=element_ids).exists()
        or MouvementStock.objects.filter(
            Q(lot_id__in=element_ids) | Q(lot_destination_id__in=element_ids)
        ).exists()
        or SessionInventaire.objects.filter(projet=projet, lot_id__in=element_ids).exists()
        or SeuilStockLot.objects.filter(projet=projet, lot_id__in=element_ids).exists()
    )


def etat_import_ms_project(projet: Projet) -> dict:
    """Détermine si un import MS Project est autorisé, bloqué ou soumis à remplacement.

    Retourne :
        {
            "autorise": bool,
            "decoupage_existant": bool,
            "remplacement_requis": bool,
            "motif_blocage": str | None,
        }
    """
    from apps.chantier.models import Blocage, RapportJournalier

    elements_qs = Element.objects.filter(projet=projet)
    decoupage_existant = elements_qs.exists()
    motifs: list[str] = []

    if RapportJournalier.objects.filter(projet=projet).exists():
        motifs.append(str(_("rapports journaliers enregistrés")))

    if decoupage_existant:
        element_ids = elements_qs.values("pk")

        a_element_demarre = (
            Element.objects.filter(projet=projet, est_actif=True)
            .filter(
                Q(quantite_realisee__gt=0)
                | Q(pourcentage_declare__gt=0)
                | Q(avancement__gt=0)
                | Q(cloture=True)
                | Q(date_debut_reelle__isnull=False)
                | Q(date_fin_reelle__isnull=False)
                | ~Q(statut=StatutActivite.PLANIFIE)
            )
            .exists()
        )
        if a_element_demarre:
            motifs.append(str(_("tâches déjà démarrées ou clôturées")))

        if MiseAJourInline.objects.filter(element_id__in=element_ids).exists():
            motifs.append(str(_("mises à jour d'avancement enregistrées")))

        if Blocage.objects.filter(projet=projet, element_id__in=element_ids).exists():
            motifs.append(str(_("blocages rattachés aux tâches")))

        if Avenant.objects.filter(projet=projet, elements__in=element_ids).exists():
            motifs.append(str(_("avenants rattachés aux tâches")))

        if AffectationEquipeElement.objects.filter(element_id__in=element_ids).exists():
            motifs.append(str(_("équipes affectées aux tâches")))

        if _stock_lie_aux_elements(projet, element_ids):
            motifs.append(str(_("données de stock liées aux tâches")))

    if motifs:
        motif_blocage = str(
            _("Import MS Project bloqué : l'exécution du projet a déjà démarré (%(motifs)s).")
        ) % {"motifs": ", ".join(motifs)}
        return {
            "autorise": False,
            "decoupage_existant": decoupage_existant,
            "remplacement_requis": False,
            "motif_blocage": motif_blocage,
        }

    if decoupage_existant:
        return {
            "autorise": True,
            "decoupage_existant": True,
            "remplacement_requis": True,
            "motif_blocage": None,
        }

    return {
        "autorise": True,
        "decoupage_existant": False,
        "remplacement_requis": False,
        "motif_blocage": None,
    }


# --------------------------------------------------------------------------
# Utilitaires XML sécurisés (agnostiques au namespace)
# --------------------------------------------------------------------------
def _nom_local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _enfant(element: ET.Element, nom: str) -> ET.Element | None:
    for child in element:
        if _nom_local(child.tag) == nom:
            return child
    return None


def _enfants(element: ET.Element, nom: str) -> list[ET.Element]:
    return [child for child in element if _nom_local(child.tag) == nom]


def _texte_enfant(element: ET.Element, nom: str) -> str:
    enfant = _enfant(element, nom)
    if enfant is None or enfant.text is None:
        return ""
    return enfant.text.strip()


def _decoder_xml_pour_controle(contenu: bytes) -> str:
    if contenu.startswith((b"\xff\xfe", b"\xfe\xff")):
        return contenu.decode("utf-16", errors="ignore")
    try:
        return contenu.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenu.decode("latin-1", errors="ignore")


def _lire_et_valider_xml(fichier) -> ET.Element:
    """Valide extension, taille, sécurité anti-XXE puis parse la racine `<Project>`."""
    if fichier is None:
        raise ValidationError({"fichier": _("Joignez un fichier MS Project au format .xml.")})

    nom = (getattr(fichier, "name", "") or "").strip().lower()
    if not nom.endswith(".xml"):
        raise ValidationError(
            {"fichier": _("Seuls les fichiers MS Project au format .xml sont acceptés.")}
        )

    taille_declaree = getattr(fichier, "size", None)
    if taille_declaree is not None and taille_declaree > TAILLE_MAX:
        raise ValidationError(
            {
                "fichier": _(
                    "Le fichier dépasse la taille maximale autorisée (%(max_mo)d Mo)."
                )
                % {"max_mo": TAILLE_MAX_MO}
            }
        )

    if hasattr(fichier, "seek"):
        fichier.seek(0)
    brut = fichier.read(TAILLE_MAX + 1)
    contenu = brut.encode("utf-8") if isinstance(brut, str) else bytes(brut or b"")

    if len(contenu) > TAILLE_MAX:
        raise ValidationError(
            {
                "fichier": _(
                    "Le fichier dépasse la taille maximale autorisée (%(max_mo)d Mo)."
                )
                % {"max_mo": TAILLE_MAX_MO}
            }
        )

    if not contenu.strip():
        raise ValidationError({"fichier": _("Le fichier XML est vide.")})

    texte_controle = _decoder_xml_pour_controle(contenu)
    if _RE_XXE_BYTES.search(contenu) or _RE_XXE_TEXTE.search(texte_controle):
        raise ValidationError(
            {
                "fichier": _(
                    "Le fichier XML contient des déclarations interdites (DOCTYPE ou ENTITY) "
                    "et a été rejeté par sécurité."
                )
            }
        )

    try:
        racine = ET.fromstring(contenu)
    except ET.ParseError:
        raise ValidationError(
            {"fichier": _("Le fichier XML est mal formé et ne peut pas être lu.")}
        ) from None

    if _nom_local(racine.tag) != "Project":
        raise ValidationError(
            {
                "fichier": _(
                    "Ce fichier XML n'est pas un export Microsoft Project valide "
                    "(balise racine <Project> attendue)."
                )
            }
        )
    return racine


def _parser_date_iso(valeur: str) -> date | None:
    if not valeur:
        return None
    correspondance = _RE_DATE_ISO.match(valeur.strip())
    if not correspondance:
        return None
    try:
        return date.fromisoformat(correspondance.group(1))
    except ValueError:
        return None


def _parser_duree_heures(valeur: str, heures_par_jour: float = 8.0) -> float | None:
    if not valeur:
        return None
    correspondance = _RE_DUREE_ISO.match(valeur.strip())
    if not correspondance:
        return None
    jours = float(correspondance.group("jours") or 0.0)
    heures = float(correspondance.group("heures") or 0.0)
    minutes = float(correspondance.group("minutes") or 0.0)
    secondes = float(correspondance.group("secondes") or 0.0)
    total = jours * heures_par_jour + heures + (minutes / 60.0) + (secondes / 3600.0)
    return round(total, 2)


def _parser_pourcentage(valeur: str) -> float | None:
    if not valeur:
        return None
    try:
        nombre = float(valeur.strip().replace(",", "."))
    except ValueError:
        return None
    return round(max(0.0, min(100.0, nombre)), 1)


def _parser_entier(valeur: str) -> int | None:
    if not valeur:
        return None
    try:
        return int(valeur.strip())
    except ValueError:
        return None


def _chemin_existe(depart: str, arrivee: str, successeurs: dict[str, list[str]]) -> bool:
    """Recherche DFS itérative d'un chemin de `depart` vers `arrivee` (anti-cycle)."""
    pile = [depart]
    vus = {depart}
    while pile:
        courant = pile.pop()
        if courant == arrivee:
            return True
        for suivant in successeurs.get(courant, ()):
            if suivant not in vus:
                vus.add(suivant)
                pile.append(suivant)
    return False


# --------------------------------------------------------------------------
# Structure interne d'analyse
# --------------------------------------------------------------------------
@dataclass
class _NoeudTache:
    uid: str
    outline_number: str
    numero: str
    libelle: str
    outline_level: int
    niveau_ordre: int
    debut: date | None
    fin: date | None
    duree_heures: float | None
    est_jalon: bool
    pourcentage_xml: float | None
    liens_bruts: list[tuple[str, str]] = field(default_factory=list)
    enfants: list[_NoeudTache] = field(default_factory=list)

    @property
    def est_feuille(self) -> bool:
        return not self.enfants


@dataclass
class _ResultatAnalyse:
    payload: dict
    racines: list[_NoeudTache]
    dependances_retenues: list[dict]
    min_debut: date | None
    max_fin: date | None


def _generer_niveaux(projet: Projet, profondeur_max: int) -> list[dict]:
    """Génère `1..profondeur_max` en reprenant les libellés proposés pour le type de projet."""
    proposition = proposer_tableau(projet)
    libelles_proposes = [
        " ".join(str(niv.get("libelle") or "").split())
        for niv in proposition.get("niveaux", [])
        if str(niv.get("libelle") or "").strip()
    ]
    niveaux: list[dict] = []
    for ordre in range(1, profondeur_max + 1):
        libelle = (
            libelles_proposes[ordre - 1]
            if ordre - 1 < len(libelles_proposes)
            else f"Niveau {ordre}"
        )
        niveaux.append({"ordre": ordre, "libelle": libelle[:LONGUEUR_MAX_NIVEAU]})
    return niveaux


def _analyser_interne(
    projet: Projet, fichier, *, etat: dict | None = None
) -> _ResultatAnalyse:
    racine = _lire_et_valider_xml(fichier)
    etat_import = etat if etat is not None else etat_import_ms_project(projet)

    minutes_par_jour = _parser_entier(_texte_enfant(racine, "MinutesPerDay"))
    heures_par_jour = (
        minutes_par_jour / 60.0 if minutes_par_jour and minutes_par_jour > 0 else 8.0
    )

    titre_xml = (
        " ".join(_texte_enfant(racine, "Title").split())
        or " ".join(_texte_enfant(racine, "Name").split())
        or None
    )
    debut_projet_xml = _parser_date_iso(_texte_enfant(racine, "StartDate"))
    fin_projet_xml = _parser_date_iso(_texte_enfant(racine, "FinishDate"))

    bloc_taches = _enfant(racine, "Tasks")
    elements_taches = _enfants(bloc_taches, "Task") if bloc_taches is not None else []

    avertissements: list[dict] = []
    racines: list[_NoeudTache] = []
    tous_noeuds: list[_NoeudTache] = []
    noeuds_par_uid: dict[str, _NoeudTache] = {}
    pile: list[_NoeudTache] = []

    for index, balise_tache in enumerate(elements_taches, start=1):
        if _texte_enfant(balise_tache, "IsNull") == "1":
            continue

        task_id = _parser_entier(_texte_enfant(balise_tache, "ID"))
        outline_level = _parser_entier(_texte_enfant(balise_tache, "OutlineLevel"))
        libelle_brut = " ".join(_texte_enfant(balise_tache, "Name").split())

        if task_id == 0 or outline_level == 0:
            if not titre_xml and libelle_brut:
                titre_xml = libelle_brut
            if debut_projet_xml is None:
                debut_projet_xml = _parser_date_iso(_texte_enfant(balise_tache, "Start"))
            if fin_projet_xml is None:
                fin_projet_xml = _parser_date_iso(_texte_enfant(balise_tache, "Finish"))
            continue

        if not libelle_brut:
            continue

        uid = _texte_enfant(balise_tache, "UID") or (
            str(task_id) if task_id is not None else f"tache-{index}"
        )
        if uid in noeuds_par_uid:
            uid_origine = uid
            uid = f"{uid_origine}-{index}"
            avertissements.append(
                {
                    "code": "UID_DUPLIQUE",
                    "message": str(
                        _(
                            "UID « %(uid)s » en double sur « %(libelle)s » : "
                            "réattribué en « %(nouveau)s »."
                        )
                    )
                    % {"uid": uid_origine, "libelle": libelle_brut, "nouveau": uid},
                }
            )

        niveau_xml = outline_level if outline_level is not None and outline_level > 0 else 1
        outline_number = _texte_enfant(balise_tache, "OutlineNumber")
        debut = _parser_date_iso(_texte_enfant(balise_tache, "Start"))
        fin = _parser_date_iso(_texte_enfant(balise_tache, "Finish"))
        est_jalon = _texte_enfant(balise_tache, "Milestone") == "1"

        if est_jalon:
            if debut is not None and fin is None:
                fin = debut
            elif fin is not None and debut is None:
                debut = fin

        if debut is not None and fin is not None and fin < debut:
            avertissements.append(
                {
                    "code": "DATES_INCOHERENTES",
                    "message": str(
                        _(
                            "Dates incohérentes sur « %(libelle)s » (fin antérieure au début) : "
                            "date de fin recalée au %(debut)s."
                        )
                    )
                    % {"libelle": libelle_brut, "debut": debut.isoformat()},
                }
            )
            fin = debut

        duree_heures = _parser_duree_heures(
            _texte_enfant(balise_tache, "Duration"), heures_par_jour=heures_par_jour
        )
        pourcentage_xml = _parser_pourcentage(_texte_enfant(balise_tache, "PercentComplete"))

        liens_bruts: list[tuple[str, str]] = []
        for lien_xml in _enfants(balise_tache, "PredecessorLink"):
            pred_uid = _texte_enfant(lien_xml, "PredecessorUID")
            type_brut = _texte_enfant(lien_xml, "Type")
            liens_bruts.append((pred_uid, type_brut))

        while pile and pile[-1].outline_level >= niveau_xml:
            pile.pop()
        niveau_ordre = len(pile) + 1

        noeud = _NoeudTache(
            uid=uid,
            outline_number=outline_number,
            numero=outline_number,
            libelle=libelle_brut,
            outline_level=niveau_xml,
            niveau_ordre=niveau_ordre,
            debut=debut,
            fin=fin,
            duree_heures=duree_heures,
            est_jalon=est_jalon,
            pourcentage_xml=pourcentage_xml,
            liens_bruts=liens_bruts,
        )
        if pile:
            pile[-1].enfants.append(noeud)
        else:
            racines.append(noeud)
        pile.append(noeud)
        tous_noeuds.append(noeud)
        noeuds_par_uid[uid] = noeud

    if not racines:
        raise ValidationError(
            {"fichier": _("Aucune tâche exploitable n'a été trouvée dans ce fichier MS Project.")}
        )

    # Normalisation de l'arbre : déduplication frères, numéros et enveloppe de dates parents.
    profondeur_max = 1

    def _normaliser_branche(noeuds: list[_NoeudTache], prefixe: str) -> None:
        nonlocal profondeur_max
        cles_vues: set[str] = set()
        for rang, noeud in enumerate(noeuds, start=1):
            if noeud.niveau_ordre > profondeur_max:
                profondeur_max = noeud.niveau_ordre

            numero_calcule = f"{prefixe}{rang}"
            if not noeud.numero:
                noeud.numero = numero_calcule

            libelle_origine = noeud.libelle
            base = libelle_origine[:LONGUEUR_MAX_LIBELLE].strip()
            if len(libelle_origine) > LONGUEUR_MAX_LIBELLE:
                avertissements.append(
                    {
                        "code": "LIBELLE_TRONQUE",
                        "message": str(
                            _("Libellé « %(extrait)s… » tronqué à %(max)d caractères.")
                        )
                        % {"extrait": base[:60], "max": LONGUEUR_MAX_LIBELLE},
                    }
                )

            cle = cle_comparaison(base)
            if cle in cles_vues:
                suffixe = 2
                while True:
                    marque = f" ({suffixe})"
                    candidat = f"{base[: LONGUEUR_MAX_LIBELLE - len(marque)].rstrip()}{marque}"
                    cle_candidat = cle_comparaison(candidat)
                    if cle_candidat not in cles_vues:
                        noeud.libelle = candidat
                        cles_vues.add(cle_candidat)
                        avertissements.append(
                            {
                                "code": "DOUBLON_FRERE",
                                "message": str(
                                    _(
                                        "Tâche « %(origine)s » renommée en « %(nouveau)s » "
                                        "(libellé en double sous le même parent)."
                                    )
                                )
                                % {"origine": libelle_origine, "nouveau": candidat},
                            }
                        )
                        break
                    suffixe += 1
            else:
                noeud.libelle = base
                cles_vues.add(cle)

            if noeud.enfants:
                _normaliser_branche(noeud.enfants, f"{numero_calcule}.")
                if noeud.debut is None:
                    debuts_enfants = [e.debut for e in noeud.enfants if e.debut is not None]
                    if debuts_enfants:
                        noeud.debut = min(debuts_enfants)
                if noeud.fin is None:
                    fins_enfants = [e.fin for e in noeud.enfants if e.fin is not None]
                    if fins_enfants:
                        noeud.fin = max(fins_enfants)

    _normaliser_branche(racines, "")

    niveaux = _generer_niveaux(projet, profondeur_max)
    libelle_par_ordre = {niv["ordre"]: niv["libelle"] for niv in niveaux}

    # Filtrage des dépendances : FS uniquement, entre deux feuilles, sans doublon ni cycle.
    dependances_retenues: list[dict] = []
    dependances_ignorees = 0
    graphe_successeurs: dict[str, list[str]] = defaultdict(list)
    paires_vues: set[tuple[str, str]] = set()

    for successeur in tous_noeuds:
        for pred_uid, type_brut in successeur.liens_bruts:
            if not pred_uid or pred_uid not in noeuds_par_uid:
                dependances_ignorees += 1
                avertissements.append(
                    {
                        "code": "DEPENDANCE_UID_INCONNU",
                        "message": str(
                            _(
                                "Lien ignoré sur « %(successeur)s » : prédécesseur UID "
                                "« %(uid)s » introuvable."
                            )
                        )
                        % {"successeur": successeur.libelle, "uid": pred_uid or "?"},
                    }
                )
                continue

            predecesseur = noeuds_par_uid[pred_uid]
            code_type = type_brut or "1"
            nom_type = TYPES_LIENS_MS_PROJECT.get(code_type, f"TYPE_{code_type}")

            if code_type != "1":
                dependances_ignorees += 1
                avertissements.append(
                    {
                        "code": "DEPENDANCE_TYPE_NON_SUPPORTE",
                        "message": str(
                            _(
                                "Lien %(type_lien)s ignoré entre « %(pred)s » et « %(succ)s » : "
                                "seuls les liens Fin→Début (FS) sont pris en charge."
                            )
                        )
                        % {
                            "type_lien": nom_type,
                            "pred": predecesseur.libelle,
                            "succ": successeur.libelle,
                        },
                    }
                )
                continue

            if not predecesseur.est_feuille or not successeur.est_feuille:
                dependances_ignorees += 1
                avertissements.append(
                    {
                        "code": "DEPENDANCE_PARENT_IGNOREE",
                        "message": str(
                            _(
                                "Lien ignoré entre « %(pred)s » et « %(succ)s » : les dépendances "
                                "ne relient que des tâches feuilles (non récapitulatives)."
                            )
                        )
                        % {"pred": predecesseur.libelle, "succ": successeur.libelle},
                    }
                )
                continue

            if predecesseur.uid == successeur.uid:
                dependances_ignorees += 1
                avertissements.append(
                    {
                        "code": "DEPENDANCE_CYCLE",
                        "message": str(
                            _("Lien ignoré : « %(tache)s » ne peut pas dépendre d'elle-même.")
                        )
                        % {"tache": successeur.libelle},
                    }
                )
                continue

            paire = (predecesseur.uid, successeur.uid)
            if paire in paires_vues:
                dependances_ignorees += 1
                avertissements.append(
                    {
                        "code": "DEPENDANCE_DOUBLON",
                        "message": str(
                            _("Lien en double ignoré entre « %(pred)s » et « %(succ)s ».")
                        )
                        % {"pred": predecesseur.libelle, "succ": successeur.libelle},
                    }
                )
                continue

            if _chemin_existe(successeur.uid, predecesseur.uid, graphe_successeurs):
                dependances_ignorees += 1
                avertissements.append(
                    {
                        "code": "DEPENDANCE_CYCLE",
                        "message": str(
                            _(
                                "Lien ignoré entre « %(pred)s » et « %(succ)s » : "
                                "ce lien créerait une boucle de dépendances."
                            )
                        )
                        % {"pred": predecesseur.libelle, "succ": successeur.libelle},
                    }
                )
                continue

            paires_vues.add(paire)
            graphe_successeurs[predecesseur.uid].append(successeur.uid)
            if predecesseur.fin is None or successeur.debut is None:
                est_respectee = None
            else:
                est_respectee = successeur.debut > predecesseur.fin

            dependances_retenues.append(
                {
                    "predecesseur_uid": predecesseur.uid,
                    "predecesseur_libelle": predecesseur.libelle,
                    "successeur_uid": successeur.uid,
                    "successeur_libelle": successeur.libelle,
                    "type": "FS",
                    "respectee": est_respectee,
                }
            )

    def _serialiser_noeud(noeud: _NoeudTache) -> dict:
        return {
            "uid": noeud.uid,
            "numero": noeud.numero,
            "libelle": noeud.libelle,
            "niveau_ordre": noeud.niveau_ordre,
            "niveau": libelle_par_ordre[noeud.niveau_ordre],
            "debut": noeud.debut.isoformat() if noeud.debut else None,
            "fin": noeud.fin.isoformat() if noeud.fin else None,
            "duree_heures": noeud.duree_heures,
            "est_jalon": noeud.est_jalon,
            "est_feuille": noeud.est_feuille,
            "pourcentage_xml": noeud.pourcentage_xml,
            "enfants": [_serialiser_noeud(enfant) for enfant in noeud.enfants],
        }

    debuts = [n.debut for n in tous_noeuds if n.debut is not None]
    fins = [n.fin for n in tous_noeuds if n.fin is not None]
    min_debut = min(debuts) if debuts else debut_projet_xml
    max_fin = max(fins) if fins else fin_projet_xml

    projet_debut_final = debut_projet_xml or min_debut
    projet_fin_final = fin_projet_xml or max_fin
    if projet_debut_final and projet_fin_final and projet_fin_final < projet_debut_final:
        projet_fin_final = projet_debut_final

    feuilles = sum(1 for n in tous_noeuds if n.est_feuille)
    jalons = sum(1 for n in tous_noeuds if n.est_jalon)

    payload = {
        "etat_import": etat_import,
        "projet_xml": {
            "titre": titre_xml,
            "date_debut": projet_debut_final.isoformat() if projet_debut_final else None,
            "date_fin": projet_fin_final.isoformat() if projet_fin_final else None,
        },
        "niveaux": niveaux,
        "taches": [_serialiser_noeud(racine_tache) for racine_tache in racines],
        "dependances": dependances_retenues,
        "statistiques": {
            "total_taches": len(tous_noeuds),
            "feuilles": feuilles,
            "jalons": jalons,
            "dependances_retenues": len(dependances_retenues),
            "dependances_ignorees": dependances_ignorees,
        },
        "avertissements": avertissements,
    }
    return _ResultatAnalyse(
        payload=payload,
        racines=racines,
        dependances_retenues=dependances_retenues,
        min_debut=min_debut,
        max_fin=max_fin,
    )


# --------------------------------------------------------------------------
# API publique du service
# --------------------------------------------------------------------------
def analyser_ms_project(projet: Projet, fichier) -> dict:
    """Analyse un fichier MS Project `.xml` sans aucune écriture en base."""
    return _analyser_interne(projet, fichier).payload


def importer_ms_project(
    projet: Projet,
    fichier,
    *,
    auteur,
    confirmer_remplacement: bool = False,
) -> dict:
    """Importe un planning MS Project `.xml` dans le découpage et les dépendances du projet."""
    from apps.audit.services import journaliser
    from apps.projets.services.avancement import recalculer_avancements_projet

    with transaction.atomic():
        projet = Projet.objects.select_for_update().get(pk=projet.pk)
        etat = etat_import_ms_project(projet)

        if not etat["autorise"]:
            raise ImportMsProjectBloque(
                etat["motif_blocage"],
                details={"etat_import": etat},
            )
        if etat["remplacement_requis"] and not confirmer_remplacement:
            raise RemplacementDecoupageRequis(details={"etat_import": etat})

        resultat_analyse = _analyser_interne(projet, fichier, etat=etat)
        payload = resultat_analyse.payload

        remplacement_effectue = bool(etat["decoupage_existant"])
        nb_dependances_remplacees = 0
        nb_elements_remplaces = 0
        nb_niveaux_remplaces = 0

        if remplacement_effectue:
            element_ids = list(Element.objects.filter(projet=projet).values_list("pk", flat=True))
            nb_dependances_remplacees = Dependance.objects.filter(
                projet=projet
            ).supprimer_logiquement(utilisateur=auteur)
            if element_ids:
                AffectationProjet.perimetres.through.objects.filter(
                    element_id__in=element_ids
                ).delete()
                PointAvancement.objects.filter(
                    projet=projet, element_id__in=element_ids
                ).supprimer_logiquement(utilisateur=auteur)
                AlerteRetard.objects.filter(
                    projet=projet, element_id__in=element_ids
                ).supprimer_logiquement(utilisateur=auteur)
            nb_elements_remplaces = Element.objects.filter(projet=projet).supprimer_logiquement(
                utilisateur=auteur
            )
            nb_niveaux_remplaces = NiveauProjet.objects.filter(
                projet=projet
            ).supprimer_logiquement(utilisateur=auteur)
        elif NiveauProjet.objects.filter(projet=projet).exists():
            NiveauProjet.objects.filter(projet=projet).supprimer_logiquement(utilisateur=auteur)

        niveaux_donnees = payload["niveaux"]
        index_alerte = len(niveaux_donnees) - 2 if len(niveaux_donnees) > 1 else 0
        niveaux_par_ordre: dict[int, NiveauProjet] = {}
        for idx, niv in enumerate(niveaux_donnees):
            niveaux_par_ordre[niv["ordre"]] = NiveauProjet.objects.create(
                projet=projet,
                ordre=niv["ordre"],
                libelle=niv["libelle"],
                alerter=(idx == index_alerte),
                cree_par=auteur,
            )

        elements_par_uid: dict[str, Element] = {}
        elements_crees = 0

        def _creer_branche(noeuds: list[_NoeudTache], parent: Element | None) -> None:
            nonlocal elements_crees
            for ordre, noeud in enumerate(noeuds, start=1):
                est_parent = not noeud.est_feuille
                mode_mesure = (
                    ModeMesure.JALON
                    if (noeud.est_jalon and noeud.est_feuille)
                    else ModeMesure.POURCENTAGE
                )
                element = Element.objects.create(
                    projet=projet,
                    parent=parent,
                    niveau=niveaux_par_ordre[noeud.niveau_ordre],
                    libelle=noeud.libelle,
                    code=(noeud.outline_number or "")[:LONGUEUR_MAX_CODE],
                    ordre=ordre,
                    mode_mesure=mode_mesure,
                    date_debut_prevue=noeud.debut,
                    date_fin_prevue=noeud.fin,
                    dates_calculees=est_parent,
                    cree_par=auteur,
                )
                elements_par_uid[noeud.uid] = element
                elements_crees += 1
                if noeud.enfants:
                    _creer_branche(noeud.enfants, element)

        _creer_branche(resultat_analyse.racines, None)

        dependances_creees = 0
        for dep in resultat_analyse.dependances_retenues:
            Dependance.objects.create(
                projet=projet,
                predecesseur=elements_par_uid[dep["predecesseur_uid"]],
                successeur=elements_par_uid[dep["successeur_uid"]],
                cree_par=auteur,
            )
            dependances_creees += 1

        if (
            projet.date_debut_prevue is None
            and projet.date_fin_prevue is None
            and resultat_analyse.min_debut is not None
            and resultat_analyse.max_fin is not None
            and resultat_analyse.max_fin >= resultat_analyse.min_debut
        ):
            projet.date_debut_prevue = resultat_analyse.min_debut
            projet.date_fin_prevue = resultat_analyse.max_fin
            projet.save(
                update_fields=[
                    "date_debut_prevue",
                    "date_fin_prevue",
                    "date_debut_baseline",
                    "date_fin_baseline",
                    "modifie_le",
                ]
            )

        recalculer_dates_derivees(projet)
        recalculer_avancements_projet(projet)

        journaliser(
            action=ActionAudit.MODIFICATION if remplacement_effectue else ActionAudit.CREATION,
            type_entite="DecoupageProjet",
            entite_id=projet.pk,
            utilisateur_id=getattr(auteur, "pk", None),
            valeur_avant=(
                {
                    "evenement": "IMPORT_MS_PROJECT",
                    "elements_remplaces": nb_elements_remplaces,
                    "niveaux_remplaces": nb_niveaux_remplaces,
                    "dependances_remplacees": nb_dependances_remplacees,
                }
                if remplacement_effectue
                else None
            ),
            valeur_apres={
                "evenement": "IMPORT_MS_PROJECT",
                "fichier": getattr(fichier, "name", "") or "",
                "elements_crees": elements_crees,
                "niveaux_crees": len(niveaux_par_ordre),
                "dependances_creees": dependances_creees,
                "remplacement_effectue": remplacement_effectue,
            },
        )

    return {
        "elements_crees": elements_crees,
        "niveaux_crees": len(niveaux_par_ordre),
        "dependances_creees": dependances_creees,
        "remplacement_effectue": remplacement_effectue,
        "avertissements": payload["avertissements"],
    }
