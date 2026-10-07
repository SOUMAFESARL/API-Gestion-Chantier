"""Lectures et projections compatibles avec l'adaptateur du frontend."""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Prefetch, Q

from apps.chantier.models import JournalChantier
from apps.chantier.services.journal import (
    affectations_actives,
    aujourdhui,
    lots_disponibles,
    statut_journal,
)
from apps.core.enums import ModeExecution
from apps.core.permissions import filtrer_queryset_par_affectations
from apps.projets.models import Activite, Projet

SECTIONS = {
    ModeExecution.REGIE: ["AVANCEMENT", "EFFECTIFS", "MATERIAUX", "LIVRAISONS", "EQUIPEMENTS"],
    ModeExecution.SOUS_TRAITANCE_INFORMELLE: ["PRODUCTION"],
    ModeExecution.SOUS_TRAITANCE_STRUCTUREE: ["AVANCEMENT", "PRESENCE_SOUS_TRAITANT"],
}


def nom(utilisateur):
    return f"{utilisateur.prenom} {utilisateur.nom}".strip() if utilisateur else ""


def journaux_visibles(request):
    qs = (
        JournalChantier.objects.filter(
            rapport__supprime_le__isnull=True,
            rapport__projet__supprime_le__isnull=True,
        )
        .select_related(
            "rapport",
            "rapport__projet",
            "rapport__projet__chef_projet",
            "rapport__auteur",
            "rapport__valide_par",
            "valide_ct_par",
        )
        .prefetch_related("alertes")
    )
    return filtrer_queryset_par_affectations(
        qs, request.user, champ_projet="rapport__projet_id", request=request
    )


def projets_visibles(request):
    return filtrer_queryset_par_affectations(
        Projet.objects.select_related("chef_projet"), request.user, request=request
    )


def pour_auteur(qs, utilisateur):
    return qs.filter(~Q(rapport__statut="BROUILLON") | Q(rapport__auteur=utilisateur))


def filtre_journaux(qs, filtres, utilisateur):
    for cle, champ in (
        ("projet", "rapport__projet_id"),
        ("date", "rapport__date_rapport"),
        ("date_debut", "rapport__date_rapport__gte"),
        ("date_fin", "rapport__date_rapport__lte"),
    ):
        if cle in filtres:
            qs = qs.filter(**{champ: filtres[cle]})
    if filtres.get("auteur") == "moi":
        qs = qs.filter(rapport__auteur=utilisateur)
    statut = filtres.get("statut")
    if statut == "VALIDE_CT":
        qs = qs.filter(rapport__statut="SOUMIS", valide_ct_le__isnull=False)
    elif statut == "SOUMIS":
        qs = qs.filter(rapport__statut="SOUMIS", valide_ct_le__isnull=True)
    elif statut:
        qs = qs.filter(rapport__statut="APPROUVE" if statut == "APPROUVE_CP" else statut)
    return qs.order_by("-rapport__date_rapport", "-modifie_le")


def theorique(debut, fin, jour):
    if not debut or not fin:
        return 0
    if jour < debut:
        return 0
    if jour >= fin:
        return 100
    return round(100 * ((jour - debut).days + 1) / max(1, (fin - debut).days + 1), 2)


