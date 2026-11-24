"""Sélecteurs dynamiques pour la Configuration et la Fiche Projet (volets 3 & 4).

Regroupe en un seul endroit les lectures dérivées sans N+1 :
- dates réelles dynamiques (`date_debut_reelle`, `date_fin_reelle`) ;
- client & contact MOA résolus depuis `tiers.Tiers` ;
- phase actuelle & liste des phases (niveau 1 du découpage) ;
- avancement par composante (niveau 1 : code, libellé, montant, avancement, statut, titulaire) ;
- entreprises et intervenants externes (Option A : déduplication par `tiers_id`, priorité aux
  titulaires du découpage, puis partenaires des équipes non déjà présents, puis maître d'œuvre) ;
- synthèse des avenants de délai / reprogrammations et budget contractuel.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date

from django.db.models import Min, Q, Sum
from django.utils import timezone

from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.enums import RoleTiersChoix, StatutActivite, StatutProjet, StatutRapport
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.sante_calculs import calculer_arbre

__all__ = [
    "calculer_dates_reelles_projet",
    "composantes_du_projet",
    "configuration_dynamique_projet",
    "contact_moa_projet",
    "dates_reelles_projets_batch",
    "intervenants_externes_projet",
    "phases_du_projet",
    "premier_rapport_valide_date",
    "resoudre_client_projet",
    "synthese_avenants_delai_projet",
    "tiers_par_nom_batch",
]

_LABELS_STATUT_DECOUPAGE = dict(StatutActivite.choices)
_LABELS_ROLE_TIERS = dict(RoleTiersChoix.choices)
_SENTINEL = object()


def _filtre_rapports_valides():
    """Rapports validés par le CT ou approuvés (même règle que `chantier.selectors.synthese`)."""
    return Q(statut=StatutRapport.APPROUVE) | Q(
        statut=StatutRapport.SOUMIS, journal__valide_ct_le__isnull=False
    )


def dates_reelles_projets_batch(projets) -> dict:
    """Date du premier rapport journalier validé/approuvé pour un lot de projets, en 1 requête."""
    from apps.chantier.models import RapportJournalier

    ids = [p.pk for p in projets]
    if not ids:
        return {}
    lignes = (
        RapportJournalier.objects.filter(projet_id__in=ids, supprime_le__isnull=True)
        .filter(_filtre_rapports_valides())
        .values("projet_id")
        .annotate(premiere_date=Min("date_rapport"))
    )
    return {ligne["projet_id"]: ligne["premiere_date"] for ligne in lignes}


def premier_rapport_valide_date(projet) -> date | None:
    """Date du premier rapport journalier validé/approuvé pour un projet."""
    from apps.chantier.models import RapportJournalier

    return (
        RapportJournalier.objects.filter(projet=projet, supprime_le__isnull=True)
        .filter(_filtre_rapports_valides())
        .aggregate(premiere_date=Min("date_rapport"))
        .get("premiere_date")
    )


def calculer_dates_reelles_projet(
    projet,
    arbre=None,
    *,
    premier_rapport=_SENTINEL,
) -> tuple[date | None, date | None]:
    """Dates réelles dynamiques du projet :
    - `date_debut_reelle` : plus ancienne date entre le 1er rapport validé/approuvé et le plus
      ancien `date_debut_reelle` d'un élément actif du découpage (`None` si aucun) ;
    - `date_fin_reelle` : date de clôture de la dernière tâche clôturée UNIQUEMENT si le projet
      est clôturé à 100 % (toutes les feuilles actives clôturées), sinon `None`.
    """
    if arbre is None:
        arbre = charger_arbre(projet, actifs_seulement=True)
    if premier_rapport is _SENTINEL:
        premier_rapport = premier_rapport_valide_date(projet)

    actifs = [e for e in arbre.elements if e.est_actif]
    debuts_elements = [e.date_debut_reelle for e in actifs if e.date_debut_reelle]
    candidats_debut = [d for d in (premier_rapport, *debuts_elements) if d is not None]
    date_debut_reelle = min(candidats_debut) if candidats_debut else None

    feuilles = arbre.feuilles(actives=True)
    if feuilles:
        if all(f.cloture for f in feuilles):
            fins = []
            for f in feuilles:
                if f.date_fin_reelle:
                    fins.append(f.date_fin_reelle)
                elif f.cloture_le:
                    fins.append(timezone.localdate(f.cloture_le))
            date_fin_reelle = max(fins) if fins else projet.date_fin_reelle
        else:
            date_fin_reelle = None
    else:
        est_acheve = projet.statut in (StatutProjet.TERMINE, StatutProjet.RECEPTIONNE)
        avancement_complet = (projet.avancement_reel or 0) >= 100
        date_fin_reelle = projet.date_fin_reelle if (est_acheve and avancement_complet) else None

    return date_debut_reelle, date_fin_reelle


def tiers_par_nom_batch(projets) -> dict[str, object]:
    """Précharge en 1 requête les `Tiers` correspondant aux `maitre_ouvrage` sans FK `client`."""
    from apps.tiers.models import Tiers

    noms = {
        (p.maitre_ouvrage or "").strip()
        for p in projets
        if not p.client_id and (p.maitre_ouvrage or "").strip()
    }
    if not noms:
        return {}
    cles = {cle_comparaison(n) for n in noms}
    correspondances: dict[str, object] = {}
    for tiers in Tiers.objects.all().prefetch_related("roles"):
        cle = cle_comparaison(tiers.raison_sociale)
        if cle not in cles:
            continue
        est_client = any(r.role == RoleTiersChoix.CLIENT_MOA for r in tiers.roles.all())
        existant = correspondances.get(cle)
        if existant is None or est_client:
            correspondances[cle] = tiers
    return correspondances


def resoudre_client_projet(projet, tiers_par_nom: dict | None = None):
    """Retourne le `Tiers` maître d'ouvrage du projet (FK `client` ou correspondance exacte)."""
    if projet.client_id and projet.client:
        return projet.client
    nom = (projet.maitre_ouvrage or "").strip()
    if not nom:
        return None
    cle = cle_comparaison(nom)
    if tiers_par_nom is not None:
        return tiers_par_nom.get(cle)
    from apps.tiers.models import Tiers

    candidats = list(Tiers.objects.filter(raison_sociale__iexact=nom).prefetch_related("roles"))
    if not candidats:
        return None
    for t in candidats:
        if any(r.role == RoleTiersChoix.CLIENT_MOA for r in t.roles.all()):
            return t
    return candidats[0]


