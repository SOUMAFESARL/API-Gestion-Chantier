# Avancement r?alis? et sant?

Les r?ponses CRUD exposent avancement_reel en lecture seule : 0 ? la cr?ation,
100 lorsque toutes les activit?s actives sont r?alis?es. Aucune saisie ni migration.
Le champ ?gale statistiques.avancement_pondere : quantit?s r?alis?es / pr?vues,
born?es de 0 ? 100 ; activit? CLOTURE ? 100. Pond?ration par budget si tous les
budgets sont positifs, sinon moyenne simple. Lots et activit?s inactifs ou supprim?s
sont exclus. Sans activit?, le r?sultat est 0. Cr?er un lot ou changer le statut
EN_COURS seul ne fait pas progresser les travaux. Ajouter des activit?s non r?alis?es
peut diminuer la moyenne. Deux activit?s ? 50 et 0 % valent 25 % sans budgets.

indice_sante reste null tant que les d?penses fiables ne sont pas reli?es.
Formule future : max(0, 100 - max(0, consommation du budget - r?alisation)).

Swagger d?crit le champ calcul?. Tests : cr?ation, lot seul, progression, liste,
d?tail, quantit? d?pass?e, d?sactivation et refus de saisie. Pour apprendre,
pr?dire le r?sultat, v?rifier puis expliquer la moyenne ? un coll?gue.
