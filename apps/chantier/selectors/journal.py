"""Lectures et projections du journal de chantier (arbre, équipes, calendrier ouvré et F3)."""

from collections import OrderedDict, defaultdict
from copy import copy
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q

from apps.accounts.models import Utilisateur
from apps.chantier.models import Blocage, JournalChantier, RelanceJournal
from apps.chantier.services import signatures as circuit_signatures
from apps.chantier.services.equipes_journal import equipes_du_journal, equipes_par_feuille
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
    est_jour_ouvre_entreprise,
    jours_saisissables_ouvres,
    migrer_saisie_ancienne,
    premier_jour_rapport,
    statut_journal,
)
from apps.core.enums import ModeExecution, StatutActivite, StatutBlocage
from apps.core.permissions import filtrer_queryset_par_affectations
from apps.projets.models import ModeMesure, Projet
from apps.projets.selectors.arbre import Arbre, charger_arbre
from apps.projets.services.calendrier_ouvre import Calendrier, calendrier_entreprise
from apps.projets.services.meteo import meteo_suggeree_journal
from apps.projets.services.referentiels import (
    libelle_mode_execution,
    mode_base,
    table_modes_execution,
)
from apps.projets.services.sante_calculs import (
    calculer_arbre,
    calculer_avancement_physique_feuille,
    calculer_avancement_temporel_element,
    calculer_temporels_arbre,
    resultat_projet,
)

SECTIONS_UNIFIEES = ["AVANCEMENT", "MATERIAUX", "LIVRAISONS", "EQUIPEMENTS"]


def nom(utilisateur) -> str:
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
    if statut in ("VALIDE", "VALIDE_CT"):
        qs = qs.filter(rapport__statut="SOUMIS", valide_ct_le__isnull=False)
    elif statut == "SOUMIS":
        qs = qs.filter(rapport__statut="SOUMIS", valide_ct_le__isnull=True)
    elif statut:
        qs = qs.filter(
            rapport__statut="APPROUVE" if statut in ("APPROUVE", "APPROUVE_CP") else statut
        )
    return qs.order_by("-rapport__date_rapport", "-modifie_le")


def _calendrier_autour_arbre(arbre: Arbre, jour: date) -> Calendrier:
    annees = {jour.year - 1, jour.year, jour.year + 1}
    for e in arbre.elements:
        for d in (
            e.date_debut_baseline,
            e.date_fin_baseline,
            e.date_debut_prevue,
            e.date_fin_prevue,
        ):
            if d is not None:
                annees.add(d.year)
    return calendrier_entreprise(date(min(annees), 1, 1), date(max(annees), 12, 31))


def noms_des_titulaires(projet, permission, chemins=()) -> str:
    """Les personnes qui tiennent la fonction sur la partie du projet, en clair."""
    return ", ".join(
        nom(t.utilisateur) for t in titulaires(projet, permission) if t.concerne(chemins)
    )


