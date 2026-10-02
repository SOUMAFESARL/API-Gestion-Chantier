> Le POST de creation utilise maintenant le [formulaire strict](api-creation-formulaire-strict.md). Les exemples historiques avec lots, equipe ou client ne sont plus acceptes en creation.

# Création de projet et contexte connecté

## Objectif et parcours

Le développeur peut visualiser ce parcours : un jeton valide identifie le
collaborateur et son entreprise ; le formulaire charge ses choix ; un POST
enregistre le projet, les lots et les affectations dans le schéma de cette
entreprise. Le créateur est distinct du chef de projet sélectionné.

## Contrats HTTP

Tous les appels portent `Authorization: Bearer <access>`.

- `GET /api/v1/auth/profil/` (alias `/api/v1/utilisateurs/moi/`) : profil
  connecté existant, avec `entreprise` et `schema`.
- `GET /api/v1/projets/contexte-creation/` : préparation du formulaire,
  réservée aux utilisateurs disposant de l'écriture sur le module projets.
  Renvoie `utilisateur`, `entreprise`, `collaborateurs`, `clients`,
  `types_projet`, `modes_execution`, `types_bordereau` et `roles_projet`.
  Les choix d'énumérations ont la forme `{ "valeur": "CP", "libelle": "Chef de Projet" }`.
  Les collaborateurs actifs ou invités sont ceux du schéma courant ;
  `assignable_responsable` exclut les DG et propriétaires pour CP/CT.
- `POST /api/v1/projets/` : création existante, enrichie du créateur.
  La réponse 201 expose `cree_par`, `entreprise`, les lots et les données projet.
- `GET /api/v1/projets/<id>/affectations/` : équipe enregistrée.

Exemple de corps POST (remplacer les UUID par les choix du contexte) :

```json
{
  "nom": "ZRAN",
  "type_projet": "BATIMENT_COMMERCIAL",
  "client": "<uuid-tiers-maitre-ouvrage>",
  "maitre_oeuvre": "Cabinet d'études",
  "ville": "Adjamé",
  "date_debut_prevue": "2026-10-01",
  "date_fin_prevue": "2026-12-31",
  "budget_initial_montant": 200000,
  "description": "Construction du bâtiment",
  "lots": [{
    "libelle": "Gros œuvre",
    "mode_execution": "SOUS_TRAITANCE_STRUCTUREE",
    "type_bordereau": "PRIX_UNITAIRE",
    "date_debut_prevue": "2026-10-01",
    "date_fin_prevue": "2026-11-15"
  }],
  "equipe": {
    "chef_projet_id": "<uuid-cp>",
    "conducteur_travaux_id": "<uuid-ct>",
    "chefs_chantier_ids": ["<uuid-cc>"],
    "visiteurs_ids": ["<uuid-visiteur>"]
  }
}
```

## Architecture et invariants

L'entreprise n'est pas un champ libre du POST : le middleware sélectionne le
schéma PostgreSQL et DRF valide le JWT avant l'accès à la vue. Les UUID du
client et des membres sont recherchés uniquement dans le schéma courant.
Ne jamais faire confiance à un `utilisateur_id`, `cree_par` ou `entreprise_id`
envoyé par le navigateur. La création utilise `request.user` et le contexte
tenant du serveur. Un jeton invalide est refusé avant les écritures.

`ModeleBase.cree_par` existe déjà : aucune nouvelle colonne n'est nécessaire.
Le projet, les lots et les affectations enregistrent ce créateur. Une
transaction englobe toute la création, y compris les comptes invités.

## Guide d'implémentation

1. Réutiliser le service `obtenir_donnees_profil` pour le contexte connecté.
2. Ajouter un serializer explicite pour le contexte et ses listes de choix.
3. Protéger le GET du contexte avec la même permission d'écriture que le POST.
4. Ajouter `cree_par` en lecture seule à la réponse et passer `request` au
   serializer pour représenter l'entreprise du schéma courant.
5. À la création, affecter `cree_par=user_connecte` côté serveur ; conserver
   le chef de projet choisi dans son champ métier.
6. Valider tous les identifiants des listes d'équipe avant de sauvegarder.
7. Tester via de vrais JWT et des schémas différents, puis vérifier le résultat
   en base, pas seulement la réponse JSON.

## Limites du formulaire actuel

- Le budget du contrat historique est en centimes de FCFA : 2 000 FCFA
  correspondent à `200000`. Ne pas changer cette unité côté API.
- `client` désigne un tiers existant, pas le nom libre du maître d'ouvrage.
- La fin du projet doit être strictement postérieure au début.
- Référence et codes des lots sont générés si omis.
- Les types et rôles sont ceux retournés par le contexte ; aucun nouveau rôle
  Directeur financier ou Bailleur n'est ajouté, conformément à la demande.
- Une affectation porte un seul rôle par utilisateur et projet. Employer des
  personnes distinctes pour les différentes fonctions de l'équipe.
- Le conducteur et les chefs de chantier restent optionnels pour préserver
  le contrat existant. Le chef de projet est obligatoire.
- L'avancement théorique et l'indice de santé conservent leurs règles
  existantes ; ce changement n'invente pas de formule de calcul.

## Pré-mortem et signal d'erreur

Avant chaque test, prédire le résultat : quel schéma sera lu, quel utilisateur
sera enregistré ? Comparer ensuite cette prédiction à la réponse et à la base.
Un UUID d'une autre entreprise doit échouer, jamais créer une affectation
partielle. Un membre inexistant ne doit pas disparaître silencieusement.
Une erreur tardive ne doit laisser ni projet ni compte invité orphelin.

## Checklist de validation

- Anonyme : 401 ; utilisateur sans écriture : 403.
- Contexte : utilisateur/entreprise du JWT, choix du tenant, comptes désactivés exclus.
- Création : 201, bon créateur sur projet/lots/affectations.
- Identités injectées dans le corps : aucun remplacement du contexte serveur.
- JWT altéré : aucune lecture métier ni écriture autorisée.
- Membre absent, désactivé ou appartenant à un autre tenant : erreur de validation.
- Erreur pendant la création : annulation transactionnelle.
- Régression : projets, profil et authentification domaine unique.

Validation effectuée le 29 septembre 2026 : 10 nouveaux tests réussis,
10 tests historiques de création réussis. La suite élargie projets/profil/
domaine unique donne 59 succès et un échec externe au changement :
`test_le_referentiel_typescript_ne_derive_pas` attend le fichier absent
`../frontend/src/features/referentiels/villes.ts`. Le frontend n'a pas été
modifié. Ruff valide tous les fichiers Python modifiés ou ajoutés.

## Défi de transmission

Expliquer à un collègue pourquoi le créateur du projet n'est pas forcément
son chef de projet, et pourquoi ajouter `entreprise_id` au formulaire
n'établit pas une autorisation. Reproduire un test d'isolation sans regarder
sa solution, puis relire le flux le lendemain pour consolider l'apprentissage.
