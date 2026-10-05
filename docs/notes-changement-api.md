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
