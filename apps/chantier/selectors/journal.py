"""Lectures et projections compatibles avec l'adaptateur du frontend."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q

from apps.accounts.models import Utilisateur
from apps.chantier.models import JournalChantier, RelanceJournal
from apps.chantier.services import signatures as circuit_signatures
from apps.chantier.services.equipes_journal import equipes_du_journal, feuilles_sans_equipe
from apps.chantier.services.fonctions import (
    APPROUVER,
    REDIGER,
    VALIDER,
    chemins_des_cases,
    titulaire_de,
    titulaires,
)
from apps.chantier.services.journal import (
    aujourdhui,
    cases_du_journal,
    premier_jour_rapport,
    statut_journal,
)
from apps.core.enums import ModeExecution
from apps.core.permissions import filtrer_queryset_par_affectations
from apps.projets.models import Projet
from apps.projets.services.calendrier_ouvre import calendrier_entreprise
from apps.projets.services.referentiels import (
    libelle_mode_execution,
    mode_base,
    table_modes_execution,
)

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


def noms_des_titulaires(projet, permission, chemins=()) -> str:
    """Les personnes qui tiennent la fonction sur la partie du projet, en clair."""
    return ", ".join(
        nom(t.utilisateur) for t in titulaires(projet, permission) if t.concerne(chemins)
    )


def contexte_projet(projet, jour, *, chemins=(), auteur=None):
    """Ce que le rédacteur saisit, sur sa partie du projet (`chemins` ; vide : tout le projet).

    Les intervenants sont ceux qui tiennent les fonctions du journal sur cette partie — par les
    permissions de leur rôle sur le projet, jamais par son nom (30/10/2026).
    """
    from apps.projets.services.avancement import quantites_synchronisees

    intervenants = {
        "CC": nom(auteur) if auteur else noms_des_titulaires(projet, REDIGER, chemins),
        "CT": noms_des_titulaires(projet, VALIDER, chemins),
        "CP": noms_des_titulaires(projet, APPROUVER, chemins),
    }
    # Une seule table code → (mode de base, libellé) pour toutes les cases du projet.
    table_modes = table_modes_execution()
    cases = cases_du_journal(projet, chemins)
    numeros = cases.arbre.numerotation()
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
    synchronisees = quantites_synchronisees(projet)
    charges_lots, charges_activites, sections = [], [], []
    for id_groupe, groupe in cases.groupes.items():
        mode = cases.mode(groupe)
        base = mode_base(mode, table_modes)
        code_groupe = groupe.code or numeros.get(groupe.pk) or ""
        charges_lots.append(
            {
                "id": id_groupe,
                "code": code_groupe,
                # Le chemin complet distingue deux cases homonymes sous des parents différents.
                "nom": " / ".join(cases.arbre.chemin_libelles(groupe)),
                # Le formulaire raisonne sur le mode de base ; le libellé garde le mode choisi.
                "mode_execution": "REGIE_DIRECTE" if base == ModeExecution.REGIE else base,
                "mode_execution_libelle": libelle_mode_execution(mode, table_modes),
                "projet_id": str(projet.id),
                "projet_nom": projet.nom,
                "projet_reference": projet.reference,
                "chef_chantier_nom": intervenants["CC"],
            }
        )
        for activite in cases.feuilles_par_groupe[id_groupe]:
            base_feuille = mode_base(cases.mode(activite), table_modes)
            for section in SECTIONS.get(base_feuille, []):
                if section not in sections:
                    sections.append(section)
            identifiant = str(activite.id)
            # La base de repli retire les quantités synchronisées pour ne pas imputer à la veille
            # des quantités déjà reportées par des rapports approuvés postérieurs au jour visé.
            base_repli = float(
                activite.quantite_realisee - synchronisees.get(identifiant, Decimal("0"))
            )
            charges_activites.append(
                {
                    "activite_id": identifiant,
                    "lot_id": id_groupe,
                    "suivi": "PRODUCTION"
                    if base_feuille == ModeExecution.SOUS_TRAITANCE_INFORMELLE
                    else "AVANCEMENT",
                    "code": activite.code or numeros.get(activite.pk) or "",
                    "libelle": activite.libelle,
                    "unite": activite.unite,
                    "quantite_prevue": float(activite.quantite_prevue or 0),
                    "cumul_veille": bases.get(identifiant, base_repli) + cumuls[identifiant],
                    "avancement_theorique": theorique(
                        activite.date_debut_prevue, activite.date_fin_prevue, jour
                    ),
                }
            )
    # Les équipes des tâches, et leurs membres ce jour (30/10/2026). Une tâche couverte par
    # une équipe garnie fait cocher ses présents au lieu des effectifs par catégorie.
    equipes = equipes_du_journal(cases, jour)
    if any(e["presence"] for e in equipes):
        sections.append("EQUIPES")
    for section, mode in (
        ("EFFECTIFS", ModeExecution.REGIE),
        ("PRESENCE_SOUS_TRAITANT", ModeExecution.SOUS_TRAITANCE_STRUCTUREE),
    ):
        if section in sections and not feuilles_sans_equipe(cases, equipes, mode):
            sections.remove(section)
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
        "equipes": equipes,
        # Pas de stock inventé : le module stocks n'a pas encore de modèle concret.
        "materiaux": [],
        "localisation": ", ".join(filter(None, [projet.quartier, projet.ville])),
        "conducteur_travaux_nom": intervenants["CT"],
        "chef_projet_nom": intervenants["CP"],
    }


#: Marque « non fourni » : `None` voudrait dire « pas de relance aujourd'hui ».
_A_LIRE = object()


def relances_du_jour(projet_ids, debut, fin) -> dict:
    """La relance envoyée aujourd'hui pour chaque ligne (chantier, rédacteur, jour) de la période.

    Seule celle du jour compte : une ligne relancée hier peut l'être de nouveau
    aujourd'hui (une relance par ligne et par jour), l'écran rend donc le bouton.
    Le rédacteur est vide sur un chantier sans rédacteur affecté.
    """
    return {
        (r.projet_id, r.redacteur_id, r.date_rapport): r.cree_le.isoformat()
        for r in RelanceJournal.objects.filter(
            projet_id__in=projet_ids, date_rapport__range=[debut, fin], jour=aujourdhui()
        )
    }


def cle_ligne(journal) -> tuple:
    r = journal.rapport
    return (r.projet_id, r.auteur_id, r.date_rapport)


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


def preparation(projet, jour, *, journal=None, precedent=None, utilisateur=None):
    if journal:
        chemins = chemins_des_cases(journal.perimetre_ids)
    else:
        redacteur = titulaire_de(projet, utilisateur, REDIGER)
        chemins = redacteur.chemins if redacteur else ()
    contexte = (
        journal.photographie
        if journal
        and journal.photographie
        and statut_journal(journal) not in ("BROUILLON", "REJETE")
        else contexte_projet(projet, jour, chemins=chemins, auteur=utilisateur)
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
            {
                **{k: ligne[k] for k in ("intervenant", "activite_id", "prix_unitaire")},
                "personne_id": ligne.get("personne_id"),
            }
            for ligne in saisie_precedente.get("production", [])
        ],
        # Les présents de la veille, à recocher.
        "equipes": [
            {"equipe_id": ligne["equipe_id"], "presents": ligne["presents"]}
            for ligne in saisie_precedente.get("equipes", [])
        ],
    }
    return {
        "aujourdhui": aujourdhui().isoformat(),
        **{k: contexte[k] for k in ("projet", "lots", "sections", "activites", "materiaux")},
        # Une photographie antérieure au 30/10/2026 n'a pas d'équipes.
        "equipes": contexte.get("equipes", []),
        "reprises": reprises,
        "rapport": existant(journal) if journal else None,
    }


def reference(journal):
    r = journal.rapport
    return f"RJ-{r.projet.reference}-{r.date_rapport:%Y%m%d}"


def _signataires(journal, etape, *, ouverte, rejete) -> list[dict]:
    """Chaque signataire attendu à l'étape, avec où il en est (30/10/2026 : tous signent)."""
    faites = {s["utilisateur_id"]: s for s in journal.signatures or [] if s["etape"] == etape}
    figes = (journal.signataires_attendus or {}).get(etape, [])
    effectifs = set(circuit_signatures.attendus_effectifs(journal, etape)) if figes else set()
    noms = {
        str(u.pk): nom(u)
        for u in Utilisateur.objects.filter(pk__in=[*figes, *faites]).only("prenom", "nom", "email")
    }
    lignes = []
    for uid in dict.fromkeys([*figes, *faites]):
        signature = faites.get(uid)
        if signature:
            etat = "SIGNE"
        elif uid not in effectifs:
            etat = "RETIRE"  # n'a plus la fonction sur le projet : n'est plus attendu
        elif rejete:
            etat = "REJETE"
        else:
            etat = "EN_ATTENTE" if ouverte else "A_VENIR"
        lignes.append(
            {
                "utilisateur_id": uid,
                "nom": signature["nom"] if signature else noms.get(uid, ""),
                "etat": etat,
                "signe_le": signature["signe_le"] if signature else None,
                "commentaire": signature["commentaire"] if signature else None,
            }
        )
    return lignes


