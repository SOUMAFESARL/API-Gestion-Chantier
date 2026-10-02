# Lots : dates r?elles et projet_id

GET et POST /api/v1/projets/{id}/lots/ exposent projet_id (UUID en lecture seule)
? la place de projet. Le projet parent reste d?termin? par URL, sans saisie.
Les r?ponses POST import exposent le m?me contrat.

Cr?ation : date_debut_reelle et date_fin_reelle facultatives, YYYY-MM-DD ou null.
Une fin r?elle avant le d?but r?el est rejet?e (400). Les dates pr?vues restent
ind?pendantes. Les champs existent d?j? en base : aucune migration.

Le mod?le Excel inclut ces deux colonnes facultatives, avec validation atomique.
Attention int?gration : remplacer la lecture de lot.projet par lot.projet_id.
Aucune modification frontend r?alis?e. V?rifier omission, null, valeurs, dates
invers?es, persistance et Swagger. Pr?dire les r?sultats puis expliquer le contrat.
