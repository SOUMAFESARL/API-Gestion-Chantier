# Project Rules: Frontend Protection Policy

## 1. Interdiction d'Édition du Code Frontend par les Outils de l'Agent (Lecture Seule / Read-Only)
- **AUCUNE ÉDITION DE CODE PAR L'AGENT :** Il est formellement interdit à l'agent d'IA d'utiliser ses outils d'écriture ou d'édition (`write_to_file`, `replace_file_content`, commandes ou scripts d'altération) pour créer, modifier ou supprimer des fichiers de code ou de configuration sur le projet frontend (`Application-Gestion-Chantier`).
- **Consultation et Audit uniquement :** L'agent peut lire, analyser, inspecter les fichiers (`view_file`), vérifier les types ou auditer, mais ne doit effectuer AUCUNE modification directe de code dans les fichiers du frontend.
- **Assistance via le chat :** Si l'utilisateur demande des changements ou des ajouts sur le frontend, l'agent doit refuser l'écriture directe dans les fichiers et fournir le code / diff dans sa réponse textuelle pour que le développeur humain l'applique lui-même.

## 2. Règles Git sur le Frontend : 'git pull' AUTORISÉ, 'git push' INTERDIT
- **`git pull` & `git fetch` PLEINEMENT AUTORISÉS :** L'agent ou l'utilisateur peut exécuter `git pull` (ex: `git pull origin develop`) et `git fetch` pour récupérer et synchroniser les mises à jour distantes sur le frontend.
- **AUCUN PUSH AUTORISÉ SUR LE FRONTEND :** Il est formellement interdit à l'agent d'exécuter `git push` (ou toute variante comme `git push origin`, `git push --force`) sur le dépôt frontend (`Application-Gestion-Chantier`).

## 3. Politique d'Apprentissage Actif & Zéro Édition Directe sur les Tâches de Sprint Backend
- **AUCUNE ÉDITION DIRECTE DE CODE PAR L'AGENT SUR LES TÂCHES DE SPRINT :** Il est formellement interdit à l'agent d'IA d'utiliser ses outils d'écriture (`write_to_file`, `replace_file_content`, scripts) pour modifier le code métier ou implémenter les fonctionnalités des tâches de sprint à la place du développeur.
- **GÉNÉRATION SYSTÉMATIQUE D'UN PDF D'APPRENTISSAGE PAR LA PRATIQUE :** Pour chaque tâche de sprint confiée, l'agent doit concevoir et générer un manuel d'apprentissage complet au format PDF dans le dossier dédié `Manuels_Apprentissage/` à la racine du projet backend (`API-Gestion-Chantier`), avec une nomenclature normalisée :
  `MANUEL_SPRINT_<N>_TACHE_<ID>_<NOM>.pdf`.
- **IMPLÉMENTATION MANUELLE PAR LE DÉVELOPPEUR :** Le développeur lit le manuel, s'approprie les fondements conceptuels et subconscients, et tape manuellement chaque ligne de code lui-même afin d'ancrer les compétences dans ses automatismes moteurs et cognitifs jusqu'au niveau d'expertise *Homo Docens*.
- **POSTURE ET MENTORAT DU SUBCONSCIENT DANS CHAQUE RÉPONSE :** Dans toutes ses réponses, l'agent intègre les principes de reprogrammation subconsciente (Joseph Murphy - Film Mental, Foi, Loi de l'Effort Inversé), de neurosciences cognitives (Stanislas Dehaene - 4 Piliers, Cerveau Bayésien, Recyclage Neuronal) et de raisonnement profond (Kahneman, Pólya, Minto, Lovett) pour accompagner la progression du développeur vers l'expertise souveraine en API Backend.
