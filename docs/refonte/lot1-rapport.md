# Rapport lot 1

## Règles
| Règle | Statut (FAIT / PARTIEL / NON FAIT) | Tests | Fichiers modifiés |
|---|---|---|---|
| A-01 | FAIT | `test_a01_catalogue_egal_registre_apres_synchronisation`, `test_a01_synchronisation_idempotente`, `test_a01_creation_permission_code_inconnu_refusee`, `test_a01_registre_est_source_unique` | `apps/catalogue/models/permission.py`, `apps/core/registre_permissions.py`, `apps/catalogue/management/commands/synchroniser_catalogue_permissions.py` |
| A-02 | FAIT | `test_a02_module_non_modifiable`, `test_a02_structure_def_permission`, `test_a02_module_est_prefixe_du_code` | `apps/catalogue/models/permission.py`, `apps/core/registre_permissions.py` |
| A-03 | FAIT | `test_a03_aucun_verbe_generique_dans_catalogue`, `test_a03_une_seule_relation_m2m_sur_role_module_permission` | `apps/catalogue/migrations/0007_supprimer_verbes_generiques_catalogue.py`, `apps/accounts/migrations/0025_supprimer_permissions_m2m_rolemodulepermission.py`, `apps/accounts/models/role.py` |
| A-04 | FAIT | `test_a04_liste_cochee_exacte`, `test_a04_valider_seul`, `test_a04_effet_immediat_apres_modification` | `apps/core/droits.py` |
| A-06 | FAIT | `test_a06_module_desactive_supprime_permissions_effectives` | `apps/core/droits.py` |
| A-12 | FAIT | `test_a12_plus_de_plafond_modele_role` | `apps/catalogue/migrations/0006_supprimer_niveau_max_modele_role_module.py`, `apps/catalogue/models/modele_role.py`, `apps/accounts/services/roles.py`, `apps/core/droits.py` |
| A-15 | FAIT | `test_a15_ged_desactive_par_defaut_nouvelle_entreprise`, `test_a15_registre_sans_ged` | `apps/referentiels/views/module.py`, `apps/core/registre_permissions.py` |
| B-05 | FAIT | `test_b05_cocher_administration_refuse_role_personnalise`, `test_b05_cocher_administration_refuse_role_systeme`, `test_b05_cocher_permission_ordinaire_accepte`, `test_b05_marqueur_reservee_administration_coherent` | `apps/accounts/views/role.py`, `apps/catalogue/migrations/0005_cataloguepermission_reservee_administration.py`, `apps/core/registre_permissions.py` |
| B-11 | FAIT | `test_b11_jwt_sans_permission`, `test_b11_claim_role_global_ignore_pour_acces`, `test_b11_changement_de_role_immediat` | `apps/core/droits.py`, `apps/core/permissions.py` |
| E-01 | FAIT | `test_e01_codes_projets_presents` | `apps/core/registre_permissions.py` |
| E-02 | FAIT | `test_e02_table_niveaux_vers_codes`, `test_e02_aucun_code_perdu_apres_migration` | `apps/accounts/migrations/0024_traduire_niveaux_vers_permissions_catalogue.py` |
| Annexe 1 | FAIT | `test_annexe1_matrice_roles_systeme` (6 tests paramétrés), `test_annexe1_roles_perso_sans_les_six_codes` | `apps/accounts/services/roles.py`, `apps/core/droits.py` |
| G-02 | FAIT | `test_g02_profil_conserve_role_global_habilitations_permissions` | `apps/accounts/serializers/role.py`, `apps/core/droits.py` |

## Sorties brutes

### 1. Pytest suite Lot 1 (`pytest tests/acceptation/lot1/ -v -p no:cacheprovider`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.2, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Administrator\Desktop\SOUMAFE\Gestion_Chantier\05_Developpement\API-Gestion-Chantier\.venv\Scripts\python.exe
django: version: 5.2.17, settings: config.settings.test (from ini)
rootdir: C:\Users\Administrator\Desktop\SOUMAFE\Gestion_Chantier\05_Developpement\API-Gestion-Chantier
configfile: pytest.ini
plugins: Faker-40.37.0, cov-7.1.0, django-4.14.0
collecting ... collected 34 items

