# Statuts du projet

POST /api/v1/projets/ accepte `statut`, facultatif, avec EN_ATTENTE par défaut.
Les réponses POST, GET liste, GET détail, PUT et PATCH exposent `statut`.
Les valeurs existantes sont conservées : EN_ATTENTE, EN_COURS, EN_RETARD,
CRITIQUE, SUSPENDU, TERMINE, ARCHIVE. Ajouts : BLOQUE, DESACTIVE, RESILIE.

Tout utilisateur authentifié ayant accès au projet par les règles d'appartenance
existantes peut envoyer PATCH /api/v1/projets/<id>/ avec uniquement :

```json
{"statut": "SUSPENDU"}
```

Utiliser BLOQUE pour bloquer, DESACTIVE pour désactiver, RESILIE pour résilier,
EN_COURS pour réactiver. Toutes les valeurs définies sont acceptées, y compris
la réactivation après résiliation. Les états sont descriptifs ; ils ne bloquent
pas les opérations et ne modifient pas les activités ni les affectations.

Les autres modifications, même mélangées au statut dans un PATCH, exigent les
permissions d'écriture existantes. POST conserve la permission Direction.
PUT sans statut préserve l'état existant. Les statuts inconnus donnent HTTP 400 ;
un membre sans accès au projet ne peut pas changer son statut.

Déploiement : appliquer la migration 0017 via le mécanisme de migrations des
schémas tenants (manage.py migrate_schemas), puis redémarrer le backend.

Validation : tests CRUD des statuts, persistance, accès visiteur, refus hors
projet, affectation inactive, requête mixte, valeurs invalides et anonyme.

Apprentissage : visualiser PATCH -> contrôle d'appartenance -> validation ->
enregistrement -> JSON. Prédire le résultat avant le test, vérifier l'hypothèse,
puis expliquer pourquoi une exception de permission doit rester limitée au
seul champ statut. Refaire cette explication le lendemain.
