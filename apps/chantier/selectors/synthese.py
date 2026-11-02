"""La synthèse périodique d'un chantier, agrégée de ses rapports journaliers validés/approuvés.

- **Le récapitulatif** reprend les lignes du journal des jours ouvrés de la période, absences
  comprises. Un brouillon y compte pour un rapport manquant.
- **Les chiffres consolidés** (avancement, présence par équipe, matériaux livrés/consommés,
  incidents, blocages) ne proviennent **que des rapports `VALIDE` et `APPROUVE`** (A5).
- **Une fois signée**, la synthèse se lit dans sa photographie normalisée.
"""

import math
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from apps.chantier.models import JournalChantier, SynthesePeriodique
from apps.chantier.selectors.journal import (
    _calendrier_autour_arbre,
    contexte_projet,
    document,
    journal_periode,
    journaux_visibles,
    nom,
)
from apps.chantier.services.fonctions import (
    SYNTHESE_APPROUVER,
    SYNTHESE_REDIGER,
    tient_fonction,
)
from apps.chantier.services.journal import aujourdhui
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.calendrier_ouvre import calendrier_entreprise
from apps.projets.services.sante_calculs import compter_jours_ouvres

FUSEAU = ZoneInfo("Africa/Abidjan")
DELAI_SIGNATURE = timedelta(hours=24)
HEURE_ECHEANCE_VALIDATION = time(17, 0)

#: Tous les rapports remis (même en attente ou rejetés) comptent dans « reçus ».
REMIS = ("SOUMIS", "VALIDE", "APPROUVE", "REJETE", "VALIDE_CT", "APPROUVE_CP")

#: Seuls les rapports validés ou approuvés alimentent les chiffres consolidés (A5).
CONSOLIDABLES = ("VALIDE", "APPROUVE", "VALIDE_CT", "APPROUVE_CP")

PROFONDEUR_RELEVE = 30

STATUT_HISTORIQUE_VERS_NOUVEAU = {
    "VALIDE_CT": "VALIDE",
    "APPROUVE_CP": "APPROUVE",
}


def arrondi(valeur: float, decimales: int = 0) -> float:
    facteur = 10**decimales
    resultat = math.floor(valeur * facteur + 0.5) / facteur
    return int(resultat) if decimales == 0 else resultat


def reference(projet, type_, debut) -> str:
    if type_ == "HEBDOMADAIRE":
        suffixe = f"S{debut.isocalendar().week}"
    elif type_ == "MENSUELLE":
        suffixe = f"M{debut:%m}"
    else:
        suffixe = f"P{debut:%m%d}"
    return f"SYNT-{debut.year}-{projet.reference[-3:]}-{suffixe}"


def releve(projet, jour: date, *, arbre=None, calendrier=None) -> tuple[float, float]:
    """Dernier avancement consolidé (`VALIDE` ou `APPROUVE`) connu à `jour`, et son théorique."""
    journaux = (
        JournalChantier.objects.filter(
            rapport__projet=projet,
            rapport__date_rapport__lte=jour,
            rapport__supprime_le__isnull=True,
        )
        .filter(
            Q(rapport__statut="APPROUVE") | Q(rapport__statut="SOUMIS", valide_ct_le__isnull=False)
        )
        .select_related("rapport", "rapport__projet", "rapport__auteur", "valide_ct_par")
        .order_by("-rapport__date_rapport")[:PROFONDEUR_RELEVE]
    )
    for journal in journaux:
        charge = document(journal, relance_le=None, arbre=arbre, calendrier=calendrier)
        if charge["avancement"] is not None:
            return charge["avancement"], charge["avancement_theorique"] or 0
    return 0, 0


def _avancement_debut_activite(ligne: dict) -> int:
    mode = ligne.get("mode_mesure", "QUANTITE")
    if mode == "POURCENTAGE":
        return min(100, arrondi(ligne.get("pourcentage_veille") or 0))
    if mode == "JALON":
        return 0
    prevue = ligne.get("quantite_prevue") or 0
    if prevue <= 0:
        return 0
    return min(100, arrondi(100 * (ligne.get("cumul_veille") or 0) / prevue))


