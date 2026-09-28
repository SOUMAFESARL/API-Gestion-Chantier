---
name: django-expert-reference
description: >-
  Référence universelle d'ingénierie, d'architecture et de bonnes pratiques Django 5 & Django REST Framework
  (issue de 'Django 5 By Example' par Antonio Melé, 2024). À activer systématiquement lors de toute question,
  session d'apprentissage, audit de performance, conception d'API ou génération de manuel PDF impliquant Django.
  Fournit les patrons de conception avancés (ORM sans N+1, Polymorphisme, ContentTypes, Cache Redis, Celery,
  Channels WebSockets, WeasyPrint, Sécurité RBAC) et les checklists Pre-Mortem associées.
---

# Référence d'Ingénierie & d'Architecture Django 5 & DRF (Melé 2024)

Ce skill constitue la **mémoire technique et architecturale souveraine** pour tout développement Django 5 et Django REST Framework. Il distille les patterns industriels éprouvés du livre *Django 5 By Example* (Antonio Melé, 5ᵉ édition, 2024) et s'articule avec l'écosystème d'apprentissage neurocognitif (`learning-orchestrator`, `sprint-task-lifecycle`).

---

## 1. Les 8 Piliers d'Architecture Django 5 & DRF

### Pilier 1 : Modélisation Avancée, Héritage & Polymorphisme
* **Typologie des 3 Héritages de Modèles :**
  1. **Modèle Abstrait (`abstract = True`) :** Factorisation de champs communs (`created_at`, `updated_at`, `is_active`) sans table physique en base de données.
  2. **Héritage Multi-Tables (MTI) :** Table parente liée par relation OneToOne implicite aux tables enfants. Utiliser avec discernement (impact de jointure SQL à chaque requête).
  3. **Modèle Proxy (`proxy = True`) :** Personnalisation du comportement Python (méthodes, tri par défaut, managers) sans altérer le schéma SQL ni créer de table supplémentaire.
