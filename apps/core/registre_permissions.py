"""Registre des points de contrôle : la seule liste de permissions qui ont un effet."""

from dataclasses import dataclass

__all__ = ["REGISTRE", "DefPermission"]


@dataclass(frozen=True)
class DefPermission:
    code: str
    module: str  # code du CatalogueModule
    rang: int  # ordre d'affichage au sein du module
    libelle: str
    reservee_administration: bool = False


REGISTRE: dict[str, DefPermission] = {
    p.code: p
    for p in [
        DefPermission("projets.lire", "projets", 1, "Consulter les projets"),
        DefPermission("projets.ecrire", "projets", 2, "Modifier les projets"),
        DefPermission("projets.creer", "projets", 3, "Créer un projet"),
        DefPermission("projets.changer_statut", "projets", 3, "Suspendre / terminer un projet"),
        DefPermission("projets.resilier_archiver", "projets", 3, "Résilier ou archiver un projet"),
        DefPermission("projets.affecter_membres", "projets", 2, "Affecter des membres aux projets"),
        DefPermission("projets.gerer_equipes", "projets", 2, "Gérer les équipes de chantier"),
        DefPermission("projets.voir_montants", "projets", 3, "Voir les montants financiers du projet"),
        DefPermission(
            "projets.referentiels_ajouter",
            "projets",
            2,
            "Ajouter des types, groupes et listes de l'entreprise",
        ),
        # Découpage en arbre (décisions v1.2, §13bis) : chaque permission s'exerce dans le
        # périmètre de l'affectation — une ou plusieurs cases de l'arbre, ou tout le projet.
        DefPermission("projets.voir_tout", "projets", 1, "Voir tout le projet, hors de son périmètre"),
        DefPermission(
            "projets.decouper",
            "projets",
            2,
            "Découper le projet (ajouter, déplacer, détailler, insérer un niveau, désactiver)",
        ),
        DefPermission("projets.chiffrer", "projets", 2, "Fixer les montants et les quantités prévues"),
        DefPermission("projets.planifier", "projets", 2, "Planifier et reprogrammer les dates"),
        DefPermission(
            "projets.prolonger", "projets", 3, "Prolonger le projet ou une case déjà commencée"
        ),
        DefPermission("projets.mesurer", "projets", 2, "Mesurer l'avancement hors du journal"),
        DefPermission("projets.retirer_membres", "projets", 2, "Retirer un membre du projet"),
        DefPermission(
            "projets.main_oeuvre_gerer", "projets", 2, "Gérer le registre de main-d'œuvre"
        ),
        DefPermission(
            "projets.modeles_gerer",
            "projets",
            3,
            "Gérer les listes et les modèles de découpage de l'entreprise",
        ),
        DefPermission("chantier.lire", "chantier", 1, "Consulter les rapports"),
        DefPermission("chantier.rediger", "chantier", 2, "Rédiger et soumettre un rapport"),
        DefPermission("chantier.valider", "chantier", 3, "Valider / rejeter un rapport"),
        DefPermission("tiers.lire", "tiers", 1, "Consulter les tiers"),
        DefPermission("tiers.ecrire", "tiers", 2, "Créer / modifier les tiers"),
        DefPermission("pilotage.lire", "pilotage", 1, "Tableaux de bord"),
        DefPermission("pilotage.voir_montants", "pilotage", 3, "Voir les montants financiers"),
        DefPermission(
            "administration.collaborateurs_voir",
            "administration",
            1,
            "Voir l'annuaire",
            reservee_administration=True,
        ),
        DefPermission(
            "administration.collaborateurs_gerer",
            "administration",
            2,
            "Inviter / suspendre / changer de rôle",
            reservee_administration=True,
        ),
        DefPermission(
            "administration.roles_gerer",
            "administration",
            2,
            "Gérer les rôles et la matrice",
            reservee_administration=True,
        ),
        DefPermission(
            "administration.entreprise_modifier",
            "administration",
            3,
            "Modifier l'entreprise",
            reservee_administration=True,
        ),
        DefPermission(
            "administration.calendrier_gerer",
            "administration",
            2,
            "Gérer le calendrier des jours ouvrés",
            reservee_administration=True,
        ),
        DefPermission(
            "administration.documents_gerer",
            "administration",
            2,
            "Configurer l'en-tête et le pied des documents",
            reservee_administration=True,
        ),
        DefPermission(
            "administration.abonnement_voir",
            "administration",
            1,
            "Consulter l'abonnement",
            reservee_administration=True,
        ),
        DefPermission(
            "administration.abonnement_gerer",
            "administration",
            2,
            "Gérer l'abonnement et paiements",
            reservee_administration=True,
        ),
        DefPermission(
            "administration.factures_voir",
            "administration",
            1,
            "Consulter les factures",
            reservee_administration=True,
        ),
        DefPermission(
            "administration.onboarding_suivre",
            "administration",
            1,
            "Suivre l'onboarding",
            reservee_administration=True,
        ),
    ]
}
