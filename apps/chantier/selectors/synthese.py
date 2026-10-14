"""La synthèse périodique d'un chantier, agrégée de ses rapports journaliers.

C'est le calcul que `agregerSynthese` (frontend, `features/chantier/regles.ts`)
rejouait en simulation ; il vit désormais ici, et la projection a la forme
exacte de `ChargeSynthese`.

- **Le récapitulatif** reprend les lignes du journal de la période, absences
  comprises. Un brouillon y compte pour un rapport manquant : la synthèse doit
  dire la même chose à tous ses lecteurs.
- **Les chiffres** ne viennent que des rapports remis (soumis, validés,
  approuvés, ou rejetés depuis) : un rapport manquant n'a rien à compter.
- **Une fois signée par le CT**, la synthèse se lit dans sa photographie, et
  non plus dans le calcul vivant.
"""

import math
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.chantier.models import JournalChantier, SynthesePeriodique
from apps.chantier.selectors.journal import (
    contexte_projet,
    document,
    journal_periode,
    journaux_visibles,
    nom,
)
from apps.chantier.services.journal import aujourdhui, tient_fonction

FUSEAU = ZoneInfo("Africa/Abidjan")

#: Le délai laissé au signataire attendu, comme pour un rapport (RG-F2-03).
DELAI_SIGNATURE = timedelta(hours=24)

#: L'heure à laquelle la synthèse d'une période close est attendue, le lendemain.
HEURE_ECHEANCE_CT = time(17, 0)

#: Les situations d'un rapport remis au circuit — même rejeté depuis.
REMIS = ("SOUMIS", "VALIDE_CT", "APPROUVE_CP", "REJETE")

#: Au-delà, on renonce à remonter le passé pour trouver l'avancement de départ.
PROFONDEUR_RELEVE = 30


def arrondi(valeur: float, decimales: int = 0) -> float:
    """Arrondi au plus proche, la moitié vers le haut — `Math.round` côté frontend."""
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


def releve(projet, jour) -> tuple[float, float]:
    """Le dernier avancement connu du chantier à `jour`, et son théorique.

    Le dernier rapport remis à cette date qui en porte un — une journée
    d'arrêt n'en porte pas. Sans rapport, le chantier part de zéro.
    """
    journaux = (
        JournalChantier.objects.filter(
            rapport__projet=projet,
            rapport__date_rapport__lte=jour,
            rapport__supprime_le__isnull=True,
            rapport__statut__in=["SOUMIS", "APPROUVE", "REJETE"],
        )
        .select_related("rapport", "rapport__projet", "rapport__auteur", "valide_ct_par")
        .order_by("-rapport__date_rapport")[:PROFONDEUR_RELEVE]
    )
    for journal in journaux:
        charge = document(journal, relance_le=None)
        if charge["avancement"] is not None:
            return charge["avancement"], charge["avancement_theorique"] or 0
    return 0, 0


def _avancement_activite(ligne) -> int:
    if ligne["quantite_prevue"] <= 0:
        return 0
    cumul = ligne["cumul_veille"] + (ligne["quantite_jour"] or 0)
    return min(100, arrondi(100 * cumul / ligne["quantite_prevue"]))


def _avancement_par_lot(lots, documents):
    """Pour chaque lot, ses activités travaillées : où elles partaient, où elles arrivent.

    Une activité se suit de la première à la dernière fois qu'elle a été
    travaillée dans la période. Son objectif est l'écart de son avancement
    théorique sur ces jours, plus le pas d'une journée : le théorique relevé
    le premier jour est déjà celui du soir.
    """
    blocs = []
    for lot in lots:
        occurrences = OrderedDict()
        for charge in documents:
            for travaux in charge["travaux"]:
                if travaux["lot"]["id"] != lot["id"]:
                    continue
                for ligne in travaux["activites"]:
                    occurrences.setdefault(ligne["libelle"], []).append(ligne)
        activites = []
        for libelle, lignes in occurrences.items():
            depart, arrivee = lignes[0], lignes[-1]
            ecart = arrivee["avancement_theorique"] - depart["avancement_theorique"]
            pas = ecart / (len(lignes) - 1) if len(lignes) > 1 else 0
            prevue = depart["quantite_prevue"] or 1
            activites.append(
                {
                    "libelle": libelle,
                    "unite": arrivee["unite"],
                    "quantite_prevue": arrivee["quantite_prevue"],
                    "avancement_debut": arrondi(100 * depart["cumul_veille"] / prevue),
                    "avancement_fin": _avancement_activite(arrivee),
                    "objectif_gain": arrondi(ecart + pas),
                }
            )
        blocs.append({"lot": lot, "activites": activites})
    return blocs


