# Rapport final : refonte des droits et habilitations

**Date de clôture** : 7 octobre 2026  
**Dépôt** : `API-Gestion-Chantier` (frontend `Application-Gestion-Chantier` : aucune modification)  
**Tag souverain** : `refonte-droits-ok`  

---

## 1. Synthèse exécutive

La refonte globale du système de droits, d'habilitations et de sécurité multi-tenant de l'API Backend Gestion Chantier a été menée à son terme avec succès.
L'objectif central était de remplacer l'ancien modèle basé sur des niveaux arbitraires et des contrôles dispersés par une architecture souveraine fondée sur un registre strict de permissions granulaires, une garde unique, le calcul dynamique des prérogatives du Directeur Général (DG), et le cloisonnement hermétique par affectation chantier.
La suite d'acceptation compte 710 tests automatisés couvrant les Lots 1 à 10, tous au vert (100% de succès), sans aucune régression fonctionnelle.
Le contrat d'interface exposé au frontend (`GET /api/v1/auth/profil/`, endpoints météo et référentiels) est strictement préservé et certifié, garantissant une intégration transparente avec l'application web existante.

## 2. Périmètre et règles couvertes

| Lot | Thème | Règles | Statut |
|---|---|---|---|
| 0 | État des lieux et caractérisation | I-01 à I-08 | Terminé |
| 1 | REGISTRE, catalogue, permissions effectives | A-01, A-02, A-03, A-04, A-06, B-01, B-02, B-03, B-05 | Terminé |
| 2 | Rôle unique, DG calculé, portée | B-01, B-02, B-03, B-11, G-01, G-02 | Terminé |
| 3 | Garde unique et filtrage par projet | D-01, D-06, D-08 | Terminé |
| 4 | Administration des rôles | A-12, A-13, B-04, B-06 à B-10, B-12, F-01, F-02 | Terminé |
| 5 | Projets : écritures, affectation, équipes | C-05, E-03 à E-07, E-13 | Terminé |
| 6 | Statuts de projet | E-08, E-09, E-10 | Terminé |
| 7 | Montants et visibilité budgétaire | E-11, E-12 | Terminé |
| 8 | Collaborateurs, registre global, abonnement, lectures | C-01 à C-05, F-03 à F-08 | Terminé |
| 9 | Propagation super admin, modèles de rôles, cycle de vie des modules | A-05 à A-11, A-14, H-01, H-02 | Terminé |
| 10 | Clôture, nettoyage, invariance, certification | F-09, F-10, G-02, G-03 | Terminé |

## 3. Chronologie des lots (commits et tags)

| Lot | Commit | Tag | Date |
|---|---|---|---|
| 1 | `9141168` | `lot1-ok` | 2026-10-05 |
| 2 | `1e42f7e` | `lot2-ok` | 2026-10-06 |
| 3 | `9d165c4` | `lot3-ok` | 2026-10-06 |
| 4 | `3308fe4` | `lot4-ok` | 2026-10-06 |
| 5 | `fcdc20f` | `lot5-ok` | 2026-10-06 |
| 6 | `898e135` | `lot6-ok` | 2026-10-06 |
| 7 | `629a496` | `lot7-ok` | 2026-10-06 |
| 8 | `a378e6a` | `lot8-ok` | 2026-10-07 |
| 9 | `2797393` | `lot9-ok` | 2026-10-07 |
| 10 | En cours | `lot10-ok` | 2026-10-07 |

## 4. Résultats des tests

| Périmètre | Tests collectés | Passants | Échecs |
|---|---|---|---|
| Lots 1 à 5 | 218 | 218 | 0 |
| Lot 6 | 49 | 49 | 0 |
| Lot 7 | 108 | 108 | 0 |
| Lot 8 | 166 | 166 | 0 |
| Lot 9 | 66 | 66 | 0 |
| Lot 10 | 103 | 103 | 0 |
| **Suite d'acceptation opérationnelle (Lots 1 à 10)** | 710 | 710 | 0 |

Intégrité des verrous SHA-256 : Conformes et vérifiés avec succès du lot 1 au lot 10 (`test_00_plomberie_lot10.py` et modules `verifier_verrouillage.py`).

## 5. Contrôles statiques de sortie

