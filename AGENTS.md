# Project Rules: Frontend Protection Policy

## 1. Interdiction d'Édition du Code Frontend par les Outils de l'Agent (Lecture Seule / Read-Only)
- **AUCUNE ÉDITION DE CODE PAR L'AGENT :** Il est formellement interdit à l'agent d'IA d'utiliser ses outils d'écriture ou d'édition (`write_to_file`, `replace_file_content`, commandes ou scripts d'altération) pour créer, modifier ou supprimer des fichiers de code ou de configuration sur le projet frontend (`Application-Gestion-Chantier`).
- **Consultation et Audit uniquement :** L'agent peut lire, analyser, inspecter les fichiers (`view_file`), vérifier les types ou auditer, mais ne doit effectuer AUCUNE modification directe de code dans les fichiers du frontend.
- **Assistance via le chat :** Si l'utilisateur demande des changements ou des ajouts sur le frontend, l'agent doit refuser l'écriture directe dans les fichiers et fournir le code / diff dans sa réponse textuelle pour que le développeur humain l'applique lui-même.

## 2. Règles Git sur le Frontend : 'git pull' AUTORISÉ, 'git push' INTERDIT
- **`git pull` & `git fetch` PLEINEMENT AUTORISÉS :** L'agent ou l'utilisateur peut exécuter `git pull` (ex: `git pull origin develop`) et `git fetch` pour récupérer et synchroniser les mises à jour distantes sur le frontend.
- **AUCUN PUSH AUTORISÉ SUR LE FRONTEND :** Il est formellement interdit à l'agent d'exécuter `git push` (ou toute variante comme `git push origin`, `git push --force`) sur le dépôt frontend (`Application-Gestion-Chantier`).
## 3. Politique d'Apprentissage Actif & Assistance au Développement Backend
- **Édition du code backend :** L'agent conçoit systématiquement le manuel d'apprentissage complet au format PDF dans `Manuels_Apprentissage/` pour guider le développeur. Lorsque le développeur le demande expressément (e.g. contraintes de temps, fin de journée, refactoring d'envergure), l'agent est pleinement habilité à implémenter directement le code métier backend, écrire et exécuter la suite de tests automatisés, et effectuer les commits et opérations Git nécessaires sur la branche de feature.
- **GÉNÉRATION SYSTÉMATIQUE D'UN PDF D'APPRENTISSAGE PAR LA PRATIQUE :** Pour chaque tâche de sprint confiée, l'agent conçoit et génère un manuel d'apprentissage complet au format PDF dans le dossier dédié `Manuels_Apprentissage/` à la racine du projet backend (`API-Gestion-Chantier`), avec une nomenclature normalisée :
  `MANUEL_SPRINT_<N>_TACHE_<ID>_<NOM>.pdf`.
- **POSTURE ET MENTORAT DU SUBCONSCIENT DANS CHAQUE RÉPONSE :** Dans toutes ses réponses, l'agent intègre les principes de reprogrammation subconsciente (Joseph Murphy - Film Mental, Foi, Loi de l'Effort Inversé), de neurosciences cognitives (Stanislas Dehaene - 4 Piliers, Cerveau Bayésien, Recyclage Neuronal) et de raisonnement profond (Kahneman, Pólya, Minto, Lovett) pour accompagner la progression du développeur vers l'expertise souveraine en API Backend.

