"""Le journal sans réseau (mode hors ligne installable PWA).

- **Le paquet** (`paquet_hors_ligne`) : la journée et le lendemain — feuilles actives, cumuls,
  équipes avec leurs membres, météo suggérée, prévisions et blocages ouverts —, les listes du
  formulaire, les limites des photos et des pièces, et les jours ouvrés ouverts à la saisie.
- **L'envoi au retour du réseau** (`synchroniser`) : la copie du téléphone est enregistrée,
  puis soumise si on le demande.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.chantier.models import JournalChantier
from apps.chantier.serializers import journal as contrats
from apps.chantier.services.equipes_journal import controler_equipes, equipes_du_journal
from apps.chantier.services.fonctions import REDIGER, chemins_des_cases, verifier_fonction
from apps.chantier.services.journal import (
    RapportIncomplet,
    aujourdhui,
    cases_du_journal,
    creer_journal,
    jours_saisissables_ouvres,
    modifier_journal,
    soumettre_journal,
    statut_journal,
    verifier_jour,
)
from apps.core.enums import StatutRapport
from apps.core.exceptions import ErreurConflit
from apps.projets.models import EquipeChantier, MembreEquipeChantier

__all__ = ["JournalDejaVise", "paquet_hors_ligne", "synchroniser", "trier_lignes"]


class JournalDejaVise(ErreurConflit):
    """Le journal a été soumis ou visé pendant la coupure : l'envoi hors ligne est refusé."""

    code_metier = "journal_deja_vise"


def _choix(classe, champ) -> list[str]:
    return list(classe().fields[champ].choices)


def listes() -> dict:
    """Les listes fermées du formulaire, en codes ; les libellés sont ceux de l'écran."""
    return {
        "meteo": _choix(contrats.MeteoSerializer, "matin"),
        "conditions": _choix(contrats.MeteoSerializer, "conditions"),
        "motifs_arret": _choix(contrats.ArretSerializer, "motif"),
        "qualite": _choix(contrats.EquipeJourSerializer, "qualite"),
        "conformite_livraison": _choix(contrats.LivraisonSerializer, "conformite"),
        "nature_besoin": _choix(contrats.BesoinSerializer, "nature"),
        "propriete_equipement": _choix(contrats.EquipementSerializer, "propriete"),
        "etat_equipement": _choix(contrats.EquipementSerializer, "etat"),
        "nature_incident": _choix(contrats.IncidentSerializer, "nature"),
        "type_incident": _choix(contrats.IncidentSerializer, "type"),
        "gravite_incident": _choix(contrats.IncidentSerializer, "gravite"),
        "decide_par": _choix(contrats.IncidentSerializer, "decide_par"),
        "niveau_blocage": _choix(contrats.BlocageLigneSerializer, "niveau"),
        "nature_blocage": _choix(contrats.BlocageLigneSerializer, "nature"),
        "fonctions_equipe": [code for code, _ in MembreEquipeChantier.FONCTION_CHOICES],
    }


def limites() -> dict:
    champs = contrats.SaisieJournalSerializer().fields
    return {
        "photos": champs["photos"].max_length,
        "pieces_jointes": champs["pieces_jointes"].max_length,
        "taille_photo_octets": contrats.TAILLE_MAX_PHOTO_OCTETS,
        "taille_piece_octets": contrats.TAILLE_MAX_PIECE_OCTETS,
    }


def paquet_hors_ligne(projet, jour: date, utilisateur, journaux) -> dict:
    """Ce que le téléphone emporte : la journée `jour` et le lendemain."""
    from apps.chantier.selectors.journal import preparation

    jours = []
    for jour_paquet in (jour, jour + timedelta(days=1)):
        journal = journaux.filter(rapport__date_rapport=jour_paquet).first()
        precedent = (
            journaux.filter(rapport__date_rapport__lt=jour_paquet)
            .order_by("-rapport__date_rapport")
            .first()
        )
        jours.append(
            {
                "date": jour_paquet.isoformat(),
                **preparation(
                    projet,
                    jour_paquet,
                    journal=journal,
                    precedent=precedent,
                    utilisateur=utilisateur,
                ),
            }
        )
    reference = aujourdhui()
    return {
        "genere_le": timezone.now().isoformat(),
        "aujourdhui": reference.isoformat(),
        "jours_ouverts": [d.isoformat() for d in jours_saisissables_ouvres(reference)],
        "jours": jours,
        "listes": listes(),
        "limites": limites(),
    }


DEPLACEE = "n'est plus dans votre journal : déplacée, suspendue, clôturée ou retirée."


