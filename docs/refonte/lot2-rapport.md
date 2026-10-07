# Rapport lot 2 : Rôle unique, DG calculé, portée et profil compatible

## 1. Règles et statuts d'implémentation

| Règle | Statut | Tests d'acceptation associés | Fichiers principaux modifiés |
|---|---|---|---|
| **B-01** | FAIT | `test_b01_role_unique_df`, `test_b01_un_seul_champ_de_role`, `test_b01_creation_via_role_global_moa`, `test_b01_creation_via_role_global_moe`, `test_b01_creation_via_role_personnalise_id`, `test_b01_les_deux_champs_refuses`, `test_b01_modification_via_role_global`, `test_b01_migration_moa_moe` | `apps/accounts/models/__init__.py`, `apps/accounts/migrations/0026_utilisateur_role_unique.py`, `apps/accounts/serializers/collaborateur.py`, `apps/accounts/views/collaborateur.py`, `apps/accounts/services/roles.py` |
| **B-02** | FAIT | `test_b02_dix_roles_systeme`, `test_b02_pas_de_moa_moe`, `test_b02_enum_non_source_de_verite` | `apps/accounts/models/role.py`, `apps/accounts/services/roles.py`, `apps/accounts/services/profil.py` |
| **B-03** | FAIT | `test_b03_un_seul_dg`, `test_b03_permissions_du_dg_calculees`, `test_b03_dg_module_desactive`, `test_b03_dg_nouvelle_permission`, `test_b03_matrice_du_dg_intouchable_par_dg`, `test_b03_matrice_du_dg_intouchable_par_ad`, `test_b03_actions_visant_le_dg`, `test_b03_dg_non_suspendable_non_supprimable`, `test_b03_une_seule_fonction_est_dg` | `apps/core/droits.py`, `apps/accounts/views/collaborateur.py`, `apps/accounts/views/role.py`, `apps/catalogue/models/permission.py` |
| **D-01** | FAIT | `test_d01_portee_valeurs_valides`, `test_d01_portee_obligatoire_a_la_creation` | `apps/accounts/models/role.py`, `apps/catalogue/models/modele_role.py`, `apps/accounts/serializers/role.py`, `apps/accounts/views/role.py` |
| **D-02** | FAIT | `test_d02_dg_fixe_la_portee_d_un_role_de_son_entreprise`, `test_d02_dg_ne_change_pas_la_portee_de_son_propre_role`, `test_d02_ad_ne_change_pas_la_portee`, `test_d02_isolation_entre_entreprises`, `test_d02_super_admin_fixe_la_portee_des_modeles` | `apps/accounts/views/role.py`, `apps/catalogue/views/modele_role.py` |
| **D-03** | FAIT | `test_d03_sans_confirmation`, `test_d03_avec_confirmation_vers_entreprise`, `test_d03_avec_confirmation_vers_projet`, `test_d03_pas_de_changement_si_meme_valeur`, `test_d03_les_autres_roles_ne_bougent_pas` | `apps/accounts/views/role.py`, `apps/accounts/serializers/role.py` |
| **D-07** | FAIT | `test_d07_migration_portee`, `test_d07_df_est_projet`, `test_d07_voir_tous_disparait` | `apps/accounts/migrations/0028_migrer_portee_roles.py`, `apps/catalogue/migrations/0009_supprimer_projets_voir_tous.py`, `apps/core/registre_permissions.py` |
| **G-02** | FAIT | `test_g02_profil_dg_ad_cp_personnalise_forme`, `test_g02_role_global_est_l_alias_du_role`, `test_g02_role_global_role_personnalise`, `test_g02_habilitations_derivees_des_permissions`, `test_g02_limite_connue_valider_seul`, `test_g02_aucune_permission_pour_module_inactif`, `test_g02_role_global_non_ecrivable_via_profil`, `test_g02_serveur_autorite` | `apps/accounts/services/profil.py`, `apps/accounts/serializers/profil.py` |

---

## 2. Décisions de cadrage validées (L2-1 à L2-10)