def contexte_projet(projet, jour):
    intervenants = dict.fromkeys(("CC", "CT", "CP"), "")
    for affectation in affectations_actives(projet.id).order_by("cree_le"):
        if affectation.role_projet in intervenants and not intervenants[affectation.role_projet]:
            intervenants[affectation.role_projet] = nom(affectation.utilisateur)
    if projet.chef_projet_id:
        intervenants["CP"] = nom(projet.chef_projet)
    lots = list(
        lots_disponibles(projet).prefetch_related(
            Prefetch("activites", queryset=Activite.objects.filter(est_actif=True))
        )
    )
    # Les journaux antérieurs constituent le cumul déclaratif du journal.
    # La quantité du planning n'est pas modifiée par une saisie de journal.
    cumuls = defaultdict(float)
    bases = {}
    precedents = (
        JournalChantier.objects.filter(
            rapport__projet=projet,
            rapport__date_rapport__lt=jour,
            rapport__supprime_le__isnull=True,
            rapport__statut__in=["SOUMIS", "APPROUVE"],
        )
        .order_by("rapport__date_rapport")
        .values_list("saisie", "photographie")
    )
    for saisie, photographie in precedents:
        for activite in photographie.get("activites", []):
            bases.setdefault(activite["activite_id"], activite["cumul_veille"])
        for ligne in saisie.get("activites", []) + saisie.get("production", []):
            cumuls[ligne["activite_id"]] += ligne["quantite_jour"] or 0
    charges_lots, charges_activites, sections = [], [], []
    for lot in lots:
        charges_lots.append(
            {
                "id": str(lot.id),
                "code": lot.code,
                "nom": lot.libelle,
                "mode_execution": "REGIE_DIRECTE"
                if lot.mode_execution == ModeExecution.REGIE
                else lot.mode_execution,
                "projet_id": str(projet.id),
                "projet_nom": projet.nom,
                "projet_reference": projet.reference,
                "chef_chantier_nom": intervenants["CC"],
            }
        )
        for section in SECTIONS.get(lot.mode_execution, []):
            if section not in sections:
                sections.append(section)
        for rang, activite in enumerate(lot.activites.all(), 1):
            identifiant = str(activite.id)
            charges_activites.append(
                {
                    "activite_id": identifiant,
                    "lot_id": str(lot.id),
                    "suivi": "PRODUCTION"
                    if lot.mode_execution == ModeExecution.SOUS_TRAITANCE_INFORMELLE
                    else "AVANCEMENT",
                    "code": f"{lot.code}.{rang:02d}",
                    "libelle": activite.libelle,
                    "unite": activite.unite,
                    "quantite_prevue": float(activite.quantite_prevue),
                    "cumul_veille": bases.get(identifiant, float(activite.quantite_realisee))
                    + cumuls[identifiant],
                    "avancement_theorique": theorique(
                        activite.date_debut_prevue, activite.date_fin_prevue, jour
                    ),
                }
            )
    return {
        "projet": {
            "id": str(projet.id),
            "nom": projet.nom,
            "reference": projet.reference,
            "chef_chantier_nom": intervenants["CC"],
        },
        "lots": charges_lots,
        "sections": sections,
        "activites": charges_activites,
        # Pas de stock inventé : le module stocks n'a pas encore de modèle concret.
        "materiaux": [],
        "localisation": ", ".join(filter(None, [projet.quartier, projet.ville])),
        "conducteur_travaux_nom": intervenants["CT"],
        "chef_projet_nom": intervenants["CP"],
    }


def existant(journal):
    return {
        "id": str(journal.rapport_id),
        "statut": statut_journal(journal),
        "saisie": journal.saisie,
        "enregistre_le": journal.modifie_le.isoformat(),
        "commentaire_rejet": journal.rapport.commentaire_validation
        if journal.rapport.statut == "REJETE"
        else None,
        "alertes_envoyees": [a.cle for a in journal.alertes.all()],
    }


def preparation(projet, jour, *, journal=None, precedent=None):
    contexte = (
        journal.photographie
        if journal
        and journal.photographie
        and statut_journal(journal) not in ("BROUILLON", "REJETE")
        else contexte_projet(projet, jour)
    )
    saisie_precedente = precedent.saisie if precedent else {}
    reprises = {
        "effectifs": [
            {"categorie": ligne["categorie"], "prevus": ligne["prevus"]}
            for ligne in saisie_precedente.get("effectifs", [])
        ],
        "equipements": [
            {k: ligne[k] for k in ("designation", "reference", "propriete", "operateur")}
            for ligne in saisie_precedente.get("equipements", [])
        ],
        "intervenants": [
            {k: ligne[k] for k in ("intervenant", "activite_id", "prix_unitaire")}
            for ligne in saisie_precedente.get("production", [])
        ],
    }
    return {
        "aujourdhui": aujourdhui().isoformat(),
        **{k: contexte[k] for k in ("projet", "lots", "sections", "activites", "materiaux")},
        "reprises": reprises,
        "rapport": existant(journal) if journal else None,
    }


