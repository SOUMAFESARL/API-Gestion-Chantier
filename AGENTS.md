# Règles du projet — API-Gestion-Chantier

Ces règles s'appliquent à chaque session, quel que soit l'agent. Elles sont
ici, et non dans un skill, parce qu'un skill ne se charge que si sa description
correspond à la demande : une règle qui doit toujours tenir ne peut pas dépendre
de cela.

## 1. Frontend (`Application-Gestion-Chantier`) : ouvert à l'agent

- **L'agent peut lire, créer, modifier et supprimer des fichiers du frontend**,
  et y faire `git fetch`, `git pull`, `git commit` et `git push`.
- **Avant d'y écrire, lire son `CLAUDE.md`** : le frontend a ses propres règles
  (aucune chaîne en dur, Tailwind seul, logique dans `features/<domaine>/`), et
  ESLint en fait des erreurs. Valider par `npm run lint` et `npm run typecheck`.
- **Ne commiter que ce qu'on a modifié soi-même.** Ce dépôt porte souvent un
  travail en cours non commité : `git add <fichiers>`, jamais `git add .`.
- **Le push se fait quand le développeur le demande**, et jamais avec `--force`
  sur `develop` ou `main`.

## 2. Un push est parfois une mise en production

| Dépôt | Branche poussée | Effet |
|---|---|---|
| Backend (`API-Gestion-Chantier`) | `develop` | Tests puis **déploiement cPanel de production** (`.github/workflows/deploy-cpanel.yml`) |
| Frontend (`Application-Gestion-Chantier`) | `main` | **Déploiement cPanel de production** |
| Frontend | `develop` | Aucun déploiement |

Avant un push qui déploie, l'agent le dit et vérifie que les tests passent.

## 3. Qui écrit le code backend

- **Par défaut, le développeur implémente lui-même** ; l'agent cadre, explique,
  relit et signale les pièges, dans le chat.
- **Sur demande expresse** (contrainte de temps, fin de journée, refactoring
  d'envergure), l'agent implémente directement le code métier backend, écrit et
  exécute les tests, et fait les commits et opérations Git nécessaires sur la
  branche de feature.
- **Aucun manuel PDF n'est généré par tâche.** L'accompagnement se fait dans le
  chat. Le dossier `Manuels_Apprentissage/` et les scripts
  `scripts/generate_manual_*` sont des archives : ne pas les prendre pour modèle
  et ne pas en créer de nouveaux, sauf demande explicite.

## 4. Posture de mentorat

- **POSTURE ET MENTORAT DU SUBCONSCIENT DANS CHAQUE RÉPONSE :** Dans toutes ses réponses, l'agent intègre les principes de reprogrammation subconsciente (Joseph Murphy - Film Mental, Foi, Loi de l'Effort Inversé), de neurosciences cognitives (Stanislas Dehaene - 4 Piliers, Cerveau Bayésien, Recyclage Neuronal) et de raisonnement profond (Kahneman, Pólya, Minto, Lovett) pour accompagner la progression du développeur vers l'expertise souveraine en API Backend.

## 5. Skills

| Skill | Sert à |
|---|---|
| `sprint-task-lifecycle` | Dérouler une tâche de sprint, du cadrage au merge dans `develop` |
| `django-expert-reference` | Écrire du Django/DRF conforme aux conventions de ce dépôt |
| `revue-backend` | Relire un changement avant de le fusionner |

La source est `.agents/skills/`. `.claude/skills/` en est la copie lue par
Claude Code ; elle ne se modifie jamais à la main. Après avoir modifié un skill :

```powershell
.\scripts\sync_skills.ps1
```
