# API du journal de chantier

Sprint 4, tâche descriptive CRUD_JOURNAL_CHANTIER (numéro de backlog non fourni).
Source : captures du 07/10/2026 et lecture seule de features/chantier/adaptateur.ts,
types.ts, validations.ts et regles.ts du frontend.

## 1. Film mental et objectif

Visualiser un chef de chantier qui retrouve son brouillon, ajoute les quantités
réalisées, enregistre, soumet puis retrouve les signatures du CT et du CP.
Cette répétition mentale prépare l'action ; elle ne remplace pas les tests.
Avancer par petites étapes observables évite de forcer une solution en cas de blocage.

## 2. Architecture et invariants

Le module existant apps.chantier et ses routes /api/v1/rapports/ restent compatibles.
Les nouvelles routes sont sous /api/v1/chantier/. Un rapport couvre un projet et
une date, avec plusieurs lots. RapportJournalier porte l'identité, les auteurs,
les dates et le statut ; un complément JournalChantier porte la saisie structurée
et les signatures intermédiaires. Les rubriques JSON sont validées par des
serializers imbriqués ; les UUID de lots et d'activités sont contrôlés en base.
Les données résident dans le schéma du tenant. Chaque accès exige la permission
du module et le périmètre projet. Seul l'auteur modifie son brouillon.

BROUILLON -> SOUMIS -> VALIDE_CT -> APPROUVE_CP ; un rejet motivé rend la saisie
modifiable. Le statut historique APPROUVE représente la signature finale du CP.
Les rapports soumis sont immuables. La fenêtre de saisie va de J-2 à J,
en heure Africa/Abidjan. Les mises à jour et signatures utilisent des transactions
et des verrous pour éviter les soumissions concurrentes et les doubles signatures.
Le journal est déclaratif : aucune sortie de stock ni paiement automatique.

## 3. Guide d'implémentation par la pratique

1. Lire les contrats du frontend et tracer un exemple de payload complet.
2. Créer le modèle de complément, sa migration et les serializers imbriqués.
3. Implémenter les services transactionnels, puis les selectors de lecture.
4. Brancher les vues et documenter les routes OpenAPI.
5. Tester le parcours réel, puis les refus d'accès et les erreurs de saisie.

Routes principales :
- GET/POST /api/v1/chantier/rapports/
- GET /api/v1/chantier/rapports/preparation/?projet=<uuid>&date=AAAA-MM-JJ
- GET/PATCH/DELETE /api/v1/chantier/rapports/<uuid>/
- PATCH /api/v1/chantier/rapports/<uuid>/draft/
- POST /api/v1/chantier/rapports/<uuid>/soumettre/
- POST /api/v1/chantier/rapports/<uuid>/valider/
- POST /api/v1/chantier/rapports/<uuid>/approuver/
- POST /api/v1/chantier/rapports/<uuid>/rejeter/
- GET /api/v1/chantier/journal/?date_debut=&date_fin=

Un brouillon accepte des champs incomplets et des nombres null. La soumission
exige les horaires, la météo, une note de 10 caractères et les rubriques
applicables. Les effectifs présents ne dépassent pas les prévus, les retards
ne dépassent pas les présents. Une absence ou un retard exige une observation.
Une journée d'arrêt ne déclare ni travail, ni personnel, ni consommation.
Photos : 5 maximum ; documents : 3 maximum. Les médias sont servis par une
réponse authentifiée du tenant et du projet, jamais par une URL publique.
Les fichiers data: base64 sont validés (type réel des images, signature des
documents, taille, extension), puis conservés dans la saisie JSON PostgreSQL.
Chaque fichier est limité à 2 Mio et le rapport complet à 16 Mio. Les images
restent directement affichables par le frontend, sans perdre l'authentification
sur une balise image. Ce choix convient aux volumes bornés du formulaire ; un
stockage binaire privé séparé sera préférable si le volume de médias augmente.

Les prix unitaires sont en centimes FCFA. Leur lecture et leur écriture exigent
projets.voir_montants ; les réponses masquent les tarifs avec null pour CC/CT.
La production quantitative peut être soumise sans tarif. Le frontend devra
rendre ce champ facultatif pour les utilisateurs sans ce droit. Un null renvoyé
par la saisie masquée conserve un tarif préexistant en base.

La validation CT exige chantier.valider et l'affectation CT. L'approbation CP
exige chantier.rediger (droit du gabarit CP actuel), l'affectation CP ou la
responsabilité chef_projet, et la signature CT préalable. Le droit de rédaction
seul ne suffit pas. Un utilisateur ne signe jamais son propre rapport.
Un motif de rejet exige 20 caractères. Le journal d'audit conserve les étapes
et commentaires antérieurs, y compris après correction et resoumission.

POST /api/v1/chantier/rapports/<uuid>/alertes/ enregistre une notification interne
dédupliquée par clé. GET /api/v1/chantier/alertes/ fournit la liste paginée adressée
à l'utilisateur (CT/CP). Ce canal est interne : aucun email ou push n'est envoyé.

## 4. Signal d'erreur et pré-mortem

Hypothèse : un UUID valide serait accessible. Réfutation : tester un projet
non affecté et un autre tenant. Hypothèse : deux autosauvegardes seraient sans
danger. Réfutation : verrouiller le rapport et refuser les modifications après
soumission. Hypothèse : un brouillon complet équivaut à une soumission.
Réfutation : vérifier les valeurs null et les contraintes au moment de soumettre.
Les erreurs sont des informations qui corrigent le modèle mental (Dehaene),
et non une mesure de la valeur du développeur. Examiner les données avant
d'adopter la première explication (Kahneman).

