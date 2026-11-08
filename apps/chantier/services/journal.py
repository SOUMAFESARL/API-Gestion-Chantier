"""Écritures atomiques du journal : brouillon, soumission, blocages et signatures."""

import base64
import binascii
import io
import json
import re
from collections.abc import Iterable, Mapping
from datetime import date, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.chantier.models import AlerteJournal, Blocage, JournalChantier, RapportJournalier
from apps.chantier.serializers.journal import (
    MOTIFS_ARRET,
    NATURES_INCIDENT,
    TAILLE_MAX_PHOTO_OCTETS,
    TAILLE_MAX_PIECE_OCTETS,
    TAILLE_MAX_RAPPORT_OCTETS,
    SaisieJournalSerializer,
)
from apps.chantier.services import signatures
from apps.chantier.services.blocage import creer_blocage, modifier_blocage
from apps.chantier.services.equipes_journal import (
    controler_equipes,
    effectif_present,
    equipes_du_journal,
    exiger_equipes,
)
from apps.chantier.services.fonctions import (
    APPROUVER,
    REDIGER,
    VALIDER,
    affectations_actives,
    chemins_des_cases,
    tient_fonction,
    titulaires,
    verifier_fonction,
)
from apps.core.enums import ActionAudit, SeveriteBlocage, StatutRapport
from apps.core.exceptions import ErreurMetier, RapportDejaExistant, RapportNonModifiable
from apps.projets.models import Element, ModeMesure, Projet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.calendrier_ouvre import calendrier_entreprise
from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture
from apps.projets.services.sante_declencheur import declencher_recalcul_sante

FUSEAU_CHANTIER = ZoneInfo("Africa/Abidjan")
FENETRE_JOURS_OUVRES = 3
HORIZON_RECHERCHE_CALENDRIER = 45

SEVERITE_BLOCAGE_PAR_NIVEAU = {
    "MINEUR": SeveriteBlocage.MINEUR,
    "SIGNIFICATIF": SeveriteBlocage.MAJEUR,
    "BLOQUANT": SeveriteBlocage.CRITIQUE,
}

DECIDEUR_ANCIEN_VERS_NOUVEAU = {
    "CC": "REDACTION",
    "CT": "VALIDATION",
    "CP": "APPROBATION",
}


class RapportIncomplet(ErreurMetier):
    """Il manque au rapport de quoi être soumis ; le code d'erreur reste « regle_metier »."""


def aujourdhui() -> date:
    return timezone.localdate(timezone=FUSEAU_CHANTIER)


def premier_jour_rapport(projet) -> date:
    """Le premier jour qui attend un rapport : début du chantier, mais jamais avant son
    enregistrement sur la plateforme (décision du 16/10/2026).
    """
    debut = projet.date_debut_reelle or projet.date_debut_prevue
    enregistre = timezone.localdate(projet.cree_le, timezone=FUSEAU_CHANTIER)
    return max(debut, enregistre) if debut else enregistre


def jours_saisissables_ouvres(
    reference: date | None = None, nb: int = FENETRE_JOURS_OUVRES
) -> list[date]:
    """Les `nb` derniers jours ouvrés du calendrier de l'entreprise jusqu'à `reference` inclus."""
    ref = reference or aujourdhui()
    debut_recherche = ref - timedelta(days=HORIZON_RECHERCHE_CALENDRIER)
    cal = calendrier_entreprise(debut_recherche, ref)
    retenus: list[date] = []
    for offset in range(HORIZON_RECHERCHE_CALENDRIER + 1):
        candidat = ref - timedelta(days=offset)
        if cal.est_ouvre(candidat):
            retenus.append(candidat)
            if len(retenus) >= nb:
                break
    retenus.reverse()
    return retenus


def jours_saisissables_projet(
    projet, reference: date | None = None, *, conserver: Iterable[date] = ()
) -> list[date]:
    """Les jours saisissables **de ce chantier** : la fenêtre de l'entreprise, resserrée au premier
    jour qui attend un rapport (`premier_jour_rapport`).

    C'est la même règle que celle de `creer_journal` : sans elle, la préparation proposait des
    jours que l'enregistrement refusait ensuite (« avant l'enregistrement du chantier »).
    `conserver` garde les jours où l'appelant a déjà un rapport, pour qu'il puisse le rouvrir.
    """
    premier = premier_jour_rapport(projet)
    gardes = set(conserver)
    return [
        jour for jour in jours_saisissables_ouvres(reference) if jour >= premier or jour in gardes
    ]


def est_jour_ouvre_entreprise(jour: date) -> bool:
    cal = calendrier_entreprise(jour, jour)
    return cal.est_ouvre(jour)


def verifier_jour(jour: date, *, statut_actuel: str | None = None) -> None:
    """Vérifie que `jour` est un jour ouvré dans la fenêtre des 3 derniers jours ouvrés.

    Un rapport rejeté (`REJETE`) demeure modifiable et re-soumissible même au-delà de J-2 ouvré.
    """
    if statut_actuel == StatutRapport.REJETE:
        return
    ref = aujourdhui()
    if jour > ref:
        raise ErreurMetier(
            "Un rapport futur ne peut pas être saisi.",
            details={"date": "hors_fenetre_saisie"},
        )
    cal = calendrier_entreprise(ref - timedelta(days=HORIZON_RECHERCHE_CALENDRIER), ref)
    if not cal.est_ouvre(jour):
        raise ErreurMetier(
            "Aucun rapport n'est attendu un jour non ouvré du calendrier de l'entreprise.",
            details={"date": "jour_non_ouvre"},
        )
    if jour not in jours_saisissables_ouvres(ref):
        raise ErreurMetier(
            "Le rapport doit porter sur l'un des 3 derniers jours ouvrés.",
            details={"date": "hors_fenetre_saisie"},
        )


