# Déploiement automatique sur cPanel

Le workflow `.github/workflows/deploy-cpanel.yml` teste les push et pull requests
vers `main`. Après un push sur `main`, il déploie par SSH uniquement si la variable
GitHub `CPANEL_DEPLOY_ENABLED` vaut `true`. Aucun accès serveur n'est enregistré
dans le dépôt. `workflow_dispatch` permet aussi une relance manuelle sur `main`.

## 1. Préparer l'application une seule fois

Dans **Setup Python App**, choisir Python **3.13** (ou au minimum 3.12), le mode
Production et un domaine HTTPS dédié, par exemple `api.exemple.ci`.
Choisir une Application root hors de `public_html`, par exemple
`/home/COMPTE/api-gestion-chantier`. Le code et `.env` ne doivent pas être servis
comme des fichiers publics.

- Application startup file : `passenger_wsgi.py`
- Application Entry point : `application`
- Variable : `DJANGO_SETTINGS_MODULE=config.settings.cpanel`

Conserver la commande d'activation affichée par cPanel : elle indique le chemin
du virtualenv, par exemple `/home/COMPTE/virtualenv/api-gestion-chantier/3.13/bin/activate`.
Le Python correspondant est `.../bin/python`.

Dans Terminal, vérifier la présence de `git`, `flock` et `ssh`.
Extraire la branche `main` du dépôt
`git@github.com:SOUMAFESARL/API-Gestion-Chantier.git` dans l'Application root.
Ce dossier doit être la racine du checkout Git sur la branche `main`.
Si cPanel y a déjà créé un fichier de démarrage, conserver son contenu avant
de le remplacer par celui du dépôt. Ne pas écraser une application existante.

Pour un dépôt privé, créer sur cPanel une clé SSH dédiée et ajouter sa partie
publique comme **Deploy key en lecture seule** dans GitHub. Vérifier la clé
d'hôte GitHub suivant ses empreintes officielles avant de l'ajouter au
`known_hosts` du compte cPanel. `git fetch origin main` doit fonctionner sans
demande de mot de passe.

Créer `.env` à partir de `.env.example` sur le serveur, puis renseigner :

- une véritable `DJANGO_SECRET_KEY` aléatoire et `DJANGO_DEBUG=False` ;
- `DJANGO_SETTINGS_MODULE=config.settings.cpanel` ;
- `DJANGO_ALLOWED_HOSTS=api.exemple.ci,.api.exemple.ci` et
  `DOMAINE_PRINCIPAL=api.exemple.ci` selon les domaines réellement utilisés ;
- les paramètres PostgreSQL de cPanel ou d'une base managée externe (recommandé : **Supabase PostgreSQL 17** via pooler IPv4 `aws-1-eu-west-3.pooler.supabase.com:5432`, ce qui contourne les versions obsolètes PostgreSQL 13/14 de certains OS cPanel et garantit les droits complets `CREATE SCHEMA`) ;
- `FRONTEND_URL` et `CORS_ALLOWED_ORIGINS` avec les URL HTTPS du frontend ;
- les paramètres SMTP et S3 définis dans `config/settings/production.py` ;
- un service Redis accessible pour le cache et Celery.

Le backend utilise des schémas PostgreSQL : l'utilisateur doit pouvoir créer
des schémas dans sa base (`django-tenants`). La présence de PostgreSQL dans cPanel ne garantit pas
ce droit, raison pour laquelle une base managée externe (Supabase) avec droits administrateur est particulièrement recommandée. Configurer aussi les domaines et certificats HTTPS des tenants.
Le proxy de l'hébergeur doit transmettre correctement le protocole HTTPS.

Passenger ne lance pas les workers Celery ni Celery Beat. Si les tâches
asynchrones sont utilisées, prévoir ces processus avec l'hébergeur. Ne pas
utiliser le cache mémoire local comme remplacement implicite du cache partagé.

Activer le virtualenv avec la commande fournie par cPanel, puis exécuter dans
la racine de l'application :

```bash
export DJANGO_SETTINGS_MODULE=config.settings.cpanel
python -m pip install -r requirements/production.txt
python manage.py check
python manage.py migrate_schemas --noinput
python manage.py collectstatic --noinput
mkdir -p tmp
touch tmp/restart.txt
```

