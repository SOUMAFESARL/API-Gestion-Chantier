# Message à coller dans Antigravity pour lancer le lot 2

Ouvrir dans Antigravity un espace de travail qui contient **les deux dépôts** :
`05_Developpement/API-Gestion-Chantier` et `05_Developpement/Application-Gestion-Chantier`.
Puis coller le message ci-dessous, **une tâche à la fois** : remplacer `<TACHE>` par la ligne
suivante de l'ordre d'exécution, et n'envoyer la suivante qu'après avoir lu le compte rendu de la
précédente.

Ordre : `B1` → `F1` → `B2` → `F2` → `B3` → `F3` → `F4` → `B4` → `F5` → `F6` → `B5` → `F7` → `F8`.

---

```text
Tu travailles sur CCD Digital, un SaaS de gestion de chantier BTP : un backend Django
(API-Gestion-Chantier) et un frontend Next.js (Application-Gestion-Chantier).

Ta mission : exécuter UNE tâche du lot 2, la tâche <TACHE>.

Avant d'écrire la moindre ligne :
1. Lis API-Gestion-Chantier/.agents/prompts/lot2/README.md en entier.
2. Si la tâche commence par F, lis aussi Application-Gestion-Chantier/.agents/prompts/lot2/README.md
   en entier.
3. Lis le fichier de la tâche en entier (B* dans le dossier du backend, F* dans celui du
   frontend), puis chacun des fichiers de code qu'il cite.
4. Lis le AGENTS.md (backend) ou le CLAUDE.md (frontend) du dépôt concerné, et les skills
   qu'indique le README.

Ensuite, avant d'implémenter, écris-moi en quelques lignes : ce que tu as compris de la tâche, les
fichiers que tu vas toucher dans l'ordre, et les deux pièges principaux. Attends mon accord.

Règles absolues :
- Toutes les décisions sont prises dans ces fichiers. N'invente aucune règle métier. Si un cas
  n'est pas tranché, arrête-toi et pose-moi la question.
- Une branche feature par tâche, partie de develop à jour. git add fichier par fichier, jamais
  "git add ." ni "-A".
- N'exécute JAMAIS git push : pousser develop déploie en production, dans les deux dépôts.
- Aucun test désactivé, aucune exemption ESLint ajoutée pour faire passer.
- N'écris jamais d'identifiant ni de mot de passe dans un fichier ou dans ton compte rendu.
- À la fin : vérifications de la section « Définition de terminé », fusion --no-ff dans develop,
  suppression de la branche, puis compte rendu : livré, tests ajoutés, échecs avant/après,
  vérifié à l'écran ou non. Puis arrête-toi.
```

---

## Après chaque tâche

- Lire le compte rendu. Une case non cochée de la « Définition de terminé » = la tâche n'est pas
  finie : renvoyer Gemini dessus avant de passer à la suivante.
- Après **B5 / F7 / F8**, demander à Claude une relecture du lot (skills `revue-backend` et
  `revue-frontend`) avant tout push.
- Le push des deux `develop` est **une seule opération, faite par le développeur** : il déploie en
  production.
