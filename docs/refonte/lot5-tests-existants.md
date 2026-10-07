# Inventaire des tests existants à adapter ou supprimer (Lot 5 - Prérequis L5-10)

Document établi conformément au protocole de refonte (Règles G-05, E-03, E-05, E-06, E-13).

---

## 1. Tests de la vue supprimée `ContexteCreationProjetView` (Règle E-13)

La règle **E-13** exige la suppression pure et simple de la vue `ContexteCreationProjetView`, de sa route `projets/contexte-creation/`, de son serializer et de ses tests.

| Fichier | Lignes | Nature | Raison |
|---|---|---|---|
| `apps/projets/tests/test_contexte_creation.py` | 1 à 257 (intégralité du fichier) | **Suppression** | Ce fichier teste exclusivement la route `/api/v1/projets/contexte-creation/` appelée par différents rôles. La route et la vue étant supprimées (E-13), le fichier de test doit être supprimé. |
| `apps/projets/tests/test_swagger_crud_only.py` | 71 | **Adaptation** | La liste des routes auditées contient `"/api/v1/projets/contexte-creation/"`. Retirer cette route de la liste des routes attendues. |

---

## 2. Tests de surcharge des permissions par projet et clé `AffectationProjet.role` (Règle E-06)

La règle **E-06** supprime le modèle `ProjetRoleModuleOverride`, la route `/projets/{id}/permissions-roles/` et la clé étrangère `AffectationProjet.role`.

| Fichier | Lignes | Nature | Raison |
|---|---|---|---|
| `apps/accounts/tests/test_alignement_entreprise_frontend.py` | 249 à 306 (`test_projets_permissions_roles_override_frontend_format`) | **Suppression ou Adaptation** | Teste `GET` et `PUT` sur `/api/v1/projets/{projet.id}/permissions-roles/`. La route et le service étant supprimés, l'endpoint renverra désormais un 404 (attendu par E-06). |
| `apps/projets/tests/test_swagger_crud_only.py` | 73 | **Adaptation** | La liste des routes auditées contient `"/api/v1/projets/00000000-0000-0000-0000-000000000001/permissions-roles/"`. Retirer cette route de la liste. |
| `apps/accounts/tests/test_roles_dg.py` | 241 (`assert affectation.role == role_ct`) | **Adaptation** | Vérifiait que la suppression d'un rôle réassignait `affectation.role`. Comme `AffectationProjet.role` disparaît, cette assertion doit être retirée (l'affectation reste active, mais n'a plus de rôle personnalisé associé). |
| `apps/projets/tests/test_lots_activites_mutations.py` | 270 | **Adaptation** | Création directe d'une affectation avec l'argument nommé `role=role` : `AffectationProjet.objects.create(projet=projet, utilisateur=user, role=role, role_projet=RoleProjet.VISITEUR)`. Retirer `role=role` pour éviter un `TypeError` une fois le champ supprimé du modèle. |

---

## 3. Tests des droits sur les équipes (Règles E-03 et E-07)

La règle **E-03** impose que la création, modification, suppression et composition des équipes soient protégées par la permission `projets.gerer_equipes`. La seule appartenance au projet ne suffit plus pour modifier ou créer une équipe.

| Fichier | Lignes | Nature | Raison |
|---|---|---|---|
| `apps/projets/tests/test_equipes_chantier_api.py` | 19, 25, 55-56 | **Adaptation** | La fixture crée un utilisateur portant le rôle `RoleGlobal.VISITEUR` (VI) et `RoleProjet.VISITEUR`, et la ligne 55 attend `assert created.status_code == 201` sur `POST /equipes/`. Or, selon le cahier des charges E-03, le rôle VI ne détient pas `projets.gerer_equipes` et doit recevoir un **403 Forbidden**. Le test doit utiliser un rôle habilité (CP ou CT) pour vérifier la création (201), et conserver le test du VI pour vérifier le refus 403. |

---

## 4. Tests d'affectation et garde `role_projet == CHEF_PROJET` (Règle E-05)

La règle **E-05** supprime le garde par étiquette `role_projet == CHEF_PROJET`. L'affectation exige désormais la permission souveraine `projets.affecter_membres` et (portée ENTREPRISE ou affectation active).

| Fichier | Lignes | Nature | Raison |
|---|---|---|---|
| `apps/projets/tests/test_affectations_equipe.py` | 8, 50-60, 110-120 | **Adaptation** | Le test supposait que la gestion des affectations était réservée à l'administrateur, au DG et au CP du chantier via `_verifier_droits_gestion_equipe`. Il doit être aligné avec la nouvelle garde `projets.affecter_membres` (par exemple un CT même avec l'étiquette CHEF_PROJET se voit refuser l'affectation s'il n'a pas la permission `projets.affecter_membres`). |
| `apps/projets/tests/test_chef_projet_optionnel.py` | 146, 179 | **À conserver** | Ces tests valident que le chef de projet est optionnel sur le chantier et que la synchronisation de `projet.chef_projet` avec les affectations fonctionne. Ces invariants sont conservés par E-06. |

---

## 5. Synthèse quantitative des impacts

- **Fichiers de tests à supprimer :** 1 (`apps/projets/tests/test_contexte_creation.py`)
- **Fichiers de tests existants à adapter :** 5 (`apps/accounts/tests/test_alignement_entreprise_frontend.py`, `apps/projets/tests/test_swagger_crud_only.py`, `apps/accounts/tests/test_roles_dg.py`, `apps/projets/tests/test_lots_activites_mutations.py`, `apps/projets/tests/test_equipes_chantier_api.py`)
- **Impact sur le code de production :**
  - Suppression de `apps/projets/views/contexte_creation.py` et `apps/projets/serializers/contexte_creation.py`.
  - Suppression de `apps/projets/models/override.py`, `apps/projets/views/override.py`, `apps/projets/services/overrides.py` et du champ `AffectationProjet.role`.
  - Nettoyage des routes associées dans `apps/projets/urls.py`.
