"""Énumérations transverses — CCD Digital.

Reprend §3 du MLD. Toute valeur qui pilote une règle de gestion est ici,
et non dans une table : un `if` du code ne doit pas dépendre d'une ligne
qu'un utilisateur peut modifier (décision D7).

Toute modification de ces listes est une migration.
"""

from django.db import models


class RoleGlobal(models.TextChoices):
    # Les 7 rôles clés du projet BTP
    ADMIN = "AD", "Administrateur"
    DIRECTEUR_GENERAL = "DG", "Directeur Général / PDG"
    CHEF_PROJET = "CP", "Chef de Projet"
    CONDUCTEUR_TRAVAUX = "CT", "Conducteur de Travaux"
    CHEF_CHANTIER = "CC", "Chef de Chantier"
    MAITRE_OUVRAGE = "MOA", "Maître d'Ouvrage (Client)"
    MAITRE_OEUVRE = "MOE", "Maître d'Œuvre"
    VISITEUR = "VI", "Consultant lecture"


# Alias sémantique conforme US-04
RoleGlobal.CONSULTANT_LECTURE = RoleGlobal.VISITEUR


class RoleProjet(models.TextChoices):
    # Les 7 rôles clés du chantier BTP
    CHEF_PROJET = "CP", "Chef de Projet"
    CONDUCTEUR_TRAVAUX = "CT", "Conducteur de Travaux"
    CHEF_CHANTIER = "CC", "Chef de Chantier"
    MAITRE_OUVRAGE = "MOA", "Maître d'Ouvrage (Client)"
    MAITRE_OEUVRE = "MOE", "Maître d'Œuvre"
    VISITEUR = "VI", "Consultant lecture"


# Alias sémantique conforme US-04
RoleProjet.CONSULTANT_LECTURE = RoleProjet.VISITEUR


class StatutUtilisateur(models.TextChoices):
    INVITE = "INVITE", "Invité"
    ACTIF = "ACTIF", "Actif"
    DESACTIVE = "DESACTIVE", "Désactivé"


class StatutEntreprise(models.TextChoices):
    ESSAI = "ESSAI", "Période d'essai"
    ACTIF = "ACTIF", "Actif"
    SUSPENDU = "SUSPENDU", "Suspendu"
    RESILIE = "RESILIE", "Résilié"