def contexte_projet(
    projet,
    jour: date,
    *,
    chemins=(),
    auteur=None,
    previsions_veille_ids: set[str] | None = None,
):
    """Ce que le rédacteur saisit, sur sa partie du projet (`chemins` ; vide : tout le projet)."""
    from apps.projets.services.avancement import quantites_synchronisees

    intervenants = {
        "REDACTION": nom(auteur) if auteur else noms_des_titulaires(projet, REDIGER, chemins),
        "VALIDATION": noms_des_titulaires(projet, VALIDER, chemins),
        "APPROBATION": noms_des_titulaires(projet, APPROUVER, chemins),
    }
    table_modes = table_modes_execution()
    cases = cases_du_journal(projet, chemins)
    numeros = cases.arbre.numerotation()
    cal = _calendrier_autour_arbre(cases.arbre, jour)
    aff_feuilles = equipes_par_feuille(cases)
    prev_ids = set(previsions_veille_ids or ())

    # Seuls les rapports validés ou approuvés alimentent les cumuls de référence (A5).
    cumuls_q = defaultdict(float)
    cumuls_pct = defaultdict(float)
    bases_q = {}
    precedents = (
        JournalChantier.objects.filter(
            rapport__projet=projet,
            rapport__date_rapport__lt=jour,
            rapport__supprime_le__isnull=True,
        )
        .filter(
            Q(rapport__statut="APPROUVE") | Q(rapport__statut="SOUMIS", valide_ct_le__isnull=False)
        )
        .order_by("rapport__date_rapport")
        .values_list("saisie", "photographie")
    )
    for s_prec, photo_prec in precedents:
        for act_photo in (photo_prec or {}).get("activites", []):
            bases_q.setdefault(str(act_photo["activite_id"]), act_photo.get("cumul_veille") or 0)
        for ligne in (s_prec or {}).get("activites", []) + (s_prec or {}).get("production", []):
            aid = str(ligne.get("activite_id") or "")
            if not aid:
                continue
            cumuls_q[aid] += ligne.get("quantite_jour") or 0
            if ligne.get("pourcentage_jour") is not None:
                cumuls_pct[aid] = max(cumuls_pct[aid], float(ligne["pourcentage_jour"]))

    # Vérifier si des rapports approuvés existent >= jour pour ne pas imputer le futur à la veille
    approuves_ulterieurs = set()
    for s_ult in JournalChantier.objects.filter(
        rapport__projet=projet,
        rapport__date_rapport__gte=jour,
        rapport__supprime_le__isnull=True,
        rapport__statut="APPROUVE",
    ).values_list("saisie", flat=True):
        for ligne in (s_ult or {}).get("activites", []):
            if ligne.get("activite_id"):
                approuves_ulterieurs.add(str(ligne["activite_id"]))

    synchronisees = quantites_synchronisees(projet)
    aucune_date_arbre = all(f.date_debut_prevue is None for f in cases.feuilles.values())

    charges_lots, charges_activites = [], []
    sections = list(SECTIONS_UNIFIEES) if cases.feuilles else []

    for id_groupe, groupe in cases.groupes.items():
        mode = cases.mode(groupe)
        base = mode_base(mode, table_modes)
        code_groupe = groupe.code or numeros.get(groupe.pk) or ""
        charges_lots.append(
            {
                "id": id_groupe,
                "code": code_groupe,
                "nom": " / ".join(cases.arbre.chemin_libelles(groupe)),
                "mode_execution": "REGIE_DIRECTE" if base == ModeExecution.REGIE else base,
                "mode_execution_libelle": libelle_mode_execution(mode, table_modes),
                "projet_id": str(projet.id),
                "projet_nom": projet.nom,
                "projet_reference": projet.reference,
                "redacteur_nom": intervenants["REDACTION"],
            }
        )
        for activite in cases.feuilles_par_groupe[id_groupe]:
            identifiant = str(activite.id)
            mode_m = activite.mode_mesure or ModeMesure.QUANTITE
            base_repli = max(
                0.0,
                float(
                    (activite.quantite_realisee or Decimal("0"))
                    - synchronisees.get(identifiant, Decimal("0"))
                ),
            )
            pct_base = (
                0.0
                if identifiant in approuves_ulterieurs
                else float(activite.pourcentage_declare or 0)
            )
            pct_veille = round(max(pct_base, cumuls_pct[identifiant]), 2)
            attendue = bool(
                (activite.date_debut_prevue is not None and activite.date_debut_prevue <= jour)
                or cases.arbre.commence(activite)
                or identifiant in prev_ids
                or aucune_date_arbre
            )
            theo = calculer_avancement_temporel_element(activite, jour, cal) or 0.0
            charges_activites.append(
                {
                    "activite_id": identifiant,
                    "lot_id": id_groupe,
                    "mode_mesure": mode_m,
                    "code": activite.code or numeros.get(activite.pk) or "",
                    "libelle": activite.libelle,
                    "chemin_libelle": " / ".join(cases.arbre.chemin_libelles(activite)),
                    "unite": activite.unite,
                    "quantite_prevue": float(activite.quantite_prevue or 0),
                    "cumul_veille": round(
                        bases_q.get(identifiant, base_repli) + cumuls_q[identifiant], 3
                    ),
                    "pourcentage_veille": pct_veille,
                    "avancement_theorique": theo,
                    "equipes_affectees": aff_feuilles.get(identifiant, []),
                    "attendue_ce_jour": attendue,
                }
            )

    equipes = equipes_du_journal(cases, jour)
    if any(e["presence"] for e in equipes):
        sections.append("EQUIPES")

    return {
        "projet": {
            "id": str(projet.id),
            "nom": projet.nom,
            "reference": projet.reference,
            "redacteur_nom": intervenants["REDACTION"],
        },
        "lots": charges_lots,
        "sections": sections,
        "activites": charges_activites,
        "equipes": equipes,
        "materiaux": [],
        "localisation": ", ".join(filter(None, [projet.quartier, projet.ville])),
        "validateurs_nom": intervenants["VALIDATION"],
        "approbateurs_nom": intervenants["APPROBATION"],
    }


