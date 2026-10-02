# Swagger projets : uniquement le CRUD

Objectif : ne montrer dans Swagger que GET et POST /api/v1/projets/,
et GET, PUT, PATCH, DELETE /api/v1/projets/{id}/.
Le contrat JSON reste limite aux onze champs du formulaire.

Architecture : config/schema.py fournit limiter_projets_au_crud.
SPECTACULAR_SETTINGS.PREPROCESSING_HOOKS active ce filtre avant la generation.
Le filtre conserve les operations des deux vues CRUD et les autres modules.
Toutes les autres routes sous /projets/ sont exclues du schema :
permissions-roles, affectations, contexte-creation, meteo,
referentiels/villes, reprogrammer, historique-dates et journal-reports.
Les routes restent accessibles aux clients autorises : masquer une route
ne supprime ni son implementation ni ses permissions.

Mise en pratique : suivre une operation du routeur jusqu au generateur.
Predire les chemins du schema, generer puis comparer. Les quatre champs
obligatoires restent nom, type_projet, ville, maitre_ouvrage.
La reference et la duree sont calculees ; Location fournit l URL du projet.

Pre-mortem : ne pas confondre retrait du Swagger et suppression de routes.
Ne pas masquer les autres modules. Ne pas laisser revenir une nouvelle
route secondaire sous /projets/ : le filtre utilise une liste autorisee.

Validation : test du schema reel pour les six operations CRUD ; test de
resolution des routes masquees ; tests du contrat JSON strict.
.venv/Scripts/python.exe -m pytest apps/projets/tests/test_swagger_crud_only.py apps/projets/tests/test_creation_formulaire_strict.py -q --reuse-db

Film mental : visualiser un groupe projets avec six operations claires.
En cas de blocage, decouper la verification sans forcer. Attention sur
un invariant, prediction active, retour du test puis rappel le lendemain.
Comprendre, planifier, executer et verifier chaque changement.
Defi de transmission : expliquer a un pair pourquoi une route masquee
reste securisee par ses permissions et comment tester ces deux dimensions.

Livraison : modification locale. Le site distant adoptera ce schema apres
deploiement de la configuration et du module config/schema.py.