class CasesDuJournal:
    """Ce que le journal saisit, lu dans l'arbre du découpage.

    Seules les **feuilles** actives, non clôturées et non suspendues sont ouvertes à la saisie.
    Chacune se range sous son **groupe** (`Arbre.groupe`).
    """

    def __init__(self, projet, chemins=()):
        self.arbre = charger_arbre(projet, actifs_seulement=True)
        self.groupes: dict[str, Element] = {}
        self.feuilles: dict[str, Element] = {}
        self.feuilles_par_groupe: dict[str, list[Element]] = {}
        for feuille in self.arbre.feuilles():
            if feuille.cloture or self.arbre.suspendu(feuille):
                continue
            if chemins and not any(feuille.chemin.startswith(c) for c in chemins):
                continue
            groupe = self.arbre.groupe(feuille)
            self.groupes.setdefault(str(groupe.pk), groupe)
            self.feuilles[str(feuille.pk)] = feuille
            self.feuilles_par_groupe.setdefault(str(groupe.pk), []).append(feuille)

    def groupe_de(self, feuille) -> Element:
        return self.arbre.groupe(feuille)

    def mode(self, element) -> str:
        return self.arbre.mode_execution(element)

    def modes(self) -> list[str]:
        return [self.mode(g) for g in self.groupes.values()] + [
            self.mode(f) for f in self.feuilles.values()
        ]


def cases_du_journal(projet, chemins=()) -> CasesDuJournal:
    return CasesDuJournal(projet, chemins)


def verifier_auteur(rapport, utilisateur):
    if rapport.auteur_id != utilisateur.id:
        raise PermissionDenied("Seul l'auteur peut modifier ou soumettre ce rapport.")


__all__ = [
    "affectations_actives",
    "est_jour_ouvre_entreprise",
    "jours_saisissables_ouvres",
    "jours_saisissables_projet",
    "migrer_saisie_ancienne",
    "tient_fonction",
    "verifier_fonction",
]


def statut_journal(journal) -> str:
    rapport = journal.rapport
    if rapport.statut == StatutRapport.APPROUVE:
        return "APPROUVE"
    if rapport.statut == StatutRapport.SOUMIS and journal.valide_ct_le:
        return "VALIDE"
    return rapport.statut


def tracer(journal, utilisateur, action, *, avant=None, evenement="", commentaire=""):
    from apps.audit.services import journaliser

    journaliser(
        action=action,
        type_entite="JournalChantier",
        entite_id=journal.rapport_id,
        utilisateur_id=utilisateur.id,
        valeur_avant=avant,
        valeur_apres={
            "statut": statut_journal(journal),
            "evenement": evenement,
            "commentaire": commentaire,
        },
    )


def _extraire_nombre_et_unite(valeur_brute) -> tuple[float | None, str]:
    if isinstance(valeur_brute, int | float) and not isinstance(valeur_brute, bool):
        return float(valeur_brute), ""
    if isinstance(valeur_brute, str):
        texte = valeur_brute.strip().replace(",", ".")
        correspondance = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(.*)$", texte)
        if correspondance:
            try:
                return float(correspondance.group(1)), correspondance.group(2).strip()[:30]
            except ValueError:
                return None, ""
    return None, ""