## 5. Checklist de tests et validation

- Création, lecture, PATCH partiel et reprise depuis préparation.
- Doublon projet/date, UUID extérieur, fenêtre J-2, brouillon d'un autre auteur.
- Soumission incomplète refusée sans écriture partielle.
- Rapport soumis verrouillé ; validation CT, approbation CP et rejet motivé.
- Limites de médias et téléchargement protégé.
- Compatibilité avec la suite existante apps/chantier/tests/test_rapports_api.py.
- manage.py check ; makemigrations --check --dry-run ; tests pytest ciblés.

## 6. Défi Homo Docens

Sans ouvrir le code, expliquer à un pair pourquoi un PATCH conserve les sections
absentes, pourquoi la validation est différente pour un brouillon et une
soumission, et pourquoi un verrou SQL protège une signature. Rejouer le parcours
en rappel actif (attention, engagement, retour d'erreur et consolidation), puis
vérifier les explications avec les tests. Réutiliser les patterns connus de
serializers et transactions pour rendre le nouveau domaine plus familier.

## Branchement frontend

JOURNAL_SIMULE et SAISIE_SIMULEE dans features/chantier/adaptateur.ts maintiennent
actuellement la simulation. Le développeur devra les basculer une fois les
migrations appliquées. Aucun fichier frontend n'est modifié par l'agent.
Sous ces routes, le contrat de saisie reprend les noms de ChargeSaisie :
projet_id, date, heure_debut, heure_fin, arret, meteo, effectifs,
presence_sous_traitant, production, lots_travailles, activites, materiaux,
livraisons, besoins, equipements, incidents, blocage, photos, pieces_jointes,
previsions et note_cc. GET détail renvoie aussi saisie pour reprendre le formulaire.

Le CRUD, la préparation, le journal quotidien, les filtres historiques et le
circuit de signatures sont couverts. Les synthèses périodiques agrégées, les
relances manuelles et la planification automatique de 17h30 sont des extensions
distinctes ; leurs routes proposées par le frontend ne sont pas livrées ici.
Le stock proposé dans préparation est vide : le module stocks n'a pas de modèle
concret. Les matériaux peuvent être déclarés librement. Le cumul de quantité
provient des journaux soumis antérieurs, avec la valeur initiale du planning,
et n'altère pas directement les quantités du planning. Les photographies des
rapports soumis conservent les libellés et références connus à la soumission.
Le tableau des rapports manquants utilise les jours ouvrés (lundi-vendredi)
et les dates actuelles des projets actifs ; il ne reconstitue pas un calendrier
historique d'activité, de congés ou de jours fériés.

## Activation et validation locale

La migration est apps/chantier/migrations/0005_alertejournal_journalchantier_and_more.py.
Elle crée les compléments et alertes et adapte l'unicité des rapports non supprimés.
Sur un environnement avec historique cohérent :

    .venv/Scripts/python.exe manage.py migrate_schemas
    .venv/Scripts/python.exe -m pytest apps/chantier/tests/ --reuse-db -q

Lors de cette tâche, la base locale ccd_digital présente une incohérence préalable :
tiers.0001_initial est enregistrée avant sa dépendance
accounts.0001_squashed_0018_seed_permission_modules_m2m. Son historique n'a pas
été modifié. Le schéma neuf a été migré et les tests ont été exécutés dans
test_journal_api_validation, issu de la base isolée journal_api_validation.
Ne pas falsifier les enregistrements django_migrations sans vérifier les tables
et les opérations réellement appliquées. La correction de cet historique reste
nécessaire avant l'activation sur cette base précise.

Exemple minimal de création (le brouillon peut rester incomplet) :

    POST /api/v1/chantier/rapports/
    {"projet_id": "<uuid-projet>", "date": "2026-10-07"}

Réponse 201 : id, statut BROUILLON, saisie normalisée, enregistre_le,
commentaire_rejet et alertes_envoyees. PATCH accepte les seules rubriques modifiées
et fusionne les champs météo/blocage ; un tableau fourni remplace ce tableau.
Soumettre accepte le payload complet ou {} si le brouillon est déjà complet.
Réponse : id et reference. La validation CT et l'approbation CP acceptent
{"commentaire": "..."}. Le rejet accepte {"motif": "20 caractères minimum"}.
DELETE renvoie 204 sans corps. Les erreurs suivent le format erreur.code,
erreur.message, erreur.details et erreur.trace_id déjà commun au projet.

## Résultats de vérification

42 tests passent : 25 tests de parcours du journal (paramétrisations comprises),
8 validations pures et 9 tests de compatibilité des anciennes routes.
Ruff passe sur les nouveaux fichiers. Aucune migration supplémentaire n'est
détectée par makemigrations --check --dry-run. La vérification des modèles Django
et la génération du schéma du journal sont contrôlées séparément.
Le schéma global conserve des erreurs préexistantes de déclaration de serializers
dans le module accounts ; les routes du journal disposent de leurs annotations.
check --deploy avec les paramètres de test signale cinq avertissements de sécurité
(HSTS, redirection HTTPS, qualité de la clé locale et cookies sécurisés) ; ces
paramètres de test ne constituent pas une configuration de déploiement.
