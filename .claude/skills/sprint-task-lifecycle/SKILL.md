---
name: sprint-task-lifecycle
description: >-
  Déroulé d'une tâche de sprint sur le backend CCD Digital : cadrage, plan dans le chat, branche
  feature, implémentation et tests, merge dans develop. À utiliser dès que l'utilisateur confie une
  tâche du backlog, une user story (« US-0xx », « T-0xx ») ou demande d'implémenter une fonctionnalité.
---

# Cycle de vie d'une tâche de sprint

Cinq étapes, dans l'ordre. Les deux premières ne modifient aucun fichier.

Qui écrit le code est fixé par `AGENTS.md` §3 : le développeur par défaut, l'agent sur demande
expresse. Dans le doute, poser la question à la fin de l'étape 2, pas avant.

## Étape 1 — Cadrage (lecture seule)

1. **Lire avant de proposer.** Le code du module concerné, et ce que la conception en dit dans
   `../../04_Conception/` quand le dossier est présent sur la machine (MLD, conventions d'API,
   spécification fonctionnelle). La conception fait foi sur le code : une divergence se signale,
   elle ne se tranche pas en silence.
2. **Vérifier ce qui existe déjà.** Une story du backlog est souvent à moitié faite : dire ce qui est
   en place, ce qui manque, ce qui s'écarte.
3. **Relever les règles métier en jeu** : OHADA, contraintes BTP, flux CinetPay, isolation
   multi-tenant, Socle Commun.
4. **Restituer le cadrage** en quatre temps — situation, complication, question, orientation —
   suivi du résultat attendu décrit du point de vue de l'utilisateur final (le « film mental » :
   ce qu'il voit et peut faire quand la tâche est finie).
5. **Poser les questions d'arbitrage** qui changent l'implémentation. Seulement celles-là.

## Étape 2 — Plan, dans le chat

Le plan remplace l'ancien manuel PDF, abandonné le 13/10/2026 : **ne générer ni PDF ni script
`generate_manual_*`**, même si le dépôt en contient des dizaines d'exemples.

Le plan tient en un message :

- les fichiers à créer ou modifier, dans l'ordre où les écrire ;
- les modèles, les contrats d'API et les invariants à tenir ;
- **les pièges de cette tâche précise** (deux ou trois, pas une liste générique), chacun avec le
  test qui le révèle ;
- les tests à écrire.

Quand le développeur implémente lui-même, expliquer le *pourquoi* de chaque choix : c'est ce qu'il
réutilisera sur la tâche suivante.

## Étape 3 — Branche feature

```bash
git checkout develop
git pull
git checkout -b feature/<nom-court-de-la-tache>
```

## Étape 4 — Implémentation et tests

1. Implémenter selon le plan. Pour les conventions du dépôt : skill `django-expert-reference`.
2. Écrire les tests en même temps que le code, pas après.
3. Valider :
   ```bash
   ruff check apps/<module>
   pytest apps/<module>/tests/ -v
   ```
4. Quand un test ou une commande échoue : lire l'erreur, dire quelle hypothèse elle infirme, corriger
   la cause. Ne pas affaiblir le test pour le faire passer.

Si la tâche demande un changement côté frontend (`../Application-Gestion-Chantier`), `AGENTS.md` §1
s'applique : lire d'abord le `CLAUDE.md` du frontend, puis valider là-bas par `npm run lint` et
`npm run typecheck`. Le frontend a sa propre branche feature et son propre commit.

## Étape 5 — Intégration dans `develop`

1. Commiter sur la branche feature, message conventionnel :
   ```bash
   git add <fichiers-concernes>
   git commit -m "feat(<scope>): <description claire et concise>"
   ```
2. Fusionner en conservant l'historique, puis supprimer la branche :
   ```bash
   git checkout develop
   git merge --no-ff feature/<nom-court-de-la-tache> -m "merge: feature/<nom-court-de-la-tache> into develop"
   git branch -d feature/<nom-court-de-la-tache>
   ```
3. **Push : quand le développeur le demande.** Il est autorisé sur le backend comme sur le
   frontend, mais `git push origin develop` sur le backend **déploie en production**
   (`AGENTS.md` §2) : le rappeler avant de pousser.
4. **Clôture.** Résumer ce qui a été livré, ce qui a été vérifié et ce qui ne l'a pas été. Puis poser
   au développeur une question qui l'oblige à expliquer le mécanisme central de la tâche comme s'il
   l'enseignait à un pair (le défi « Homo Docens ») — une seule, précise, sans réponse dans le code.
