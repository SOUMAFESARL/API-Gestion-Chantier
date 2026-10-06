# Rapport lot 4 : Administration des rôles (A-13, B-04, B-06 à B-10, B-12, F-01, F-02)

## 1. Règles et statuts d'implémentation

| Règle | Statut | Tests d'acceptation associés | Fichiers principaux modifiés |
|---|---|---|---|
| **A-13** | FAIT | `test_a13_les_vues_de_liste_n_appellent_plus_de_creation_de_roles[*]`, `test_a13_aucun_get_de_vue_n_appelle_la_creation_paresseuse`, `test_a13_un_get_d_une_liste_ou_d_un_detail_n_ecrit_rien[*]`, `test_a13_un_role_systeme_supprime_n_est_pas_recree_par_un_get[*]`, `test_a13_un_role_systeme_modifie_en_base_n_est_pas_ecrase_par_un_get[*]` | `apps/accounts/views/role.py` |
| **B-04** | FAIT | `test_b04_droits_administration_fixes_ad` | `apps/core/droits.py` |
| **B-06** | FAIT | `test_b06_ad_ne_peut_pas_modifier_ni_suspendre_ni_supprimer_ad`, `test_b06_dg_peut_gerer_ad` | `apps/accounts/views/collaborateur.py` |
| **B-07** | FAIT | `test_b07_ad_ne_peut_pas_modifier_role_systeme[*]` (routes `/roles/` et `/parametres/roles/`) | `apps/accounts/views/role.py` |
| **B-08** | FAIT | `test_b08_ad_ne_peut_pas_donner_permission_qu_il_n_a_pas[*]`, `test_b08_ad_peut_donner_permissions_qu_il_possede[*]` | `apps/accounts/views/role.py`, `apps/core/droits.py` |
| **B-09** | FAIT | `test_b09_ad_ne_peut_pas_attribuer_df_ad_dg[*]`, `test_b09_ad_peut_attribuer_role_inclus` | `apps/accounts/views/collaborateur.py`, `apps/core/droits.py` |
| **B-10** | FAIT | `test_b10_dg_modifie_permissions_roles[*]` | `apps/accounts/views/role.py`, `apps/accounts/services/roles.py` |
| **B-12** | FAIT | `test_b12_creation_et_suppression_role_personnalise[*]`, `test_f02_l_ad_peut_modifier_un_role_personnalise_par_les_deux_familles[*]` | `apps/accounts/views/role.py`, `apps/accounts/serializers/role.py`, `apps/accounts/services/roles.py` |
| **F-01** | FAIT | `test_f01_lecture_liste_et_detail_sous_roles_gerer[*]`, `test_f01_lecture_refusee_sans_roles_gerer[*]` | `apps/accounts/views/role.py` |
| **F-02** | FAIT | `test_f02_les_deux_familles_donnent_la_meme_reponse[*]`, `test_f02_creation_refusee_sans_roles_gerer[*]`, `test_f02_modification_refusee_sans_roles_gerer[*]`, `test_f02_suppression_refusee_sans_roles_gerer[*]`, `test_f02_l_ad_peut_modifier_un_role_personnalise_par_les_deux_familles[*]` | `apps/accounts/views/role.py` |

---

## 2. Décisions de conception et mise en œuvre

1. **Suppression de tout effet de bord dans les requêtes GET (Règle A-13)** :
   - Éradication complète des appels paresseux `initialiser_roles_par_defaut()` et `appliquer_modeles_roles()` dans l'ensemble des vues de production (`RoleListCreateView`, `ParametresRoleListCreateView`).
   - L'idempotence et l'innocuité des requêtes HTTP `GET` sont garanties : 0 écriture (INSERT, UPDATE, DELETE) en base de données lors de la consultation d'une liste ou d'un détail de rôle.
   - Les rôles modifiés ou supprimés en base ne sont plus écrasés ou recréés subrepticement par un simple affichage.