def reference(journal):
    r = journal.rapport
    return f"RJ-{r.projet.reference}-{r.date_rapport:%Y%m%d}"


def circuit(journal, contexte):
    r = journal.rapport
    statut = statut_journal(journal)
    cc_signe = bool(r.soumis_le)
    ct_signe = bool(journal.valide_ct_le)
    cp_signe = statut == "APPROUVE_CP"
    echeance_ct = (r.soumis_le + timedelta(hours=24)).isoformat() if r.soumis_le else None
    echeance_cp = (
        (journal.valide_ct_le + timedelta(hours=24)).isoformat() if journal.valide_ct_le else None
    )
    rejete = statut == "REJETE"
    return [
        {
            "role": "CC",
            "signataire_nom": nom(r.auteur),
            "etat": "SIGNE" if cc_signe else "EN_ATTENTE",
            "signe_le": r.soumis_le.isoformat() if r.soumis_le else None,
            "echeance": None,
            "commentaire": None,
        },
        {
            "role": "CT",
            "signataire_nom": nom(journal.valide_ct_par) or contexte["conducteur_travaux_nom"],
            "etat": "REJETE"
            if rejete and not ct_signe
            else "SIGNE"
            if ct_signe
            else "EN_ATTENTE"
            if cc_signe
            else "A_VENIR",
            "signe_le": journal.valide_ct_le.isoformat() if ct_signe else None,
            "echeance": echeance_ct,
            "commentaire": r.commentaire_validation
            if rejete and not ct_signe
            else journal.commentaire_ct,
        },
        {
            "role": "CP",
            "signataire_nom": nom(r.valide_par) if cp_signe else contexte["chef_projet_nom"],
            "etat": "REJETE"
            if rejete and ct_signe
            else "SIGNE"
            if cp_signe
            else "EN_ATTENTE"
            if ct_signe
            else "A_VENIR",
            "signe_le": r.valide_le.isoformat() if cp_signe else None,
            "echeance": echeance_cp,
            "commentaire": r.commentaire_validation if cp_signe or (rejete and ct_signe) else None,
        },
    ]


