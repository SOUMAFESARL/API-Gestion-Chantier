# Deploiement SSH de feature/api-chantier

Le workflow lance les verifications et tests PostgreSQL, puis deploie les pushs
sur `feature/api-chantier`. Les pull requests executent uniquement les tests.
Un lancement manuel doit selectionner cette branche.

Dans GitHub > Settings > Secrets and variables > Actions, configurer :

| Type | Nom | Valeur |
| --- | --- | --- |
| Secret | `CPANEL_SSH_HOST` | Hote SSH cPanel |
| Secret | `CPANEL_SSH_USERNAME` | Utilisateur SSH |
| Secret | `CPANEL_SSH_KEY` | Cle privee SSH, ou utiliser le mot de passe ci-dessous |
| Secret | `CPANEL_SSH_PASSWORD` | Mot de passe SSH si aucune cle n'est configuree |
| Secret | `CPANEL_SSH_PORT` | Port SSH, 22 par defaut |
| Secret | `CPANEL_SSH_FINGERPRINT` | Empreinte SHA256 de l'hote SSH (facultative) |
| Variable | `CPANEL_PROJECT_DIR` | Chemin absolu du dossier de cette application |
| Variable | `CPANEL_VENV_PYTHON` | Chemin absolu du Python du virtualenv cPanel (Python 3.13 ou compatible avec requirements.txt) |
| Variable | `CPANEL_HEALTH_URL` | URL publique de l'API, facultative |

Le dossier cible doit correspondre a cette version de l'application. Le transfert
remplace les fichiers correspondants sans supprimer les anciens fichiers distants.
Les migrations modifient la base configuree dans le `.env` du serveur.

Preparer dans cPanel une application Python avec `passenger_wsgi.py` comme fichier
de demarrage et `application` comme point d'entree. Creer le fichier `.env` serveur
depuis `.env.example`, avec les identifiants PostgreSQL, une cle secrete,
`DEBUG=False` et le domaine public dans `ALLOWED_HOSTS`. Ce fichier reste sur le serveur.
Configurer le serveur web pour servir `/static/` depuis `staticfiles/`.

Le workflow installe `requirements.txt`, applique les migrations, collecte les
fichiers statiques puis demande le redemarrage Passenger via `tmp/restart.txt`.
