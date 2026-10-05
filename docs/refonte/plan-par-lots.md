# Plan par lots et protocole de travail (Refonte droits, backend)

Document à donner à Gemini avec le cahier gelé (`docs/refonte/cahier-regles.md`). Il se lit en entier avant tout lot.

---

# PARTIE 1. PROTOCOLE (s'applique à tous les lots)

## 1.1 Les trois principes

1. **Tu n'inventes rien.** Un nom, un chemin, un numéro de ligne, un code de permission, une règle : tu les as lus dans le code ou dans le cahier, ou tu n'écris pas.
2. **Tu ne prends aucun raccourci.** Un test qui échoue se résout en changeant le code de production, jamais le test.
3. **Dans le doute, tu t'arrêtes et tu poses une question.** S'arrêter n'est jamais un échec. Deviner en est un.

## 1.2 Ce que tu lis, dans cet ordre, au début de chaque lot

1. Le cahier : `docs/refonte/cahier-regles.md`.
2. La fiche du lot dans la partie 3 de ce document.
3. Les tests du lot : `tests/acceptation/lotN/`. Ils sont la définition de « terminé ».
4. L'inventaire validé : `docs/refonte/inventaire-lot0.md`.
5. Les questions déjà résolues : `docs/refonte/questions-ouvertes.md`.

Tu ne travailles **que** sur les règles citées dans la fiche. Une chose utile mais hors fiche (un bug voisin, un renommage, un nettoyage) va dans le rapport de fin de lot sous « Constaté, non traité ». Tu n'y touches pas.

## 1.3 Boucle de travail d'un lot

| Étape | Action | Preuve à garder |
|---|---|---|
| 1 | Vérifier les **prérequis** de la fiche. Un seul manquant : STOP, question. | Liste cochée dans `docs/refonte/lotN-journal.md` |
| 2 | Lancer `pytest tests/acceptation/lotN -q`. Les tests doivent **échouer**. Un test qui passe déjà : le noter, ne rien « réparer ». | Sortie réelle collée dans le journal |
| 3 | Écrire dans le journal un tableau : règle, fichiers que tu comptes modifier, tests qui la prouvent. **Aucun code avant ce tableau.** | Le tableau |
| 4 | Implémenter dans **l'ordre des étapes de la fiche**. Après chaque étape, relancer les tests concernés. | Une ligne de journal par étape |
| 5 | Lancer la suite complète : `pytest -q`. Comparer à `docs/refonte/baseline-tests.txt`. Aucun test qui passait ne doit échouer, sauf ceux que la fiche autorise. | Sortie réelle |
| 6 | `python manage.py migrate_schemas` doit passer. | Sortie réelle |
| 7 | Mettre à jour `docs/notes-changement-api.md` si le contrat de l'API change (G-03). | Le diff |
| 8 | Lancer les **commandes de sortie** de la fiche (greps, comptages). Coller le résultat brut. | Sortie brute |
| 9 | Un seul commit : `lot N: <titre>`. Écrire `docs/refonte/lotN-rapport.md` (modèle en 1.7). | Le rapport |

Tu ne passes pas à l'étape suivante tant que la précédente n'est pas prouvée. Tu n'enchaînes jamais deux lots.

## 1.4 Interdits absolus

Chacun de ces gestes est une faute, même « temporaire », même « pour débloquer ».

**Sur les tests**
- Modifier une assertion, un nom, une constante, un `import` d'un test dans `tests/acceptation/`.
- Ajouter `skip`, `skipif`, `xfail`, `pytest.importorskip`, ou supprimer/renommer/déplacer un test.
- Modifier un test existant hors de la liste I-08 validée.
- Remplacer un vrai appel par un mock quand le test vérifie un contrôle d'accès.
- Modifier `conftest.py` ou la configuration pytest d'un lot verrouillé.
- Adapter une fabrique (`tests/fabriques.py`) autrement que pour un **nom de champ réel** ; chaque adaptation est listée dans le journal.

