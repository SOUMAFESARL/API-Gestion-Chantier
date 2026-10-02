# Notifications d'expiration des abonnements

`GET /api/v1/abonnement/notifications/`, JWT requis, roles AD, DG, DF.
Swagger : section **Notifications d'abonnement**.
Renvoie un tableau vide ou l'alerte de l'abonnement le plus recent de l'entreprise.
Le frontend appelle cette route a l'ouverture de l'espace et periodiquement pour
afficher le message et le lien de renouvellement. Ce n'est pas un flux WebSocket.
L'alerte est calculee sans ecriture ni envoi d'email : des J-7, avec des niveaux
a J-3, J-1, J0, puis un etat expire. Elle disparait apres renouvellement au-dela
de sept jours. Aucun historique de lecture individuel n'est conserve.

## Emails automatiques

Abonnements ACTIF uniquement, dates exactes J-7, J-3, J-1, J0.
Un email individuel par AD, DG ou DF actif du schema client. Les essais gardent
leurs relances existantes. La trace inclut abonnement, echeance, seuil et adresse.
Une relance reussie n'est pas repetee ; un echec SMTP peut etre reessaye le meme
jour. Pas de rattrapage des seuils passes. Comme pour tout envoi SMTP, un arret
entre acceptation du message et validation SQL peut provoquer un doublon.

Configurer SMTP et FRONTEND_URL pour le domaine reel, installer les migrations :

```bash
python manage.py migrate_schemas --noinput --settings=config.settings.cpanel
```

Une tache Celery Beat quotidienne a 06:00 UTC est creee par migration. Elle exige
un worker Celery et Beat actifs. Sur cPanel sans Celery, creer une tache cron
quotidienne (horaire 06:00, selon le fuseau du serveur) :

```bash
cd /home/c2858133c/public_html/api-chantier && /home/c2858133c/virtualenv/public_html/api-chantier/3.13/bin/python manage.py relancer_abonnements --settings=config.settings.cpanel
```

La commande envoie des emails reels selon la configuration SMTP. Les tests
utilisent uniquement la boite email en memoire de Django.