def migrer_saisie_ancienne(existante: Mapping | None) -> dict:
    """Convertit un brouillon ou rapport historique stocké en base vers le nouveau contrat."""
    if not existante or not isinstance(existante, Mapping):
        return {}
    d = dict(existante)
    if "note_cc" in d:
        note_ancienne = d.pop("note_cc") or ""
        if not d.get("note_redacteur"):
            d["note_redacteur"] = note_ancienne

    if isinstance(d.get("meteo"), Mapping):
        meteo = d["meteo"]
        d["meteo"] = {
            "matin": meteo.get("matin") or "",
            "apres_midi": meteo.get("apres_midi") or "",
            "conditions": meteo.get("conditions") or "",
        }

    if isinstance(d.get("arret"), Mapping):
        arret = dict(d["arret"])
        if arret.get("motif") not in MOTIFS_ARRET:
            ancienne_precision = arret.get("precision") or ""
            arret["motif"] = "AUTRE"
            arret["precision"] = ancienne_precision or "Arrêt de chantier"
        d["arret"] = arret

    # Fusionner d'éventuelles lignes historiques de `production` dans `activites`
    production_ancienne = d.pop("production", None) or []
    activites_actuelles = [dict(a) for a in (d.get("activites") or []) if isinstance(a, Mapping)]
    par_activite = {
        str(a.get("activite_id")): a for a in activites_actuelles if a.get("activite_id")
    }
    for prod in production_ancienne:
        if not isinstance(prod, Mapping) or not prod.get("activite_id"):
            continue
        aid = str(prod["activite_id"])
        q = prod.get("quantite_jour") or 0
        if aid in par_activite:
            par_activite[aid]["quantite_jour"] = (par_activite[aid].get("quantite_jour") or 0) + q
        else:
            nouvelle = {
                "activite_id": aid,
                "equipe_ids": [],
                "quantite_jour": q,
                "pourcentage_jour": None,
                "jalon_atteint": False,
                "localisation": "",
                "observation": "",
            }
            activites_actuelles.append(nouvelle)
            par_activite[aid] = nouvelle
    for a in activites_actuelles:
        a.pop("avancement_estime", None)
        a.setdefault("equipe_ids", [])
        a.setdefault("pourcentage_jour", None)
        a.setdefault("jalon_atteint", False)
        a.setdefault("localisation", "")
        a.setdefault("observation", "")
    d["activites"] = activites_actuelles

    d.pop("effectifs", None)
    d.pop("presence_sous_traitant", None)

    # Ancien blocage unique -> liste `blocages`
    ancien_blocage = d.pop("blocage", None)
    if "blocages" not in d:
        if isinstance(ancien_blocage, Mapping) and ancien_blocage.get("niveau") in (
            "MINEUR",
            "SIGNIFICATIF",
            "BLOQUANT",
        ):
            d["blocages"] = [
                {
                    "cle": "blc-historique-1",
                    "blocage_id": None,
                    "element_id": None,
                    "titre": "",
                    "niveau": ancien_blocage["niveau"],
                    "nature": ancien_blocage.get("nature") or "",
                    "description": ancien_blocage.get("description") or "",
                    "impact": ancien_blocage.get("impact") or "",
                }
            ]
        else:
            d["blocages"] = []

    livraisons = []
    for liv in d.get("livraisons") or []:
        if not isinstance(liv, Mapping):
            continue
        copie = dict(liv)
        q_val, u_val = _extraire_nombre_et_unite(copie.get("quantite"))
        copie["quantite"] = q_val
        if not copie.get("unite"):
            copie["unite"] = u_val
        copie.setdefault("fournisseur", "")
        copie.setdefault("designation", "")
        copie.setdefault("bon_livraison", "")
        copie.setdefault("heure", "")
        copie.setdefault("conformite", "CONFORME")
        copie.setdefault("observation", "")
        livraisons.append(copie)
    d["livraisons"] = livraisons

    besoins = []
    for bes in d.get("besoins") or []:
        if not isinstance(bes, Mapping):
            continue
        copie = dict(bes)
        q_val, u_val = _extraire_nombre_et_unite(copie.get("quantite"))
        copie["quantite"] = q_val
        if not copie.get("unite"):
            copie["unite"] = u_val
        copie.setdefault("nature", "URGENT")
        copie.setdefault("designation", "")
        copie.setdefault("observation", "")
        besoins.append(copie)
    d["besoins"] = besoins

    equipements = []
    for idx, eq in enumerate(d.get("equipements") or [], start=1):
        if not isinstance(eq, Mapping):
            continue
        copie = dict(eq)
        util_texte = copie.pop("utilisation", None)
        if util_texte and not copie.get("usage"):
            h_val, reste = _extraire_nombre_et_unite(util_texte)
            if copie.get("heures_utilisation") is None and h_val is not None and h_val <= 24:
                copie["heures_utilisation"] = h_val
            copie["usage"] = reste or str(util_texte)[:200]
        copie.setdefault("cle", f"eq-{idx}")
        copie.setdefault("designation", "")
        copie.setdefault("reference", "")
        copie.setdefault("propriete", "")
        copie.setdefault("heures_utilisation", None)
        copie.setdefault("usage", "")
        copie.setdefault("operateur", "")
        copie.setdefault("etat", "")
        copie.setdefault("duree_arret", None)
        copie.setdefault("observation", "")
        equipements.append(copie)
    d["equipements"] = equipements

    incidents = []
    for idx, inc in enumerate(d.get("incidents") or [], start=1):
        if not isinstance(inc, Mapping):
            continue
        copie = dict(inc)
        copie.setdefault("cle", f"inc-{idx}")
        if copie.get("nature") not in NATURES_INCIDENT:
            copie["nature"] = "EVENEMENT_PARTICULIER"
        copie.setdefault("type", "")
        copie.setdefault("heure_debut", "")
        copie.setdefault("heure_fin", "")
        copie.setdefault("gravite", "")
        decide = copie.get("decide_par") or ""
        copie["decide_par"] = DECIDEUR_ANCIEN_VERS_NOUVEAU.get(decide, decide)
        copie.setdefault("description", "")
        copie.setdefault("action_entreprise", "")
        incidents.append(copie)
    d["incidents"] = incidents

    photos = []
    for idx, ph in enumerate(d.get("photos") or [], start=1):
        if isinstance(ph, Mapping):
            copie = dict(ph)
            copie.setdefault("cle", f"ph-{idx}")
            copie.setdefault("element_id", None)
            copie.setdefault("legende", "")
            copie.setdefault("horodatage_utc", "")
            copie.setdefault("latitude", None)
            copie.setdefault("longitude", None)
            photos.append(copie)
    d["photos"] = photos

    previsions = []
    for pr in d.get("previsions") or []:
        if isinstance(pr, Mapping):
            copie = dict(pr)
            copie.setdefault("activite_id", None)
            copie.setdefault("equipe_id", None)
            previsions.append(copie)
    d["previsions"] = previsions

    pieces = []
    for pj in d.get("pieces_jointes") or []:
        if isinstance(pj, Mapping):
            pieces.append(dict(pj))
    d["pieces_jointes"] = pieces

    d.setdefault("heure_debut", "")
    d.setdefault("heure_fin", "")
    d.setdefault("arret", None)
    if not isinstance(d.get("meteo"), Mapping):
        d["meteo"] = {"matin": "", "apres_midi": "", "conditions": ""}
    d.setdefault("equipes", [])
    d.setdefault("lots_travailles", [])
    d.setdefault("materiaux", [])
    d.setdefault("note_redacteur", "")

    champs_connus = set(SaisieJournalSerializer().fields)
    return {k: v for k, v in d.items() if k in champs_connus}


