---
name: prevent-frontend-modification
description: >-
  Règle impérative interdisant formellement à l'agent d'utiliser ses outils d'écriture pour modifier le code frontend (Application-Gestion-Chantier).
  Autorise explicitement 'git pull' pour récupérer les mises à jour distantes, mais interdit 'git push' et toute modification directe de fichiers par les outils de l'agent.
---

# Règle Absolue : Protection du Code Frontend (Application-Gestion-Chantier)

## 1. Contexte & Principe Directeur

Le code source du frontend **Application-Gestion-Chantier** est sanctuarisé :
1. **L'agent d'IA ne doit JAMAIS utiliser ses outils d'édition** (`write_to_file`, `replace_file_content`, scripts de modification) pour altérer directement les fichiers de code frontend.
2. **`git pull` et `git fetch` sont PLEINEMENT AUTORISÉS** : La mise à jour légitime du code local par récupération des commits distants depuis `origin/develop` (ou une autre branche) n'est pas bloquée.
3. **`git push` reste STRICTEMENT INTERDIT** pour l'agent.

---

## 2. Ce qui est STRICTEMENT INTERDIT pour l'Agent

L'agent ne doit **JAMAIS**, sous aucun prétexte :
- **Modifier des fichiers existants avec ses outils** : Ne pas utiliser `replace_file_content`, ni de scripts/commandes altérant les fichiers de code (`sed`, patchs, redirections...).
- **Créer de nouveaux fichiers de code** : Ne pas utiliser `write_to_file` pour générer du code, des composants, des pages ou des configurations dans le frontend.
- **Supprimer ou déplacer des fichiers de code** : Ne jamais exécuter `git rm`, `rm`, `Remove-Item`, `mv` sur les fichiers du frontend.
- **Exécuter `git push`** : Tout envoi vers un dépôt distant (`git push`, `git push origin`, `git push --force`) est prohibé.

---

## 3. Ce qui est PLEINEMENT AUTORISÉ

L'agent et l'utilisateur conservent l'accès aux opérations suivantes :
- ✅ **Synchronisation descendante Git** : `git pull`, `git pull origin develop`, `git fetch` pour intégrer le travail validé depuis le dépôt distant.
- ✅ **Lecture & inspection** : `view_file`, recherche de symboles, exploration d'arborescence (`Get-ChildItem`), recherche textuelle (`Select-String`, `grep`).
- ✅ **Audits & diagnostics** : `npm run typecheck`, `npm run lint` (sans `--fix`), `git status`, `git log`, `git diff`.
- ✅ **Assistance textuelle dans le chat** : Fournir l'analyse, les explications et les blocs de code / diffs prêts à l'emploi directement dans la réponse pour que le développeur humain les applique manuellement.

---

## 4. Conduite à Tenir face à une Demande Utilisateur

- **Si l'utilisateur demande de modifier un fichier frontend** :
  L'agent refuse l'écriture directe dans le fichier et fournit le code ou diff complet dans le chat :
  > "Conformément à la politique du projet et au skill `prevent-frontend-modification`, il m'est interdit de modifier directement les fichiers de code frontend avec mes outils. Voici le code / diff que vous pouvez appliquer vous-même :"

- **Si l'utilisateur demande d'effectuer un `git pull`** :
  L'agent confirme que cette opération est autorisée et peut l'exécuter ou fournir la commande appropriée (`git pull origin develop`).

- **Si l'utilisateur demande d'effectuer un `git push`** :
  L'agent refuse fermement et rappelle que le push est réservé exclusivement au développeur humain.