class StatutProjet(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    EN_COURS = "EN_COURS", "En cours"
    EN_RETARD = "EN_RETARD", "En retard"
    CRITIQUE = "CRITIQUE", "Critique"
    SUSPENDU = "SUSPENDU", "Suspendu"
    RECEPTIONNE = "RECEPTIONNE", "Réceptionné"
    TERMINE = "TERMINE", "Terminé"
    BLOQUE = "BLOQUE", "Bloqué"
    DESACTIVE = "DESACTIVE", "Désactivé"
    RESILIE = "RESILIE", "Résilié"
    ARCHIVE = "ARCHIVE", "Archivé"


class StatutLot(models.TextChoices):
    PLANIFIE = "PLANIFIE", "Planifié"
    EN_COURS = "EN_COURS", "En cours"
    EN_RETARD = "EN_RETARD", "En retard"
    SUSPENDU = "SUSPENDU", "Suspendu"
    CLOTURE = "CLOTURE", "Clôturé"


class StatutActivite(models.TextChoices):
    PLANIFIE = "PLANIFIE", "Planifiée"
    EN_COURS = "EN_COURS", "En cours"
    EN_RETARD = "EN_RETARD", "En retard"
    SUSPENDU = "SUSPENDU", "Suspendu"
    CLOTURE = "CLOTURE", "Clôturée"


class TypeProjet(models.TextChoices):
    BATIMENT_RESIDENTIEL = "BATIMENT_RESIDENTIEL", "Bâtiment — Résidentiel"
    BATIMENT_COMMERCIAL = "BATIMENT_COMMERCIAL", "Bâtiment — Commercial"
    TP_ROUTE = "TP_ROUTE", "TP — Route"
    TP_GENIE_CIVIL = "TP_GENIE_CIVIL", "TP — Génie civil"
    VRD = "VRD", "VRD"
    INFRASTRUCTURE_INDUSTRIELLE = "INFRASTRUCTURE_INDUSTRIELLE", "Infrastructure industrielle"


class ModeExecution(models.TextChoices):
    """Attribut le plus structurant du produit — irréversible (RG-03).

    Il conditionne les champs du rapport journalier (module 2) et le mode
    de rémunération (module 3).
    """

    REGIE = "REGIE", "Régie"
    SOUS_TRAITANCE_STRUCTUREE = "SOUS_TRAITANCE_STRUCTUREE", "Sous-traitance structurée"
    SOUS_TRAITANCE_INFORMELLE = "SOUS_TRAITANCE_INFORMELLE", "Sous-traitance informelle"


class UniteMesure(models.TextChoices):
    METRE_CARRE = "M2", "m²"
    METRE_LINEAIRE = "ML", "ml"
    METRE_CUBE = "M3", "m³"
    KILOGRAMME = "KG", "kg"
    UNITE = "U", "u"
    FORFAIT = "FORFAIT", "forfait"
    SAC = "SAC", "sac(s)"
    LITRE = "L", "l"
    TONNE = "T", "t"
    ROULEAU = "ROULEAU", "rouleau(x)"


class TypeBordereau(models.TextChoices):
    FORFAIT = "FORFAIT", "Forfait"
    PRIX_UNITAIRE = "PRIX_UNITAIRE", "Prix unitaire"
    MIXTE = "MIXTE", "Mixte"


class CategorieReport(models.TextChoices):
    INTEMPERIES = "INTEMPERIES", "Intempéries"
    CLIENT = "CLIENT", "Client"
    TECHNIQUE = "TECHNIQUE", "Technique"
    ADMINISTRATIF = "ADMINISTRATIF", "Administratif"
    AUTRE = "AUTRE", "Autre"


class StatutRapport(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumis"
    APPROUVE = "APPROUVE", "Approuvé"
    REJETE = "REJETE", "Rejeté"


class Meteo(models.TextChoices):
    ENSOLEILLE = "ENSOLEILLE", "Ensoleillé"
    NUAGEUX = "NUAGEUX", "Nuageux"
    PLUIE = "PLUIE", "Pluie"
    ORAGE = "ORAGE", "Orage"


class Gravite(models.TextChoices):
    MINEUR = "MINEUR", "Mineur"
    MAJEUR = "MAJEUR", "Majeur"
    BLOQUANT = "BLOQUANT", "Bloquant"


class StatutBlocage(models.TextChoices):
    OUVERT = "OUVERT", "Ouvert"
    PRIS_EN_CHARGE = "PRIS_EN_CHARGE", "Pris en charge"
    RESOLU = "RESOLU", "Résolu"


class SeveriteBlocage(models.TextChoices):
    MINEUR = "MINEUR", "Mineur"
    MAJEUR = "MAJEUR", "Majeur"
    CRITIQUE = "CRITIQUE", "Critique"


class BadgeSante(models.TextChoices):
    VERT = "VERT", "Vert"
    ORANGE = "ORANGE", "Orange"
    ROUGE = "ROUGE", "Rouge"


class StatutBonPaiement(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    A_SIGNER = "A_SIGNER", "À signer"
    SIGNE = "SIGNE", "Signé"
    PAYE = "PAYE", "Payé"
    CLOTURE = "CLOTURE", "Clôturé"


class NiveauRejet(models.TextChoices):
    MINEUR = "MINEUR", "Mineur"
    SIGNIFICATIF = "SIGNIFICATIF", "Significatif"
    GRAVE = "GRAVE", "Grave"


class ModePaiement(models.TextChoices):
    CASH = "CASH", "Espèces"
    VIREMENT = "VIREMENT", "Virement"
    ORANGE_MONEY = "ORANGE_MONEY", "Orange Money"
    WAVE = "WAVE", "Wave"
    MTN_MOMO = "MTN_MOMO", "MTN MoMo"


class ActionAudit(models.TextChoices):
    CREATION = "CREATION", "Création"
    MODIFICATION = "MODIFICATION", "Modification"
    SUPPRESSION = "SUPPRESSION", "Suppression"
    CONNEXION = "CONNEXION", "Connexion"
    DECONNEXION = "DECONNEXION", "Déconnexion"
    EXPORT = "EXPORT", "Export"
    VALIDATION = "VALIDATION", "Validation"
    SIGNATURE = "SIGNATURE", "Signature"
    ASSISTANCE = "ASSISTANCE", "Assistance Super Admin"


class TypeTiers(models.TextChoices):
    PERSONNE = "PERSONNE", "Personne physique"
    ENTREPRISE = "ENTREPRISE", "Personne morale"


class RoleTiersChoix(models.TextChoices):
    CLIENT_MOA = "CLIENT_MOA", "Client / Maître d'ouvrage"
    MAITRE_OEUVRE = "MAITRE_OEUVRE", "Maître d'œuvre"
    FOURNISSEUR = "FOURNISSEUR", "Fournisseur"
    SOUS_TRAITANT = "SOUS_TRAITANT", "Sous-traitant"
    TACHERON = "TACHERON", "Tâcheron"
    BUREAU_CONTROLE = "BUREAU_CONTROLE", "Bureau de contrôle"
    ADMINISTRATION = "ADMINISTRATION", "Administration"
    PRESTATAIRE = "PRESTATAIRE", "Prestataire"


class TypeObjetLie(models.TextChoices):
    """Cibles autorisées d'une liaison de document (RG-15)."""

    PROJET = "PROJET", "Projet"
    ELEMENT = "ELEMENT", "Case du découpage"
    RAPPORT = "RAPPORT", "Rapport journalier"
    BON_PAIEMENT = "BON_PAIEMENT", "Bon de paiement"
    CONTRAT = "CONTRAT", "Contrat"
    EQUIPEMENT = "EQUIPEMENT", "Équipement"
    EMPLOYE = "EMPLOYE", "Employé"
    NON_CONFORMITE = "NON_CONFORMITE", "Non-conformité"


# --------------------------------------------------------------------------
# Configuration initiale — le wizard d'entrée (MLD §3, v1.3)
# --------------------------------------------------------------------------
class StatutConfiguration(models.TextChoices):
    """État du wizard de configuration d'une entreprise.

    Il n'existe **aucune transition `TERMINEE → EN_COURS`** : une fois la
    configuration terminée, les données se modifient par les écrans du produit,
    jamais en rouvrant le wizard. C'est un chemin d'entrée, pas un mode
    d'édition.
    """

    EN_COURS = "EN_COURS", "En cours"
    TERMINEE = "TERMINEE", "Terminée"


class ModeEtape(models.TextChoices):
    """Comment une étape a été franchie.

    **Les deux comptent dans le pourcentage** (R-93) : quelqu'un qui décide
    sciemment de ne pas inviter son équipe a terminé sa configuration. La
    distinction est gardée parce qu'elle répond à une question que l'éditeur
    posera — combien de nouveaux clients invitent un collaborateur la première
    semaine ? Un chiffre qu'on n'a pas gardé ne se reconstitue pas.
    """

    VALIDEE = "VALIDEE", "Validée"
    PASSEE = "PASSEE", "Passée"


class CodeEtape(models.TextChoices):
    """Les trois étapes du wizard, dans l'ordre — contrat T-024 §2.1."""

    ENTREPRISE = "ENTREPRISE", "Votre entreprise"
    PROJET = "PROJET", "Premier projet"
    EQUIPE = "EQUIPE", "Votre équipe"


class ModuleChoix(models.TextChoices):
    """Les 6 modules applicatifs souverains de CCD Digital."""

    PROJETS = "projets", "Gestion des Projets"
    CHANTIER = "chantier", "Suivi Technique / Chantier"
    GED = "ged", "Gestion Documentaire (GED)"
    PILOTAGE = "pilotage", "Tableaux de bord & Pilotage"
    TIERS = "tiers", "Parties Prenantes / Tiers"
    STOCK = "stock", "Stock & Approvisionnements"


MODULES_DETAILS = {
    ModuleChoix.PROJETS: {
        "description": "Fiches projets, lots, activités, jalons et planification des chantiers.",
        "ordre": 1,
        "icone": "folder-kanban",
    },
    ModuleChoix.CHANTIER: {
        "description": (
            "Rapports journaliers, avancement des travaux, blocages terrain et pointages."
        ),
        "ordre": 2,
        "icone": "hard-hat",
    },
    ModuleChoix.GED: {
        "description": (
            "Classeurs, plans d'exécution, procès-verbaux et traçabilité des pièces jointes."
        ),
        "ordre": 3,
        "icone": "file-text",
    },
    ModuleChoix.PILOTAGE: {
        "description": (
            "Indicateurs d'avancement, indice de santé global, météo et aide à la décision."
        ),
        "ordre": 4,
        "icone": "bar-chart-3",
    },
    ModuleChoix.TIERS: {
        "description": "Clients, maîtres d'ouvrage, sous-traitants, fournisseurs et partenaires.",
        "ordre": 5,
        "icone": "users",
    },
    ModuleChoix.STOCK: {
        "description": (
            "Demandes d'approvisionnement, bons de commande, réceptions terrain (BRV), "
            "gestion du stock et inventaires."
        ),
        "ordre": 6,
        "icone": "boxes",
    },
}


# --------------------------------------------------------------------------
# Permissions granulaires applicatives CCD Digital
# --------------------------------------------------------------------------
class CodePermission(models.TextChoices):
    """Codes de permissions applicatives du catalogue CCD Digital."""

    # Projets
    PROJETS_LIRE = "projets.lire", "Consulter les projets"
    PROJETS_ECRIRE = "projets.ecrire", "Modifier les projets"
    PROJETS_CREER = "projets.creer", "Créer un projet"
    PROJETS_CHANGER_STATUT = "projets.changer_statut", "Suspendre / terminer un projet"
    PROJETS_RESILIER_ARCHIVER = "projets.resilier_archiver", "Résilier ou archiver un projet"
    PROJETS_AFFECTER_MEMBRES = "projets.affecter_membres", "Affecter des membres aux projets"
    PROJETS_GERER_EQUIPES = "projets.gerer_equipes", "Gérer les équipes de chantier"
    PROJETS_VOIR_MONTANTS = "projets.voir_montants", "Voir les montants financiers du projet"
    PROJETS_REFERENTIELS_AJOUTER = (
        "projets.referentiels_ajouter",
        "Ajouter des types, groupes et listes de l'entreprise",
    )
    PROJETS_VOIR_TOUT = "projets.voir_tout", "Voir tout le projet, hors de son périmètre"
    PROJETS_DECOUPER = (
        "projets.decouper",
        "Découper le projet (ajouter, déplacer, détailler, insérer un niveau, désactiver)",
    )
    PROJETS_CHIFFRER = "projets.chiffrer", "Fixer les montants et les quantités prévues"
    PROJETS_PLANIFIER = "projets.planifier", "Planifier et reprogrammer les dates"
    PROJETS_PROLONGER = "projets.prolonger", "Prolonger le projet ou une case déjà commencée"
    PROJETS_MESURER = "projets.mesurer", "Mesurer l'avancement hors du journal"
    PROJETS_RETIRER_MEMBRES = "projets.retirer_membres", "Retirer un membre du projet"
    PROJETS_MAIN_OEUVRE_GERER = "projets.main_oeuvre_gerer", "Gérer le registre de main-d'œuvre"
    PROJETS_MODELES_GERER = (
        "projets.modeles_gerer",
        "Gérer les listes et les modèles de découpage de l'entreprise",
    )
    PROJETS_AVENANTS_GERER = (
        "projets.avenants_gerer",
        "Enregistrer et retirer les avenants au contrat",
    )
    PROJETS_ALERTES_MODEREES = "projets.alertes_moderees", "Recevoir les alertes de retard modérées"
    PROJETS_ALERTES_ELEVEES = "projets.alertes_elevees", "Recevoir les alertes de retard élevées"
    PROJETS_ALERTES_CRITIQUES = (
        "projets.alertes_critiques",
        "Recevoir les alertes de retard critiques",
    )

    # Journal / Chantier
    CHANTIER_LIRE = "chantier.lire", "Consulter les rapports"
    CHANTIER_REDIGER = "chantier.rediger", "Rédiger et soumettre un rapport"
    CHANTIER_VALIDER = "chantier.valider", "Valider / rejeter un rapport"
    CHANTIER_APPROUVER = "chantier.approuver", "Approuver / rejeter un rapport"
    CHANTIER_SYNTHESE_REDIGER = "chantier.synthese_rediger", "Rédiger la synthèse de la semaine"
    CHANTIER_SYNTHESE_APPROUVER = (
        "chantier.synthese_approuver",
        "Approuver la synthèse de la semaine",
    )

    # Tiers
    TIERS_LIRE = "tiers.lire", "Consulter les tiers"
    TIERS_ECRIRE = "tiers.ecrire", "Créer / modifier les tiers"

    # Pilotage
    PILOTAGE_LIRE = "pilotage.lire", "Tableaux de bord"
    PILOTAGE_VOIR_MONTANTS = "pilotage.voir_montants", "Voir les montants financiers"

    # Administration
    ADMINISTRATION_COLLABORATEURS_VOIR = "administration.collaborateurs_voir", "Voir l'annuaire"
    ADMINISTRATION_COLLABORATEURS_GERER = (
        "administration.collaborateurs_gerer",
        "Inviter / suspendre / changer de rôle",
    )
    ADMINISTRATION_ROLES_GERER = "administration.roles_gerer", "Gérer les rôles et la matrice"
    ADMINISTRATION_ENTREPRISE_MODIFIER = (
        "administration.entreprise_modifier",
        "Modifier l'entreprise",
    )
    ADMINISTRATION_CALENDRIER_GERER = (
        "administration.calendrier_gerer",
        "Gérer le calendrier des jours ouvrés",
    )
    ADMINISTRATION_DOCUMENTS_GERER = (
        "administration.documents_gerer",
        "Configurer l'en-tête et le pied des documents",
    )
    ADMINISTRATION_ABONNEMENT_VOIR = "administration.abonnement_voir", "Consulter l'abonnement"
    ADMINISTRATION_ABONNEMENT_GERER = (
        "administration.abonnement_gerer",
        "Gérer l'abonnement et paiements",
    )
    ADMINISTRATION_FACTURES_VOIR = "administration.factures_voir", "Consulter les factures"
    ADMINISTRATION_ONBOARDING_SUIVRE = "administration.onboarding_suivre", "Suivre l'onboarding"

    # F6 GED (Gestion Documentaire)
    GED_LIRE = "ged.lire", "Consulter la GED"
    GED_TELECHARGER = "ged.telecharger", "Télécharger un document"
    GED_VOIR_PLANS = "ged.voir_plans", "Voir les plans"
    GED_DEPOSER_PLANS = "ged.deposer_plans", "Déposer des plans"
    GED_SUPPRIMER_PLANS = "ged.supprimer_plans", "Supprimer des plans"
    GED_VOIR_CONTRATS = "ged.voir_contrats", "Voir les contrats"
    GED_DEPOSER_CONTRATS = "ged.deposer_contrats", "Déposer des contrats"
    GED_SUPPRIMER_CONTRATS = "ged.supprimer_contrats", "Supprimer des contrats"
    GED_VOIR_RAPPORTS = "ged.voir_rapports", "Voir les rapports"
    GED_DEPOSER_RAPPORTS = "ged.deposer_rapports", "Déposer des rapports"
    GED_SUPPRIMER_RAPPORTS = "ged.supprimer_rapports", "Supprimer des rapports"
    GED_VOIR_ADMINISTRATIF = "ged.voir_administratif", "Voir les documents administratifs"
    GED_DEPOSER_ADMINISTRATIF = "ged.deposer_administratif", "Déposer des documents administratifs"
    GED_SUPPRIMER_ADMINISTRATIF = (
        "ged.supprimer_administratif",
        "Supprimer des documents administratifs",
    )
    GED_VOIR_PHOTOS = "ged.voir_photos", "Voir les photos"
    GED_DEPOSER_PHOTOS = "ged.deposer_photos", "Déposer des photos"
    GED_SUPPRIMER_PHOTOS = "ged.supprimer_photos", "Supprimer des photos"
    GED_VOIR_DIVERS = "ged.voir_divers", "Voir les documents divers"
    GED_DEPOSER_DIVERS = "ged.deposer_divers", "Déposer des documents divers"
    GED_SUPPRIMER_DIVERS = "ged.supprimer_divers", "Supprimer des documents divers"

    # F9 Stock & Approvisionnements
    STOCK_LIRE = "stock.lire", "Consulter le stock et les mouvements"
    STOCK_DA_CREER = "stock.da_creer", "Émettre une demande d'approvisionnement (DA)"
    STOCK_DA_MODIFIER = "stock.da_modifier", "Modifier une DA au statut EN_ATTENTE"
    STOCK_DA_LIRE = "stock.da_lire", "Voir les demandes d'approvisionnement (DA)"
    STOCK_BC_EMETTRE = "stock.bc_emettre", "Émettre un bon de commande (exclusif DO/DG)"
    STOCK_BC_LIRE = "stock.bc_lire", "Voir les bons de commande (BC)"
    STOCK_BC_CLOTURER = "stock.bc_cloturer", "Clôturer un bon de commande partiel"
    STOCK_RECEPTION_SAISIR = (
        "stock.reception_saisir",
        "Saisir une réception de livraison sur chantier",
    )
    STOCK_BRV_VALIDER_CT = "stock.brv_valider_ct", "Valider le BRV matériaux (technique)"
    STOCK_BRV_VALIDER_CP = "stock.brv_valider_cp", "Valider le BRV équipements (séquentiel)"
    STOCK_JUSTIFICATIF_UPLOADER = (
        "stock.justificatif_uploader",
        "Téléverser le bon de livraison (BL) signé",
    )
    STOCK_MOUVEMENT_MANUEL_CREER = (
        "stock.mouvement_manuel_creer",
        "Saisir un mouvement manuel de stock",
    )
    STOCK_TRANSFERT_INTER_LOTS = "stock.transfert_inter_lots", "Autoriser un transfert inter-lots"
    STOCK_TRANSFERT_INTER_CHANTIERS = (
        "stock.transfert_inter_chantiers",
        "Autoriser un transfert inter-chantiers",
    )
    STOCK_INVENTAIRE_REALISER = "stock.inventaire_realiser", "Réaliser un inventaire physique"
    STOCK_INVENTAIRE_VALIDER = "stock.inventaire_valider", "Valider un inventaire physique"


# Alias sémantique
PermissionCode = CodePermission


# --------------------------------------------------------------------------
# F6 — Gestion Documentaire (GED)
# --------------------------------------------------------------------------
class CategorieDocument(models.TextChoices):
    """Les 6 catégories métier BTP de la gestion documentaire (F6)."""

    PLANS = "PLANS", "Plans"
    CONTRATS = "CONTRATS", "Contrats"
    RAPPORTS = "RAPPORTS", "Rapports"
    ADMINISTRATIF = "ADMINISTRATIF", "Administratif"
    PHOTOS = "PHOTOS", "Photos"
    DIVERS = "DIVERS", "Divers"


class TypeSourceLiaison(models.TextChoices):
    """Sources automatiques de documents pour liaison inter-modules (RG-15 / F6)."""

    F1_CONTRAT = "F1_CONTRAT", "Contrat / Avenant (F1)"
    F2_RAPPORT = "F2_RAPPORT", "Rapport journalier (F2)"
    F9_BRV = "F9_BRV", "Bon de réception / BL (F9)"


TypeSourceDocument = TypeSourceLiaison


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------
class CanalNotification(models.TextChoices):
    """Canaux de diffusion des notifications."""

    IN_APP = "IN_APP", "In-app (cloche)"
    EMAIL = "EMAIL", "E-mail"
    PUSH = "PUSH", "Push mobile"


class TypeEvenementNotification(models.TextChoices):
    """Types d'événements déclencheurs de notifications."""

    # Projets / Chantier
    PROJET_CREE = "PROJET_CREE", "Nouveau projet créé"
    RAPPORT_SOUMIS = "RAPPORT_SOUMIS", "Rapport de chantier soumis"
    RAPPORT_APPROUVE = "RAPPORT_APPROUVE", "Rapport de chantier approuvé"
    ALERTE_RETARD = "ALERTE_RETARD", "Alerte de retard de chantier"
    BLOCAGE_CRITIQUE = "BLOCAGE_CRITIQUE", "Blocage critique signalé"

    # F6 GED
    DOCUMENT_DEPOSE = "DOCUMENT_DEPOSE", "Nouveau document déposé"

    # F9 Stock
    DA_CREEE = "DA_CREEE", "Demande d'approvisionnement créée"
    BC_EMIS = "BC_EMIS", "Bon de commande émis"
    BRV_RECU = "BRV_RECU", "Livraison réceptionnée sur chantier"
    BRV_VALIDE = "BRV_VALIDE", "Bon de réception (BRV) validé"
    STOCK_ALERTE_SEUIL = "STOCK_ALERTE_SEUIL", "Alerte stock sous seuil critique"
    INVENTAIRE_VALIDE = "INVENTAIRE_VALIDE", "Session d'inventaire validée"

    # Générique
    AUTRE = "AUTRE", "Autre notification"


# --------------------------------------------------------------------------
# F9 — Stock & Approvisionnements
# --------------------------------------------------------------------------
class CategorieArticle(models.TextChoices):
    """Catégories d'articles au catalogue stock."""

    MATERIAU = "MATERIAU", "Matériau"
    EQUIPEMENT = "EQUIPEMENT", "Équipement"
    CONSOMMABLE = "CONSOMMABLE", "Consommable"
    OUTILLAGE = "OUTILLAGE", "Outillage"


TypeArticle = CategorieArticle


class StatutDemandeAppro(models.TextChoices):
    """Statuts du cycle d'une demande d'approvisionnement (DA)."""

    EN_ATTENTE = "EN_ATTENTE", "En attente"
    COMMANDEE_PARTIELLEMENT = "COMMANDEE_PARTIELLEMENT", "Commandée partiellement"
    COMMANDEE = "COMMANDEE", "Commandée"
    SOLDEE = "SOLDEE", "Soldée"
    ANNULEE = "ANNULEE", "Annulée"


StatutDA = StatutDemandeAppro


class TypeCommande(models.TextChoices):
    """Origine d'un bon de commande."""

    STANDARD = "STANDARD", "Issue d'une DA"
    COMMANDE_DIRECTE = "COMMANDE_DIRECTE", "Commande directe (urgence)"


OrigineBonCommande = TypeCommande


class StatutBonCommande(models.TextChoices):
    """Statuts d'un bon de commande (BC)."""

    EMIS = "EMIS", "Émis"
    EN_ATTENTE_LIVRAISON = "EN_ATTENTE_LIVRAISON", "En attente de livraison"
    RECU_PARTIELLEMENT = "RECU_PARTIELLEMENT", "Reçu partiellement"
    LIVRE = "LIVRE", "Livré"
    ANNULE = "ANNULE", "Annulé"


StatutBC = StatutBonCommande


class StatutReceptionChantier(models.TextChoices):
    """Statuts de la réception terrain et du bon de réception et validation (BRV)."""

    EN_ATTENTE_VALIDATION_CT = "EN_ATTENTE_VALIDATION_CT", "En attente de validation CT"
    EN_ATTENTE_VALIDATION_CP = "EN_ATTENTE_VALIDATION_CP", "En attente de validation CP"
    VALIDE_WORKFLOW = "VALIDE_WORKFLOW", "Validé workflow (attente justificatif)"
    VALIDE_AVEC_JUSTIFICATIF = "VALIDE_AVEC_JUSTIFICATIF", "Validé avec justificatif (BRV complet)"
    REJETE = "REJETE", "Rejeté"


StatutLivraison = StatutReceptionChantier


class TypeMouvementStock(models.TextChoices):
    """Types de mouvements de stock (immuables)."""

    ENTREE = "ENTREE", "Entrée de stock"
    SORTIE = "SORTIE", "Sortie de stock"
    TRANSFERT = "TRANSFERT", "Transfert"
    INVENTAIRE = "INVENTAIRE", "Ajustement d'inventaire"


class SourceMouvementStock(models.TextChoices):
    """Origine d'un mouvement de stock."""

    BRV = "BRV", "Bon de réception et validation"
    F2 = "F2", "Rapport journalier F2"
    MANUEL = "MANUEL", "Sortie manuelle"
    INVENTAIRE = "INVENTAIRE", "Session d'inventaire"
    TRANSFERT = "TRANSFERT", "Transfert inter-lots / inter-chantiers"


class StatutSessionInventaire(models.TextChoices):
    """Statuts d'une session d'inventaire physique."""

    BROUILLON = "BROUILLON", "Brouillon / En cours"
    VALIDE = "VALIDE", "Validée par le CP"
    ANNULE = "ANNULE", "Annulée"


class StatutLigneInventaire(models.TextChoices):
    """Statut de conformité d'une ligne d'inventaire."""

    CONFORME = "CONFORME", "Conforme"
    ECART_ACCEPTABLE = "ECART_ACCEPTABLE", "Écart acceptable"
    DEPASSEMENT_SEUIL = "DEPASSEMENT_SEUIL", "Dépassement de seuil"