def valider_media(ligne, *, photo=False):
    """Uniquement les fichiers embarqués du formulaire ; aucun téléchargement distant."""
    fichier = ligne["fichier"]
    try:
        entete, contenu = fichier.split(",", 1)
        if not entete.startswith("data:") or not entete.endswith(";base64"):
            raise ValueError
        mime = entete[5:-7]
        octets = base64.b64decode(contenu, validate=True)
    except (ValueError, binascii.Error):
        raise ValidationError(
            {"fichier": "Un fichier data: MIME;base64 valide est requis."}
        ) from None
    limite = TAILLE_MAX_PHOTO_OCTETS if photo else TAILLE_MAX_PIECE_OCTETS
    limite_mio = 2 if photo else 5
    if not octets or len(octets) > limite:
        raise ValidationError(
            {"fichier": f"Le fichier doit peser entre 1 octet et {limite_mio} Mio."}
        )
    if photo:
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            raise ValidationError({"fichier": "Format photo non accepté."})
        try:
            with Image.open(io.BytesIO(octets)) as image:
                if image.width * image.height > 25_000_000 or Image.MIME.get(image.format) != mime:
                    raise ValueError
                image.verify()
        except (ValueError, OSError, Image.DecompressionBombError):
            raise ValidationError({"fichier": "Image invalide ou trop grande."}) from None
        if bool(ligne["latitude"] is None) != bool(ligne["longitude"] is None):
            raise ValidationError(
                {"longitude": "Latitude et longitude doivent être fournies ensemble."}
            )
    else:
        if mime != ligne["type_mime"] or len(octets) != ligne["taille"]:
            raise ValidationError(
                {"fichier": "Le type MIME ou la taille ne correspond pas au contenu."}
            )
        extensions = {
            "application/pdf": (".pdf",),
            "application/msword": (".doc",),
            "application/vnd.ms-excel": (".xls",),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx",),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (".xlsx",),
        }
        if mime not in extensions or not ligne["nom"].lower().endswith(extensions[mime]):
            raise ValidationError({"nom": "L'extension du document ne correspond pas à son type."})
        if mime == "application/pdf" and not octets.startswith(b"%PDF-"):
            raise ValidationError({"fichier": "Contenu PDF invalide."})
        if mime in ("application/msword", "application/vnd.ms-excel") and not octets.startswith(
            bytes.fromhex("D0CF11E0A1B11AE1")
        ):
            raise ValidationError({"fichier": "Document Office invalide."})
        if mime.endswith(".document") or mime.endswith(".sheet"):
            import zipfile

            try:
                with zipfile.ZipFile(io.BytesIO(octets)) as archive:
                    attendu = (
                        "word/document.xml" if mime.endswith(".document") else "xl/workbook.xml"
                    )
                    if (
                        attendu not in archive.namelist()
                        or "[Content_Types].xml" not in archive.namelist()
                    ):
                        raise ValueError
            except (ValueError, zipfile.BadZipFile):
                raise ValidationError({"fichier": "Document Office Open XML invalide."}) from None


def normaliser_saisie(data, *, projet, jour, utilisateur, existante=None, chemins=()):
    if not isinstance(data, Mapping):
        raise ValidationError("Un objet JSON est requis.")
    base_existante = migrer_saisie_ancienne(existante)
    fusion = {**base_existante, **data}
    if isinstance(data.get("meteo"), Mapping):
        fusion["meteo"] = {**base_existante.get("meteo", {}), **data["meteo"]}
    fusion.setdefault("projet_id", str(projet.id))
    fusion.setdefault("date", jour.isoformat())

    serializer = SaisieJournalSerializer(data=fusion)
    serializer.is_valid(raise_exception=True)
    saisie = dict(serializer.data)

    if saisie["projet_id"] != str(projet.id) or saisie["date"] != jour.isoformat():
        raise ValidationError("Le projet et la date du rapport sont immuables.")

    from apps.chantier.serializers import journal as contrats

    nested_meteo = contrats.MeteoSerializer(data=saisie["meteo"])
    nested_meteo.is_valid(raise_exception=True)
    saisie["meteo"] = dict(nested_meteo.data)

    if (
        saisie["arret"]
        and saisie["arret"]["motif"] == "INTEMPERIES"
        and not saisie["meteo"].get("conditions")
    ):
        saisie["meteo"]["conditions"] = "ARRET"

    cases = cases_du_journal(projet, chemins)
    lots = cases.groupes
    equipes = equipes_du_journal(cases, jour)
    equipes_par_id = {e["equipe_id"]: e for e in equipes}
    controler_equipes(saisie, equipes)

    activites = cases.feuilles
    vus_lots: set[str] = set()
    lots_normalises = []
    for ligne in saisie["lots_travailles"]:
        identifiant = str(ligne["lot_id"])
        if identifiant not in lots or identifiant in vus_lots:
            raise ValidationError({"lots_travailles": "Lot extérieur, inactif ou dupliqué."})
        vus_lots.add(identifiant)
        lots_normalises.append({"lot_id": identifiant, "observation": ligne["observation"]})

    lignes_vues: set[str] = set()
    for ligne in saisie["activites"]:
        act_id = str(ligne["activite_id"])
        ligne["activite_id"] = act_id
        activite = activites.get(act_id)
        if activite is None or act_id in lignes_vues:
            raise ValidationError({"activites": "Feuille extérieure, clôturée ou dupliquée."})
        id_groupe = str(cases.groupe_de(activite).pk)
        if id_groupe not in vus_lots:
            vus_lots.add(id_groupe)
            lots_normalises.append({"lot_id": id_groupe, "observation": ""})
        lignes_vues.add(act_id)
    saisie["lots_travailles"] = lots_normalises

    ids_arbre = set(cases.arbre.par_id.keys())
    for section in ("blocages", "photos"):
        for ligne in saisie[section]:
            elem_id = ligne.get("element_id")
            if elem_id is not None:
                try:
                    elem_uuid = UUID(str(elem_id))
                except ValueError:
                    raise ValidationError({section: "Identifiant de case invalide."}) from None
                if elem_uuid not in ids_arbre:
                    raise ValidationError({section: "La case désignée n'appartient pas au projet."})
                ligne["element_id"] = str(elem_uuid)

    for ligne in saisie["blocages"]:
        if ligne.get("blocage_id") is not None:
            ligne["blocage_id"] = str(ligne["blocage_id"])

    for ligne in saisie["previsions"]:
        aid = ligne.get("activite_id")
        if aid is not None:
            aid_str = str(aid)
            feuille = activites.get(aid_str)
            if feuille is None:
                raise ValidationError(
                    {"previsions": "La tâche prévue n'appartient pas au périmètre."}
                )
            ligne["activite_id"] = aid_str
            if not ligne["activite"].strip():
                ligne["activite"] = feuille.libelle
        eid = ligne.get("equipe_id")
        if eid is not None:
            eid_str = str(eid)
            equipe = equipes_par_id.get(eid_str)
            if equipe is None:
                raise ValidationError(
                    {"previsions": "L'équipe prévue n'appartient pas au périmètre."}
                )
            ligne["equipe_id"] = eid_str
            if not ligne["equipe"].strip():
                ligne["equipe"] = equipe["nom"]

    for section in ("incidents", "blocages", "photos", "pieces_jointes"):
        cles = [ligne["cle"] for ligne in saisie[section] if ligne.get("cle")]
        if len(cles) != len(set(cles)):
            raise ValidationError({section: "Les clés de ligne doivent être uniques."})

    try:
        json.dumps(saisie, allow_nan=False)
    except ValueError:
        raise ValidationError("Les nombres doivent être finis.") from None

    for ligne in saisie["photos"]:
        valider_media(ligne, photo=True)
    for ligne in saisie["pieces_jointes"]:
        valider_media(ligne)
    if len(json.dumps(saisie).encode()) > TAILLE_MAX_RAPPORT_OCTETS:
        raise ValidationError("Le rapport dépasse la taille maximale autorisée (36 Mio).")
    return saisie


