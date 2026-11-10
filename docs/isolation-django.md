# Isolation par Django seul

Arbitrage explicite du développeur : supprimer toute la RLS et conserver
l'isolation dans Django. Cette décision remplace les prescriptions RLS de D9.

Les gestionnaires de `ModeleEntreprise`, le contexte authentifié, les permissions
et les contraintes entre entreprises restent actifs. `portee_plateforme` reste
une portée Python explicite et journalisée, sans changement de rôle PostgreSQL.
Le moteur PostgreSQL standard remplace le wrapper de session.

Le SQL brut et `_base_manager` ne sont plus filtrés par PostgreSQL : toute requête
qui les utilise doit porter son filtre d'entreprise explicite ou appartenir à
une opération de plateforme autorisée. La suite d'étanchéité continue de tester
les routes API et les gestionnaires ORM. Elle ne garantit plus l'isolation SQL.

## Migration des bases existantes

`0003_sans_politique_plateforme` remplace `0003_plateforme_sans_role` sans
réécrire cette dernière, même sur une base où elle n'a pas pu être appliquée.
`0004_retirer_rls` désactive la RLS, retire les deux politiques connues et
adapte le déclencheur d'historique : sa modification reste interdite ; sa purge
exige toujours le marqueur explicite de l'entreprise à supprimer.

Appliquer `python manage.py migrate` avec le propriétaire des tables et de la
fonction d'historique. Le compte applicatif actuellement configuré sur cPanel
n'est pas propriétaire de `role` : il ne pourra donc pas appliquer ce retrait.
Utiliser le compte propriétaire pour migrer ou demander à l'hébergeur de le faire.
Aucune suppression de données et aucun `--fake` ne sont nécessaires.

Les anciennes migrations restent rejouables sur une base vide ; elles posent
les protections historiques, puis `0004` les retire. Aucun rôle BYPASSRLS n'est
requis. Ne pas déployer seulement le code sur une base restant sous RLS : les
requêtes ORM seraient filtrées par PostgreSQL sans réglage de session.

`verifier_isolation` contrôle désormais l'absence de RLS résiduelle sur les
tables métier. Il ne certifie pas le filtrage Django : les tests ORM et API
assurent cette validation.
