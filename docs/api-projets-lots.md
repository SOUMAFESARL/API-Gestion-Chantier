# Lots d'un projet existant

Un projet possède plusieurs lots. Les trois routes ci-dessous exigent un jeton
et l'accès au projet selon les règles d'appartenance existantes ; aucune
permission d'écriture supplémentaire n'est requise. Un visiteur affecté peut
donc créer des lots, conformément au périmètre demandé.

- GET /api/v1/projets/{id}/lots/ : liste des lots non supprimés, ordonnée.
- POST /api/v1/projets/{id}/lots/ : création d'un lot (201).
- POST /api/v1/projets/{id}/lots/import/ : import .xlsx multipart (201).
- GET /api/v1/projets/{id}/lots/modele/ : téléchargement du modèle Excel.

Le champ `nom` correspond au libellé du modèle. Saisie manuelle : nom,
mode_execution et type_bordereau obligatoires ; dates et budget facultatifs.

```json
{
  "nom": "Gros œuvre",
  "mode_execution": "REGIE",
  "type_bordereau": "FORFAIT",
  "budget_initial_montant": 2500000000,
  "date_debut_prevue": null,
  "date_fin_prevue": null
}
```

Budget JSON en centimes : 25 000 000 FCFA deviennent 2 500 000 000 centimes.
Modes : REGIE, SOUS_TRAITANCE_STRUCTUREE, SOUS_TRAITANCE_INFORMELLE.
Bordereaux : FORFAIT, PRIX_UNITAIRE, MIXTE.
Code L-01, L-02, etc. et ordre générés sous verrou du projet pour éviter les
collisions concurrentes. Les lots appartiennent toujours au projet de l'URL.
Le créateur est l'utilisateur connecté. Même nom autorisé pour plusieurs lots.

## Excel

Envoyer le champ multipart `fichier`. Maximum 5 Mo et 1000 lignes de données.
Première feuille, première ligne d'en-têtes, colonnes : nom, mode_execution,
type_bordereau, budget_fcfa, date_debut_prevue, date_fin_prevue.
Seul nom obligatoire ; REGIE/FORFAIT si les valeurs sont absentes.
Dates ISO YYYY-MM-DD ou cellules de date Excel. Budget Excel en FCFA, converti
automatiquement en centimes. Pas de formules. Toute ligne invalide annule
l'import avec détails par numéro de ligne. Une requête répétée crée de nouveaux
lots : l'import n'est pas un mécanisme de synchronisation ou de dédoublonnage.
Les budgets sont prévisionnels et ne constituent pas des dépenses réelles.

## Intégration et validation

Le frontend peut appeler ces routes à partir de l'id du projet affiché, puis
rafraîchir la liste et le compteur après une réponse 201. Aucun fichier frontend
n'est modifié par l'agent. Swagger présente les routes et les types attendus.
Installer les dépendances et appliquer migrate_schemas (migration 0018) avant
de déployer. Historique des migrations regroupées à vérifier si incohérent.

Tests : membre visiteur, plusieurs lots, codes distincts, droits hors projet,
affectation inactive, valeurs invalides, dates, budgets, import tout ou rien,
conversion FCFA, modèle, formules et fichiers malformés.

Film mental : projet -> plusieurs lots -> activités. Prédire chaque réponse,
exécuter les tests puis expliquer la différence entre clé étrangère, contrôle
d'accès et validation d'entrée. Consolider cette explication le lendemain.
