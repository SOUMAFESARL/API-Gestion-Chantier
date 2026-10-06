# Rapport lot 6 : Statuts de projet, transitions et workflow chantier (E-08, E-09, E-10)

## 1. Règles et statuts d'implémentation

| Règle | Statut | Tests d'acceptation associés | Fichiers principaux modifiés |
|---|---|---|---|
| **E-08** | FAIT | `test_e08_vi_ayant_projets_lire_seul_refuse_403`, `test_e08_cp_autorise_sur_statuts_operationnels`, `test_e08_cp_refuse_403_sur_resilier_archiver`, `test_e08_do_autorise_sur_resiliation`, `test_e08_reouverture_projet_clos_exige_resilier_archiver`, `test_e08_ct_ayant_projets_ecrire_seul_refuse_sur_statut`, `test_e08_appel_anonyme_refuse_401`, `test_e08_acteur_non_affecte_refuse_403`, `test_e08_dg_pouvoirs_souverains_sur_tous_statuts` | `apps/projets/views/__init__.py`, `apps/projets/tests/test_statuts_crud.py`, `tests/caracterisation/test_statuts_projet.py`, `docs/api-projets-statuts.md` |
| **E-09** | FAIT | `test_e09_cp_peut_passer_projet_a_critique`, `test_e09_vi_ne_peut_pas_passer_a_critique`, `test_e09_tache_nocturne_n_ecrase_pas_statut_critique`, `test_e09_evaluation_quotidienne_projet_nominal_en_retard` | `apps/projets/services/machine_etats.py` |
| **E-10** | FAIT | `test_e10_projet_resilie_rapport_refuse_409_projet_clos`, `test_e10_projet_suspendu_rapport_autorise_201`, `test_e10_projet_resilie_ecritures_lots_refusees_409`, `test_e10_projet_resilie_equipes_refusees_409`, `test_e10_projet_resilie_affectations_refusees_409`, `test_e10_projet_resilie_reprogrammation_refusee_409`, `test_e10_priorite_garde_rbac_sur_projet_clos`, `test_e10_lecture_projet_clos_reste_autorisee_200`, `test_e10_projet_termine_nouveau_rapport_refuse_409`, `test_e10_projet_termine_reprogrammation_refusee_409` | `apps/projets/services/machine_etats.py`, `apps/chantier/serializers/rapport_journalier.py`, `apps/projets/views/lot.py`, `apps/projets/views/activite.py`, `apps/projets/views/equipe.py`, `apps/projets/views/affectation.py`, `apps/projets/views/reprogrammation.py` |

---

## 2. Décisions de conception et mise en œuvre

1. **Suppression de l'exception legacy et séparation stricte des permissions de statut (Règle E-08)** :
   - L'ancienne dérogation dans `ProjetDetailView.get_permissions` permettant à tout membre affecté avec `projets.lire` seul de muter le statut via un `PATCH {"statut": ...}` a été définitivement supprimée.
   - Les statuts opérationnels (`EN_ATTENTE`, `EN_COURS`, `EN_RETARD`, `CRITIQUE`, `SUSPENDU`, `BLOQUE`, `RECEPTIONNE`, `TERMINE`) exigent le code `projets.changer_statut` (DG, AD, DO, CP autorisés ; CT, CC, VI, BAI refusés 403).
   - Les statuts de fin de vie (`RESILIE`, `ARCHIVE`, `DESACTIVE`) et la réouverture d'un projet clos exigent le code `projets.resilier_archiver` (DG, AD, DO autorisés ; CP refusé 403).
   - Les requêtes modifiant d'autres champs que le statut continuent d'exiger `projets.ecrire`.

2. **Sanctuarisation du statut CRITIQUE (Règle E-09)** :
   - Le statut `CRITIQUE` a été inclus dans la constante `STATUTS_PROJET_MANUELS_FIXES` de `apps/projets/services/machine_etats.py`.
   - La tâche de fond d'évaluation quotidienne (`executer_evaluation_quotidienne_schema`) ignore désormais les projets marqués `CRITIQUE`, garantissant que ce diagnostic posé par l'humain n'est pas écrasé lors du calcul de nuit.

3. **Verrouillage des écritures et gestion des statuts d'achèvement (Règle E-10)** :
   - Implémentation de la fonction souveraine `verifier_statut_projet_pour_ecriture(projet, action="ECRITURE")` et de l'exception `ProjetClosError` (HTTP 409 Conflict, code `projet_clos`).
   - Fin de vie (`RESILIE`, `ARCHIVE`, `DESACTIVE`) : lecture seule absolue. Tout POST/PATCH/DELETE sur les rapports journaliers, lots, activités, équipes, affectations, reprogrammations et projet est refusé 409 `projet_clos`.
   - Achèvement (`RECEPTIONNE`, `TERMINE`) : interdiction des nouveaux rapports journaliers (`action="NOUVEAU_RAPPORT"`) et des reprogrammations de calendrier (`action="REPROGRAMMATION"`). Les écritures de structure restent autorisées.
   - Arrêts opérationnels (`SUSPENDU`, `BLOQUE`) : toutes les écritures restent permises (201/200).
   - Priorité des gardes : le garde RBAC (403) s'exécute toujours en amont de la validation d'état du projet (409).

