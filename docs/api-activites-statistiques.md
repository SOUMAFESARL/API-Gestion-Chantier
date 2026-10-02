# Activités de lot et statistiques

Les réponses POST/GET/PUT/PATCH du CRUD projet exposent aussi `statistiques`,
avec `lots_count` et `activites_count` pour ce projet. Les champs restent calculés
en lecture seule. La liste et le détail préchargent les lots et activités.

GET/POST /api/v1/lots/{lot_id}/activites/ : consulter ou créer les activités
du lot. Utilisateur connecté ayant accès au projet parent. Le lot de l'URL
impose le rattachement ; lot_id ne se saisit pas dans le corps JSON.

```json
{
  "libelle": "Carte_transport",
  "quantite_prevue": "100.000",
  "unite": "M2",
  "date_debut_prevue": "2026-10-04",
  "date_fin_prevue": "2026-10-11",
  "dependance": null,
  "equipe_ids": [],
  "budget_initial_montant": null
}
```

Libellé requis. Quantité facultative (1 par défaut), unité U par défaut.
Unités : M2, ML, M3, KG, U, FORFAIT ; quantité FORFAIT normalisée à 1.
Dates facultatives (null accepté), fin >= début et respect des bornes du lot.
Dépendance active du même projet, éventuellement dans un autre lot. Si les
dates sont connues, début au plus tôt à la fin de l'activité précédente.
Equipe facultative : equipe_ids liste des UUID de collaborateurs actifs
affectés au même projet, ou ses responsables directs. Maximum 50 personnes.
Quantité réalisée, statut et avancement automatiques/non saisissables à la création.
GET /api/v1/activites/{id}/ consulte le détail ; DELETE conserve ses permissions
d'écriture existantes. Aucun endpoint de modification de l'équipe ou de la
dépendance n'est ajouté ici : l'affectation ultérieure reste une tâche future.

GET /api/v1/projets/{id}/statistiques/ retourne lots_count, activites_count,
avancement_pondere, ponderation, activites_en_retard et budget_activites_montant.
Les lots exposent aussi activites_count et avancement recalculé.

Pourcentage réalisé = quantité réalisée / quantité prévue, borné entre 0 et 100.
Une activité CLOTURE compte à 100 %. Avancement pondéré par budgets en centimes
si toutes les activités ont un budget positif ; sinon moyenne uniforme et
ponderation=UNIFORME. Deux activités réalisées à 50 % et 0 %, budgets de 10000
et 30000 centimes, donnent 12,5 % avec ponderation=BUDGET.
Les statistiques représentent le réalisé (0 -> 100), contrairement au restant
du CRUD projet (100 -> 0). Ne pas additionner les quantités de différentes unités.
Retard : fin passée, réalisation < 100 %, statut non clôturé. Dates inconnues
non comptées comme retard. Lots/activités inactifs ou supprimés exclus.
Budgets prévisionnels facultatifs ; ce ne sont pas des dépenses réelles.

Statistiques calculées à chaque lecture, sans cache. Equipes/activités préchargées
pour éviter les N+1. Le frontend doit rafraîchir les trois listes/statistiques
après création. Aucun fichier frontend modifié par l'agent.

Déploiement : appliquer la migration 0020 via migrate_schemas. Tests de création,
dates facultatives, quantité, unité, dépendance et équipe hors projet, accès,
pondération budget, compteurs, retard et exclusions. Vérifier les migrations
regroupées si l'historique de la base existante est incohérent.

Film mental : projet -> lots -> activités -> réalisation -> statistiques.
Prédire les chiffres avant le test, vérifier l'hypothèse, expliquer la pondération
à un collègue puis refaire cette explication le lendemain.
