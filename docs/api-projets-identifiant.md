# Identifiant projet dans les reponses CRUD

Objectif : visualiser une liste ou chaque projet expose son UUID stable, utilisable pour GET, PUT, PATCH et DELETE.

Architecture : conserver CHAMPS_FORMULAIRE pour les entrees et definir CHAMPS_REPONSE = ("id", *CHAMPS_FORMULAIRE). Le ModelSerializer de sortie expose l UUID existant en lecture seule. Aucune migration et aucune regeneration d identifiants.

Implementation : modifier uniquement Meta.fields et Meta.read_only_fields du serializer de sortie. Les entrees restent strictes et rejettent id. Swagger derive automatiquement id de type string, format uuid, readOnly true.

Pre-mortem : ajouter id au formulaire risquerait d autoriser une entree non souhaitee. Verifier la stabilite sur POST, liste GET, detail GET, PUT et PATCH. DELETE reste sans corps, HTTP 204.

Validation : comparer l UUID au modele persiste et au Location, verifier les schemas de sortie et l absence du champ dans le schema d entree ; conserver les tests contrats et permissions.

Apprentissage actif : predire les reponses avant execution, observer les erreurs puis corriger une hypothese a la fois. Comprendre, planifier, executer et verifier. Expliquer a un collegue pourquoi un identifiant serveur doit etre expose sans pouvoir etre choisi par le client ; revisiter cet exemple demain pour consolider.
