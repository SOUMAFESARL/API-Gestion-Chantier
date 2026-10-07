# Cadrage des tests : LOT 10, Clôture, nettoyage, invariance et certification finale

**Règles** : F-09, F-10, G-02, G-03 (vérification finale) + contrôles statiques de sortie de refonte
**Dossier des tests** : `tests/acceptation/lot10/`
**Point de départ** : lot 9 clos, tag `lot9-ok`, commit `2797393`, 66 / 66 (lot 9), 274 / 274 (lots 7 et 8), 607 tests d'acceptation (lots 0 à 9)
**Livrable final** : `docs/refonte/rapport-final.md`, puis tag souverain `refonte-droits-ok`

---

## 1. Décisions sur les questions de cadrage

| # | Décision | Traduction dans les tests |
|---|---|---|
| **Q1** F-09 | On fige les **quatre priorités de localisation** de la météo et le comportement du référentiel des villes. Le fournisseur météo externe est neutralisé et **espionné** : on vérifie la ville qui lui est transmise, pas la météo réelle. Aucun contrôle d'accès n'est jamais patché. | `test_f09_meteo_villes_invariance.py` (15 tests, tous `carac`) |
| **Q2** F-10 | Le remplacement est **validé** : `facture.py` → « Roles autorises : DG, AD. » ; `expiration.py` → « Roles DG, AD. ». Amélioration facultative : nommer aussi la permission (`administration.factures_voir`), plus durable que des noms de rôles. Le test ne l'impose pas. Contrôle : aucune chaîne littérale (docstring ou description OpenAPI) des deux fichiers ne contient `DF` ; DG et AD restent cités. | `test_f10_...` : 2 `regle`, 6 `carac` |
| **Q3** G-02 | Certification sur **cinq profils** : DG, AD, DF, CP, rôle personnalisé. Contrat : 5 champs avec types, habilitations entières de 0 à 3, permissions sans doublon, DG et AD exposent les 3 permissions d'administration, les trois autres profils n'en exposent aucune, `role_personnalise` vrai seulement pour le rôle personnalisé, 401 sans jeton. | `test_g02_compatibilite_contrat_front.py` (22 tests, tous `carac`) |
| **Q4** G-03 | Format imposé : un titre `## Lot N : titre` par lot, puis **cinq rubriques** (refus HTTP, codes d'erreur, routes, impact frontend, règles couvertes ; écrire « Aucun » si vide). Complétude : section de 8 lignes non vides minimum, **toutes les règles du lot citées** dans sa section. Les sections des lots 1 à 7 et le code `projet_clos` doivent rester présents. | `test_g03_notes_changement_api.py` (8 `carac`, 22 `regle`) |
| **Q5** Statiques | Les 7 greps de sortie, appliqués à `apps/` avec les exclusions justifiées (classe dépréciée `PermissionModule` et `RoleRequis` dans `apps/core/permissions.py` ; migrations pour `ProjetRoleModuleOverride`). Ajouts : `makemigrations --check` (aucune dérive), constantes mortes dans `config/` aussi, présence et complétude du rapport final. | `test_statiques_cloture_refonte.py` (10 `carac`, 22 `regle`) |
| **Q6** Rapport | Dix rubriques fixes (voir le gabarit `rapport-final.gabarit.md`) : synthèse, périmètre, chronologie, résultats des tests, contrôles statiques, écarts, risques, compatibilité frontend, déploiement et retour arrière, certification. Le rapport doit citer **le tag de chaque lot (`lot1-ok` à `lot10-ok`) et `refonte-droits-ok`**, et ne contenir aucun « À COMPLÉTER ». | tests `regle` du fichier statique |

---

## 2. Marqueurs et état attendu

| Marqueur | Sens | Tests | État attendu avant corrections |
|---|---|---|---|
| `carac` | Doivent déjà passer à la clôture du lot 9 | 81 | **verts** (après branchement des fabriques) |
| `regle` | Nouvelles exigences du lot 10 | 46 | **rouges**, puis verts après correction des docstrings, des notes et du rapport |

Total collecté ici : **127 tests**, plus un test de verrou par lot précédent (`test_verrou_des_lots_precedents_intact`, jusqu'à 9) quand le script existe.

| Fichier | `carac` | `regle` | Contenu |
|---|---|---|---|
| `test_00_plomberie_lot10.py` | 19 + verrous | 0 | fichiers requis, fichiers du lot, tag `lot9-ok` sur `2797393`, verrous SHA-256 des lots 1 à 9 intacts |
| `test_f09_meteo_villes_invariance.py` | 15 | 0 | siège, `ville` explicite, projet visible / non visible, affectation la plus récente, repli entreprise, champs de réponse, villes par pays, accès sans permission, module désactivé, 401 |
| `test_f10_nettoyage_docstrings_constantes.py` | 6 | 2 | 3 constantes mortes, mention `DF`, DG et AD toujours cités, paragraphe « Apprentissage » |
| `test_g02_compatibilite_contrat_front.py` | 22 | 0 | contrat du profil par profil type |
| `test_g03_notes_changement_api.py` | 8 | 22 | sections lots 1 à 7, `projet_clos`, sections 8 à 10, rubriques, règles citées |
| `test_statiques_cloture_refonte.py` | 10 | 22 | 8 greps, `voir_tous`, migrations, rapport final |

---

## 3. À faire AVANT le gel (par Durel, pas par Gemini)

1. **Brancher `fabriques_lot10.py`** : 7 fonctions (`creer_entreprise`, `creer_utilisateur`, `client_authentifie`, `client_anonyme`, `creer_projet`, `affecter`, `desactiver_module`) et le context manager `espion_fournisseur_meteo`. S'appuyer sur `tests/acceptation/lot2/test_g02_profil.py` et les fabriques du lot 9. Seul le corps des fonctions change. Si tu me colles ces deux fichiers, je les branche moi-même.
2. **Renseigner `REGLES_PAR_LOT[8]`** dans `test_g03_notes_changement_api.py` depuis la fiche du lot 8 de `plan-par-lots.md`.
3. **Vérifier trois hypothèses** en lançant les tests `carac` : (a) les rôles de siège de la météo sont bien DG, AD et DF (`ROLES_VUE_SIEGE`) ; (b) le refus d'un projet non visible est 403 ou 404, puis **figer le code exact** ; (c) les titres des lots 1 à 7 de `notes-changement-api.md` commencent par `Lot N`.
4. Lancer `pytest tests/acceptation/lot10 -m carac` : tout doit être vert. Un `carac` rouge décrit un comportement réel différent de mon hypothèse : on corrige le test, jamais le code.
5. Lancer `-m regle` : tout doit être rouge.
6. Générer le verrou : `python tests/acceptation/lot10/verifier_verrouillage.py --generer`, coller le résultat dans `EMPREINTES_ATTENDUES`, committer, poser le tag `verrouille-lot10`. (Les empreintes fournies correspondent aux fichiers livrés ; elles changent dès que les fabriques sont branchées.)

---

## 4. Travail demandé à Gemini après le gel

| Action | Tests qui passent au vert |
|---|---|
| Corriger les deux descriptions OpenAPI (Q2) | `test_f10_aucune_mention_df_dans_les_descriptions` |
| Compléter `docs/notes-changement-api.md` : sections Lot 8, 9, 10 au format de Q4 | `test_g03_*` (regle) |
| Rédiger `docs/refonte/rapport-final.md` à partir du gabarit | `test_cloture_rapport_*` |
| Ne modifier aucun fichier de `tests/acceptation/lot10/` | `verifier_verrouillage.py` |

Aucun changement de code applicatif n'est attendu : le lot 10 ne touche que des textes et de la documentation.

---

## 5. Sortie de lot

1. `pytest tests/acceptation/lot10 -q` : 100 % vert.
2. `pytest tests/acceptation -q` : suite globale verte (607 + lot 10).
3. `python tests/acceptation/lot10/verifier_verrouillage.py` : tous les fichiers conformes ; idem pour les lots 1 à 9 (couvert par la plomberie).
4. Dépôt frontend `Application-Gestion-Chantier` : arbre de travail propre, aucune écriture.
5. Commit du lot 10, tag `lot10-ok`.
6. Rapport final relu par Durel, checklist de la section 10 cochée, tag souverain `refonte-droits-ok`.

---

## 6. Points ouverts

| # | Point | Impact |
|---|---|---|
| 1 | Règles du lot 8 à renseigner (je n'ai pas sa fiche sous les yeux) | `test_g03_regles_lot8_renseignees` et `test_g03_toutes_les_regles_du_lot_sont_citees[8]` |
| 2 | Code HTTP exact du refus de projet non visible (météo) | `test_f09_projet_non_visible_est_refuse_sans_appel_externe` accepte 403 ou 404 en attendant |
| 3 | `makemigrations --check` peut révéler une dérive antérieure au lot 10 | `test_cloture_aucune_derive_de_migrations` |
| 4 | Harmonisation avec le marqueur `django_db` utilisé par les lots 2 et 9 (j'ai mis `transaction=True`, nécessaire pour les schémas) | tests F-09 et G-02 |
| 5 | Si Gemini souhaite aussi contrôler le schéma OpenAPI généré (et pas seulement le code source), on ajoute un test sur la route de schéma | option, non incluse |
