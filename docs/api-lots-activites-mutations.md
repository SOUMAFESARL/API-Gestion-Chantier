# Modification, suppression et activation des lots et activités

| Opération | Lot | Activité |
| --- | --- | --- |
| Détail | GET `/api/v1/lots/{id}/` | GET `/api/v1/activites/{id}/` |
| Modification partielle | PATCH `/api/v1/lots/{id}/` | PATCH `/api/v1/activites/{id}/` |
| Suppression logique | DELETE `/api/v1/lots/{id}/` | DELETE `/api/v1/activites/{id}/` |
| Activation ou désactivation | PATCH `/api/v1/lots/{id}/activation/` | PATCH `/api/v1/activites/{id}/activation/` |

GET exige la lecture du module Projets ; les mutations exigent l'écriture.
L'accès au projet parent reste contrôlé par les permissions existantes.
Ces routes vivent dans le schéma tenant ; authentifier un compte de l'entreprise.

PATCH renvoie 200 et l'objet actualisé. Envoyer uniquement les champs modifiés :
`{"nom": "Fondations"}` pour un lot ou `{"libelle": "Terrassement"}` pour une activité.
Le serializer accepte les mêmes champs métier que la création. Les champs inconnus
ou calculés, le parent, l'UUID et la baseline sont refusés.
Budget en centimes FCFA. L'équipe et la quantité restent intactes si elles sont absentes.
La quantité prévue ne peut pas être abaissée sous le réalisé.

Les dates prévisionnelles déjà renseignées passent par
POST `/api/v1/lots/{id}/reprogrammer/` ou
POST `/api/v1/activites/{id}/reprogrammer/` (motif et justification, RG-11).
Un premier renseignement d'une date vide reste possible ; la baseline est alors initialisée.
Les dates réelles du lot sont modifiables avec contrôle chronologique.

Activation : `{"est_actif": false}` ou `{"est_actif": true}` ; champ obligatoire.
La répétition du même état est idempotente. Désactiver un lot ne change pas l'état
individuel de ses activités. Un lot désactivé refuse les nouvelles activités et
la réactivation d'une activité ; réactiver le lot au préalable.

DELETE renvoie 204 sans corps et conserve la ligne avec son acteur de suppression.
Un lot contenant des activités non supprimées renvoie 400 : supprimer les activités
au préalable ou désactiver le lot. Une activité ayant des successeurs non supprimés
renvoie 400 : retirer les dépendances auparavant. Un objet supprimé ou dont le
parent est supprimé renvoie 404. Aucun changement de schéma n'est nécessaire.

Les mutations et la création d'activités verrouillent le projet puis le lot
(puis l'activité pour sa mutation) dans une transaction. Cela sérialise les
modifications des dépendances entre lots du même projet.

Swagger : les tags `lots` et `activités` exposent ces opérations avec exemples,
schémas d'entrée et réponses 200/204/400/401/403/404. Vérifier le déploiement effectif
avant de s'attendre à leur apparition sur le serveur.

Validation sans base :
`python -m pytest apps/projets/tests/test_lots_activites_validation.py apps/projets/tests/test_swagger_crud_only.py -q`

Validation PostgreSQL :
`python -m pytest apps/projets/tests/test_lots_activites_mutations.py apps/projets/tests/test_lots_api.py apps/projets/tests/test_activites_formulaire.py -q --reuse-db`

Apprentissage actif : prédire chaque réponse avant le test, expliquer la différence
entre modification, désactivation et suppression logique, puis reprendre un cas
de validation le lendemain.
