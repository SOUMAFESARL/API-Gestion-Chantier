# Notes de changement API

## Lot 1 : REGISTRE, catalogue et permissions effectives

### Nouveaux refus et validations (HTTP 400 / 403)
- **[A-01] Validation des codes de permissions** : Les créations arbitraires de permissions hors du `REGISTRE` sont refusées avec `HTTP 400 Bad Request`.
- **[A-02] Immutabilité du module** : Le module associé à une permission ne peut pas être modifié.
- **[B-05] Sécurisation des permissions d'administration** : L'attribution ou la modification de permissions du module `administration.*` sur des rôles personnalisés ou système via les endpoints `/api/v1/roles/` et `/api/v1/parametres/roles/` est strictement refusée avec `HTTP 400 Bad Request`.

### Évolution du modèle de données et des contrats
- **[A-03] Granularité des permissions** : Suppression des verbes génériques (`LECTURE`, `ECRITURE`, `VALIDATION`, `SUPPRESSION`) dans `CataloguePermission`. La relation M2M `RoleModulePermission.permissions_catalogue` référence exclusivement les codes granulaires (`module.action`).
- **[A-04] Règle de non-inférence** : Les permissions effectives (`/profil/`) reflètent exactement la liste des permissions cochées, sans inférence automatique des niveaux inférieurs.
- **[A-06] Désactivation de modules** : La désactivation d'un module pour une entreprise retire immédiatement l'ensemble de ses permissions de la liste des permissions effectives.
- **[A-12] Suppression des plafonds de modèles** : Suppression définitive des anciens plafonds de niveau sur les modèles de rôles.
- **[A-15] Activation des modules à la création** : Le module `ged` n'est plus actif par défaut pour les nouvelles entreprises.
- **[B-11] Allègement des JWT** : Les jetons JWT ne transportent plus de liste de permissions statiques ; les droits sont résolus dynamiquement à chaque requête.

## Lot 2 : Rôle unique, DG calculé, portée et profil compatible

