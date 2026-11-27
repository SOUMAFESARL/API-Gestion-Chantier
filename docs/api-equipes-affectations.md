# Équipes de chantier et affectations

Ces équipes regroupent des personnes pour exécuter les activités. Elles sont
distinctes des affectations RBAC qui autorisent l'accès au projet. Toutes les
routes exigent un utilisateur authentifié ayant accès au projet de l'URL.
Saisir une personne par son nom ne crée ni compte ni droit d'accès.

Routes sous `/api/v1/projets/{id}/equipes/` :
- `GET` / `POST` : liste et constitution d'une équipe.
- `GET` / `PATCH` / `DELETE` `{equipe_id}/` : détail, modification et suppression logique.
- `POST` `{equipe_id}/membres/` : ajout d'un ou plusieurs membres du registre (`personne_id`, `personne_ids`, `utilisateur_id`, `utilisateur_ids`).
- `PATCH` / `DELETE` `{equipe_id}/membres/{membre_id}/` : modification indépendante de `fonction`, `est_chef`, `date_arrivee`, `date_depart` ; `DELETE` date le départ (ou `?supprimer=true` en cas d'erreur de saisie).
- `GET` `statistiques/` : quatre indicateurs automatiques.
- `GET` / `POST` `affectations/` : liste et affectation équipe-case de l'arbre.
- `DELETE` `affectations/{affectation_id}/` : retrait de l'affectation.

## Fonctions / métiers d'équipe et statut de chef (`est_chef`)

- Les fonctions d'équipe proviennent du référentiel dynamique `FONCTION_EQUIPE` (`/api/v1/referentiels/fonctions-equipe/` pour l'entreprise, `/api/v1/admins/referentiels/fonctions-equipe/` pour la plateforme).
- `fonction` et `est_chef` sont strictement découplés : `CHEF_EQUIPE` est refusé comme valeur de `fonction`.
- Si `fonction` est vide ou absente à l'ajout d'un membre, elle est déduite depuis `personne.metier` (comparaison normalisée sur `FONCTION_EQUIPE`), avec repli sur `OUVRIER`.
- Nommer ou retirer un chef via `est_chef` n'écrase jamais la fonction métier du membre ni celle du chef sortant.
- Lors d'un départ daté (`date_depart` posée via `DELETE` ou `PATCH`), `est_chef` est conservé dans l'historique ; la contrainte partielle `uq_membre_equipe_chef` (`est_chef = true AND date_depart IS NULL AND supprime_le IS NULL`) garantit un seul chef actif par équipe tout en préservant l'historique des anciens chefs.
- `MembreSerializer` et les membres du journal exposent `fonction` (code) et `fonction_libelle` (résolu depuis `FONCTION_EQUIPE`, y compris pour les entrées retirées depuis).

## Constituer une équipe

```json
{
  "nom": "Équipe Maçonnerie B",
  "corps_etat": "Maçonnerie / coffrage",
  "entreprise_partenaire_id": null,
  "membres": [
    {"personne_id": "<uuid>", "fonction": "MACON", "est_chef": true},
    {"personne_id": "<uuid>", "fonction": "OUVRIER"}
  ]
}
```

Nom, nature (INTERNE ou SOUS_TRAITANTE), corps_etat et chef obligatoires.
Les membres sont facultatifs, maximum 100 personnes chef compris. Fonction
libre, OUVRIER par défaut. Chaque personne contient soit utilisateur_id (UUID
d'un collaborateur actif affecté au projet ou responsable direct), soit nom.
Jamais les deux. Doublons de collaborateurs ou de noms dans une équipe refusés.
La réponse contient id, projet, chef, membres, effectif et est_actif.
La modification des équipes n'est pas ajoutée dans cette tâche.

## Affecter une équipe

La réponse d'affectation comprend lot_id, lot_nom, date_debut, date_fin,
effectif (chef compris) et statut de l'activité, pour alimenter le tableau.
La période suit les dates de l'activité, même après reprogrammation ; pas de
période indépendante à saisir. Dates absentes : null. Le statut n'est pas un
nouveau statut d'affectation. Recherche GET avec recherche, lot_id, equipe_id.
Exemple : affectations/?lot_id=<uuid>&equipe_id=<uuid>&recherche=Maçonnerie.
Un UUID de filtre invalide renvoie 400. Les filtres ne dépassent jamais le projet.

POST affectations/ avec equipe_id et activite_id. Les deux objets doivent être
actifs et appartenir au même projet. Une activité terminée n'est plus affectable.
Une équipe peut tenir plusieurs activités ; une activité peut recevoir plusieurs
équipes. Doublon actif équipe-activité refusé. Retirer une affectation ne supprime
pas les personnes et permet une nouvelle affectation ultérieure.
Les collaborateurs directs equipe_ids de l'API d'activités restent distincts :
cette page compte exclusivement les équipes nommées et leurs affectations.

## Statistiques

equipes_count : équipes actives non supprimées.
effectif_mobilise : chefs compris ; collaborateurs identifiés dédupliqués par UUID
entre équipes ; les personnes saisies par nom restent des entrées séparées car
deux homonymes ne prouvent pas une identité commune.
activites_affectees : activités actives non terminées ayant au moins une équipe active.
activites_a_affecter : autres activités actives non terminées, lots actifs seulement.
Une activité rattachée à deux équipes n'est comptée qu'une fois.
Suppression d'équipe : conservation de l'historique, exclusion immédiate des
statistiques et affectations visibles. Aucune suppression physique.

## Validation et apprentissage

Swagger expose les routes et exemples. Migration 0021 via migrate_schemas.
Tests : membre visiteur, chef et membres libres/internes, champs requis,
personne hors projet, doublons, affectation hors projet, retrait/restauration,
activité terminée, suppression logique, effectif et compteur distinct.
Film mental : projet -> équipes -> personnes -> affectations -> activités.
Prédire les indicateurs avant d'exécuter les tests, vérifier puis expliquer à
un collègue pourquoi une affectation de chantier n'accorde aucun droit RBAC.
Reprendre cette explication demain pour consolider la compréhension.
