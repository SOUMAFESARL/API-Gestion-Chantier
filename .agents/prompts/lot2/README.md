# Lot 2 — Back-office de la plateforme : prompts pour l'agent d'implémentation (backend)

Rédigé le 14/10/2026 par l'agent de cadrage (Claude), pour être exécuté par un autre agent
(Gemini sur Antigravity). **Toutes les décisions sont prises** : l'agent d'implémentation
n'arbitre rien, il exécute. S'il rencontre un cas que ces fichiers ne tranchent pas, il
**s'arrête et le signale au développeur** au lieu d'inventer une règle.

Le frontend a son propre dossier, construit en miroir :
`../Application-Gestion-Chantier/.agents/prompts/lot2/`. Chaque tâche backend `Bx` a sa
jumelle frontend `Fx` ; **la tâche backend se fait d'abord**, le frontend se branche ensuite
sur un contrat déjà servi et testé.

---

## 1. Ordre d'exécution — impératif

| Ordre | Backend (ce dossier) | Frontend | Tâche du plan | Pourquoi cet ordre |
|---|---|---|---|---|
| 1 | `B1_droits_superviseur.md` | `F1_role_reel.md` | 2.0 | Toutes les autres tâches s'appuient sur la séparation SUPERVISEUR / SUPPORT |
| 2 | `B2_echeance_abonnement.md` | `F2_echeance_abonnement.md` | 2.2 | L'écran existe déjà et appelle une route qui répond 405 |
| 3 | `B3_modules_client.md` | `F3_modules_client.md` | 2.3 | Petite règle serveur, gros écran |
| 4 | *(rien à faire côté serveur)* | `F4_messagerie.md` | 2.5 | Le backend est complet ; B1 a déjà posé ses droits |
| 5 | `B4_journal_plateforme.md` | `F5_journal_plateforme.md` | 2.6 | Le format de réponse change (pagination) |
| 6 | *(rien d'autre que B1)* | `F6_permissions.md` | 2.7 | Le backend est complet |
| 7 | `B5_suppression_entreprise.md` | `F7_suppression_entreprise.md` | 2.4 (US 1.1) | La plus dangereuse : en dernier, quand tout le reste est stable |
| 8 | — | `F8_cloture.md` | 2.8 | Retrait de la simulation, documentation |

La tâche **2.1** (mot de passe oublié du super-administrateur) est **déjà faite** : ne pas y
toucher.

---

## 2. Règles communes — à relire avant CHAQUE tâche

### 2.1 Ce que l'agent lit avant d'écrire

1. `AGENTS.md` (racine de ce dépôt) — règles du projet.
2. `.agents/skills/django-expert-reference/SKILL.md` — conventions Django/DRF du dépôt.
3. `.agents/skills/sprint-task-lifecycle/SKILL.md` — le cycle d'une tâche.
4. Le fichier de la tâche, **en entier**, puis chacun des fichiers de code qu'il cite.

### 2.2 Git — non négociable

```bash
git checkout develop
git pull
git checkout -b feature/lot2-<nom-court>     # nom donné dans chaque fichier de tâche
```

- **Une branche par tâche.** Ne jamais mélanger deux tâches dans une branche.
- `git add <fichiers précis>` — **jamais** `git add .` ni `git add -A` : le dépôt peut porter
  un travail en cours qui n'est pas le vôtre.
- Message de commit : `feat(platform_admin): <description>` ou `fix(...)`, en français.
- Fusion :
  ```bash
  git checkout develop
  git merge --no-ff feature/lot2-<nom-court> -m "merge: feature/lot2-<nom-court> into develop"
  git branch -d feature/lot2-<nom-court>
  ```
- **INTERDIT : `git push`.** Pousser `develop` **déploie en production** (CI puis cPanel).
  Le push du lot entier est fait **une seule fois**, par le développeur, après relecture par
  Claude (skill `revue-backend`) et vérification à l'écran. Jamais `--force`.
- Ne pas modifier `.claude/` (copie générée), ni `01_Sources_Client/`, ni les migrations
  existantes.

### 2.3 Environnement Windows de cette machine

- Python : `.venv\Scripts\python.exe` (Python 3.13). Le 3.14 du système n'est pas supporté.
- PostgreSQL 16 local, base `ccd_digital`. Schémas `public` et `demo` présents.
- Backend sur le port **8000** ; si le port est occupé (souvent par le serveur PHP d'un autre
  projet, LOGISTIC--V), **libérer le port**, ne jamais basculer sur 8001.
- PowerShell 5.1 : pas de `&&`. Pour un message de commit multi-ligne, l'écrire dans un
  fichier temporaire et faire `git commit -F <fichier>`.

### 2.4 Vérifications obligatoires avant chaque commit

```bash
.venv/Scripts/python.exe -m ruff check apps/platform_admin apps/tenants
.venv/Scripts/python.exe -m pytest apps/platform_admin/tests/ -q
.venv/Scripts/python.exe -m pytest tests/acceptation -q
```

- **Avant de commencer la tâche**, lancer ces mêmes commandes sur `develop` et **noter le
  nombre d'échecs** (la suite locale a des échecs connus, sans rapport avec ce lot, dont
  `tests/acceptation/lot10` `verrou[9]`, qui échoue sous Windows à cause des fins de ligne
  CRLF et passe sur la CI Linux). **Après la tâche, aucun échec nouveau n'est admis.** Un
  échec nouveau se corrige à sa cause ; on ne désactive jamais un test pour passer.