**Sur le code**
- Écrire du code qui détecte qu'on est en test (`settings.TESTING`, `"pytest" in sys.modules`, variable d'environnement de test).
- Écrire en dur le résultat attendu d'un test (renvoyer 403 pour un utilisateur précis, une valeur précise).
- Décider d'un accès d'après un **nom de rôle** ou un **niveau** au lieu d'un **code de permission** (sauf là où le cahier l'exige : DG, B-03).
- Entourer un contrôle d'accès d'un `try/except` large qui laisse passer.
- Modifier ou supprimer une migration déjà commitée. On en crée une nouvelle.
- Ajouter une dépendance (pip) sans question préalable.
- Renommer une route, un champ ou un modèle que le cahier ne cite pas (G-02).
- Toucher au dépôt front (G-01), même pour lire autre chose que son état.

**Sur la méthode**
- Utiliser `git commit --no-verify`, `git push --force`, `git reset --hard` sur des commits partagés, `git tag` (les tags sont posés par Durel).
- Dire qu'une chose est faite sans l'avoir exécutée. Écrire « devrait passer » : interdit, on exécute.
- Écrire un résumé de sortie de test au lieu de la sortie réelle.

## 1.5 Quand tu t'arrêtes (STOP)

Tu t'arrêtes, tu écris une question (1.6), et tu ne continues pas sur la partie concernée, dans **chacun** de ces cas :

1. Une règle est ambiguë, ou deux règles se contredisent.
2. Un nom du cahier (modèle, champ, route, fonction) est introuvable dans le code, ou y existe sous une forme différente.
3. Un test te semble impossible à satisfaire, ou absurde.
4. Un prérequis de la fiche manque, ou une valeur `A_CONFIRMER` subsiste dans I-07 et la fiche en dépend.
5. Un test existant, hors liste I-08, échoue après ton changement.
6. Tu as essayé **deux approches différentes** pour faire passer le même test et il échoue toujours.
7. Un changement toucherait plus de fichiers que ceux annoncés dans ton tableau d'étape 3.
8. Tu devrais ajouter une dépendance, modifier une migration passée, ou toucher au front.
9. Tu es tenté d'utiliser un interdit de 1.4. Cette tentation est le signal pour t'arrêter.

## 1.6 Format d'une question

Fichier : `docs/refonte/questions-ouvertes.md`. Une question par bloc, numérotée à la suite.

```
## Q-007 | B-09 | OUVERTE
**Contexte** : faits vérifiés, avec chemin:ligne.
**Question** : une seule phrase.
**Options** : A) ... B) ... (au plus trois, chacune avec sa conséquence)
**Impact** : ce qui est bloqué (tests, étapes).
**Déjà fait / pas fait** : où tu t'es arrêté.
```

Le titre suit exactement `## Q-NNN | <règle ou GENERAL> | OUVERTE`. Tu n'écris jamais la réponse. Durel ajoute `**Réponse de Durel** : ...` et passe le statut à `RESOLUE`. Tu n'édites jamais une réponse ni un statut `RESOLUE`.

## 1.7 Modèle du rapport de fin de lot (`docs/refonte/lotN-rapport.md`)

```
# Rapport lot N
## Règles
| Règle | Statut (FAIT / PARTIEL / NON FAIT) | Tests | Fichiers modifiés |
## Sorties brutes
(pytest lot, pytest complet, migrate_schemas, commandes de sortie : coller tel quel)
## Constaté, non traité
## Questions ouvertes liées
## Adaptations de fabriques
```

Un statut `PARTIEL` ou `NON FAIT` est accepté s'il est honnête. Un `FAIT` non prouvé par une sortie brute est traité comme `NON FAIT`.

## 1.8 Convention des tests (pour Durel et Claude, qui les écrivent)

- Dossier `tests/acceptation/lotN/`. Les tests sont commités par Durel, puis le tag `verrouille-lotN` est posé.
- Chaque fonction de test commence sa docstring par l'identifiant de règle : `"""[B-06] Un AD qui suspend un AD reçoit 403."""`.
- Chaque critère d'acceptation (CA) du cahier a au moins un test. Chaque règle de refus a un test du cas autorisé **et** un du cas refusé.
- Les requêtes sont de vraies requêtes HTTP (client de test), jamais des appels directs aux fonctions de garde.
- Les fabriques d'objets sont dans `tests/fabriques.py` (adaptables pour les noms de champs réels, voir 1.4).

