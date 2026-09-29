# CRUD des projets — Sprint 3, tâche CRUD_PROJETS

## 1. Visualiser le résultat

Créer ZRAN avec ses informations, ses lots et son équipe, le retrouver dans
la liste, modifier ses informations et le retirer des projets actifs.
Prédire chaque réponse HTTP avant de lancer la requête : cette boucle
prédiction, essai, correction sert d'exercice d'apprentissage actif.

## 2. Architecture et invariants

Le contrat de création à trois étapes reste celui de `docs/api-creation-projet.md`.
Les routes sont authentifiées, isolées par schéma d'entreprise et soumises
aux permissions du module PROJETS. La modification et la suppression
requièrent aussi l'accès au projet. La suppression est logique : l'historique
reste en base, avec l'auteur et la date, mais le projet disparaît de la liste.

| Méthode | Route | Résultat |
| --- | --- | --- |
| POST | /api/v1/projets/ | Création, 201 |
| GET | /api/v1/projets/ | Liste accessible, 200 |
| GET | /api/v1/projets/{id}/ | Détail, 200 |
| PATCH | /api/v1/projets/{id}/ | Modification partielle, 200 |
| DELETE | /api/v1/projets/{id}/ | Suppression logique, 204 |

PATCH conserve les champs absents. Les responsables peuvent être modifiés
par leurs UUID ; `conducteur_travaux_id: null` retire le conducteur.
Le chef reste obligatoire. Les nouvelles affectations sont synchronisées,
les anciennes affectations des responsables remplacés sont désactivées.
Les listes d'équipe se gèrent avec les routes d'affectations existantes.
Les lots sont ajoutés en PATCH avec `lots` et supprimés avec
`lots_supprimer_ids` (voir `api-lignes-lots.md`). Les invitations imbriquées
ne sont pas acceptées en PATCH et produisent une erreur explicite.
Le formulaire de création conserve ses lots et ses invitations imbriqués.

## 3. Implémentation pas à pas

1. Dans la vue détail, ajouter DELETE avec les permissions existantes.
2. Charger le projet actif, vérifier les permissions objet, puis appeler
   `projet.delete(utilisateur=request.user)` et répondre sans corps en 204.
3. Dans la validation PATCH, valider les lots ajoutés et refuser les champs
   d'équipe non pris en charge. Vérifier les responsables actifs du schéma courant,
   leur éligibilité et l'absence de cumul de rôles.
4. Encapsuler la modification dans une transaction ; utiliser le service
   d'affectation pour réactiver une affectation historique si nécessaire.
5. Distinguer un champ absent d'un champ nul : seul le second retire le CT.
6. Garder la référence inchangée si elle n'est pas envoyée ; refuser une
   référence vide en modification et les doublons.

Exemple :

```json
{"nom": "ZRAN - phase 2", "conducteur_travaux_id": null}
```

Pour les trois écrans : un POST final utilise le corps documenté dans
`api-creation-projet.md`. Le maître d'ouvrage est un UUID de tiers,
le budget est en centimes de FCFA, la fin doit suivre le début.
Directeur financier et bailleurs ne font pas partie du contrat actuel.
Les captures illustrent le besoin ; elles ne remplacent pas les invariants
du backend (notamment des personnes distinctes pour CP et CT).

## 4. Pré-mortem et retour d'erreur

- Suppression physique : perte d'historique. Vérifier `tous_objets` après DELETE.
- Champs ignorés : formulaire apparemment enregistré. Refuser les entrées
  non prises en charge plutôt que les éliminer silencieusement.
- Ancien responsable encore autorisé : vérifier son affectation après changement.
- Compte d'une autre entreprise ou inactif : refuser avant toute écriture.
- Date de fin invalide : vérifier le PATCH d'une seule date contre la date conservée.

## 5. Validation

Exécuter les tests du CRUD et les tests existants de création et de détail.
Vérifier POST 201, GET/PATCH 200, DELETE 204, puis GET/PATCH/DELETE 404.
Tester un utilisateur non affecté et un anonyme ; aucune suppression ne
doit avoir lieu. Vérifier la conservation des lots et de l'historique en base.
Les résultats réellement exécutés sont rapportés séparément à la livraison.

## 6. Défi de transmission

Expliquer pourquoi DELETE renvoie 204 alors que la ligne reste en base,
et pourquoi `null` et l'absence d'un champ ne signifient pas la même chose.
Reproduire ensuite un test sans son modèle, comparer le résultat attendu
au résultat observé, puis reprendre l'exercice le lendemain. La visualisation
est ici un outil de préparation ; la preuve du fonctionnement vient des tests.
