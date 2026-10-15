# Chantier « droits » — rôles, modules et permissions : prompts pour l'agent d'implémentation

Rédigé le 16/10/2026 par l'agent de cadrage (Claude), après validation du développeur
(recommandations R0 à R11, toutes retenues). **Toutes les décisions sont prises** : en cas de doute,
s'arrêter et demander, ne jamais inventer une règle.

Jumeau frontend : `../Application-Gestion-Chantier/.agents/prompts/droits/`.

> **Prérequis** : `develop` du backend contient `6ec1880` (B1, poussé et déployé le 16/10) et
> `bf3ae8d` (garde `acces_par_defaut`, fusionnée en local). Vérifier :
> `git log --oneline develop | grep -E "droits-b1|garde-acces"` → deux lignes.

---

## 1. Ce que le chantier livre

Le backend sait déjà tout faire (matrice dynamique, portée, B-08, catalogue). Le frontend, lui :

- affiche **douze modules écrits en dur** (`MODULES_CCD`), dont sept n'existent pas côté serveur —
  toute écriture d'un rôle échoue (« Module inconnu : 'finance' ») ;
- ne lit que des **niveaux** (lecture / saisie / validation), jamais les **codes** de permission
  (`projets.creer`, `projets.voir_montants`…) ;
- donne à tout non-DG une portée « personne » : l'AD et le DO ne voient que leurs chantiers ;
- réserve tout l'écran des rôles au DG, alors que l'AD a `administration.roles_gerer` ;
- côté super admin, édite un « accès par défaut » qui, traduit par le serveur, **effaçait les
  permissions fines du module** (garde posée le 16/10, `bf3ae8d`).

Et le service de catalogue du back-office (backend) travaille encore sur l'**ancien** référentiel
de permissions (`accounts.Permission`, codes `LECTURE`…) au lieu du catalogue
(`catalogue.CataloguePermission`, codes `projets.lire`…) : rattacher une vraie permission échoue,
la supprimer aussi. C'est B2.

## 2. Ordre d'exécution — une seule phase, sans arrêt

Décision du développeur : **tout s'enchaîne du premier au dernier**, sans point de relecture. La
relecture de Claude a lieu à la fin, avant le push.

| Ordre | Tâche | Dépôt | Objet |
|---|---|---|---|
| 1 | `B2_catalogue.md` | backend | Le service du back-office travaille sur le catalogue |
| 2 | `F1_droits_profil.md` | frontend | Les droits lus dans les codes du profil ; portée entreprise |
| 3 | `F2_gestes_par_codes.md` | frontend | Chaque geste des projets suit son code (D-08) |
| 4 | `F3_montants.md` | frontend | Les montants n'apparaissent qu'à qui a `projets.voir_montants` |
| 5 | `F4_ecran_roles.md` | frontend | Matrice dynamique, cases par permission, raccourcis, règles DG / AD |
| 6 | `F5_portee.md` | frontend | La portée d'un rôle : badge, choix, changement confirmé |
| 7 | `F6_modules_super_admin.md` | frontend | Modules du back-office : ordre, icône, permissions rattachées |
| 8 | `F7_permissions_super_admin.md` | frontend | Permissions du back-office alignées sur B2 |
| 9 | `F8_cloture.md` | frontend | Plan d'alignement et compte rendu |

`PROMPT_DE_LANCEMENT.md` donne le message à coller dans Antigravity.

## 3. Règles communes

**Identiques aux lots 2 à 4** : relire `../lot2/README.md` §2. En résumé :

- branche `feature/droits-<nom>` partie de `develop` à jour ; `git add <fichiers>` seulement,
  **jamais** `git add .` ni `-A` ; fusion `--no-ff` dans `develop` ; branche supprimée ensuite ;
- **jamais `git push`** — un push de `develop` déploie en production (backend et frontend) ;
- messages d'erreur et libellés en français, **mot pour mot** ceux des tâches ;
- les erreurs se **lèvent** (`ValidationError`, `PermissionDenied`, `RequeteRefusee`) ; jamais
  `return Response({"detail": …})`.