## 1.9 Qui fait quoi à chaque lot

| Qui | Action |
|---|---|
| Claude + Durel | Écrivent les tests du lot N sur la base des faits de l'inventaire. Durel les relit. |
| Durel | Commite les tests, pose `verrouille-lotN`. Résout les prérequis bloquants. |
| Gemini | Exécute le lot selon 1.3. |
| Durel | Relit le rapport, lance les commandes de la section « Sortie de lot », pose le tag `lotN-ok`. |

---

# PARTIE 2. VUE D'ENSEMBLE

| Lot | Titre | Règles | Dépend de | Bloqué tant que |
|---|---|---|---|---|
| 0 | État des lieux, sans changement de comportement | G-01, G-03, G-04, G-05 (inventaires de A-12, B-03, C-04, H-01, E-09, D-04) | cahier gelé | points 1 à 5 de `00-points-avant-gel.md` |
| 1 | REGISTRE, catalogue, permissions effectives | A-01 à A-04, A-06, A-12, A-15, B-05, B-11, E-01, E-02, annexe 1 | 0 | I-01, I-06, I-08 validés ; snapshot des rôles (point 13) |
| 2 | Rôle unique, DG calculé, portée, profil compatible | B-01, B-02, B-03, D-01 à D-03, D-07, G-02 | 1 | I-02 validé ; point 9 |
| 3 | Garde unique et filtrage par projet | D-04 à D-06, D-08 | 2 | I-07 sans `A_CONFIRMER` (point 10) |
| 4 | Administration des rôles | A-13, B-04, B-06 à B-10, B-12, F-01, F-02 | 3 | point 6 tranché |
| 5 | Projets : écritures, affectation, équipes | C-05 (puces 2 et 3), E-03 à E-07, E-13 | 4 | points 1, 7 |
| 6 | Statuts de projet | E-08, E-09, E-10 | 5 | point 4 ; I-05 |
| 7 | Montants | E-11, E-12 | 6 | point 11 |
| 8 | Collaborateurs, registre global, abonnement, lectures | C-01 à C-04, C-05 (puce 1), F-03 à F-08 | 7 | I-03 ; points 8, 12 |
| 9 | Propagation super admin, plateforme | A-05 à A-11, A-14, H-01, H-02 | 8 | I-04, I-10 ; point 12 |
| 10 | Clôture | F-09, F-10, vérification de G-02 et G-03 | 9 | aucun |

Couverture : toutes les règles du cahier sont dans exactement un lot, sauf G-02, G-03, G-05 (transversales, vérifiées à chaque lot et au lot 10). F-09 (inchangé) est vérifié par non-régression au lot 10.

---

# PARTIE 3. FICHES DE LOT

## LOT 0. État des lieux (aucun changement de comportement)

**Objectif** : établir les faits dont les lots suivants dépendent, et prouver que Gemini sait citer le code sans inventer. Aucun fichier de production n'est modifié.

**Prérequis (faits par Durel avant de lancer Gemini)**
1. Les points BLOQUANT de `00-points-avant-gel.md` sont réglés ; cahier copié dans `docs/refonte/cahier-regles.md` avec `Statut : GELÉ`.
2. Branche `refonte-droits` créée, tag `base-refonte` posé sur son commit de départ.
3. Variable `FRONT_REPO` définie.
4. Tests du lot 0 commités dans `tests/acceptation/lot0/`, tag `verrouille-lot0` posé.
5. Le gabarit est commité dans `docs/refonte/gabarit-inventaire-lot0.md`, avec le cahier gelé et les tests (zone autorisée du lot 0).

