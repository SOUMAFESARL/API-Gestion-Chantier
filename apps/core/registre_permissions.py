"""Registre des points de contrôle : la seule liste de permissions qui ont un effet."""

from dataclasses import dataclass

__all__ = ["DefPermission", "REGISTRE", "permissions_du_module"]


@dataclass(frozen=True)
class DefPermission:
    code: str
    module: str  # code du CatalogueModule
    rang: int  # 1 lecture, 2 écriture, 3 validation (sert à traduire le niveau 0-3 du front)
    libelle: str


REGISTRE: dict[str, DefPermission] = {
    p.code: p
    for p in [
        DefPermission("projets.lire", "projets", 1, "Consulter les projets"),
        DefPermission("projets.ecrire", "projets", 2, "Modifier les projets"),
        DefPermission("projets.creer", "projets", 2, "Créer un projet"),
        DefPermission("projets.changer_statut", "projets", 3, "Suspendre / terminer un projet"),
        DefPermission("projets.voir_tous", "projets", 3, "Voir tous les projets de l'entreprise"),
        DefPermission("chantier.lire", "chantier", 1, "Consulter les rapports"),
        DefPermission("chantier.rediger", "chantier", 2, "Rédiger et soumettre un rapport"),
        DefPermission("chantier.valider", "chantier", 3, "Valider / rejeter un rapport"),
        DefPermission("tiers.lire", "tiers", 1, "Consulter les tiers"),
        DefPermission("tiers.ecrire", "tiers", 2, "Créer / modifier les tiers"),
        DefPermission("pilotage.lire", "pilotage", 1, "Tableaux de bord"),
        DefPermission("pilotage.voir_montants", "pilotage", 3, "Voir les montants financiers"),
        DefPermission("administration.collaborateurs_voir", "administration", 1, "Voir l'annuaire"),
        DefPermission(
            "administration.collaborateurs_gerer",
            "administration",
            2,
            "Inviter / suspendre / changer de rôle",
        ),
        DefPermission(
            "administration.roles_gerer", "administration", 3, "Gérer les rôles et la matrice"
        ),
        DefPermission(
            "administration.entreprise_modifier", "administration", 3, "Modifier l'entreprise"
        ),
    ]
}


def permissions_du_module(module: str, niveau: int) -> set[str]:
    """Traduit le niveau 0-3 envoyé par le front en codes : rang <= niveau."""
    return {c for c, p in REGISTRE.items() if p.module == module and p.rang <= niveau}
