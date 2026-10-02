# Avancement restant et santé

Les réponses CRUD ajoutent deux champs calculés en lecture seule :
`avancement_reel` (nombre, pourcentage restant) et `indice_sante` (entier ou null).
Un projet neuf expose 100 et null. Aucune migration de modèle nécessaire.

Le sens du champ avancement_reel dans ce contrat CRUD est le restant demandé
par le développeur. Le champ du modèle et celui du tableau de bord conservent
leur sens historique de pourcentage réalisé. Préférer le libellé « Restant »
dans l'interface pour éviter une confusion.

Le réalisé est la moyenne pondérée des ratios quantite_realisee/quantite_prevue,
bornés entre 0 et 100. Poids explicite si positif ; sinon une activité sans
poids compte pour 1. Un poids nul ou négatif est exclu. Ne pas sommer des
quantités de différentes unités. Lots et activités inactifs ou supprimés sont
exclus. Sans activité exploitable, utiliser le réalisé stocké du projet.
Restant = 100 - réalisé. TERMINE donne 0. Changer EN_COURS seul ne fait pas
diminuer le restant : seules les données de réalisation le font évoluer.
Ajouter des activités au périmètre peut augmenter le restant.

La santé suit : max(0, 100 - max(0, % budget consommé - % réalisé)), arrondie.
Elle vaut null si budget absent, non positif ou dépenses inconnues. Le registre
des dépenses n'étant pas encore connecté, le CRUD retourne actuellement null,
même avec budget renseigné. Ne pas remplacer des dépenses inconnues par zéro.
Le helper de calcul est prêt et testé ; son alimentation financière reste future.

Préchargement lots/activités pour la liste et le détail afin d'éviter les N+1.
Swagger décrit les valeurs, lecture seule et nullabilité. Le frontend devra
afficher null comme « Non calculable » et lire les deux champs de la réponse.

Tests : création, liste, PATCH, activités commencées, dépassement de quantité,
activité désactivée, projet terminé, refus de saisie d'un champ calculé et
équilibre budget/réalisation. Prédire le résultat, observer et expliquer le
calcul à un collègue ; revisiter le lendemain pour consolider la compréhension.