**Garde-fou des tests (backend), avant et après chaque tâche backend :**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/acceptation/lot1 tests/acceptation/lot2 tests/acceptation/lot3 tests/acceptation/lot4 -q -p no:cacheprovider
```

Ce sont les seuls tests qui conditionnent le déploiement (CI, commit `84be147`). **177 passent
aujourd'hui. Un seul échec après la tâche = s'arrêter, ne pas fusionner, le signaler.** Les tests
d'acceptation ne se modifient jamais sans l'accord écrit du développeur.

La machine manque de mémoire : **une seule commande lourde à la fois** (pas de `pytest` en même
temps qu'un `npm run build`). Si PostgreSQL s'arrête (« connection timeout », « out of memory ») :
`Start-Service postgresql-x64-16`, puis relancer.

## 4. Décisions validées par le développeur (15 et 16/10/2026)

| # | Décision |
|---|---|
| R0 | Le défaut serveur passe en premier. B1 (Claude, en production) ; B2 (ce dossier) |
| R2 | Les modules d'un écran viennent **du serveur** (`GET /modules/`), plus de liste en dur |
| R3b | La matrice de la page est un **résumé en lecture** (niveaux). La modale édite **permission par permission**, avec des raccourcis Aucun / Lecture / Saisie / Validation. L'écran envoie la **liste complète** `permissions` |
| R4 | Portée : badge, choix à la création, changement **DG seul**, confirmé (personnes touchées ; passer en « entreprise » désactive leurs affectations de chantier) |
| R5 | Rôle DG en lecture seule pour tous ; rôles système modifiables par le DG seul ; l'AD ne voit que les permissions qu'il détient ; le module `administration` n'apparaît jamais ; les avertissements du serveur s'affichent |
| R6 | L'option `supprimer_collaborateurs` de la suppression d'un rôle **n'est pas exposée** |
| R7 | Les droits du frontend se lisent dans `permissions` (codes) et `portee` du profil ; `ENTREPRISE` = tous les chantiers ; chaque geste fin suit son code |
| R8 | Back-office : un module montre son ordre, son icône et ses permissions ; les rattacher passe par `PATCH /admins/modules/{id}/permissions/`, avec confirmation de la propagation |
| R9 | L'écran des permissions du back-office est aligné sur ce que B2 accepte |
| R10 | Les modèles de rôles (`ModeleRole`) sont **hors périmètre** |
| R11a | B1 poussé dès qu'il était prêt (fait le 16/10, CI verte, production à jour) |

Décisions prises par Claude au cadrage, dans le mandat donné par le développeur (« pour le reste tu
prends toutes les décisions ») :

| # | Décision | Pourquoi |
|---|---|---|
| D1 | Un AD qui ouvre un rôle portant une permission **qu'il ne détient pas** n'en modifie pas la matrice (lecture seule, message) ; intitulé et description restent modifiables | B-08 compare **toute** la liste envoyée aux droits de l'AD : la renvoyer échoue (403), l'omettre retire la permission au rôle |
| D2 | Une permission `x.action` ne se rattache **qu'au module `x`** | Les 23 permissions du catalogue suivent déjà cette règle ; c'est elle qui donne son sens au préfixe |
| D3 | Les codes de permission restent **en minuscules**, tels que le REGISTRE les écrit | Le service les passait en majuscules : `projets.lire` devenait `PROJETS.LIRE`, introuvable |
| D4 | `/parametres/roles` s'ouvre à `administration.roles_gerer`, `/parametres/collaborateurs` à `administration.collaborateurs_voir` ; `/abonnement` et `/parametres/configuration` restent au DG | L'AD détient les deux premiers (B-04) ; l'abonnement n'est pas dans ce chantier |
| D5 | Les écrans ne changent pas de type pour les montants : une règle `peutVoirMontants` décide de leur affichage | Le serveur **retire** les clés de montant ; l'adaptateur les remplace par 0, et un 0 affiché est faux |