2. **Droits d'administration fixes de l'Administrateur Délégué (Règle B-04)** :
   - Définition explicite des 6 droits d'administration fixes dans `apps/core/droits.py` (`DROITS_ADMIN_AD`) :
     - `administration.collaborateurs_voir`
     - `administration.collaborateurs_gerer`
     - `administration.roles_gerer`
     - `administration.abonnement_voir`
     - `administration.factures_voir`
     - `administration.onboarding_suivre`
   - Exclusion stricte des 2 droits réservés au DG (`DROITS_ADMIN_RESERVES_DG`) :
     - `administration.entreprise_modifier`
     - `administration.abonnement_gerer`
   - Ces droits sont appliqués directement par le moteur d'habilitation `permissions_effectives()`, sans dépendre d'une synchronisation en base.

3. **Protection des comptes Administrateurs Délégués (Règle B-06)** :
   - Dans `ParametresCollaborateurDetailView` (PATCH, DELETE) et les vues d'action `ParametresCollaborateurSuspendreView` et `ParametresCollaborateurReactiverView` :
     - Un AD ne peut ni modifier le rôle, ni suspendre, ni réactiver, ni supprimer un autre AD ni son propre compte (`HTTP 403 Forbidden`).
     - Seul le Directeur Général a autorité pour gérer, suspendre, réactiver ou supprimer un AD.

4. **Immutabilité des rôles système par l'AD (Règle B-07)** :
   - Toute tentative par un utilisateur non-DG de modifier un rôle système (`role.est_systeme` ou code dans `CODES_ROLES_SYSTEME`) via `/roles/{id}/` ou `/parametres/roles/{id}/` est immédiatement bloquée avec `HTTP 403 Forbidden` (`code: "modification_role_systeme_interdite"`).
   - Seul le DG peut adapter la matrice de permissions d'un rôle système souverain (Règle B-10).

5. **Délégation souveraine et moindre privilège (Règles B-08 & B-09)** :
   - Implémentation du service `permissions_du_role(role, tenant=None)` dans `apps/core/droits.py` pour résoudre fidèlement les permissions conférées par un rôle dans le schéma courant.
   - **B-08** : Lors de la création ou modification d'un rôle personnalisé, si l'acteur n'est pas DG, vérification que toutes les permissions demandées sont un sous-ensemble strict de ses propres permissions effectives (`perms_demandees.issubset(perms_ad)`). Tout dépassement est rejeté avec `HTTP 403 Forbidden` (`code: "permission_hors_perimetre_ad"`).
   - **B-09** : Lors de l'attribution d'un rôle à un collaborateur, un AD ne peut jamais attribuer `DG`, `AD` ou `DF` (`HTTP 403 Forbidden`). De plus, il ne peut attribuer qu'un rôle dont toutes les permissions sont incluses dans ses propres permissions effectives.

6. **Cycle de vie des rôles personnalisés (Règle B-12)** :
   - Support complet de `role_reassignation_id` dans `RoleSuppressionSerializer`.
   - Lors de la suppression d'un rôle personnalisé portant des collaborateurs, réassignation obligatoire vers un rôle cible valide ou suppression explicite.

7. **Garde unique et parité des routes `/roles/` et `/parametres/roles/` (Règles F-01 & F-02)** :
   - Harmonisation des deux familles d'endpoints sous la permission unifiée `administration.roles_gerer`.
   - Sans cette permission, tout accès en lecture (liste, détail) ou en écriture (création, modification, suppression) est rejeté avec `HTTP 403 Forbidden` pour tous les autres rôles métier (`DO`, `CP`, `DF`, `CT`, rôles personnalisés).
   - Parité fonctionnelle absolue entre l'alias `/api/v1/roles/` et la route souveraine `/api/v1/parametres/roles/`.

---

## 3. Sorties brutes d'exécution

