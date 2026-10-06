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

