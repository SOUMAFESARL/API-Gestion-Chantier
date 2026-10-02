# Correction des regressions CI du CRUD projets

## 1. Film mental et objectif

Visualisez une CI verte avec un CRUD strict et des invariants metier intacts. La visualisation sert a preparer le travail : predire un resultat, tester, comparer. En cas de blocage, reduire le probleme sans forcer.

## 2. Architecture et invariants

Le formulaire public expose onze champs. Les champs techniques, les lots et equipe restent hors du CRUD. ProjetCreationSerializer demeure un orchestrateur interne ; les tests de ses lots et invitations le sollicitent directement, sans recreer un endpoint public. Baseline v0 reste immuable. RG-11 impose une route de reprogrammation pour changer les dates deja definies.

## 3. Correction pas a pas

Dans ProjetPostSerializer.to_internal_value, traiter explicitement les champs baseline interdits lors des modifications pour conserver le message metier Baseline v0. Dans ProjetPatchSerializer.validate, comparer les dates effectives d un PUT au planning existant : une omission ne doit pas effacer une date sous protection RG-11. Dans la reponse, le maitre ouvrage des projets historiques est le texte saisi ou le nom du client lie. Aucun nouveau champ JSON.

## 4. Adapter les tests sans affaiblir les invariants

Les tests API utilisent Location pour les actions sur un projet et reference pour les listes. L auteur se verifie en base et ne se retrouve plus dans le JSON. Les identites falsifiees sont refusees avant toute creation. Les tests membres internes verifient encore utilisateurs inexistants, inactifs, roles multiples, isolation et rollback. Les affectations se testent sur leurs routes specialisees. Les tests onboarding utilisent le maitre ouvrage textuel, sans creer une liaison client implicite.

## 5. Signal erreur et pre-mortem

Trois pieges : croire que tous les rejets 400 prouvent une regle metier alors que le filtre des champs intervient plus tot ; transformer un service interne en faux endpoint dans les tests ; effacer silencieusement le planning en PUT. ResultatService est un adaptateur de tests du serializer, sans route ni permissions HTTP : la securite est couverte par les vrais tests API. Ne pas ignorer des tests backend pour obtenir une CI verte.

## 6. Validation et transmission

Executer la suite apps avec la seule exclusion deja utilisee en CI pour le referentiel TypeScript externe. Sous Windows, fournir un basetemp dans le workspace pour eviter les permissions du repertoire temporaire global. Verifier Ruff et manage.py check. Attention : focaliser un invariant ; engagement actif : predire ; retour : comparer le test ; consolidation : reproduire le raisonnement le lendemain. Expliquer a un pair pourquoi les tests publics et internes ont des contrats differents. Comprendre, planifier, executer, verifier.

Commande CI :
```powershell
.venv/Scripts/python.exe -m pytest apps -q --reuse-db --deselect=apps/projets/tests/test_meteo.py::test_le_referentiel_typescript_ne_derive_pas
```


L entete Location est expose via CORS afin que le navigateur puisse lire
l URL du projet cree sans identifiant technique dans le JSON.


Validation finale : 538 tests reussis, 1 deselection identique a la CI,
3 avertissements. manage.py check sans probleme nouveau. Ruff valide le
serializer et les tests modifies ; les six constats preexistants dans
config/settings/base.py sont inchanges. Aucune migration supplementaire.
