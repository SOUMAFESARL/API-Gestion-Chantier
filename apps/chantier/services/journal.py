"""Écritures atomiques du journal : brouillon, soumission et signatures."""

import base64
import binascii
import io
import json
from collections.abc import Mapping
from datetime import time, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.chantier.models import AlerteJournal, JournalChantier, RapportJournalier
from apps.chantier.serializers.journal import SaisieJournalSerializer
from apps.core.enums import ActionAudit, ModeExecution, StatutRapport
from apps.core.exceptions import ErreurMetier, RapportDejaExistant, RapportNonModifiable
from apps.projets.models import Activite, AffectationProjet, Lot, Projet
from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture
from apps.projets.services.sante_declencheur import declencher_recalcul_sante


def aujourdhui():
    return timezone.localdate(timezone=ZoneInfo("Africa/Abidjan"))


def verifier_jour(jour):
    if not aujourdhui() - timedelta(days=2) <= jour <= aujourdhui():
        raise ErreurMetier(
            "Le rapport doit dater de J-2, J-1 ou J.", details={"date": "hors_fenetre_saisie"}
        )


def affectations_actives(projet_id):
    return (
        AffectationProjet.objects.filter(
            projet_id=projet_id,
            est_actif=True,
            date_debut__lte=aujourdhui(),
            utilisateur__supprime_le__isnull=True,
            utilisateur__statut="ACTIF",
        )
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=aujourdhui()))
        .select_related("utilisateur")
    )


def lots_disponibles(projet):
    return Lot.objects.filter(projet=projet, est_actif=True).exclude(statut="CLOTURE")


def verifier_auteur(rapport, utilisateur):
    if rapport.auteur_id != utilisateur.id:
        raise PermissionDenied("Seul l'auteur peut modifier ou soumettre ce rapport.")


def verifier_signataire(journal, utilisateur, role):
    from apps.core.droits import est_dg

    if journal.rapport.auteur_id == utilisateur.id:
        raise PermissionDenied("L'auteur ne peut pas valider son propre rapport.")
        # Les permissions RBAC sont également vérifiées par la vue. Une signature
        # identifie un intervenant réel du circuit, jamais un simple droit d'édition.
    if utilisateur.is_superuser or est_dg(utilisateur):
        return
    if role == "CP" and journal.rapport.projet.chef_projet_id == utilisateur.id:
        return
    if (
        not affectations_actives(journal.rapport.projet_id)
        .filter(utilisateur=utilisateur, role_projet=role)
        .exists()
    ):
        raise PermissionDenied(f"Cette signature exige l'affectation {role} sur le chantier.")


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


def normaliser_saisie(data, *, projet, jour, utilisateur, existante=None):
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
            (ligne["activite_id"], ligne["intervenant"]): ligne["prix_unitaire"]
            for ligne in (existante or {}).get("production", [])
        }
        for ligne in saisie["production"]:
            if ligne["prix_unitaire"] is not None:
                raise ValidationError(
                    {"production": "Le prix exige la permission projets.voir_montants."}
                )
            # Une valeur masquée renvoyée par le formulaire ne doit pas effacer
            # le tarif déjà autorisé en base.
            ligne["prix_unitaire"] = anciens_prix.get((ligne["activite_id"], ligne["intervenant"]))
    if saisie["projet_id"] != str(projet.id) or saisie["date"] != jour.isoformat():
        raise ValidationError("Le projet et la date du rapport sont immuables.")
    # Les valeurs par défaut d'un serializer imbriqué sont appliquées explicitement.
    for cle, classe in (("meteo", "MeteoSerializer"), ("blocage", "BlocageSerializer")):
        from apps.chantier.serializers import journal as contrats

        nested = getattr(contrats, classe)(data=saisie[cle])
        nested.is_valid(raise_exception=True)
        saisie[cle] = dict(nested.data)
    lots = {str(ligne.id): ligne for ligne in lots_disponibles(projet)}
    activites = {
        str(a.id): a
        for a in Activite.objects.filter(lot_id__in=lots, est_actif=True).select_related("lot")
    }
    vus = set()
    for ligne in saisie["lots_travailles"]:
        identifiant = ligne["lot_id"]
        if identifiant not in lots or identifiant in vus:
            raise ValidationError({"lots_travailles": "Lot extérieur, inactif ou dupliqué."})
        if lots[identifiant].mode_execution == ModeExecution.SOUS_TRAITANCE_INFORMELLE:
            raise ValidationError(
                {"lots_travailles": "Ce lot se suit par la production des intervenants."}
            )
        vus.add(identifiant)
    for section in ("activites", "production"):
        lignes_vues = set()
        for ligne in saisie[section]:
            activite = activites.get(ligne["activite_id"])
            cle = (ligne["activite_id"], ligne.get("intervenant", ""))
            if activite is None or cle in lignes_vues:
                raise ValidationError({section: "Activité extérieure, inactive ou dupliquée."})
            production = activite.lot.mode_execution == ModeExecution.SOUS_TRAITANCE_INFORMELLE
            if production != (section == "production"):
                raise ValidationError({section: "Le mode de suivi ne correspond pas au lot."})
            if section == "activites" and str(activite.lot_id) not in vus:
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


