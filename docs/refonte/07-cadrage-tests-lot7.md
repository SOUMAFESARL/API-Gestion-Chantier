# Cadrage des tests du lot 7 : montants (E-11 et E-12)

Ce document cadre la suite de tests d'acceptation du lot 7. Il s'appuie sur `docs/refonte/champs-montants.md` et sur le cahier des règles (`docs/refonte/cahier-regles.md`).

**Règle d'or pour Gemini.** Il ne modifie jamais un fichier `test_*.py`. Il peut adapter seulement `tests/fabriques_lot7.py` et `tests/acceptation/lot7/conftest.py`. Si une assertion lui semble fausse, il s'arrête et le signale avec preuve (voir section 7). Il ne devine pas, il n'ajoute aucune règle.

---

## 1. Règles couvertes

**E-11. Montants et permission `projets.voir_montants`**
- Détenteurs (annexe 1) : DG, DF, DO, CP. Non-détenteurs : AD, CT, CC, MAG, BAI, VI.
- Lecture : sans la permission, tous les champs de montants sont **absents** du JSON (pas `null`, pas `0`) : `budget_initial_montant` (projet, lot, activité), `budget_total_montant` et `budget_initial_montant` de chaque projet du tableau de bord, `montant` des bons de paiement.
- Écriture : pour écrire un montant, il faut `projets.voir_montants` **et** le droit d'écrire la ressource. Sinon **400** « champ non accepté », sans aucun enregistrement.

**E-12. Retrait des champs sans source réelle**, pour tous les rôles, DG compris : `budget_consomme_montant`, `budget_engage_montant`, `bons_a_signer_montant`, `budget_activites_montant`, et la consommation par projet du tableau de bord.

## 2. Précisions retenues [D] (à confirmer par Durel)

- **P-1. `null` n'est pas un montant.** Un montant **non nul** envoyé sans `voir_montants` est refusé (400). La clé absente, ou envoyée à `null`, est acceptée et ignorée. Raison : le front actuel (non modifié) peut envoyer la clé à `null`.
- **P-2. Ordre des contrôles.** Le droit d'écrire la ressource est contrôlé d'abord : un rôle sans `projets.ecrire` (DF, VI) reçoit 403, même s'il envoie un montant. Le 400 ne concerne que les rôles qui ont le droit d'écrire mais pas `voir_montants` (AD, CT).
- **P-3. Conséquence assumée.** L'AD peut créer un projet, un lot ou une activité **sans** montant, et modifier le reste. Il ne peut jamais écrire de montant.
- **P-4. Un refus n'enregistre rien.** Un PATCH refusé ne modifie aucun autre champ de la même requête. Une création refusée ne crée rien.
- **P-5. Filet générique.** Pour AD et CT, aucune clé dont le nom contient `montant`, `budget`, `cout` ou `prix` ne doit apparaître dans aucune ressource lue (y compris les statistiques). Il couvre les oublis possibles.
- **P-6. Champs non monétaires conservés.** `bons_a_signer_count`, `bons_paiement_a_valider`, `id`, `statut` restent présents pour tous.

## 3. Points que Gemini doit vérifier ou signaler (sans les résoudre seul)

Ces points viennent d'incohérences entre ses réponses précédentes et les faits du lot 7. Il répond par `VÉRIFIÉ (fichier:ligne)` ou `NON VÉRIFIÉ`.

