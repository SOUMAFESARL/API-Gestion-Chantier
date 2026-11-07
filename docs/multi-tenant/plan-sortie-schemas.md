# Sortie du multi-schéma — plan par lots

| | |
|---|---|
| **Statut** | Décisions prises le 07/11/2026 (§8) — ordre de réalisation à valider (§11) |
| **Date** | vendredi 6 novembre 2026 |
| **Décision** | Abandonner « un schéma PostgreSQL par entreprise » (django-tenants) pour **un schéma unique, chaque ligne portant son `entreprise_id`**, avec une **structure native de Django** : aucune bibliothèque tierce de multi-entreprise, plus de notion de « tenant », plus d'en-tête `X-Tenant`, plus d'admin Django |
| **Portée** | Backend seulement. Le contrat d'API ne change pas : le frontend n'est pas touché |
| **Charge estimée** | 27 à 31 jours-développeur, bascule comprise (estimation d'avant-lot, à affiner au lot 0) |
| **Données de production** | **Aucune entreprise n'a de données réelles** (réponse à Q1, 06/11/2026) : pas de fusion, la base repart de zéro (§5) |

---

## 1. En une page

On passe d'une isolation **par construction** (chaque entreprise a ses tables) à une isolation **par filtrage** (toutes les entreprises partagent les tables, chaque ligne dit à qui elle appartient).

**Le risque principal change de nature.** Aujourd'hui, une erreur de contexte *ferme la porte* : la requête tombe sur `public` et ne trouve rien. Demain, un filtre oublié *l'ouvrirait* : la requête rendrait les lignes de toutes les entreprises, sans erreur. Tout le plan est construit pour que la panne continue de fermer la porte, par **trois couches indépendantes** :

1. **L'ORM refuse de travailler hors contexte.** Toute requête sur un modèle d'entreprise sans entreprise active lève une erreur, au lieu de tout rendre.
2. **PostgreSQL filtre de lui-même** (Row Level Security, forcée) : même une requête SQL brute ou un filtre oublié ne voit que l'entreprise active.
3. **Une suite de tests d'étanchéité** appelle chaque route avec le compte d'une entreprise sur les objets d'une autre, à chaque commit.

**Ce qu'on gagne :** une seule migration par déploiement (au lieu d'une par client), une inscription en quelques secondes (des insertions au lieu de 193 migrations), un pilotage de la plateforme par simples requêtes, la fin de l'écart E1, du registre global des e-mails et du `SET search_path`.

**Ce qui rend le chantier faisable :** aucune entreprise n'a de données réelles en production. Il n'y a **rien à fusionner** : la base de production repart de zéro avec le nouveau modèle, et les migrations recommencent à `0001` dans chaque application. Le jeu `peupler_donnees_test`, régénéré dans le nouveau modèle, sert de base de comparaison : mêmes comptes, mêmes écrans, mêmes chiffres.

---

## 2. État des lieux (mesuré le 06/11/2026)

| Élément | Volume | Conséquence |
|---|---|---|
| Applications côté entreprise | 10 (`projets`, `chantier`, `ged`, `pilotage`, `tiers`, `notifications`, `onboarding`, plus `accounts`, `audit`, `core` des deux côtés — écart E1) | Toutes passent dans le schéma unique |
| Modèles côté entreprise | 46, plus 9 tables de liaison M2M | Chacun reçoit `entreprise_id` |
| Clés primaires non UUID | 1 : `audit.JournalAudit` (entier) | Sans conséquence : la base repart de zéro (§5) |
| Contraintes d'unicité | 39, dont environ 13 « globales à l'entreprise » | Ces 13 s'élargissent à `entreprise_id` (§4.4) |
| `schema_context(...)` | 159 occurrences dans 54 fichiers | Remplacées par `contexte_entreprise(...)` |
| `connection.schema_name`, `set_tenant`, `request.tenant` | 22 + 16 + 11 occurrences | Remplacées par l'entreprise du contexte |
| Fichiers qui importent `django_tenants` | 68 | Tous revus ; le paquet disparaît au lot 8 |
| SQL brut (`cursor.execute`) | 54 occurrences dans 6 fichiers | Revus un par un ; la RLS les couvre |
| Tâches Celery | 11, qui reçoivent un `schema_name` | Reçoivent un `entreprise_id` |
| Commandes de gestion | 23 | Une option `--entreprise` explicite |
| Fichiers stockés | Clé `{schema}/projets/…` enregistrée en base | **Aucun fichier à déplacer** : les clés existantes restent valides |
| Tables en double (E1) | 18 | Disparaissent |

