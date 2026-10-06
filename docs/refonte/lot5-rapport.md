# Rapport lot 5 : Projets, écritures, affectation, équipes (C-05, E-03, E-04, E-05, E-06, E-07, E-13)

## 1. Règles et statuts d'implémentation

| Règle | Statut | Tests d'acceptation associés | Fichiers principaux modifiés |
|---|---|---|---|
| **C-05 (puces 2 & 3)** | FAIT | `test_c05_affectations_vi_pii_masquees`, `test_c05_affectations_acteurs_autorises_voient_pii`, `test_c05_affectations_do_ne_voit_pas_pii`, `test_c05_affectations_non_affecte_refuse`, `test_c05_route_collaborateurs_affectables_acces_et_champs`, `test_c05_collaborateurs_affectables_filtrage_candidats`, `test_c05_collaborateurs_affectables_refus_pour_non_habilites` | `apps/projets/views/affectation.py`, `apps/projets/serializers/affectation.py` |
| **E-03 & E-07** | FAIT | `test_e03_post_equipe_autorisations_et_refus`, `test_e03_delete_equipe_autorisations_et_refus`, `test_e03_affectation_equipe_activite_autorisations_et_refus`, `test_e03_ecritures_lots_sous_projets_ecrire`, `test_e03_arret_chantier_ecritures_exigent_projets_ecrire`, `test_e03_lectures_equipes_lots_arrets_autorisees_affectes_refus_non_affectes`, `test_e03_non_affecte_toutes_ecritures_refusees`, `test_e07_membre_equipe_non_affecte_renvoie_400` | `apps/projets/views/equipe.py`, `apps/projets/serializers/equipe.py`, `apps/projets/views/arret_chantier.py`, `apps/core/permissions.py` |
| **E-04** | FAIT | `test_e04_creation_par_portee_entreprise_aucune_affectation`, `test_e04_cp_sans_droit_creer_refuse`, `test_e04_ca_cp_avec_droit_creer_auto_affectation`, `test_e04_cp_cree_deux_projets_deux_affectations_distinctes` | `apps/projets/views/__init__.py` |
| **E-05** | FAIT | `test_e05_acteur_dg_ad_non_affectes_autorises`, `test_e05_acteur_cp_affecte_autorise`, `test_e05_acteur_cp_non_affecte_refuse`, `test_e05_acteur_cp_affectation_desactivee_refuse`, `test_e05_acteur_do_refuse`, `test_e05_acteur_ct_affecte_refuse`, `test_e05_acteur_ct_affecte_avec_etiquette_cp_refuse`, `test_e05_acteur_cp_affecte_autre_etiquette_autorise`, `test_e05_candidat_portee_entreprise_refuse`, `test_e05_candidat_inactif_refuse`, `test_e05_candidat_inconnu_refuse`, `test_e05_candidat_cc_actif_accepte`, `test_e05_patch_delete_acteurs_autorises_et_refus` | `apps/projets/views/affectation.py`, `apps/projets/serializers/affectation.py`, `apps/projets/services/affectations.py` |
| **E-06** | FAIT | `test_e06_route_permissions_roles_supprimee`, `test_e06_statique_override_absent`, `test_e06_modele_affectation_sans_champ_role`, `test_e06_cc_avec_role_projet_ct_garde_droits_cc`, `test_e06_ct_avec_role_projet_cp_ne_gagne_pas_affecter_membres`, `test_e06_synchronisation_chef_projet_et_conducteur`, `test_e06_roles_projet_moa_et_moe_acceptes` | `apps/projets/models/projet.py`, `apps/projets/migrations/0027_supprimer_override_et_role_affectation.py`, suppression de `apps/projets/models/override.py`, `apps/projets/views/override.py`, `apps/projets/services/overrides.py` |
| **E-13** | FAIT | `test_e13_route_contexte_creation_supprimee`, `test_e13_statique_contexte_creation_absent` | `apps/projets/urls.py`, suppression de `apps/projets/views/contexte_creation.py`, `apps/projets/serializers/contexte_creation.py`, `apps/projets/tests/test_contexte_creation.py` |

---

## 2. Décisions de conception et mise en œuvre

1. **Suppression définitive de la vue `contexte-creation` (Règle E-13)** :
   - Suppression du fichier de vue `apps/projets/views/contexte_creation.py`, du serializer `apps/projets/serializers/contexte_creation.py` et du test associé.
   - Suppression de la route `projets/contexte-creation/` dans `apps/projets/urls.py`. La route renvoie désormais 404.

