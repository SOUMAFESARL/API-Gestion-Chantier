# Creation projet : formulaire strict

POST /api/v1/projets/ accepte uniquement nom, type_projet, ville,
maitre_ouvrage, maitre_oeuvre, date_debut_prevue, date_fin_prevue,
budget_initial_montant et description.

nom, type_projet, ville et maitre_ouvrage sont obligatoires.
reference et duree_jours_ouvres sont uniquement dans la reponse :
le serveur les calcule. La reponse contient exactement les onze champs
du formulaire, sans id, createur, entreprise, lots ou equipe.
Tout champ supplementaire ou calcule envoye dans la requete produit 400.
Les dates et le budget peuvent etre omis ou null ; la fin doit etre
strictement apres le debut. Le budget reste en centimes de FCFA.

Cette evolution rompt la compatibilite avec les anciens POST complets
(client UUID, equipe, lots, reference manuelle) et les clients qui
attendent un id dans la reponse 201. GET liste/detail, POST, PUT et PATCH partagent maintenant les onze champs.
Le POST fournit l URL du projet dans l entete Location. Utiliser cette URL
pour GET detail, PUT, PATCH et DELETE ; aucun id supplementaire dans le JSON.
PUT requiert les quatre champs obligatoires et reinitialise les facultatifs omis.
PATCH conserve les champs omis. DELETE effectue une suppression logique,
retourne 204 sans JSON ; les appels suivants renvoient 404.

1. Film mental : visualiser formulaire, validation, sauvegarde, retour 201.
Decouper un probleme difficile en hypotheses verifiables sans forcer.
2. Architecture : ProjetPostSerializer filtre les champs et refuse les extras.
Il reutilise validation et creation existantes ; aucune migration necessaire.
ProjetCreationResponseSerializer limite la reponse. La vue POST les utilise.
3. Pratique : envoyer les quatre champs requis puis ajouter les facultatifs.
Reconstituer le trajet d'un champ pour apprendre activement.
4. Pre-mortem : anticiper extras silencieusement ignores, confusion centimes,
et anciens clients attendant id. Predire puis comparer les reponses.
5. Tests : creation minimale et complete, persistance, duree, champs requis,
extras, budget negatif et dates inversees.
.venv/Scripts/python.exe -m pytest apps/projets/tests/test_creation_formulaire_strict.py -q --reuse-db
6. Transmission : expliquer a un pair pourquoi une reference generee ne doit
pas etre acceptee en entree. Attention, pratique, retour d'erreur et rappel
le lendemain consolident le contrat. Comprendre, planifier, executer, verifier.

Les autres endpoints metier (affectations, meteo, tableau de bord) gardent
leurs contrats specialises. Les anciens tests de creation et modification
avec champs hors formulaire correspondent au contrat abandonne.

Validation actuelle : 27 tests du contrat CRUD strict reussis.
Exercice : predire la difference entre PUT et PATCH avant de les executer.