def _pourcentages_acquis_veille(projet, jour: date) -> dict[str, float]:
    """Pour chaque feuille en mode POURCENTAGE, le maximum déjà approuvé avant `jour`."""
    acquis: dict[str, float] = {}
    for elem_id, pct in Element.objects.filter(
        projet=projet, mode_mesure=ModeMesure.POURCENTAGE, supprime_le__isnull=True
    ).values_list("pk", "pourcentage_declare"):
        if pct is not None:
            acquis[str(elem_id)] = float(pct)
    precedents = JournalChantier.objects.filter(
        rapport__projet=projet,
        rapport__date_rapport__lt=jour,
        rapport__supprime_le__isnull=True,
        rapport__statut=StatutRapport.APPROUVE,
    ).values_list("saisie", flat=True)
    for s_prec in precedents:
        for ligne in (s_prec or {}).get("activites", []):
            aid = str(ligne.get("activite_id") or "")
            p = ligne.get("pourcentage_jour")
            if aid and p is not None:
                acquis[aid] = max(acquis.get(aid, 0.0), float(p))
    return acquis


def valider_soumission(saisie, projet, chemins=()):
    erreurs: dict[str, list[str]] = {}

    def exiger(condition, cle, message):
        if not condition:
            erreurs.setdefault(cle, []).append(message)

    def horaire(valeur):
        try:
            return time.fromisoformat(valeur) if valeur and len(valeur) == 5 else None
        except ValueError:
            return None

    exiger(
        all(saisie["meteo"].get(k) for k in ("matin", "apres_midi", "conditions")),
        "meteo",
        "Matin, après-midi et conditions météo sont requis.",
    )

    debut, fin = horaire(saisie["heure_debut"]), horaire(saisie["heure_fin"])
    jour = date.fromisoformat(saisie["date"])

    if saisie["arret"]:
        exiger(
            saisie["arret"]["motif"] != "AUTRE" or bool(saisie["arret"]["precision"].strip()),
            "arret",
            "Préciser le motif de l'arrêt.",
        )
        if saisie["heure_debut"] or saisie["heure_fin"]:
            exiger(
                debut is not None and fin is not None and fin > debut,
                "heure_fin",
                "Lorsque les horaires sont renseignés, la fin doit être postérieure au début.",
            )
        exiger(
            not saisie["activites"],
            "activites",
            "Une journée d'arrêt complet ne déclare pas d'avancement de travaux.",
        )
        exiger(
            not any(ligne.get("presents") for ligne in saisie["equipes"]),
            "equipes",
            "Une journée d'arrêt complet ne pointe pas d'équipe au travail.",
        )
    else:
        exiger(debut is not None, "heure_debut", "Un horaire HH:MM est requis.")
        exiger(
            fin is not None and (debut is None or fin > debut),
            "heure_fin",
            "La fin doit être postérieure au début.",
        )
        exiger(
            len((saisie.get("note_redacteur") or "").strip()) >= 10,
            "note_redacteur",
            "La synthèse de fin de journée doit comporter au moins 10 caractères.",
        )

        cases = cases_du_journal(projet, chemins)
        equipes = equipes_du_journal(cases, jour)
        pct_veille = _pourcentages_acquis_veille(projet, jour)

        lignes_ayant_avance: list[tuple[dict, str]] = []
        groupes_par_activite: dict[str, str] = {}

        for ligne in saisie["activites"]:
            act_id = str(ligne["activite_id"])
            feuille = cases.feuilles.get(act_id)
            if feuille is None:
                continue
            groupes_par_activite[act_id] = str(cases.groupe_de(feuille).pk)
            mode = feuille.mode_mesure or ModeMesure.QUANTITE
            a_avance = False
            if mode == ModeMesure.POURCENTAGE:
                pct = ligne.get("pourcentage_jour")
                exiger(
                    pct is not None,
                    "activites",
                    f"{feuille.libelle} : le pourcentage cumulé est requis.",
                )
                acquis = pct_veille.get(act_id, 0.0)
                if pct is not None:
                    exiger(
                        pct >= acquis,
                        "activites",
                        f"{feuille.libelle} : le pourcentage ({pct} %) ne peut pas être inférieur "
                        f"au cumul acquis ({acquis} %).",
                    )
                    a_avance = pct > acquis
            elif mode == ModeMesure.JALON:
                a_avance = bool(ligne.get("jalon_atteint"))
            else:
                q_jour = ligne.get("quantite_jour")
                exiger(
                    q_jour is not None,
                    "activites",
                    f"{feuille.libelle} : la quantité réalisée du jour est requise.",
                )
                a_avance = (q_jour or 0) > 0

            if a_avance:
                lignes_ayant_avance.append((ligne, feuille.libelle))

        exiger_equipes(saisie, equipes, lignes_ayant_avance, exiger)

        ids_avancees = {str(item["activite_id"]) for item, _ in lignes_ayant_avance}
        for point in saisie["lots_travailles"]:
            lot_id = str(point["lot_id"])
            feuilles_lot = [
                item
                for item in saisie["activites"]
                if groupes_par_activite.get(str(item["activite_id"])) == lot_id
            ]
            avance_lot = any(str(item["activite_id"]) in ids_avancees for item in feuilles_lot)
            obs_feuille = any(
                bool((item.get("observation") or "").strip()) for item in feuilles_lot
            )
            exiger(
                avance_lot or obs_feuille or bool((point.get("observation") or "").strip()),
                "lots_travailles",
                "Une observation est requise lorsqu'un lot déclaré n'a pas avancé.",
            )

    # Règles communes aux rubriques renseignées (journée normale ou journée d'arrêt)
    for ligne in saisie["materiaux"]:
        exiger(
            bool(ligne["designation"].strip())
            and bool(ligne["unite"].strip())
            and ligne["quantite_consommee"] is not None,
            "materiaux",
            "Désignation, unité et quantité consommée sont requises.",
        )
    for ligne in saisie["livraisons"]:
        exiger(
            bool(ligne["fournisseur"].strip())
            and bool(ligne["designation"].strip())
            and (ligne["quantite"] or 0) > 0
            and bool(ligne["unite"].strip())
            and bool(ligne["conformite"]),
            "livraisons",
            "Fournisseur, désignation, quantité (> 0), unité et conformité sont requis.",
        )
        exiger(
            ligne["conformite"] == "CONFORME" or bool(ligne["observation"].strip()),
            "livraisons",
            "Motiver une livraison partielle ou non conforme.",
        )
    for ligne in saisie["besoins"]:
        exiger(bool(ligne["designation"].strip()), "besoins", "La désignation est requise.")
    for ligne in saisie["equipements"]:
        exiger(
            bool(ligne["designation"].strip()) and bool(ligne["propriete"]) and bool(ligne["etat"]),
            "equipements",
            "Désignation, propriété et état sont requis.",
        )
        if ligne["etat"] == "BON":
            exiger(
                ligne["heures_utilisation"] is not None,
                "equipements",
                "Indiquer les heures d'utilisation de l'équipement.",
            )
        else:
            exiger(
                ligne["duree_arret"] is not None and bool(ligne["observation"].strip()),
                "equipements",
                "Préciser la durée et le motif d'immobilisation ou de panne.",
            )
    for ligne in saisie["incidents"]:
        gravite_requise = ligne["nature"] != "VISITE_INSTRUCTION"
        exiger(
            len(ligne["description"].strip()) >= 20
            and bool(ligne["decide_par"])
            and bool(ligne["type"])
            and (not gravite_requise or bool(ligne["gravite"])),
            "incidents",
            "Décrire l'événement en 20 caractères avec catégorie, décideur et gravité.",
        )
        if ligne["heure_debut"] or ligne["heure_fin"]:
            d_inc, f_inc = horaire(ligne["heure_debut"]), horaire(ligne["heure_fin"])
            exiger(
                d_inc is not None and f_inc is not None and f_inc >= d_inc,
                "incidents",
                "Les horaires de l'événement sont incohérents.",
            )
    for ligne in saisie["blocages"]:
        exiger(
            bool(ligne["nature"])
            and len(ligne["description"].strip()) >= 20
            and bool(ligne["impact"].strip()),
            "blocages",
            "Chaque blocage exige nature, description (20 car. min.) et impact.",
        )
    for ligne in saisie["photos"]:
        exiger(bool(ligne["legende"].strip()), "photos", "La légende est requise sur chaque photo.")
    for ligne in saisie["previsions"]:
        exiger(
            bool(ligne["activite"].strip()) and bool(ligne["objectif"].strip()),
            "previsions",
            "La tâche et l'objectif sont requis pour chaque prévision.",
        )

    if erreurs:
        raise RapportIncomplet("Le rapport est incomplet pour être soumis.", details=erreurs)


