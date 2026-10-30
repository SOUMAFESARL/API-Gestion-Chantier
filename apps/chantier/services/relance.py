"""Relancer une ligne du journal : réclamer un rapport, ou une signature.

Une ligne, c'est un chantier, un rédacteur, un jour : chacun écrit son propre rapport, sur sa
partie du projet (30/10/2026). Selon où elle en est, la relance va :

- au **rédacteur** si son rapport manque, reste en brouillon ou a été rejeté — à lui seul ;
- aux **validateurs encore attendus** si le rapport est soumis ;
- aux **approbateurs encore attendus** s'il est validé.

Rédacteurs, validateurs et approbateurs sont ceux qui en ont la permission sur le projet
(`fonctions`), jamais un nom de rôle.

Un rapport approuvé n'attend plus personne : il ne se relance pas.

**Une relance par ligne et par jour** (décision du 14/10/2026). La seconde
demande du même jour rend la première sans renvoyer d'e-mail : un bouton
pressé deux fois, ou la tâche de 17 h 30 passant après une relance manuelle,
ne harcèle personne.
"""

import logging
from datetime import date

from django.db import transaction

from apps.audit.services import journaliser
from apps.chantier.models import JournalChantier, RelanceJournal
from apps.chantier.services import signatures
from apps.chantier.services.fonctions import REDIGER, titulaires
from apps.chantier.services.journal import (
    aujourdhui,
    premier_jour_rapport,
    statut_journal,
)
from apps.core.emails import adresse_frontend, envoyer
from apps.core.enums import ActionAudit
from apps.core.exceptions import ErreurMetier
from apps.projets.services.calendrier_ouvre import Calendrier, calendrier_entreprise

logger = logging.getLogger(__name__)

#: Les chantiers dont le journal attend un rapport chaque jour ouvré.
STATUTS_SUIVIS = ("EN_COURS", "EN_RETARD", "CRITIQUE")


class RelanceSansDestinataire(ErreurMetier):
    code_metier = "regle_metier"
    default_detail = (
        "Personne n'occupe cette fonction sur le chantier : il n'y a personne à relancer."
    )


class RelanceNonEnvoyee(ErreurMetier):
    status_code = 503
    code_metier = "service_indisponible"
    default_detail = "La relance n'a pas pu partir par e-mail. Réessayez dans un instant."


def journal_de_la_ligne(projet, date_rapport: date, redacteur=None) -> JournalChantier | None:
    qs = JournalChantier.objects.select_related("rapport", "rapport__auteur").filter(
        rapport__projet=projet,
        rapport__date_rapport=date_rapport,
        rapport__supprime_le__isnull=True,
    )
    if redacteur is not None:
        qs = qs.filter(rapport__auteur=redacteur)
    return qs.first()


def cible(projet, journal: JournalChantier | None, redacteur=None) -> tuple[str, list]:
    """L'étape attendue sur la ligne, et les personnes qui la tiennent encore."""
    from apps.accounts.models import Utilisateur

    statut = statut_journal(journal) if journal else None
    if statut == "APPROUVE_CP":
        raise ErreurMetier("Ce rapport est approuvé : il n'y a personne à relancer.")
    if statut in ("SOUMIS", "VALIDE_CT"):
        # Seuls les signataires attendus qui n'ont pas encore signé.
        restants = signatures.attendus_restants(journal)
        personnes = list(Utilisateur.objects.filter(pk__in=restants))
        return ("CT" if statut == "SOUMIS" else "CP"), _sans_doublon(personnes)
    # Rapport absent, en brouillon ou rejeté : c'est à son rédacteur d'écrire.
    if journal and journal.rapport.auteur_id:
        return "CC", [journal.rapport.auteur]
    if redacteur is not None:
        return "CC", _sans_doublon([redacteur])
    return "CC", _sans_doublon([t.utilisateur for t in titulaires(projet, REDIGER)])


def _sans_doublon(personnes: list) -> list:
    vus, uniques = set(), []
    for personne in personnes:
        if personne.id not in vus and personne.email:
            vus.add(personne.id)
            uniques.append(personne)
    return uniques


def relance_du_jour(projet, date_rapport: date, redacteur=None) -> RelanceJournal | None:
    return RelanceJournal.objects.filter(
        projet=projet, date_rapport=date_rapport, redacteur=redacteur, jour=aujourdhui()
    ).first()


def verifier_ligne(
    projet,
    date_rapport: date,
    journal: JournalChantier | None,
    calendrier: Calendrier | None = None,
) -> None:
    """Une ligne qui n'existe pas dans le journal ne se relance pas."""
    if date_rapport > aujourdhui():
        raise ErreurMetier("Un rapport futur ne se réclame pas.")
    if journal is None:
        if projet.statut not in STATUTS_SUIVIS:
            raise ErreurMetier("Ce chantier n'attend pas de rapport journalier.")
        cal = calendrier or calendrier_entreprise(date_rapport, date_rapport)
        if not cal.est_ouvre(date_rapport):
            raise ErreurMetier(
                "Aucun rapport n'est attendu ce jour : "
                "il n'est pas ouvré dans le calendrier de l'entreprise."
            )


