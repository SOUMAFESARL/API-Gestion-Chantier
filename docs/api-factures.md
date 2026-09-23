# Factures d'abonnement

Les factures sont creees par `POST /api/v1/cinetpay/initier/` et passent de
`EMISE` a `PAYEE` apres confirmation du paiement par le service CinetPay existant.
La reponse d'initiation fournit `facture_id`, `facture_url`, `facture_pdf_url`.

## Consultation

- `GET /api/v1/factures/` : liste paginee, filtre optionnel `statut`.
- `GET /api/v1/factures/<uuid>/` : detail et paiements, sans charge utile prestataire.
- `GET /api/v1/factures/<uuid>/pdf/` : telechargement PDF authentifie.

Utiliser le jeton JWT de l'entreprise. Roles autorises : AD, DG, DF.
Une facture d'une autre entreprise retourne 404. Le schema public ne permet pas
la consultation des factures clientes. Aucune creation ou modification manuelle
n'est exposee. Les montants JSON sont des entiers en centimes XOF ; le PDF les
convertit en FCFA avec deux decimales. Pagination : `page`, `taille_page`.

## Configuration et historique

Renseigner les variables `FACTURATION_*` de `.env.example` avec les coordonnees
reelles de l'emetteur avant d'emettre des factures. Aucune identite, banque ou
certification fictive du modele HTML fourni n'est reprise.
Les nouvelles factures archivent le client, l'emetteur et la prestation dans
`contexte_facturation`. Les anciennes restent consultables avec une mention
signalant l'absence de coordonnees archivees ; aucun historique n'est invente.
Le PDF reprend les blocs du modele : emetteur, client, dates, prestation,
montants HT/TVA/TTC et reglement. Il ne constitue pas une integration DGI/FNE.

## Installation

Installer `requirements/local.txt` en developpement ou `requirements/base.txt`
en production, puis executer `python manage.py migrate_schemas --noinput`.
ReportLab produit le PDF en memoire, sans URL publique de stockage.