def trier_lignes(saisie, projet, jour: date, chemins) -> list[dict]:
    """Écarte les lignes que l'arbre n'accepte plus ; rend les lignes refusées et leur motif."""
    cases = cases_du_journal(projet, chemins)
    libelles = {str(e.pk): e.libelle for e in cases.arbre.elements}
    libelles.update(
        (str(pk), nom)
        for pk, nom in EquipeChantier.objects.filter(projet=projet).values_list("pk", "nom")
    )
    refusees: list[dict] = []

    def refuser(section, ligne, motif) -> None:
        identifiant = (
            ligne.get("activite_id")
            or ligne.get("lot_id")
            or ligne.get("equipe_id")
            or ligne.get("element_id")
            or ""
        )
        refusees.append(
            {
                "section": section,
                "ligne": ligne,
                "libelle": libelles.get(str(identifiant), ""),
                "motif": motif,
            }
        )

    lots = []
    for ligne in saisie.get("lots_travailles", []):
        lid = str(ligne["lot_id"])
        groupe = cases.groupes.get(lid)
        if groupe is None:
            refuser("lots_travailles", ligne, f"Cette partie {DEPLACEE}")
        elif any(str(autre["lot_id"]) == lid for autre in lots):
            refuser("lots_travailles", ligne, "Ligne en double.")
        else:
            lots.append({**ligne, "lot_id": lid})
    saisie["lots_travailles"] = lots
    travailles = {ligne["lot_id"] for ligne in lots}

    activites = []
    for ligne in saisie.get("activites", []):
        aid = str(ligne["activite_id"])
        feuille = cases.feuilles.get(aid)
        if feuille is None:
            refuser("activites", ligne, f"La tâche {DEPLACEE}")
        elif any(str(autre["activite_id"]) == aid for autre in activites):
            refuser("activites", ligne, "Ligne en double.")
        else:
            id_groupe = str(cases.groupe_de(feuille).pk)
            if id_groupe not in travailles:
                travailles.add(id_groupe)
                lots.append({"lot_id": id_groupe, "observation": ""})
            activites.append({**ligne, "activite_id": aid})
    saisie["activites"] = activites

    ids_arbre = {str(pk) for pk in cases.arbre.par_id}
    for section in ("blocages", "photos"):
        for ligne in saisie.get(section, []):
            eid = ligne.get("element_id")
            if eid is not None and str(eid) not in ids_arbre:
                refuser(section, ligne, f"La case associée {DEPLACEE}")
                ligne["element_id"] = None

    controler_equipes(saisie, equipes_du_journal(cases, jour), refuser)
    return refusees


def _refuser_si_vise(journal) -> None:
    rapport = journal.rapport
    if rapport.statut in (StatutRapport.BROUILLON, StatutRapport.REJETE):
        return
    signataires = [s["nom"] for s in journal.signatures or []]
    jour = rapport.date_rapport.strftime("%d/%m/%Y")
    message = (
        f"Non envoyé : le journal du {jour} a déjà été visé par {', '.join(signataires)}."
        if signataires
        else f"Non envoyé : le journal du {jour} a déjà été soumis."
    )
    raise JournalDejaVise(
        message + " Votre saisie n'a pas été enregistrée.",
        details={
            "statut": statut_journal(journal),
            "soumis_le": rapport.soumis_le.isoformat() if rapport.soumis_le else None,
            "signatures": [
                {k: s.get(k) for k in ("etape", "nom", "signe_le")}
                for s in journal.signatures or []
            ],
        },
    )


def synchroniser(*, projet, utilisateur, saisie: dict, soumettre: bool = False) -> dict:
    """La copie du téléphone, au retour du réseau. `saisie` est déjà validée par le contrat."""
    saisie = json.loads(json.dumps(saisie))
    jour = date.fromisoformat(saisie["date"])
    journal = (
        JournalChantier.objects.select_related("rapport")
        .filter(
            rapport__projet=projet,
            rapport__auteur=utilisateur,
            rapport__date_rapport=jour,
            rapport__supprime_le__isnull=True,
        )
        .first()
    )
    if journal is not None:
        _refuser_si_vise(journal)
    verifier_jour(jour, statut_actuel=journal.rapport.statut if journal else None)
    if journal is not None:
        chemins = chemins_des_cases(journal.perimetre_ids)
    else:
        chemins = verifier_fonction(projet, utilisateur, REDIGER).chemins
    refusees = trier_lignes(saisie, projet, jour, chemins)
    if journal is None:
        journal = creer_journal(projet=projet, utilisateur=utilisateur, jour=jour, data=saisie)
    else:
        journal = modifier_journal(journal=journal, utilisateur=utilisateur, data=saisie)
    erreurs = None
    if soumettre:
        try:
            journal = soumettre_journal(journal=journal, utilisateur=utilisateur, data={})
        except RapportIncomplet as exc:
            erreurs = exc.details
        except ValidationError as exc:
            erreurs = exc.detail
    return {"journal": journal, "lignes_refusees": refusees, "erreurs_soumission": erreurs}