@transaction.atomic
def relancer(
    *,
    projet,
    date_rapport: date,
    redacteur=None,
    utilisateur=None,
    automatique: bool = False,
    calendrier: Calendrier | None = None,
):
    """Relance la ligne ; rend la relance du jour, existante ou nouvelle."""
    existante = relance_du_jour(projet, date_rapport, redacteur)
    if existante:
        return existante

    journal = journal_de_la_ligne(projet, date_rapport, redacteur)
    verifier_ligne(projet, date_rapport, journal, calendrier=calendrier)
    etape, destinataires = cible(projet, journal, redacteur)
    if not destinataires:
        raise RelanceSansDestinataire()

    relance = RelanceJournal.objects.create(
        projet=projet,
        date_rapport=date_rapport,
        redacteur=redacteur,
        jour=aujourdhui(),
        journal=journal,
        etape=etape,
        automatique=automatique,
        cree_par=utilisateur,
    )
    relance.destinataires.set(destinataires)
    if journal:
        journal.relance_le = relance.cree_le
        journal.save(update_fields=["relance_le", "modifie_le"])

    envoyes = sum(_envoyer(relance, personne) for personne in destinataires)
    if not envoyes:
        # Aucun e-mail n'est parti : l'écran ne doit pas dire « relance envoyée ».
        raise RelanceNonEnvoyee()

    journaliser(
        action=ActionAudit.CREATION,
        type_entite="RelanceJournal",
        entite_id=relance.id,
        utilisateur_id=getattr(utilisateur, "id", None),
        valeur_apres={
            "projet": str(projet.id),
            "date_rapport": date_rapport.isoformat(),
            "redacteur": str(redacteur.pk) if redacteur else None,
            "etape": etape,
            "automatique": automatique,
            "destinataires": [str(personne.id) for personne in destinataires],
        },
    )
    return relance


def _envoyer(relance: RelanceJournal, personne) -> bool:
    """Un e-mail par personne : les destinataires ne voient pas les adresses des autres."""
    projet = relance.projet
    if relance.etape == "CC":
        jour_iso = relance.date_rapport.isoformat()
        lien = f"{adresse_frontend()}/rapports/saisie/{projet.id}?date={jour_iso}"
    else:
        lien = f"{adresse_frontend()}/rapports/{relance.journal.rapport_id}"
    jour = relance.date_rapport.strftime("%d/%m/%Y")
    sujet = {
        "CC": f"Rapport journalier attendu — {projet.nom} — {jour}",
        "CT": f"Rapport journalier à valider — {projet.nom} — {jour}",
        "CP": f"Rapport journalier à approuver — {projet.nom} — {jour}",
    }[relance.etape]
    envoye = envoyer(
        "relance_journal",
        sujet,
        personne.email,
        {
            "prenom": personne.prenom,
            "etape": relance.etape,
            "projet_nom": projet.nom,
            "projet_reference": projet.reference,
            "date_rapport": relance.date_rapport,
            "automatique": relance.automatique,
            "lien": lien,
        },
    )
    if not envoye:
        logger.warning("Relance %s non envoyée à %s", relance.id, personne.id)
    return envoye


def relancer_rapports_manquants(jour: date | None = None) -> dict:
    """La relance automatique de 17 h 30 : chaque rédacteur sans rapport remis ce jour.

    À appeler dans le schéma de l'entreprise (`schema_context`). Un rédacteur dont le rapport
    est soumis, validé ou approuvé n'est pas relancé ; un brouillon, si — il n'est pas remis.
    Chacun l'est pour son propre rapport : celui qui a remis le sien n'est pas dérangé.
    """
    from apps.projets.models import Projet

    jour = jour or aujourdhui()
    bilan = {"relances": 0, "deja_relances": 0, "sans_destinataire": 0, "echecs": 0}
    cal = calendrier_entreprise(jour, jour)
    if not cal.est_ouvre(jour):
        return bilan
    for projet in Projet.objects.filter(statut__in=STATUTS_SUIVIS).select_related("chef_projet"):
        if jour < premier_jour_rapport(projet):
            continue  # rien à rattraper avant l'enregistrement du chantier
        redacteurs = [t.utilisateur for t in titulaires(projet, REDIGER)] or [None]
        for redacteur in redacteurs:
            journal = journal_de_la_ligne(projet, jour, redacteur)
            if journal and journal.rapport.statut != "BROUILLON":
                continue
            if relance_du_jour(projet, jour, redacteur):
                bilan["deja_relances"] += 1
                continue
            try:
                relancer(
                    projet=projet,
                    date_rapport=jour,
                    redacteur=redacteur,
                    automatique=True,
                    calendrier=cal,
                )
                bilan["relances"] += 1
            except RelanceSansDestinataire:
                bilan["sans_destinataire"] += 1
            except ErreurMetier as erreur:
                logger.warning("Relance automatique impossible pour %s : %s", projet.id, erreur)
                bilan["echecs"] += 1
    return bilan
