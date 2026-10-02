# Validation des inscriptions

Nouveau parcours : depot public, verification de l'email et choix du mot de
passe, attente A_VALIDER, approbation par un super admin, puis creation de l'espace.
Les entreprises existantes ne sont pas bloquees par cette modification.

## API super admin

Se connecter via `POST /api/v1/admins/connexion/` et transmettre le jeton `access`
dans `Authorization: Bearer <access>`. Seul un compte actif avec is_superuser=True
dans le schema public est autorise. Un administrateur d'entreprise est refuse.

- `GET /api/v1/admins/inscriptions/?statut=A_VALIDER` : liste paginee.
- `GET /api/v1/admins/inscriptions/<id>/` : detail sans empreinte ni mot de passe.
- `POST /api/v1/admins/inscriptions/<id>/approuver/` : sans corps, reponse 202.
- `POST /api/v1/admins/inscriptions/<id>/refuser/` : `{"motif": "Dossier incomplet"}`.

La decision, sa date, son auteur et le motif sont conserves et journalises.
Rejouer une decision identique ne cree pas de nouvelle tache ni de nouvelle trace.
Une decision opposee ou une demande dont l'email n'est pas verifie retourne 409.
La connexion du super admin ne valide aucune demande automatiquement.

## Adaptation du frontend

`POST /api/v1/inscription/activer/` renvoie maintenant `A_VALIDER`, et non
`PROVISIONNEMENT`. Afficher l'attente de validation et interroger la route de suivi
existante `GET /api/v1/inscription/etat/<suivi>/`.
Elle renvoie A_VALIDER, REFUSEE (avec motif_refus), PROVISIONNEMENT, PRET ou ECHEC.
EN_ATTENTE et ABANDONNEE sont egalement exposes avant verification de l'email.
L'espace n'est cree qu'apres approbation. Le refus n'envoie pas d'email additionnel ;
le motif est disponible dans le suivi. L'email espace pret existant reste utilise.

## Deploiement

Executer `python manage.py migrate_schemas --noinput --settings=config.settings.cpanel`
avant de redemarrer l'application. Le provisionnement conserve la configuration
Celery existante. Cette livraison ajoute une migration tenants pour les decisions,
les etats et la reservation de l'email/slug jusqu'a la fin du provisionnement.
