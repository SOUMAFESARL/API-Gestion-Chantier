# Rapport lot 3 : Garde unique et filtrage par projet (D-01, D-06, D-08)

## 1. Règles et statuts d'implémentation

| Règle | Statut | Tests d'acceptation associés | Fichiers principaux modifiés |
|---|---|---|---|
| **D-01** | FAIT | `test_d01_role_entreprise_voit_tous_les_projets_futurs_compris`, `test_d01_role_projet_ne_voit_que_ses_projets`, `test_d01_role_projet_sans_affectation_ne_voit_rien`, `test_d01_affectation_desactivee_ne_donne_plus_acces`, `test_d01_changer_la_portee_change_la_liste_a_la_requete_suivante` | `apps/core/permissions.py`, `apps/projets/views/__init__.py` |
| **D-06** | FAIT | `test_d06_cp_voit_uniquement_les_reports_de_ses_projets`, `test_d06_role_entreprise_voit_tous_les_reports`, `test_d06_role_projet_sans_affectation_ne_voit_aucun_report`, `test_d06_affectation_desactivee_masque_les_reports` | `apps/core/permissions.py`, `apps/projets/views/reprogrammation.py` |
| **D-08** | FAIT | `test_d08_lecture_code_et_portee_ou_affectation[*]`, `test_d08_ecriture_code_et_portee_ou_affectation[*]`, `test_d08_la_portee_du_role_est_lue_a_chaque_requete_lecture[*]`, `test_d08_la_portee_du_role_est_lue_a_chaque_requete_ecriture[*]`, `test_d08_plus_aucune_vue_n_utilise_permissionmodule`, `test_d08_plus_aucune_vue_n_utilise_membreduprojet`, `test_d08_roleRequis_limite_aux_apps_des_lots_suivants` | `apps/core/permissions.py`, `apps/projets/views/*.py`, `apps/chantier/permissions.py`, `apps/tiers/views/__init__.py`, `apps/accounts/services/roles.py` |

---

## 2. Décisions de conception et mise en œuvre

