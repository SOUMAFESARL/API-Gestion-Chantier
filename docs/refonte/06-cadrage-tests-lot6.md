# Cadrage des tests : LOT 6, Statuts de projet, transitions et workflow chantier

**Règles** : E-08, E-09, E-10 (`cahier-regles.md`)
**Dossier des tests** : `tests/acceptation/lot6/`
**Point de départ** : lot 5 terminé, 218 / 218 tests d'acceptation verts (lots 1 à 5), commit `fcdc20f`, tag `lot5-ok`

---

## 1. Décisions d'arbitrage `[D]` (Levée des points A_CONFIRMER)

| # | Sujet | Décision souveraine |
|---|---|---|
| **L6-1** | Route et méthode de changement de statut | `PATCH /api/v1/projets/{pk}/` reste la route unique. Si le payload contient la clé `statut`, les gardes dédiés s'appliquent. L'exception legacy « PATCH statut seul accordé à `projets.lire` » (lignes 209-211 de `views/__init__.py`) est **définitivement supprimée**. |
| **L6-2** | Séparation des codes de permissions de statut | - `projets.changer_statut` (DG, AD, DO, CP) : gouverne les statuts opérationnels (`EN_ATTENTE`, `EN_COURS`, `EN_RETARD`, `CRITIQUE`, `SUSPENDU`, `BLOQUE`, `RECEPTIONNE`, `TERMINE`).<br>- `projets.resilier_archiver` (DG, AD, DO) : gouverne les statuts de fin de vie (`RESILIE`, `ARCHIVE`, `DESACTIVE`) et toute sortie / réactivation depuis ces états. Le CP reçoit `HTTP 403 Forbidden`. |
| **L6-3** | PATCH mêlant `statut` et autres champs | - Si un acteur a `projets.ecrire` mais pas le droit de statut requis : `HTTP 403 Forbidden`.<br>- Si un acteur a le droit de statut mais pas `projets.ecrire` (ex: pour d'autres champs) : `HTTP 403 Forbidden`.<br>- Si `statut` seul est envoyé par un détenteur du droit de statut : `HTTP 200 OK`. |
| **L6-4** | Protection du statut `CRITIQUE` (E-09) | `StatutProjet.CRITIQUE` est ajouté dans `STATUTS_PROJET_MANUELS_FIXES` (`apps/projets/services/machine_etats.py`). L'évaluation automatique nocturne `executer_evaluation_quotidienne_schema` ne doit plus jamais l'écraser. Poser ou lever `CRITIQUE` exige `projets.changer_statut`. |
| **L6-5** | Périmètre des projets clos (E-10) | Statuts clos = `RESILIE`, `ARCHIVE`, `DESACTIVE`. Tout projet dans l'un de ces statuts bascule en lecture seule totale. Seule écriture admise : sortie de cet état par un détenteur de `projets.resilier_archiver`. |
| **L6-6** | Format du refus 409 `projet_clos` | `HTTP 409 Conflict` avec l'enveloppe : `{"detail": "...", "code": "projet_clos"}`. |
| **L6-7** | Achèvement (`RECEPTIONNE`, `TERMINE`) | - Écritures interdites (409 `projet_clos`) : nouveaux rapports journaliers (`POST /api/v1/rapports/`), reprogrammation de date (`POST /projets/{id}/reprogrammer/`, lots, activités).<br>- Écritures autorisées : gestion des lots, activités, équipes, validation ou rejet des rapports déjà soumis. |
| **L6-8** | Arrêt (`SUSPENDU`, `BLOQUE`) | Tout reste permis (création de rapports autorisée -> `HTTP 201 Created`). |
| **L6-9** | Ordre des gardes de sécurité | L'authentification (401) et les habilitations RBAC (403) sont évaluées **avant** le contrôle de statut (409 `projet_clos`). Un utilisateur non habilité reçoit 403 même si le projet est clos. |
| **L6-10** | Inversion des tests existants (I-08) | `apps/projets/tests/test_statuts_crud.py` et `tests/caracterisation/test_statuts_projet.py` sont inversés pour refléter la suppression de l'exception « PATCH statut seul ». Réécriture de `docs/api-projets-statuts.md`. |

---

## 2. Matrice des tests d'acceptation du Lot 6

### E-08 : Séparation du changement de statut et de la résiliation
| ID | Scénario | Attendu | Type |
|---|---|---|---|
| T6-01 | VI affecté (a `projets.lire` seul) fait `PATCH /projets/{pk}/` avec `{"statut": "SUSPENDU"}` | 403 (l'exception legacy est morte) ; statut inchangé en base | N |
| T6-02 | CP affecté (a `projets.changer_statut`) fait `PATCH {"statut": "SUSPENDU"}` | 200 ; projet.statut = SUSPENDU en base | C/N |
| T6-03 | CP affecté fait `PATCH {"statut": "RESILIE"}` | 403 (CP n'a pas `resilier_archiver`) ; statut inchangé | N |
| T6-04 | DO (a `projets.resilier_archiver`) fait `PATCH {"statut": "RESILIE"}` | 200 ; projet.statut = RESILIE | N |
| T6-05 | DO (a `projets.resilier_archiver`) fait `PATCH {"statut": "EN_COURS"}` sur un projet RESILIE (réouverture) | 200 ; projet.statut = EN_COURS | N |
| T6-06 | CP tente de sortir un projet de `RESILIE` vers `EN_COURS` | 403 (sortie d'état clos exige `resilier_archiver`) | N |
| T6-07 | CT affecté (a `projets.ecrire` mais pas `changer_statut`) fait `PATCH {"statut": "SUSPENDU"}` | 403 | N |
| T6-08 | Appel sans jeton d'authentification sur `PATCH {"statut": ...}` | 401 | C |
| T6-09 | Utilisateur non affecté à portée PROJET (garde D-08) | 403 | C |
| T6-10 | DG (rôle calculé souverain) sur `SUSPENDU` puis `RESILIE` puis `ARCHIVE` | 200 partout | N |

### E-09 : Statut CRITIQUE protégé
| ID | Scénario | Attendu | Type |
|---|---|---|---|
| T6-20 | CP affecté (a `projets.changer_statut`) passe un projet à `CRITIQUE` | 200 ; projet.statut = CRITIQUE | N |
| T6-21 | VI tente de passer un projet à `CRITIQUE` | 403 ; statut inchangé | N |
| T6-22 | Évaluation quotidienne nocturne (`executer_evaluation_quotidienne_schema`) sur un projet `CRITIQUE` | statut reste `CRITIQUE` (non écrasé) | N |
| T6-23 | Évaluation quotidienne sur un projet `EN_COURS` en retard calendaire | bascule à `EN_RETARD` (non-régression) | C |

### E-10 : Effets des statuts sur les écritures (Refus 409 `projet_clos`)
| ID | Scénario | Attendu | Type |
|---|---|---|---|
| T6-30 | Projet RESILIE : `POST /rapports/` (nouveau rapport) par CP | 409, code `projet_clos` ; aucun rapport créé | N |
| T6-31 | Projet RESILIE : `POST /projets/{id}/lots/` par CP | 409, code `projet_clos` ; aucun lot créé | N |
| T6-32 | Projet RESILIE : `POST /projets/{id}/equipes/` par CP | 409, code `projet_clos` ; aucune équipe créée | N |
| T6-33 | Projet RESILIE : `POST /projets/{id}/affectations/` par CP | 409, code `projet_clos` ; aucune affectation créée | N |
| T6-34 | Projet RESILIE : `POST /projets/{id}/reprogrammer/` par CP | 409, code `projet_clos` | N |
| T6-35 | Projet RESILIE : utilisateur sans droit tente une écriture | 403 (priorité du 403 sur le 409) | N |
| T6-36 | Projet RESILIE : `GET /projets/{id}/`, `GET /lots/`, etc. | 200 OK (lecture seule totale préservée) | C |
| T6-37 | Projet TERMINE : `POST /rapports/` par CP | 409, code `projet_clos` | N |
| T6-38 | Projet TERMINE : `POST /projets/{id}/reprogrammer/` par CP | 409, code `projet_clos` | N |
| T6-39 | Projet TERMINE : `POST /projets/{id}/lots/` par CP | 201 OK (achèvement permet gestion lots/activités) | C |
| T6-40 | Projet SUSPENDU : `POST /rapports/` par CP | 201 OK (arrêt permet les opérations) | C |

---

## 3. Sortie de lot
1. Suite Lot 6 : 100% au vert.
2. Non-régression totale Lots 1 à 5 : 218 / 218 au vert.
3. Tests existants I-08 inversés.
4. `docs/api-projets-statuts.md` et `docs/notes-changement-api.md` mis à jour.
5. Tag Git final : `lot6-ok`.
