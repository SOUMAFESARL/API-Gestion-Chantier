# Contrats multiples dans le CRUD projet

1. Film mental : visualiser plusieurs documents envoyes ensemble, projet sauvegarde,
reponse JSON contenant contrat, puis telechargement authentifie. Decouper les
invariants plutot que forcer une implementation globale.

2. Architecture : ProjetContrat relie plusieurs fichiers au projet tenant. Le champ
contrat en entree est une liste FileField. Les fichiers ne font pas partie des champs
metier envoyes au serializer interne ; ils sont stockes apres validation de tout le lot.
Le JSON de sortie inclut contrat : id, nom, taille, type_contenu, url.
Les onze champs existants et les droits de projet restent en place.

3. Pratique : envoyer multipart/form-data, avec contrat repete par fichier. POST cree
le projet ; PUT/PATCH ajoutent des contrats et conservent les existants lorsque le
champ est omis. JSON reste accepte sans fichiers ; un chemin ou URL JSON ne vaut
pas un upload. Pour telecharger : GET sur le detail avec ?contrat=UUID et JWT.
Seules les six operations CRUD restent dans Swagger.

4. Validation et pre-mortem : PDF lu par pypdf, PNG et JPEG verifies par Pillow.
Extensions .pdf, .jpg, .jpeg, .png et variante .jepg ; contenu et extension doivent
correspondre. Maximum 10 fichiers par requete, 10 Mo chacun, 50 Mo ensemble.
Un document invalide annule le lot. Nettoyer les objets de stockage si une ecriture
ulterieure echoue : transaction SQL et stockage ne partagent pas le meme rollback.
Ne pas publier les contrats par MEDIA_URL ; stockage local prive (Apache interdit
par .htaccess) ou stockage objet prive de production. Les fichiers de projets
supprimes logiquement sont conserves mais le telechargement est refuse.

5. Tests : creation avec fichiers mixtes, ajout PUT/PATCH, JSON sans fichier,
formats invalides, taille/nombre, rollback de stockage, acces anonyme/externe,
projet supprime, contrats appartenant a un autre projet, schema multipart binary,
isolation tenant et absence de N+1. Executer ensuite toute la suite CI.

6. Transmission : expliquer a un pair la difference entre rollback SQL et nettoyage
du stockage. Predire le resultat avant les tests, analyser le signal erreur et
reproduire le raisonnement le lendemain : attention, engagement actif, retour et
consolidation. Comprendre, planifier, executer et verifier chaque invariant.


Exemple JavaScript (documentation uniquement) :
```javascript
const form = new FormData();
form.append("nom", "Immeuble Les Palmiers R+5");
form.append("type_projet", "BATIMENT_RESIDENTIEL");
form.append("ville", "Man");
form.append("maitre_ouvrage", "sglaq");
for (const fichier of fichiersSelectionnes) {
  form.append("contrat", fichier);
}
const response = await fetch(`${baseUrl}/api/v1/projets/`, {
  method: "POST",
  headers: { Authorization: `Bearer ${jeton}` },
  body: form,
});
const projet = await response.json();
```
Laisser le navigateur produire Content-Type et le boundary multipart.
PUT/PATCH utilisent la meme cle repetee. Sans fichier, JSON reste accepte.
La liste contrat est vide pour les projets existants et pour les creations sans fichiers.

Telechargement : effectuer une requete GET avec Authorization sur contrat[i].url.
La reponse est un fichier avec Content-Disposition: attachment et Cache-Control:
private, no-store. Aucune URL publique de stockage n est renvoyee.

Migration : projets/0016_projetcontrat.py. Sur une instance existante, appliquer :
python manage.py migrate_schemas --noinput
pypdf passe des dependances locales aux dependances communes ; le workflow
installe requirements/base.txt avant les migrations. Le stockage local utilise
PROJET_CONTRATS_ROOT (par defaut media_prive). .htaccess interdit le service
Apache direct ; un chemin personnalise doit rester hors des repertoires web.
S3 utilise le stockage objet prive deja configure en production.

Les nouveaux contrats sont AJOUTES, y compris en PUT. Omission ou liste vide
conservent les contrats existants. DELETE projet conserve les fichiers comme
les autres donnees supprimees logiquement ; les telechargements deviennent 404.


Validation : 564 tests backend reussis, 1 test frontend deselectionne comme en CI,
3 avertissements preexistants. Les 26 tests contrats couvrent stockage,
permissions, formats, schema Swagger, transactions et isolation tenant.
Migration 0016 appliquee au schema demo local.
