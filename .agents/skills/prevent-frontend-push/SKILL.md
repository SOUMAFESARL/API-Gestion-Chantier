---
name: prevent-frontend-push
description: >-
  Règle impérative interdisant formellement tout 'git push' sur le frontend (Application-Gestion-Chantier).
  À activer lors de toute tâche Git, fin de sprint, commit, merge, livraison, ou demande d'envoi vers un dépôt distant.
---

# Règle Absolue : Interdiction de Push sur le Frontend (Application-Gestion-Chantier)

## 1. Contexte & Principe Directeur

Sur le projet frontend **Application-Gestion-Chantier**, tout envoi vers un dépôt distant (`git push`) est **strictement prohibé** pour les agents d'IA.

Cette restriction protège le code distant contre tout déploiement non supervisé, écrasement involontaire de branches distantes (`develop`, `main`), ou déclenchement intempestif de pipelines CI/CD de production.

---

## 2. Ce qui est STRICTEMENT INTERDIT

L'agent ne doit **JAMAIS**, sous aucun prétexte, exécuter l'une des commandes suivantes sur le dépôt frontend :
- `git push`
- `git push origin <branche>`
- `git push --all`
- `git push --tags`
- `git push --force` ou `git push -f`
- Tout script, hook, commande chaînée ou outil automatisé déclenchant un `git push`.

---

## 3. Ce qui est AUTORISÉ en Local

Le travail de développement, de test et de versionnement local reste pleinement opérationnel :
- ✅ Consultation : `git status`, `git log`, `git diff`, `git branch`
- ✅ Navigation : `git checkout`, `git switch`
- ✅ Réception des nouveautés : `git pull`, `git fetch`
- ✅ Enregistrement local : `git add`, `git commit` (avec messages conventionnels)
- ✅ Intégration locale : `git merge --no-ff feature/<nom>` dans `develop`
- ✅ Nettoyage local : `git branch -d feature/<nom>`

---

## 4. Protocole d'Intégration Local Frontend

Lors de la finalisation d'une tâche de sprint ou de refonte sur le frontend :

1. Valider le code localement :
   ```bash
   npm run lint
   npm run typecheck
   ```
2. Commiter sur la branche feature :
   ```bash
   git add <fichiers>
   git commit -m "feat/fix(<scope>): <description>"
   ```
3. Fusionner en local dans `develop` :
   ```bash
   git checkout develop
   git merge --no-ff feature/<nom-de-branche> -m "merge: feature/<nom-de-branche> into develop"
   ```
4. Supprimer la branche feature locale :
   ```bash
   git branch -d feature/<nom-de-branche>
   ```
5. **ARRÊT OBLIGATOIRE** : Ne PAS exécuter `git push`.

---

## 5. Conduite à Tenir face à une Demande Utilisateur

Si l'utilisateur demande explicitement :
> *"Fais un push"*, *"Pousse sur GitHub"*, *"Met en ligne sur origin"*, etc.

L'agent doit **refuser poliment mais fermement** et répondre :
> **Refus de sécurité :** "Conformément à la politique du projet et au skill `prevent-frontend-push`, il m'est formellement interdit d'effectuer un `git push` sur le frontend (`Application-Gestion-Chantier`). L'envoi vers le dépôt distant doit être validé et effectué manuellement par vos soins."
>
> Fournir la commande que l'utilisateur peut taper lui-même s'il souhaite pousser :
> ```bash
> git push origin develop
> ```