2. **Éradication des surcharges locales et suppression du champ `AffectationProjet.role` (Règle E-06)** :
   - Suppression du modèle `ProjetRoleModuleOverride`, de son service `apps/projets/services/overrides.py`, de sa vue `apps/projets/views/override.py` et de la route `projets/{id}/permissions-roles/`.
   - Suppression du champ `role` sur le modèle `AffectationProjet` via la migration Django dédiée `0027_supprimer_override_et_role_affectation.py`.
   - L'affectation ne porte plus de rôle d'entreprise : les habilitations d'un utilisateur découlent exclusivement de son rôle global/entreprise (`utilisateur.role`), tandis que `AffectationProjet.role_projet` ne sert que d'étiquette métier d'affichage (ex: `MOA`, `MOE`) ou de synchronisation des champs informatifs du projet (`chef_projet`, `conducteur_travaux`).

3. **Garde unique et étanchéité de l'affectation (Règle E-05)** :
   - Point d'entrée unique sous le code d'habilitation `projets.affecter_membres` pour `POST /projets/{id}/affectations/`, `PATCH` et `DELETE` sur `/projets/{id}/affectations/{pk}/`.
   - Acteurs autorisés : DG et AD (non affectés), CP affecté activement.
   - Acteurs refusés (403) : CT affecté (même avec étiquette CP), DO, VI, BAI, CC, et tout utilisateur non affecté ou dont l'affectation est inactive.
   - Validation stricte des candidats (400 `candidat_invalide`) : refus des utilisateurs à portée ENTREPRISE (DG, AD, DO), des utilisateurs inactifs/suspendus, et des identifiants inexistants.

4. **Masquage PII et nouvelle route de liste réduite (Règle C-05, puces 2 & 3)** :
   - Implémentation de la route `GET /api/v1/projets/{projet_id}/collaborateurs-affectables/` (décision L5-1) : accessible uniquement aux utilisateurs disposant de `projets.affecter_membres` et ayant accès au projet. Ne retourne que `id`, `nom`, `role` pour les collaborateurs actifs à portée `PROJET` (exclusion de DG, AD, DO).
   - Masquage dynamique des données personnelles (PII) dans `GET /projets/{projet_id}/affectations/` : omission stricte des clés contenant `mail` ou `phone` / `telephone` pour les rôles non habilités (VI, CC, DO). Présence des PII réservée aux acteurs possédant `projets.affecter_membres` ou `projets.gerer_equipes` (DG, AD, CP, CT).

5. **Création de projet et auto-affectation souveraine (Règle E-04)** :
   - Lorsque le créateur a un rôle à portée `ENTREPRISE` (DG, AD), le projet est créé sans aucune `AffectationProjet` (vision consolidée naturelle).
   - Lorsque le créateur a un rôle à portée `PROJET` (ex: CP auquel le DG a coché `projets.creer`), une `AffectationProjet` active est automatiquement générée avec `role_projet=""` sans écraser `projet.chef_projet`.

6. **Écritures des équipes et arrêts de chantier (Règles E-03 & E-07)** :
   - Création, modification et suppression d'équipes de chantier protégées par le garde `projets.gerer_equipes`.
   - Écritures sur les arrêts de chantier basculées sous `projets.ecrire` (décision L5-2).
   - Validation E-07 : rejet (400) lors de l'ajout d'un membre non affecté activement au projet dans une équipe.

---

## 3. Sorties brutes d'exécution

### 3.1. Pytest suite Lot 5 (`pytest tests/acceptation/lot5/ -v --reuse-db`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.2, pytest-9.1.1, pluggy-1.6.0
django: version: 5.2.17, settings: config.settings.test (from ini)
rootdir: C:\Users\Administrator\Desktop\SOUMAFE\Gestion_Chantier\05_Developpement\API-Gestion-Chantier
configfile: pytest.ini
plugins: Faker-40.37.0, cov-7.1.0, django-4.14.0
collected 41 items