def _synchroniser_blocages_du_journal(journal, utilisateur) -> None:
    """Crée ou met à jour les entrées `Blocage` du suivi opérationnel sans doublon au rejet."""
    saisie = journal.saisie
    projet = journal.rapport.projet
    modifie = False
    for ligne in saisie.get("blocages", []):
        severite = SEVERITE_BLOCAGE_PAR_NIVEAU.get(ligne["niveau"], SeveriteBlocage.MINEUR)
        desc = ligne["description"].strip()
        impact = (ligne.get("impact") or "").strip()
        description_complete = f"{desc}\nImpact : {impact}" if impact else desc
        titre = (ligne.get("titre") or "").strip() or desc[:140]
        element = None
        if ligne.get("element_id"):
            element = Element.objects.filter(
                pk=ligne["element_id"], projet=projet, supprime_le__isnull=True
            ).first()

        existant = None
        if ligne.get("blocage_id"):
            existant = Blocage.objects.filter(
                pk=ligne["blocage_id"], projet=projet, supprime_le__isnull=True
            ).first()

        if existant is not None:
            modifier_blocage(
                blocage=existant,
                modifie_par=utilisateur,
                titre=titre,
                description=description_complete,
                severite=severite,
            )
            if existant.element_id != (element.id if element else None):
                existant.element = element
                existant.save(update_fields=["element", "modifie_le"])
        else:
            cree = creer_blocage(
                projet=projet,
                element=element,
                titre=titre,
                description=description_complete,
                severite=severite,
                auteur=utilisateur,
                cree_par=utilisateur,
            )
            ligne["blocage_id"] = str(cree.id)
            modifie = True

    if modifie:
        journal.saisie = saisie


