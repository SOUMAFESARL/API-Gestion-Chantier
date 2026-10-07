# Swagger : projets et journal de chantier

## Objectif et film mental
Visualiser le parcours : ouvrir Swagger, se connecter, préparer un rapport, créer un brouillon et lire la réponse JSON. Procéder par étapes courtes et vérifier chaque résultat, sans forcer lorsque le signal d'erreur demande une nouvelle hypothèse.

## Architecture et invariants
La documentation publique doit présenter les routes métier du routage tenant. Ce choix concerne uniquement le schéma OpenAPI : les requêtes exécutées restent protégées par le JWT, la résolution du tenant et les permissions existantes. La génération ne nécessite aucune migration métier.

## Pratique guidée
1. Configurer les deux vues de schéma avec le routage config.urls_tenant.
2. Déclarer request=None pour les actions sans corps, et les champs réellement attendus pour les fichiers et mots de passe.
3. Documenter le POST de modification d'un collaborateur comme alias du PATCH.
4. Corriger le guide : la route projets/contexte-creation n'existe pas. Employer les listes existantes pour obtenir les identifiants.
5. Ouvrir /api/v1/docs/, obtenir un JWT par /api/v1/auth/token/ et utiliser Authorize.
6. Préparer le journal par GET /api/v1/chantier/rapports/preparation/?projet=<uuid>&date=YYYY-MM-DD, puis créer avec POST /api/v1/chantier/rapports/.

## Pré-mortem et signal d'erreur
Un schéma public incomplet masque les opérations métier. Une action sans request déclaré provoque une erreur d'inférence. Les exemples UUID doivent être remplacés par des identifiants réels. La documentation ne corrige pas l'historique des migrations : l'exécution métier exige une base à jour.

## Validation
Les 13 tests Swagger (journal et projets) passent. La génération OpenAPI complète produit zéro erreur ; huit avertissements de noms d'enums et d'alias d'opérations subsistent. Les URL locales docs et schema répondent HTTP 200.
Générer OpenAPI avec spectacular --settings=config.settings.test --urlconf config.urls_tenant --validate. Vérifier aussi le schéma servi par chacune des deux vues sans accès à la base, la présence du CRUD journal et des corps des actions. Exécuter les tests Swagger existants des projets.

## Consolidation et transmission
Expliquer à un collègue pourquoi la visibilité d'une route dans Swagger ne donne aucun droit sur ses données. Rejouer mentalement le parcours réussi puis, demain, reconstruire les étapes de mémoire : attention, engagement actif, retour sur erreur et consolidation.