tests/acceptation/lot5/test_c05_puces_2_et_3.py::test_c05_affectations_vi_pii_masquees PASSED [  2%]
tests/acceptation/lot5/test_c05_puces_2_et_3.py::test_c05_affectations_acteurs_autorises_voient_pii PASSED [  4%]
tests/acceptation/lot5/test_c05_puces_2_et_3.py::test_c05_affectations_do_ne_voit_pas_pii PASSED [  7%]
tests/acceptation/lot5/test_c05_puces_2_et_3.py::test_c05_affectations_non_affecte_refuse PASSED [  9%]
tests/acceptation/lot5/test_c05_puces_2_et_3.py::test_c05_route_collaborateurs_affectables_acces_et_champs PASSED [ 12%]
tests/acceptation/lot5/test_c05_puces_2_et_3.py::test_c05_collaborateurs_affectables_filtrage_candidats PASSED [ 14%]
tests/acceptation/lot5/test_c05_puces_2_et_3.py::test_c05_collaborateurs_affectables_refus_pour_non_habilites PASSED [ 17%]
tests/acceptation/lot5/test_e03_e07_ecritures_et_equipes.py::test_e03_post_equipe_autorisations_et_refus PASSED [ 19%]
tests/acceptation/lot5/test_e03_e07_ecritures_et_equipes.py::test_e03_delete_equipe_autorisations_et_refus PASSED [ 21%]
tests/acceptation/lot5/test_e03_e07_ecritures_et_equipes.py::test_e03_affectation_equipe_activite_autorisations_et_refus PASSED [ 24%]
tests/acceptation/lot5/test_e03_e07_ecritures_et_equipes.py::test_e03_ecritures_lots_sous_projets_ecrire PASSED [ 26%]
tests/acceptation/lot5/test_e03_e07_ecritures_et_equipes.py::test_e03_arret_chantier_ecritures_exigent_projets_ecrire PASSED [ 29%]
tests/acceptation/lot5/test_e03_e07_ecritures_et_equipes.py::test_e03_lectures_equipes_lots_arrets_autorisees_affectes_refus_non_affectes PASSED [ 31%]
tests/acceptation/lot5/test_e03_e07_ecritures_et_equipes.py::test_e03_non_affecte_toutes_ecritures_refusees PASSED [ 34%]
tests/acceptation/lot5/test_e03_e07_ecritures_et_equipes.py::test_e07_membre_equipe_non_affecte_renvoie_400 PASSED [ 36%]
tests/acceptation/lot5/test_e04_creation_et_auto_affectation.py::test_e04_creation_par_portee_entreprise_aucune_affectation PASSED [ 39%]
tests/acceptation/lot5/test_e04_creation_et_auto_affectation.py::test_e04_cp_sans_droit_creer_refuse PASSED [ 41%]
tests/acceptation/lot5/test_e04_creation_et_auto_affectation.py::test_e04_ca_cp_avec_droit_creer_auto_affectation PASSED [ 43%]
tests/acceptation/lot5/test_e04_creation_et_auto_affectation.py::test_e04_cp_cree_deux_projets_deux_affectations_distinctes PASSED [ 46%]
tests/acceptation/lot5/test_e05_affectation.py::test_e05_acteur_dg_ad_non_affectes_autorises PASSED [ 48%]
tests/acceptation/lot5/test_e05_affectation.py::test_e05_acteur_cp_affecte_autorise PASSED [ 51%]
tests/acceptation/lot5/test_e05_affectation.py::test_e05_acteur_cp_non_affecte_refuse PASSED [ 53%]
tests/acceptation/lot5/test_e05_affectation.py::test_e05_acteur_cp_affectation_desactivee_refuse PASSED [ 56%]
tests/acceptation/lot5/test_e05_affectation.py::test_e05_acteur_do_refuse PASSED [ 58%]
tests/acceptation/lot5/test_e05_affectation.py::test_e05_acteur_ct_affecte_refuse PASSED [ 60%]
tests/acceptation/lot5/test_e05_affectation.py::test_e05_acteur_ct_affecte_avec_etiquette_cp_refuse PASSED [ 63%]
tests/acceptation/lot5/test_e05_affectation.py::test_e05_acteur_cp_affecte_autre_etiquette_autorise PASSED [ 65%]
tests/acceptation/lot5/test_e05_candidat_portee_entreprise_refuse PASSED [ 68%]
tests/acceptation/lot5/test_e05_candidat_inactif_refuse PASSED [ 70%]
tests/acceptation/lot5/test_e05_candidat_inconnu_refuse PASSED [ 73%]
tests/acceptation/lot5/test_e05_candidat_cc_actif_accepte PASSED [ 75%]
tests/acceptation/lot5/test_e05_patch_delete_acteurs_autorises_et_refus PASSED [ 78%]
tests/acceptation/lot5/test_e06_override_et_role_affectation.py::test_e06_route_permissions_roles_supprimee PASSED [ 80%]
tests/acceptation/lot5/test_e06_override_et_role_affectation.py::test_e06_statique_override_absent PASSED [ 82%]
tests/acceptation/lot5/test_e06_modele_affectation_sans_champ_role PASSED [ 85%]
tests/acceptation/lot5/test_e06_cc_avec_role_projet_ct_garde_droits_cc PASSED [ 87%]
tests/acceptation/lot5/test_e06_ct_avec_role_projet_cp_ne_gagne_pas_affecter_membres PASSED [ 90%]
tests/acceptation/lot5/test_e06_synchronisation_chef_projet_et_conducteur PASSED [ 92%]
tests/acceptation/lot5/test_e06_roles_projet_moa_et_moe_acceptes PASSED [ 95%]
tests/acceptation/lot5/test_e13_vue_supprimee.py::test_e13_route_contexte_creation_supprimee PASSED [ 97%]
tests/acceptation/lot5/test_e13_vue_supprimee.py::test_e13_statique_contexte_creation_absent PASSED [100%]

============================= 41 passed in 33.70s =============================
```

### 3.2. Pytest suite complète de non-régression Lots 1 à 5 (`pytest tests/acceptation/lot1 ... lot5 -v --reuse-db`)
```
======================= 218 passed in 110.92s (0:01:50) =======================
```
Total des tests d'acceptation validés : **218 / 218 au vert (100% de réussite)**.