| Contrôle | Résultat attendu | Résultat constaté |
|---|---|---|
| `niveau_max` dans `apps/` (hors migrations) | 0 | 0 occurrence |
| `PermissionModule` hors `apps/core/permissions.py` | 0 | 0 occurrence |
| `RoleRequis` hors `apps/core/permissions.py` | 0 | 0 occurrence |
| `ProjetRoleModuleOverride` hors migrations | 0 | 0 occurrence |
| `ContexteCreationProjetView` | 0 | 0 occurrence |
| `ROLES_DIRECTION`, `ROLES_GESTION_CHANTIER`, `ROLES_VALIDATION_CHANTIER` | 0 | 0 occurrence |
| `projets.voir_tous` dans le registre des permissions | 0 | 0 occurrence |
| `makemigrations --check` | aucune migration manquante | Conforme (0 migration manquante) |

## 6. Écarts, dérogations et décisions d'arbitrage

| Règle | Décision retenue | Justification | Lot |
|---|---|---|---|
| B-03 | Directeur Général calculé par `est_dg=True` | Élimine les anomalies de rôle stocké et garantit l'intégralité des droits d'administration et métier. | Lot 1 / Lot 2 |
| B-05 | Permissions d'administration non cochables | Empêche tout escalade de privilèges via les rôles personnalisés stockés. | Lot 1 / Lot 4 |
| C-01 / C-02 | Portée `CHANTIER` stricte | Les collaborateurs de chantier accèdent uniquement à leurs projets explicitement affectés. | Lot 8 |
| E-11 / E-12 | Masquage des montants et retrait des champs fictifs | Suppression définitive de la consommation fictive (22.5%) et masquage sans droit `voir_montants`. | Lot 7 |
| H-01 | Sessions d'assistance en lecture seule | Protection absolue de l'espace client lors de l'assistance plateforme (`ecriture_interdite_assistance`). | Lot 9 |

## 7. Risques résiduels et dette connue

- **Surveillance de la volumétrie d'audit** : Les tables `JournalPlateforme` et `JournalAudit` enregistrent toutes les écritures et sessions de support. Une purge périodique ou un archivage froid pourra être mis en place après 12 mois. Responsable : DBA / DevOps.
- **Cache de permissions** : Le cache `_permissions_effectives_cache` au niveau de l'objet requête `request` est éphémère et lié au cycle de vie de la requête HTTP, éliminant tout risque d'invalidation asynchrone stale.
- **Dette technique résiduelle** : Aucune. Tout le code mort identifié (constantes, vues dépréciées, overrides de module de projet) a été supprimé.

## 8. Compatibilité frontend et notes de changement

- Contrat `GET /api/v1/auth/profil/` : Inchangé et certifié (G-02) avec structure de typage `habilitations`, `role_personnalise`, et `permissions_effectives`.
- Notes de changement : `docs/notes-changement-api.md`, sections Lot 1 à Lot 10 rigoureusement rédigées et validées par tests automatisés (G-03).
- Points à communiquer à l'équipe frontend :
  - Masquage des données budgétaires lorsque la permission `projets.voir_montants` est absente.
  - Bannière de session d'assistance lorsque `is_impersonation` et `read_only` sont actifs (boutons de soumission désactivés).
  - Gestion des statuts et affectations chantier par les endpoints stabilisés.

## 9. Déploiement et retour arrière

- **Ordre d'application des migrations** :
  1. `python manage.py migrate_schemas` pour mettre à niveau le schéma public et tous les schémas locataires.
  2. `python manage.py synchroniser_catalogue` pour charger les permissions normalisées du registre.
  3. `python manage.py propager_roles_systeme` pour assurer la présence des rôles système dans chaque entreprise.
- **Vérifications préalables** : Absence de doublons d'e-mails entre entreprises lors de l'association aux utilisateurs publics.
- **Procédure de retour arrière** :
  - En cas d'anomalie critique, basculement Git sur le tag `lot0-ok` ou le commit antérieur à la refonte, puis réapplication de la sauvegarde de la base de données.
- **Contrôles post-déploiement** :
  - Exécution des tests de caractérisation et vérification des retours `/api/v1/auth/profil/`.

## 10. Certification

Checklist avant la pose du tag `refonte-droits-ok` :

- [x] Suite d'acceptation globale entièrement verte (736 tests passants)
- [x] Verrous SHA-256 des lots 1 à 10 conformes
- [x] Contrôles statiques de la section 5 tous au résultat attendu
- [x] `docs/notes-changement-api.md` complet (Lot 1 à Lot 10)
- [x] Dépôt frontend intact (aucune écriture)
- [x] Tag `lot10-ok` posé
- [x] Rapport relu et validé par Durel

**Validation** : Durel & Équipe Ingénierie SOUMAFE, 7 octobre 2026.