1. **Garde unique `GardePermissionProjet` (alias `GardeProjet`)** :
   - Fusionne en un point unique le contrôle du code de permission RBAC (`projets.lire`, `projets.ecrire`, etc.) et le contrôle de périmètre (`ENTREPRISE` vs affectation active au projet).
   - Une action est autorisée SSI :
     1. Le code de permission requis est détenu par l'utilisateur (`a_permission(user, perm)`).
     2. ET (`user.is_superuser` OU `est_dg(user)` OU `obtenir_portee_role(user) == "ENTREPRISE"` OU l'utilisateur possède une affectation active sur le projet ciblé).
   - Résolution multi-niveaux du projet ciblé : kwargs URL (`pk`, `projet_id`, `projet_pk`) et parcours récursif des objets liés (`Projet`, `Lot`, `Activite`, `AffectationProjet`).

2. **Filtrage par portée (`filtrer_queryset_par_affectations`)** :
   - Pour un collaborateur portant un rôle de portée `ENTREPRISE`, aucun filtre n'est appliqué : visibilité totale et consolidée sur tous les chantiers (actuels et futurs).
   - Pour un rôle de portée `PROJET`, restriction stricte aux chantiers activement affectés (`AffectationProjet.objects.filter(utilisateur=user, est_actif=True)` ou gestion directe comme chef de projet / conducteur de travaux).
   - Un utilisateur sans affectation active reçoit un QuerySet vide.
   - La désactivation d'une affectation masque instantanément le projet à la requête suivante sans réauthentification.

3. **Préservation de la portée lors des synchronisations dynamiques** :
   - `appliquer_modeles_roles` préserve désormais la portée (`role.portee`) des rôles déjà existants dans le schéma tenant au lieu d'écraser la configuration personnalisée par les valeurs du gabarit souverain.
   - Permet à un changement de portée (`PROJET` -> `ENTREPRISE`) d'avoir un effet immédiat et persistant à chaque requête (conformité règles B-11 et D-01).

4. **Éradication des gardes obsolètes (`PermissionModule` et `MembreDuProjet`)** :
   - Remplacement intégral de `PermissionModule` et `MembreDuProjet` par `GardePermissionProjet` et `APermission`.
   - 0 occurrence de `PermissionModule` et 0 occurrence de `MembreDuProjet` dans le code de production de l'ensemble de l'API.
   - Les occurrences de `RoleRequis` ont été circonscrites exclusivement aux modules prévus pour les lots ultérieurs (`notifications`, `audit`, `platform_admin`, `ged`, `export_import`).

---

## 3. Sorties brutes d'exécution

### 3.1. Pytest suite Lot 3 (`pytest tests/acceptation/lot3/test_d01_d06_filtrage.py tests/acceptation/lot3/test_d08_garde_unique.py -v`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.2, pytest-9.1.1, pluggy-1.6.0
django: version: 5.2.17, settings: config.settings.test (from ini)
rootdir: C:\Users\Administrator\Desktop\SOUMAFE\Gestion_Chantier\05_Developpement\API-Gestion-Chantier
configfile: pytest.ini
plugins: Faker-40.37.0, cov-7.1.0, django-4.14.0
collected 28 items

tests/acceptation/lot3/test_d01_d06_filtrage.py::test_d01_role_entreprise_voit_tous_les_projets_futurs_compris PASSED [  3%]
tests/acceptation/lot3/test_d01_d06_filtrage.py::test_d01_role_projet_ne_voit_que_ses_projets PASSED [  7%]
tests/acceptation/lot3/test_d01_d06_filtrage.py::test_d01_role_projet_sans_affectation_ne_voit_rien PASSED [ 10%]
tests/acceptation/lot3/test_d01_d06_filtrage.py::test_d01_affectation_desactivee_ne_donne_plus_acces PASSED [ 14%]
tests/acceptation/lot3/test_d01_d06_filtrage.py::test_d01_changer_la_portee_change_la_liste_a_la_requete_suivante PASSED [ 17%]
tests/acceptation/lot3/test_d06_cp_voit_uniquement_les_reports_de_ses_projets PASSED [ 21%]
tests/acceptation/lot3/test_d06_role_entreprise_voit_tous_les_reports PASSED [ 25%]
tests/acceptation/lot3/test_d06_role_projet_sans_affectation_ne_voit_aucun_report PASSED [ 28%]
tests/acceptation/lot3/test_d06_affectation_desactivee_masque_les_reports PASSED [ 32%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_lecture_code_et_portee_ou_affectation[dg_non_affecte] PASSED [ 35%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_lecture_code_et_portee_ou_affectation[do_non_affecte] PASSED [ 39%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_lecture_code_et_portee_ou_affectation[cp_affecte] PASSED [ 42%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_lecture_code_et_portee_ou_affectation[cp_non_affecte] PASSED [ 46%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_lecture_code_et_portee_ou_affectation[cp_affectation_inactive] PASSED [ 50%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_lecture_code_et_portee_ou_affectation[role_entreprise_sans_code] PASSED [ 53%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_lecture_code_et_portee_ou_affectation[role_projet_sans_code_affecte] PASSED [ 57%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_ecriture_code_et_portee_ou_affectation[dg_non_affecte] PASSED [ 60%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_ecriture_code_et_portee_ou_affectation[do_non_affecte] PASSED [ 64%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_ecriture_code_et_portee_ou_affectation[cp_affecte] PASSED [ 67%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_ecriture_code_et_portee_ou_affectation[cp_non_affecte] PASSED [ 71%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_ecriture_code_et_portee_ou_affectation[cp_affectation_inactive] PASSED [ 75%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_ecriture_code_et_portee_ou_affectation[role_entreprise_sans_code] PASSED [ 78%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_ecriture_code_et_portee_ou_affectation[role_projet_sans_code_affecte] PASSED [ 82%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_la_portee_du_role_est_lue_a_chaque_requete_lecture[cp_devenu_entreprise] PASSED [ 85%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_la_portee_du_role_est_lue_a_chaque_requete_ecriture[cp_devenu_entreprise] PASSED [ 89%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_plus_aucune_vue_n_utilise_permissionmodule PASSED [ 92%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_plus_aucune_vue_n_utilise_membreduprojet PASSED [ 96%]
tests/acceptation/lot3/test_d08_garde_unique.py::test_d08_roleRequis_limite_aux_apps_des_lots_suivants PASSED [100%]

============================= 28 passed in 17.38s =============================
```

### 3.2. Pytest suite Lots 1 et 2 (non-régression : `pytest tests/acceptation/lot1/ tests/acceptation/lot2/ -v`)
```
============================= 77 passed in 31.13s =============================
```

### 3.3. Contrôle d'absence du terme interdit `niveau_max`
```
$ git grep -n "niveau_max" -- "*.py" ":(exclude)*migrations*" ":(exclude)tests/acceptation/lot0*"
(Aucun résultat, code retour 1)
```