#: Marque « non fourni » : `None` voudrait dire « pas de relance aujourd'hui ».
_A_LIRE = object()


def relances_du_jour(projet_ids, debut, fin) -> dict:
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
    statut = statut_journal(journal)
    saisie = (
        migrer_saisie_ancienne(journal.saisie)
        if statut in ("BROUILLON", "REJETE")
        else journal.saisie
    )
    return {
        "id": str(journal.rapport_id),
        "statut": statut,
        "saisie": saisie,
        "enregistre_le": journal.modifie_le.isoformat(),
        "commentaire_rejet": journal.rapport.commentaire_validation
        if journal.rapport.statut == "REJETE"
        else None,
        "alertes_envoyees": [a.cle for a in journal.alertes.all()],
    }


def blocages_ouverts_projet(projet) -> list[dict]:
    """Les blocages toujours actifs sur le chantier, rappelés au rédacteur."""
    qs = (
        Blocage.objects.filter(
            projet=projet,
            statut__in=[StatutBlocage.OUVERT, StatutBlocage.PRIS_EN_CHARGE],
            supprime_le__isnull=True,
        )
        .select_related("element")
        .order_by("-ouvert_le")[:25]
    )
    return [
        {
            "id": str(b.id),
            "titre": b.titre,
            "severite": b.severite,
            "statut": b.statut,
            "element_id": str(b.element_id) if b.element_id else None,
            "element_libelle": b.element.libelle if b.element else None,
            "ouvert_le": b.ouvert_le.isoformat(),
        }
        for b in qs
    ]


def _normaliser_contexte_lu(contexte: dict) -> dict:
    """Assure la compatibilité des photographies figées avant la refonte."""
    c = dict(contexte)
    proj = dict(c.get("projet") or {})
    if "redacteur_nom" not in proj:
        proj["redacteur_nom"] = proj.get("chef_chantier_nom") or ""
    c["projet"] = proj
    if "validateurs_nom" not in c:
        c["validateurs_nom"] = c.get("conducteur_travaux_nom") or ""
    if "approbateurs_nom" not in c:
        c["approbateurs_nom"] = c.get("chef_projet_nom") or ""
    lots = []
    for lot in c.get("lots") or []:
        copie_lot = dict(lot)
        if "redacteur_nom" not in copie_lot:
            copie_lot["redacteur_nom"] = copie_lot.get("chef_chantier_nom") or proj["redacteur_nom"]
        lots.append(copie_lot)
    c["lots"] = lots
    acts = []
    for act in c.get("activites") or []:
        copie_act = dict(act)
        copie_act.setdefault("mode_mesure", "QUANTITE")
        copie_act.setdefault("chemin_libelle", copie_act.get("libelle", ""))
        copie_act.setdefault("pourcentage_veille", 0.0)
        copie_act.setdefault("equipes_affectees", [])
        copie_act.setdefault("attendue_ce_jour", True)
        acts.append(copie_act)
    c["activites"] = acts
    return c


def preparation(projet, jour: date, *, journal=None, precedent=None, utilisateur=None):
    if journal:
        chemins = chemins_des_cases(journal.perimetre_ids)
    else:
        redacteur = titulaire_de(projet, utilisateur, REDIGER)
        chemins = redacteur.chemins if redacteur else ()

    saisie_precedente = migrer_saisie_ancienne(precedent.saisie) if precedent else {}
    previsions_veille = [
        {
            "activite_id": p.get("activite_id"),
            "equipe_id": p.get("equipe_id"),
            "activite": p.get("activite") or "",
            "equipe": p.get("equipe") or "",
            "objectif": p.get("objectif") or "",
            "prerequis": p.get("prerequis") or "",
        }
        for p in saisie_precedente.get("previsions", [])
    ]
    prev_ids = {str(p["activite_id"]) for p in previsions_veille if p.get("activite_id")}

    contexte = (
        _normaliser_contexte_lu(journal.photographie)
        if journal
        and journal.photographie
        and statut_journal(journal) not in ("BROUILLON", "REJETE")
        else contexte_projet(
            projet,
            jour,
            chemins=chemins,
            auteur=utilisateur,
            previsions_veille_ids=prev_ids,
        )
    )

    reprises = {
        "equipements": [
            {
                "designation": ligne.get("designation") or "",
                "reference": ligne.get("reference") or "",
                "propriete": ligne.get("propriete") or "",
                "operateur": ligne.get("operateur") or "",
                "usage": ligne.get("usage") or "",
            }
            for ligne in saisie_precedente.get("equipements", [])
        ],
        "equipes": [
            {
                "equipe_id": str(ligne["equipe_id"]),
                "presents": [str(p) for p in ligne.get("presents", [])],
            }
            for ligne in saisie_precedente.get("equipes", [])
        ],
    }

    return {
        "aujourdhui": aujourdhui().isoformat(),
        "est_jour_ouvre": est_jour_ouvre_entreprise(jour),
        "jours_saisissables": [d.isoformat() for d in jours_saisissables_ouvres()],
        "meteo_suggeree": meteo_suggeree_journal(projet.ville),
        "previsions_veille": previsions_veille,
        "blocages_ouverts": blocages_ouverts_projet(projet),
        **{k: contexte[k] for k in ("projet", "lots", "sections", "activites", "materiaux")},
        "equipes": contexte.get("equipes", []),
        "reprises": reprises,
        "rapport": existant(journal) if journal else None,
    }


