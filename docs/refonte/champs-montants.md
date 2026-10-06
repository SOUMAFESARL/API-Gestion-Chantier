# Inventaire exhaustif des champs de montants (Règles E-11 et E-12)

Ce document dresse l'état des lieux factuel (`chemin:ligne`) de tous les champs de montants de l'API BTP. Il sert de socle de vérité pour le cadrage et l'écriture des tests du Lot 7.

---

## 1. Cartographie des champs par ressource

### 1.1 Ressource : Projet

| Emplacement | Fichier & Lignes | Champ technique | Type & Usage | Règle associée |
|---|---|---|---|---|
| **Modèle** | `apps/projets/models/projet.py:48-52` | `budget_initial_montant` | `BigIntegerField` (centimes FCFA, facultatif) | E-11 |
| **Entrée POST** | `apps/projets/serializers/__init__.py:266-268` / `apps/projets/serializers/swagger.py:34, 52` | `budget_initial_montant` | `IntegerField(min_value=0, required=False, allow_null=True)` | E-11 (refus 400 si non habilité) |
| **Entrée PUT/PATCH** | `apps/projets/serializers/swagger.py:195-210` | `budget_initial_montant` | Hérite de `ProjetPostSerializer` | E-11 (refus 400 si non habilité) |
| **Sortie GET détail/liste** | `apps/projets/serializers/__init__.py:164` | `budget_initial_montant` | Exposé dans `ProjetResponseSerializer` | E-11 (masqué sans droit) |
| **Sortie GET détail/liste** | `apps/projets/serializers/__init__.py:147, 165, 199-203` | `budget_consomme_montant` | `SerializerMethodField` calculant `budget * 0.225` (fake 22,5 %) | **E-12 (À RETIRER)** |
| **Sortie Swagger / Formulaire** | `apps/projets/serializers/swagger.py:34, 40, 191` | `budget_initial_montant` | Inclus dans `CHAMPS_REPONSE` de `ProjetCreationResponseSerializer` | E-11 (masqué sans droit) |

**Routes concernées :**
- `POST /api/v1/projets/` (`ProjetListCreateView.post`, `apps/projets/views/__init__.py:152`)
- `GET /api/v1/projets/` (`ProjetListCreateView.get`, `apps/projets/views/__init__.py:125`)
- `GET /api/v1/projets/{pk}/` (`ProjetDetailView.get`, `apps/projets/views/__init__.py:269`)
- `PUT /api/v1/projets/{pk}/` & `PATCH /api/v1/projets/{pk}/` (`ProjetDetailView._modifier`, `apps/projets/views/__init__.py:277`)

---

### 1.2 Ressource : Lot

| Emplacement | Fichier & Lignes | Champ technique | Type & Usage | Règle associée |
|---|---|---|---|---|
| **Modèle** | `apps/projets/models/lot.py:47-49` | `budget_initial_montant` | `BigIntegerField` (centimes FCFA, facultatif) | E-11 |
| **Entrée POST** | `apps/projets/serializers/lot.py:25-31` | `budget_initial_montant` | `IntegerField(required=False, allow_null=True, min_value=0)` | E-11 (refus 400 si non habilité) |
| **Entrée PATCH** | `apps/projets/serializers/lot.py:55` | `budget_initial_montant` | Hérite de `LotCreationSerializer` | E-11 (refus 400 si non habilité) |
| **Sortie GET détail/liste** | `apps/projets/serializers/lot.py:124` | `budget_initial_montant` | Exposé dans `LotResponseSerializer` | E-11 (masqué sans droit) |

**Routes concernées :**
- `POST /api/v1/projets/{pk}/lots/` (`ProjetLotListCreateView.post`, `apps/projets/views/lot.py:101`)
- `POST /api/v1/projets/{pk}/lots/importer/` (`ProjetLotImportView.post`, `apps/projets/views/lot.py:144`)
- `GET /api/v1/projets/{pk}/lots/` (`ProjetLotListCreateView.get`, `apps/projets/views/lot.py:56`)
- `GET /api/v1/lots/{pk}/` (`LotDetailView.get`, `apps/projets/views/lot.py:209`)
- `PATCH /api/v1/lots/{pk}/` (`LotDetailView.patch`, `apps/projets/views/lot.py:228`)

---

### 1.3 Ressource : Activité

| Emplacement | Fichier & Lignes | Champ technique | Type & Usage | Règle associée |
|---|---|---|---|---|
| **Modèle** | `apps/projets/models/activite.py:80-84` | `budget_initial_montant` | `BigIntegerField` (centimes FCFA, facultatif) | E-11 |
| **Entrée POST** | `apps/projets/serializers/activite.py:83-89, 112` | `budget_initial_montant` | `IntegerField(required=False, allow_null=True, min_value=0)` | E-11 (refus 400 si non habilité) |
| **Entrée PATCH** | `apps/projets/serializers/activite.py:206` | `budget_initial_montant` | Hérite de `ActiviteCreationSerializer` | E-11 (refus 400 si non habilité) |
| **Sortie GET détail/liste** | `apps/projets/serializers/activite.py:34` | `budget_initial_montant` | Exposé dans `ActiviteSerializer` | E-11 (masqué sans droit) |