def document(journal, *, contexte=None):
    """Projection ChargeRapport, calculée sans requête par ligne de rubrique."""
    r, saisie = journal.rapport, journal.saisie
    contexte = contexte or journal.photographie or contexte_projet(r.projet, r.date_rapport)
    quantites = defaultdict(float)
    for ligne in saisie["activites"] + saisie["production"]:
        quantites[ligne["activite_id"]] += ligne["quantite_jour"] or 0
    observations = {ligne["activite_id"]: ligne["observation"] for ligne in saisie["activites"]}
    points = {ligne["lot_id"]: ligne["observation"] for ligne in saisie["lots_travailles"]}
    lots = [
        ligne
        for ligne in contexte["lots"]
        if ligne["id"] in points
        or any(
            a["lot_id"] == ligne["id"] and a["activite_id"] in quantites
            for a in contexte["activites"]
        )
    ]
    travaux = []
    activites = {a["activite_id"]: a for a in contexte["activites"]}
    for lot in lots:
        toutes = [a for a in contexte["activites"] if a["lot_id"] == lot["id"]]
        lignes = [
            {
                "libelle": a["libelle"],
                "unite": a["unite"],
                "quantite_prevue": a["quantite_prevue"],
                "cumul_veille": a["cumul_veille"],
                "quantite_jour": quantites[a["activite_id"]],
                "avancement_theorique": a["avancement_theorique"],
                "observation": observations.get(a["activite_id"]),
            }
            for a in toutes
            if a["activite_id"] in quantites
        ]
        avance = sum(
            min(100, 100 * (a["cumul_veille"] + quantites[a["activite_id"]]) / a["quantite_prevue"])
            for a in toutes
            if a["quantite_prevue"] > 0
        )
        travaux.append(
            {
                "lot": lot,
                "avancement": round(avance / len(toutes), 2) if toutes else 0,
                "avancement_theorique": round(
                    sum(a["avancement_theorique"] for a in toutes) / len(toutes), 2
                )
                if toutes
                else 0,
                "observation": points.get(lot["id"]),
                "activites": lignes,
            }
        )
    blocage = saisie["blocage"]
    effectifs = (
        saisie["effectifs"] if "EFFECTIFS" in contexte["sections"] and not saisie["arret"] else None
    )
    production = (
        [
            {
                "intervenant": ligne["intervenant"],
                "activite": activites[ligne["activite_id"]]["libelle"],
                "unite": activites[ligne["activite_id"]]["unite"],
                "prix_unitaire": ligne["prix_unitaire"],
                "quantite_jour": ligne["quantite_jour"],
                "cumul": activites[ligne["activite_id"]]["cumul_veille"]
                + (ligne["quantite_jour"] or 0),
            }
            for ligne in saisie["production"]
            if ligne["activite_id"] in activites
        ]
        if "PRODUCTION" in contexte["sections"]
        else None
    )
    return {
        "id": str(r.id),
        "reference": reference(journal) if r.soumis_le else None,
        "date": r.date_rapport.isoformat(),
        "chantier": {
            "projet_id": str(r.projet_id),
            "projet_nom": contexte["projet"]["nom"],
            "projet_reference": contexte["projet"]["reference"],
            "chef_chantier_nom": nom(r.auteur),
        },
        "lots": lots,
        "statut": statut_journal(journal),
        "effectif_present": sum(ligne["presents"] or 0 for ligne in effectifs)
        if effectifs is not None
        else None,
        "effectif_prevu": sum(ligne["prevus"] or 0 for ligne in effectifs)
        if effectifs is not None
        else None,
        "avancement": round(sum(ligne["avancement"] for ligne in travaux) / len(travaux), 2)
        if travaux
        else None,
        "avancement_theorique": round(
            sum(ligne["avancement_theorique"] for ligne in travaux) / len(travaux), 2
        )
        if travaux
        else None,
        "nb_incidents": len(saisie["incidents"]),
        "nb_blocages": int(blocage["niveau"] != "AUCUN"),
        "nb_photos": len(saisie["photos"]),
        "soumis_le": r.soumis_le.isoformat() if r.soumis_le else None,
        "dernier_rapport_le": None,
        "relance_le": journal.relance_le.isoformat() if journal.relance_le else None,
        "note_chef_chantier": saisie["note_cc"],
        "circuit": circuit(journal, contexte),
        "localisation": contexte["localisation"],
        "conducteur_travaux_nom": contexte["conducteur_travaux_nom"],
        "chef_projet_nom": contexte["chef_projet_nom"],
        "heure_debut": saisie["heure_debut"],
        "heure_fin": saisie["heure_fin"],
        "arret": saisie["arret"],
        "meteo": saisie["meteo"],
        "effectifs": effectifs,
        "production": production,
        "travaux": travaux,
        "materiaux": [
            {
                "designation": ligne["designation"],
                "unite": ligne["unite"],
                "stock_debut": None,
                "livre": 0,
                "utilise": ligne["quantite_consommee"],
                "seuil_alerte": None,
            }
            for ligne in saisie["materiaux"]
        ],
        "livraisons": saisie["livraisons"],
        "besoins": saisie["besoins"],
        "equipements": saisie["equipements"],
        "incidents": [
            {
                **ligne,
                "numero": f"INC-{i:02d}",
                "action": ligne["action_entreprise"],
                "resolu": False,
            }
            for i, ligne in enumerate(saisie["incidents"], 1)
        ],
        "blocages": [
            {
                **blocage,
                "numero": "BLC-01",
                "escalade": "CP"
                if blocage["niveau"] == "BLOQUANT"
                else "CT"
                if blocage["niveau"] == "SIGNIFICATIF"
                else None,
            }
        ]
        if blocage["niveau"] != "AUCUN"
        else [],
        "photos": [
            {
                **ligne,
                "url": ligne["fichier"],
                "heure": ligne["horodatage_utc"][11:16],
                "gps_confirme": ligne["latitude"] is not None and ligne["longitude"] is not None,
            }
            for ligne in saisie["photos"]
        ],
        "pieces_jointes": saisie["pieces_jointes"],
        "previsions": saisie["previsions"],
        "saisie": saisie,
        "enregistre_le": journal.modifie_le.isoformat(),
    }