def _nb_blocages_critiques(saisie: dict) -> int:
    return sum(1 for b in saisie.get("blocages", []) if b.get("niveau") == "BLOQUANT")


@transaction.atomic
def creer_journal(*, projet, utilisateur, jour, data):
    verifier_jour(jour)
    projet = get_object_or_404(Projet.objects.select_for_update(), pk=projet.pk)
    if jour < premier_jour_rapport(projet):
        raise ErreurMetier(
            "Aucun rapport n'est attendu avant l'enregistrement du chantier sur la plateforme.",
            details={"date": "avant_enregistrement_projet"},
        )
    verifier_statut_projet_pour_ecriture(projet, action="NOUVEAU_RAPPORT")
    redacteur = verifier_fonction(projet, utilisateur, REDIGER)
    saisie = normaliser_saisie(
        data, projet=projet, jour=jour, utilisateur=utilisateur, chemins=redacteur.chemins
    )
    if RapportJournalier.objects.filter(
        projet=projet, auteur=utilisateur, date_rapport=jour
    ).exists():
        raise RapportDejaExistant(
            "Vous avez déjà un rapport sur ce chantier à cette date."
        ) from None
    try:
        with transaction.atomic():
            rapport = RapportJournalier.objects.create(
                projet=projet,
                date_rapport=jour,
                auteur=utilisateur,
                cree_par=utilisateur,
                statut=StatutRapport.BROUILLON,
                soumis_le=None,
                effectif_present=effectif_present(saisie),
                observations=saisie["note_redacteur"],
                blocages_critiques=_nb_blocages_critiques(saisie),
            )
            journal = JournalChantier.objects.create(
                rapport=rapport,
                saisie=saisie,
                perimetre_ids=list(redacteur.perimetre_ids),
                cree_par=utilisateur,
            )
    except IntegrityError:
        raise RapportDejaExistant(
            "Vous avez déjà un rapport sur ce chantier à cette date."
        ) from None
    tracer(journal, utilisateur, ActionAudit.CREATION, evenement="BROUILLON_CREE")
    return journal


def verrouiller(journal):
    rapport = get_object_or_404(
        RapportJournalier.objects.select_for_update(), pk=journal.rapport_id
    )
    journal = get_object_or_404(JournalChantier.objects.select_for_update(), pk=journal.pk)
    journal.rapport = rapport
    return journal


def enregistrer(journal, utilisateur, data):
    rapport = journal.rapport
    verifier_auteur(rapport, utilisateur)
    if rapport.statut not in (StatutRapport.BROUILLON, StatutRapport.REJETE):
        raise RapportNonModifiable("Un rapport soumis ne peut plus être modifié.")
    verifier_jour(rapport.date_rapport, statut_actuel=rapport.statut)
    verifier_statut_projet_pour_ecriture(rapport.projet, action="NOUVEAU_RAPPORT")
    ancienne_saisie = journal.saisie
    journal.saisie = normaliser_saisie(
        data,
        projet=rapport.projet,
        jour=rapport.date_rapport,
        utilisateur=utilisateur,
        existante=journal.saisie,
        chemins=chemins_des_cases(journal.perimetre_ids),
    )
    journal.save(update_fields=["saisie", "modifie_le"])
    rapport.effectif_present = effectif_present(journal.saisie)
    rapport.observations = journal.saisie["note_redacteur"]
    rapport.blocages_critiques = _nb_blocages_critiques(journal.saisie)
    rapport.save(
        update_fields=["effectif_present", "observations", "blocages_critiques", "modifie_le"]
    )
    if ancienne_saisie != journal.saisie:
        tracer(
            journal,
            utilisateur,
            ActionAudit.MODIFICATION,
            avant={
                "champs_modifies": [
                    cle
                    for cle in journal.saisie
                    if (ancienne_saisie or {}).get(cle) != journal.saisie[cle]
                ]
            },
            evenement="BROUILLON_ENREGISTRE",
        )
    return journal


