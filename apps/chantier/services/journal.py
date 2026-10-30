"""Écritures atomiques du journal : brouillon, soumission et signatures."""

import base64
import binascii
import io
import json
from collections.abc import Mapping
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.chantier.models import AlerteJournal, JournalChantier, RapportJournalier
from apps.chantier.serializers.journal import SaisieJournalSerializer
from apps.chantier.services import signatures
from apps.chantier.services.equipes_journal import (
    cle_production,
    controler_equipes,
    effectif_present,
    equipes_du_journal,
    exiger_equipes,
    feuilles_sans_equipe,
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
from apps.core.enums import ActionAudit, ModeExecution, StatutRapport
from apps.core.exceptions import ErreurMetier, RapportDejaExistant, RapportNonModifiable
from apps.projets.models import Element, Projet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture
from apps.projets.services.referentiels import mode_base, table_modes_execution
from apps.projets.services.sante_declencheur import declencher_recalcul_sante


def aujourdhui():
    return timezone.localdate(timezone=ZoneInfo("Africa/Abidjan"))


def premier_jour_rapport(projet):
    """Le premier jour qui attend un rapport : début du chantier, mais **jamais avant son
    enregistrement sur la plateforme** (décision du 16/10/2026). Un chantier saisi avec une
    date de début passée n'a pas de rapports à rattraper sur ce passé.
    """
    debut = projet.date_debut_reelle or projet.date_debut_prevue
    enregistre = timezone.localdate(projet.cree_le, timezone=ZoneInfo("Africa/Abidjan"))
    return max(debut, enregistre) if debut else enregistre


def verifier_jour(jour):
    if not aujourdhui() - timedelta(days=2) <= jour <= aujourdhui():
        raise ErreurMetier(
            "Le rapport doit dater de J-2, J-1 ou J.", details={"date": "hors_fenetre_saisie"}
        )


class CasesDuJournal:
    """Ce que le journal saisit, lu dans l'arbre du découpage.

    Les **feuilles** actives et non clôturées tiennent le rôle des anciennes activités ; chacune
    se range sous son **groupe** (sa case parente, ou elle-même à la racine), qui tient celui de
    l'ancien lot. Le contrat JSON du journal garde donc `lot_id` (le groupe) et `activite_id`
    (la feuille). Le mode d'exécution est celui que la case hérite de l'arbre.

    `chemins` : la partie du projet du rédacteur (30/10/2026) ; vide, tout le projet.
    """

    def __init__(self, projet, chemins=()):
        self.arbre = charger_arbre(projet, actifs_seulement=True)
        self.groupes: dict[str, Element] = {}
        self.feuilles: dict[str, Element] = {}
        self.feuilles_par_groupe: dict[str, list[Element]] = {}
        for feuille in self.arbre.feuilles():
            if feuille.cloture:
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


__all__ = ["affectations_actives", "tient_fonction", "verifier_fonction"]


def statut_journal(journal):
    rapport = journal.rapport
    if rapport.statut == StatutRapport.APPROUVE:
        return "APPROUVE_CP"
    if rapport.statut == StatutRapport.SOUMIS and journal.valide_ct_le:
        return "VALIDE_CT"
    return rapport.statut


def tracer(journal, utilisateur, action, *, avant=None, evenement="", commentaire=""):
    """Conserve les signatures précédentes lorsqu'un rejet est corrigé."""
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
    if not octets or len(octets) > 2 * 1024 * 1024:
        raise ValidationError({"fichier": "Le fichier doit peser entre 1 octet et 2 Mio."})
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
    # PATCH conserve les sections absentes ; les objets météo/blocage sont fusionnés.
    fusion = {**(existante or {}), **data}
    for cle in ("meteo", "blocage"):
        if isinstance(data.get(cle), dict):
            fusion[cle] = {**(existante or {}).get(cle, {}), **data[cle]}
    fusion.setdefault("projet_id", str(projet.id))
    fusion.setdefault("date", jour.isoformat())
    serializer = SaisieJournalSerializer(data=fusion)
    serializer.is_valid(raise_exception=True)
    saisie = dict(serializer.data)
    from apps.core.droits import peut_voir_montants

    if "production" in data and not peut_voir_montants(utilisateur):
        anciens_prix = {
            cle_production(ligne): ligne["prix_unitaire"]
            for ligne in (existante or {}).get("production", [])
        }
        for ligne in saisie["production"]:
            if ligne["prix_unitaire"] is not None:
                raise ValidationError(
                    {"production": "Le prix exige la permission projets.voir_montants."}
                )
            # Une valeur masquée renvoyée par le formulaire ne doit pas effacer
            # le tarif déjà autorisé en base.
            ligne["prix_unitaire"] = anciens_prix.get(cle_production(ligne))
    if saisie["projet_id"] != str(projet.id) or saisie["date"] != jour.isoformat():
        raise ValidationError("Le projet et la date du rapport sont immuables.")
    # Les valeurs par défaut d'un serializer imbriqué sont appliquées explicitement.
    for cle, classe in (("meteo", "MeteoSerializer"), ("blocage", "BlocageSerializer")):
        from apps.chantier.serializers import journal as contrats

        nested = getattr(contrats, classe)(data=saisie[cle])
        nested.is_valid(raise_exception=True)
        saisie[cle] = dict(nested.data)
    cases = cases_du_journal(projet, chemins)
    lots = cases.groupes
    table_modes = table_modes_execution()
    controler_equipes(saisie, equipes_du_journal(cases, jour))
    activites = cases.feuilles
    vus = set()
    for ligne in saisie["lots_travailles"]:
        identifiant = ligne["lot_id"]
        if identifiant not in lots or identifiant in vus:
            raise ValidationError({"lots_travailles": "Lot extérieur, inactif ou dupliqué."})
        base_lot = mode_base(cases.mode(lots[identifiant]), table_modes)
        if base_lot == ModeExecution.SOUS_TRAITANCE_INFORMELLE:
            raise ValidationError(
                {"lots_travailles": "Ce lot se suit par la production des intervenants."}
            )
        vus.add(identifiant)
    for section in ("activites", "production"):
        lignes_vues = set()
        for ligne in saisie[section]:
            activite = activites.get(ligne["activite_id"])
            cle = cle_production(ligne) if section == "production" else ligne["activite_id"]
            if activite is None or cle in lignes_vues:
                raise ValidationError({section: "Activité extérieure, inactive ou dupliquée."})
            production = (
                mode_base(cases.mode(activite), table_modes)
                == ModeExecution.SOUS_TRAITANCE_INFORMELLE
            )
            if production != (section == "production"):
                raise ValidationError({section: "Le mode de suivi ne correspond pas au lot."})
            if section == "activites" and str(cases.groupe_de(activite).pk) not in vus:
                raise ValidationError({section: "L'activité doit appartenir à un lot travaillé."})
            lignes_vues.add(cle)
    for section in ("incidents", "photos", "pieces_jointes"):
        cles = [ligne["cle"] for ligne in saisie[section]]
        if len(cles) != len(set(cles)):
            raise ValidationError({section: "Les clés de ligne doivent être uniques."})
            # JSON standard : ni NaN ni Infinity, y compris dans les flottants imbriqués.
    try:
        json.dumps(saisie, allow_nan=False)
    except ValueError:
        raise ValidationError("Les nombres doivent être finis.") from None
    for ligne in saisie["photos"]:
        valider_media(ligne, photo=True)
    for ligne in saisie["pieces_jointes"]:
        valider_media(ligne)
    if len(json.dumps(saisie).encode()) > 16 * 1024 * 1024:
        raise ValidationError("Le rapport dépasse 16 Mio.")
    return saisie


def valider_soumission(saisie, projet, chemins=()):
    erreurs = {}

    def exiger(condition, cle, message):
        if not condition:
            erreurs.setdefault(cle, []).append(message)

    def horaire(valeur):
        try:
            return time.fromisoformat(valeur) if len(valeur) == 5 else None
        except ValueError:
            return None

    debut, fin = horaire(saisie["heure_debut"]), horaire(saisie["heure_fin"])
    exiger(debut is not None, "heure_debut", "Un horaire HH:MM est requis.")
    exiger(
        fin is not None and (debut is None or fin > debut),
        "heure_fin",
        "La fin doit être postérieure au début.",
    )
    exiger(
        all(saisie["meteo"].get(k) for k in ("matin", "apres_midi", "conditions")),
        "meteo",
        "Matin, après-midi et conditions sont requis.",
    )
    if saisie["arret"]:
        exiger(
            saisie["arret"]["motif"] != "AUTRE" or bool(saisie["arret"]["precision"]),
            "arret",
            "Préciser le motif de l'arrêt.",
        )
        for cle in (
            "lots_travailles",
            "activites",
            "production",
            "effectifs",
            "equipes",
            "equipements",
            "materiaux",
            "livraisons",
            "besoins",
            "incidents",
            "photos",
            "pieces_jointes",
            "previsions",
        ):
            exiger(not saisie[cle], cle, "Une journée d'arrêt ne déclare pas cette rubrique.")
        exiger(
            saisie["presence_sous_traitant"] is None,
            "presence_sous_traitant",
            "Sans objet pour une journée d'arrêt.",
        )
        exiger(
            saisie["blocage"]["niveau"] == "AUCUN",
            "blocage",
            "Sans objet pour une journée d'arrêt.",
        )
    else:
        exiger(
            len(saisie["note_cc"].strip()) >= 10,
            "note_cc",
            "La note doit comporter au moins 10 caractères.",
        )
        table_modes = table_modes_execution()
        cases = cases_du_journal(projet, chemins)
        modes = {mode_base(code, table_modes) for code in cases.modes()}
        equipes = equipes_du_journal(cases, date.fromisoformat(saisie["date"]))
        exiger_equipes(saisie, equipes, exiger)
        # Les effectifs par catégorie demeurent pour les tâches en régie sans équipe.
        if ModeExecution.REGIE in modes and feuilles_sans_equipe(
            cases, equipes, ModeExecution.REGIE
        ):
            exiger(
                bool(saisie["effectifs"]),
                "effectifs",
                "Au moins une catégorie est requise en régie.",
            )
        for ligne in saisie["effectifs"]:
            exiger(
                bool(ligne["categorie"])
                and all(ligne[k] is not None for k in ("prevus", "presents", "heures")),
                "effectifs",
                "Catégorie, prévus, présents et heures sont requis.",
            )
            absence = (
                ligne["prevus"] is not None
                and ligne["presents"] is not None
                and ligne["presents"] < ligne["prevus"]
            )
            exiger(
                not (absence or (ligne["retards"] or 0)) or bool(ligne["observation"]),
                "effectifs",
                "Une absence ou un retard exige un motif.",
            )
        points = {p["lot_id"]: p for p in saisie["lots_travailles"]}
        groupes = {
            ligne["activite_id"]: str(cases.groupe_de(cases.feuilles[ligne["activite_id"]]).pk)
            for ligne in saisie["activites"]
            if ligne["activite_id"] in cases.feuilles
        }
        for ligne in saisie["activites"]:
            exiger(ligne["quantite_jour"] is not None, "activites", "La quantité est requise.")
        for identifiant, point in points.items():
            avance = any(
                (ligne["quantite_jour"] or 0) > 0
                and groupes.get(ligne["activite_id"]) == identifiant
                for ligne in saisie["activites"]
            )
            exiger(
                avance or bool(point["observation"]),
                "lots_travailles",
                "Une observation est requise si aucune activité du lot n'a avancé.",
            )
        if ModeExecution.SOUS_TRAITANCE_INFORMELLE in modes:
            exiger(
                bool(saisie["production"]),
                "production",
                "La production est requise pour la sous-traitance informelle.",
            )
        for ligne in saisie["production"]:
            exiger(
                bool(ligne["intervenant"]) and ligne["quantite_jour"] is not None,
                "production",
                "Intervenant et quantité sont requis ; "
                "le tarif est réservé aux détenteurs des montants.",
            )
        # La ligne de l'équipe partenaire remplace la présence du sous-traitant.
        if ModeExecution.SOUS_TRAITANCE_STRUCTUREE in modes and feuilles_sans_equipe(
            cases, equipes, ModeExecution.SOUS_TRAITANCE_STRUCTUREE
        ):
            presence = saisie["presence_sous_traitant"] or {}
            exiger(
                bool(presence.get("presence")) and bool(presence.get("qualite")),
                "presence_sous_traitant",
                "Présence et qualité sont requises.",
            )
            exiger(
                presence.get("presence") == "PRESENT" or bool(presence.get("motif")),
                "presence_sous_traitant",
                "Motiver une absence ou présence partielle.",
            )
        for ligne in saisie["materiaux"]:
            exiger(
                bool(ligne["designation"])
                and bool(ligne["unite"])
                and ligne["quantite_consommee"] is not None,
                "materiaux",
                "Désignation, unité et quantité sont requises.",
            )
        for ligne in saisie["livraisons"]:
            exiger(
                all(ligne[k] for k in ("fournisseur", "designation", "quantite", "conformite")),
                "livraisons",
                "Fournisseur, désignation, quantité et conformité sont requis.",
            )
            exiger(
                ligne["conformite"] == "CONFORME" or bool(ligne["observation"]),
                "livraisons",
                "Motiver une livraison non conforme ou partielle.",
            )
        for ligne in saisie["equipements"]:
            exiger(
                all(ligne[k] for k in ("designation", "propriete", "utilisation", "etat")),
                "equipements",
                "Désignation, propriété, utilisation et état sont requis.",
            )
            exiger(
                ligne["etat"] == "BON"
                or (ligne["duree_arret"] is not None and bool(ligne["observation"])),
                "equipements",
                "Préciser la durée et le motif d'immobilisation.",
            )
        for ligne in saisie["incidents"]:
            exiger(
                len(ligne["description"]) >= 20
                and bool(ligne["gravite"])
                and bool(ligne["decide_par"])
                and bool(ligne["type"]),
                "incidents",
                "Décrire l'événement en 20 caractères, avec catégorie, gravité et décideur.",
            )
            if ligne["heure_debut"] or ligne["heure_fin"]:
                d, f = horaire(ligne["heure_debut"]), horaire(ligne["heure_fin"])
                exiger(
                    d is not None and f is not None and f >= d,
                    "incidents",
                    "Les horaires de l'événement sont incohérents.",
                )
        blocage = saisie["blocage"]
        exiger(bool(blocage["niveau"]), "blocage", "L'incidence sur le chantier est requise.")
        if blocage["niveau"] != "AUCUN":
            exiger(
                bool(blocage["nature"])
                and len(blocage["description"]) >= 20
                and bool(blocage["impact"]),
                "blocage",
                "Décrire la nature, l'incidence et le blocage (20 caractères).",
            )
        for ligne in saisie["photos"]:
            exiger(bool(ligne["legende"]), "photos", "La légende est requise.")
        for ligne in saisie["besoins"]:
            exiger(bool(ligne["designation"]), "besoins", "La désignation est requise.")
        for ligne in saisie["previsions"]:
            exiger(
                bool(ligne["activite"]) and bool(ligne["objectif"]),
                "previsions",
                "L'activité et l'objectif sont requis.",
            )
    if erreurs:
        raise ErreurMetier("Le rapport est incomplet pour être soumis.", details=erreurs)


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
    # Écrit le journal qui en a la permission sur le projet ; un rapport par rédacteur et par
    # jour, sur sa partie du projet (30/10/2026).
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
                observations=saisie["note_cc"],
                blocages_critiques=int(saisie["blocage"]["niveau"] == "BLOQUANT"),
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
    # Ordre unique : rapport puis complément, également pour les vues historiques.
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
    verifier_jour(rapport.date_rapport)
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
    # La saisie est la source de vérité, y compris pour les anciennes listes.
    rapport.effectif_present = effectif_present(journal.saisie)
    rapport.observations = journal.saisie["note_cc"]
    rapport.blocages_critiques = int(journal.saisie["blocage"]["niveau"] == "BLOQUANT")
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
                    cle for cle in journal.saisie if ancienne_saisie.get(cle) != journal.saisie[cle]
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
    # Stabiliser l'arbre (modes d'exécution) pour la validation et la photographie.
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
    journal.photographie = contexte_projet(
        rapport.projet, rapport.date_rapport, chemins=chemins, auteur=utilisateur
    )
    rapport.statut = StatutRapport.SOUMIS
    rapport.soumis_le = timezone.now()
    rapport.valide_par = None
    rapport.valide_le = None
    rapport.commentaire_validation = ""
    rapport.save()
    # Les signataires attendus sont figés maintenant ; sans validateur, l'étape est sautée.
    signatures.figer_signataires(journal)
    signatures.reevaluer(journal)
    journal.save()
    declencher_recalcul_sante(
        projet_id=rapport.projet_id,
        declencheur_type="RAPPORT_SOUMISSION",
        declencheur_id=rapport.id,
    )
    tracer(journal, utilisateur, ActionAudit.SIGNATURE, avant=avant, evenement="SOUMISSION_CC")
    return journal


@transaction.atomic
def signer_journal(*, journal, utilisateur, etape, commentaire=""):
    """Une signature de l'étape en cours ; l'étape se clôt quand tous les attendus ont signé.

    `etape` : « CT » pour la validation, « CP » pour l'approbation — les noms des routes, pas
    ceux des rôles : signe qui a la permission sur le projet (30/10/2026).
    """
    journal = verrouiller(journal)
    verifier_statut_projet_pour_ecriture(journal.rapport.projet)
    attendu = statut_journal(journal)
    signatures.signer(
        journal,
        utilisateur,
        signatures.VALIDATION if etape == "CT" else signatures.APPROBATION,
        commentaire,
    )
    journal.save()
    tracer(
        journal,
        utilisateur,
        ActionAudit.SIGNATURE,
        avant={"statut": attendu},
        evenement=f"SIGNATURE_{etape}",
        commentaire=commentaire,
    )
    return journal


@transaction.atomic
def rejeter_journal(*, journal, utilisateur, motif):
    journal = verrouiller(journal)
    statut = statut_journal(journal)
    if statut not in ("SOUMIS", "VALIDE_CT"):
        raise ErreurMetier("Seul un rapport soumis ou validé par le CT peut être rejeté.")
    # Refuse une personne attendue à l'étape en cours ; le rapport repart chez son auteur et
    # toutes les signatures sont effacées.
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
    journal.signatures = []
    journal.valide_ct_par = None
    journal.valide_ct_le = None
    journal.save()
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
    # Exception limitée aux nouveaux brouillons ; la règle historique delete()
    # reste en vigueur pour les rapports archivés et les anciennes routes.
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
        # Ceux qui signeront ce rapport : les validateurs et approbateurs de sa partie du projet.
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
