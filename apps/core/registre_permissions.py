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
        DefPermission(
            "projets.avenants_gerer", "projets", 3, "Enregistrer et retirer les avenants au contrat"
        ),
        # Destinataires des alertes de retard, par niveau (30/10/2026).
        DefPermission(
            "projets.alertes_moderees", "projets", 1, "Recevoir les alertes de retard modérées"
        ),
        DefPermission(
            "projets.alertes_elevees", "projets", 1, "Recevoir les alertes de retard élevées"
        ),
        DefPermission(
            "projets.alertes_critiques", "projets", 1, "Recevoir les alertes de retard critiques"
        ),
        DefPermission("chantier.lire", "chantier", 1, "Consulter les rapports"),
        DefPermission("chantier.rediger", "chantier", 2, "Rédiger et soumettre un rapport"),
        DefPermission("chantier.valider", "chantier", 3, "Valider / rejeter un rapport"),
        # Le circuit du journal suit les permissions, jamais le nom des rôles (30/10/2026).
        DefPermission("chantier.approuver", "chantier", 3, "Approuver / rejeter un rapport"),
        DefPermission(
            "chantier.synthese_rediger", "chantier", 2, "Rédiger la synthèse de la semaine"
        ),
        DefPermission(
            "chantier.synthese_approuver", "chantier", 3, "Approuver la synthèse de la semaine"
        ),
        DefPermission("tiers.lire", "tiers", 1, "Consulter les tiers"),
        DefPermission("tiers.ecrire", "tiers", 2, "Créer / modifier les tiers"),
        DefPermission("pilotage.lire", "pilotage", 1, "Tableaux de bord"),
        DefPermission("pilotage.voir_montants", "pilotage", 3, "Voir les montants financiers"),
        # F6 GED (Gestion Documentaire)
        DefPermission("ged.lire", "ged", 1, "Consulter la GED"),
        DefPermission("ged.telecharger", "ged", 1, "Télécharger un document"),
        DefPermission("ged.voir_plans", "ged", 2, "Voir les plans"),
        DefPermission("ged.deposer_plans", "ged", 2, "Déposer des plans"),
        DefPermission("ged.supprimer_plans", "ged", 3, "Supprimer des plans"),
        DefPermission("ged.voir_contrats", "ged", 2, "Voir les contrats"),
        DefPermission("ged.deposer_contrats", "ged", 2, "Déposer des contrats"),
        DefPermission("ged.supprimer_contrats", "ged", 3, "Supprimer des contrats"),
        DefPermission("ged.voir_rapports", "ged", 2, "Voir les rapports"),
        DefPermission("ged.deposer_rapports", "ged", 2, "Déposer des rapports"),
        DefPermission("ged.supprimer_rapports", "ged", 3, "Supprimer des rapports"),
        DefPermission(
            "ged.voir_administratif", "ged", 2, "Voir les documents administratifs"
        ),
        DefPermission(
            "ged.deposer_administratif",
            "ged",
            2,
            "Déposer des documents administratifs",
        ),
        DefPermission(
            "ged.supprimer_administratif",
            "ged",
            3,
            "Supprimer des documents administratifs",
        ),
        DefPermission("ged.voir_photos", "ged", 2, "Voir les photos"),
        DefPermission("ged.deposer_photos", "ged", 2, "Déposer des photos"),
        DefPermission("ged.supprimer_photos", "ged", 3, "Supprimer des photos"),
        DefPermission("ged.voir_divers", "ged", 2, "Voir les documents divers"),
        DefPermission("ged.deposer_divers", "ged", 2, "Déposer des documents divers"),
        DefPermission("ged.supprimer_divers", "ged", 3, "Supprimer des documents divers"),
        # F9 Stock & Approvisionnements
        DefPermission(
            "stock.lire", "stock", 1, "Consulter le stock et les mouvements"
        ),
        DefPermission(
            "stock.da_creer",
            "stock",
            2,
            "Émettre une demande d'approvisionnement (DA)",
        ),
        DefPermission(
            "stock.da_modifier",
            "stock",
            2,
            "Modifier une DA au statut EN_ATTENTE",
        ),
        DefPermission(
            "stock.da_lire",
            "stock",
            1,
            "Voir les demandes d'approvisionnement (DA)",
        ),
        DefPermission(
            "stock.bc_emettre",
            "stock",
            3,
            "Émettre un bon de commande (exclusif DO/DG)",
        ),
        DefPermission(
            "stock.bc_lire", "stock", 1, "Voir les bons de commande (BC)"
        ),
        DefPermission(
            "stock.bc_cloturer", "stock", 2, "Clôturer un bon de commande partiel"
        ),
        DefPermission(
            "stock.reception_saisir",
            "stock",
            2,
            "Saisir une réception de livraison sur chantier",
        ),
        DefPermission(
            "stock.brv_valider_ct",
            "stock",
            3,
            "Valider le BRV matériaux (technique)",
        ),
        DefPermission(
            "stock.brv_valider_cp",
            "stock",
            3,
            "Valider le BRV équipements (séquentiel)",
        ),
        DefPermission(
            "stock.justificatif_uploader",
            "stock",
            2,
            "Téléverser le bon de livraison (BL) signé",
        ),
        DefPermission(
            "stock.mouvement_manuel_creer",
            "stock",
            2,
            "Saisir un mouvement manuel de stock",
        ),
        DefPermission(
            "stock.transfert_inter_lots",
            "stock",
            2,
            "Autoriser un transfert inter-lots",
        ),
        DefPermission(
            "stock.transfert_inter_chantiers",
            "stock",
            2,
            "Autoriser un transfert inter-chantiers",
        ),
        DefPermission(
            "stock.inventaire_realiser",
            "stock",
            2,
            "Réaliser un inventaire physique",
        ),
        DefPermission(
            "stock.inventaire_valider",
            "stock",
            3,
            "Valider un inventaire physique",
        ),
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
