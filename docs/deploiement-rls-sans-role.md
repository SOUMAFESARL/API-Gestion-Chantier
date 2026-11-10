# cPanel : plateforme sans rôle PostgreSQL privilégié

Arbitrage du développeur : rendre `ccd_plateforme` facultatif en conservant
l'isolation RLS entre entreprises sur l'hébergement mutualisé.

Les réglages cPanel activent `CCD_PLATEFORME_SANS_ROLE=True` par défaut.
La migration `core.0003_plateforme_sans_role` ajoute une politique permissive
de plateforme aux tables protégées et adapte la purge de l'historique immuable.
Elle s'applique avec le propriétaire des tables, sans créer de rôle PostgreSQL.

Le wrapper synchronise `ccd.portee_plateforme` avec le contexte Python : `on`
uniquement dans une portée plateforme explicite, `off` dans tous les autres cas.
La politique exige aussi l'absence d'entreprise active. La RLS forcée et les
politiques d'entreprise restent actives ; les gestionnaires ORM restent cloisonnés.
La purge de l'historique exige toujours le marqueur de l'entreprise à supprimer
et refuse toujours les modifications ordinaires.

Ce réglage n'est pas une frontière contre une injection SQL : du SQL arbitraire
peut le changer, comme `ccd.entreprise_id` ou `SET ROLE` dans le mode historique.
Ne jamais le déduire d'un paramètre fourni par le client HTTP.

Validation après déploiement : `python manage.py verifier_isolation
--settings=config.settings.cpanel`. En dehors de cPanel, activer explicitement
la variable `CCD_PLATEFORME_SANS_ROLE=True` si le même mode est souhaité.
Pour conserver le mode avec rôle sur cPanel : `CCD_PLATEFORME_SANS_ROLE=False`.

Une future table d'entreprise doit recevoir aussi la politique
`portee_plateforme_session` ; le diagnostic la signale sinon en mode session.