ENTREE_CHAMPS = (
    "id",
    "reference",
    "date",
    "chantier",
    "lots",
    "statut",
    "effectif_present",
    "effectif_prevu",
    "avancement",
    "avancement_theorique",
    "nb_incidents",
    "nb_blocages",
    "nb_photos",
    "soumis_le",
    "dernier_rapport_le",
    "relance_le",
    "note_chef_chantier",
    "circuit",
)


def entree(journal, *, contexte=None):
    charge = document(journal, contexte=contexte)
    return {cle: charge[cle] for cle in ENTREE_CHAMPS}


def entree_manquante(projet, jour, contexte, *, dernier=None):
    return {
        "id": f"{projet.id}_{jour.isoformat()}",
        "reference": None,
        "date": jour.isoformat(),
        "chantier": {
            "projet_id": str(projet.id),
            "projet_nom": projet.nom,
            "projet_reference": projet.reference,
            "chef_chantier_nom": contexte["projet"]["chef_chantier_nom"],
        },
        "lots": contexte["lots"],
        "statut": "NON_SOUMIS",
        "effectif_present": None,
        "effectif_prevu": None,
        "avancement": None,
        "avancement_theorique": None,
        "nb_incidents": None,
        "nb_blocages": None,
        "nb_photos": None,
        "soumis_le": None,
        "dernier_rapport_le": dernier,
        "relance_le": None,
        "note_chef_chantier": None,
        "circuit": [],
    }


def journal_periode(request, debut, fin, *, projet_id=None):
    projets = projets_visibles(request).filter(statut__in=["EN_COURS", "EN_RETARD", "CRITIQUE"])
    if projet_id:
        projets = projets.filter(pk=projet_id)
        # Inclure aussi les projets achevés avec des rapports dans l'intervalle.
    qs = journaux_visibles(request).filter(rapport__date_rapport__range=[debut, fin])
    if projet_id:
        qs = qs.filter(rapport__projet_id=projet_id)
    rapports = list(qs)
    par_jour = {(j.rapport.projet_id, j.rapport.date_rapport): j for j in rapports}
    charges = []
    for projet in projets:
        contexte = contexte_projet(projet, fin)
        premier = max(
            debut,
            projet.date_debut_reelle
            or projet.date_debut_prevue
            or aujourdhui() - timedelta(days=2),
        )
        dernier = min(fin, aujourdhui(), projet.date_fin_reelle or fin)
        for offset in range(max(0, (dernier - premier).days + 1)):
            jour = premier + timedelta(days=offset)
            if jour.weekday() >= 5 and (projet.id, jour) not in par_jour:
                continue
            j = par_jour.pop((projet.id, jour), None)
            if j and (j.rapport.statut != "BROUILLON" or j.rapport.auteur_id == request.user.id):
                # Une photographie d'une soumission a priorité sur le contexte vivant.
                charges.append(entree(j, contexte=j.photographie or contexte))
            else:
                charges.append(entree_manquante(projet, jour, contexte))
    for j in par_jour.values():
        if j.rapport.statut != "BROUILLON" or j.rapport.auteur_id == request.user.id:
            charges.append(entree(j))
    return sorted(
        charges, key=lambda c: (c["date"], c["chantier"]["projet_reference"]), reverse=True
    )