def _effectifs(documents):
    categories = OrderedDict()
    for charge in documents:
        for ligne in charge["effectifs"] or []:
            categories.setdefault(ligne["categorie"], []).append(ligne)
    return [
        {
            "categorie": categorie,
            "prevu_par_jour": max(ligne["prevus"] or 0 for ligne in lignes),
            "presence_moyenne": arrondi(
                sum(ligne["presents"] or 0 for ligne in lignes) / len(lignes), 1
            ),
            "heures": arrondi(sum(ligne["heures"] or 0 for ligne in lignes)),
            "absences": sum(
                max(0, (ligne["prevus"] or 0) - (ligne["presents"] or 0)) for ligne in lignes
            ),
            "observation": next(
                (ligne["observation"] for ligne in lignes if ligne["observation"]), None
            ),
        }
        for categorie, lignes in categories.items()
    ]


def _materiaux(documents):
    """Consommé et livré de la période. Le module stocks n'existe pas : pas de stock inventé."""
    materiaux = OrderedDict()
    for charge in documents:
        for ligne in charge["materiaux"]:
            cumul = materiaux.setdefault(
                ligne["designation"],
                {
                    "designation": ligne["designation"],
                    "unite": ligne["unite"],
                    "stock_debut": None,
                    "consomme": 0,
                    "livre": 0,
                    "stock_fin": None,
                    "seuil_alerte": None,
                },
            )
            cumul["consomme"] += ligne["utilise"] or 0
            cumul["livre"] += ligne["livre"] or 0
    return list(materiaux.values())


