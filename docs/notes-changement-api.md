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