def _avancement_fin_activite(ligne: dict) -> int:
    mode = ligne.get("mode_mesure", "QUANTITE")
    if mode == "POURCENTAGE":
        pct = ligne.get("pourcentage_jour")
        if pct is None:
            pct = ligne.get("pourcentage_veille") or 0
        return min(100, arrondi(pct))
    if mode == "JALON":
        return 100 if ligne.get("jalon_atteint") else 0
    prevue = ligne.get("quantite_prevue") or 0
    if prevue <= 0:
        return 0
    cumul = (ligne.get("cumul_veille") or 0) + (ligne.get("quantite_jour") or 0)
    return min(100, arrondi(100 * cumul / prevue))


def _avancement_par_lot(lots, documents):
    blocs = []
    for lot in lots:
        occurrences = OrderedDict()
        for charge in documents:
            for travaux in charge["travaux"]:
                if travaux["lot"]["id"] != lot["id"]:
                    continue
                for ligne in travaux["activites"]:
                    cle = ligne.get("activite_id") or ligne["libelle"]
                    occurrences.setdefault(cle, []).append(ligne)
        activites = []
        for _cle, lignes in occurrences.items():
            depart, arrivee = lignes[0], lignes[-1]
            ecart = arrivee["avancement_theorique"] - depart["avancement_theorique"]
            pas = ecart / (len(lignes) - 1) if len(lignes) > 1 else 0
            activites.append(
                {
                    "libelle": arrivee["libelle"],
                    "mode_mesure": arrivee.get("mode_mesure", "QUANTITE"),
                    "unite": arrivee["unite"],
                    "quantite_prevue": arrivee["quantite_prevue"],
                    "avancement_debut": _avancement_debut_activite(depart),
                    "avancement_fin": _avancement_fin_activite(arrivee),
                    "objectif_gain": arrondi(ecart + pas),
                }
            )
        blocs.append({"lot": lot, "activites": activites})
    return blocs


def _effectifs(documents):
    """Agrège le pointage nominatif par équipe (`equipes`), avec repli historique."""
    groupes_equipes = OrderedDict()
    categories_historiques = OrderedDict()

    for charge in documents:
        if charge.get("equipes"):
            for eq in charge["equipes"]:
                intitule = (
                    f"{eq['nom']} ({eq['entreprise']})" if eq.get("entreprise") else eq["nom"]
                )
                groupes_equipes.setdefault(intitule, []).append(eq)
        elif charge.get("effectifs"):
            for cat in charge["effectifs"]:
                categories_historiques.setdefault(cat["categorie"], []).append(cat)

    resultat = [
        {
            "categorie": nom_eq,
            "prevu_par_jour": max(eq["membres"] or 0 for eq in lignes),
            "presence_moyenne": arrondi(sum(len(eq["presents"]) for eq in lignes) / len(lignes), 1),
            "heures": arrondi(sum(eq.get("heures") or 0 for eq in lignes)),
            "absences": sum(len(eq.get("absents") or []) for eq in lignes),
            "observation": next(
                (eq["observation"] for eq in lignes if eq.get("observation")), None
            ),
        }
        for nom_eq, lignes in groupes_equipes.items()
    ]

    for categorie, lignes in categories_historiques.items():
        resultat.append(
            {
                "categorie": categorie,
                "prevu_par_jour": max(ligne.get("prevus") or 0 for ligne in lignes),
                "presence_moyenne": arrondi(
                    sum(ligne.get("presents") or 0 for ligne in lignes) / len(lignes), 1
                ),
                "heures": arrondi(sum(ligne.get("heures") or 0 for ligne in lignes)),
                "absences": sum(
                    max(0, (ligne.get("prevus") or 0) - (ligne.get("presents") or 0))
                    for ligne in lignes
                ),
                "observation": next(
                    (ligne["observation"] for ligne in lignes if ligne.get("observation")), None
                ),
            }
        )
    return resultat