**Étapes**
1. Lancer la suite complète existante : `pytest -q > docs/refonte/baseline-tests.txt 2>&1`. Ne rien corriger, même si des tests échouent déjà. Le résumé pytest (`N passed`) doit apparaître dans le fichier.
2. Créer `docs/notes-changement-api.md` avec pour seule première ligne `# Notes de changement API` (G-03).
3. Créer `docs/refonte/questions-ouvertes.md` avec une ligne de titre `# Questions ouvertes`.
4. Copier le gabarit vers `docs/refonte/inventaire-lot0.md` et remplir **section par section** (I-01 à I-10), en suivant les règles de remplissage du gabarit. Pour chaque section, chercher dans le code avec de vraies commandes (`grep -rn`), jamais de mémoire.
5. Écrire `tests/caracterisation/test_statut_critique.py` : un test qui décrit ce que fait **aujourd'hui** `executer_evaluation_quotidienne_schema` sur un projet CRITIQUE. Il doit passer sur le code actuel. Si ce comportement ne peut pas être établi, écrire une question E-09.
6. Pour chaque écart avec le cahier (par exemple 6 conditions DG au lieu de 5), écrire une question.
7. Lancer `pytest tests/acceptation/lot0 -q`, corriger **l'inventaire** (jamais le test) jusqu'à ce que tout passe.
8. Commit unique : `lot 0: état des lieux`.

**Hors périmètre** : corriger le moindre code, renommer, nettoyer, « améliorer » un test existant, résoudre une question toi-même.

**Sortie de lot** (Durel) : `pytest tests/acceptation/lot0 -q` tout vert ; relecture humaine de l'inventaire (surtout I-02, I-03, I-04, I-07, I-08) ; décisions sur les questions ; tag `lot0-ok`.

**Pièges**
- Les numéros de ligne sont ceux du commit `base-refonte`. Ne modifie aucun fichier de production : ils ne bougent pas.
- Un constat sans référence doit s'écrire `ABSENT`. Écrire « aucune limite » avec une référence inventée fera échouer les tests.
- Une hésitation n'a pas sa place dans l'inventaire. Elle devient une question.

---

## LOT 1. REGISTRE, catalogue, permissions effectives

**Règles** : A-01, A-02, A-03, A-04, A-06, A-12, A-15, B-05, B-11, E-01, E-02, annexe 1.

**Prérequis** : I-01, I-06, I-08 validés par Durel ; fichier `docs/refonte/snapshot-roles-avant.json` produit (point 13) ; table niveau → codes de E-02 écrite par Durel dans le journal du lot, d'après I-06 ; tests du lot commités et tag posé.

**Étapes (dans cet ordre)**
1. Ajouter au REGISTRE les codes nouveaux de E-01 et le marqueur `reservee_administration`. `rang` reste (G-02).
2. Commande de synchronisation `CataloguePermission` (idempotente, code inconnu refusé en 400).
3. **Migration de données** : traduire les niveaux actuels en lignes de `permissions_catalogue` (E-02) et appliquer la matrice de l'annexe 1. À ce stade, rien n'est supprimé.
4. `permissions_effectives()` lit uniquement la liste cochée, ignore `niveau_max`, ignore les modules désactivés et les permissions désactivées (A-06, A-12).
5. Retirer `niveau_max` aux endroits de I-01 (code et les tests de I-08 concernés, comme le cahier le dit).
6. Valider côté serveur : refus 400 d'une permission `administration.*` cochée (B-05), d'un code inconnu (A-01).
7. **Dernière migration** : supprimer la relation `permissions` vers `accounts.Permission` et les 4 verbes génériques (A-03).
8. Vérifier que le JWT ne porte aucune permission et que `role_global` du claim n'est lu nulle part pour décider d'un accès (B-11).

**Hors périmètre** : le rôle unique (lot 2), la portée (lot 2), toute vue (lot 3 et suivants).

**Sortie de lot** : `grep -rn niveau_max --include=*.py . | grep -v migrations` ne renvoie plus rien ; `CataloguePermission` ne contient aucun des 4 verbes génériques ; migrations OK.