4. **Inversion des tests existants (Liste I-08)** :
   - `tests/caracterisation/test_statuts_projet.py` : l'assertion de caractérisation qui attendait 200 sur le comportement legacy pour un simple visiteur a été inversée vers `assert res.status_code == 403`.
   - `apps/projets/tests/test_statuts_crud.py` : adaptation du test `test_member_status_only_permissions` vers 403 pour un simple membre, et de `test_creation_and_roundtrip_status` pour valider le refus 409 sur les PUT de projets clos.

---

## 3. Sorties brutes d'exécution

### 3.1. Pytest suite Lot 6 (`pytest tests/acceptation/lot6/ -v --reuse-db`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.2, pytest-9.1.1, pluggy-1.6.0
django: version: 5.2.17, settings: config.settings.test (from ini)
rootdir: C:\Users\Administrator\Desktop\SOUMAFE\Gestion_Chantier\05_Developpement\API-Gestion-Chantier
configfile: pytest.ini
plugins: Faker-40.37.0, cov-7.1.0, django-4.14.0
collected 23 items

tests/acceptation/lot6/test_e08_changements_statut.py::test_e08_vi_ayant_projets_lire_seul_refuse_403 PASSED [  4%]
tests/acceptation/lot6/test_e08_changements_statut.py::test_e08_cp_autorise_sur_statuts_operationnels PASSED [  8%]
tests/acceptation/lot6/test_e08_changements_statut.py::test_e08_cp_refuse_403_sur_resilier_archiver PASSED [ 13%]
tests/acceptation/lot6/test_e08_changements_statut.py::test_e08_do_autorise_sur_resiliation PASSED [ 17%]
tests/acceptation/lot6/test_e08_changements_statut.py::test_e08_reouverture_projet_clos_exige_resilier_archiver PASSED [ 21%]
tests/acceptation/lot6/test_e08_changements_statut.py::test_e08_ct_ayant_projets_ecrire_seul_refuse_sur_statut PASSED [ 26%]
tests/acceptation/lot6/test_e08_changements_statut.py::test_e08_appel_anonyme_refuse_401 PASSED [ 30%]
tests/acceptation/lot6/test_e08_changements_statut.py::test_e08_acteur_non_affecte_refuse_403 PASSED [ 34%]
tests/acceptation/lot6/test_e08_changements_statut.py::test_e08_dg_pouvoirs_souverains_sur_tous_statuts PASSED [ 39%]
tests/acceptation/lot6/test_e09_statut_critique.py::test_e09_cp_peut_passer_projet_a_critique PASSED [ 43%]
tests/acceptation/lot6/test_e09_statut_critique.py::test_e09_vi_ne_peut_pas_passer_a_critique PASSED [ 47%]
tests/acceptation/lot6/test_e09_statut_critique.py::test_e09_tache_nocturne_n_ecrase_pas_statut_critique PASSED [ 52%]
tests/acceptation/lot6/test_e09_statut_critique.py::test_e09_evaluation_quotidienne_projet_nominal_en_retard PASSED [ 56%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_projet_resilie_rapport_refuse_409_projet_clos PASSED [ 60%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_projet_suspendu_rapport_autorise_201 PASSED [ 65%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_projet_resilie_ecritures_lots_refusees_409 PASSED [ 69%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_projet_resilie_equipes_refusees_409 PASSED [ 73%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_projet_resilie_affectations_refusees_409 PASSED [ 78%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_projet_resilie_reprogrammation_refusee_409 PASSED [ 82%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_priorite_garde_rbac_sur_projet_clos PASSED [ 86%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_lecture_projet_clos_reste_autorisee_200 PASSED [ 91%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_projet_termine_nouveau_rapport_refuse_409 PASSED [ 95%]
tests/acceptation/lot6/test_e10_effets_statuts_ecritures.py::test_e10_projet_termine_reprogrammation_refusee_409 PASSED [100%]

============================= 23 passed in 19.84s =============================
```

### 3.2. Pytest suite complète Lots 1 à 6 (`pytest tests/acceptation/lot1 ... lot6 -v --reuse-db`)
```
======================= 241 passed in 133.33s (0:02:13) =======================
```

---

## 4. Bilan et engagements de souveraineté

- **Total tests d'acceptation Lots 1 à 6 :** **241 / 241 PASSED (100%)**.
- **Tests existants adaptés :** 13 / 13 PASSED sur `test_statuts_crud.py` et `test_statuts_projet.py`.
- **Politique Frontend :** Strict respect de la politique de protection frontend : aucune modification, aucun push sur `Application-Gestion-Chantier`.
- **Nomenclature :** Zéro occurrence du terme banni `niveau_max`.