def _materiaux(documents):
    """Consommé et livré de la période, agrégés sur les rapports validés/approuvés."""
    materiaux = OrderedDict()
    for charge in documents:
        for ligne in charge["materiaux"]:
            cle = (ligne["designation"].strip().lower(), (ligne["unite"] or "").strip().lower())
            cumul = materiaux.setdefault(
                cle,
                {
                    "designation": ligne["designation"],
                    "unite": ligne["unite"],
                    "stock_debut": None,
                    "consomme": 0.0,
                    "livre": 0.0,
                    "stock_fin": None,
                    "seuil_alerte": None,
                },
            )
            cumul["consomme"] = round(cumul["consomme"] + float(ligne["utilise"] or 0), 3)
            cumul["livre"] = round(cumul["livre"] + float(ligne["livre"] or 0), 3)
    return list(materiaux.values())


def _normaliser_calcul_lu(calcul_brut: dict) -> dict:
    """Normalise une photographie de synthèse antérieure (statuts et libellés sans rôle en dur)."""
    c = dict(calcul_brut)
    if "validateurs_nom" not in c:
        c["validateurs_nom"] = c.get("conducteur_travaux_nom") or ""
    if "approbateurs_nom" not in c:
        c["approbateurs_nom"] = c.get("chef_projet_nom") or ""
    recap = []
    for ligne in c.get("recapitulatif") or []:
        copie = dict(ligne)
        copie["statut"] = STATUT_HISTORIQUE_VERS_NOUVEAU.get(
            copie.get("statut"), copie.get("statut")
        )
        ch = dict(copie.get("chantier") or {})
        if "redacteur_nom" not in ch:
            ch["redacteur_nom"] = ch.get("chef_chantier_nom") or ""
        copie["chantier"] = ch
        if "note_redacteur" not in copie:
            copie["note_redacteur"] = copie.get("note_chef_chantier")
        recap.append(copie)
    c["recapitulatif"] = recap
    return c


