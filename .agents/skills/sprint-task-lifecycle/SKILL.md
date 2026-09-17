---
name: sprint-task-lifecycle
description: >-
  Workflow standard pour traiter toute nouvelle tâche ou fonctionnalité du sprint (Backend ou Frontend).
  À déclencher dès que l'utilisateur confie une tâche du backlog ou demande d'implémenter une feature.
  Impose un cycle strict en 5 étapes : Brainstorming -> Plan d'implémentation -> Branche feature -> Tests -> Merge dans develop
  puis suppression immédiate de la branche feature pour ne conserver que develop propre et à jour.
---

# Cycle de Vie d'une Tâche de Sprint

Suivre scrupuleusement ces 5 étapes séquentielles pour chaque tâche de développement :

## Étape 1 : Exploration & Brainstorming interactif (Lecture seule)
1. **Explorer le code existant** en rapport avec la tâche avant toute proposition.
2. **Identifier les règles métier** (normes OHADA, contraintes BTP, flux CinetPay, architecture multi-tenant, etc.).
3. **Mener le brainstorming avec l'utilisateur** :
   - Présenter la compréhension du besoin.
   - Proposer les choix d'architecture ou de design possibles.
   - Poser les questions d'arbitrage indispensables.
   - **Règle d'or :** Aucun fichier de code n'est modifié durant cette étape. Attendre les réponses et orientations de l'utilisateur.

## Étape 2 : Plan d'Implémentation & Validation formelle
1. Rédiger le document technique détaillé dans l'artefact `implementation_plan.md`.
2. Définir précisément :
   - Les composants impactés et les nouveaux fichiers à créer (`[NEW]`, `[MODIFY]`).
   - Les arbitrages validés lors du brainstorming.
   - Le plan de vérification automatisé et manuel.
3. **Attendre le feu vert explicite** de l'utilisateur avant d'écrire la moindre ligne de code.

## Étape 3 : Isolation Git sur Branche Feature éphémère
1. Se repositionner sur la branche principale d'intégration et récupérer les dernières modifications :
   ```bash
   git checkout develop
   git pull
   ```
2. Créer la branche dédiée à la tâche :
   ```bash
   git checkout -b feature/<nom-court-de-la-tache>
   ```

## Étape 4 : Implémentation, Tests & Vérification automatique
1. Développer la solution en respectant les conventions du projet :
   - Backend Django : architecture selectors/services, modèles conformes MLD, typage Python.
   - Frontend Next.js : composants accessibles, tokens CSS de la charte, internationalisation, typage strict.
2. Exécuter les commandes de validation :
   - **Backend :**
     ```bash
     pytest apps/<module>/tests/ -v
     ```
   - **Frontend :**
     ```bash
     npx tsc --noEmit
     npm run lint
     ```
3. Résoudre toute erreur ou régression avant de passer à l'étape suivante.

## Étape 5 : Intégration dans `develop`, Suppression de Branche & Rapport
1. Commiter les modifications sur la branche de feature avec un message conventionnel :
   ```bash
   git add <fichiers-concernes>
   git commit -m "feat(<scope>): <description claire et concise>"
   ```
2. Basculer sur `develop` et fusionner avec conservation de l'historique (merge commit) :
   ```bash
   git checkout develop
   git merge --no-ff feature/<nom-court-de-la-tache> -m "merge: feature/<nom-court-de-la-tache> into develop"
   ```
3. **Supprimer immédiatement la branche de feature** pour ne garder que `develop` propre :
   ```bash
   git branch -d feature/<nom-court-de-la-tache>
   ```
4. Rédiger ou mettre à jour le bilan de réalisation dans l'artefact `walkthrough.md`.
