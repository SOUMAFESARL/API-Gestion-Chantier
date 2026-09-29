# Sprint 3 — Ajout et suppression des lignes de lots

## Objectif pratique
Visualiser un projet comportant trois lots : supprimer deux lignes et en
ajouter deux laisse trois lots actifs. Prédire ce résultat puis le vérifier
dans la réponse API constitue l'exercice de validation.

## Contrat
PATCH /api/v1/projets/{id}/ avec authentification habituelle.

```json
{
  "lots": [{"libelle": "Electricité"}, {"libelle": "Plomberie"}],
  "lots_supprimer_ids": ["uuid-lot-1", "uuid-lot-2"]
}
```

Remplacer les UUID par les identifiants réels du détail projet.
`lots` ajoute une ou plusieurs lignes. Chaque ligne exige un libellé ;
code, mode d'exécution, type de bordereau et dates suivent le contrat de
création existant. Le code est généré s'il n'est pas fourni.
`lots_supprimer_ids` supprime logiquement les lignes indiquées.
Champs absents ou listes vides : aucune action sur les lots existants.
La réponse 200 contient les lots actifs actualisés.

## Architecture et implémentation
Le serializer valide les nouvelles lignes avec un serializer non partiel :
un PATCH du projet n'autorise pas un nouveau lot sans libellé.
La transaction verrouille le projet, résout les identifiants exclusivement
dans ses lots actifs et réserve les codes explicites avant la génération
automatique. Les codes actifs doivent être distincts, sans distinction de casse.
La suppression renseigne l'auteur et la date et désactive la ligne.
Les liens historiques, notamment les rapports de chantier, sont conservés.
Les lots restants ne sont ni recréés ni remplacés.

## Pré-mortem
Un UUID d'un autre projet ou inexistant doit produire 400. Une date invalide,
un libellé absent ou un code en doublon doit annuler aussi les suppressions
et les modifications des informations générales présentes dans la requête.
Les permissions du PATCH projet s'appliquent à toutes ces opérations.

## Vérification et transmission
Tester plusieurs ajouts et suppressions dans le même appel, les codes
automatiques mélangés aux codes explicites, les listes vides et les erreurs.
Expliquer pourquoi une ligne omise n'est pas supprimée et pourquoi une
suppression logique conserve les rapports. Reproduire ensuite le test
sans consulter son modèle pour consolider la compréhension.

## Intégration du formulaire
Avant la création, retirer une ligne revient à la retirer du tableau local
envoyé au POST. Pour un projet enregistré, conserver les UUID des lignes
retirées dans lots_supprimer_ids et envoyer seulement les nouvelles lignes
dans lots. Le frontend reste à adapter manuellement selon la politique du dépôt.

Exemple JavaScript à appliquer manuellement dans le formulaire :

```javascript
const idsRestants = new Set(lignes.filter(l => l.id).map(l => l.id));
const payload = {
  lots: lignes.filter(l => !l.id).map(l => ({
    libelle: l.libelle,
    mode_execution: l.mode_execution,
    type_bordereau: l.type_bordereau,
    date_debut_prevue: l.date_debut_prevue || null,
    date_fin_prevue: l.date_fin_prevue || null,
  })),
  lots_supprimer_ids: lotsInitiaux
    .filter(l => !idsRestants.has(l.id)).map(l => l.id),
};
```

`lotsInitiaux` est la copie chargée depuis le serveur et `lignes` le tableau
éditable. Ne pas attribuer un UUID serveur fictif aux nouvelles lignes ;
utiliser une clé locale distincte pour leur affichage. Après un PATCH réussi,
remplacer les deux tableaux avec les lots de la réponse. En cas d'erreur,
conserver les saisies, afficher le message et réactiver le bouton.
Bloquer les doubles clics pendant l'enregistrement. En cas de réponse réseau
incertaine, recharger le projet avant de réessayer : les ajouts ne sont pas
idempotents. Ce contrat ajoute et supprime ; il ne modifie pas les valeurs
des lignes existantes.

## Résultats de validation — 29 septembre 2026

Commande exécutée :
`python -m pytest apps/projets/tests apps/chantier/tests -q --reuse-db --tb=short`.
Résultat : 70 succès et 1 échec. L'échec est
`test_le_referentiel_typescript_ne_derive_pas` : le fichier attendu
`../frontend/src/features/referentiels/villes.ts` est absent.
La suite complète n'est donc pas entièrement verte. Ruff et la commande
`manage.py check --settings=config.settings.test` passent.

Deux nouveaux tests avec connexion JWT ont reproduit une erreur 500 du POST
lorsque des codes automatiques entraient en collision avec des codes saisis.
La création réserve maintenant tous les codes explicites avant de générer
les autres codes. Ces deux tests passent après correction.
Les tests couvrent également la création en trois étapes, les opérations
groupées sur les lots, les permissions, les erreurs sans écriture partielle
et la conservation des rapports après suppression logique d'un lot.
Ces résultats proviennent de l'environnement local de test ; ils ne
constituent pas une validation du serveur cPanel déployé.

## Swagger

Documentation interactive : `/api/v1/docs/`. Schéma : `/api/v1/schema/`.
Le POST documente les lignes restantes du formulaire de création ; le PATCH
propose quatre exemples : ajouter deux lots, supprimer deux lots, combiner
les opérations et modifier les informations générales. Remplacer les UUID
fictifs par ceux du projet réel avant d'utiliser « Try it out ».
Les composants de requête sont distincts pour ne pas proposer la suppression
au POST ni les invitations au PATCH. Le DELETE expose une réponse 204 sans corps.
Pour apprendre à vérifier le contrat, comparer les champs proposés dans
Swagger à ceux de l'exemple de requête avant de l'exécuter.

Validation : schéma OpenAPI généré avec `spectacular --validate` ; vérification
des champs POST/PATCH, du statut DELETE 204 et du composant LotProjet.
Le générateur signale encore une vue collaborateurs sans serializer et des
collisions préexistantes d'operationId et d'énumération hors du module projets.
