---
name: revue-backend
description: >-
  Relit un changement du backend CCD Digital (diff en cours, branche, commit, PR) contre les règles
  propres à ce dépôt : isolation multi-tenant, suppression logique, montants, droits, contrats d'API.
  À utiliser quand on demande une revue ou une relecture de code Django de ce dépôt, avant un merge
  dans develop, ou à la question « est-ce que ce code est bon ? ».
---

# Revue d'un changement backend

Une revue générique trouve ce que `ruff` trouve déjà. Celle-ci cherche ce qu'aucun outil ne voit :
les défauts qui tiennent à l'architecture de ce produit.

## 1. Délimiter

```bash
git diff develop...HEAD --stat     # une branche
git diff                           # le travail en cours
```

Lire le diff, puis **les fichiers voisins** de chaque modification : un défaut est rarement dans la
ligne changée, plus souvent dans ce qu'elle suppose de son appelant.

## 2. Chercher, du plus coûteux au moins coûteux

**Isolation des données — bloquant**
- Nouvelle application : rangée dans `TENANT_APPS` ou `SHARED_APPS` à dessein ?
- Tâche Celery : reçoit le schéma et ouvre `schema_context` ?
- Clé de cache portant une donnée d'un client : contient le schéma ?
- Clé de fichier : préfixée par le schéma ? URL stockée en base au lieu de la clé ?

**Droits — bloquant**
- Chaque vue nouvelle déclare une permission au-delà de `IsAuthenticated`.
- La **liste** est filtrée par affectations, pas seulement le détail.
- Dans une `APIView`, `check_object_permissions` est bien appelé sur l'objet chargé.

**Socle Commun — bloquant**
- Modèle qui n'hérite pas de `ModeleBase`, ou suppression physique.
- Journal d'audit modifié ou supprimé (il est en insertion seule).
- Montant hors `MontantField`, ou calculé en `float`.
- Texte affiché à l'utilisateur sans `_("…")`.

**Justesse**
- Écriture multi-tables hors `transaction.atomic()` ; course possible sans `select_for_update()`.
- `update_fields` : chaque nom existe-t-il sur le modèle ?
- Cas limites : liste vide, valeur nulle, objet supprimé logiquement, deuxième appel identique.
- Erreur métier levée par une sous-classe d'`ErreurMetier`, pas une `Response` bricolée.

**Structure**
- `views.py` / `models.py` créé à côté du paquet du même nom : ignoré sans message.
- Règle de gestion dans une vue ou un serializer plutôt que dans `services/`.
- N+1 : requête dans un `SerializerMethodField` ou dans une boucle.

**Migrations**
- Une migration accompagne chaque changement de modèle ; aucune migration déjà appliquée n'est
  réécrite.
- Une migration de données fonctionne sur un schéma vide comme sur un schéma peuplé.

**Contrat d'API**
- Champ renommé ou retiré : chercher qui le lit dans `../Application-Gestion-Chantier` avant de
  conclure qu'il est libre.
- `@extend_schema` à jour.

**Tests**
- Chaque règle nouvelle a un test qui échoue sans elle.
- Les tests métier s'exécutent dans un schéma (`schema_demo`).

## 3. Vérifier plutôt que supposer

```bash
ruff check apps/<module>
pytest apps/<module>/tests/ -v
```

Un soupçon se confirme en lisant le code appelé ou en lançant le test, pas en le formulant au
conditionnel.

## 4. Restituer

Par ordre de gravité — **bloquant**, **à corriger**, **suggestion** — et pour chaque constat :

- `fichier:ligne` ;
- le scénario concret : quelle entrée ou quel état produit quel mauvais résultat ;
- la correction proposée.

Ne pas signaler ce que `ruff` formate ou corrige seul. Terminer par ce qui **n'a pas** été vérifié
(tests non lancés, module non lu) : une revue qui ne dit pas ses limites passe pour complète.