tests/acceptation/lot1/test_annexe1.py::test_annexe1_matrice_roles_systeme[projets.creer-roles_autorises0] PASSED [  2%]
tests/acceptation/lot1/test_annexe1.py::test_annexe1_matrice_roles_systeme[projets.changer_statut-roles_autorises1] PASSED [  5%]
tests/acceptation/lot1/test_annexe1.py::test_annexe1_matrice_roles_systeme[projets.resilier_archiver-roles_autorises2] PASSED [  8%]
tests/acceptation/lot1/test_annexe1.py::test_annexe1_matrice_roles_systeme[projets.affecter_membres-roles_autorises3] PASSED [ 11%]
tests/acceptation/lot1/test_annexe1.py::test_annexe1_matrice_roles_systeme[projets.gerer_equipes-roles_autorises4] PASSED [ 14%]
tests/acceptation/lot1/test_annexe1.py::test_annexe1_matrice_roles_systeme[projets.voir_montants-roles_autorises5] PASSED [ 17%]
tests/acceptation/lot1/test_annexe1.py::test_annexe1_roles_perso_sans_les_six_codes PASSED [ 20%]
tests/acceptation/lot1/test_catalogue.py::test_a01_catalogue_egal_registre_apres_synchronisation PASSED [ 23%]
tests/acceptation/lot1/test_catalogue.py::test_a01_synchronisation_idempotente PASSED [ 26%]
tests/acceptation/lot1/test_catalogue.py::test_a01_creation_permission_code_inconnu_refusee PASSED [ 29%]
tests/acceptation/lot1/test_catalogue.py::test_a02_module_non_modifiable PASSED [ 32%]
tests/acceptation/lot1/test_catalogue.py::test_a03_aucun_verbe_generique_dans_catalogue PASSED [ 35%]
tests/acceptation/lot1/test_catalogue.py::test_a03_une_seule_relation_m2m_sur_role_module_permission PASSED [ 38%]
tests/acceptation/lot1/test_catalogue.py::test_a15_ged_desactive_par_defaut_nouvelle_entreprise PASSED [ 41%]
tests/acceptation/lot1/test_jwt.py::test_b11_jwt_sans_permission PASSED  [ 44%]
tests/acceptation/lot1/test_jwt.py::test_b11_claim_role_global_ignore_pour_acces PASSED [ 47%]
tests/acceptation/lot1/test_jwt.py::test_b11_changement_de_role_immediat PASSED [ 50%]
tests/acceptation/lot1/test_migration_niveaux.py::test_e02_table_niveaux_vers_codes PASSED [ 52%]
tests/acceptation/lot1/test_migration_niveaux.py::test_e02_aucun_code_perdu_apres_migration PASSED [ 55%]
tests/acceptation/lot1/test_non_regression_g02.py::test_g02_profil_conserve_role_global_habilitations_permissions PASSED [ 58%]
tests/acceptation/lot1/test_permissions_effectives.py::test_a04_liste_cochee_exacte PASSED [ 61%]
tests/acceptation/lot1/test_permissions_effectives.py::test_a04_valider_seul PASSED [ 64%]
tests/acceptation/lot1/test_permissions_effectives.py::test_a04_effet_immediat_apres_modification PASSED [ 67%]
tests/acceptation/lot1/test_permissions_effectives.py::test_a06_module_desactive_supprime_permissions_effectives PASSED [ 70%]
tests/acceptation/lot1/test_a12_plus_de_plafond_modele_role PASSED [ 73%]
tests/acceptation/lot1/test_registre.py::test_a01_registre_est_source_unique PASSED [ 76%]
tests/acceptation/lot1/test_registre.py::test_a02_structure_def_permission PASSED [ 79%]
tests/acceptation/lot1/test_registre.py::test_a02_module_est_prefixe_du_code PASSED [ 82%]
tests/acceptation/lot1/test_registre.py::test_a15_registre_sans_ged PASSED [ 85%]
tests/acceptation/lot1/test_registre.py::test_b05_marqueur_reservee_administration_coherent PASSED [ 88%]
tests/acceptation/lot1/test_registre.py::test_e01_codes_projets_presents PASSED [ 91%]
tests/acceptation/lot1/test_roles_admin.py::test_b05_cocher_administration_refuse_role_personnalise PASSED [ 94%]
tests/acceptation/lot1/test_roles_admin.py::test_b05_cocher_administration_refuse_role_systeme PASSED [ 97%]
tests/acceptation/lot1/test_roles_admin.py::test_b05_cocher_permission_ordinaire_accepte PASSED [100%]

============================= 34 passed in 55.39s =============================
```

### 2. Pytest non-régression rôles et front (`pytest apps/accounts/tests/test_roles.py apps/accounts/tests/test_parametres_roles.py apps/accounts/tests/test_alignement_entreprise_frontend.py -v`)
```
============================= 19 passed in 57.32s =============================
```

### 3. Application des migrations (`python manage.py migrate_schemas`)
```
=== Starting migration
Operations to perform:
  Apply all migrations: accounts, admin, audit, auth, billing, catalogue, chantier, contenttypes, django_celery_beat, onboarding, platform_admin, projets, referentiels, sessions, tenants, tiers
Running migrations:
  No migrations to apply.
```

### 4. Commande de sortie de lot (absence de la chaîne interdite hors migrations et lot 0)
`git grep -n "niveau_max" -- "*.py" ":(exclude)*migrations*" ":(exclude)tests/acceptation/lot0*"`
-> Sortie : code 1 (0 occurrence trouvée).

### 5. Vérification absence des 4 verbes génériques dans `CataloguePermission`
-> Sortie : `Trouves: []` (0 occurrence).

## Constaté, non traité
- Les codes d'administration pour l'AD sont attribués dynamiquement dans `permissions_effectives()` conformément au point P-2 du cahier de cadrage pour éviter d'insérer une ligne artificielle dans `RoleModulePermission` sur le module `administration` (qui altérerait le décompte des modules actifs du tenant). Le statut fixe de l'AD sera définitivement cadré au Lot 4.

## Questions ouvertes liées
- Aucune question bloquante en suspens pour le Lot 1.

## Adaptations de fabriques
- Néant.