**Routes concernées :**
- `POST /api/v1/lots/{lot_id}/activites/` (`LotActiviteListCreateView.post`, `apps/projets/views/activite.py:106`)
- `GET /api/v1/lots/{lot_id}/activites/` (`LotActiviteListCreateView.get`, `apps/projets/views/activite.py:52`)
- `GET /api/v1/activites/{pk}/` (`ActiviteDetailView.get`, `apps/projets/views/activite.py:181`)
- `PATCH /api/v1/activites/{pk}/` (`ActiviteDetailView.patch`, `apps/projets/views/activite.py:206`)

---

### 1.4 Ressource : Statistiques de projet

| Emplacement | Fichier & Lignes | Champ technique | Type & Usage | Règle associée |
|---|---|---|---|---|
| **Serializer** | `apps/projets/serializers/statistiques.py:10` | `budget_activites_montant` | `IntegerField(help_text="Centimes FCFA.")` | **E-12 (À RETIRER)** |
| **Service de calcul** | `apps/projets/services/statistiques.py:88` | `budget_activites_montant` | `sum(a.budget_initial_montant or 0 for a in activites)` | **E-12 (À RETIRER)** |

**Routes concernées :**
- `GET /api/v1/projets/{pk}/statistiques/` (`ProjetStatistiquesView.get`, `apps/projets/views/statistiques.py:45`)
- Imbriqué dans `ProjetCreationResponseSerializer.get_statistiques()` (`apps/projets/serializers/swagger.py:158-164`)

---

### 1.5 Ressource : Tableau de bord (Dashboard)

| Emplacement | Fichier & Lignes | Champ technique | Type & Usage | Règle associée |
|---|---|---|---|---|
| **Métriques (global)** | `apps/projets/serializers/dashboard.py:47-49` | `budget_total_montant` | `IntegerField` (somme des budgets initiaux réels) | E-11 (masqué sans droit) |
| **Métriques (global)** | `apps/projets/serializers/dashboard.py:50-52` | `budget_engage_montant` | `IntegerField` (fake fixé à 0 en backend) | **E-12 (À RETIRER)** |
| **Métriques (global)** | `apps/projets/serializers/dashboard.py:56-58` | `bons_a_signer_montant` | `IntegerField` (fake fixé à 0 en backend) | **E-12 (À RETIRER)** |
| **Synthèse par projet** | `apps/projets/serializers/dashboard.py:77` | `budget_initial_montant` | `IntegerField(allow_null=True)` (budget réel du projet) | E-11 (masqué sans droit) |
| **Synthèse par projet** | `apps/projets/serializers/dashboard.py:78` | `budget_consomme_montant` | `IntegerField` (consommation fake / vide) | **E-12 (À RETIRER)** |
| **Bons de paiement urgents** | `apps/projets/serializers/dashboard.py:97` | `montant` | `IntegerField(help_text="Montant net en centimes FCFA")` | E-11 (masqué sans droit) |

*(Note : `bons_a_signer_count` ligne 53 est un compteur entier d'objets, pas un montant. Il est conservé).*

**Route concernée :**
- `GET /api/v1/dashboard/` (`DashboardConsolideView.get`, `apps/projets/views/tableau_de_bord.py:34`)

---

## 2. Définition des règles E-11 et E-12

### Règle E-11 : Montants et permission `projets.voir_montants`
1. **Acteurs autorisés :**
   - Rôles détenant `projets.voir_montants` (Annexe 1 et registre RBAC) : **DG**, **DF**, **DO**, **CP**.
   - Ou tout rôle personnalisé pour lequel `projets.voir_montants` est activé.
2. **Acteurs non autorisés :**
   - Rôles système : **AD**, **CT**, **CC**, **MAG**, **BAI**, **VI**.
3. **Comportement en lecture (GET) :**
   - Pour tout utilisateur dépourvu de `projets.voir_montants`, **tous les champs de montants sont absents de la réponse** (clés omises du dictionnaire JSON, pas `null` ni `0`).
   - Champs masqués :
     - Projet : `budget_initial_montant`.
     - Lot : `budget_initial_montant`.
     - Activité : `budget_initial_montant`.
     - Tableau de bord : `budget_total_montant` (dans `metriques`), `budget_initial_montant` (dans `projets`), `montant` (dans `bons_paiement_a_valider`).
4. **Comportement en écriture (POST / PUT / PATCH) :**
   - Pour écrire un montant (création ou modification), l'utilisateur doit disposer de `projets.voir_montants` **ET** de la permission d'écriture de la ressource (`projets.creer`, `projets.ecrire`).
   - Si un utilisateur sans `projets.voir_montants` envoie un champ de montant dans le payload (ex: `budget_initial_montant`), la requête est rejetée avec **HTTP 400 Bad Request** (« champ non accepté »).
   - Exemple du CA : un AD qui crée un projet avec `budget_initial_montant` reçoit 400 ; un CP l'enregistre (201) ; un VI ne reçoit aucun champ de montant (GET).

---

### Règle E-12 : Retrait des champs sans source réelle (Calculs fake)
Les champs suivants sont définitivement retirés des réponses de l'API (n'apparaissent JAMAIS, même pour les utilisateurs ayant `voir_montants`) :
1. `budget_consomme_montant` (ratio fake de 22,5 % dans le détail projet et dans le tableau de bord).
2. `budget_engage_montant` (champ fake dans les métriques du tableau de bord).
3. `bons_a_signer_montant` (champ fake dans les métriques du tableau de bord).
4. `budget_activites_montant` (champ dans `StatistiquesProjetSerializer` et `ProjetCreationResponseSerializer`).
5. La consommation par projet du tableau de bord.

*(Note de compatibilité G-03 : Le frontend gère déjà l'absence de ces clés avec un repli défensif à zéro).*