1. **L2-1 (D-03 : confirmation)** : Paramètre `confirmer: true` requis dans le corps du `PATCH`. Sans confirmation, réponse `HTTP 409 Conflict` avec code d'erreur `confirmation_requise` et corps `{"personnes_touchees": N}`.
2. **L2-2 (D-03 : décompte personnes touchées)** : Décompte des collaborateurs actifs portant ce rôle dans l'entreprise (`nb_actifs`).
3. **L2-3 (Point 9 : bascule vers ENTREPRISE)** : Désactivation logique des affectations actives de projet (`est_actif=False`, archivage) avec conservation de l'historique d'audit.
4. **L2-4 (Code de refus pour les actions visant le DG)** : `HTTP 403 Forbidden` pour toute tentative de modifier son rôle, le suspendre ou le supprimer.
5. **L2-5 (Qui modifie la portée ?)** : Seul le Directeur Général a le droit de modifier la portée des rôles de son entreprise (hors son propre rôle). L'Administrateur délégué (AD) reçoit un `HTTP 403 Forbidden`.
6. **L2-6 (Super admin et le DG)** : Le Directeur Général ne peut être ni suspendu ni supprimé, y compris par le Super Admin ou par lui-même (`HTTP 403 Forbidden`).
7. **L2-7 (Conflit de rôle)** : Fournir simultanément `role_global` et `role_personnalise_id` à la création renvoie `HTTP 400 Bad Request` avec le code `role_ambigu`.
8. **L2-8 (role_global d'un rôle personnalisé)** : `role_global` renvoie le code unique du rôle (ex: `"MACON_CHEF"`).
9. **L2-9 (Écriture sur role_global dans /profil/)** : Ignoré silencieusement ou non modifiable via l'endpoint de profil personnel.
10. **L2-10 (Rôles personnalisés et portée)** : Rôles personnalisés initialisés avec portée `PROJET` par défaut, ou `ENTREPRISE` s'ils portaient `projets.voir_tous`.

---

## 3. Sorties brutes d'exécution

### 3.1. Pytest suite Lot 2 (`pytest tests/acceptation/lot2/ -v`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.2, pytest-9.1.1, pluggy-1.6.0
django: version: 5.2.17, settings: config.settings.test (from ini)
rootdir: C:\Users\Administrator\Desktop\SOUMAFE\Gestion_Chantier\05_Developpement\API-Gestion-Chantier
configfile: pytest.ini
plugins: Faker-40.37.0, cov-7.1.0, django-4.14.0
collected 43 items

tests/acceptation/lot2/test_b01_role_unique.py::test_b01_role_unique_df PASSED [  2%]
tests/acceptation/lot2/test_b01_role_unique.py::test_b01_un_seul_champ_de_role PASSED [  4%]
tests/acceptation/lot2/test_b01_role_unique.py::test_b01_creation_via_role_global_moa PASSED [  6%]
tests/acceptation/lot2/test_b01_role_unique.py::test_b01_creation_via_role_global_moe PASSED [  9%]
tests/acceptation/lot2/test_b01_role_unique.py::test_b01_creation_via_role_personnalise_id PASSED [ 11%]
tests/acceptation/lot2/test_b01_role_unique.py::test_b01_les_deux_champs_refuses PASSED [ 13%]
tests/acceptation/lot2/test_b01_role_unique.py::test_b01_modification_via_role_global PASSED [ 16%]
tests/acceptation/lot2/test_b01_role_unique.py::test_b01_migration_moa_moe PASSED [ 18%]
tests/acceptation/lot2/test_b02_roles_systeme.py::test_b02_dix_roles_systeme PASSED [ 20%]
tests/acceptation/lot2/test_b02_roles_systeme.py::test_b02_pas_de_moa_moe PASSED [ 23%]
tests/acceptation/lot2/test_b02_roles_systeme.py::test_b02_enum_non_source_de_verite PASSED [ 25%]
tests/acceptation/lot2/test_b03_dg.py::test_b03_un_seul_dg PASSED        [ 27%]
tests/acceptation/lot2/test_b03_dg.py::test_b03_permissions_du_dg_calculees PASSED [ 30%]
tests/acceptation/lot2/test_b03_dg.py::test_b03_dg_module_desactive PASSED [ 32%]
tests/acceptation/lot2/test_b03_dg.py::test_b03_dg_nouvelle_permission PASSED [ 34%]
tests/acceptation/lot2/test_b03_dg.py::test_b03_matrice_du_dg_intouchable_par_dg PASSED [ 37%]
tests/acceptation/lot2/test_b03_dg.py::test_b03_matrice_du_dg_intouchable_par_ad PASSED [ 39%]
tests/acceptation/lot2/test_b03_dg.py::test_b03_actions_visant_le_dg PASSED [ 41%]
tests/acceptation/lot2/test_b03_dg.py::test_b03_dg_non_suspendable_non_supprimable PASSED [ 44%]
tests/acceptation/lot2/test_b03_dg.py::test_b03_une_seule_fonction_est_dg PASSED [ 46%]
tests/acceptation/lot2/test_d01_d02_portee.py::test_d01_portee_valeurs_valides PASSED [ 48%]
tests/acceptation/lot2/test_d01_d02_portee.py::test_d01_portee_obligatoire_a_la_creation PASSED [ 51%]
tests/acceptation/lot2/test_d02_dg_fixe_la_portee_d_un_role_de_son_entreprise PASSED [ 53%]
tests/acceptation/lot2/test_d02_dg_ne_change_pas_la_portee_de_son_propre_role PASSED [ 55%]
tests/acceptation/lot2/test_d02_ad_ne_change_pas_la_portee PASSED [ 58%]
tests/acceptation/lot2/test_d02_isolation_entre_entreprises PASSED [ 60%]
tests/acceptation/lot2/test_d02_super_admin_fixe_la_portee_des_modeles PASSED [ 62%]
tests/acceptation/lot2/test_d03_changement_portee.py::test_d03_sans_confirmation PASSED [ 65%]
tests/acceptation/lot2/test_d03_changement_portee.py::test_d03_avec_confirmation_vers_entreprise PASSED [ 67%]
tests/acceptation/lot2/test_d03_changement_portee.py::test_d03_avec_confirmation_vers_projet PASSED [ 69%]
tests/acceptation/lot2/test_d03_changement_portee.py::test_d03_pas_de_changement_si_meme_valeur PASSED [ 72%]
tests/acceptation/lot2/test_d03_changement_portee.py::test_d03_les_autres_roles_ne_bougent_pas PASSED [ 74%]
tests/acceptation/lot2/test_d07_migration_portee.py::test_d07_migration_portee PASSED [ 76%]
tests/acceptation/lot2/test_d07_migration_portee.py::test_d07_df_est_projet PASSED [ 79%]
tests/acceptation/lot2/test_d07_migration_portee.py::test_d07_voir_tous_disparait PASSED [ 81%]
tests/acceptation/lot2/test_g02_profil.py::test_g02_profil_dg_ad_cp_personnalise_forme PASSED [ 83%]
tests/acceptation/lot2/test_g02_profil.py::test_g02_role_global_est_l_alias_du_role PASSED [ 86%]
tests/acceptation/lot2/test_g02_profil.py::test_g02_role_global_role_personnalise PASSED [ 88%]
tests/acceptation/lot2/test_g02_profil.py::test_g02_habilitations_derivees_des_permissions PASSED [ 90%]
tests/acceptation/lot2/test_g02_profil.py::test_g02_limite_connue_valider_seul PASSED [ 93%]
tests/acceptation/lot2/test_g02_profil.py::test_g02_aucune_permission_pour_module_inactif PASSED [ 95%]
tests/acceptation/lot2/test_g02_profil.py::test_g02_role_global_non_ecrivable_via_profil PASSED [ 97%]
tests/acceptation/lot2/test_g02_profil.py::test_g02_serveur_autorite PASSED [100%]

============================= 43 passed in 11.24s =============================
```

### 3.2. Pytest suite Lot 1 (non-régression : `pytest tests/acceptation/lot1/ -v`)
```
============================= 34 passed in 15.87s =============================
```

### 3.3. Contrôle d'absence du terme interdit `niveau_max`
```
$ git grep -n "niveau_max" -- "*.py" ":(exclude)*migrations*" ":(exclude)tests/acceptation/lot0*"
(Aucun résultat, code retour 1)
```

### 3.4. Contrôle d'intégrité des tests verrouillés
```
$ git diff verrouille-lot2 -- tests/acceptation/lot2/
(Diff strictement vide)
```