### Nouveaux refus et validations (HTTP 400 / 403 / 409)
- **[B-01 / L2-7] Refus d'ambiguïté de rôle (HTTP 400)** : Fournir simultanément `role_global` et `role_personnalise_id` lors de la création d'un collaborateur est rejeté avec `HTTP 400 Bad Request` (code d'erreur `role_ambigu`).
- **[B-03 / L2-4 / L2-6] Protection absolue du Directeur Général (HTTP 403)** : Toute tentative de modifier le rôle du DG, de le suspendre ou de le supprimer (y compris par le DG lui-même ou par un administrateur) est systématiquement refusée avec `HTTP 403 Forbidden`.
- **[B-03] Matrice de permissions du rôle DG intouchable (HTTP 403)** : La matrice de permissions du rôle `DG` ne peut pas être modifiée via l'API (`HTTP 403 Forbidden`). Ses permissions sont entièrement calculées dynamiquement.
- **[D-01] Validation de la portée (HTTP 400)** : Le champ `portee` n'accepte que les valeurs `ENTREPRISE` ou `PROJET`. Toute autre valeur est rejetée avec `HTTP 400 Bad Request`.
- **[D-02 / L2-5] Gouvernance de la portée (HTTP 403)** : Seul le Directeur Général peut modifier la portée des rôles de son entreprise. L'Administrateur délégué (AD) ne peut pas la modifier (`HTTP 403 Forbidden`). Le DG ne peut pas modifier la portée de son propre rôle (`HTTP 403 Forbidden`).
- **[D-03 / L2-1] Confirmation obligatoire du changement de portée (HTTP 409)** : Toute bascule de portée via `PATCH /api/v1/parametres/roles/{id}/` exige le paramètre explicite `confirmer: true`. En l'absence de ce paramètre, l'API répond avec `HTTP 409 Conflict`, le code d'erreur `confirmation_requise` et le corps `{"personnes_touchees": N}` (collaborateurs actifs portant ce rôle). Aucune donnée n'est altérée sans confirmation.

### Évolution du modèle de données et des contrats
- **[B-01] Rôle unique** : Unification des champs de rôles sur `Utilisateur`. Le champ `role` (ForeignKey vers `accounts.Role`) devient la source unique de vérité. Le champ `role_personnalise` est supprimé de la base de données. Le champ `role_global` est conservé comme alias en lecture seule pour compatibilité frontend.
- **[B-02] Rôles système souverains** : Les 10 rôles système souverains (`DG`, `AD`, `DO`, `DF`, `CP`, `CT`, `CC`, `MAG`, `BAI`, `VI`) vivent dans la table `Role` avec `est_systeme=True`. L'énumération Python n'est plus la source de vérité.
- **[B-03] Permissions du DG calculées** : Le DG n'a plus de permissions figées en base ; il reçoit dynamiquement toutes les permissions des modules actifs de l'entreprise et de l'administration.
- **[D-01 / D-07] Champ portée et migration** : Ajout du champ `portee` (`ENTREPRISE` / `PROJET`) sur `Role` et `ModeleRole`. Les rôles transverses (`DG`, `AD`, `DO`) et les rôles portant historiquement `projets.voir_tous` sont migrés vers `ENTREPRISE`, tous les autres vers `PROJET`.
- **[D-07] Suppression de `projets.voir_tous`** : Le code `projets.voir_tous` est définitivement retiré du `REGISTRE` et du catalogue de permissions. La visibilité projet est gouvernée par la portée du rôle.
- **[G-02] Compatibilité du profil pour le frontend** : `GET /api/v1/auth/profil/` conserve sa structure descendante exacte (`role_global`, `role_libelle`, `role_personnalise`, `habilitations` modulaires calculées de 0 à 3 et `permissions` effectives).

## Lot 3 : Garde unique et filtrage par projet (D-01, D-06, D-08)

### Nouveaux refus et validations (HTTP 403)
- **[D-08] Garde unique sur le module projets (`GardePermissionProjet`)** : Toute action sur le module projets ou ses ressources enfants (lots, activités, équipes, affectations, santé, programmation) exige simultanément la possession du code de permission RBAC (ex: `projets.lire`, `projets.ecrire`) ET (la portée `ENTREPRISE` ou une affectation active au chantier). Tout accès en dehors de cette condition est rejeté avec `HTTP 403 Forbidden` (`{"detail": "Vous n'êtes pas affecté à ce projet."}`).

### Évolution des contrats et du comportement de l'API
- **[D-01] Filtrage dynamique de la liste des projets** :
  - Pour les rôles de portée `ENTREPRISE` (DG, AD, DO ou rôle personnalisé configuré) : accès consolidé à l'ensemble des projets de l'entreprise, y compris les projets nouvellement créés.
  - Pour les rôles de portée `PROJET` (CP, CT, CC, etc.) : restriction stricte aux projets sur lesquels le collaborateur est affecté activement (`AffectationProjet.est_actif=True`) ou dont il est responsable direct (chef de projet / conducteur de travaux).
  - Un rôle de portée `PROJET` sans affectation active reçoit une liste vide (`[]`).
  - La désactivation d'une affectation masque immédiatement le chantier à la requête suivante, sans reconnexion.
  - La modification de portée d'un rôle (`PROJET` -> `ENTREPRISE`) est prise en compte instantanément à la requête suivante sans réauthentification.
- **[D-06] Filtrage du journal consolidé des reports** : L'endpoint `/api/v1/projets/journal-reports/` filtre désormais automatiquement les rapports de reports par les seuls projets accessibles à l'utilisateur selon sa portée et ses affectations.
- **[D-08] Éradication des gardes legacy** : `PermissionModule` et `MembreDuProjet` sont définitivement supprimés et remplacés par `GardePermissionProjet` et `APermission`.



## Lot 4 : Administration des rôles (A-13, B-04, B-06 à B-10, B-12, F-01, F-02)

### Nouveaux refus et validations (HTTP 403 / 400)
- **[A-13] Pas d'écriture dans les requêtes GET** : Les routes de consultation de listes et détails de rôles (`/api/v1/roles/` et `/api/v1/parametres/roles/`) n'appellent plus de création ou synchronisation paresseuse de rôles. Toute requête GET est 100% idempotente et sans effet de bord en base de données.
- **[B-04] Droits d'administration fixes de l'AD** : L'AD possède en dur 6 droits fixes du module administration (`collaborateurs_voir`, `collaborateurs_gerer`, `roles_gerer`, `abonnement_voir`, `factures_voir`, `onboarding_suivre`). Les 2 droits `entreprise_modifier` et `abonnement_gerer` sont strictement réservés au DG.
- **[B-06] Protection des comptes AD (HTTP 403)** : Un AD ne peut ni modifier le rôle, ni suspendre, ni réactiver, ni supprimer un autre compte AD ni son propre compte (`HTTP 403 Forbidden`). Seul le DG a autorité pour gérer, suspendre ou supprimer les administrateurs.
- **[B-07] Protection des rôles système contre l'AD (HTTP 403)** : Toute modification d'un rôle système par un non-DG est rejetée avec `HTTP 403 Forbidden` (`code: "modification_role_systeme_interdite"`). Seul le DG peut adapter un rôle système (B-10).
- **[B-08] Principe du moindre privilège / délégation (HTTP 403)** : Un AD ne peut créer ou modifier un rôle personnalisé qu'en attribuant des permissions faisant partie de ses propres permissions effectives (`code: "permission_hors_perimetre_ad"`).
- **[B-09] Attribution de rôles aux collaborateurs (HTTP 403)** : Un AD ne peut pas attribuer les rôles `DG`, `AD` ou `DF`, ni aucun rôle octroyant des permissions hors de son propre périmètre d'habilitation (`HTTP 403 Forbidden`).
- **[F-01] Garde unique sur l'administration des rôles (`administration.roles_gerer`) (HTTP 403)** : L'accès en lecture et en écriture sur `/roles/` et `/parametres/roles/` requiert la permission `administration.roles_gerer`. Les autres rôles sans ce droit reçoivent systématiquement un `HTTP 403 Forbidden`.

### Évolution des contrats et du comportement de l'API
- **[B-12] Gestion du cycle de vie des rôles personnalisés** : Support de `role_reassignation_id` lors de la suppression d'un rôle personnalisé pour réassigner de manière fluide les collaborateurs associés.
- **[F-02] Parité et équivalence totale `/roles/` et `/parametres/roles/`** : Les deux familles d'endpoints offrent désormais la même signature, le même niveau de sécurité, les mêmes codes de réponse HTTP et la même structure de données.

## Lot 5 : Projets, écritures, affectation, équipes (C-05, E-03 à E-07, E-13)

### Nouveaux refus et validations (HTTP 400 / 403 / 404)
- **[E-13] Suppression de la route `contexte-creation` (HTTP 404)** : L'endpoint `GET /api/v1/projets/contexte-creation/` a été supprimé définitivement. Les requêtes vers cette route renvoient désormais `HTTP 404 Not Found`.
- **[E-06] Suppression de la route d'override de permissions (HTTP 404)** : L'endpoint `/api/v1/projets/{id}/permissions-roles/` (GET, PUT, PATCH) a été supprimé définitivement.
- **[E-05] Garde souverain sur les affectations (`projets.affecter_membres`) (HTTP 403)** : Les opérations de création (`POST /projets/{id}/affectations/`), modification et révocation (`PATCH` et `DELETE` sur `/projets/{id}/affectations/{pk}/`) requièrent impérativement la permission `projets.affecter_membres`. Tout utilisateur dépourvu de ce droit (DO, CT, VI, BAI, CC, ou collaborateur non affecté / affectation désactivée) reçoit `HTTP 403 Forbidden`. L'étiquette `role_projet = 'CP'` ne confère aucun droit à un utilisateur dont le rôle n'a pas la permission.
- **[E-05] Validation stricte des candidats à l'affectation (HTTP 400)** : Tout candidat dont le compte est suspendu/inactif, inexistant, ou dont le rôle est à portée `ENTREPRISE` (DG, AD, DO) est immédiatement rejeté avec `HTTP 400 Bad Request` et le code d'erreur `candidat_invalide`. Seuls les collaborateurs actifs à portée `PROJET` peuvent être affectés.
- **[E-03] Garde souverain sur la gestion des équipes (`projets.gerer_equipes`) (HTTP 403)** : La constitution, la modification, la suppression d'équipes et l'association équipe-activité exigent la permission `projets.gerer_equipes`. Les rôles VI, BAI, CC, DO et non affectés reçoivent `HTTP 403 Forbidden`.
- **[E-03] Écritures sur les arrêts de chantier sous `projets.ecrire` (HTTP 403)** : La création, la modification et la suppression d'arrêts de chantier (`POST`, `PATCH`, `DELETE`) exigent la permission `projets.ecrire`.
- **[E-07] Validation d'appartenance des membres d'équipe (HTTP 400)** : Tenter d'ajouter à une équipe un collaborateur qui n'est pas préalablement affecté activement au projet est rejeté avec `HTTP 400 Bad Request`.

### Évolution des contrats et du comportement de l'API
- **[E-06] Suppression du champ `AffectationProjet.role`** : Le champ `role` (ForeignKey vers `accounts.Role`) a été définitivement supprimé du modèle `AffectationProjet`. Les habilitations ne sont plus altérées localement par chantier. Le champ `role_projet` est une étiquette d'affichage et synchronise uniquement les attributs informatifs `chef_projet` et `conducteur_travaux` du projet.
- **[E-04] Auto-affectation des créateurs de projet à portée PROJET** : Quand un créateur à portée `PROJET` disposant de `projets.creer` crée un projet, il est automatiquement doté d'une `AffectationProjet` active sur ce projet (avec `role_projet=""` et sans altérer `chef_projet`). Les créateurs à portée `ENTREPRISE` (DG, AD) ne reçoivent aucune affectation.
- **[C-05 puce 2] Nouvelle route de collaborateurs affectables** : Endpoint `GET /api/v1/projets/{projet_id}/collaborateurs-affectables/` retournant la liste minimale (`id`, `nom`, `role`) des collaborateurs actifs éligibles (portée `PROJET`), sans informations personnelles (email, téléphone) ni rôles transverses `ENTREPRISE`.
- **[C-05 puce 3] Masquage des données personnelles (PII)** : Dans `GET /api/v1/projets/{projet_id}/affectations/`, les champs `email` et `telephone` sont strictement omis pour les utilisateurs ne disposant pas des permissions `projets.affecter_membres` ou `projets.gerer_equipes` (VI, CC, DO).

## Lot 6 : Statuts de projet, transitions et workflow chantier (E-08, E-09, E-10)

### Nouveaux refus et validations (HTTP 403 / 409)
- **[E-08] Suppression de l'exception historique "PATCH statut seul" (HTTP 403)** : L'ancienne exception qui permettait à tout utilisateur affecté disposant de la seule permission `projets.lire` de modifier le statut d'un projet a été définitivement supprimée.
- **[E-08] Séparation des permissions de statut (HTTP 403)** :
  - La modification vers un statut opérationnel (`EN_ATTENTE`, `EN_COURS`, `EN_RETARD`, `CRITIQUE`, `SUSPENDU`, `BLOQUE`, `RECEPTIONNE`, `TERMINE`) requiert la permission `projets.changer_statut` (détenue par DG, AD, DO, CP). Les rôles sans cette permission (CT, CC, VI, BAI) reçoivent `HTTP 403 Forbidden`.
  - La modification vers un statut de fin de vie (`RESILIE`, `ARCHIVE`, `DESACTIVE`) ainsi que la réouverture/réactivation d'un chantier clos requiert la permission `projets.resilier_archiver` (réservée à DG, AD, DO). Le Chef de Projet (CP) reçoit `HTTP 403 Forbidden`.
  - Les requêtes modifiant d'autres champs du projet en plus du statut exigent la permission `projets.ecrire`.
- **[E-10] Verrouillage des écritures sur projets en fin de vie (HTTP 409)** :
  - Lorsqu'un projet est au statut `RESILIE`, `ARCHIVE` ou `DESACTIVE`, il est verrouillé en lecture seule.
  - Toute tentative d'écriture (création de rapport journalier, création/modification/suppression de lot, activité, équipe, affectation, reprogrammation, ou modification du projet hors réouverture) est rejetée avec `HTTP 409 Conflict` et le code d'erreur standard `projet_clos` (`{"detail": "...", "code": "projet_clos"}`).
- **[E-10] Verrouillage des rapports et reprogrammations sur projets achevés (HTTP 409)** :
  - Lorsqu'un projet est au statut `RECEPTIONNE` ou `TERMINE`, l'enregistrement de nouveaux rapports journaliers (`POST /api/v1/rapports/`) et les reprogrammations de calendrier (`POST /api/v1/projets/{id}/reprogrammer/`) sont rejetés avec `HTTP 409 Conflict` et le code d'erreur `projet_clos`. Les modifications de structure restent admises.
- **[E-10] Priorité des gardes (Ordre d'évaluation)** : Les contrôles de permissions RBAC (`HTTP 403`) sont évalués en amont de l'état du chantier (`HTTP 409`). Un utilisateur sans permission reçoit 403 même sur un projet clos.

### Évolution des contrats et du comportement de l'API
- **[E-09] Protection du statut CRITIQUE** : Le statut `CRITIQUE` peut être positionné manuellement par un utilisateur habilité (`projets.changer_statut`) et n'est plus jamais écrasé par la tâche d'évaluation quotidienne (`executer_evaluation_quotidienne_schema`).
- **[E-10] Maintien des écritures sur chantiers en arrêt** : Les statuts opérationnels d'arrêt (`SUSPENDU`, `BLOQUE`) maintiennent toutes les capacités d'écriture ouvertes (`HTTP 201 / 200`).

## Lot 7 : Montants financiers et visibilité budgétaire (E-11, E-12)

### Nouveaux refus et validations (HTTP 400)
- **[E-11] Refus d'écriture de montant sans la permission `projets.voir_montants` (HTTP 400)** :
  - Tout utilisateur qui possède la permission d'écriture (`projets.ecrire` ou `projets.creer`), comme l'Administrateur Délégué (`AD`) ou le Conducteur de Travaux (`CT`), mais qui ne possède **pas** la permission `projets.voir_montants`, reçoit un refus `HTTP 400 Bad Request` lorsqu'il transmet un montant non nul (`budget_initial_montant`).
  - Aucun enregistrement n'est effectué en base : ni le montant, ni les autres champs d'une création ou d'une modification partielle ne sont enregistrés en cas de 400.
  - La valeur `null` ou l'absence du champ reste acceptée et ignorée sans erreur (`HTTP 200 / 201`), permettant aux rôles sans droit financier de créer ou modifier les chantiers, lots et activités sans montant (règle P-1 et P-3).
  - L'ordre des contrôles est strictement préservé : le contrôle d'accès `HTTP 403 Forbidden` (`projets.ecrire` ou appartenance) prime sur le contrôle de validation `HTTP 400 Bad Request` (règle P-2).

### Évolution des contrats et du comportement de l'API
- **[E-11] Masquage strict en lecture des montants sans `projets.voir_montants`** :
  - Pour tous les utilisateurs dépourvus de la permission `projets.voir_montants` (AD, CT, CC, MAG, BAI, VI) :
    - Le champ `budget_initial_montant` est **strictement absent** du JSON (ni `null`, ni `0`) sur toutes les ressources : projets (liste et détail), lots (liste et détail), activités (liste et détail), et liste des projets du tableau de bord.
    - Le champ `budget_total_montant` est strictement absent des métriques du tableau de bord.
    - Le champ `montant` des bons de paiement du tableau de bord est strictement masqué.
    - Filet de sécurité générique : aucune clé dont le nom évoque une donnée financière ou budgétaire n'est exposée aux rôles sans droit (y compris dans les statistiques).
    - Les champs non financiers (`id`, `reference`, `nom`, `statut`, `bons_a_signer_count`, `bons_paiement_a_valider`) restent présents et intacts pour tous les rôles autorisés.
- **[E-12] Retrait définitif des champs financiers sans source réelle** :
  - Suppression totale pour l'ensemble des utilisateurs (Directeur Général `DG` compris) des 4 champs suivants :
    - `budget_consomme_montant` (retiré de `ProjetSerializer` et du tableau de bord)
    - `budget_engage_montant` (retiré des métriques du tableau de bord)
    - `bons_a_signer_montant` (retiré des métriques du tableau de bord)
    - `budget_activites_montant` (retiré des statistiques de projet)
  - Suppression définitive de la valeur de consommation fictive calculée en dur à `0.225` (22,5 %).
  - Impact frontend : la tuile « Dépensé » et la zone budget doivent prendre en compte l'absence de ces champs et le masquage par `voir_montants`.

## Lot 8 : Visibilité multi-chantiers, affectations et parité des routes

### Refus HTTP et validations
- **[C-01] Cloisonnement par affectation chantier** : Un utilisateur avec une portée `CHANTIER` ne peut accéder qu'aux chantiers sur lesquels il est explicitement affecté. Tout accès à un autre chantier est rejeté avec `HTTP 403 Forbidden` ou masqué dans les listes.
- **[C-02] Droits d'écriture par affectation** : Les écritures sont strictement restreintes aux collaborateurs affectés possédant la permission requise.
- **[C-03] Cascade de visibilité sur les sous-ressources** : L'accès aux lots, activités, plannings et journaux de chantier hérite du contrôle d'affectation au niveau projet.
- **[C-04] Règle d'affectation des collaborateurs** : Refus d'affectation si l'utilisateur est inactif ou dépourvu de rôle de projet valide.
- **[C-05] Protection de la composition des équipes** : Refus de suppression de la dernière affectation requise sur un chantier actif.
- **[F-03] Parité stricte des routes `/api/v1/projets/` et `/api/v1/chantiers/`** : Comportement, schémas et permissions identiques sur les deux chemins.
- **[F-04] Alignement des filtres et pagination** : Les filtres par statut, dates et recherche textuelle sont rigoureusement alignés.
- **[F-05] Égalité des permissions requises** : Application uniforme des vérifications `projets.creer`, `projets.ecrire`, `projets.voir`.
- **[F-06] Alignement des réponses d'erreurs** : Mêmes statuts HTTP et formats de payload en cas d'erreur.
- **[F-07] Nettoyage des routes orphelines** : Suppression des endpoints non maintenus.
- **[F-08] Maintien des alias de compatibilité** : Conservation transparente des alias avec redirection ou traitement identique.

### Codes d'erreur
- `HTTP 403 Forbidden` : `permission_refusee`, `chantier_non_affecte`.
- `HTTP 404 Not Found` : ressource inexistante ou hors périmètre d'affectation.
- `HTTP 400 Bad Request` : affectation invalide ou doublon d'affectation.

### Routes et endpoints concernés
- `/api/v1/projets/` et alias `/api/v1/chantiers/`
- `/api/v1/projets/{id}/affectations/`
- `/api/v1/projets/{id}/lots/`
- `/api/v1/projets/{id}/activites/`

### Impact frontend
- Filtrage automatique des sélecteurs de chantiers pour les rôles de chantier (Conducteur de Travaux, Chef de Chantier).
- Les écrans de gestion des équipes s'appuient sur les endpoints d'affectation unifiés.

### Règles couvertes
- C-01, C-02, C-03, C-04, C-05, F-03, F-04, F-05, F-06, F-07, F-08

## Lot 9 : Propagation super admin, plateforme et sessions d'assistance

### Refus HTTP et contrôles d'accès plateforme
- **[H-01] Contrôle strict de session d'assistance (Impersonation)** : Le jeton d'assistance super admin est en lecture seule stricte. Toute tentative d'écriture (POST, PUT, PATCH, DELETE) est rejetée avec `HTTP 403 Forbidden` et le code `ecriture_interdite_assistance`, à l'exception de la déconnexion explicite.
- **[H-02] Cloisonnement de l'API plateforme** : Seuls les utilisateurs du schéma public ayant `is_staff=True` ou `is_superuser=True` peuvent accéder à l'API `/admins/`. Les requêtes non autorisées reçoivent `HTTP 403 Forbidden`.
- **[A-05] Non-attribution automatique des nouvelles permissions** : Une nouvelle permission synchronisée dans le catalogue n'est ajoutée à aucun rôle stocké (y compris AD). Elle devient sélectionnable par le DG et est possédée par le DG par calcul dynamique.
- **[A-06] Désactivation globale d'une permission catalogue** : La désactivation d'une permission retire instantanément son effet sur tous les rôles de toutes les entreprises.
- **[A-07] Propagation idempotente des rôles système** : `propager_roles_systeme` ne crée que les rôles système manquants et n'écrase jamais un rôle existant.
- **[A-08] Immutabilité rétroactive des modèles** : La modification d'un modèle de rôle n'impacte pas les rôles déjà instanciés dans les entreprises.
- **[A-09] Résolution de conflit rôle système / rôle personnalisé** : En cas de collision de code ou nom, le rôle système l'emporte et le rôle personnalisé est automatiquement renommé avec le suffixe `_perso`.
- **[A-10] Désactivation d'un module client** : Retire immédiatement les permissions associées des permissions effectives, tout en conservant les configurations intactes en base.
- **[A-11] Activation d'un module client** : Initialise les permissions par défaut du modèle sur les rôles système et crée une ligne vide pour les rôles personnalisés.
- **[A-14] Notification e-mail au Directeur Général** : Envoi d'un e-mail d'audit au DG lors de l'ouverture d'assistance, activation/désactivation de modules, propagation de rôle système ou désactivation de permission catalogue.

### Codes d'erreur
- `ecriture_interdite_assistance` : renvoyé en HTTP 403 lors d'une tentative d'écriture en mode assistance.
- `HTTP 403 Forbidden` : accès refusé aux non-super-admins sur `/admins/`.
- `HTTP 404 Not Found` : client ou module introuvable.

### Routes plateforme et assistance
- `/api/v1/admins/clients/{client_id}/modules/{module_id}/activer/`
- `/api/v1/admins/clients/{client_id}/modules/{module_id}/desactiver/`
- `/api/v1/admins/assistance/connexion/`
- `/api/v1/admins/assistance/deconnexion/`
- `/api/v1/admins/modeles-roles/`
- `/api/v1/admins/catalogue-permissions/`

### Impact frontend
- Affichage de la bannière de session d'assistance en lecture seule.
- Désactivation préventive des formulaires et boutons de soumission pour l'opérateur de support.

### Règles couvertes
- A-05, A-06, A-07, A-08, A-09, A-10, A-11, A-14, H-01, H-02

## Lot 10 : Clôture, nettoyage, invariance et certification finale

### Refus HTTP et préservation des contrats
- **[F-09] Invariance météo et référentiels** : Les endpoints météo et villes préservent rigoureusement leur comportement historique. Si le projet n'est pas renseigné ou n'est pas visible, repli transparent sur la ville du siège de l'entreprise avec statut 200.
- **[G-02] Compatibilité totale du contrat profil frontend** : L'endpoint `/api/v1/auth/profil/` garantit la présence et le typage exact de tous les champs attendus par le client web (`habilitations`, `role_personnalise`, `permissions_effectives`). Refus `HTTP 401 Unauthorized` pour tout utilisateur non authentifié.

### Codes d'erreur
- Aucun nouveau code d'erreur spécifique introduit.
- Préservation des codes standards `HTTP 401 Unauthorized` et `HTTP 403 Forbidden`.

### Routes stabilisées
- `/api/v1/projets/meteo/`
- `/api/v1/projets/referentiels/villes/`
- `/api/v1/auth/profil/`

### Impact frontend
- **[F-10] Nettoyage et assainissement** : Suppression des anciennes constantes mortes (`ROLES_DIRECTION`, `ROLES_GESTION_CHANTIER`, `ROLES_VALIDATION_CHANTIER`) et élimination des mentions obsolètes de l'ancien rôle « DF » dans les docstrings et descriptions OpenAPI.
- **[G-03] Documentation exhaustive des évolutions d'API** : Alignement de toutes les spécifications pour l'équipe frontend et zéro régression contractuelle.

### Règles couvertes
- F-09, F-10, G-02, G-03




