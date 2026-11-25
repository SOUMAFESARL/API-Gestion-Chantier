"""Analyse et import de plannings Microsoft Project (.xml) — Tâches 2.18 / 2.19 (amendé 25/11/2026).

Le format XML Microsoft Project (MSPDI) expose un arbre de tâches hiérarchisées par
`OutlineLevel`, des dates ISO 8601, des baselines (`<Baseline><Number>0</Number>`), des durées
ISO (`PT...`), des jalons (`Milestone=1` ou durée nulle), des tâches désactivées (`Active=0`),
des coûts (`<Cost>`), un calendrier hebdomadaire (`<Calendars>`) et des dépendances
`<PredecessorLink>` (types `FS`, `SS`, `FF`, `SF` + décalages `LinkLag`/`LagFormat`).

Règles métier appliquées :
- **Verrou strict de démarrage** (`etat_import_ms_project`) : dès qu'au moins une trace
  d'exécution existe sur le découpage du projet, l'import est bloqué.
- **Remplacement explicite** : si un découpage existe sans exécution démarrée, l'import exige
  `confirmer_remplacement=True` et supprime **logiquement** (`supprimer_logiquement`) les
  anciennes dépendances, cases et niveaux dans cet ordre.
- **Sécurité XML (anti-XXE)** : toute déclaration `<!DOCTYPE` ou `<!ENTITY` est rejetée
  avant l'analyse `xml.etree.ElementTree`, sans dépendance tierce.
- **Dépendances** : les quatre types (`FS`, `SS`, `FF`, `SF`) avec décalages en jours ouvrés
  entre deux feuilles actives sans cycle sont retenus ; tout lien écarté ou arrondi est
  expliqué dans `avertissements`.
- **Montants (`<Cost>`)** : opt-in (`importer_montants=True`), sous `projets.chiffrer` sur tout
  le projet, conversion vers centimes de FCFA avec anti-double-comptage parents/feuilles.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.contexte import entreprise_courante_id
from apps.core.enums import ActionAudit, StatutActivite
from apps.core.exceptions import ErreurMetier
from apps.core.validators import MONTANT_MAX_CENTIMES
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
    SemaineType,
    TypeDependance,
)
from apps.projets.services import dependances as service_dependances
from apps.projets.services.calendrier_ouvre import (
    CALENDRIER_PAR_DEFAUT_SEMAINE,
    Calendrier,
    calendrier_entreprise,
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
    "0": TypeDependance.FF,
    "1": TypeDependance.FS,
    "2": TypeDependance.SF,
    "3": TypeDependance.SS,
}

# Formats MSPDI de <LagFormat> exprimés en pourcentage de la durée du prédécesseur.
LAG_FORMATS_POURCENTAGE = frozenset({"19", "20", "51", "52"})

# Correspondance MSPDI <DayType> (1=Dimanche .. 7=Samedi) -> date.weekday() (0=Lundi .. 6=Dimanche).
DAY_TYPE_VERS_WEEKDAY = {
    "1": 6,  # Dimanche
    "2": 0,  # Lundi
    "3": 1,  # Mardi
    "4": 2,  # Mercredi
    "5": 3,  # Jeudi
    "6": 4,  # Vendredi
    "7": 5,  # Samedi
}

NOMS_JOURS_COURTS = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")

TAUX_CONVERSION_SUGGERES: dict[str, float] = {
    "XOF": 1.0,
    "EUR": 655.957,
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


def _parser_cout_brut(valeur: str) -> Decimal | None:
    """Lit `<Cost>` MSPDI (stocké en centièmes de la devise) → unité de devise, ou None."""
    if not valeur:
        return None
    try:
        brut = Decimal(valeur.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not brut.is_finite() or brut <= 0:
        return None
    return brut / Decimal("100")


def _extraire_baseline_zero(balise_tache: ET.Element) -> tuple[date | None, date | None]:
    """Extrait `<Start>` et `<Finish>` du bloc `<Baseline>` portant `<Number>0</Number>`."""
    for bl in _enfants(balise_tache, "Baseline"):
        numero = _texte_enfant(bl, "Number")
        if numero == "0":
            b_debut = _parser_date_iso(_texte_enfant(bl, "Start"))
            b_fin = _parser_date_iso(_texte_enfant(bl, "Finish"))
            if b_debut is not None and b_fin is not None and b_fin < b_debut:
                b_fin = b_debut
            return b_debut, b_fin
    return None, None


def _extraire_jours_semaine_xml(racine: ET.Element) -> frozenset[int] | None:
    """Lit les jours ouvrés de la semaine du calendrier principal `<Calendar>` du XML."""
    bloc_calendriers = _enfant(racine, "Calendars")
    if bloc_calendriers is None:
        return None
    calendriers = _enfants(bloc_calendriers, "Calendar")
    if not calendriers:
        return None

    uid_cible = _texte_enfant(racine, "CalendarUID") or "1"
    cal_choisi = next((c for c in calendriers if _texte_enfant(c, "UID") == uid_cible), None)
    if cal_choisi is None:
        cal_choisi = next(
            (c for c in calendriers if _texte_enfant(c, "IsBaseCalendar") == "1"),
            calendriers[0],
        )

    bloc_weekdays = _enfant(cal_choisi, "WeekDays")
    if bloc_weekdays is None:
        return None

    jours = set(CALENDRIER_PAR_DEFAUT_SEMAINE)
    au_moins_un = False
    for wd in _enfants(bloc_weekdays, "WeekDay"):
        day_type = _texte_enfant(wd, "DayType")
        weekday = DAY_TYPE_VERS_WEEKDAY.get(day_type)
        if weekday is None:
            continue
        day_working = _texte_enfant(wd, "DayWorking")
        if day_working == "1":
            jours.add(weekday)
            au_moins_un = True
        elif day_working == "0":
            jours.discard(weekday)
            au_moins_un = True
    return frozenset(jours) if au_moins_un else None


def _formater_jours_semaine(jours: frozenset[int]) -> str:
    if not jours:
        return str(_("aucun jour"))
    return ", ".join(NOMS_JOURS_COURTS[j] for j in sorted(jours) if 0 <= j <= 6)


def _convertir_en_centimes_fcfa(
    cout_brut: Decimal,
    taux_conversion: Decimal,
    *,
    valider_plafond: bool = False,
) -> int:
    """Convertit un coût brut (unité de devise XML) en entier de centimes de FCFA."""
    centimes = int(
        (cout_brut * taux_conversion).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 100
    )
    if valider_plafond and centimes > MONTANT_MAX_CENTIMES:
        raise ValidationError(
            {
                "taux_conversion": _(
                    "Un montant converti dépasse le plafond autorisé de 999 999 999 999 FCFA."
                )
            }
        )
    return centimes


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
class _LienBrut:
    predecesseur_uid: str
    type_brut: str
    link_lag: int
    lag_format: str


@dataclass
class _NoeudTache:
    uid: str
    outline_number: str
    code_source: str
    numero: str
    libelle: str
    outline_level: int
    niveau_ordre: int
    debut: date | None
    fin: date | None
    debut_baseline: date | None
    fin_baseline: date | None
    duree_heures: float | None
    duree_brute: str
    est_jalon: bool
    est_actif: bool
    est_summary_xml: bool
    pourcentage_xml: float | None
    cout_brut: Decimal | None
    code_metier: str = ""
    enveloppe_active_brute: Decimal | None = None
    liens_bruts: list[_LienBrut] = field(default_factory=list)
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
    debut_baseline_projet: date | None
    fin_baseline_projet: date | None
    devise_code: str
    cout_total_brut_actif: Decimal


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


def _calendrier_pour_analyse(tous_noeuds: list[_NoeudTache]) -> Calendrier:
    dates = [
        d
        for n in tous_noeuds
        for d in (n.debut, n.fin, n.debut_baseline, n.fin_baseline)
        if d is not None
    ]
    if dates:
        d_min = min(dates) - timedelta(days=365)
        d_max = max(dates) + timedelta(days=365)
    else:
        aujourd_hui = date.today()
        d_min = aujourd_hui - timedelta(days=365)
        d_max = aujourd_hui + timedelta(days=365)
    if entreprise_courante_id() is not None:
        return calendrier_entreprise(d_min, d_max)
    return Calendrier(
        jours_semaine=CALENDRIER_PAR_DEFAUT_SEMAINE,
        feries=frozenset(),
        exceptions={},
    )


def _convertir_lag_en_jours(
    predecesseur: _NoeudTache,
    successeur: _NoeudTache,
    lien: _LienBrut,
    *,
    minutes_par_jour: int,
    heures_par_jour: float,
    calendrier: Calendrier,
    avertissements: list[dict],
) -> int:
    """Convertit `<LinkLag>` / `<LagFormat>` MSPDI en jours ouvrés entiers signés."""
    if lien.link_lag == 0:
        return 0

    lag_format = (lien.lag_format or "7").strip()
    if lag_format in LAG_FORMATS_POURCENTAGE:
        if predecesseur.duree_heures is not None and heures_par_jour > 0:
            duree_jours = Decimal(str(predecesseur.duree_heures)) / Decimal(str(heures_par_jour))
        elif predecesseur.debut is not None and predecesseur.fin is not None:
            duree_jours = Decimal(
                service_dependances.compter_duree_ouvree(
                    predecesseur.debut, predecesseur.fin, calendrier
                )
            )
        else:
            duree_jours = Decimal(0)

        brut_jours = duree_jours * Decimal(lien.link_lag) / Decimal(100)
        jours = int(brut_jours.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if brut_jours != Decimal(jours) or (duree_jours == 0 and lien.link_lag != 0):
            avertissements.append(
                {
                    "code": "DEPENDANCE_DECALAGE_ARRONDI",
                    "message": str(
                        _(
                            "Décalage en pourcentage (%(pct)d %%) entre « %(pred)s » et "
                            "« %(succ)s » converti et arrondi à %(jours)d jour(s) ouvré(s)."
                        )
                    )
                    % {
                        "pct": lien.link_lag,
                        "pred": predecesseur.libelle,
                        "succ": successeur.libelle,
                        "jours": jours,
                    },
                }
            )
        return jours

    dixiemes_par_jour = minutes_par_jour * 10
    jours = round(lien.link_lag / dixiemes_par_jour)
    if lien.link_lag % dixiemes_par_jour != 0:
        avertissements.append(
            {
                "code": "DEPENDANCE_DECALAGE_ARRONDI",
                "message": str(
                    _(
                        "Décalage non entier entre « %(pred)s » et « %(succ)s » "
                        "(%(brut).2f j) arrondi à %(jours)d jour(s) ouvré(s)."
                    )
                )
                % {
                    "pred": predecesseur.libelle,
                    "succ": successeur.libelle,
                    "brut": lien.link_lag / dixiemes_par_jour,
                    "jours": jours,
                },
            }
        )
    return jours


def _calculer_couts_anti_double_comptage(racines: list[_NoeudTache]) -> tuple[Decimal, int]:
    """Détermine les enveloppes parents sans double comptage et le total actif brut.

    Règle anti-double-comptage :
    - Feuille active avec coût > 0 : porte directement son montant ; compte dans `taches_chiffrees`.
    - Parent actif avec coût > 0 : si toutes ses feuilles actives descendantes ont un coût > 0
      et `cout_parent == somme_enfants_directs` → `enveloppe_active_brute = None` (simple cumul
      MS Project) ; sinon → `enveloppe_active_brute = cout_parent` (enveloppe explicite).
    - Tâches inactives (`est_actif=False`) : exclues du total actif et des montants importés.
    """
    taches_chiffrees = 0

    def _visiter(noeud: _NoeudTache) -> tuple[Decimal, bool]:
        """Rend `(cout_effectif_branche, toutes_feuilles_actives_chiffrees)`."""
        nonlocal taches_chiffrees
        if not noeud.est_actif:
            noeud.enveloppe_active_brute = None
            return Decimal(0), True

        if noeud.est_feuille:
            if noeud.cout_brut is not None and noeud.cout_brut > 0:
                taches_chiffrees += 1
                return noeud.cout_brut, True
            return Decimal(0), False

        enfants_actifs = [e for e in noeud.enfants if e.est_actif]
        if not enfants_actifs:
            if noeud.cout_brut is not None and noeud.cout_brut > 0:
                noeud.enveloppe_active_brute = noeud.cout_brut
                taches_chiffrees += 1
                return noeud.cout_brut, True
            noeud.enveloppe_active_brute = None
            return Decimal(0), False

        resultats_enfants = [_visiter(e) for e in enfants_actifs]
        somme_effective = sum((c for c, _ in resultats_enfants), Decimal(0))
        somme_directe = sum(
            (
                e.cout_brut if e.cout_brut is not None else c_eff
                for e, (c_eff, _) in zip(enfants_actifs, resultats_enfants, strict=True)
            ),
            Decimal(0),
        )
        toutes_feuilles_chiffrees = all(ok for _, ok in resultats_enfants)

        if noeud.cout_brut is not None and noeud.cout_brut > 0:
            if toutes_feuilles_chiffrees and noeud.cout_brut == somme_directe:
                noeud.enveloppe_active_brute = None
                return somme_effective, True
            noeud.enveloppe_active_brute = noeud.cout_brut
            taches_chiffrees += 1
            return noeud.cout_brut, toutes_feuilles_chiffrees

        noeud.enveloppe_active_brute = None
        return somme_effective, toutes_feuilles_chiffrees

    total_actif = sum((_visiter(r)[0] for r in racines), Decimal(0))
    return total_actif, taches_chiffrees


def _analyser_interne(
    projet: Projet,
    fichier,
    *,
    etat: dict | None = None,
    peut_voir_montants: bool = True,
    peut_chiffrer: bool = True,
) -> _ResultatAnalyse:
    racine = _lire_et_valider_xml(fichier)
    etat_base = etat if etat is not None else etat_import_ms_project(projet)
    etat_import = {
        **etat_base,
        "peut_voir_montants": bool(peut_voir_montants),
        "peut_chiffrer": bool(peut_chiffrer),
    }

    minutes_xml = _parser_entier(_texte_enfant(racine, "MinutesPerDay"))
    minutes_par_jour = minutes_xml if minutes_xml and minutes_xml > 0 else 480
    heures_par_jour = minutes_par_jour / 60.0

    devise_code = (_texte_enfant(racine, "CurrencyCode") or "XOF").strip().upper()
    devise_symbole = (
        _texte_enfant(racine, "CurrencySymbol")
        or ("FCFA" if devise_code == "XOF" else devise_code)
    ).strip()
    taux_suggere = TAUX_CONVERSION_SUGGERES.get(devise_code)

    titre_xml = (
        " ".join(_texte_enfant(racine, "Title").split())
        or " ".join(_texte_enfant(racine, "Name").split())
        or None
    )
    debut_projet_xml = _parser_date_iso(_texte_enfant(racine, "StartDate"))
    fin_projet_xml = _parser_date_iso(_texte_enfant(racine, "FinishDate"))
    debut_baseline_projet_xml: date | None = None
    fin_baseline_projet_xml: date | None = None

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

        uid_brut = _texte_enfant(balise_tache, "UID")
        task_id = _parser_entier(_texte_enfant(balise_tache, "ID"))
        outline_level = _parser_entier(_texte_enfant(balise_tache, "OutlineLevel"))
        libelle_brut = " ".join(_texte_enfant(balise_tache, "Name").split())

        if uid_brut == "0" or task_id == 0 or outline_level == 0:
            if not titre_xml and libelle_brut:
                titre_xml = libelle_brut
            if debut_projet_xml is None:
                debut_projet_xml = _parser_date_iso(_texte_enfant(balise_tache, "Start"))
            if fin_projet_xml is None:
                fin_projet_xml = _parser_date_iso(_texte_enfant(balise_tache, "Finish"))
            b_deb, b_fin = _extraire_baseline_zero(balise_tache)
            if debut_baseline_projet_xml is None and b_deb is not None:
                debut_baseline_projet_xml = b_deb
            if fin_baseline_projet_xml is None and b_fin is not None:
                fin_baseline_projet_xml = b_fin
            continue

        if not libelle_brut:
            continue

        uid = uid_brut or (str(task_id) if task_id is not None else f"tache-{index}")
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
        wbs = _texte_enfant(balise_tache, "WBS")
        code_source = (wbs or outline_number or "").strip()

        debut = _parser_date_iso(_texte_enfant(balise_tache, "Start"))
        fin = _parser_date_iso(_texte_enfant(balise_tache, "Finish"))
        debut_baseline, fin_baseline = _extraire_baseline_zero(balise_tache)

        duree_brute = _texte_enfant(balise_tache, "Duration").strip().upper()
        duree_heures = _parser_duree_heures(duree_brute, heures_par_jour=heures_par_jour)
        est_jalon = _texte_enfant(balise_tache, "Milestone") == "1"
        est_actif = _texte_enfant(balise_tache, "Active") != "0"
        est_summary_xml = _texte_enfant(balise_tache, "Summary") == "1"
        pourcentage_xml = _parser_pourcentage(_texte_enfant(balise_tache, "PercentComplete"))
        cout_brut = _parser_cout_brut(_texte_enfant(balise_tache, "Cost"))

        if est_jalon:
            if debut is not None:
                fin = debut
            elif fin is not None:
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

        liens_bruts: list[_LienBrut] = []
        for lien_xml in _enfants(balise_tache, "PredecessorLink"):
            liens_bruts.append(
                _LienBrut(
                    predecesseur_uid=_texte_enfant(lien_xml, "PredecessorUID"),
                    type_brut=_texte_enfant(lien_xml, "Type"),
                    link_lag=_parser_entier(_texte_enfant(lien_xml, "LinkLag")) or 0,
                    lag_format=_texte_enfant(lien_xml, "LagFormat") or "7",
                )
            )

        while pile and pile[-1].outline_level >= niveau_xml:
            pile.pop()
        niveau_ordre = len(pile) + 1

        noeud = _NoeudTache(
            uid=uid,
            outline_number=outline_number,
            code_source=code_source,
            numero=outline_number,
            libelle=libelle_brut,
            outline_level=niveau_xml,
            niveau_ordre=niveau_ordre,
            debut=debut,
            fin=fin,
            debut_baseline=debut_baseline,
            fin_baseline=fin_baseline,
            duree_heures=duree_heures,
            duree_brute=duree_brute,
            est_jalon=est_jalon,
            est_actif=est_actif,
            est_summary_xml=est_summary_xml,
            pourcentage_xml=pourcentage_xml,
            cout_brut=cout_brut,
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

    # Normalisation de l'arbre : propagation est_actif, détection jalons, codes anti-doublon,
    # déduplication frères et enveloppe de dates parents.
    profondeur_max = 1

    def _normaliser_branche(
        noeuds: list[_NoeudTache], prefixe: str, *, parent_actif: bool = True
    ) -> None:
        nonlocal profondeur_max
        cles_vues: set[str] = set()
        for rang, noeud in enumerate(noeuds, start=1):
            if not parent_actif:
                noeud.est_actif = False
            if noeud.niveau_ordre > profondeur_max:
                profondeur_max = noeud.niveau_ordre

            numero_calcule = f"{prefixe}{rang}"
            if not noeud.numero:
                noeud.numero = numero_calcule

            # Anti-doublon code : on ne conserve dans Element.code qu'un code distinct de la
            # numérotation hiérarchique calculée (1, 1.1, 1.2…).
            if not noeud.code_source or noeud.code_source == numero_calcule:
                noeud.code_metier = ""
            else:
                noeud.code_metier = noeud.code_source[:LONGUEUR_MAX_CODE]

            # Détection des jalons à durée nulle sur les feuilles + alignement fin = debut.
            if (
                not noeud.est_jalon
                and noeud.est_feuille
                and (noeud.duree_heures == 0.0 or noeud.duree_brute == "PT0H0M0S")
            ):
                noeud.est_jalon = True

            if noeud.est_jalon:
                if noeud.debut is not None:
                    noeud.fin = noeud.debut
                elif noeud.fin is not None:
                    noeud.debut = noeud.fin
                if noeud.debut_baseline is not None:
                    noeud.fin_baseline = noeud.debut_baseline
                elif noeud.fin_baseline is not None:
                    noeud.debut_baseline = noeud.fin_baseline

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
                _normaliser_branche(
                    noeud.enfants, f"{numero_calcule}.", parent_actif=noeud.est_actif
                )
                enfants_dates = [e for e in noeud.enfants if e.est_actif] or noeud.enfants
                if noeud.debut is None:
                    debuts_enfants = [e.debut for e in enfants_dates if e.debut is not None]
                    if debuts_enfants:
                        noeud.debut = min(debuts_enfants)
                if noeud.fin is None:
                    fins_enfants = [e.fin for e in enfants_dates if e.fin is not None]
                    if fins_enfants:
                        noeud.fin = max(fins_enfants)
            elif noeud.est_summary_xml:
                avertissements.append(
                    {
                        "code": "SUMMARY_VIDE",
                        "message": str(
                            _(
                                "La tâche récapitulative « %(libelle)s » (Summary=1) ne contient "
                                "aucune sous-tâche : elle sera importée comme tâche feuille."
                            )
                        )
                        % {"libelle": noeud.libelle},
                    }
                )

    _normaliser_branche(racines, "", parent_actif=True)

    # Avertissements anti-pertes silencieuses
    nb_inactives = sum(1 for n in tous_noeuds if not n.est_actif)
    if nb_inactives > 0:
        avertissements.append(
            {
                "code": "TACHES_INACTIVES_IMPORTEES",
                "message": str(
                    _(
                        "%(nb)d tâche(s) désactivée(s) dans MS Project seront importées comme "
                        "inactives (exclues du planning actif, de l'avancement et des dépendances)."
                    )
                )
                % {"nb": nb_inactives},
            }
        )

    nb_avancement = sum(
        1 for n in tous_noeuds if n.pourcentage_xml is not None and n.pourcentage_xml > 0
    )
    if nb_avancement > 0:
        avertissements.append(
            {
                "code": "AVANCEMENT_XML_IGNORE",
                "message": str(
                    _(
                        "%(nb)d tâche(s) portent un avancement dans MS Project "
                        "(PercentComplete > 0) : ces valeurs ne sont pas importées "
                        "(l'avancement démarre à 0 %% dans CCD Digital)."
                    )
                )
                % {"nb": nb_avancement},
            }
        )

    if projet.date_debut_prevue is not None or projet.date_fin_prevue is not None:
        nb_debordement = sum(
            1
            for n in tous_noeuds
            if n.est_actif
            and (
                (
                    projet.date_debut_prevue is not None
                    and n.debut is not None
                    and n.debut < projet.date_debut_prevue
                )
                or (
                    projet.date_fin_prevue is not None
                    and n.fin is not None
                    and n.fin > projet.date_fin_prevue
                )
            )
        )
        if nb_debordement > 0:
            avertissements.append(
                {
                    "code": "DEBORDEMENT_DATES_PROJET",
                    "message": str(
                        _(
                            "%(nb)d tâche(s) du planning XML sortent des dates prévisionnelles "
                            "actuelles du projet (%(debut)s → %(fin)s)."
                        )
                    )
                    % {
                        "nb": nb_debordement,
                        "debut": (
                            projet.date_debut_prevue.isoformat()
                            if projet.date_debut_prevue
                            else "—"
                        ),
                        "fin": (
                            projet.date_fin_prevue.isoformat()
                            if projet.date_fin_prevue
                            else "—"
                        ),
                    },
                }
            )

    jours_xml = _extraire_jours_semaine_xml(racine)
    if jours_xml is not None:
        jours_entreprise = (
            SemaineType.courante().jours_travailles()
            if entreprise_courante_id() is not None
            else CALENDRIER_PAR_DEFAUT_SEMAINE
        )
        if jours_xml != jours_entreprise:
            avertissements.append(
                {
                    "code": "CALENDRIER_SEMAINE_DIVERGENTE",
                    "message": str(
                        _(
                            "La semaine travaillée du calendrier MS Project (%(xml)s) diffère "
                            "de celle de votre entreprise (%(entreprise)s) : le calendrier "
                            "d'entreprise s'appliquera après import."
                        )
                    )
                    % {
                        "xml": _formater_jours_semaine(jours_xml),
                        "entreprise": _formater_jours_semaine(jours_entreprise),
                    },
                }
            )

    niveaux = _generer_niveaux(projet, profondeur_max)
    libelle_par_ordre = {niv["ordre"]: niv["libelle"] for niv in niveaux}

    # Calcul des coûts (anti-double-comptage)
    cout_total_brut_actif, taches_chiffrees = _calculer_couts_anti_double_comptage(racines)

    # Filtrage des dépendances : 4 types (FS, SS, FF, SF) + décalage, entre feuilles actives,
    # sans doublon ni cycle.
    calendrier = _calendrier_pour_analyse(tous_noeuds)
    dependances_retenues: list[dict] = []
    dependances_ignorees = 0
    graphe_successeurs: dict[str, list[str]] = defaultdict(list)
    paires_vues: set[tuple[str, str]] = set()

    for successeur in tous_noeuds:
        for lien in successeur.liens_bruts:
            pred_uid = lien.predecesseur_uid
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
            code_type = lien.type_brut or "1"
            nom_type = TYPES_LIENS_MS_PROJECT.get(code_type)

            if nom_type is None:
                dependances_ignorees += 1
                avertissements.append(
                    {
                        "code": "DEPENDANCE_TYPE_NON_SUPPORTE",
                        "message": str(
                            _(
                                "Lien de type inconnu « %(type_brut)s » ignoré entre « %(pred)s » "
                                "et « %(succ)s »."
                            )
                        )
                        % {
                            "type_brut": code_type,
                            "pred": predecesseur.libelle,
                            "succ": successeur.libelle,
                        },
                    }
                )
                continue

            if not predecesseur.est_actif or not successeur.est_actif:
                dependances_ignorees += 1
                avertissements.append(
                    {
                        "code": "DEPENDANCE_TACHE_INACTIVE_IGNOREE",
                        "message": str(
                            _(
                                "Lien ignoré entre « %(pred)s » et « %(succ)s » : au moins une "
                                "des deux tâches est désactivée dans MS Project."
                            )
                        )
                        % {"pred": predecesseur.libelle, "succ": successeur.libelle},
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

            decalage_jours = _convertir_lag_en_jours(
                predecesseur,
                successeur,
                lien,
                minutes_par_jour=minutes_par_jour,
                heures_par_jour=heures_par_jour,
                calendrier=calendrier,
                avertissements=avertissements,
            )

            paires_vues.add(paire)
            graphe_successeurs[predecesseur.uid].append(successeur.uid)
            est_respectee = service_dependances.respectee(
                predecesseur,
                successeur,
                type_lien=nom_type,
                decalage_jours=decalage_jours,
                calendrier=calendrier,
            )

            dependances_retenues.append(
                {
                    "predecesseur_uid": predecesseur.uid,
                    "predecesseur_libelle": predecesseur.libelle,
                    "successeur_uid": successeur.uid,
                    "successeur_libelle": successeur.libelle,
                    "type": str(nom_type),
                    "decalage_jours": decalage_jours,
                    "respectee": est_respectee,
                }
            )

    taux_apercu = Decimal(str(taux_suggere)) if taux_suggere is not None else None

    def _serialiser_noeud(noeud: _NoeudTache) -> dict:
        if peut_voir_montants and noeud.cout_brut is not None:
            cout_brut_val = float(noeud.cout_brut)
            cout_fcfa_val = (
                _convertir_en_centimes_fcfa(noeud.cout_brut, taux_apercu)
                if taux_apercu is not None
                else None
            )
        else:
            cout_brut_val = None
            cout_fcfa_val = None
        return {
            "uid": noeud.uid,
            "numero": noeud.numero,
            "libelle": noeud.libelle,
            "niveau_ordre": noeud.niveau_ordre,
            "niveau": libelle_par_ordre[noeud.niveau_ordre],
            "debut": noeud.debut.isoformat() if noeud.debut else None,
            "fin": noeud.fin.isoformat() if noeud.fin else None,
            "debut_baseline": noeud.debut_baseline.isoformat() if noeud.debut_baseline else None,
            "fin_baseline": noeud.fin_baseline.isoformat() if noeud.fin_baseline else None,
            "duree_heures": noeud.duree_heures,
            "est_jalon": noeud.est_jalon,
            "est_feuille": noeud.est_feuille,
            "est_actif": noeud.est_actif,
            "pourcentage_xml": noeud.pourcentage_xml,
            "cout_brut": cout_brut_val,
            "cout_fcfa": cout_fcfa_val,
            "enfants": [_serialiser_noeud(enfant) for enfant in noeud.enfants],
        }

    noeuds_dates = [n for n in tous_noeuds if n.est_actif] or tous_noeuds
    debuts = [n.debut for n in noeuds_dates if n.debut is not None]
    fins = [n.fin for n in noeuds_dates if n.fin is not None]
    min_debut = min(debuts) if debuts else debut_projet_xml
    max_fin = max(fins) if fins else fin_projet_xml

    projet_debut_final = debut_projet_xml or min_debut
    projet_fin_final = fin_projet_xml or max_fin
    if projet_debut_final and projet_fin_final and projet_fin_final < projet_debut_final:
        projet_fin_final = projet_debut_final

    feuilles = sum(1 for n in tous_noeuds if n.est_feuille)
    jalons = sum(1 for n in tous_noeuds if n.est_jalon)

    if peut_voir_montants and cout_total_brut_actif > 0:
        cout_total_brut_val: float | None = float(cout_total_brut_actif)
        cout_total_fcfa_val: int | None = (
            _convertir_en_centimes_fcfa(cout_total_brut_actif, taux_apercu)
            if taux_apercu is not None
            else None
        )
    else:
        cout_total_brut_val = None
        cout_total_fcfa_val = None

    payload = {
        "etat_import": etat_import,
        "projet_xml": {
            "titre": titre_xml,
            "date_debut": projet_debut_final.isoformat() if projet_debut_final else None,
            "date_fin": projet_fin_final.isoformat() if projet_fin_final else None,
            "date_debut_baseline": (
                debut_baseline_projet_xml.isoformat() if debut_baseline_projet_xml else None
            ),
            "date_fin_baseline": (
                fin_baseline_projet_xml.isoformat() if fin_baseline_projet_xml else None
            ),
            "devise_code": devise_code,
            "devise_symbole": devise_symbole,
            "taux_conversion_suggere": taux_suggere,
            "cout_total_brut": cout_total_brut_val,
            "cout_total_fcfa": cout_total_fcfa_val,
        },
        "niveaux": niveaux,
        "taches": [_serialiser_noeud(racine_tache) for racine_tache in racines],
        "dependances": dependances_retenues,
        "statistiques": {
            "total_taches": len(tous_noeuds),
            "feuilles": feuilles,
            "jalons": jalons,
            "inactives": nb_inactives,
            "taches_chiffrees": taches_chiffrees,
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
        debut_baseline_projet=debut_baseline_projet_xml,
        fin_baseline_projet=fin_baseline_projet_xml,
        devise_code=devise_code,
        cout_total_brut_actif=cout_total_brut_actif,
    )


# --------------------------------------------------------------------------
# API publique du service
# --------------------------------------------------------------------------
def analyser_ms_project(
    projet: Projet,
    fichier,
    *,
    peut_voir_montants: bool = True,
    peut_chiffrer: bool = True,
) -> dict:
    """Analyse un fichier MS Project `.xml` sans aucune écriture en base."""
    return _analyser_interne(
        projet,
        fichier,
        peut_voir_montants=peut_voir_montants,
        peut_chiffrer=peut_chiffrer,
    ).payload


def importer_ms_project(
    projet: Projet,
    fichier,
    *,
    auteur,
    confirmer_remplacement: bool = False,
    importer_montants: bool = False,
    taux_conversion: Decimal = Decimal("1"),
) -> dict:
    """Importe un planning MS Project `.xml` dans le découpage et les dépendances du projet."""
    from apps.audit.services import journaliser
    from apps.projets.services.avancement import recalculer_avancements_projet

    try:
        taux = Decimal(str(taux_conversion)) if taux_conversion is not None else Decimal("1")
    except InvalidOperation:
        raise ValidationError(
            {"taux_conversion": _("Le taux de conversion doit être un nombre valide.")}
        ) from None
    if importer_montants and (not taux.is_finite() or taux <= 0):
        raise ValidationError(
            {"taux_conversion": _("Le taux de conversion doit être strictement positif.")}
        )

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

        resultat_analyse = _analyser_interne(
            projet,
            fichier,
            etat=etat,
            peut_voir_montants=True,
            peut_chiffrer=True,
        )
        payload = resultat_analyse.payload

        # Pré-validation de tous les montants convertis avant écriture
        montants_par_uid: dict[str, tuple[int | None, int | None]] = {}
        total_actif_centimes = 0
        if importer_montants:
            def _preparer_montants(noeuds: list[_NoeudTache]) -> None:
                for noeud in noeuds:
                    if not noeud.est_actif:
                        montants_par_uid[noeud.uid] = (None, None)
                    elif noeud.est_feuille:
                        montant_c = (
                            _convertir_en_centimes_fcfa(
                                noeud.cout_brut, taux, valider_plafond=True
                            )
                            if noeud.cout_brut is not None and noeud.cout_brut > 0
                            else None
                        )
                        montants_par_uid[noeud.uid] = (montant_c, None)
                    else:
                        enveloppe_c = (
                            _convertir_en_centimes_fcfa(
                                noeud.enveloppe_active_brute, taux, valider_plafond=True
                            )
                            if noeud.enveloppe_active_brute is not None
                            and noeud.enveloppe_active_brute > 0
                            else None
                        )
                        montants_par_uid[noeud.uid] = (None, enveloppe_c)
                    if noeud.enfants:
                        _preparer_montants(noeud.enfants)

            _preparer_montants(resultat_analyse.racines)
            if resultat_analyse.cout_total_brut_actif > 0:
                total_actif_centimes = _convertir_en_centimes_fcfa(
                    resultat_analyse.cout_total_brut_actif, taux, valider_plafond=True
                )

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
                montant_elem, enveloppe_elem = montants_par_uid.get(noeud.uid, (None, None))
                element = Element.objects.create(
                    projet=projet,
                    parent=parent,
                    niveau=niveaux_par_ordre[noeud.niveau_ordre],
                    libelle=noeud.libelle,
                    code=noeud.code_metier,
                    ordre=ordre,
                    mode_mesure=mode_mesure,
                    montant=montant_elem,
                    enveloppe=enveloppe_elem,
                    date_debut_prevue=noeud.debut,
                    date_fin_prevue=noeud.fin,
                    date_debut_baseline=noeud.debut_baseline,
                    date_fin_baseline=noeud.fin_baseline,
                    dates_calculees=est_parent,
                    est_actif=noeud.est_actif,
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
                type_lien=dep["type"],
                decalage_jours=dep["decalage_jours"],
                cree_par=auteur,
            )
            dependances_creees += 1

        champs_projet_maj: list[str] = []
        if (
            projet.date_debut_prevue is None
            and projet.date_fin_prevue is None
            and resultat_analyse.min_debut is not None
            and resultat_analyse.max_fin is not None
            and resultat_analyse.max_fin >= resultat_analyse.min_debut
        ):
            projet.date_debut_prevue = resultat_analyse.min_debut
            projet.date_fin_prevue = resultat_analyse.max_fin
            if (
                projet.date_debut_baseline is None
                and resultat_analyse.debut_baseline_projet is not None
            ):
                projet.date_debut_baseline = resultat_analyse.debut_baseline_projet
            if (
                projet.date_fin_baseline is None
                and resultat_analyse.fin_baseline_projet is not None
            ):
                projet.date_fin_baseline = resultat_analyse.fin_baseline_projet
            champs_projet_maj.extend(
                [
                    "date_debut_prevue",
                    "date_fin_prevue",
                    "date_debut_baseline",
                    "date_fin_baseline",
                ]
            )

        if (
            importer_montants
            and projet.budget_initial_montant is None
            and total_actif_centimes > 0
        ):
            projet.budget_initial_montant = total_actif_centimes
            champs_projet_maj.append("budget_initial_montant")

        if champs_projet_maj:
            champs_projet_maj.append("modifie_le")
            projet.save(update_fields=list(dict.fromkeys(champs_projet_maj)))

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
                "importer_montants": bool(importer_montants),
                "taux_conversion": str(taux) if importer_montants else None,
            },
        )

    return {
        "elements_crees": elements_crees,
        "niveaux_crees": len(niveaux_par_ordre),
        "dependances_creees": dependances_creees,
        "remplacement_effectue": remplacement_effectue,
        "avertissements": payload["avertissements"],
    }
