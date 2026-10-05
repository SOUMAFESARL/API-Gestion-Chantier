"""Manuel reproductible pour le motif informatif des lots et activités."""

import generate_manual_lots_activites_crud as manuel

manuel.OUTPUT = manuel.ROOT / "Manuels_Apprentissage/MANUEL_SPRINT_4_TACHE_MOTIF_LOTS_ACTIVITES.pdf"
manuel.SECTIONS = [
    (
        "1. Film mental et objectif",
        [
            "Visualiser POST puis GET avec motif : Suspension pour intempéries. "
            "Prédire puis vérifier la conservation du texte. Sprint 4 et identifiant descriptif "
            "retenus faute de référence officielle. La visualisation sert de préparation.",
        ],
    ),
    (
        "2. Architecture et invariants",
        [
            "Projet -> Lot -> Activite. motif est un TextField(blank=True, default='') "
            "sur les deux modèles : texte facultatif, vide autorisé, null interdit. "
            "Il est indépendant du référentiel motif_id de reprogrammation.",
            "Conserver les permissions de module et de projet, les UUID parents et "
            "la suppression logique. Le motif informatif ne déclenche aucune transition.",
        ],
    ),
    (
        "3. Guide pratique",
        [
            "Ajouter motif aux deux modèles et créer la migration 0025, dépendante de 0024. "
            "Appliquer python manage.py migrate_schemas --tenant avant utilisation.",
            "Déclarer motif = serializers.CharField(required=False, allow_blank=True, "
            "trim_whitespace=False) dans les serializers de création. Les serializers "
            "PATCH héritent du champ ; les serializers de réponse doivent aussi l'exposer.",
            'Exemple POST ou PATCH : {"statut": "Suspendu", "motif": "Intempéries"}. '
            'Sans motif en création : "". Sans motif en PATCH : conservation. '
            'Envoyer {"motif": ""} pour effacer. Accents et espaces conservés.',
            "Mettre à jour les exemples Swagger. Les annexes présentent les serializers "
            "et vues effectivement utilisés, pour relier le contrat à son implémentation.",
        ],
    ),
    (
        "4. Signal d'erreur et pre-mortem",
        [
            "Piège : accepter motif mais l'oublier en réponse. Piège : une valeur par défaut "
            "du serializer efface motif lors d'un PATCH sans ce champ. Piège : utiliser "
            "ce texte à la place du motif_id obligatoire de reprogrammation.",
            "Pólya : comprendre le contrat avant de contrôler la sauvegarde. Ralentir "
            "sur migration et permissions ; réviser ses hypothèses avec les erreurs observées.",
        ],
    ),
    (
        "5. Validation",
        [
            "Tester POST, GET, PATCH du motif, PATCH d'un autre champ préservant motif, "
            "effacement par chaîne vide et refus de null. Tester lots et activités.",
            "Vérifier Swagger : motif string, facultatif et modifiable en entrée ; présent "
            "en sortie. Comparer migration et modèles. Exécuter test_lots_activites_mutations, "
            "test_lots_api, test_activites_formulaire, test_lots_activites_validation et "
            "test_swagger_crud_only avec pytest. Tests PostgreSQL : --reuse-db.",
        ],
    ),
    (
        "6. Défi Homo Docens",
        [
            "Expliquer à un pair pourquoi facultatif ne signifie pas nullable. Prédire, "
            "tester, expliquer puis reprendre le lendemain : attention, engagement actif, "
            "retour d'erreur et consolidation. Utiliser le film mental comme préparation, "
            "soutenir la confiance par des résultats vérifiés et relâcher la pression si "
            "un cas bloque, sans promesse de reprogrammation automatique.",
        ],
    ),
]

if __name__ == "__main__":
    manuel.main()