* **Framework `contenttypes` & Relations Génériques :**
  * Utiliser `ContentType`, `object_id` et `GenericForeignKey` pour relier polymorphiquement des entités hétérogènes (ex: Journal d'audit universel, photos de chantier, pièces jointes, tags) sans multiplier les clés étrangères directes.
* **Champs de Modèles Personnalisés (*Custom Model Fields*) :**
  * Création de champs sur-mesure (ex: `OrderField` pour l'ordonnancement dynamique d'éléments au sein d'un parent spécifique) en surchargeant `pre_save()`.
* **Énumérations Typées :**
  * Utiliser `models.TextChoices` ou `models.IntegerChoices` pour des statuts stricts et lisibles.

---

### Pilier 2 : Maîtrise de l'ORM & Performance SQL Sans Faille
* **Éradication Absolue du Problème $N+1$ :**
  * **`select_related(*fields)` :** À utiliser pour les relations directes mono-valeur (`ForeignKey`, `OneToOne`). Génère une jointure SQL (`JOIN`) en une seule requête.
  * **`prefetch_related(*lookups)` :** À utiliser pour les relations multi-valeurs (`ManyToManyField`, `ForeignKey` inverses). Exécute une requête SQL par table et réalise la fusion en mémoire Python.
  * **`Prefetch()` objects :** Pour filtrer ou ordonner les relations préchargées avant leur jointure en mémoire.
* **Évaluation Paresseuse & Optimisation des Requêtes :**
  * Les QuerySets sont *lazy* : ils ne touchent la base de données qu'à l'itération, au découpage (*slicing*), à l'appel de `len()`, `list()` ou `bool()`.
  * Utiliser `exists()` plutôt que `count() > 0` pour tester la présence d'un enregistrement.
  * Utiliser `only()` ou `defer()` pour éviter de charger des champs lourds (ex: descriptions volumineuses) lorsque non requis.
* **Requêtes Avancées :**
  * Objets `Q` pour les requêtes combinatoires (`|` pour OR, `&` pour AND, `~` pour NOT).
  * Expressions `F` pour manipuler et incrémenter des valeurs directement en base sans race condition (ex: `stock = F('stock') - 1`).
* **Transactions Atomiques & Verrous :**
  * Encapsuler toute opération multi-tables critique (commandes, décomptes financiers, déstockages) dans un bloc `with transaction.atomic():`.
  * Verrous pessimistes avec `select_for_update()` pour empêcher les collisions concurrentes.
* **Custom Managers & QuerySets :**
  * Encapsuler la logique de requête métier dans des QuerySets chaînables (`models.QuerySet.as_manager()`).

---

### Pilier 3 : Django REST Framework (DRF) & API Craftsman
* **Sérialiseurs & Validation Robuste :**
  * Séparation nette : Sérialiseur d'entrée (validation stricte des inputs) vs Sérialiseur de sortie (représentation optimisée).
  * Validations chirurgicales : `validate_<champ>()` pour une règle unitaire, `validate(data)` pour les contraintes inter-champs.
  * Utilisation de `SerializerMethodField` pour les calculs dynamiques (avec pré-calcul au niveau de l'ORM pour éviter les régressions de performance).
* **ViewSets & Routers :**
  * Utilisation de `ModelViewSet` pour les ressources CRUD standards.
  * Exposition des routes métiers via le décorateur `@action(detail=True/False, methods=['post'])`.
  * Routage clair et versionné via `DefaultRouter`.
* **Sécurité & Contrôle d'Accès Fin (RBAC) :**
  * Éviter de limiter la sécurité au niveau de la vue : implémenter des classes `BasePermission` dédiées.
  * Surcharger `has_permission(request, view)` pour l'accès global et `has_object_permission(request, view, obj)` pour vérifier la propriété de l'objet (ex: appartenance au chantier ou à l'entreprise).

---

### Pilier 4 : Asynchronisme Industriel & Tâches de Fond (Celery)
* **Architecture Distribuée :**
  * Message Broker : RabbitMQ ou Redis.
  * Workers Celery avec `@shared_task(bind=True, max_retries=3, default_retry_delay=60)`.
* **Idempotence & Résilience :**
  * Toute tâche asynchrone doit être strictement **idempotente** (son exécution répétée avec les mêmes paramètres ne doit pas altérer l'état final).
  * Ne jamais passer d'instances de modèles Django complexes en argument de tâche (risque de données obsolètes) ; passer uniquement des identifiants primitifs (`order_id`, `chantier_id`).
* **Cas d'usage types :**
  * Envoi d'e-mails transactionnels et SMS d'alerte.
  * Génération lourde d'états financiers ou de bilans OHADA.
  * Synchronisation périodique avec des services tiers (passerelles de paiement, webhooks).

---

### Pilier 5 : Stratégies de Cache Multi-Niveaux & Moteur Redis
* **Backend de Cache :**
  * Utiliser `django-redis` pour bénéficier de la rapidité mémoire et des structures de données natives de Redis.
* **Les 4 Paliers de Mise en Cache :**
  1. **Low-level Cache API :** `cache.get_or_set(key, callable, timeout)` pour les agrégats lourds (ex: solde global d'un chantier).
  2. **Template Fragment Cache :** `{% cache timeout key %}` pour les blocs HTML complexes non dynamiques.
  3. **View Cache :** Décorateur `@cache_page(timeout)` pour les endpoints publics peu changeants.
  4. **Per-Site Cache :** `UpdateCacheMiddleware` et `FetchFromCacheMiddleware` pour les sites vitrines.
* **Structures Redis Natives pour les Métriques :**
  * Compteurs atomiques (`INCR`, `INCRBY`) pour les statistiques d'accès.
  * Ensembles ordonnés (*Sorted Sets* : `ZADD`, `ZINCRBY`, `ZREVRANGE`) pour les classements et tableaux d'honneur en temps réel.
* **Politique d'Invalidation :**
  * Clés de cache déterministes et invalidation ciblée lors des signaux `post_save` / `post_delete`.

---

### Pilier 6 : Temps Réel avec Django Channels & WebSockets (ASGI)
* **Architecture ASGI vs WSGI :**
  * WSGI est synchrone (une requête bloque un thread).
  * ASGI (piloté par Daphne) gère les connexions persistantes asynchrones par boucle d'événements.
* **Consumers WebSockets :**
  * Utiliser `AsyncWebsocketConsumer` pour une scalabilité maximale.
  * Gérer explicitement les événements `connect()`, `disconnect()` et `receive()`.
* **Channel Layers (Redis) :**
  * Diffusion de messages par groupes (`group_add`, `group_discard`, `group_send`).
  * Utilisation obligatoire de `database_sync_to_async` pour exécuter des requêtes Django ORM au sein d'un consumer asynchrone sans bloquer la boucle ASGI.

---

### Pilier 7 : Sécurité, Facturation & Médias Dynamiques
* **Custom User Model :**
  * Toujours définir un modèle héritant de `AbstractUser` dès l'initialisation du projet (`AUTH_USER_MODEL`).
* **Gestion Sécurisée des Webhooks (Stripe / CinetPay) :**
  * Vérification impérative de la signature cryptographique de la charge utile (*payload*).
  * Traitement des événements avec protection contre le rejeu (*replay attack*) via vérification d'unicité de l'identifiant d'événement.
* **Génération PDF Dynamique Haute Définition :**
  * Compilation HTML/CSS Paged Media via `WeasyPrint` pour produire des factures, bordereaux de livraison et états comptables officiels.
  * Intégration d'en-têtes, pieds de page, pagination dynamique (`counter(pages)`) et QR codes.

---

### Pilier 8 : Production, Déploiement & DevOps
* **Architecture des Paramètres Modulaires :**
  * `config/settings/base.py` (paramètres communs).
  * `config/settings/local.py` (développement avec debug et outils de profilage).
  * `config/settings/production.py` (sécurité stricte, pas de secrets en dur, variables `.env`).
* **Multiplexage Nginx + uWSGI/Gunicorn + Daphne :**
  * Nginx en frontal : gère le SSL/TLS, sert les fichiers statiques (`STATIC_ROOT`) et médias (`MEDIA_ROOT`).
  * Routage HTTP classique vers uWSGI/Gunicorn.
  * Routage WebSocket (`/ws/`) avec mise à niveau des en-têtes (`Upgrade`, `Connection "Upgrade"`) vers Daphne.
* **Audit de Durcissement :**
  * Validation pré-livraison obligatoire : `python manage.py check --deploy`.
  * Activation de HSTS, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.

---

## 2. Table des Pre-Mortems & Anti-Patterns Fréquents

| Anti-Pattern Détecté | Conséquence Système | Solution Architecturale (Melé / Django 5) |
| :--- | :--- | :--- |
| **Requête SQL dans la boucle du Serializer** | Explosion du nombre de requêtes ($N+1$), latence $\times 20$. | Utiliser `select_related()` ou `prefetch_related()` en amont dans le `get_queryset()` du ViewSet. |
| **Appel ORM synchrone dans un `AsyncWebsocketConsumer`** | Blocage brutal de la boucle d'événements Daphne pour tous les utilisateurs. | Encapsuler l'appel dans `database_sync_to_async(fonction)`. |
| **Opération bancaire / stock sans transaction atomique** | Incohérence des données en cas d'erreur réseau intermédiaire. | Encapsuler dans `with transaction.atomic():` avec `select_for_update()`. |
| **Passage d'un objet modèle lourd à une tâche Celery** | Désynchronisation de données (*race condition*) et échec de sérialisation. | Passer uniquement la clé primaire `instance.id` et recharger l'objet dans le worker. |
| **Oubli de signature sur un endpoint Webhook** | Falsification possible de paiements par injection de requêtes forgées. | Valider systématiquement le HMAC/Signature envoyé dans l'en-tête de la passerelle. |
| **Indexation absente sur les champs filtrés fréquemment** | Scans complets de table (*Full Table Scans*) écroulant PostgreSQL. | Ajouter explicitement `models.Index(fields=['statut', 'date_debut'])` dans `Meta.indexes`. |

---

## 3. Guide de Transposition pour les Manuels PDF (`sprint-task-lifecycle`)

Lorsqu'un manuel PDF de tâche de sprint backend est généré pour le développeur, **ce skill garantit que le contenu technique intègre** :

1. **Section Film Mental :** Visualisation précise du flux de données et du comportement de l'API sous charge.
2. **Section Architecture & Invariants :** Schéma relationnel rigoureux, contraintes de validation et contrats d'interfaces JSON normalisés.
3. **Section Guide Pas-à-Pas :** Code exemplaire, documenté selon les idiomes Django 5 (évitement des fonctions dépréciées, utilisation des génériques).
4. **Section Pre-Mortem :** Les 3 pièges subtils de la tâche et comment les tester.
5. **Section Défi Homo Docens :** Question de réflexion profonde forçant l'apprenant à expliquer la mécanique sous le capot (ex: *"Comment Django gère-t-il la relation inverse sans table physique ?"*).
