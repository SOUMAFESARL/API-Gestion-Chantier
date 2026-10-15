# Message à coller dans Antigravity pour lancer le lot 4

Même espace de travail qu'aux lots précédents (les deux dépôts, plus `Gestion_Chantier/04_Conception/`
en lecture). **Une tâche à la fois**, dans cet ordre, phase A puis phase B **sans arrêt entre les
deux** (décision du développeur) :

`B1` → `F1` → `B2` → `F2` → `F3` → `B3` → `F4` → `B4` → `F5` → `B5` → `F6` → `B6` → `F7` → `F8`.

Prérequis : le lot 3 est entièrement fusionné dans les deux `develop`.

---

```text
Tu travailles sur CCD Digital, un SaaS de gestion de chantier BTP : un backend Django
(API-Gestion-Chantier) et un frontend Next.js (Application-Gestion-Chantier).

Ta mission : exécuter UNE tâche du lot 4, la tâche <TACHE>.

Avant d'écrire la moindre ligne :
1. Lis API-Gestion-Chantier/.agents/prompts/lot4/README.md en entier, puis
   API-Gestion-Chantier/.agents/prompts/lot2/README.md §2 (règles communes, toujours valables).
2. Si la tâche commence par F, lis aussi Application-Gestion-Chantier/.agents/prompts/lot4/README.md.
3. Lis le fichier de la tâche en entier (B* côté backend, F* côté frontend), puis chacun des
   fichiers de code qu'il cite.
4. Lis le AGENTS.md (backend) ou le CLAUDE.md (frontend) du dépôt concerné, et les skills
   qu'indique le README.

Ensuite, avant d'implémenter, écris-moi en quelques lignes : ce que tu as compris de la tâche, les
fichiers que tu vas toucher dans l'ordre, et les deux pièges principaux. Attends mon accord.

Règles absolues :
- Toutes les décisions sont prises dans ces fichiers. N'invente aucune règle métier. Si un cas
  n'est pas tranché, ou si un test d'acceptation (tests/acceptation/) devrait changer, arrête-toi
  et pose-moi la question.
- Une branche feature par tâche, partie de develop à jour. git add fichier par fichier, jamais
  "git add ." ni "-A".
- N'exécute JAMAIS git push : pousser develop déploie en production, dans les deux dépôts.
- Aucun test désactivé, aucune exemption ESLint ajoutée pour faire passer.
- N'écris jamais d'identifiant ni de mot de passe dans un fichier ou dans ton compte rendu.
- À la fin : vérifications de la « Définition de terminé », fusion --no-ff dans develop,
  suppression de la branche, puis compte rendu : livré, tests ajoutés, échecs avant/après,
  vérifié à l'écran ou non. Puis arrête-toi.
```

---

## Après le lot

Relecture par Claude (`revue-backend`, `revue-frontend`), puis push par le développeur, **après**
ceux des lots 2 et 3. Ce lot ajoute trois migrations au module projets (B4, B5) : les pousser
seules, et contrôler le déploiement (migrate) avant d'enchaîner.