def calculer(request, projet, type_, debut: date, fin: date) -> dict:
    """La synthèse calculée maintenant sur les seuls rapports validés et approuvés."""
    lignes = sorted(
        (
            ligne
            for ligne in journal_periode(
                request, debut, fin, projet_id=projet.id, brouillons_visibles=False
            )
            if ligne["chantier"]["projet_id"] == str(projet.id)
        ),
        key=lambda ligne: ligne["date"],
    )
    remises = [ligne for ligne in lignes if ligne["statut"] in REMIS]
    validees = [ligne for ligne in lignes if ligne["statut"] in CONSOLIDABLES]

    arbre = charger_arbre(projet)
    cal_arbre = _calendrier_autour_arbre(arbre, min(fin, aujourdhui()))
    cal_periode = calendrier_entreprise(debut, fin)

    documents = [
        document(journal, relance_le=None, arbre=arbre, calendrier=cal_arbre)
        for journal in journaux_visibles(request)
        .filter(rapport_id__in=[ligne["id"] for ligne in validees])
        .order_by("rapport__date_rapport")
    ]

    contexte = contexte_projet(projet, min(fin, aujourdhui()))
    lots = {lot["id"]: lot for lot in contexte["lots"]}
    for charge in documents:
        for lot in charge["lots"]:
            lots.setdefault(lot["id"], lot)
    lots = sorted(lots.values(), key=lambda lot: lot["code"])

    effectifs = _effectifs(documents)
    incidents = [
        {**incident, "date": charge["date"]}
        for charge in documents
        for incident in charge["incidents"]
    ]
    livraisons = [livraison for charge in documents for livraison in charge["livraisons"]]
    avec_effectifs = [
        ligne
        for ligne in validees
        if ligne["effectif_present"] is not None and ligne["effectif_prevu"] is not None
    ]

    depart, theorique_depart = releve(
        projet, debut - timedelta(days=1), arbre=arbre, calendrier=cal_arbre
    )
    arrivee, theorique = releve(projet, min(fin, aujourdhui()), arbre=arbre, calendrier=cal_arbre)
    depart, arrivee = arrondi(depart), arrondi(arrivee)
    theorique_depart, theorique = arrondi(theorique_depart), arrondi(theorique)

    fin_effective = min(fin, aujourdhui())
    nb_jours_ouvres = (
        compter_jours_ouvres(debut, fin_effective, cal_periode) if fin_effective >= debut else 0
    )

    return {
        "reference": reference(projet, type_, debut),
        "type": type_,
        "date_debut": debut.isoformat(),
        "date_fin": fin.isoformat(),
        "projet_id": str(projet.id),
        "projet_nom": projet.nom,
        "projet_reference": projet.reference,
        "localisation": contexte["localisation"],
        "approbateurs_nom": contexte["approbateurs_nom"],
        "validateurs_nom": contexte["validateurs_nom"],
        "lots": lots,
        "chiffres": {
            "jours_ouvres": nb_jours_ouvres,
            "rapports_attendus": len(lignes),
            "rapports_recus": len(remises),
            "rapports_valides": len(validees),
            "effectifs_presents": sum(ligne["effectif_present"] for ligne in avec_effectifs),
            "effectifs_prevus": sum(ligne["effectif_prevu"] for ligne in avec_effectifs),
            "heures": arrondi(sum(ligne["heures"] for ligne in effectifs)),
            "livraisons": len(livraisons),
            "livraisons_partielles": sum(
                livraison["conformite"] != "CONFORME" for livraison in livraisons
            ),
            "incidents": len(incidents),
            "incidents_majeurs": sum(
                incident.get("gravite") in ("SIGNIFICATIF", "GRAVE") for incident in incidents
            ),
            "blocages": sum(len(charge["blocages"]) for charge in documents),
        },
        "progression": {
            "debut": depart,
            "fin": arrivee,
            "gain": arrivee - depart,
            "objectif": theorique - theorique_depart,
            "theorique": theorique,
        },
        "recapitulatif": lignes,
        "avancement": _avancement_par_lot(lots, documents),
        "effectifs": effectifs,
        "materiaux": _materiaux(documents),
        "incidents": incidents,
    }


def synthese_enregistree(projet, type_, debut, fin) -> SynthesePeriodique | None:
    if type_ not in SynthesePeriodique.Type.values:
        return None
    return (
        SynthesePeriodique.objects.select_related("redigee_par", "signee_ct_par", "decidee_cp_par")
        .filter(projet=projet, type=type_, date_debut=debut, date_fin=fin)
        .first()
    )


def statut(synthese: SynthesePeriodique | None, type_, fin) -> str:
    if type_ not in SynthesePeriodique.Type.values:
        return "LIBRE"
    if synthese:
        return synthese.statut
    return "EN_COURS" if fin >= aujourdhui() else "A_REDIGER"


def _echeance_validation(fin):
    lendemain = datetime.combine(fin + timedelta(days=1), HEURE_ECHEANCE_VALIDATION, tzinfo=FUSEAU)
    return lendemain.isoformat()


