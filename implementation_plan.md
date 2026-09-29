# Mise à jour Swagger — proposition à valider

## Constats

- La documentation est générée par drf-spectacular et exposée sur `/api/v1/docs/` et `/api/v1/schema/`.
- Deux routages existent : `config.urls_public` et `config.urls_tenant`.
- La description globale annonce une pagination `count/next/previous/results`, alors que `PaginationStandard` renvoie `total/page/nombre_pages/suivant/precedent/resultats`.
- La description annonce du JSON pour toutes les ressources alors que des endpoints servent des PDF.

## Périmètre proposé

Actualiser la documentation des routes existantes sans modifier les règles métier. Conserver la distinction public/tenant. Aucun déploiement prévu.

## Composants

- [MODIFY] `config/settings/base.py` : corriger les conventions décrites, vérifier les indications JWT et multi-tenant contre leur implémentation.
- [MODIFY si nécessaire] `config/urls_public.py`, `config/urls_tenant.py` : assurer que chaque schéma documente le routage correspondant.
- [MODIFY si nécessaire] annotations des vues et serializers des endpoints routés : corriger les omissions et avertissements constatés lors de la génération, préciser requêtes, réponses et paramètres.
- [NEW] `apps/core/tests/test_schema.py` : couverture des schémas public et tenant, des routes attendues et des contrats corrigés.
- [NEW] `walkthrough.md` : bilan et résultats des vérifications.

## Réalisation après validation

1. Créer une branche dédiée depuis `develop` à jour, en préservant les changements locaux éventuels.
2. Générer et valider les deux schémas pour établir les anomalies exactes.
3. Appliquer les corrections documentaires nécessaires.
4. Exécuter les tests ciblés du schéma et les tests existants des contrats concernés, notamment les factures.
5. Vérifier les chemins, la pagination, les réponses PDF et la sécurité JWT dans le schéma produit ; contrôler Swagger dans le navigateur si un serveur est disponible.
6. Commit et intégration locale dans `develop`, suppression de la branche dédiée conformément au workflow du projet.

## Validation attendue

Accord sur ce périmètre avant modification du code, conformément au skill sprint-task-lifecycle.

---

# API structure projet — proposition à valider

## Constats et périmètre

- `Projet` et `Lot` existent dans le schéma tenant. Les routes projets proposent déjà GET/POST et GET/PATCH sur le détail.
- Aucune route de gestion des lots, activités ou baselines n'est actuellement exposée.
- `UniteMesure` définit déjà M2/m², ML/ml, M3/m³, KG/kg, U/u et FORFAIT/forfait : réutiliser ce référentiel fermé.
- Compléter les modèles et migrations puis exposer une API DRF documentée dans Swagger.
- Arbitrage utilisateur validé : baseline v0 créée automatiquement dès la création du projet, dans la même transaction.

## Contrat proposé sous /api/v1/

- Conserver les routes existantes `projets/` et `projets/{id}/`.
- GET/POST `projets/{projet_id}/lots/` : liste et création.
- GET/PATCH/DELETE `projets/{projet_id}/lots/{lot_id}/` : détail, modification et suppression logique ; refuser la suppression d'un lot contenant des activités actives.
- GET/POST `projets/{projet_id}/lots/{lot_id}/activites/` : liste et création.
- GET/PATCH/DELETE `projets/{projet_id}/lots/{lot_id}/activites/{activite_id}/` : détail, modification et suppression logique.
- GET `projets/referentiels/unites/` : codes et libellés des six unités autorisées.
- GET `projets/{projet_id}/baseline/` : consultation de la référence initiale.
- Aucun POST manuel de baseline : la v0 est créée automatiquement avec le projet et consultable en lecture seule. Les projets antérieurs sans baseline renvoient une absence explicite (404), sans inventer leur état historique.

## Données et règles

- Activité : lot, code unique parmi les activités non supprimées du lot, libellé, unité normalisée, quantité prévue décimale, prix unitaire en centimes de FCFA, dates prévues et ordre.
- Baseline : projet, version 0, auteur et date de création, copie des données initiales du projet. La création actuelle de projet ne reçoit pas de lots/activités : leurs collections initiales sont donc vides, sans reconstruction ultérieure de l'historique.
- Conserver les valeurs de référence malgré les modifications ou suppressions logiques ultérieures de la structure courante.
- Contraintes sur unités, valeurs positives ou nulles et cohérence des dates ; cohérence des relations projet/lot/activité vérifiée sur chaque route.
- Authentification et isolation tenant, avec application des permissions projet selon les mécanismes existants après inspection ciblée.
- Création de la baseline transactionnelle, unicité en base et protection contre les créations concurrentes.

## Fichiers

- [NEW] `apps/projets/models/activite.py`, `apps/projets/models/baseline.py` et migration Django correspondante.
- [MODIFY] `apps/projets/models/__init__.py` : export des nouveaux modèles.
- [MODIFY] `apps/projets/serializers/__init__.py` : création automatique de la baseline dans la transaction de création du projet.
- [NEW] `apps/projets/serializers/structure.py`, `apps/projets/views/structure.py` : contrats, validations et annotations OpenAPI.
- [NEW] `apps/projets/services/structure.py`, `apps/projets/selectors/structure.py` : écritures transactionnelles et lectures limitées au projet concerné.
- [MODIFY] `apps/projets/urls.py` : nouvelles routes.
- [NEW] `apps/projets/tests/test_structure.py` : tests modèles/services/API.
- [NEW] `docs/api-structure-projet.md` : endpoints et exemples JSON.
- [NEW ou MODIFY] `walkthrough.md` : réalisation et résultats de validation.

## Vérifications et intégration après validation

1. Créer une branche feature depuis develop à jour en préservant les fichiers locaux existants.
2. Générer les migrations ; vérifier leur cohérence et les appliquer à une base locale de test disponible.
3. Tester CRUD, unités invalides, dates/quantités/prix invalides, unicité, suppression logique et relations entre projets.
4. Tester authentification, permissions, isolation tenant, copie fidèle et immutabilité de la baseline, doublons et atomicité.
5. Exécuter les tests du module projets et vérifier la génération du schéma OpenAPI.
6. Commit ciblé, intégration locale dans develop et suppression de la branche feature ; documenter les résultats et toute limite de vérification.

## Validation attendue

Déclenchement automatique validé par l'utilisateur. Accord explicite attendu sur ce plan avant modification du code, conformément au skill sprint-task-lifecycle.