---

## 3. Ce qui change, ce qui ne change pas

| Disparaît | Apparaît | Ne change pas |
|---|---|---|
| django-tenants, `Domaine`, `TenantSyncRouter`, `migrate_schemas` | `ModeleEntreprise` (FK `entreprise` sur chaque modèle métier) | Les URL et les réponses de l'API, hormis les champs `schema` / `schema_name` (deviennent `entreprise`) |
| L'en-tête `X-Tenant`, le vocabulaire « tenant » (`apps/tenants` devient `apps/entreprises`) | Le claim `entreprise` du jeton, à la place de `schema` | |
| L'admin Django (`django.contrib.admin`, `/admin/`, l'option `--acces-django`) | | |
| Le middleware de résolution de schéma | Le contexte d'entreprise (`contextvars`) | Les UUID de toutes les lignes |
| Le provisionnement en trois transactions et sa compensation (MLD §7.5) | Le gestionnaire ORM qui refuse le hors-contexte | Les clés des fichiers stockés |
| `registre_email` (l'e-mail devient unique dans `utilisateur`) | Les politiques RLS de PostgreSQL | Le journal d'audit immuable (Socle §2.4) |
| L'écart E1 (18 tables en double) | La suite de tests d'étanchéité | La suppression logique (Socle §3.1) |
| `DROP SCHEMA` pour supprimer un client | La comparaison du claim du jeton à l'utilisateur (sécurité JWT §5.2) | |

---

## 4. Architecture cible

### 4.1 Le modèle de données

- **`entreprise_cliente` reste**, sans `TenantMixin`. La colonne `schema_name` devient `slug` : elle sert encore aux clés de fichiers et aux URL lisibles.
- **Tout modèle métier hérite de `ModeleEntreprise(ModeleBase)`** : une FK `entreprise` (`on_delete=PROTECT`, indexée, non nulle).
- **Même les tables « enfants » portent `entreprise_id`** (un `Element` porte celui de son `Projet`). C'est une redondance assumée : la RLS filtre table par table, sans jointure, et une incohérence parent-enfant devient détectable par une contrainte (§4.4).
- **`Utilisateur`** : `entreprise` **nullable** — nulle pour le personnel de CCD Digital (super admin, support). L'e-mail est unique sur toute la plateforme, comme le registre global le garantit déjà : `registre_email` disparaît.
- **Rôles et permissions** : `role.entreprise` — chaque entreprise garde ses rôles, copiés à l'inscription comme aujourd'hui.
- **Copies locales `accounts.Module` / `accounts.Permission`** : **supprimées** (décision Q3). Le catalogue global fait foi ; `RoleModulePermission` ne pointe plus que vers lui.

### 4.2 Le contexte d'entreprise

- `apps/core/contexte.py` : une variable de contexte (`contextvars`), un gestionnaire `with contexte_entreprise(entreprise_id): …` et une fonction `entreprise_courante()`.
- **Il est posé par l'authentification**, pas par un middleware qui lit un jeton non vérifié : une classe dérivée de `JWTAuthentication` vérifie le jeton, **compare son claim `entreprise` à `utilisateur.entreprise_id`** (la barrière de la sécurité JWT §5.2, enfin explicite) puis active le contexte.
- **Celery** : chaque tâche reçoit `entreprise_id` et ouvre le contexte — c'est le patron actuel de `schema_context`, transposé mécaniquement.
- **Commandes** : `--entreprise <slug>` explicite ; sans elle, la commande travaille en portée plateforme, et le dit.
- **Portée plateforme** : `with portee_plateforme(motif="…"):` pour le code de l'éditeur qui traverse les entreprises (administration, tâches planifiées, statistiques). Chaque usage est nommé, journalisé, et relu en revue.

### 4.3 L'isolation en trois couches

**Couche 1 — l'ORM ferme la porte.** `ManagerEntreprise`, gestionnaire par défaut de tout `ModeleEntreprise` :

- filtre sur l'entreprise du contexte ;
- **lève `HorsContexteEntreprise`** quand aucune entreprise n'est active et qu'on n'est pas en portée plateforme — jamais « tout » ;
- `save()` remplit `entreprise` depuis le contexte et refuse une valeur différente.

C'est le principe de la bibliothèque django-scopes (*fail closed*), **écrit nous-mêmes** en une centaine de lignes : la structure reste native de Django (décision Q7).

**Les deux gestionnaires sont cloisonnés.** `objects` et `tous_objets` (25 usages, dont la numérotation des projets) filtrent tous deux sur l'entreprise du contexte ; les 4 appels directs à `_base_manager`, qui ne filtre jamais, sont relus un par un au lot 3. Les verrous consultatifs et les clés de cache indexés par `schema_name` passent à l'`entreprise_id`.

**Couche 2 — PostgreSQL filtre de lui-même.** Sur chaque table métier :

```sql
ALTER TABLE projet ENABLE ROW LEVEL SECURITY;
ALTER TABLE projet FORCE ROW LEVEL SECURITY;   -- s'applique aussi au propriétaire des tables
CREATE POLICY isolation_entreprise ON projet
  USING (entreprise_id = nullif(current_setting('ccd.entreprise_id', true), '')::uuid)
  WITH CHECK (entreprise_id = nullif(current_setting('ccd.entreprise_id', true), '')::uuid);
-- Pas de clause « plateforme » : la portée plateforme passe par le rôle ccd_plateforme (BYPASSRLS).
```

- Le contexte Python pose `ccd.entreprise_id` sur la connexion `default`, et **le retire en fin de requête et de tâche**. Avec `CONN_MAX_AGE`, une connexion sert plusieurs requêtes : le retrait est obligatoire, et une connexion sans réglage **ne voit rien**.
- **Trois rôles PostgreSQL** (Q5 : on dispose d'un superutilisateur, hypothèse à confirmer sur le serveur) : `ccd_app`, **non** superutilisateur et sans `BYPASSRLS`, pour l'application ; `ccd_plateforme`, avec `BYPASSRLS`, pour la seule portée plateforme ; le superutilisateur, pour les migrations uniquement. **`ccd_plateforme` se prend par `SET ROLE`** sur la connexion de l'application, le temps de la portée (arbitrage du 07/11/2026, lot 4) : une seconde connexion Django aurait sorti ces requêtes des `transaction.atomic()` et des `select_for_update` ouverts sur la première. Côté sécurité, rien ne change : la RLS par réglage de session protège du filtre oublié, pas de l'injection SQL, qui peut changer le réglage elle-même.
- **Garde-fou :** un test échoue si `current_user` est superutilisateur ou possède `BYPASSRLS` sur la connexion `default`.

**Couche 3 — les tests d'étanchéité.** Deux entreprises peuplées par `peupler_donnees_test`. Pour **chaque route** de l'URLconf (introspection, pas une liste écrite à la main) :

- le compte de A appelle la route sur les identifiants de B : la réponse est 403 ou 404, et aucun identifiant de B n'apparaît dans le corps ;
- les listes de A ne contiennent aucune ligne de B ;
- toute requête ORM hors contexte lève `HorsContexteEntreprise`.

C'est **la seule suite de tests obligatoire pendant la suspension des tests** (décision du 29/10/2026) : elle tourne en CI avant tout déploiement.

### 4.4 Les contraintes d'unicité

Les 39 contraintes se rangent en deux familles :

- **Déjà portées par un parent** (`element` par `projet`, `membre` par `equipe`…) : l'unicité vaut dans le parent, qui appartient à une seule entreprise. **Inchangées.**
- **Globales à l'entreprise** : elles **gagnent `entreprise_id`**. `Role.code`, `MotifReport.code`, `Projet.reference`, `ReferentielEntreprise.code`, `ExceptionCalendrier.date`, `SemaineType`, `ParametresDocuments`, `ProgressionConfiguration`, `EtapeConfiguration`, `ValeurListeEntreprise` (branche « liste plateforme »), plus `Module.code` et `Permission.code` si on les garde.
- **`Utilisateur.email`** devient unique sur toute la plateforme (ce que le registre garantit déjà).

S'y ajoute une **cohérence parent-enfant** : une clé étrangère composite `(projet_id, entreprise_id) → projet(id, entreprise_id)` sur les enfants directs du projet. Un élément ne peut alors pas pointer vers le projet d'une autre entreprise, même par erreur de code.

### 4.5 Index

`entreprise_id` en tête des index composites sur les filtres chauds : listes de projets, rapports par date, affectations. Chaque lot se mesure avec `mesurer_requetes` et `EXPLAIN` ; la RLS ajoute une condition par table, négligeable avec ces index.

### 4.6 Journal d'audit

`journal_audit.entreprise_id` **nullable** (nul : action de la plateforme), renseigné à l'insertion depuis le contexte. Son immuabilité reste posée en base : aucune ligne ne se modifie après coup. La politique RLS s'applique aussi en lecture, ce qui borne la consultation du journal à l'entreprise active.

### 4.7 Fichiers

Les clés existantes (`{schema}/projets/{id}/contrats/…`) restent en base et sur le disque : aucun déplacement. Les nouvelles clés sont préfixées par le `slug` de l'entreprise, qui vaut l'ancien nom de schéma : le rangement reste homogène.

### 4.8 Inscription et suppression

- **Inscription** : une transaction d'insertions (entreprise, rôles par défaut, administrateur, abonnement d'essai) — quelques secondes, sans `migrate_schemas`. Les trois transactions et la compensation du MLD §7.5 disparaissent.
- **Suppression définitive** (phase de test du MVP, purge) : suppression par `entreprise_id`, enfants d'abord, dans une transaction. Le Socle §3.1 (suppression logique) continue de régir les données métier.

---

## 5. Pas de fusion : la base repart de zéro

Aucune entreprise n'a de données réelles (Q1). Plutôt que de fusionner les schémas, on **recrée la base** :

- **Migrations remises à zéro** : une migration `0001` par application, générée depuis les modèles du lot 2. On ne garde pas 193 migrations écrites pour un autre modèle — c'était déjà la doctrine de la refonte du découpage (« pas de données de production : on remplace, sans migration de reprise »).
- **Ce qu'on réensemence** dans la base neuve : le catalogue (modules, permissions, référentiels, jours fériés), les plans d'abonnement (tarifs à `NULL`, décision A7), les comptes du personnel CCD Digital (Q8), et en développement le jeu `peupler_donnees_test`.
- **Ce qu'on perd volontairement** : les entreprises de test de la production et leur historique, journal d'audit compris. Une sauvegarde complète est prise avant, et conservée.
- **Le contrôle de non-régression** : `peupler_donnees_test` dans l'ancien modèle et dans le nouveau, puis comparaison des chiffres clés (avancement, santé, statuts, nombre de journaux, droits par compte). Les UUID étant régénérés, on compare les contenus, pas les empreintes.

---

## 6. Les lots

Tout se fait sur une **branche d'intégration** `feature/schema-unique`, comme pour la refonte du découpage : les deux modèles ne peuvent pas cohabiter en production (django-tenants route toute la base). `develop` ne la reçoit qu'à la bascule.

| Lot | Contenu | Critère de fin | Charge |
|---|---|---|---|
| **0** | **Conception.** Note de décision dans `04_Conception` ; MLD v2.0 (`entreprise_id`, unicités, clés composites) ; architecture et sécurité (les cinq barrières deviennent trois couches) ; conventions A5 ; réponses aux questions du §8 | Validé par le PO | 2 j |
| **1** | **Socle du contexte.** `contexte.py`, `ModeleEntreprise`, `ManagerEntreprise` qui refuse le hors-contexte, portée plateforme, authentification qui compare le claim, aides Celery et commandes | Tests unitaires du socle | 3 j |
| **2** | **Modèle de données.** Toutes les applications dans le schéma unique ; `entreprise` sur les 46 modèles ; unicités élargies ; clés composites ; index ; `Utilisateur.entreprise` ; rôles par entreprise ; Q3 tranchée | Migrations depuis une base vide ; `check` propre | 5 j |
| **3** | **Le code.** Les 159 `schema_context`, `connection.schema_name`, `request.tenant`, `set_tenant` ; les services de la plateforme (catalogue, clients, emprunt d'identité) en portée plateforme ; 11 tâches Celery ; clés de cache ; chemins de fichiers | Plus aucun import de `schema_context` hors du lot 8 ; `peupler_donnees_test` passe | 6 j |
| **4** | **SQL brut et RLS.** Revue des 54 `cursor.execute` ; migration des politiques RLS ; pose et retrait du réglage par requête et par tâche ; vérification du rôle de production | Une requête SQL brute hors contexte ne voit rien | 3 j |
| **5** | **Inscription, connexion, suppression.** Provisionnement en une transaction ; connexion par l'e-mail seul (unique sur la plateforme), **`X-Tenant` retiré** (code et en-têtes CORS) ; claim `entreprise` dans le jeton ; suppression par `entreprise_id` ; retrait de `registre_email` | Parcours d'inscription complet en moins de 5 s | 3 j |
| **6** | **Base neuve.** Migrations `0001` par application ; commande d'ensemencement (catalogue, plans, personnel CCD Digital) ; `peupler_donnees_test` adapté ; comparaison des chiffres clés avec l'ancien modèle | Une base vide se monte en une commande ; chiffres clés identiques | 1 à 2 j |
| **7** | **Étanchéité et performance.** La suite du §4.3 en CI ; comparaison de `mesurer_requetes` avant et après | Zéro fuite ; pas de régression de requêtes | 4 j |
| **8** | **Retrait de django-tenants et du vocabulaire « tenant ».** Paquet, `Domaine`, middleware, réglages ; `apps/tenants` renommée `apps/entreprises` ; `schema_name` renommé `slug` ; admin Django retirée ; commandes obsolètes (`creer_tenant_demo`, `gerer_entreprises`, `remplir_registre_global`…) ; `CLAUDE.md`, `AGENTS.md`, skill `django-expert-reference` | `grep -ri tenant` ne rend plus rien dans le code | 2 j |
| **9** | **Bascule en production.** Procédure du §7 | Ouverture après les contrôles | 1 j + fenêtre |

**Ordre imposé :** 0 → 1 → 2 → 3 et 4 (en parallèle possible) → 5 → 6 → 7 → 8 → 9. Le lot 7 commence dès le lot 3 : la suite d'étanchéité s'écrit au fur et à mesure, pas à la fin.

**Avec la branche `feature/perf-requetes`** (non fusionnée) : son lot 1 (`TENANT_LIMIT_SET_CALLS`) devient sans objet ; ses lots 2 à 4 (droits, préchargement des arbres) restent valables et se reportent tels quels.

---

## 7. La bascule

Sans données réelles, pas de fenêtre de maintenance à négocier : on prévient les testeurs.

1. Sauvegarde complète de la production, vérifiée et conservée.
2. Base de production vidée (schémas des entreprises de test supprimés, `public` recréé).
3. Déploiement de la branche ; `migrate` (une passe, depuis `0001`) ; ensemencement.
4. Contrôles : tests d'étanchéité contre la production ; connexion du personnel CCD Digital ; une inscription de bout en bout ; un rapport journalier saisi.

**Retour arrière :** restauration de la sauvegarde et redéploiement de l'étiquette précédente.

---

## 8. Décisions (07/11/2026)

| # | Question | Décision |
|---|---|---|
| Q1 | Données réelles en production | **Aucune** : pas de fusion, base recréée (§5) |
| Q2 | Fenêtre de maintenance | **Sans objet** : on prévient les testeurs |
| Q3 | Copies locales `accounts.Module` / `Permission` | **Supprimées** ; le catalogue fait foi |
| Q4 | Personnel CCD Digital | **Dans `utilisateur`**, avec `entreprise` nulle |
| Q5 | Rôle PostgreSQL de production | **Superutilisateur disponible** (hypothèse retenue, à confirmer sur le serveur, §8.1) : trois rôles (§4.3) |
| Q6 | Conservation des anciens schémas | **Sans objet** : la sauvegarde complète suffit |
| Q7 | Gestionnaire maison ou django-scopes | **Maison** : structure native de Django |
| Q8 | Ce qu'on garde de la production | **Le personnel CCD Digital et le catalogue** ; entreprises de test abandonnées après sauvegarde |
| Q9 | Place dans le calendrier | **Un ordre est à définir** : proposition au §11 |
| — | RLS PostgreSQL | **Gardée** comme deuxième couche |
| — | Tests | **`pytest` en CI pour la suite d'étanchéité**, exception à la suspension du 29/10/2026 |
| — | Admin Django | **Supprimée** |
| — | Vocabulaire « tenant », en-tête `X-Tenant` | **Supprimés** partout, frontend compris |
| — | Nettoyage du frontend | **Dès que possible** (§11, étape 1) |
| — | Branches en cours | `fix/nettoyage-registre-email` **fusionnée dans `develop`** le 07/11 (non poussée) ; lots 2 à 4 de `feature/perf-requetes` **reportés** dans `feature/schema-unique` |

### 8.1 Vérifier le rôle de production (Q5)

Dans la base de production, connecté avec le rôle **qu'utilise Django** (celui du `.env` du serveur) :

```sql
SELECT rolname, rolsuper, rolbypassrls, rolcreaterole
FROM pg_roles WHERE rolname = current_user;
```

- `rolsuper = t` : la RLS ne s'applique pas à ce rôle, même forcée. Il faut un rôle applicatif distinct (`CREATE ROLE ccd_app LOGIN`, ce que le superutilisateur peut faire). C'est même la meilleure configuration : un rôle restreint pour l'application, un second avec `BYPASSRLS` pour la portée plateforme, le superutilisateur pour les seules migrations.
- `rolsuper = f` et `rolcreaterole = f` : on reste sur le réglage `ccd.portee` décrit au §4.3, avec sa limite.

Un **compte superutilisateur Django** (`is_superuser` dans la table `utilisateur`) n'a aucun rapport : il ne donne aucun droit dans PostgreSQL. En local, le rôle `ccd` n'est pas superutilisateur (vérifié le 06/11/2026).

---

## 9. Risques

| Risque | Parade |
|---|---|
| Un filtre oublié laisse voir une autre entreprise | Couche 1 (refus hors contexte) + couche 2 (RLS forcée) + couche 3 (tests sur toutes les routes) |
| La RLS est contournée (rôle superutilisateur, réglage resté sur une connexion réutilisée) | Vérification du rôle au lot 0 ; retrait du réglage en fin de requête ; connexion sans réglage = rien de visible |
| Un code de la plateforme reste en portée plateforme trop largement | Portée nommée, journalisée, cherchable (`portee_plateforme(`), relue en revue |
| Le personnel CCD Digital ou le catalogue est perdu à la remise à zéro | Sauvegarde complète ; ensemencement testé sur une base vide avant la bascule |
| Régression de performance | Index composites ; `mesurer_requetes` à chaque lot |
| Le journal d'audit perd son ordre ou son immuabilité | Insertion ordonnée par `cree_le`, jamais de mise à jour ; déclencheurs conservés |
| La RLS est inopérante parce que Django tourne en superutilisateur | Rôle applicatif distinct (§8.1), et un test qui échoue si `current_user` est superutilisateur |
| Des tâches Celery en attente portent un `schema_name` | File vidée et planificateur arrêté avant la bascule |
| Le chantier s'étire et bloque les modules métier | Branche d'intégration ; les lots 0 et 1 ne bloquent rien ; décision de poursuivre réexaminée après le lot 2 |

---

## 10. Critères de réussite

- Zéro fuite dans la suite d'étanchéité, sur toutes les routes.
- Chiffres clés de `peupler_donnees_test` identiques dans l'ancien et le nouveau modèle.
- Un déploiement = une passe de `migrate`, en moins d'une minute.
- Une inscription en moins de 5 secondes.
- Plus aucune dépendance à django-tenants, plus de `SET search_path`, plus d'écart E1.

---

## 11. Ordre de réalisation (proposition)

Le principe : **ce qui ne dépend de rien part tout de suite, et rien de nouveau ne se construit sur l'ancienne structure.**

| Étape | Quoi | Dépôt | Dépend de | Charge |
|---|---|---|---|---|
| **1** | **Fait le 07/11/2026** (`7b3a49f`, frontend) — **Nettoyage du frontend, partie indépendante** : `baseApi()` et `basePlateforme()` ne déduisent plus l'API du sous-domaine (seule `NEXT_PUBLIC_API_URL` compte) ; plus de redirection vers un sous-domaine après l'activation ; commentaires « tenant » réécrits. Le frontend n'envoie déjà aucun `X-Tenant` (vérifié) | Frontend | Rien : la connexion marche déjà sans sous-domaine | 0,5 à 1 j |
| **2** | **Lot 0 — conception** : note de décision, MLD v2.0, architecture et sécurité, conventions A5 — **rédigé le 07/11/2026, en attente de validation du PO** (`decision_schema_unique_CCD_Digital.md`) | `04_Conception` | Rien | 2 j |
| **3** | **Lots 1 et 2** — socle du contexte, modèle de données | Backend, `feature/schema-unique` | Étape 2 validée | 8 j |
| **4** | **Lots 3 et 4** — le code, le SQL brut et la RLS ; la suite d'étanchéité (lot 7) **commence ici** | Backend | Étape 3 | 9 j |
| **5** | **Lot 5** — inscription, connexion, suppression, retrait de `X-Tenant` | Backend | Étape 4 | 3 j |
| **6** | **Lot 6 et report de `feature/perf-requetes`** — base neuve, ensemencement, droits en une requête, préchargement des arbres | Backend | Étape 5 | 2 à 3 j |
| **7** | **Lots 7 et 8** — suite d'étanchéité complète en CI ; retrait de django-tenants, de l'admin Django et du vocabulaire « tenant » | Backend | Étape 6 | 6 j |
| **8** | **Nettoyage du frontend, partie liée au contrat** : `schema` / `schema_name` deviennent `entreprise` ; libellés « sous-domaine » de l'administration | Frontend | Étape 7 (contrat stabilisé) | 0,5 j |
| **9** | **Lot 9 — bascule** en production, backend et frontend ensemble | Les deux | Étapes 7 et 8 | 1 j |

**Avec les autres chantiers :**

- **Le chantier frontend du découpage continue en parallèle** : il consomme des routes dont le contrat ne change pas.
- **Gel des nouveaux modèles backend sur `develop`** pendant les étapes 3 à 7 : un modèle ajouté sur l'ancienne structure serait à refaire. Les corrections urgentes passent sur `develop` et sont reportées dans `feature/schema-unique` chaque semaine.
- **Les modules métier (A1) démarrent après la bascule** : les écrire avant, c'est les écrire deux fois.

---

## 12. Avancement

| Lot | État | Commits |
|---|---|---|
| 1 | Fait — socle du contexte | `26de87c` |
| 2 | Fait — modèle de données | `773b9bd`, `a7e14a4` (ensemencement) |
| 3 | Fait le 07/11/2026 — voir ci-dessous | `428dfa8`, `801a502` |
| 4 | Fait le 07/11/2026 — voir ci-dessous | (ce commit) |

### Lot 3 — ce qui a été fait, et ce qu'il a fait apparaître

- **Passerelle** `apps/core/passerelle_schema.py` : l'ancien vocabulaire (`contexte_schema`, `schema_courant`…) traduit vers le contexte d'entreprise, en un seul endroit. 66 fichiers ne dépendent plus de django-tenants. Retirée au lot 8.
- **La table `utilisateur` est cloisonnée** (`RequeteComptes`) : les comptes de l'entreprise active ; **sans entreprise active, le personnel de l'éditeur** — ce que rendait `public` ; tout, en portée plateforme. Sans cela, la liste des collaborateurs d'une entreprise montrait les comptes de toutes les autres.
- **Connexion, invitation, réinitialisation** : l'entreprise se lit en portée plateforme (adresse ou empreinte du lien), puis s'active pour la requête — le `set_tenant` d'hier, sans balayer les schémas.
- **Le jeton porte le claim `entreprise`** ; l'authentification cherche le compte **dans** cette entreprise, puis compare (§5.2). `schema` reste dans le jeton et le profil jusqu'à l'étape 8 du §11 (frontend).
- **Personnel de l'éditeur** : `EstSuperAdminPlateforme` et l'emprunt d'identité exigent un compte **sans entreprise** — sans cela, tout administrateur d'entreprise (`AD`) passait la condition de rôle. `JetonReinitialisation` suit le compte (entreprise nulle pour le personnel) : la réinitialisation du personnel levait `HorsContexteEntreprise`.
- **Middlewares** (lecture seule d'abonnement, modules fermés) : plus de `request.tenant` ; ils lisent l'entreprise du **jeton vérifié** (`entreprise_du_jeton`), et ne s'en servent que pour restreindre.
- **Une seule URLconf** : `urls_tenant` reprend les routes de maintenance de `urls_public`.
- **Tâches Celery** : `recalculer_sante_projet_task`, `notifier_dg_derive_delai` et l'alerte rouge reçoivent un `entreprise_id` ; la clé de cache du recalcul est indexée par l'entreprise.
- **Suppression définitive** : deux `_base_manager` lisaient les comptes et les contrats de **toutes** les entreprises — l'aperçu aurait listé les dirigeants des autres clients, la purge emporté leurs fichiers. Bornés à l'entreprise.
- **`peupler_donnees_test`** repris de `feature/perf-requetes` (`6e7e31e`) : `--entreprise`, et il crée lui-même les rôles personnalisés `IT`, `MOE`, `MOA` qui n'existaient qu'à la main dans l'ancienne base `demo`. Il passe sur la base neuve.

**Reste hors du lot 3** : le provisionnement de l'inscription et le registre des e-mails (lot 5), le SQL brut de `nettoyage` et de la suppression (lot 4), les copies locales `accounts.Module`/`Permission` encore lues par le catalogue (Q3), la comparaison chiffrée avec l'ancien modèle (lot 6).

### Lot 4 — ce qui a été fait

- **Moteur `apps.core.backends.postgresql`** : le moteur de Django, plus un *execute wrapper* (`apps/core/rls.py`) qui, avant chaque requête, met la session d'accord avec le contexte Python — `ccd.entreprise_id` et le rôle. Une requête de réglage seulement quand le contexte change ; elle passe par le curseur brut, donc hors de `assertNumQueries` et de `mesurer_requetes`. L'état mémorisé est oublié après `ROLLBACK` et `ROLLBACK TO SAVEPOINT`, qui annulent un `set_config` côté serveur.
- **Migration `core.0001_isolation_rls`** : RLS activée, forcée, et politique `isolation_entreprise` sur les 46 tables d'entreprise. `utilisateur`, `jeton_reinitialisation` et `journal_audit` (entreprise nullable) : une ligne nulle n'est visible que sans entreprise active, comme `RequeteComptes`. Les 9 tables de liaison M2M, sans `entreprise_id`, restent hors RLS. Une nouvelle table d'entreprise ajoute `isolation_entreprise("<table>")` à sa migration.
- **Rôles** : `scripts/sql/roles_rls.sql`, à jouer en superutilisateur, crée `ccd_plateforme` (`NOLOGIN BYPASSRLS`), l'accorde au rôle de connexion et lui donne les droits sur les lignes. La migration redonne ces droits sur chaque base neuve (base de test comprise).
- **Contrôle** : `manage.py verifier_isolation` (et `check --database default`, `core.E101`) échoue si le rôle de connexion est superutilisateur ou `BYPASSRLS`, si `ccd_plateforme` manque, ou si une table d'entreprise n'a pas sa politique.
- **Celery** : contexte remis à zéro avant et après chaque tâche.
- **SQL brut revu** : le verrou de numérotation des projets est indexé par l'entreprise (et non plus par le schéma) ; le nettoyage et la suppression définitive passent leur SQL en portée plateforme ; la purge « zanf » (route de maintenance et `_purger_tout_zanf`), écrite pour les schémas, est supprimée. `audit_catalogue.py` et la migration `catalogue.0002` lisent des tables de l'ancien modèle : sans effet sur une base neuve, retirés au lot 8.
- **Critère tenu** : hors contexte, `SELECT count(*) FROM projet` rend 0 ; dans `demo`, 11.

**Reste au lot 5** : la suppression définitive repose encore sur `DROP SCHEMA` ; elle ne peut pas aboutir (les lignes de l'entreprise retiennent `entreprise_cliente`) tant qu'elle n'est pas réécrite par `entreprise_id` — trigger d'immuabilité de `historique_date` compris.