1. **URL du tableau de bord.** Les faits donnent `/api/v1/dashboard/`. L'inventaire précédent citait `/api/v1/projets/tableau-de-bord/` et `/api/v1/projets/{id}/tableau-de-bord/`. Donner la ou les routes réelles et ce que chacune renvoie.
2. **Statistiques.** Les faits ne citent que `budget_activites_montant`. L'inventaire précédent attribuait aussi `budget_initial_montant` et `budget_consomme_montant` à `StatistiquesProjetSerializer`. Donner la liste exacte des champs de montant renvoyés par `/api/v1/projets/{pk}/statistiques/`.
3. **Origine de `bons_paiement_a_valider`.** Une réponse précédente disait que le module Finance n'est pas implémenté. D'où viennent les éléments de cette liste (modèle, calcul, liste vide) ? La fabrique `bon_paiement` est-elle possible ? Sinon la signaler, sans contourner.
4. **Routes de lot.** Les faits citent `/api/v1/lots/{pk}/`. Une réponse précédente citait `/api/v1/projets/{id}/lots/{lot_id}/`. Donner les routes réelles de détail d'un lot et d'une activité.
5. **Budget obligatoire ?** Le champ `budget_initial_montant` est-il obligatoire à la création d'un projet, d'un lot ou d'une activité ? S'il l'est, l'AD ne pourrait jamais créer : c'est une contradiction avec P-3, à signaler avant tout code.
6. **Contraintes entre budgets.** Existe-t-il une règle métier (budget d'un lot au plus égal à celui du projet, etc.) ? Les tests d'écriture utilisent 20 M (projet), 10 M (lot), 500 k (activité existante), 1 M (montant écrit).

## 4. Inventaire des tests (144 : 98 `carac`, 46 `regle`)

**Légende.** `carac` : comportement déjà vrai, vert avant et après. `regle` : règle nouvelle, rouge avant, vert après.

| Fichier | Tests | carac | regle | Couverture |
|---|---|---|---|---|
| `test_00_plomberie_lot7.py` | 15 | 15 | 0 | Canari : chaque client = son utilisateur, URL et payloads valides pour le DG, forme du tableau de bord |
| `test_e11_masquage_montants_lecture.py` | 37 | 17 | 20 | Lecture : DG, DO, CP, DF voient ; AD, CT, CC, BAI, VI ne voient pas ; tableau de bord ; bons de paiement ; filet générique |
| `test_e11_refus_ecriture_montants_sans_droit.py` | 81 | 66 | 15 | Écriture : droit complet, sans montant, `null`, 400 pour AD et CT, 403 pour DF et VI, rien n'est enregistré, création de projet |
| `test_e12_retrait_champs_sans_source.py` | 11 | 0 | 11 | Aucun des champs retirés dans 8 ressources pour 6 rôles, dans les réponses d'écriture, dans le code, valeur 22,5 %, notes de changement API |

Les nombres exacts de rouges peuvent différer dans le dépôt réel : toute différence avec cette table doit être expliquée par Gemini au dry-run.

**Référence de validation.** Les 144 tests ont été exécutés contre une API simulée en mémoire : état « cible » (E-11 et E-12 appliquées) : 144 réussis ; état « actuel » (sans masquage, avec les champs inventés) : 98 réussis, 46 échoués, dont aucun test `carac`. Cela prouve la cohérence interne des tests, pas leur compatibilité avec le vrai code.

## 5. Contrat des fabriques (`tests/fabriques_lot7.py`)

Gemini implémente chaque méthode en réutilisant `tests/fabriques_lot6.py`. Les signatures sont figées.

- Acteurs : `utilisateur(role_code, *, actif=True)`, `client(utilisateur=None)`, `affecter(projet, utilisateur, role_projet="VI")`.
- Données : `projet(*, budget=None, statut="EN_COURS")`, `lot(projet, *, budget=None)`, `activite(lot, *, budget=None)`, `bon_paiement(projet, *, montant)`, `nombre_projets()`.
- URL : `url_projets`, `url_projet`, `url_lots`, `url_lot`, `url_activites`, `url_activite`, `url_statistiques`, `url_dashboard` (les URL réelles de l'API).
- Charges sans montant : `payload_projet`, `payload_modification_projet`, `payload_lot`, `payload_modification_lot`, `payload_activite`, `payload_modification_activite`.

## 6. Anti-triche et verrouillage

- Le canari `test_00_plomberie_lot7.py` doit être vert avant tout code. Il vérifie notamment que chaque client est bien son utilisateur : une plomberie qui authentifie tout le monde en DG est détectée.
- Aucun `skip`, `xfail`, `importorskip`, aucune modification de `conftest.py` pour masquer un test.
- `python tests/acceptation/lot7/verifier_verrouillage.py` compare l'empreinte de chaque `test_*.py` à celle attendue (insensible aux fins de ligne CRLF/LF) et refuse `skip`/`xfail`. Il doit afficher « Verrou intact » à chaque étape et dans le rapport final.
- Aucun fichier du dépôt front n'est modifié (règle G-01).

## 7. Déroulé pour Gemini

1. **Copier** les fichiers aux emplacements indiqués (la structure est celle du dépôt) et lancer `verifier_verrouillage.py`.
2. **Répondre aux points de la section 3**, sans écrire de code applicatif.
3. **Implémenter la plomberie** (`fabriques_lot7.py`, `conftest.py`) en réutilisant le lot 6.
4. **Lancer le canari** et coller la sortie brute. Il doit être vert à 100 %.
5. **Dry-run** : lancer toute la suite lot 7 (sans rien changer) et coller : la commande, la durée, la liste des tests rouges et verts, et pour chaque test rouge de type `carac` la cause. Comparer à la section 4.
6. **Analyse par Claude.** Aucune implémentation ne démarre avant cette analyse. Elle peut conduire à corriger des tests (par Claude).
7. **Commit de verrouillage** après accord : `git add tests/fabriques_lot7.py tests/acceptation/lot7 docs/refonte/07-cadrage-tests-lot7.md`, puis un commit et `git tag verrouille-lot7`.
8. **Implémenter** E-11 et E-12 dans le backend uniquement, par petits lots, avec tests. Mettre à jour `notes-changement-api.md` (champs retirés, masquage par `voir_montants`, nouveau 400, impact sur le front : tuile « Dépensé », zone budget).
9. **Rapport final** : sortie brute de la suite lot 7 (144 verts), de la suite complète (au moins 241 + 144, aucun test précédent rouge), `git diff --stat`, `verifier_verrouillage.py`, `git status` du dépôt front (propre).

**Si un test semble faux :** s'arrêter, citer le test, la ligne du code qui le contredit et la sortie brute. Ne rien contourner.

## 8. Hors périmètre du lot 7

- Le front : tuiles « Dépensé » et « budget non défini », bouton « cadrer le budget » (annexe 3 du cahier).
- La validation du schéma OpenAPI (contrôlée seulement par l'absence des noms dans le code).
- Les autres statuts, la portée, les permissions d'administration.

## 9. Décisions à confirmer par Durel avant le verrouillage

- **P-1** : un montant à `null` est accepté et ignoré.
- **P-2** : 403 avant 400.
- **P-3** : l'AD écrit sans montant, jamais avec.
- **P-5** : le filet générique pour AD et CT.
