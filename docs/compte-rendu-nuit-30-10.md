# Compte rendu de la nuit du 30/10/2026 — lots backend 1, 5 et 10 du découpage en arbre

| | |
|---|---|
| Dépôt | `SOUMAFESARL/API-Gestion-Chantier`, depuis `develop` (`d4675fb`) |
| Lots | 1 (référentiel et back-office des listes et modèles), 5 (dupliquer, import DQE, historique), 10 (dépendances) |
| Décisions suivies | `docs/decoupage/decisions-v1.2.md` (§3, §4, §11, §11bis, §12, §13bis, §13quinquies) et les décisions du développeur données avec la tâche |
| Tests | Aucun test pytest ajouté (décision du 29/10/2026) |

## 1. Ce qui est fait

| Lot | Branche | Commit | Contrat d'API |
|---|---|---|---|
| 1 | `decoupage/lot-1-referentiel-backoffice` (depuis `develop`) | `7e946f8` | `docs/api-decoupage-listes-modeles.md` |
| 5 | `decoupage/lot-5-dupliquer-dqe-historique` (depuis le lot 1) | `dc63ba8` | `docs/api-decoupage-dupliquer-dqe-historique.md` |
| 10 | `decoupage/lot-10-dependances` (depuis le lot 5) | `0b99783` | `docs/api-decoupage-dependances.md` |

Ce compte rendu est commité sur la branche du lot 10.