def circuit(synthese, etat, calcul) -> list:
    """Signature de rédaction/validation, puis d'approbation (par permission)."""
    if etat == "LIBRE":
        return []
    statuts = SynthesePeriodique.Statut
    signee_val = synthese is not None and etat in (statuts.SOUMISE, statuts.APPROUVEE)
    decidee_app = synthese is not None and etat in (statuts.APPROUVEE, statuts.REJETEE)
    etape_val = {
        "role": "VALIDATION",
        "signataire_nom": nom(synthese.signee_ct_par) if signee_val else calcul["validateurs_nom"],
        "etat": "SIGNE" if signee_val else "A_VENIR" if etat == "EN_COURS" else "EN_ATTENTE",
        "signe_le": synthese.signee_ct_le.isoformat() if signee_val else None,
        "echeance": None,
        "commentaire": None,
    }
    if etat in ("A_REDIGER", statuts.BROUILLON):
        etape_val["echeance"] = _echeance_validation(date.fromisoformat(calcul["date_fin"]))
    elif etat == statuts.REJETEE:
        etape_val["echeance"] = (synthese.decidee_cp_le + DELAI_SIGNATURE).isoformat()

    etape_app = {
        "role": "APPROBATION",
        "signataire_nom": nom(synthese.decidee_cp_par)
        if decidee_app
        else calcul["approbateurs_nom"],
        "etat": "SIGNE"
        if etat == statuts.APPROUVEE
        else "REJETE"
        if etat == statuts.REJETEE
        else "EN_ATTENTE"
        if etat == statuts.SOUMISE
        else "A_VENIR",
        "signe_le": synthese.decidee_cp_le.isoformat() if decidee_app else None,
        "echeance": (synthese.signee_ct_le + DELAI_SIGNATURE).isoformat()
        if etat == statuts.SOUMISE
        else None,
        "commentaire": (synthese.commentaire_cp or None) if decidee_app else None,
    }
    return [etape_val, etape_app]


def etape_a_signer(
    utilisateur, projet, etat, synthese: SynthesePeriodique | None = None
) -> str | None:
    """Étape signable par cet utilisateur (`VALIDATION` | `APPROBATION` | `None`)."""
    statuts = SynthesePeriodique.Statut
    if etat in ("A_REDIGER", statuts.BROUILLON, statuts.REJETEE):
        return "VALIDATION" if tient_fonction(projet, utilisateur, SYNTHESE_REDIGER) else None
    if etat == statuts.SOUMISE:
        if synthese is not None and synthese.signee_ct_par_id == utilisateur.id:
            return None
        return "APPROBATION" if tient_fonction(projet, utilisateur, SYNTHESE_APPROUVER) else None
    return None


def projection(request, projet, type_, debut, fin) -> dict:
    """La charge complète de `GET /chantier/syntheses/` : `ChargeSynthese`."""
    synthese = synthese_enregistree(projet, type_, debut, fin)
    etat = statut(synthese, type_, fin)
    figee = synthese is not None and bool(synthese.photographie)
    calcul = (
        _normaliser_calcul_lu(synthese.photographie)
        if figee
        else calculer(request, projet, type_, debut, fin)
    )
    publiee = synthese is not None and etat != SynthesePeriodique.Statut.BROUILLON
    redacteur = etat in ("A_REDIGER", "BROUILLON", "REJETEE") and tient_fonction(
        projet, request.user, SYNTHESE_REDIGER
    )
    return {
        **calcul,
        "id": str(synthese.id) if synthese else None,
        "statut": etat,
        "genere_le": (synthese.signee_ct_le if figee else timezone.now()).isoformat(),
        "appreciation": {
            "auteur_nom": nom(synthese.redigee_par),
            "redigee_le": synthese.redigee_le.isoformat(),
            "texte": synthese.appreciation,
        }
        if publiee and synthese.appreciation
        else None,
        "objectifs": synthese.objectifs if publiee else [],
        "redaction": {
            "appreciation": synthese.appreciation if synthese else "",
            "objectifs": synthese.objectifs if synthese else [],
        }
        if redacteur
        else None,
        "circuit": circuit(synthese, etat, calcul),
        "etape_a_signer": etape_a_signer(request.user, projet, etat, synthese=synthese),
    }


def suivi(request, *, projet_id=None, depuis=None) -> list:
    from apps.chantier.selectors.journal import projets_visibles

    qs = SynthesePeriodique.objects.filter(projet__in=projets_visibles(request))
    if projet_id:
        qs = qs.filter(projet_id=projet_id)
    if depuis:
        qs = qs.filter(date_fin__gte=depuis)
    return [
        {
            "id": str(synthese.id),
            "projet_id": str(synthese.projet_id),
            "type": synthese.type,
            "date_debut": synthese.date_debut.isoformat(),
            "date_fin": synthese.date_fin.isoformat(),
            "statut": synthese.statut,
        }
        for synthese in qs.order_by("-date_debut", "type")
    ]