def calculer(request, projet, type_, debut, fin) -> dict:
    """La synthèse calculée maintenant, sans ce que le CT y écrit ni le circuit."""
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
    documents = [
        document(journal, relance_le=None)
        for journal in journaux_visibles(request)
        .filter(rapport_id__in=[ligne["id"] for ligne in remises])
        .order_by("rapport__date_rapport")
    ]

    contexte = contexte_projet(projet, min(fin, aujourdhui()))
    lots = {lot["id"]: lot for lot in contexte["lots"]}
    # Un lot clôturé depuis reste dans la synthèse de la période où il a été travaillé.
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
        for ligne in remises
        if ligne["effectif_present"] is not None and ligne["effectif_prevu"] is not None
    ]

    depart, theorique_depart = releve(projet, debut - timedelta(days=1))
    arrivee, theorique = releve(projet, min(fin, aujourdhui()))
    depart, arrivee = arrondi(depart), arrondi(arrivee)
    theorique_depart, theorique = arrondi(theorique_depart), arrondi(theorique)

    return {
        "reference": reference(projet, type_, debut),
        "type": type_,
        "date_debut": debut.isoformat(),
        "date_fin": fin.isoformat(),
        "projet_id": str(projet.id),
        "projet_nom": projet.nom,
        "projet_reference": projet.reference,
        "localisation": contexte["localisation"],
        "chef_projet_nom": contexte["chef_projet_nom"],
        "conducteur_travaux_nom": contexte["conducteur_travaux_nom"],
        "lots": lots,
        "chiffres": {
            "jours_ouvres": len({ligne["date"] for ligne in lignes}),
            "rapports_attendus": len(lignes),
            "rapports_recus": len(remises),
            "rapports_valides": sum(
                ligne["statut"] in ("VALIDE_CT", "APPROUVE_CP") for ligne in lignes
            ),
            "effectifs_presents": sum(ligne["effectif_present"] for ligne in avec_effectifs),
            "effectifs_prevus": sum(ligne["effectif_prevu"] for ligne in avec_effectifs),
            "heures": arrondi(sum(ligne["heures"] for ligne in effectifs)),
            "livraisons": len(livraisons),
            "livraisons_partielles": sum(
                livraison["conformite"] != "CONFORME" for livraison in livraisons
            ),
            "incidents": len(incidents),
            "incidents_majeurs": sum(incident["gravite"] != "MINEUR" for incident in incidents),
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


# ---------------------------------------------------------------------------
# Ce que le CT écrit, et le circuit
# ---------------------------------------------------------------------------


def synthese_enregistree(projet, type_, debut, fin) -> SynthesePeriodique | None:
    if type_ not in SynthesePeriodique.Type.values:
        return None
    return (
        SynthesePeriodique.objects.select_related("redigee_par", "signee_ct_par", "decidee_cp_par")
        .filter(projet=projet, type=type_, date_debut=debut, date_fin=fin)
        .first()
    )


def statut(synthese: SynthesePeriodique | None, type_, fin) -> str:
    """Où en est la synthèse — de quoi décider ce que l'écran propose.

    `LIBRE` : période personnalisée, hors circuit. `EN_COURS` : la période
    n'est pas close. `A_REDIGER` : close, et le CT n'a encore rien écrit.
    Sinon, le statut enregistré.
    """
    if type_ not in SynthesePeriodique.Type.values:
        return "LIBRE"
    if synthese:
        return synthese.statut
    return "EN_COURS" if fin >= aujourdhui() else "A_REDIGER"


def _echeance_ct(fin):
    lendemain = datetime.combine(fin + timedelta(days=1), HEURE_ECHEANCE_CT, tzinfo=FUSEAU)
    return lendemain.isoformat()


def circuit(synthese, etat, calcul) -> list:
    """La signature du CT, puis celle du CP. Une période personnalisée n'en a pas."""
    if etat == "LIBRE":
        return []
    statuts = SynthesePeriodique.Statut
    signee_ct = synthese is not None and etat in (statuts.SOUMISE, statuts.APPROUVEE)
    decidee_cp = synthese is not None and etat in (statuts.APPROUVEE, statuts.REJETEE)
    ct = {
        "role": "CT",
        "signataire_nom": nom(synthese.signee_ct_par)
        if signee_ct
        else calcul["conducteur_travaux_nom"],
        "etat": "SIGNE" if signee_ct else "A_VENIR" if etat == "EN_COURS" else "EN_ATTENTE",
        "signe_le": synthese.signee_ct_le.isoformat() if signee_ct else None,
        "echeance": None,
        "commentaire": None,
    }
    if etat in ("A_REDIGER", statuts.BROUILLON):
        ct["echeance"] = _echeance_ct(date.fromisoformat(calcul["date_fin"]))
    elif etat == statuts.REJETEE:
        ct["echeance"] = (synthese.decidee_cp_le + DELAI_SIGNATURE).isoformat()
    cp = {
        "role": "CP",
        "signataire_nom": nom(synthese.decidee_cp_par) if decidee_cp else calcul["chef_projet_nom"],
        "etat": "SIGNE"
        if etat == statuts.APPROUVEE
        else "REJETE"
        if etat == statuts.REJETEE
        else "EN_ATTENTE"
        if etat == statuts.SOUMISE
        else "A_VENIR",
        "signe_le": synthese.decidee_cp_le.isoformat() if decidee_cp else None,
        "echeance": (synthese.signee_ct_le + DELAI_SIGNATURE).isoformat()
        if etat == statuts.SOUMISE
        else None,
        "commentaire": (synthese.commentaire_cp or None) if decidee_cp else None,
    }
    return [ct, cp]


def projection(request, projet, type_, debut, fin) -> dict:
    """La charge complète de `GET /chantier/syntheses/` : `ChargeSynthese`."""
    synthese = synthese_enregistree(projet, type_, debut, fin)
    etat = statut(synthese, type_, fin)
    figee = synthese is not None and bool(synthese.photographie)
    calcul = synthese.photographie if figee else calculer(request, projet, type_, debut, fin)
    # Un brouillon reste au CT : les autres lecteurs ne voient qu'une appréciation signée.
    publiee = synthese is not None and etat != SynthesePeriodique.Statut.BROUILLON
    redacteur = etat in ("A_REDIGER", "BROUILLON", "REJETEE") and tient_fonction(
        projet, request.user, "CT"
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
        # Ce que le CT a en cours d'écriture, pour qu'il le reprenne : à lui seul.
        "redaction": {
            "appreciation": synthese.appreciation if synthese else "",
            "objectifs": synthese.objectifs if synthese else [],
        }
        if redacteur
        else None,
        "circuit": circuit(synthese, etat, calcul),
    }


def suivi(request, *, projet_id=None, depuis=None) -> list:
    """Les synthèses enregistrées des chantiers visibles : où en est chacune."""
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