def reference(journal):
    r = journal.rapport
    return f"RJ-{r.projet.reference}-{r.date_rapport:%Y%m%d}"


def _signataires(journal, etape, *, ouverte, rejete) -> list[dict]:
    r = journal.rapport
    rejete_par_id = str(r.valide_par_id) if rejete and r.valide_par_id else None
    faites = {s["utilisateur_id"]: s for s in journal.signatures or [] if s["etape"] == etape}
    figes = (journal.signataires_attendus or {}).get(etape, [])
    effectifs = set(circuit_signatures.attendus_effectifs(journal, etape)) if figes else set()
    ids = list(dict.fromkeys([*figes, *faites, *([rejete_par_id] if rejete_par_id else [])]))
    noms = {
        str(u.pk): nom(u)
        for u in Utilisateur.objects.filter(pk__in=ids).only("prenom", "nom", "email")
    }
    lignes = []
    for uid in ids:
        signature = faites.get(uid)
        est_rejeteur = rejete and (rejete_par_id == uid if rejete_par_id else True)
        if signature:
            etat = "SIGNE"
        elif est_rejeteur:
            etat = "REJETE"
        elif uid not in effectifs:
            etat = "RETIRE"
        else:
            etat = "EN_ATTENTE" if ouverte else "A_VENIR"
        lignes.append(
            {
                "utilisateur_id": uid,
                "nom": signature["nom"] if signature else noms.get(uid, ""),
                "etat": etat,
                "signe_le": (
                    signature["signe_le"]
                    if signature
                    else (r.valide_le.isoformat() if est_rejeteur and r.valide_le else None)
                ),
                "commentaire": (
                    signature["commentaire"]
                    if signature
                    else (
                        r.commentaire_validation
                        if est_rejeteur and r.commentaire_validation
                        else None
                    )
                ),
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
    """Circuit en 3 étapes gouvernées par permission : REDACTION -> VALIDATION -> APPROBATION."""
    r = journal.rapport
    statut = statut_journal(journal)
    redaction_signee = bool(r.soumis_le)
    validation_signee = bool(journal.valide_ct_le)
    approbation_signee = statut == "APPROUVE"
    rejete = statut == "REJETE"
    rejete_validation = rejete and not validation_signee
    rejete_approbation = rejete and validation_signee
    echeance_val = (r.soumis_le + timedelta(hours=24)).isoformat() if r.soumis_le else None
    echeance_app = (
        (journal.valide_ct_le + timedelta(hours=24)).isoformat() if journal.valide_ct_le else None
    )
    validation = _signataires(
        journal,
        circuit_signatures.VALIDATION,
        ouverte=redaction_signee and not validation_signee and not rejete,
        rejete=rejete_validation,
    )
    approbation = _signataires(
        journal,
        circuit_signatures.APPROBATION,
        ouverte=validation_signee and not approbation_signee and not rejete,
        rejete=rejete_approbation,
    )
    return [
        {
            "role": "REDACTION",
            "signataire_nom": nom(r.auteur),
            "etat": "SIGNE" if redaction_signee else "EN_ATTENTE",
            "signe_le": r.soumis_le.isoformat() if r.soumis_le else None,
            "echeance": None,
            "commentaire": None,
            "signataires": [],
        },
        {
            "role": "VALIDATION",
            "signataire_nom": ", ".join(ligne["nom"] for ligne in validation)
            or contexte["validateurs_nom"],
            "etat": _etat_etape(
                validation,
                close=validation_signee,
                ouverte=redaction_signee,
                rejete=rejete_validation,
            ),
            "signe_le": (
                journal.valide_ct_le.isoformat()
                if validation_signee
                else (r.valide_le.isoformat() if rejete_validation and r.valide_le else None)
            ),
            "echeance": echeance_val,
            "commentaire": r.commentaire_validation
            if rejete_validation
            else journal.commentaire_ct,
            "signataires": validation,
            "sans_signataire": redaction_signee and not validation,
        },
        {
            "role": "APPROBATION",
            "signataire_nom": ", ".join(ligne["nom"] for ligne in approbation)
            or contexte["approbateurs_nom"],
            "etat": _etat_etape(
                approbation,
                close=approbation_signee,
                ouverte=validation_signee,
                rejete=rejete_approbation,
            ),
            "signe_le": (
                r.valide_le.isoformat()
                if (approbation_signee or rejete_approbation) and r.valide_le
                else None
            ),
            "echeance": echeance_app,
            "commentaire": r.commentaire_validation
            if approbation_signee or rejete_approbation
            else None,
            "signataires": approbation,
            "sans_signataire": validation_signee and not approbation_signee and not approbation,
        },
    ]


def presences_equipes(saisie, contexte) -> list[dict]:
    """Les présents par équipe, avec les noms figés à la soumission."""
    equipes = {str(e["equipe_id"]): e for e in contexte.get("equipes", [])}
    lignes = []
    for ligne in saisie.get("equipes", []):
        eid = str(ligne["equipe_id"])
        equipe = equipes.get(eid)
        if equipe is None:
            continue
        noms = {str(m["personne_id"]): m["nom"] for m in equipe["membres"]}
        presents_ids = [str(p) for p in ligne.get("presents", [])]
        retards_ids = [str(p) for p in ligne.get("retards", [])]
        presents_set = set(presents_ids)
        lignes.append(
            {
                "equipe_id": eid,
                "nom": equipe["nom"],
                "entreprise": equipe.get("entreprise") or "",
                "presence": "PRESENT"
                if presents_set and len(presents_set) >= len(noms)
                else "PARTIEL"
                if presents_set
                else "ABSENT",
                "membres": len(noms),
                "presents": [noms.get(p, "") for p in presents_ids],
                "absents": [n for p, n in noms.items() if p not in presents_set],
                "retards": [noms.get(p, "") for p in retards_ids],
                "heures": ligne.get("heures"),
                "qualite": ligne.get("qualite") or None,
                "observation": ligne.get("observation") or "",
            }
        )
    return lignes


def _arbre_simule_au_soir(
    arbre_source: Arbre, contexte: dict, mesures_saisie: dict[str, dict]
) -> Arbre:
    """Clone les feuilles de `arbre_source` en mémoire avec les cumuls au soir du rapport."""
    activites_ctx = {str(a["activite_id"]): a for a in contexte.get("activites", [])}
    elements_clones = []
    for elem in arbre_source.elements:
        copie_elem = copy(elem)
        aid = str(elem.pk)
        if aid in activites_ctx:
            ctx = activites_ctx[aid]
            m = mesures_saisie.get(aid, {})
            mode_m = ctx.get("mode_mesure") or elem.mode_mesure or ModeMesure.QUANTITE
            copie_elem.mode_mesure = mode_m
            if mode_m == ModeMesure.POURCENTAGE:
                pct_soir = m.get("pourcentage_jour")
                if pct_soir is None:
                    pct_soir = ctx.get("pourcentage_veille") or 0.0
                copie_elem.pourcentage_declare = Decimal(str(pct_soir))
                copie_elem.cloture = float(pct_soir) >= 100.0
            elif mode_m == ModeMesure.JALON:
                atteint = bool(m.get("jalon_atteint")) or bool(elem.cloture)
                copie_elem.cloture = atteint
                if not atteint and copie_elem.statut == StatutActivite.CLOTURE:
                    copie_elem.statut = StatutActivite.EN_COURS
            else:
                q_soir = (ctx.get("cumul_veille") or 0.0) + (m.get("quantite_jour") or 0.0)
                copie_elem.quantite_realisee = Decimal(str(round(q_soir, 3)))
                copie_elem.cloture = False
                if copie_elem.statut == StatutActivite.CLOTURE:
                    copie_elem.statut = StatutActivite.EN_COURS
        elements_clones.append(copie_elem)
    return Arbre(
        projet=arbre_source.projet,
        elements=elements_clones,
        niveaux=arbre_source.niveaux,
        actifs_seulement=arbre_source.actifs_seulement,
    )


def _agreger_materiaux_et_livraisons(saisie: dict) -> list[dict]:
    """Fusionne matériaux consommés et livraisons reçues par `(designation, unite)`."""
    table: OrderedDict[tuple[str, str], dict] = OrderedDict()

    def cle_mat(des: str, uni: str) -> tuple[str, str]:
        return (des.strip().lower(), uni.strip().lower())

    for ligne in saisie.get("materiaux", []):
        des = (ligne.get("designation") or "").strip()
        uni = (ligne.get("unite") or "").strip()
        if not des:
            continue
        entree = table.setdefault(
            cle_mat(des, uni),
            {
                "designation": des,
                "unite": uni,
                "stock_debut": None,
                "livre": 0.0,
                "utilise": 0.0,
                "seuil_alerte": None,
            },
        )
        entree["utilise"] = round(
            entree["utilise"] + float(ligne.get("quantite_consommee") or 0), 3
        )

    for liv in saisie.get("livraisons", []):
        des = (liv.get("designation") or "").strip()
        uni = (liv.get("unite") or "").strip()
        q = liv.get("quantite")
        if not des or not isinstance(q, int | float) or isinstance(q, bool):
            continue
        entree = table.setdefault(
            cle_mat(des, uni),
            {
                "designation": des,
                "unite": uni,
                "stock_debut": None,
                "livre": 0.0,
                "utilise": 0.0,
                "seuil_alerte": None,
            },
        )
        entree["livre"] = round(entree["livre"] + float(q), 3)

    return list(table.values())


def document(
    journal,
    *,
    contexte=None,
    relance_le=_A_LIRE,
    arbre: Arbre | None = None,
    calendrier: Calendrier | None = None,
):
    """Projection `ChargeRapport` complète, compatible avec les rapports historiques."""
    r = journal.rapport
    brut = journal.saisie or {}
    saisie = migrer_saisie_ancienne(brut)
    effectifs_historiques = brut.get("effectifs") if "effectifs" in brut else None

    if relance_le is _A_LIRE:
        relance_le = relances_du_jour([r.projet_id], r.date_rapport, r.date_rapport).get(
            cle_ligne(journal)
        )
    contexte_brut = contexte or journal.photographie or contexte_projet(r.projet, r.date_rapport)
    contexte = _normaliser_contexte_lu(contexte_brut)

    arbre_base = arbre or charger_arbre(r.projet)
    cal = calendrier or _calendrier_autour_arbre(arbre_base, r.date_rapport)
    libelles_arbre = {str(e.pk): e.libelle for e in arbre_base.elements}
    noms_equipes = {str(e["equipe_id"]): e["nom"] for e in contexte.get("equipes", [])}

    mesures_par_act: dict[str, dict] = {}
    for ligne in saisie.get("activites", []):
        aid = str(ligne["activite_id"])
        mesures_par_act[aid] = ligne

    points = {
        str(ligne["lot_id"]): ligne.get("observation") or ""
        for ligne in saisie.get("lots_travailles", [])
    }
    lots = [
        ligne
        for ligne in contexte["lots"]
        if ligne["id"] in points
        or any(
            a["lot_id"] == ligne["id"] and a["activite_id"] in mesures_par_act
            for a in contexte["activites"]
        )
    ]

    arbre_soir = _arbre_simule_au_soir(arbre_base, contexte, mesures_par_act)
    resultats_f3 = calculer_arbre(arbre_soir)
    temporels_f3 = calculer_temporels_arbre(arbre_soir, resultats_f3, r.date_rapport, cal)
    clones_par_str = {str(e.pk): e for e in arbre_soir.elements}

    travaux = []
    for lot in lots:
        toutes = [a for a in contexte["activites"] if a["lot_id"] == lot["id"]]
        lignes = []
        for a in toutes:
            aid = a["activite_id"]
            if aid not in mesures_par_act:
                continue
            m = mesures_par_act[aid]
            lignes.append(
                {
                    "activite_id": aid,
                    "libelle": a["libelle"],
                    "mode_mesure": a.get("mode_mesure", "QUANTITE"),
                    "unite": a["unite"],
                    "quantite_prevue": a["quantite_prevue"],
                    "cumul_veille": a["cumul_veille"],
                    "quantite_jour": m.get("quantite_jour") or 0,
                    "pourcentage_veille": a.get("pourcentage_veille", 0.0),
                    "pourcentage_jour": m.get("pourcentage_jour"),
                    "jalon_atteint": bool(m.get("jalon_atteint")),
                    "avancement_theorique": a["avancement_theorique"],
                    "equipes_noms": [
                        noms_equipes[str(eid)]
                        for eid in m.get("equipe_ids", [])
                        if str(eid) in noms_equipes
                    ],
                    "localisation": m.get("localisation") or "",
                    "observation": m.get("observation") or None,
                }
            )

        lot_elem = clones_par_str.get(lot["id"])
        res_lot = resultats_f3.get(lot_elem.pk) if lot_elem else None
        theo_lot = temporels_f3.get(lot_elem.pk) if lot_elem else None

        if res_lot and res_lot.physique is not None:
            av_lot = round(float(res_lot.physique), 2)
        elif toutes:
            # Repli non pondéré uniquement si aucun montant n'est renseigné sur les feuilles
            vals = [
                calculer_avancement_physique_feuille(clones_par_str[a["activite_id"]])
                if a["activite_id"] in clones_par_str
                else 0.0
                for a in toutes
            ]
            av_lot = round(sum(vals) / len(vals), 2)
        else:
            av_lot = 0.0

        if theo_lot is not None:
            av_theo_lot = round(float(theo_lot), 2)
        elif toutes:
            av_theo_lot = round(sum(a["avancement_theorique"] for a in toutes) / len(toutes), 2)
        else:
            av_theo_lot = 0.0

        travaux.append(
            {
                "lot": lot,
                "avancement": av_lot,
                "avancement_theorique": av_theo_lot,
                "observation": points.get(lot["id"]),
                "activites": lignes,
            }
        )

    res_projet = resultat_projet(r.projet, arbre_soir, resultats_f3)
    if saisie["arret"]:
        av_rapport = None
        av_theo_rapport = None
    elif travaux:
        if res_projet.physique is not None and not journal.perimetre_ids:
            av_rapport = round(float(res_projet.physique), 2)
        else:
            av_rapport = round(sum(t["avancement"] for t in travaux) / len(travaux), 2)
        av_theo_rapport = round(sum(t["avancement_theorique"] for t in travaux) / len(travaux), 2)
    else:
        av_rapport = None
        av_theo_rapport = None

    equipes = presences_equipes(saisie, contexte)
    effectifs = effectifs_historiques if effectifs_historiques and not saisie["arret"] else None
    personnes_uniques = {
        str(p) for l_eq in saisie.get("equipes", []) for p in l_eq.get("presents", [])
    }
    membres_uniques_prevus = {
        str(m["personne_id"])
        for e_ctx in contexte.get("equipes", [])
        if any(
            str(l_eq["equipe_id"]) == str(e_ctx["equipe_id"]) for l_eq in saisie.get("equipes", [])
        )
        for m in e_ctx.get("membres", [])
    }

    eff_present = (
        sum(item.get("presents") or 0 for item in effectifs or []) + len(personnes_uniques)
        if effectifs is not None or equipes
        else None
    )
    eff_prevu = (
        sum(item.get("prevus") or 0 for item in effectifs or []) + len(membres_uniques_prevus)
        if effectifs is not None or equipes
        else None
    )

    blocages_proj = [
        {
            **b,
            "numero": f"BLC-{i:02d}",
            "element_libelle": libelles_arbre.get(str(b["element_id"]))
            if b.get("element_id")
            else None,
            "escalade": "APPROBATION"
            if b["niveau"] == "BLOQUANT"
            else "VALIDATION"
            if b["niveau"] == "SIGNIFICATIF"
            else None,
        }
        for i, b in enumerate(saisie.get("blocages", []), start=1)
    ]

    return {
        "id": str(r.id),
        "reference": reference(journal) if r.soumis_le else None,
        "date": r.date_rapport.isoformat(),
        "chantier": {
            "projet_id": str(r.projet_id),
            "projet_nom": contexte["projet"]["nom"],
            "projet_reference": contexte["projet"]["reference"],
            "redacteur_nom": nom(r.auteur),
        },
        "lots": lots,
        "statut": statut_journal(journal),
        "effectif_present": eff_present,
        "effectif_prevu": eff_prevu,
        "avancement": av_rapport,
        "avancement_theorique": av_theo_rapport,
        "nb_incidents": len(saisie["incidents"]),
        "nb_blocages": len(blocages_proj),
        "nb_photos": len(saisie["photos"]),
        "soumis_le": r.soumis_le.isoformat() if r.soumis_le else None,
        "dernier_rapport_le": None,
        "relance_le": relance_le,
        "note_redacteur": saisie["note_redacteur"],
        "circuit": circuit(journal, contexte),
        "localisation": contexte["localisation"],
        "validateurs_nom": contexte["validateurs_nom"],
        "approbateurs_nom": contexte["approbateurs_nom"],
        "heure_debut": saisie["heure_debut"],
        "heure_fin": saisie["heure_fin"],
        "arret": saisie["arret"],
        "meteo": saisie["meteo"],
        "effectifs": effectifs,
        "equipes": equipes,
        "travaux": travaux,
        "materiaux": _agreger_materiaux_et_livraisons(saisie),
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
        "blocages": blocages_proj,
        "photos": [
            {
                **ligne,
                "element_libelle": libelles_arbre.get(str(ligne["element_id"]))
                if ligne.get("element_id")
                else None,
                "url": ligne["fichier"],
                "heure": str(ligne["horodatage_utc"])[11:16],
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
    "note_redacteur",
    "circuit",
)


def entree(journal, *, contexte=None, relance_le=_A_LIRE, arbre=None, calendrier=None):
    charge = document(
        journal,
        contexte=contexte,
        relance_le=relance_le,
        arbre=arbre,
        calendrier=calendrier,
    )
    return {cle: charge[cle] for cle in ENTREE_CHAMPS}


def identifiant_ligne(projet, jour, redacteur=None) -> str:
    base = f"{projet.id}_{jour.isoformat()}"
    return f"{base}_{redacteur.pk}" if redacteur else base


def entree_manquante(projet, jour, contexte, *, dernier=None, relance_le=None, redacteur=None):
    ctx = _normaliser_contexte_lu(contexte)
    return {
        "id": identifiant_ligne(projet, jour, redacteur),
        "reference": None,
        "date": jour.isoformat(),
        "chantier": {
            "projet_id": str(projet.id),
            "projet_nom": projet.nom,
            "projet_reference": projet.reference,
            "redacteur_nom": ctx["projet"]["redacteur_nom"],
        },
        "lots": ctx["lots"],
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
        "note_redacteur": None,
        "circuit": [],
    }


def journal_periode(request, debut, fin, *, projet_id=None, brouillons_visibles=True):
    """Les lignes du journal sur `[debut, fin]`, rapports manquants sur jours ouvrés compris."""
    lecteur = request.user.id if brouillons_visibles else None
    projets = list(
        projets_visibles(request).filter(statut__in=["EN_COURS", "EN_RETARD", "CRITIQUE"])
    )
    if projet_id:
        projets = [p for p in projets if str(p.pk) == str(projet_id)]
    qs = journaux_visibles(request).filter(rapport__date_rapport__range=[debut, fin])
    if projet_id:
        qs = qs.filter(rapport__projet_id=projet_id)
    rapports = list(qs)
    par_ligne = {cle_ligne(j): j for j in rapports}
    relances = relances_du_jour(
        {p.id for p in projets} | {j.rapport.projet_id for j in rapports}, debut, fin
    )
    charges = []
    cal = calendrier_entreprise(debut, fin)
    arbres_cache: dict = {}

    for projet in projets:
        arbres_cache[projet.id] = charger_arbre(projet)
        cal_arbre = _calendrier_autour_arbre(arbres_cache[projet.id], fin)
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
                    charges.append(
                        entree(
                            j,
                            contexte=j.photographie or contexte,
                            relance_le=relances.get(cle),
                            arbre=arbres_cache[projet.id],
                            calendrier=cal_arbre,
                        )
                    )
                elif cal.est_ouvre(jour):
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
            pid = j.rapport.projet_id
            if pid not in arbres_cache:
                arbres_cache[pid] = charger_arbre(j.rapport.projet)
            charges.append(
                entree(
                    j,
                    relance_le=relances.get(cle_ligne(j)),
                    arbre=arbres_cache[pid],
                )
            )

    return sorted(
        charges, key=lambda c: (c["date"], c["chantier"]["projet_reference"]), reverse=True
    )
