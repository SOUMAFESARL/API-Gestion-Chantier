# Inventaire du Lot 0

## I-01 Occurrences de `niveau_max` (A-12)

- apps/accounts/services/roles.py:237 | Vérifie si le niveau demandé dépasse le plafond niveau_max du modèle de rôle
- apps/accounts/services/roles.py:241 | Message d'erreur signalant le dépassement du plafond niveau_max
- apps/accounts/services/roles.py:290 | Dictionnaire associant chaque code de module à son niveau_max
- apps/catalogue/models/modele_role.py:86 | Définition du champ niveau_max sur le modèle ModeleRoleModule
- apps/catalogue/models/modele_role.py:108 | Représentation textuelle de ModeleRoleModule affichant le niveau_max
- apps/catalogue/tests/test_modeles_roles.py:15 | Test vérifiant les plafonds niveau_max pour le rôle DG
- apps/catalogue/tests/test_modeles_roles.py:21 | Test vérifiant les plafonds niveau_max pour le rôle AD
- apps/catalogue/tests/test_modeles_roles.py:32 | Test vérifiant les plafonds niveau_max pour le rôle CT
- apps/catalogue/tests/test_modeles_roles.py:38 | Test vérifiant les plafonds niveau_max pour le rôle MAG
- apps/core/droits.py:9 | Docstring décrivant le plafond du modèle associé au rôle ModeleRoleModule.niveau_max
- apps/core/droits.py:74 | Docstring de la fonction retournant les plafonds niveau_max par module
- apps/core/droits.py:98 | Enregistrement de niveau_max dans le dictionnaire des plafonds

Total : 12

## I-02 Conditions copiées de test « est le DG » (B-03)

- apps/accounts/services/profil.py:159 | or getattr(utilisateur, "is_dg", False)
- apps/accounts/services/roles.py:575 | getattr(supprime_par, "is_dg", False)
- apps/accounts/services/utilisateurs.py:52 | if getattr(collaborateur, "is_owner", False) or getattr(collaborateur, "is_dg", False) or getattr(collaborateur, "role_global", None) == RoleGlobal.DIRECTEUR_GENERAL:
- apps/accounts/views/collaborateur.py:270 | getattr(request.user, "is_dg", False) or getattr(request.user, "is_owner", False)
- apps/accounts/views/collaborateur.py:489 | or getattr(collaborateur, "is_dg", False)
- apps/accounts/views/collaborateur.py:509 | getattr(request.user, "is_dg", False)
- apps/accounts/views/collaborateur.py:584 | or getattr(collaborateur, "is_dg", False)
- apps/accounts/views/collaborateur.py:637 | or getattr(collaborateur, "is_dg", False)
- apps/accounts/views/role.py:45 | if not (getattr(user, "is_dg", False) or getattr(user, "is_owner", False)):
- apps/accounts/views/role.py:195 | getattr(request.user, "is_dg", False)
- apps/accounts/views/role.py:382 | getattr(request.user, "is_dg", False)
- apps/core/permissions.py:141 | or getattr(user, "is_dg", False)
- apps/projets/views/affectation.py:39 | or getattr(user, "is_dg", False)

Total : 13

## I-03 Facturation et limites du plan (C-04)

- Limite collaborateurs actifs : Vérification stricte des sièges occupés avant invitation | apps/billing/services/quota.py:66 apps/accounts/views/collaborateur.py:298
- Limite projets : Aucune limite de nombre de projets imposée par l'abonnement | ABSENT
- Erreur dédiée à la limite : Exception QuotaPlanAtteint dédiée au blocage de quota | apps/core/exceptions.py:125
- Abonnement expiré (lecture seule) : Aucun basculement global du tenant en lecture seule lors de l'expiration | ABSENT
- Actions de paiement : Endpoints d'initiation et de consultation de session CinetPay | apps/billing/views/cinetpay.py:55

## I-04 Impersonation (H-01)

- Claim read_only émis : Émission du flag read_only dans le jeton JWT d'assistance | apps/platform_admin/services/impersonation.py:158
- Middleware lecteur du claim : Interception et contrôle des requêtes par le middleware | apps/platform_admin/middleware.py:40
- Méthodes bloquées : POST, PUT, PATCH, DELETE | apps/platform_admin/middleware.py:21
- Journalisation début de session : Traçabilité au démarrage dans JournalPlateforme et JournalAudit | apps/platform_admin/services/impersonation.py:170 apps/platform_admin/services/impersonation.py:193
- Journalisation fin de session : Traçabilité à la clôture dans JournalPlateforme et JournalAudit | apps/platform_admin/services/impersonation.py:261 apps/platform_admin/services/impersonation.py:279
- E-mail au DG : Aucun e-mail notifiant le DG lors de l'ouverture d'une session Super Admin | ABSENT

## I-05 Statut CRITIQUE (E-09)

- Comportement actuel du statut CRITIQUE : ECRASE | tests/caracterisation/test_statut_critique.py:19

## I-06 REGISTRE des permissions (A-01, A-02)

- Fichier du REGISTRE : REGISTRE | apps/core/registre_permissions.py:16
- projets.lire | projets
- projets.ecrire | projets
- projets.creer | projets
- projets.changer_statut | projets
- projets.voir_tous | projets
- chantier.lire | chantier
- chantier.rediger | chantier
- chantier.valider | chantier
- tiers.lire | tiers
- tiers.ecrire | tiers
- pilotage.lire | pilotage
- pilotage.voir_montants | pilotage
- administration.collaborateurs_voir | administration
- administration.collaborateurs_gerer | administration
- administration.roles_gerer | administration
- administration.entreprise_modifier | administration

Total : 16

## I-07 Modules et portée proposée (D-04)

- projets | PROJET
- chantier | PROJET
- tiers | GLOBALE
- pilotage | GLOBALE
- administration | GLOBALE
- ged | A_CONFIRMER

## I-08 Tests existants à adapter (A-12, E-08)

- apps/projets/tests/test_statuts_crud.py:40 | Test vérifiant le changement de statut par un membre à inverser selon E-08
- tests/caracterisation/test_statuts_projet.py:1 | Caractérisation du comportement actuel des statuts de projet face aux droits
- apps/catalogue/tests/test_modeles_roles.py:15 | Test vérifiant les plafonds niveau_max des modèles de rôles à adapter selon A-12

Total : 3

## I-09 Comptages de départ

- PermissionModule : 37
- MembreDuProjet : 66
- RoleRequis : 26
- RoleGlobal : 210
- role_global : 185
- ROLES_DIRECTION : 1
- ROLES_GESTION_CHANTIER : 1
- ROLES_VALIDATION_CHANTIER : 1
- ContexteCreationProjetView : 3
- ProjetRoleModuleOverride : 32
- appliquer_modeles_roles : 2

## I-10 Tâche de fond, e-mail, audit (A-14, H-01)

- Tâche de fond (mécanisme) : Celery avec décorateur @shared_task | apps/projets/tasks.py:20
- Envoi d'e-mail existant : Fonction envoyer avec gabarits Django | apps/core/emails.py:52
- Journal d'audit existant : Fonction journaliser et modèle JournalAudit | apps/audit/services/__init__.py:20 apps/audit/models/__init__.py:23