**Lot 1.** Catégorie `lots` retirée des routes `referentiels/` et `admins/referentiels/` (types de
projet et modes d'exécution inchangés) ; back-office `/admins/decoupage/` des listes de valeurs
(lister, créer, modifier, retirer, ajout en masse, corriger ou retirer une valeur) et des modèles
plateforme (lister, créer, mettre à jour avec version, retirer) ; lecture SUPPORT et SUPERVISEUR,
écriture SUPERVISEUR, chaque écriture au journal de la plateforme. Les services du découpage
(`services/listes_modeles.py`) servent les deux côtés.

**Lot 5.** `POST elements/{id}/dupliquer/` ; import DQE en deux temps (`…/decoupage/dqe/` pour le
bilan, `…/dqe/appliquer/` pour l'application ligne par ligne), colonne « Prix unitaire » ;
`GET elements/{id}/historique/` lu dans `JournalAudit`, paginé.

**Lot 10.** Modèle `Dependance` (migration `projets/0050_dependances`, schéma de l'entreprise) ;
routes `GET`/`POST elements/{id}/dependances/` et `DELETE dependances/{id}/` ; garde à la
planification et à la reprogrammation (`dependance_non_respectee`) ; aperçu du report avec les
successeurs à décaler (`apercu: true`), décalage confirmé par `decaler_successeurs`, sinon
`successeurs_a_decaler` ; héritage des liens au détail ; retrait tracé à la désactivation ;
prédécesseurs et successeurs dans la case et flèches dans `GET projets/{id}/planning/`.

## 2. Branches poussées : aucune — accès refusé

**Le push a échoué pour les trois branches** : GitHub refuse toute écriture à l'intégration Claude
de cette session sur ce dépôt.

```
remote: Claude doesn't have GitHub access to SOUMAFESARL/API-Gestion-Chantier for your organization.
fatal: unable to access 'https://github.com/SOUMAFESARL/API-Gestion-Chantier/': The requested URL returned error: 403
```

La lecture fonctionne (`git fetch`, API de lecture), mais la création de branche par l'API répond
aussi `403 Resource not accessible by integration`. Rien n'a été poussé, ni `develop`, ni `main`,
ni les branches de lot.

**Pour récupérer le travail** : le bundle git `decoupage-nuit-30-10.bundle`, remis avec le message
de fin de session, contient les trois branches. Depuis le dépôt local :

```bash
git fetch ./decoupage-nuit-30-10.bundle 'refs/heads/decoupage/*:refs/heads/decoupage/*'
```

```bash
git push -u origin decoupage/lot-1-referentiel-backoffice decoupage/lot-5-dupliquer-dqe-historique decoupage/lot-10-dependances
```

Pour que les prochaines sessions puissent pousser : reconnecter GitHub sur
https://claude.ai/connect-github et vérifier que l'application GitHub Claude est installée sur
l'organisation `SOUMAFESARL` avec l'accès en écriture à ce dépôt.

## 3. Vérifications

Python 3.13.17, Django 5.2.18, dépendances de `requirements/local.txt`, PostgreSQL 16 local
(cluster de la machine), réglages `config.settings.local`.

| Commande | Résultat |
|---|---|
| `python manage.py check` | `System check identified no issues (1 silenced).` — sur chaque branche |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` — sur chaque branche |
| `python manage.py migrate_schemas --shared` | Toutes les migrations publiques appliquées sur une base neuve |
| `python manage.py migrate_schemas --schema=verif` | Toutes les migrations d'entreprise appliquées, dont `projets.0050_dependances` |
| `ruff check` | **Aucune erreur nouvelle** : sur chaque fichier touché, autant d'erreurs que sur `develop` (`apps/projets` 94, `apps/platform_admin` 137, `apps/catalogue` 7, toutes antérieures) ; les fichiers créés sont propres |
| `ruff format --check` | Fichiers créés et modifiés formatés, sauf `platform_admin/urls.py` et `projets/views/reprogrammation.py`, déjà non formatés sur `develop` (laissés tels quels pour ne pas mêler de reformatage au diff) |
| `python manage.py spectacular` | Le schéma se génère ; les nouvelles routes y figurent ; les erreurs affichées concernent des vues existantes |

**Essais fonctionnels** (scripts jetables, hors du dépôt, contre la base locale, vues appelées par
`APIRequestFactory`) :

- **Lot 1** : SUPPORT lit (200) mais n'écrit pas (403) ; doublon de liste 409 `libelle_en_double` ;
  ajout en masse avec doublon ignoré ; modèle plateforme créé, refusé sur C-1 (422), refusé sur une
  liste d'entreprise (422), refusé sur un type de projet inconnu (400) ; mise à jour → version 2 ;
  retrait d'une liste utilisée refusé (422) puis accepté après retrait du modèle ; journal de la
  plateforme écrit ; côté entreprise, listes, ajout aux listes plateforme, modèles et
  personnalisation inchangés.
- **Lot 5** : copie à côté (« Gros œuvre (copie) », puis « (copie 2) »), sous une autre branche,
  refus sous une tâche commencée (A-5) et sur niveau sauté (A-1) ; la copie a 0 réalisé, ni dates ;
  bilan DQE (mises à jour avant/après, deux nouvelles branches, refus C-2 et unité inconnue),
  application refusée sans motif puis appliquée ; refus `quantite_sous_realise`,
  `dates_deja_fixees`, `dates_hors_parent` ; historique paginé avec l'entrée `IMPORT_DQE` ; export
  en FCFA.
- **Lot 10** : liens A→B, B→C ; boucle C→A refusée (409 `dependance_boucle`) ; doublon, parent,
  deux identifiants refusés ; B reprogrammée avant la fin de A refusée (`dependance_non_respectee`,
  message nommant A) ; aperçu du report de A listant B puis C décalées ; report refusé sans
  confirmation, refusé avec B seule, accepté avec B et C (dates, historique des dates et journal
  d'audit vérifiés) ; planning avec les flèches ; détail de B → liens reportés sur ses deux
  sous-tâches ; désactivation → liens retirés ; import DQE refusant une ligne qui viole un lien ;
  ajout d'une sous-tâche sous une feuille liée → lien reporté.

**Impossible ou incomplet** :

- `python manage.py creer_tenant_demo` **échoue sur `develop`** sur une base neuve, avant toute
  modification de cette nuit : `accounts.0033_role_unique_par_projet` lève
  `OperationalError: cannot ALTER TABLE "role" because it has pending trigger events` (précédé de
  `Entreprise.DoesNotExist`). Le schéma de vérification a donc été créé en enregistrant d'abord la
  ligne `Entreprise`, puis en migrant (`migrate_schemas --schema=verif`), ce qui passe. À corriger à
  part.
- Pas de scénario de recette rejoué dans le frontend (autre session).

## 4. Décisions prises seul

**Lot 1**

1. La catégorie `LOT` reste dans `CategorieReferentiel` et en base (changer les choix aurait exigé
   une migration) ; plus aucune route ne l'expose. Les noms de lot ajoutés par une entreprise
   (`referentiel_entreprise`, catégorie `LOT`) **ne sont pas recopiés** dans la liste « Lots » :
   §14, pas de données à préserver.
2. Retirer une liste plateforme est **refusé tant qu'un modèle plateforme y puise** ; les niveaux de
   projets et de modèles d'entreprise qui la citent la gardent (on ne peut pas les vérifier sans
   parcourir tous les schémas).
3. Un modèle plateforme ne cite que des **types de projet du référentiel plateforme** (400 sinon).
4. En plus de l'ajout en masse : **corriger** (`PATCH`) et **retirer** (`DELETE`) une valeur
   plateforme, et `est_actif` sur un modèle plateforme.
5. Les écritures du back-office vont au **journal de la plateforme** (comme les référentiels), pas
   au `JournalAudit` des entreprises.
6. Réenregistrer un modèle retirait ses anciens niveaux et lignes **physiquement**
   (`QuerySet.delete()`) : remplacé par la suppression logique (Socle §3.1).
7. Les valeurs d'une liste portent désormais `ordre` (ajout de champ, sans rupture).

**Lot 5**

1. La copie **ne reprend pas le code libre** (il numérote une ligne du bordereau du client), ni les
   cases désactivées, ni la suspension. Sans `parent_id`, elle se pose à côté de l'original. La
   poser sous une case commencée exige un motif, comme un ajout (§12.2).
2. **Montants du fichier en FCFA.** L'import et l'export Excel existants traitaient la colonne
   « Montant (FCFA) » comme des centimes (l'export écrivait des centimes sous cet en-tête). Un DQE
   est en FCFA, et Montant = Quantité × Prix unitaire aussi : la conversion se fait désormais au
   bord du fichier, dans les deux sens. **Effet sur le frontend** : le montant d'une ligne importée
   est 100 fois plus grand qu'avant pour un même fichier (c'est la valeur juste).
3. Le bilan accepte un fichier (multipart) ou des lignes déjà lues (JSON) ; l'application reçoit
   les lignes en JSON, refait le bilan et **applique ligne par ligne** (point de sauvegarde par
   ligne) ; une ligne est refusée en entier si une de ses valeurs l'est.
4. **Dates par le DQE** : seulement pour une feuille encore sans dates, dans le cadre de ses
   parents ; jamais de reprogrammation ni de prolongation par fichier.
5. Une ligne qui porte des valeurs sur une case parente est refusée (`case_parente`) ; une ligne
   « sans effet » (sa dernière case a des enfants sur d'autres lignes) n'est qu'un avertissement,
   comme dans le tableau.
6. L'historique ne montre que **la case elle-même** et que **`JournalAudit`** ; les reports de dates
   (`historique-dates/`) et les mesures hors journal (`MiseAJourInline`) ont leurs propres routes.
   Une case vue par son seul chemin répond 403.

**Lot 10**

1. « Après la fin » se lit **strictement** : B commence au plus tôt le **lendemain** de la fin de A.
2. Lier deux tâches déjà en violation est **refusé** (pas de décalage automatique à la création du
   lien) : reprogrammer B d'abord.
3. Décocher un successeur dans l'aperçu **refuse le report** plutôt que de laisser une violation :
   jamais de décalage silencieux, jamais de lien non respecté créé par un report.
4. Le décalage se propage **de proche en proche** ; chaque successeur décalé doit être confirmé et
   exige `projets.planifier` dans son périmètre ; la prolongation de ses parents suit le même
   `prolonger` et `projets.prolonger` évaluée sur lui.
5. La **première planification** de A propose aussi de décaler des successeurs déjà datés (avec
   motif et justification, puisque c'est un report pour eux).
6. Les liens sont reportés sur les nouvelles feuilles **chaque fois qu'une feuille liée devient un
   parent** (détail, ajout, copie dessous, tableau, import DQE), pas seulement au détail.
7. **Désactiver ou supprimer** une case retire les liens de **toute sa branche** ; réactiver ne les
   rétablit pas.
8. Le respect d'un lien se lit sur les **dates prévues** (le planning dessine la baseline quand elle
   est complète).
9. Une tâche liée hors du périmètre de lecture n'est donnée que par son identifiant
   (`visible: false`).
10. `ReprogrammationRequestSerializer` : `motif_id` et `justification` deviennent facultatifs **dans
    le schéma** (pour l'aperçu) ; ils restent exigés, avec les mêmes messages, pour un vrai report.

## 5. Points ouverts

1. **Pousser les trois branches** (§2), puis les relire et les fusionner selon le plan ; aucune n'a
   touché `develop` ni `main`.
2. **Frontend** : les routes `referentiels/lots/` et `admins/referentiels/lots/` répondent 404 ; les
   écrans doivent lire la liste « Lots » (`decoupage/listes/`). Montants Excel en FCFA (§4, lot 5).
3. **`creer_tenant_demo` en échec sur base neuve** (`accounts.0033`, §3), antérieur à cette nuit.
4. Côté entreprise, créer une liste, y ajouter des valeurs, enregistrer ou supprimer un modèle
   n'écrivent **pas** au journal d'audit (antérieur, non traité).
5. `appliquer_tableau` (ajout en masse) ne vérifie ni A-2 ni le cadre des dates des parents pour
   les nouvelles branches (antérieur) ; le bilan DQE vérifie A-2 lui-même.
6. Une branche en récursion s'exporte avec plus de cellules que de niveaux : le fichier ne se
   réimporte pas tel quel (limite antérieure, §5.9).
7. Le plan complet des 14 lots (dépôt frontend, `docs/plan_decoupage_arbre.md`) n'a pas été relu :
   le travail suit la description des lots donnée avec la tâche et les décisions v1.2.