@transaction.atomic
def modifier_journal(*, journal, utilisateur, data):
    return enregistrer(verrouiller(journal), utilisateur, data)


@transaction.atomic
def soumettre_journal(*, journal, utilisateur, data):
    from apps.chantier.selectors.journal import contexte_projet

    journal = verrouiller(journal)
    avant = {"statut": statut_journal(journal)}
    list(
        Element.objects.filter(projet=journal.rapport.projet)
        .select_for_update()
        .order_by("id")
        .values_list("id", flat=True)
    )
    journal = enregistrer(journal, utilisateur, data)
    rapport = journal.rapport
    chemins = chemins_des_cases(journal.perimetre_ids)
    valider_soumission(journal.saisie, rapport.projet, chemins)
    _synchroniser_blocages_du_journal(journal, utilisateur)
    journal.photographie = contexte_projet(
        rapport.projet, rapport.date_rapport, chemins=chemins, auteur=utilisateur
    )
    rapport.statut = StatutRapport.SOUMIS
    rapport.soumis_le = timezone.now()
    rapport.valide_par = None
    rapport.valide_le = None
    rapport.commentaire_validation = ""
    rapport.blocages_critiques = _nb_blocages_critiques(journal.saisie)
    rapport.save()
    signatures.figer_signataires(journal)
    signatures.reevaluer(journal)
    journal.save()
    declencher_recalcul_sante(
        projet_id=rapport.projet_id,
        declencheur_type="RAPPORT_SOUMISSION",
        declencheur_id=rapport.id,
    )
    tracer(journal, utilisateur, ActionAudit.SIGNATURE, avant=avant, evenement="SOUMISSION")
    return journal


@transaction.atomic
def signer_journal(*, journal, utilisateur, etape, commentaire=""):
    """Signature de l'étape en cours (`VALIDATION` ou `APPROBATION`, avec alias `CT` / `CP`)."""
    journal = verrouiller(journal)
    verifier_statut_projet_pour_ecriture(journal.rapport.projet)
    attendu = statut_journal(journal)
    cible_etape = (
        signatures.VALIDATION if etape in ("CT", signatures.VALIDATION) else signatures.APPROBATION
    )
    signatures.signer(journal, utilisateur, cible_etape, commentaire)
    journal.save()
    tracer(
        journal,
        utilisateur,
        ActionAudit.SIGNATURE,
        avant={"statut": attendu},
        evenement=f"SIGNATURE_{cible_etape}",
        commentaire=commentaire,
    )
    return journal


@transaction.atomic
def rejeter_journal(*, journal, utilisateur, motif):
    journal = verrouiller(journal)
    statut = statut_journal(journal)
    if statut not in ("SOUMIS", "VALIDE"):
        raise ErreurMetier("Seul un rapport soumis ou validé peut être rejeté.")
    if not signatures.peut_refuser(journal, utilisateur):
        raise PermissionDenied("Vous n'êtes pas attendu pour signer ce rapport.")
    verifier_statut_projet_pour_ecriture(journal.rapport.projet)
    if len(motif.strip()) < 20:
        raise ErreurMetier("Le motif de rejet doit comporter au moins 20 caractères.")
    rapport = journal.rapport
    rapport.statut = StatutRapport.REJETE
    rapport.commentaire_validation = motif.strip()
    rapport.valide_par = utilisateur
    rapport.valide_le = timezone.now()
    rapport.save()
    tracer(
        journal,
        utilisateur,
        ActionAudit.VALIDATION,
        avant={"statut": statut},
        evenement="REJET",
        commentaire=motif.strip(),
    )
    return journal


@transaction.atomic
def supprimer_brouillon(*, journal, utilisateur):
    journal = verrouiller(journal)
    verifier_auteur(journal.rapport, utilisateur)
    verifier_statut_projet_pour_ecriture(journal.rapport.projet)
    if journal.rapport.statut != StatutRapport.BROUILLON:
        raise ErreurMetier("Seuls les brouillons peuvent être supprimés.")
    journal.rapport.supprime_le = timezone.now()
    journal.rapport.supprime_par = utilisateur
    journal.rapport.save(update_fields=["supprime_le", "supprime_par", "modifie_le"])
    journal.delete(utilisateur=utilisateur)
    tracer(journal, utilisateur, ActionAudit.SUPPRESSION, evenement="BROUILLON_SUPPRIME")


@transaction.atomic
def alerter_journal(*, journal, utilisateur, data):
    journal = verrouiller(journal)
    verifier_auteur(journal.rapport, utilisateur)
    verifier_statut_projet_pour_ecriture(journal.rapport.projet)
    if statut_journal(journal) not in ("BROUILLON", "REJETE"):
        raise RapportNonModifiable()
    alerte, creee = AlerteJournal.objects.get_or_create(
        journal=journal, cle=data["cle"], defaults={**data, "cree_par": utilisateur}
    )
    if not creee and alerte.type != data["type"]:
        raise ErreurMetier("Cette clé identifie déjà un autre type d'alerte.")
    if creee:
        chemins = chemins_des_cases(journal.perimetre_ids)
        projet = journal.rapport.projet
        destinataires = {
            t.utilisateur.pk
            for permission in (VALIDER, APPROUVER)
            for t in titulaires(projet, permission)
            if t.concerne(chemins)
        }
        alerte.destinataires.set(destinataires)
        tracer(
            journal,
            utilisateur,
            ActionAudit.CREATION,
            evenement=data["type"],
            commentaire=data["description"],
        )
    return alerte
