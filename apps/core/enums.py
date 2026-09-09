"""Énumérations transverses — CCD Digital.

Reprend §3 du MLD. Toute valeur qui pilote une règle de gestion est ici,
et non dans une table : un `if` du code ne doit pas dépendre d'une ligne
qu'un utilisateur peut modifier (décision D7).

Toute modification de ces listes est une migration.
"""

from django.db import models


class RoleGlobal(models.TextChoices):
    ADMIN = "AD", "Administrateur"
    DIRECTEUR_GENERAL = "DG", "Directeur Général / PDG"
    DIRECTEUR_PROJET = "DP", "Directeur de Projet"
    CHEF_PROJET = "CP", "Chef de Projet"
    CONDUCTEUR_TRAVAUX = "CT", "Conducteur de Travaux"
    CHEF_CHANTIER = "CC", "Chef de Chantier"
    INGENIEUR_TECHNICIEN = "IT", "Ingénieur / Technicien"
    RESPONSABLE_FINANCIER = "RF", "Responsable Financier"
    DIRECTEUR_FINANCIER = "DF", "Directeur Financier"
    RESPONSABLE_ACHATS = "RA", "Responsable Achats"
    MAGASINIER = "MAG", "Magasinier"
    RESPONSABLE_RH = "RH", "Responsable RH"
    SOUS_TRAITANT = "ST", "Sous-traitant"
    FOURNISSEUR = "FRN", "Fournisseur"
    MAITRE_OUVRAGE = "MOA", "Maître d'Ouvrage (Client)"
    VISITEUR = "VI", "Visiteur"


class RoleProjet(models.TextChoices):
    DIRECTEUR_PROJET = "DP", "Directeur de Projet"
    CHEF_PROJET = "CP", "Chef de Projet"
    CONDUCTEUR_TRAVAUX = "CT", "Conducteur de Travaux"
    CHEF_CHANTIER = "CC", "Chef de Chantier"
    INGENIEUR_TECHNICIEN = "IT", "Ingénieur / Technicien"
    MAGASINIER = "MAG", "Magasinier"
    SOUS_TRAITANT = "ST", "Sous-traitant"
    FOURNISSEUR = "FRN", "Fournisseur"
    MAITRE_OUVRAGE = "MOA", "Maître d'Ouvrage (Client)"
    VISITEUR = "VI", "Visiteur"


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
    TERMINE = "TERMINE", "Terminé"
    ARCHIVE = "ARCHIVE", "Archivé"


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


class TypeTiers(models.TextChoices):
    PERSONNE = "PERSONNE", "Personne physique"
    ENTREPRISE = "ENTREPRISE", "Personne morale"


class RoleTiersChoix(models.TextChoices):
    CLIENT_MOA = "CLIENT_MOA", "Client / Maître d'ouvrage"
    FOURNISSEUR = "FOURNISSEUR", "Fournisseur"
    SOUS_TRAITANT = "SOUS_TRAITANT", "Sous-traitant"
    TACHERON = "TACHERON", "Tâcheron"
    BUREAU_CONTROLE = "BUREAU_CONTROLE", "Bureau de contrôle"
    ADMINISTRATION = "ADMINISTRATION", "Administration"
    PRESTATAIRE = "PRESTATAIRE", "Prestataire"


class TypeObjetLie(models.TextChoices):
    """Cibles autorisées d'une liaison de document (RG-15)."""

    PROJET = "PROJET", "Projet"
    LOT = "LOT", "Lot"
    ACTIVITE = "ACTIVITE", "Activité"
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


class NiveauAcces(models.IntegerChoices):
    """Niveaux d'accès aux modules pour le RBAC (Socle IAM / Projets)."""

    AUCUN = 0, "Aucun"
    LECTURE = 1, "Lecture"
    ECRITURE = 2, "Écriture / Saisie"
    VALIDATION = 3, "Validation / Approbation"


class ModuleChoix(models.TextChoices):
    """Les 12 modules applicatifs de CCD Digital."""

    PROJETS = "projets", "Gestion des Projets"
    CHANTIER = "chantier", "Suivi Technique / Chantier"
    FINANCE = "finance", "Gestion Financière"
    ACHATS = "achats", "Achats & Approvisionnements"
    STOCKS = "stocks", "Gestion des Stocks"
    RH = "rh", "Ressources Humaines"
    EQUIPEMENTS = "equipements", "Matériel & Équipements"
    QHSE = "qhse", "QHSE"
    CONTRATS = "contrats", "Contrats & Sous-traitance"
    TIERS = "tiers", "Parties Prenantes / Tiers"
    GED = "ged", "Gestion Documentaire (GED)"
    PILOTAGE = "pilotage", "Pilotage & Tableaux de bord"
