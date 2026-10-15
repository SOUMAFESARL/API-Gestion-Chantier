# Message à coller dans Antigravity pour lancer le lot 3

Même espace de travail qu'au lot 2 : les **deux dépôts** ouverts
(`05_Developpement/API-Gestion-Chantier` et `05_Developpement/Application-Gestion-Chantier`).
**Ajouter aussi le dossier `Gestion_Chantier/04_Conception/`** (lecture seule) : B3 s'appuie sur le
MLD v1.7, qui vit hors des deux dépôts.
**Une tâche à la fois** : remplacer `<TACHE>` par la suivante de l'ordre, et n'envoyer la suivante
qu'après avoir lu le compte rendu de la précédente.

Ordre : `B1` → `F1` → `B2` → `F2` → `F3` → `B3` → `F4` → `F5` → `F6` → `F7` → `F8`.

Avant `B1` : le lot 2 doit être entièrement fusionné dans les deux `develop` (c'est le cas au
15/10/2026). Le relire et le pousser n'est **pas** un prérequis du lot 3 ; ne pas mélanger les
deux pushs pour autant (voir plus bas).

---

```text
Tu travailles sur CCD Digital, un SaaS de gestion de chantier BTP : un backend Django
(API-Gestion-Chantier) et un frontend Next.js (Application-Gestion-Chantier).

Ta mission : exécuter UNE tâche du lot 3, la tâche <TACHE>.

Avant d'écrire la moindre ligne :
1. Lis API-Gestion-Chantier/.agents/prompts/lot3/README.md en entier, puis
   API-Gestion-Chantier/.agents/prompts/lot2/README.md §2 (règles communes, toujours valables).
2. Si la tâche commence par F, lis aussi Application-Gestion-Chantier/.agents/prompts/lot3/README.md.
3. Lis le fichier de la tâche en entier (B* dans le dossier du backend, F* dans celui du
   frontend), puis chacun des fichiers de code qu'il cite.
4. Pour B3, lis aussi le MLD : Gestion_Chantier/04_Conception/architecture_base_donnees/MLD_CCD_Digital.md,
   §4.1 et §4.1.1.
5. Lis le AGENTS.md (backend) ou le CLAUDE.md (frontend) du dépôt concerné, et les skills
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

- Une case non cochée de la « Définition de terminé » = la tâche n'est pas finie.
- Après `F8`, demander à Claude la relecture du lot 3 (`revue-backend`, `revue-frontend`).
- **Ordre des pushs** : le lot 2 d'abord (relu, vérifié à l'écran, poussé, déploiement contrôlé),
  le lot 3 ensuite. Pousser les deux d'un coup mettrait en production deux lots qu'on ne saurait plus
  distinguer si quelque chose casse — et B3 ajoute une migration au schéma `public`.