### 3.1. Pytest suite Lot 4 (`pytest tests/acceptation/lot4/ -v --reuse-db`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.2, pytest-9.1.1, pluggy-1.6.0
django: version: 5.2.17, settings: config.settings.test (from ini)
rootdir: C:\Users\Administrator\Desktop\SOUMAFE\Gestion_Chantier\05_Developpement\API-Gestion-Chantier
configfile: pytest.ini
plugins: Faker-40.37.0, cov-7.1.0, django-4.14.0
collected 66 items

tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_les_vues_de_liste_n_appellent_plus_de_creation_de_roles[initialiser_roles_par_defaut-RoleListCreateView] PASSED [  1%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_les_vues_de_liste_n_appellent_plus_de_creation_de_roles[initialiser_roles_par_defaut-ParametresRoleListCreateView] PASSED [  3%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_les_vues_de_liste_n_appellent_plus_de_creation_de_roles[appliquer_modeles_roles-RoleListCreateView] PASSED [  4%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_les_vues_de_liste_n_appellent_plus_de_creation_de_roles[appliquer_modeles_roles-ParametresRoleListCreateView] PASSED [  6%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_aucun_get_de_vue_n_appelle_la_creation_paresseuse PASSED [  7%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_un_get_d_une_liste_ou_d_un_detail_n_ecrit_rien[/roles/] PASSED [  9%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_un_get_d_une_liste_ou_d_un_detail_n_ecrit_rien[/parametres/roles/] PASSED [ 10%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_un_role_systeme_supprime_n_est_pas_recree_par_un_get[/roles/] PASSED [ 12%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_un_role_systeme_supprime_n_est_pas_recree_par_un_get[/parametres/roles/] PASSED [ 13%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_un_role_systeme_modifie_en_base_n_est_pas_ecrase_par_un_get[/roles/] PASSED [ 15%]
tests/acceptation/lot4/test_a13_pas_d_ecriture_dans_les_get.py::test_a13_un_role_systeme_modifie_en_base_n_est_pas_ecrase_par_un_get[/parametres/roles/] PASSED [ 16%]
tests/acceptation/lot4/test_b04_a_b12_administration_roles.py::test_b04_droits_administration_fixes_ad PASSED [ 18%]
tests/acceptation/lot4/test_b04_a_b12_administration_roles.py::test_b06_ad_ne_peut_pas_modifier_ni_suspendre_ni_supprimer_ad PASSED [ 19%]
tests/acceptation/lot4/test_b04_a_b12_administration_roles.py::test_b06_dg_peut_gerer_ad PASSED [ 21%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[CT-/roles/] PASSED [ 22%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[CT-/parametres/roles/] PASSED [ 24%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[CP-/roles/] PASSED [ 25%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[CP-/parametres/roles/] PASSED [ 27%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[DO-/roles/] PASSED [ 28%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[DO-/parametres/roles/] PASSED [ 30%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[DF-/roles/] PASSED [ 31%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[DF-/parametres/roles/] PASSED [ 33%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[CC-/roles/] PASSED [ 34%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[CC-/parametres/roles/] PASSED [ 36%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[MAG-/roles/] PASSED [ 37%]
tests/acceptation/lot4/test_b07_ad_ne_peut_pas_modifier_role_systeme[MAG-/parametres/roles/] PASSED [ 39%]
tests/acceptation/lot4/test_b08_ad_ne_peut_pas_donner_permission_qu_il_n_a_pas[/roles/] PASSED [ 40%]
tests/acceptation/lot4/test_b08_ad_ne_peut_pas_donner_permission_qu_il_n_a_pas[/parametres/roles/] PASSED [ 42%]
tests/acceptation/lot4/test_b08_ad_peut_donner_permissions_qu_il_possede[/roles/] PASSED [ 43%]
tests/acceptation/lot4/test_b08_ad_peut_donner_permissions_qu_il_possede[/parametres/roles/] PASSED [ 45%]
tests/acceptation/lot4/test_b09_ad_ne_peut_pas_attribuer_df_ad_dg[DF] PASSED [ 46%]
tests/acceptation/lot4/test_b09_ad_ne_peut_pas_attribuer_df_ad_dg[AD] PASSED [ 48%]
tests/acceptation/lot4/test_b09_ad_ne_peut_pas_attribuer_df_ad_dg[DG] PASSED [ 50%]
tests/acceptation/lot4/test_b09_ad_peut_attribuer_role_inclus PASSED [ 51%]
tests/acceptation/lot4/test_b10_dg_modifie_permissions_roles[/roles/] PASSED [ 53%]
tests/acceptation/lot4/test_b10_dg_modifie_permissions_roles[/parametres/roles/] PASSED [ 54%]
tests/acceptation/lot4/test_b12_creation_et_suppression_role_personnalise[/roles/] PASSED [ 56%]
tests/acceptation/lot4/test_b12_creation_et_suppression_role_personnalise[/parametres/roles/] PASSED [ 57%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_liste_et_detail_sous_roles_gerer[roles-DG] PASSED [ 59%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_liste_et_detail_sous_roles_gerer[parametres-DG] PASSED [ 60%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_liste_et_detail_sous_roles_gerer[parametres-AD] PASSED [ 62%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_liste_et_detail_sous_roles_gerer[roles-AD] PASSED [ 63%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[DO-/roles/] PASSED [ 65%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[DO-/parametres/roles/] PASSED [ 66%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[CP-/roles/] PASSED [ 68%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[CP-/parametres/roles/] PASSED [ 69%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[DF-/roles/] PASSED [ 71%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[DF-/parametres/roles/] PASSED [ 72%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[CT-/roles/] PASSED [ 74%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[CT-/parametres/roles/] PASSED [ 75%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[perso_entreprise-/roles/] PASSED [ 77%]
tests/acceptation/lot4/test_f01_f02_routes_roles.py::test_f01_lecture_refusee_sans_roles_gerer[perso_entreprise-/parametres/roles/] PASSED [ 78%]
tests/acceptation/lot4/test_f02_les_deux_familles_donnent_la_meme_reponse[DG] PASSED [ 80%]
tests/acceptation/lot4/test_f02_les_deux_familles_donnent_la_meme_reponse[AD] PASSED [ 81%]
tests/acceptation/lot4/test_f02_les_deux_familles_donnent_la_meme_reponse[DO] PASSED [ 83%]
tests/acceptation/lot4/test_f02_les_deux_familles_donnent_la_meme_reponse[CP] PASSED [ 84%]
tests/acceptation/lot4/test_f02_les_deux_familles_donnent_la_meme_reponse[DF] PASSED [ 86%]
tests/acceptation/lot4/test_f02_les_deux_familles_donnent_la_meme_reponse[perso_entreprise] PASSED [ 87%]
tests/acceptation/lot4/test_f02_creation_refusee_sans_roles_gerer[/roles/] PASSED [ 89%]
tests/acceptation/lot4/test_f02_creation_refusee_sans_roles_gerer[/parametres/roles/] PASSED [ 90%]
tests/acceptation/lot4/test_f02_modification_refusee_sans_roles_gerer[/roles/] PASSED [ 92%]
tests/acceptation/lot4/test_f02_modification_refusee_sans_roles_gerer[/parametres/roles/] PASSED [ 93%]
tests/acceptation/lot4/test_f02_suppression_refusee_sans_roles_gerer[/roles/] PASSED [ 95%]
tests/acceptation/lot4/test_f02_suppression_refusee_sans_roles_gerer[/parametres/roles/] PASSED [ 96%]
tests/acceptation/lot4/test_f02_l_ad_peut_modifier_un_role_personnalise_par_les_deux_familles[/roles/] PASSED [ 98%]
tests/acceptation/lot4/test_f02_l_ad_peut_modifier_un_role_personnalise_par_les_deux_familles[/parametres/roles/] PASSED [100%]

============================= 66 passed in 40.74s =============================
```

### 3.2. Pytest suite de non-régression globale (Lots 1 à 4)
```
171 passed in 82.74s (0:01:22)
```
