"""Selectors du module « tiers ».

Référentiel unique des acteurs externes (décision H3 du MCD).
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Q

from apps.tiers.models import Tiers

__all__ = [
    "lister_tiers",
    "nombre_projets_par_tiers",
    "projets_lies_du_tiers",
    "references_du_tiers",
]


def _normaliser_filtre_actif(est_actif: str | None) -> bool | None:
    """Interprète le paramètre de requête `est_actif`.

    - omis / vide / `"true"` / `"1"` : actifs uniquement (comportement historique des listes) ;
    - `"false"` / `"0"` : inactifs uniquement ;
    - `"all"` / `"tous"` : tous les tiers (actifs et inactifs).
    """
    if est_actif is None:
        return True
    valeur = str(est_actif).strip().lower()
    if valeur in ("", "true", "1", "oui"):
        return True
    if valeur in ("false", "0", "non"):
        return False
    if valeur in ("all", "tous", "toutes", "*"):
        return None
    return True


def lister_tiers(
    *,
    role: str | None = None,
    type_tiers: str | None = None,
    est_actif: str | None = "true",
    recherche: str = "",
):
    """Liste filtrée des tiers de l'entreprise courante, avec leurs rôles préchargés."""
    qs = Tiers.objects.all().prefetch_related("roles")

    filtre_actif = _normaliser_filtre_actif(est_actif)
    if filtre_actif is not None:
        qs = qs.filter(est_actif=filtre_actif)

    if role:
        codes = [c.strip().upper() for c in str(role).split(",") if c.strip()]
        if codes:
            qs = qs.filter(roles__role__in=codes, roles__supprime_le__isnull=True).distinct()

    if type_tiers:
        type_code = str(type_tiers).strip().upper()
        if type_code:
            qs = qs.filter(type_tiers=type_code)

    terme = (recherche or "").strip()
    if terme:
        qs = qs.filter(
            Q(raison_sociale__icontains=terme)
            | Q(telephone__icontains=terme)
            | Q(email__icontains=terme)
            | Q(ville__icontains=terme)
            | Q(rccm__icontains=terme)
            | Q(nif__icontains=terme)
        )

    return qs.order_by("raison_sociale", "id")


def nombre_projets_par_tiers(tiers_ids) -> dict:
    """Nombre de projets distincts liés à chaque tiers, calculé en lot (4 requêtes max)."""
    ids = list(tiers_ids)
    if not ids:
        return {}

    from apps.projets.models import Element, EquipeChantier, Projet
    from apps.stock.models import BonCommande

    projets_par_tiers: dict = defaultdict(set)

    for tiers_id, projet_id in Projet.objects.filter(client_id__in=ids).values_list(
        "client_id", "id"
    ):
        projets_par_tiers[tiers_id].add(projet_id)

    for tiers_id, projet_id in Element.objects.filter(
        titulaire_id__in=ids, projet__supprime_le__isnull=True
    ).values_list("titulaire_id", "projet_id"):
        projets_par_tiers[tiers_id].add(projet_id)

    for tiers_id, projet_id in EquipeChantier.objects.filter(
        entreprise_partenaire_id__in=ids, projet__supprime_le__isnull=True
    ).values_list("entreprise_partenaire_id", "projet_id"):
        projets_par_tiers[tiers_id].add(projet_id)

    for tiers_id, projet_id in BonCommande.objects.filter(
        fournisseur_id__in=ids, projet__supprime_le__isnull=True
    ).values_list("fournisseur_id", "projet_id"):
        projets_par_tiers[tiers_id].add(projet_id)

    return {tid: len(projets_par_tiers.get(tid, set())) for tid in ids}


def projets_lies_du_tiers(tiers: Tiers) -> list[dict]:
    """Projets non supprimés dans lesquels ce tiers intervient, avec ses types de relation."""
    from apps.projets.models import Element, EquipeChantier, Projet
    from apps.stock.models import BonCommande

    relations_par_projet: dict = defaultdict(list)

    def _enregistrer(projet_id, relation: str) -> None:
        if relation not in relations_par_projet[projet_id]:
            relations_par_projet[projet_id].append(relation)

    for pid in Projet.objects.filter(client=tiers).values_list("id", flat=True):
        _enregistrer(pid, "CLIENT_MOA")

    for pid in (
        Element.objects.filter(titulaire=tiers, projet__supprime_le__isnull=True)
        .values_list("projet_id", flat=True)
        .distinct()
    ):
        _enregistrer(pid, "TITULAIRE")

    for pid in (
        EquipeChantier.objects.filter(
            entreprise_partenaire=tiers, projet__supprime_le__isnull=True
        )
        .values_list("projet_id", flat=True)
        .distinct()
    ):
        _enregistrer(pid, "EQUIPE")

    for pid in (
        BonCommande.objects.filter(fournisseur=tiers, projet__supprime_le__isnull=True)
        .values_list("projet_id", flat=True)
        .distinct()
    ):
        _enregistrer(pid, "FOURNISSEUR")

    if not relations_par_projet:
        return []

    projets = Projet.objects.filter(pk__in=relations_par_projet.keys()).order_by(
        "reference", "nom"
    )
    return [
        {
            "id": str(p.pk),
            "reference": p.reference,
            "nom": p.nom,
            "statut": p.statut,
            "ville": p.ville or "",
            "relations": relations_par_projet[p.pk],
        }
        for p in projets
    ]


def references_du_tiers(tiers: Tiers) -> list[str]:
    """Domaines actifs référençant encore ce tiers (bloquant la suppression)."""
    from apps.projets.models import Element, EquipeChantier, PersonneMainOeuvre, Projet
    from apps.stock.models import BonCommande

    references: list[str] = []
    if Projet.objects.filter(client=tiers).exists():
        references.append("projets")
    if Element.objects.filter(titulaire=tiers).exists():
        references.append("elements")
    if EquipeChantier.objects.filter(entreprise_partenaire=tiers).exists():
        references.append("equipes")
    if PersonneMainOeuvre.objects.filter(entreprise_partenaire=tiers).exists():
        references.append("main_oeuvre")
    if BonCommande.objects.filter(fournisseur=tiers).exists():
        references.append("bons_commande")
    return references
