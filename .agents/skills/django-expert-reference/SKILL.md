---
name: django-expert-reference
description: >-
  Conventions Django 5.2 / DRF propres au backend CCD Digital, et patrons de « Django 5 By Example »
  (Melé, 2024) tels qu'ils s'y appliquent. À utiliser avant d'écrire ou de modifier un modèle, une
  requête ORM, un serializer, une vue, une permission, une tâche Celery ou une clé de cache dans ce
  dépôt, et pour expliquer pourquoi le code y est organisé ainsi.
---

# Django / DRF dans ce dépôt

Ce qui suit ne répète pas la documentation de Django : il dit **où ce projet s'en écarte**, et
quels patrons généraux y comptent vraiment. Quand une règle du livre contredit une convention
d'ici, c'est la convention d'ici qui s'applique.

## 1. Ce que le multi-tenant change

Un schéma PostgreSQL par entreprise cliente (django-tenants). L'isolation vient du `search_path`,
pas d'un filtre.

- **`SHARED_APPS` ou `TENANT_APPS`** (`config/settings/base.py`) : à trancher avant le premier
  modèle d'une application. Une application métier dans `SHARED_APPS` met tous les clients dans la
  même table, et cela ne se rattrape pas après la première migration.
- **Pas de colonne `tenant_id`**, pas de filtre « par entreprise » dans les requêtes métier.
- **Migrations** : `migrate_schemas --shared` puis `--tenant`. `migrate` seul ne fait rien d'utile.
- **Une tâche Celery n'hérite pas du schéma.** Elle reçoit `schema_name` en argument et travaille
  dans `with schema_context(schema_name):`. Sans cela elle tourne sur `public`, ne trouve rien et
  ne lève rien. Modèle : `apps/projets/tasks.py`.