def valider_soumission(saisie, projet):
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
        modes = set(lots_disponibles(projet).values_list("mode_execution", flat=True))
        if ModeExecution.REGIE in modes:
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
        from apps.projets.models import Activite

        activites = {
            str(a.id): a
            for a in Activite.objects.filter(
                id__in=[ligne["activite_id"] for ligne in saisie["activites"]]
            ).select_related("lot")
        }
        for ligne in saisie["activites"]:
            exiger(ligne["quantite_jour"] is not None, "activites", "La quantité est requise.")
        for identifiant, point in points.items():
            avance = any(
                (ligne["quantite_jour"] or 0) > 0
                and str(activites[ligne["activite_id"]].lot_id) == identifiant
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
        if ModeExecution.SOUS_TRAITANCE_STRUCTUREE in modes:
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
    verifier_statut_projet_pour_ecriture(projet, action="NOUVEAU_RAPPORT")
    saisie = normaliser_saisie(data, projet=projet, jour=jour, utilisateur=utilisateur)
    if RapportJournalier.objects.filter(
        projet=projet, date_rapport=jour, lot__isnull=True
    ).exists():
        raise RapportDejaExistant("Un rapport existe déjà pour ce chantier à cette date.") from None
    try:
        with transaction.atomic():
            rapport = RapportJournalier.objects.create(
                projet=projet,
                date_rapport=jour,
                auteur=utilisateur,
                cree_par=utilisateur,
                statut=StatutRapport.BROUILLON,
                soumis_le=None,
                effectif_present=sum(ligne["presents"] or 0 for ligne in saisie["effectifs"]),
                observations=saisie["note_cc"],
                blocages_critiques=int(saisie["blocage"]["niveau"] == "BLOQUANT"),
            )
            journal = JournalChantier.objects.create(
                rapport=rapport, saisie=saisie, cree_par=utilisateur
            )
    except IntegrityError:
        raise RapportDejaExistant("Un rapport existe déjà pour ce chantier à cette date.") from None
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
    )
    journal.save(update_fields=["saisie", "modifie_le"])
    # La saisie est la source de vérité, y compris pour les anciennes listes.
    rapport.effectif_present = sum(ligne["presents"] or 0 for ligne in journal.saisie["effectifs"])
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
    # Stabiliser les modes d'exécution pour la validation et la photographie.
    list(lots_disponibles(journal.rapport.projet).select_for_update().order_by("id"))
    journal = enregistrer(journal, utilisateur, data)
    rapport = journal.rapport
    valider_soumission(journal.saisie, rapport.projet)
    journal.photographie = contexte_projet(rapport.projet, rapport.date_rapport)
    journal.valide_ct_par = None
    journal.valide_ct_le = None
    journal.commentaire_ct = ""
    journal.save()
    rapport.statut = StatutRapport.SOUMIS
    rapport.soumis_le = timezone.now()
    rapport.valide_par = None
    rapport.valide_le = None
    rapport.commentaire_validation = ""
    rapport.save()
    Lot.objects.filter(id__in=[lot["id"] for lot in journal.photographie["lots"]]).update(
        premier_rapport_soumis=True
    )
    declencher_recalcul_sante(
        projet_id=rapport.projet_id,
        declencheur_type="RAPPORT_SOUMISSION",
        declencheur_id=rapport.id,
    )
    tracer(journal, utilisateur, ActionAudit.SIGNATURE, avant=avant, evenement="SOUMISSION_CC")
    return journal


@transaction.atomic
def signer_journal(*, journal, utilisateur, etape, commentaire=""):
    journal = verrouiller(journal)
    verifier_signataire(journal, utilisateur, "CT" if etape == "CT" else "CP")
    verifier_statut_projet_pour_ecriture(journal.rapport.projet)
    attendu = "SOUMIS" if etape == "CT" else "VALIDE_CT"
    if statut_journal(journal) != attendu:
        raise ErreurMetier(f"La signature exige le statut {attendu}.")
    if etape == "CT":
        journal.valide_ct_par = utilisateur
        journal.valide_ct_le = timezone.now()
        journal.commentaire_ct = commentaire
        journal.save()
    else:
        rapport = journal.rapport
        rapport.statut = StatutRapport.APPROUVE
        rapport.valide_par = utilisateur
        rapport.valide_le = timezone.now()
        rapport.commentaire_validation = commentaire
        rapport.save()
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
    verifier_signataire(journal, utilisateur, "CP" if statut == "VALIDE_CT" else "CT")
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
        destinataires = [
            a.utilisateur_id
            for a in affectations_actives(journal.rapport.projet_id).filter(
                role_projet__in=["CT", "CP"]
            )
        ]
        if journal.rapport.projet.chef_projet_id:
            destinataires.append(journal.rapport.projet.chef_projet_id)
        alerte.destinataires.set(destinataires)
        tracer(
            journal,
            utilisateur,
            ActionAudit.CREATION,
            evenement=data["type"],
            commentaire=data["description"],
        )
    return alerte