def contact_moa_projet(projet, tiers_par_nom: dict | None = None) -> dict | None:
    """Coordonnées dynamiques du MOA / client issues de son `Tiers`."""
    tiers = resoudre_client_projet(projet, tiers_par_nom=tiers_par_nom)
    if tiers is None:
        return None
    return {
        "tiers_id": str(tiers.pk),
        "raison_sociale": tiers.raison_sociale,
        "telephone": tiers.telephone or "",
        "email": tiers.email or "",
        "ville": tiers.ville or "",
        "adresse": tiers.adresse or "",
    }


def phases_du_projet(arbre, resultats=None, numeros=None) -> tuple[str | None, list[dict]]:
    """Phase actuelle et liste des phases issues des éléments actifs de niveau 1 du découpage."""
    racines = [r for r in arbre.racines() if r.est_actif]
    if not racines:
        return None, []
    resultats = resultats if resultats is not None else calculer_arbre(arbre)
    numeros = numeros if numeros is not None else arbre.numerotation()

    actuelle = next(
        (
            r
            for r in racines
            if r.statut in (StatutActivite.EN_RETARD, StatutActivite.EN_COURS)
        ),
        None,
    )
    if actuelle is None:
        actuelle = next((r for r in racines if arbre.commence(r) and not r.cloture), None)
    if actuelle is None:
        if all(r.statut == StatutActivite.CLOTURE or r.cloture for r in racines):
            actuelle = racines[-1]
        else:
            actuelle = racines[0]

    phases = []
    for r in racines:
        res = resultats.get(r.pk)
        phases.append(
            {
                "id": str(r.pk),
                "code": r.code or numeros.get(r.pk) or "",
                "libelle": r.libelle,
                "statut": r.statut,
                "statut_libelle": _LABELS_STATUT_DECOUPAGE.get(r.statut, r.statut),
                "avancement": res.physique if res else None,
                "est_actuelle": bool(actuelle and r.pk == actuelle.pk),
            }
        )
    return (actuelle.libelle if actuelle else None), phases


def composantes_du_projet(
    arbre,
    resultats=None,
    numeros=None,
    *,
    montants_visibles: bool = True,
) -> list[dict]:
    """Avancement par composante (éléments actifs de niveau 1 du découpage).

    Expose code, libellé, montant, avancement, statut du découpage et titulaire (vide si absent).
    """
    racines = [r for r in arbre.racines() if r.est_actif]
    if not racines:
        return []
    resultats = resultats if resultats is not None else calculer_arbre(arbre)
    numeros = numeros if numeros is not None else arbre.numerotation()

    composantes = []
    for r in racines:
        res = resultats.get(r.pk)
        montant = None
        if montants_visibles:
            if res and res.poids:
                montant = int(res.poids)
            elif r.montant:
                montant = int(r.montant)
            elif r.enveloppe:
                montant = int(r.enveloppe)
        titulaire_nom = r.titulaire.raison_sociale if r.titulaire_id and r.titulaire else ""
        composantes.append(
            {
                "id": str(r.pk),
                "code": r.code or numeros.get(r.pk) or "",
                "libelle": r.libelle,
                "montant": montant,
                "avancement": res.physique if res else None,
                "statut": r.statut,
                "statut_libelle": _LABELS_STATUT_DECOUPAGE.get(r.statut, r.statut),
                "titulaire_id": str(r.titulaire_id) if r.titulaire_id else None,
                "titulaire": titulaire_nom,
            }
        )
    return composantes