Configurer le tenant public et son domaine réel, ainsi que les tenants clients,
selon les données de production. Les migrations seules ne créent pas ces données.
Ne pas installer les comptes de démonstration en production. Vérifier que
`https://api.exemple.ci/api/health/` répond `{"statut":"ok",...}` avant activation.

## 2. Configurer GitHub Actions

Dans le dépôt GitHub : **Settings → Secrets and variables → Actions**.

### Secrets

| Nom | Valeur |
| --- | --- |
| `CPANEL_SSH_HOST` | Hôte SSH fourni par l'hébergeur, sans `https://` |
| `CPANEL_SSH_USER` | Utilisateur cPanel |
| `CPANEL_SSH_PRIVATE_KEY` | Clé privée dédiée aux connexions GitHub Actions → cPanel |
| `CPANEL_SSH_KNOWN_HOSTS` | Ligne de clé d'hôte SSH du serveur, vérifiée auprès de l'hébergeur |

Autoriser la clé publique correspondante dans **SSH Access → Manage SSH Keys**.
Cette clé est distincte de la clé de lecture cPanel → GitHub. Ne jamais coller
de clé privée dans une conversation, un fichier versionné ou un journal.
Pour un port SSH personnalisé, la ligne known_hosts utilise `[hote]:port`.
Une collecte avec `ssh-keyscan` seule ne vérifie pas l'identité du serveur.

### Variables

| Nom | Exemple |
| --- | --- |
| `CPANEL_SSH_PORT` | `22` (défaut) |
| `CPANEL_APP_ROOT` | `/home/COMPTE/api-gestion-chantier` |
| `CPANEL_PYTHON_BIN` | `/home/COMPTE/virtualenv/api-gestion-chantier/3.13/bin/python` |
| `CPANEL_HEALTH_URL` | `https://api.exemple.ci/api/health/` |
| `CPANEL_DEPLOY_ENABLED` | `true`, seulement une fois la configuration terminée |

Les chemins doivent être absolus, sous `/home`, sans espaces. Le serveur doit
accepter les connexions SSH du runner GitHub et disposer d'un accès à GitHub
et à l'index des paquets Python.

## 3. Fonctionnement et limites

1. Les tests backend s'exécutent sous Python 3.13 avec PostgreSQL 16.
2. Le test `test_le_referentiel_typescript_ne_derive_pas` est explicitement
   désélectionné : il nécessite le vrai dépôt frontend, absent de ce dépôt.
   Il reste à exécuter dans une CI qui extrait les deux dépôts ; aucun fichier
   généré artificiellement ne remplace cette vérification.
3. Le déploiement refuse les modifications locales suivies par Git et une
   branche autre que `main`. Il utilise un verrou et une fusion fast-forward.
4. Le SHA déployé doit être celui testé et toujours être la tête de `origin/main`.
   Si un push plus récent est arrivé, le workflow ancien échoue sans déployer.
5. Les dépendances de production, toutes les migrations de schémas et les
   fichiers statiques sont mis à jour. `.env` reste local au serveur.
6. `tmp/restart.txt` demande le rechargement de Passenger à la prochaine requête.
   Le workflow vérifie ensuite la réponse JSON du point de santé HTTPS.

Le point de santé confirme une réponse de l'application, pas la version exacte
servie ni l'état de tous les services externes. Le déploiement est **en place** :
une interruption est possible. Il n'y a pas de retour arrière automatique,
notamment après une migration. Prévoir une sauvegarde PostgreSQL et une procédure
de restauration avant le premier déploiement. En cas d'échec après la mise à jour
du code, consulter les logs Actions/Passenger et terminer ou restaurer le déploiement.
Les dépendances du projet ne sont pas verrouillées : leur résolution peut varier.

## Références

- [Application Python WSGI sur cPanel](https://docs.cpanel.net/knowledge-base/web-services/how-to-install-a-python-wsgi-application/)
- [Redémarrage Passenger](https://www.phusionpassenger.com/docs/references/config_reference/apache/)
- [Empreintes SSH de GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)
- [Déploiements GitHub Actions](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)