- La CI de production exécute `tests/acceptation/lot1` à `lot10`. Un test d'acceptation
  cassé bloque le déploiement de tout le monde.

### 2.5 Conventions de code de ce dépôt (rappel)

- `models/`, `views/`, `serializers/`, `services/` sont des **paquets**. Un `views.py` créé à
  côté du dossier `views/` est ignoré sans message.
- Logique métier dans `services/`, lecture dans `selectors/`, la vue ne fait que valider,
  appeler et répondre.
- Toute action d'écriture d'un agent de la plateforme laisse **exactement une** ligne dans
  `JournalPlateforme` (schéma public, via `journaliser_plateforme`) et, si elle modifie
  l'espace d'une entreprise, **exactement une** ligne dans le `JournalAudit` de son schéma
  (via `journaliser_tenant`). Les deux sont dans `apps/platform_admin/services/notifications.py`.
- Le Directeur Général d'une entreprise est prévenu par courriel de toute modification de son
  espace par la plateforme : `notifier_dg_action_plateforme(...)` (même fichier), envoyé après
  validation de la transaction.
- Format d'erreur du produit : `{"erreur": {"code", "message", "details", "trace_id"}}`.
  `ErreurConflit` (`apps/core/exceptions.py`) produit un 409 `conflit`. Les erreurs de
  validation DRF (`serializers.ValidationError`) produisent un 400 avec `details` par champ.
- Messages d'erreur **en français**, phrase complète, qui disent quoi faire. Ils sont donnés
  mot pour mot dans chaque tâche : les reprendre **exactement**, le frontend les affiche tels
  quels.
- Pas de commentaire qui paraphrase le code ; un commentaire dit **pourquoi**.

### 2.6 Rôles du back-office — la règle que B1 pose et que tout le lot respecte

| Rôle | Porté par | Peut |
|---|---|---|
| **SUPERVISEUR** | `is_superuser = True` | Tout |
| **SUPPORT** | `is_staff = True`, `is_superuser = False` | **Lire** tout le back-office ; **activer / désactiver un module pour un client** (geste de support courant) ; rien d'autre |

Sont réservés au superviseur : ce qui touche à **l'argent** (forfait, échéance), **à l'accès**
(suspension, réactivation, comptes administrateurs), **au paramétrage de la plateforme**
(modules du catalogue, permissions, tarifs, identité, messagerie) et **ce qui détruit**
(suppression définitive). Le contrôle se fait **côté serveur** ; le frontend ne fait que
griser les boutons.

---

## 3. Décisions déjà prises (ne pas les rediscuter)

| # | Décision |
|---|---|
| 2.2 a | La date de fin se modifie par `PATCH /admins/clients/{id}/`, qui ne touche **que** l'échéance (`date_fin`, et `fin_essai` si l'abonnement est en essai) |
| 2.2 b | La nouvelle date ne peut pas être antérieure à aujourd'hui |
| 2.2 c | Motif obligatoire, **10 caractères au moins**, journalisé |
| 2.2 d | Le DG est prévenu par courriel (sans le motif, qui est interne) |
| 2.2 e | Aucune réactivation automatique : une entreprise suspendue le reste |
| 2.3 a | Désactiver un module **conserve les données** et coupe l'accès ; confirmation à l'écran |
| 2.3 b | La confirmation d'activation dit que les rôles personnalisés n'obtiennent **aucun droit** sur le module (seuls les rôles système reçoivent leurs droits par défaut) |
| 2.3 c | Le module `projets` (socle de l'espace) **ne se désactive jamais** — refus serveur 409 |
| 2.3 d | Le DG est prévenu à l'activation comme à la désactivation (déjà le cas) |
| 2.4 a | Motif ≥ 20 caractères, journalisé ; nom technique retapé ; `public` et `demo` protégés ; interrupteur `SUPPRESSION_ENTREPRISE_ACTIVEE` **éteint par défaut** |
| 2.4 b | Seule une entreprise **déjà suspendue** peut être supprimée |
| 2.4 c | Sauvegarde automatique du schéma (`pg_dump`) avant suppression, conservée 30 jours ; **si la sauvegarde échoue, la suppression est refusée** |
| 2.4 d | Le DG reçoit un courriel **avant** la suppression, sans le motif |
| 2.5 | L'écran messagerie montre la configuration réellement utilisée (`effectif.source`) |
| 2.6 | Journal : filtres période + agent + entreprise + action, pagination serveur, export CSV/PDF côté frontend |
| 2.7 | Permissions : lecture pour tous ; création, modification, rattachement et suppression réservés au superviseur, suppression confirmée avec son impact |
| 2.8 | Retrait de la simulation du back-office |

Note de cadrage sur 2.7 : la discussion avait laissé au SUPPORT le rattachement des
permissions aux modules. Il lui est finalement **retiré** : c'est du paramétrage de la
plateforme, et l'écran du paramétrage est déjà en lecture seule pour le SUPPORT. Une règle
unique est plus sûre qu'une exception.

---

## 4. Fin du lot

Quand les huit tâches sont fusionnées dans `develop` (sans push) :

1. Lister les commits du lot : `git log --oneline develop ^origin/develop`.
2. Écrire au développeur un compte rendu : par tâche, ce qui est livré, les tests ajoutés, le
   nombre d'échecs avant / après, ce qui n'a pas été vérifié.
3. **S'arrêter.** La relecture (Claude, skill `revue-backend`), la vérification à l'écran et
   le push sont faits par le développeur.