**Pièges** : ne jamais supprimer avant d'avoir traduit (étape 3 avant 7). `rang` n'a plus aucun rôle de décision, mais il reste pour `habilitations`.

---

## LOT 2. Rôle unique, DG calculé, portée, profil compatible

**Règles** : B-01, B-02, B-03, D-01, D-02, D-03, D-07, G-02.

**Prérequis** : lot 1 terminé ; I-02 validé ; point 9 tranché ; tests commités.

**Étapes**
1. Champ de rôle unique sur le collaborateur ; migration de données MOA vers BAI, MOE vers VI.
2. Les entrées `role_global` et `role_personnalise_id` restent acceptées et sont traduites vers le rôle unique.
3. Fonction unique `est_dg(utilisateur)` ; remplacer **toutes** les conditions de I-02 par cet appel.
4. Rôle du DG calculé (toutes les permissions des modules activés + administration), non modifiable, DG non suspendable ni supprimable.
5. Portée ENTREPRISE ou PROJET sur le rôle ; migration D-07 (ENTREPRISE pour qui a `projets.voir_tous` aujourd'hui, PROJET sinon) **avant** de retirer `voir_tous` du REGISTRE.
6. Changement de portée avec confirmation explicite (D-03).
7. `GET /profil/` : `role_global`, `habilitations`, `permissions` (G-02).

**Hors périmètre** : toute règle de l'AD (lot 4), la garde des vues (lot 3).

**Sortie de lot** : le `grep` de la condition DG copiée ne renvoie plus que `est_dg` ; compteur `RoleGlobal` comparé à I-09 (il baisse, aucun accès n'en dépend).

**Pièges** : le JWT peut contenir encore `role_global` : ne jamais le lire pour décider.

---

## LOT 3. Garde unique et filtrage par projet

**Règles** : D-04, D-05, D-06, D-08.

**Prérequis** : lot 2 terminé ; **I-07 sans aucun `A_CONFIRMER`** ; `MotifReport` et `pilotage` : décision de Durel écrite dans le journal ; tests commités.

**Étapes**
1. Garde unique (D-08) : code détenu ET (portée ENTREPRISE OU affectation active au projet).
2. Méthode commune de filtrage par projet (D-06) ; `GlobalJournalReportsView` filtré.
3. Module mixte séparé (D-04), avertissement D-05.
4. Remplacer **vue par vue** `PermissionModule`, `MembreDuProjet`, `RoleRequis`. Dans le journal, un tableau : vue, ancienne garde, nouveau code. **Le comportement actuel est conservé** (les changements viennent aux lots 5 et 6). Si aucune permission du REGISTRE ne correspond à l'ancienne garde d'une vue : STOP, question.

**Sortie de lot** : `grep -rn -E "PermissionModule|MembreDuProjet|RoleRequis" --include=*.py . | grep -v -E "migrations|tests"` ne renvoie rien (ou, pour `MembreDuProjet`, seulement ce que D-08 autorise, à préciser par question).

**Pièges** : ne pas profiter du lot pour « corriger » une garde faible. Constater dans le rapport.

---

## LOT 4. Administration des rôles

**Règles** : A-13, B-04, B-06, B-07, B-08, B-09, B-10, B-12, F-01, F-02.

**Prérequis** : lot 3 terminé ; **point 6 tranché** (conséquence de B-09) ; tests commités.

**Étapes**
1. A-13 : supprimer l'appel à `appliquer_modeles_roles()` sur entreprise existante ; créer la fonction qui n'ajoute que les rôles système manquants ; retirer les appels paresseux dans les GET.
2. Droits d'administration de l'AD en liste fixe dans le code (B-04).
3. Règles B-06 à B-09 (AD et AD, AD et rôles système, « ne donne que ce qu'il possède », attribution).
4. B-10 : pouvoirs du DG sur les rôles.
5. B-12 : rôles personnalisés.
6. F-01, F-02 : les deux familles de routes de rôles appliquent les mêmes règles ; lectures protégées par `administration.roles_gerer`.

**Sortie de lot** : un GET sur la liste des rôles n'écrit rien en base (vérifié par test).

---

## LOT 5. Projets : écritures, affectation, équipes

**Règles** : C-05 (puces 2 et 3), E-03, E-04, E-05, E-06, E-07, E-13.

**Prérequis** : lot 4 terminé ; points 1 et 7 réglés ; tests commités.

**Étapes**
1. E-13 : supprimer `ContexteCreationProjetView` (vue, route, serializer, tests).
2. E-06 : supprimer `ProjetRoleModuleOverride` (modèle, migration nouvelle, services, vue, route `permissions-roles`) et la clé `AffectationProjet.role` ; `role_projet` reste une étiquette qui synchronise `chef_projet` et `conducteur_travaux`.
3. E-05 : point d'entrée unique d'affectation ; supprimer le garde par étiquette `role_projet == CHEF_PROJET`.
4. E-03 : lots, import, activités, reprogrammation = `projets.ecrire` ; équipes = `projets.gerer_equipes`. Plus aucune écriture protégée par la seule appartenance.
5. E-04 : création = `projets.creer` ; créateur à portée PROJET auto-affecté.
6. C-05 : liste réduite et lecture des affectations.

**Sortie de lot** : compteurs `ProjetRoleModuleOverride` et `ContexteCreationProjetView` à 0 hors migrations.

---

## LOT 6. Statuts de projet

**Règles** : E-08, E-09, E-10.

**Prérequis** : lot 5 terminé ; point 4 tranché ; I-05 validé ; tests commités.

**Étapes**
1. E-08 : séparation `changer_statut` / `resilier_archiver` ; suppression de l'exception « PATCH statut seul ».
2. Inverser `test_statuts_crud.py` et `test_statuts_projet.py` **comme E-08 le demande** (liste I-08). Réécrire `docs/api-projets-statuts.md`.
3. E-09 : statut CRITIQUE protégé, selon le constat de I-05.
4. E-10 : effets des statuts sur les écritures ; refus 409 avec le code `projet_clos`.

---

## LOT 7. Montants

**Règles** : E-11, E-12.

**Prérequis** : lot 6 terminé ; **`docs/refonte/champs-montants.md` écrit par Gemini en premier, puis validé par Durel** (point 11) ; tests commités.

**Étapes**
1. Produire `champs-montants.md` : chaque champ de montant avec `chemin:ligne`, ressource concernée. STOP et attendre la validation.
2. Retirer les champs de montants des réponses sans `projets.voir_montants`.
3. Refuser en 400 l'écriture d'un montant sans `voir_montants` plus droit d'écriture.
4. E-12 : retirer les champs sans source réelle.

---

## LOT 8. Collaborateurs, registre global, abonnement, lectures

**Règles** : C-01, C-02, C-03, C-04, C-05 (puce 1), F-03 à F-08.

**Prérequis** : lot 7 terminé ; I-03 relue ; **C-04 complétée par Durel** (point 12) ; points 8 et 9 réglés.

**Étapes** : ajout en deux temps, départ, registre global e-mail → entreprise (schéma public) et connexion sans boucle sur les schémas, limites du plan, lectures protégées F-03 à F-08.

---

## LOT 9. Propagation super admin, plateforme

**Règles** : A-05 à A-11, A-14, H-01, H-02.

**Prérequis** : lot 8 terminé ; I-04 et I-10 relues ; **H-01 complétée par Durel** (point 12).

**Étapes** : propagation des rôles système (A-07 à A-09), activation et désactivation de module (A-10, A-11), journalisation et e-mail au DG après commit (A-14), impersonation (H-01), un seul niveau de super admin (H-02).

---

## LOT 10. Clôture

**Règles** : F-09, F-10, vérification finale de G-02 et G-03.

**Étapes** : suppression des constantes mortes et correction des docstrings (F-10) ; relecture de `docs/notes-changement-api.md` contre la liste des changements de chaque rapport de lot ; exécution de tous les greps de sortie ; suite complète ; `git status` du dépôt front propre.

**Sortie** : `docs/refonte/rapport-final.md` ; Durel pose `refonte-droits-ok`.
