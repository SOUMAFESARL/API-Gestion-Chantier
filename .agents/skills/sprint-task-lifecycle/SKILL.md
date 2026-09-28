---
name: sprint-task-lifecycle
description: >-
  Workflow standard pour traiter toute nouvelle tâche ou fonctionnalité du sprint (Backend ou Frontend).
  À déclencher dès que l'utilisateur confie une tâche du backlog ou demande d'implémenter une feature.
  Impose un cycle strict : Cadrage & Brainstorming -> Génération du Manuel PDF d'Apprentissage Pratique
  (Zéro code par l'agent, le développeur implémente manuellement) -> Branche Git -> Tests & Pre-Mortem ->
  Consolidation Métacognitive et élévation au niveau Homo Docens.
---

# Cycle de Vie d'une Tâche de Sprint & Apprentissage Pratique

Suivre scrupuleusement ces 5 étapes séquentielles pour chaque tâche de développement :

## Étape 1 : Exploration & Cadrage Neurocognitif (Lecture seule)
1. **Explorer le code existant** en rapport avec la tâche avant toute proposition.
2. **Identifier les règles métier** (normes OHADA, contraintes BTP, flux CinetPay, architecture multi-tenant, etc.).
3. **Mener le cadrage interactif avec l'utilisateur** :
   - Cadrage narratif SCQA (Situation, Complication, Question, Orientation).
   - Ensemencement du **Film Mental (Murphy)** : visualiser le livrable final accompli.
   - Poser les questions d'arbitrage indispensables.
   - **Règle d'or :** Aucun fichier de code n'est modifié durant cette étape.

## Étape 2 : Rédaction et Génération du « Manuel PDF d'Apprentissage par la Pratique »
1. **Interdiction formelle d'écrire le code métier par l'agent** :
   - L'agent ne modifie aucun fichier de code backend pour la tâche.
2. **Génération du Manuel PDF de Tâche** :
   - L'agent génère un guide complet au format PDF via `reportlab` dans :
     `Manuels_Apprentissage/MANUEL_SPRINT_<N>_TACHE_<ID>_<NOM>.pdf`
   - Ce manuel structure l'apprentissage actif :
     * *Section 1 : Film Mental & Objectif Sacré* (Visualisation subconsciente).
     * *Section 2 : Architecture & Invariants (Pólya / Dehaene)* (Modèles de données, contrats d'API).
     * *Section 3 : Guide d'Implémentation Pas-à-Pas pour vos Mains* (Code commenté, explications profondes).
     * *Section 4 : Signal d'Erreur Bayésien & Pre-Mortem (Dehaene P3 / Kahneman)* (Cas limites, pièges classiques).
     * *Section 5 : Checklist de Tests & Validation manuelle*.
     * *Section 6 : Défi Homo Docens* (Transmettre et enseigner la notion à un pair).

## Étape 3 : Isolation Git sur Branche Feature
1. Se repositionner sur la branche principale d'intégration et récupérer les dernières modifications :
   ```bash
   git checkout develop
   git pull
   ```
2. Créer la branche dédiée à la tâche :
   ```bash
   git checkout -b feature/<nom-court-de-la-tache>
   ```

## Étape 4 : Implémentation Manuelle par le Développeur & Tests
1. **Le développeur tape le code manuellement** en suivant le manuel PDF généré.
2. L'agent reste en posture de mentor socratique et de soutien subconscient :
   - Réfutation bienveillante des erreurs de compilation ou de test (Predictive Coding).
   - Application de la Loi de l'Effort Inversé si blocage (respirer, décharger).
3. Exécuter les commandes de validation :
   - **Backend :**
     ```bash
     pytest apps/<module>/tests/ -v
     ```
   - **Frontend :**
     ```bash
     npx tsc --noEmit
     npm run lint
     ```

## Étape 5 : Intégration dans `develop`, Suppression de Branche & Ancrage Homo Docens
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
3. **Supprimer immédiatement la branche de feature** :
   ```bash
   git branch -d feature/<nom-court-de-la-tache>
   ```
4. **Attention frontend :** Sur le frontend (`Application-Gestion-Chantier`), l'exécution de `git push` est **strictement interdite** (se référer au skill `prevent-frontend-push`).
5. **Clôture Métacognitive** : L'apprenant valide son défi *Homo Docens* et planifie sa consolidation nocturne (Replay à $20\times$).