def _roles_tiers_libelle(tiers) -> str:
    """Libellé lisible des rôles d'un `Tiers` (hors CLIENT_MOA s'il en a d'autres), ou ''."""
    if tiers is None:
        return ""
    codes = [r.role for r in tiers.roles.all() if r.supprime_le is None]
    if not codes:
        return ""
    filtres = [c for c in codes if c != RoleTiersChoix.CLIENT_MOA] or codes
    return ", ".join(_LABELS_ROLE_TIERS.get(c, c) for c in dict.fromkeys(filtres))


def intervenants_externes_projet(projet, arbre=None) -> list[dict]:
    """Entreprises et intervenants externes — Option A déduplication par `tiers_id` :

    1. Priorité aux `titulaires` du découpage (et leurs périmètres) ;
    2. Puis les `entreprise_partenaire` des `EquipeChantier` actives non déjà présentes ;
    3. Plus le `maitre_oeuvre` (s'il n'est pas déjà présent).
    """
    from apps.projets.models import EquipeChantier
    from apps.tiers.models import Tiers

    if arbre is None:
        arbre = charger_arbre(projet, actifs_seulement=True)

    # Précharger les rôles des tiers titulaires du découpage en 1 requête.
    titulaire_ids = {e.titulaire_id for e in arbre.elements if e.est_actif and e.titulaire_id}
    tiers_map = (
        {
            t.pk: t
            for t in Tiers.objects.filter(pk__in=titulaire_ids).prefetch_related("roles")
        }
        if titulaire_ids
        else {}
    )

    entrees_par_tiers: OrderedDict = OrderedDict()
    noms_vus: set[str] = set()

    # 1. Priorité aux titulaires posés dans le découpage
    for elem in arbre.elements:
        if not elem.est_actif or not elem.titulaire_id:
            continue
        tiers = tiers_map.get(elem.titulaire_id) or elem.titulaire
        if tiers is None:
            continue
        entree = entrees_par_tiers.get(tiers.pk)
        if entree is None:
            entree = {
                "tiers_id": str(tiers.pk),
                "nom": tiers.raison_sociale,
                "org": tiers.raison_sociale,
                "role": _roles_tiers_libelle(tiers),
                "perimetres": [],
                "_perimetres_ids": set(),
                "source": "DECOUPAGE",
            }
            entrees_par_tiers[tiers.pk] = entree
            noms_vus.add(cle_comparaison(tiers.raison_sociale))
        if elem.pk not in entree["_perimetres_ids"]:
            entree["_perimetres_ids"].add(elem.pk)
            entree["perimetres"].append(
                {
                    "id": str(elem.pk),
                    "libelle": elem.libelle,
                    "chemin": " / ".join(arbre.chemin_libelles(elem)),
                }
            )

    # 2. Entreprises partenaires des équipes de chantier non déjà présentes
    equipes = (
        EquipeChantier.objects.filter(
            projet=projet, est_actif=True, entreprise_partenaire__isnull=False
        )
        .select_related("entreprise_partenaire")
        .prefetch_related(
            "entreprise_partenaire__roles",
            "affectations_elements__element",
        )
    )
    equipes_ajoutees: OrderedDict = OrderedDict()
    for eq in equipes:
        tiers = eq.entreprise_partenaire
        if tiers is None or tiers.pk in entrees_par_tiers:
            continue
        entree = equipes_ajoutees.get(tiers.pk)
        if entree is None:
            role_tiers = _roles_tiers_libelle(tiers) or (eq.corps_etat or "").strip()
            entree = {
                "tiers_id": str(tiers.pk),
                "nom": tiers.raison_sociale,
                "org": tiers.raison_sociale,
                "role": role_tiers,
                "perimetres": [],
                "_perimetres_ids": set(),
                "source": "EQUIPE",
            }
            equipes_ajoutees[tiers.pk] = entree
            noms_vus.add(cle_comparaison(tiers.raison_sociale))
        elif not entree["role"] and eq.corps_etat:
            entree["role"] = eq.corps_etat.strip()

        for aff in eq.affectations_elements.all():
            if aff.supprime_le is not None:
                continue
            elem = arbre.par_id.get(aff.element_id) or aff.element
            if elem is None or elem.supprime_le is not None or not elem.est_actif:
                continue
            if elem.pk not in entree["_perimetres_ids"]:
                entree["_perimetres_ids"].add(elem.pk)
                chemin = (
                    " / ".join(arbre.chemin_libelles(elem))
                    if elem.pk in arbre.par_id
                    else elem.libelle
                )
                entree["perimetres"].append(
                    {"id": str(elem.pk), "libelle": elem.libelle, "chemin": chemin}
                )

    resultats = []
    for entree in [*entrees_par_tiers.values(), *equipes_ajoutees.values()]:
        perimetres = entree["perimetres"]
        resultats.append(
            {
                "tiers_id": entree["tiers_id"],
                "nom": entree["nom"],
                "org": entree["org"],
                "role": entree["role"],
                "perimetre": ", ".join(p["libelle"] for p in perimetres),
                "perimetres": perimetres,
                "source": entree["source"],
            }
        )

    # 3. Maître d'œuvre (s'il n'est pas déjà présent)
    moe_nom = (projet.maitre_oeuvre or "").strip()
    if moe_nom:
        tiers_moe = (
            Tiers.objects.filter(raison_sociale__iexact=moe_nom).prefetch_related("roles").first()
        )
        deja_present = (tiers_moe is not None and (
            tiers_moe.pk in entrees_par_tiers or tiers_moe.pk in equipes_ajoutees
        )) or cle_comparaison(moe_nom) in noms_vus
        if not deja_present:
            nom_affiche = tiers_moe.raison_sociale if tiers_moe else moe_nom
            resultats.append(
                {
                    "tiers_id": str(tiers_moe.pk) if tiers_moe else None,
                    "nom": nom_affiche,
                    "org": nom_affiche,
                    "role": _LABELS_ROLE_TIERS.get(RoleTiersChoix.MAITRE_OEUVRE, "Maître d'œuvre"),
                    "perimetre": "",
                    "perimetres": [],
                    "source": "MAITRE_OEUVRE",
                }
            )

    return resultats


