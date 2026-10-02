# Équipes de chantier et affectations

Ces équipes regroupent des personnes pour exécuter les activités. Elles sont
distinctes des affectations RBAC qui autorisent l'accès au projet. Toutes les
routes exigent un utilisateur authentifié ayant accès au projet de l'URL.
Saisir une personne par son nom ne crée ni compte ni droit d'accès.

Routes sous /api/v1/projets/{id}/equipes/ :
- GET / POST : liste et constitution d'une équipe.
- GET / DELETE {equipe_id}/ : détail et suppression logique.
- GET statistiques/ : quatre indicateurs automatiques.
- GET / POST affectations/ : liste et affectation équipe-activité.
- DELETE affectations/{affectation_id}/ : retrait de l'affectation.

## Constituer une équipe

```json
{
  "nom": "Équipe Maçonnerie B",
  "nature": "INTERNE",
  "corps_etat": "Maçonnerie / coffrage",
  "chef": {"nom": "Chef externe"},
  "membres": [
    {"nom": "Ouvrier 1", "fonction": "OUVRIER"},
    {"nom": "Ouvrier 2", "fonction": "OUVRIER"}
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
