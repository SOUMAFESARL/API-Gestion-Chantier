"""Validation et normalisation des informations complémentaires de la fiche projet."""

from __future__ import annotations

import json
from typing import Any

from rest_framework import serializers

__all__ = ["valider_informations_complementaires"]

CHAMPS_TEXTE: frozenset[str] = frozenset(
    {
        # 1. Identification
        "delegue",
        "tutelle",
        "agence",
        "operateur",
        "numero_fiche",
        "secteur",
        "contact",
        "phase",
        "region",
        "interet",
        # 2. Programme et caractéristiques
        "capacite_projet",
        "capacite_terme",
        "unite_capacite",
        "lits",
        "superficie_ha",
        "perimetre",
        "niveaux",
        "usage",
        "terrain_m2",
        "surface_batie",
        "offre_formation",
        # 3. Calendrier et budget complémentaires
        "date_situation",
        "duree_contrat",
        "reprogrammation",
        "cout",
        "devise",
        "taux_change",
        "regime",
        "budget_contractuel",
        # 4. Financement
        "mode_fin",
        "statut_fin",
        "etat_imputation",
        "etat_effectif",
        "etat_decaissement",
        "procedure",
        "texte_applicable",
        "historique",
        "source_fin",
        "etablissement",
        "contractualisation",
        # 5. Foncier, autorisations et études
        "disponibilite",
        "delimitation",
        "purge_total",
        "purge_engage",
        "purge_paye",
        "titre_foncier",
        "permis_statut",
        "permis_num",
        # 6. Avancement
        "taux_saisi",
        "etat_narratif",
        # 7. Note du chef de projet
        "note_cp",
    }
)

LISTES_TEXTE: frozenset[str] = frozenset({"objectifs", "impacts"})

COLONNES_TABLEAUX: dict[str, tuple[str, ...]] = {
    "bailleurs": ("org", "type", "signature", "limite", "effectif", "decaisse"),
    "etudes": ("nom", "statut", "avancement", "prestataire", "montant"),
    "lots": ("code", "nom", "montant", "avancement", "statut", "prestataire"),
    "difficultes": ("desc", "gravite", "date", "statut"),
    "recos": ("texte", "dest", "echeance"),
    "intervenants": ("role", "org", "lot"),
    "etapes": ("etape", "echeance", "resp"),
}


def valider_informations_complementaires(valeur: Any) -> dict[str, Any]:
    """Valide et nettoie la structure JSON des informations complémentaires d'un projet."""
    if valeur is None or valeur == "":
        return {}
    if isinstance(valeur, str):
        try:
            valeur = json.loads(valeur)
        except ValueError as exc:
            raise serializers.ValidationError(
                "Format JSON invalide pour les informations complémentaires."
            ) from exc
    if not isinstance(valeur, dict):
        raise serializers.ValidationError(
            "Les informations complémentaires doivent être un objet JSON."
        )

    propre: dict[str, Any] = {}

    # 1. Champs scalaires
    for cle in CHAMPS_TEXTE:
        if cle in valeur and valeur[cle] is not None:
            propre[cle] = str(valeur[cle]).strip()[:5000]

    # 2. Listes de chaînes (objectifs, impacts)
    for cle in LISTES_TEXTE:
        if cle in valeur:
            brute = valeur[cle]
            if not isinstance(brute, list):
                raise serializers.ValidationError(f"La rubrique « {cle} » doit être une liste.")
            propre[cle] = [
                str(item).strip()[:1000]
                for item in brute[:50]
                if item is not None and str(item).strip()
            ]

    # 3. Coordonnateur du projet (équipe publique)
    if "coordonnateur" in valeur and valeur["coordonnateur"] is not None:
        coord = valeur["coordonnateur"]
        if not isinstance(coord, dict):
            raise serializers.ValidationError("Le champ « coordonnateur » doit être un objet.")
        propre["coordonnateur"] = {
            "nom": str(coord.get("nom") or "").strip()[:200],
            "tel": str(coord.get("tel") or "").strip()[:60],
            "email": str(coord.get("email") or "").strip()[:200],
        }

    # 4. Tableaux éditables
    for cle_tbl, colonnes in COLONNES_TABLEAUX.items():
        if cle_tbl in valeur and valeur[cle_tbl] is not None:
            lignes = valeur[cle_tbl]
            if not isinstance(lignes, list):
                raise serializers.ValidationError(
                    f"Le tableau « {cle_tbl} » doit être une liste de lignes."
                )
            lignes_propres: list[dict[str, str]] = []
            for ligne in lignes[:100]:
                if not isinstance(ligne, dict):
                    continue
                normalisee = {col: str(ligne.get(col) or "").strip()[:1000] for col in colonnes}
                if any(normalisee.values()):
                    lignes_propres.append(normalisee)
            propre[cle_tbl] = lignes_propres

    return propre