def _etat_etape(lignes, *, close, ouverte, rejete) -> str:
    if close:
        return "SIGNE"
    if rejete:
        return "REJETE"
    return "EN_ATTENTE" if ouverte else "A_VENIR"


def circuit(journal, contexte):
    """Le rédacteur, puis tous les validateurs, puis tous les approbateurs (30/10/2026).

    Les clés `role` gardent les codes des étapes (CC, CT, CP) que l'écran connaît ; ceux qui
    signent sont ceux qui en ont la permission sur le projet, listés dans `signataires`.
    """
    r = journal.rapport
    statut = statut_journal(journal)
    cc_signe = bool(r.soumis_le)
    ct_signe = bool(journal.valide_ct_le)
    cp_signe = statut == "APPROUVE_CP"
    rejete = statut == "REJETE"
    echeance_ct = (r.soumis_le + timedelta(hours=24)).isoformat() if r.soumis_le else None
    echeance_cp = (
        (journal.valide_ct_le + timedelta(hours=24)).isoformat() if journal.valide_ct_le else None
    )
    validation = _signataires(
        journal, circuit_signatures.VALIDATION, ouverte=cc_signe and not ct_signe, rejete=rejete
    )
    approbation = _signataires(
        journal,
        circuit_signatures.APPROBATION,
        ouverte=ct_signe and not cp_signe,
        rejete=rejete and ct_signe,
    )
    return [
        {
            "role": "CC",
            "signataire_nom": nom(r.auteur),
            "etat": "SIGNE" if cc_signe else "EN_ATTENTE",
            "signe_le": r.soumis_le.isoformat() if r.soumis_le else None,
            "echeance": None,
            "commentaire": None,
            "signataires": [],
        },
        {
            "role": "CT",
            "signataire_nom": ", ".join(ligne["nom"] for ligne in validation)
            or contexte["conducteur_travaux_nom"],
            "etat": _etat_etape(
                validation,
                close=ct_signe,
                ouverte=cc_signe,
                rejete=rejete and not ct_signe,
            ),
            "signe_le": journal.valide_ct_le.isoformat() if ct_signe else None,
            "echeance": echeance_ct,
            "commentaire": r.commentaire_validation
            if rejete and not ct_signe
            else journal.commentaire_ct,
            "signataires": validation,
            # Validation sautée : personne n'avait la permission sur la partie du rapport.
            "sans_signataire": cc_signe and not validation,
        },
        {
            "role": "CP",
            "signataire_nom": ", ".join(ligne["nom"] for ligne in approbation)
            or contexte["chef_projet_nom"],
            "etat": _etat_etape(
                approbation, close=cp_signe, ouverte=ct_signe, rejete=rejete and ct_signe
            ),
            "signe_le": r.valide_le.isoformat() if cp_signe else None,
            "echeance": echeance_cp,
            "commentaire": r.commentaire_validation if cp_signe or (rejete and ct_signe) else None,
            "signataires": approbation,
            # Aucun approbateur affecté : le rapport attend qu'on en affecte un.
            "sans_signataire": ct_signe and not cp_signe and not approbation,
        },
    ]