def synthese_avenants_delai_projet(projet, *, montants_visibles: bool = True) -> dict:
    """Synthèse dynamique des avenants de délai, reprogrammations et budget contractuel."""
    from apps.projets.models import Avenant, HistoriqueDate, TypeObjetHistorique

    nb_avenants = Avenant.objects.filter(projet=projet).count()
    reprogs = HistoriqueDate.objects.filter(
        projet=projet, type_objet=TypeObjetHistorique.PROJET
    )
    nb_reprogs = reprogs.count()
    agg_reprogs = reprogs.filter(champ="date_fin_prevue").aggregate(
        total_ecart=Sum("ecart_jours"),
    )
    derniere = reprogs.order_by("-cree_le").values_list("cree_le", flat=True).first()

    donnees = {
        "nombre_avenants": nb_avenants,
        "avenants_delai_jours": projet.jours_accordes or 0,
        "prolongation_avenants": projet.prolongation_contractuelle,
        "montant_marche_initial": projet.budget_contractuel_initial if montants_visibles else None,
        "montant_avenants": (projet.montant_avenants or 0) if montants_visibles else None,
        "budget_contractuel": projet.budget_contractuel if montants_visibles else None,
        "nombre_reprogrammations": nb_reprogs,
        "ecart_reprogrammation_jours": agg_reprogs.get("total_ecart") or 0,
        "derniere_reprogrammation_le": (
            timezone.localdate(derniere).isoformat() if derniere else None
        ),
    }
    return donnees


def configuration_dynamique_projet(
    projet,
    *,
    montants_visibles: bool = True,
    tiers_par_nom: dict | None = None,
    premier_rapport=_SENTINEL,
) -> dict:
    """Agrège toutes les données dynamiques utiles à la Configuration et à la Fiche projet."""
    arbre = charger_arbre(projet, actifs_seulement=True)
    resultats = calculer_arbre(arbre)
    numeros = arbre.numerotation()
    date_debut_reelle, date_fin_reelle = calculer_dates_reelles_projet(
        projet, arbre, premier_rapport=premier_rapport
    )
    phase_actuelle, phases = phases_du_projet(arbre, resultats, numeros)
    return {
        "projet_id": str(projet.pk),
        "date_debut_reelle": date_debut_reelle.isoformat() if date_debut_reelle else None,
        "date_fin_reelle": date_fin_reelle.isoformat() if date_fin_reelle else None,
        "contact_moa": contact_moa_projet(projet, tiers_par_nom=tiers_par_nom),
        "phase_actuelle": phase_actuelle,
        "phases_disponibles": phases,
        "synthese_avenants_delai": synthese_avenants_delai_projet(
            projet, montants_visibles=montants_visibles
        ),
        "avancement_composantes": composantes_du_projet(
            arbre, resultats, numeros, montants_visibles=montants_visibles
        ),
        "intervenants_externes": intervenants_externes_projet(projet, arbre),
    }
