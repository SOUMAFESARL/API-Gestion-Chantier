# Project Rules: Frontend Protection Policy

## 1. Interdiction d'Édition du Code Frontend par les Outils de l'Agent (Lecture Seule / Read-Only)
- **AUCUNE ÉDITION DE CODE PAR L'AGENT :** Il est formellement interdit à l'agent d'IA d'utiliser ses outils d'écriture ou d'édition (`write_to_file`, `replace_file_content`, commandes ou scripts d'altération) pour créer, modifier ou supprimer des fichiers de code ou de configuration sur le projet frontend (`Application-Gestion-Chantier`).
- **Consultation et Audit uniquement :** L'agent peut lire, analyser, inspecter les fichiers (`view_file`), vérifier les types ou auditer, mais ne doit effectuer AUCUNE modification directe de code dans les fichiers du frontend.
- **Assistance via le chat :** Si l'utilisateur demande des changements ou des ajouts sur le frontend, l'agent doit refuser l'écriture directe dans les fichiers et fournir le code / diff dans sa réponse textuelle pour que le développeur humain l'applique lui-même.

## 2. Règles Git sur le Frontend : 'git pull' AUTORISÉ, 'git push' INTERDIT
- **`git pull` & `git fetch` PLEINEMENT AUTORISÉS :** L'agent ou l'utilisateur peut exécuter `git pull` (ex: `git pull origin develop`) et `git fetch` pour récupérer et synchroniser les mises à jour distantes sur le frontend.
- **AUCUN PUSH AUTORISÉ SUR LE FRONTEND :** Il est formellement interdit à l'agent d'exécuter `git push` (ou toute variante comme `git push origin`, `git push --force`) sur le dépôt frontend (`Application-Gestion-Chantier`).
