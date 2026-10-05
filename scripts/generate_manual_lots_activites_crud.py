"""Manuel pratique, Sprint 4, identifiant descriptif faute de numéro de backlog."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Manuels_Apprentissage/MANUEL_SPRINT_4_TACHE_CRUD_LOTS_ACTIVITES.pdf"
SECTIONS = [
    (
        "1. Film mental et objectif",
        [
            (
                "Visualiser un chantier : ouvrir un lot, corriger son nom, désactiver une "
                "activité, la réactiver puis supprimer une activité sans perdre son "
                "historique. La visualisation sert de préparation, sans garantie de "
                "performance."
            ),
            (
                "Contrat : GET et PATCH /api/v1/lots/{id}/ et /api/v1/activites/{id}/ ; "
                "DELETE sur les mêmes routes ; PATCH /activation/ avec est_actif true ou "
                "false. Succès : 200, suppression : 204 sans corps."
            ),
            (
                "Sprint 4 retenu d'après les travaux récents ; CRUD_LOTS_ACTIVITES est un "
                "identifiant descriptif, à remplacer si le backlog attribue un numéro "
                "officiel."
            ),
        ],
    ),
    (
        "2. Architecture et invariants",
        [
            (
                "Projet -> Lot -> Activite. Les UUID parents restent immuables ; quantités "
                "réalisées, avancement et baseline ne sont pas éditables par ces endpoints. "
                "Budget exprimé en centimes FCFA."
            ),
            (
                "Authentification, permission du module Projets et appartenance au projet "
                "sont cumulatives. Le détail nécessite LECTURE ; les mutations ECRITURE. Un "
                "UUID modifié ne doit jamais donner accès à un autre chantier."
            ),
            (
                "Supprimer signifie renseigner supprime_le et supprime_par : aucune "
                "suppression physique. Un lot contenant des activités non supprimées est "
                "protégé. Une activité avec des successeurs non supprimés est protégée."
            ),
            (
                "Désactiver conserve les données et ne cascade pas vers les enfants. "
                "Réactiver une activité nécessite un lot actif. Les objets dont le parent "
                "est supprimé sont inaccessibles."
            ),
        ],
    ),
    (
        "3. Implémentation pas à pas",
        [
            (
                "Étape 1 : lire ModeleBase et ManagerActif. Prédire pourquoi une ligne "
                "supprimée devient invisible avant d'exécuter la requête."
            ),
            (
                "Étape 2 : dériver les serializers de modification des serializers de "
                "création. Fusionner les valeurs envoyées avec les valeurs de l'instance "
                "uniquement pour valider ; sauvegarder seulement les champs transmis."
            ),
            (
                "Étape 3 : vérifier chronologie, bornes du lot, dépendances sans cycle, "
                "équipe autorisée et quantité prévue compatible avec le réalisé. Conserver "
                "les dates baseline existantes."
            ),
            (
                "RG-11 : une date prévisionnelle déjà renseignée ne peut pas être "
                "changée par PATCH. Utiliser POST /lots/{id}/reprogrammer/ ou "
                "/activites/{id}/reprogrammer/ avec motif et justification. Une date "
                "vide peut être initialisée après validation des bornes."
            ),
            (
                "Étape 4 : créer les vues de détail et d'activation, vérifier les "
                "permissions objet puis utiliser transaction.atomic et select_for_update. "
                "Verrouiller le projet puis le lot puis l'activité, comme la création "
                "d'activité, pour sérialiser les changements de dépendance entre lots."
            ),
            (
                "Étape 5 : déclarer les routes et annoter chaque méthode avec "
                "extend_schema, request et responses. Ne documenter que les méthodes "
                "réellement implémentées."
            ),
            (
                'Exemple : PATCH /lots/{id}/ avec {"nom": "Fondations"}. Exemple : PATCH '
                '/activites/{id}/ avec {"libelle": "Terrassement"}. Exemple : PATCH '
                '/activation/ avec {"est_actif": false}.'
            ),
        ],
    ),
    (
        "4. Signal d'erreur et pre-mortem",
        [
            (
                "Piège 1 : PATCH d'une seule date. Si la validation oublie l'autre date "
                "enregistrée, elle accepte une chronologie invalide. Vérifier 400 et "
                "absence de mutation."
            ),
            (
                "Piège 2 : quantité par défaut lors d'un PATCH du libellé. Vérifier que la "
                "quantité et l'équipe ne changent pas. Les valeurs par défaut de création "
                "ne doivent pas écraser l'existant."
            ),
            (
                "Piège 3 : supprimer un parent laisse des enfants accessibles par leurs "
                "UUID. Bloquer les suppressions avec enfants et filtrer les parents "
                "supprimés dans les nouvelles vues."
            ),
            (
                "Piège 4 : dépendance sur soi-même ou cycle indirect. Parcourir les "
                "prédécesseurs avec un ensemble d'UUID déjà visités ; rejeter les cycles "
                "avec 400."
            ),
            (
                "Pólya : comprendre, planifier, exécuter, vérifier. Kahneman : ralentir sur "
                "droits, concurrence et suppression. Utiliser les erreurs observées pour "
                "réviser son hypothèse plutôt que forcer une conclusion."
            ),
        ],
    ),
    (
        "5. Tests et validation",
        [
            (
                "Tester chaque route : anonyme, membre sans écriture, administrateur, "
                "utilisateur hors projet, objet supprimé. Vérifier 401/403/404 selon le cas."
            ),
            (
                "Tester modification partielle, champs inconnus, dates, budget négatif, "
                "quantité, baseline conservée, équipe et dépendances. Tester état false "
                "puis true et répétition idempotente."
            ),
            (
                "Tester suppression logique et acteur, 204 sans corps, refus d'un lot avec "
                "activités et d'une activité avec successeurs. Tester refus de création "
                "d'activité dans un lot désactivé."
            ),
            (
                "Générer le schéma avec SchemaGenerator(urlconf='config.urls_tenant') et "
                "vérifier présence de GET/PATCH/DELETE et des routes d'activation sous lots "
                "et activités."
            ),
            (
                "Commande : python -m pytest "
                "apps/projets/tests/test_lots_activites_mutations.py "
                "apps/projets/tests/test_swagger_crud_only.py "
                "apps/projets/tests/test_lots_api.py "
                "apps/projets/tests/test_activites_formulaire.py -q --reuse-db."
            ),
            (
                "Après livraison : attendre le déploiement effectif, ouvrir Swagger, "
                "authentifier un compte de test et vérifier les opérations. Un push seul ne "
                "prouve pas que le serveur a chargé le nouveau code."
            ),
        ],
    ),
    (
        "6. Défi Homo Docens",
        [
            (
                "Expliquer à un pair pourquoi désactivation et suppression logique sont "
                "distinctes, et pourquoi une validation PATCH doit relire l'état courant."
            ),
            (
                "Mobiliser attention, engagement actif, retour d'erreur et consolidation : "
                "prédire le résultat, lancer le test, expliquer l'écart, reprendre "
                "l'exercice le lendemain. Réutiliser les schémas familiers et actualiser "
                "ses attentes avec les résultats."
            ),
            (
                "Murphy comme métaphore de préparation : film mental concret et confiance "
                "dans une démarche vérifiable ; en cas de blocage, relâcher l'effort forcé, "
                "prendre une pause puis revenir à un seul cas de test. Aucune promesse de "
                "reprogrammation automatique."
            ),
        ],
    ),
]


def main():
    OUTPUT.parent.mkdir(exist_ok=True)
    styles = getSampleStyleSheet()
    story = [Paragraph("Manuel pratique : lots et activités", styles["Title"])]
    for title, paragraphs in SECTIONS:
        story.append(Paragraph(title, styles["Heading1"]))
        for paragraph in paragraphs:
            story.extend([Paragraph(escape(paragraph), styles["BodyText"]), Spacer(1, 9)])
    for name in (
        "apps/projets/serializers/lot.py",
        "apps/projets/serializers/activite.py",
        "apps/projets/views/lot.py",
        "apps/projets/views/activite.py",
    ):
        story.extend([PageBreak(), Paragraph("Annexe : " + name, styles["Heading1"])])
        code_style = styles["Code"].clone("Source")
        code_style.fontSize = 6
        code_style.leading = 8
        story.append(
            Preformatted((ROOT / name).read_text(encoding="utf-8"), code_style, maxLineLength=110)
        )
    SimpleDocTemplate(str(OUTPUT)).build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()