def presences_equipes(saisie, contexte) -> list[dict]:
    """Les présents par équipe, avec les noms figés à la soumission."""
    equipes = {e["equipe_id"]: e for e in contexte.get("equipes", [])}
    lignes = []
    for ligne in saisie.get("equipes", []):
        equipe = equipes.get(ligne["equipe_id"])
        if equipe is None:
            continue
        noms = {m["personne_id"]: m["nom"] for m in equipe["membres"]}
        presents = set(ligne["presents"])
        lignes.append(
            {
                "equipe_id": ligne["equipe_id"],
                "nom": equipe["nom"],
                "entreprise": equipe["entreprise"],
                "presence": "PRESENT"
                if presents and len(presents) >= len(noms)
                else "PARTIEL"
                if presents
                else "ABSENT",
                "membres": len(noms),
                "presents": [noms.get(p, "") for p in ligne["presents"]],
                "absents": [n for p, n in noms.items() if p not in presents],
                "retards": [noms.get(p, "") for p in ligne["retards"]],
                "heures": ligne["heures"],
                "qualite": ligne["qualite"] or None,
                "observation": ligne["observation"],
            }
        )
    return lignes


def document(journal, *, contexte=None, relance_le=_A_LIRE):
    """Projection ChargeRapport, calculée sans requête par ligne de rubrique.

    `relance_le` : la relance du jour, déjà lue par l'appelant ; sinon lue ici.
    """
    r, saisie = journal.rapport, journal.saisie
    if relance_le is _A_LIRE:
        relance_le = relances_du_jour([r.projet_id], r.date_rapport, r.date_rapport).get(
            cle_ligne(journal)
        )
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
    equipes = presences_equipes(saisie, contexte)
    production = (
        [
            {
                "intervenant": ligne["intervenant"],
                "personne_id": ligne.get("personne_id"),
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
        "effectif_present": sum(ligne["presents"] or 0 for ligne in effectifs or [])
        + sum(len(e["presents"]) for e in equipes)
        if effectifs is not None or equipes
        else None,
        "effectif_prevu": sum(ligne["prevus"] or 0 for ligne in effectifs or [])
        + sum(e["membres"] for e in equipes)
        if effectifs is not None or equipes
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
        "relance_le": relance_le,
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
        "equipes": equipes,
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


def entree(journal, *, contexte=None, relance_le=_A_LIRE):
    charge = document(journal, contexte=contexte, relance_le=relance_le)
    return {cle: charge[cle] for cle in ENTREE_CHAMPS}


def identifiant_ligne(projet, jour, redacteur=None) -> str:
    """L'identifiant d'un rapport manquant : `{projet}_{jour}`, suivi du rédacteur s'il y en a un."""
    base = f"{projet.id}_{jour.isoformat()}"
    return f"{base}_{redacteur.pk}" if redacteur else base


def entree_manquante(projet, jour, contexte, *, dernier=None, relance_le=None, redacteur=None):
    return {
        "id": identifiant_ligne(projet, jour, redacteur),
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
        "relance_le": relance_le,
        "note_chef_chantier": None,
        "circuit": [],
    }


def journal_periode(request, debut, fin, *, projet_id=None, brouillons_visibles=True):
    """Les lignes du journal, rapports manquants compris.

    `brouillons_visibles` : l'auteur d'un brouillon le voit dans son journal ;
    une synthèse, elle, doit lire la même chose quel que soit son lecteur, et
    passe `False` — un brouillon y compte pour un rapport manquant.
    """
    lecteur = request.user.id if brouillons_visibles else None
    projets = projets_visibles(request).filter(statut__in=["EN_COURS", "EN_RETARD", "CRITIQUE"])
    if projet_id:
        projets = projets.filter(pk=projet_id)
        # Inclure aussi les projets achevés avec des rapports dans l'intervalle.
    qs = journaux_visibles(request).filter(rapport__date_rapport__range=[debut, fin])
    if projet_id:
        qs = qs.filter(rapport__projet_id=projet_id)
    rapports = list(qs)
    # Une ligne par rédacteur et par jour (30/10/2026) : chacun écrit son rapport.
    par_ligne = {cle_ligne(j): j for j in rapports}
    relances = relances_du_jour(
        {p.id for p in projets} | {j.rapport.projet_id for j in rapports}, debut, fin
    )
    charges = []
    cal = calendrier_entreprise(debut, fin)
    for projet in projets:
        # Sans rédacteur affecté, le chantier attend quand même son rapport : une ligne anonyme.
        attendus = [
            (t.utilisateur, contexte_projet(projet, fin, chemins=t.chemins, auteur=t.utilisateur))
            for t in titulaires(projet, REDIGER)
        ] or [(None, contexte_projet(projet, fin))]
        premier = max(debut, premier_jour_rapport(projet))
        dernier = min(fin, aujourdhui(), projet.date_fin_reelle or fin)
        for offset in range(max(0, (dernier - premier).days + 1)):
            jour = premier + timedelta(days=offset)
            for redacteur, contexte in attendus:
                cle = (projet.id, redacteur.pk if redacteur else None, jour)
                if not cal.est_ouvre(jour) and cle not in par_ligne:
                    continue
                j = par_ligne.pop(cle, None)
                if j and (j.rapport.statut != "BROUILLON" or j.rapport.auteur_id == lecteur):
                    # Une photographie d'une soumission a priorité sur le contexte vivant.
                    charges.append(
                        entree(j, contexte=j.photographie or contexte, relance_le=relances.get(cle))
                    )
                else:
                    charges.append(
                        entree_manquante(
                            projet,
                            jour,
                            contexte,
                            relance_le=relances.get(cle),
                            redacteur=redacteur,
                        )
                    )
    for j in par_ligne.values():
        if j.rapport.statut != "BROUILLON" or j.rapport.auteur_id == lecteur:
            charges.append(entree(j, relance_le=relances.get(cle_ligne(j))))
    return sorted(
        charges, key=lambda c: (c["date"], c["chantier"]["projet_reference"]), reverse=True
    )