- **Redis n'isole rien.** `CACHES` n'a pas de `KEY_FUNCTION` : une clé de cache qui porte une donnée
  d'un client contient le nom du schéma. Une clé sans schéma n'est acceptable que pour une donnée
  identique pour tous (ex. la météo d'une ville, `apps/projets/services/meteo.py`).
- **Tests** : un test métier s'exécute dans un schéma — fixture `schema_demo` de `conftest.py`.

## 2. Organisation d'une application

`models/`, `views/`, `serializers/`, `services/`, `selectors/` sont des **paquets**. Un `views.py`
créé à côté du dossier `views/` est ignoré sans aucun message.

| Couche | Rôle |
|---|---|
| `selectors/` | Lit, ne modifie rien. Porte les `select_related` / `prefetch_related` |
| `services/` | Modifie l'état, porte la règle de gestion et la transaction |
| `views/` | `APIView` sans logique : permission, validation, appel du service, réponse |
| `serializers/` | Entrée (validation stricte) séparée de la sortie (représentation) |

Une règle de gestion écrite dans une vue sera réécrite le jour où une tâche Celery ou une commande
d'administration en aura besoin.

Pagination (`apps.core.pagination.PaginationStandard`), format d'erreur
(`apps.core.exceptions.gestionnaire_erreurs`) et authentification sont globaux : ne pas les refaire
par module. Une erreur métier est une sous-classe d'`ErreurMetier`, pas une `Response` construite à
la main.

## 3. Modèles

- **Hériter de `ModeleBase`** (`apps/core/models`) : UUID, horodatages, auteur, suppression logique.
  Seule exception : `JournalAudit`, en insertion seule, dont l'ordre d'insertion est une information.
- **La suppression physique n'existe pas.** `objet.delete()` pose `supprime_le`. `objects` masque
  les lignes supprimées ; `tous_objets` les montre, et s'en servir est un choix à justifier.
- **Montants : `MontantField`**, en centimes, sur `BigIntegerField`. Jamais de `float`, jamais de
  francs. `PourcentageField` et `QuantiteField` pour le reste (`apps/core/fields.py`).
- **Dates : UTC en base** (`TIMESTAMPTZ`), conversion à l'affichage.
- **Statuts : `models.TextChoices`**, regroupés dans `apps/core/enums.py` quand ils sont partagés.
- **Fichiers : la clé de stockage en base, jamais l'URL.** En production l'URL S3 est signée et
  périme ; elle se calcule à la lecture. La clé commence par le nom du schéma.
- **Héritage** : abstrait pour factoriser des champs, proxy pour changer un comportement sans
  toucher au schéma ; l'héritage multi-tables coûte une jointure à chaque requête.
- **Relations génériques** (`ContentType` + `GenericForeignKey`) pour rattacher une même entité à
  des parents hétérogènes — journal d'audit, pièces jointes — plutôt qu'une clé étrangère par parent.
- **Index** sur les champs filtrés ou triés souvent : `Meta.indexes`.

## 4. ORM

- **N+1** : `select_related` pour `ForeignKey` / `OneToOne`, `prefetch_related` pour les relations
  multiples, `Prefetch()` pour filtrer ou trier ce qui est préchargé. À poser dans le selector, pas
  dans le serializer.
- Un `SerializerMethodField` qui interroge la base est un N+1 : annoter le queryset à la place.
- `exists()` plutôt que `count() > 0` ; `only()` / `defer()` pour écarter un champ lourd.
- `F()` pour incrémenter en base sans course ; `Q()` pour les conditions combinées.
- **`transaction.atomic()`** autour de toute écriture multi-tables ; `select_for_update()` quand
  deux requêtes peuvent modifier la même ligne (numérotation, stock, paiement).
- `save(update_fields=[...])` : les noms sont des chaînes qu'aucun outil ne vérifie. Un test qui
  appelle la fonction est la seule protection contre une faute de frappe.

## 5. Droits

`DEFAULT_PERMISSION_CLASSES` impose l'authentification ; chaque vue déclare en plus qui a le droit.

- Les classes sont dans `apps/core/permissions.py` : `PermissionModule`, `RoleRequis`,
  `EstDirection`, `MembreDuProjet`, `GardePermissionProjet`.
- **Une liste se restreint aussi** : `filtrer_queryset_par_affectations` ou
  `ScopedProjetQuerySetMixin`. Protéger le détail sans filtrer la liste laisse voir les projets des
  autres.
- `has_object_permission` n'est pas appelé par une vue qui ne passe pas par `get_object()` : dans
  une `APIView`, appeler `self.check_object_permissions(request, obj)`.

## 6. Celery

- Arguments **primitifs** : identifiants et nom de schéma, jamais une instance de modèle.
- Tâches **idempotentes** : rejouées avec les mêmes arguments, elles laissent le même état.
- `bind=True, max_retries=…` pour ce qui dépend d'un service tiers (email, CinetPay).
- Une tâche planifiée « tous tenants » boucle sur les entreprises actives et ouvre un
  `schema_context` par entreprise.

## 7. Paiement et webhooks (CinetPay)

- Vérifier la signature de la charge utile avant tout traitement.
- Protéger contre le rejeu : un identifiant d'événement ne se traite qu'une fois.
- Ne jamais faire confiance au montant reçu : le relire côté serveur.

## 8. Avant de livrer

- Tout texte montré à l'utilisateur passe par `_("…")` (Socle Commun §1.1).
- `@extend_schema` à jour sur les vues modifiées : le frontend lit ce contrat.
- `ruff check`, `pytest apps/<module>/tests/`, et `python manage.py check --deploy` pour un
  changement de réglages.
- Le déploiement est cPanel + Passenger (`passenger_wsgi.py`, `docs/deploiement-cpanel.md`) : pas de
  Nginx ni d'ASGI à supposer.

## 9. Anti-patterns, et ce qu'ils provoquent ici

| Anti-pattern | Conséquence | Parade |
|---|---|---|
| Requête dans la boucle d'un serializer | N+1, latence multipliée | `select_related` / `prefetch_related` dans le selector |
| Tâche Celery sans `schema_context` | Tourne sur `public`, ne trouve rien, ne lève rien | Passer `schema_name`, ouvrir le contexte |
| Clé de cache sans le schéma | Un client lit la donnée d'un autre | Schéma dans la clé |
| Instance de modèle passée à une tâche | Donnée périmée, échec de sérialisation | Passer l'identifiant, recharger dans la tâche |
| Écriture multi-tables sans transaction | État incohérent si une étape échoue | `transaction.atomic()` + `select_for_update()` |
| Règle de gestion dans la vue | Réécrite ailleurs, puis divergente | La mettre dans `services/` |
| URL de fichier stockée en base | Lien mort à l'expiration de la signature | Stocker la clé, calculer l'URL à la lecture |
| Webhook sans vérification de signature | Paiement falsifiable | Valider la signature, refuser le rejeu |
| Champ filtré souvent, sans index | Parcours complet de table | `models.Index` dans `Meta.indexes` |
