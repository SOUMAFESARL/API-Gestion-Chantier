# B6 — Les routes absentes du schéma OpenAPI (phase B)

Branche : `feature/lot4-openapi`
Prérequis : B1 à B5 fusionnées.

## 1. Contexte

Le plan d'alignement (`../Application-Gestion-Chantier/docs/plan_alignement_api.md:73`) relève
**18 routes absentes du schéma OpenAPI, dont 15 du module projets** (relevé du 13/10/2026). Le schéma
sert au frontend de contrat lisible (`/api/schema/`, Swagger) : une route absente n'a pas de
contrat écrit, et c'est exactement ce qui a laissé passer les écarts de ce lot.

## 2. Méthode

1. Générer le schéma : `.venv/Scripts/python.exe manage.py spectacular --file scratch_schema.yml --validate`
   (fichier hors dépôt ou ignoré ; **ne pas le commiter**). Noter les **avertissements** : une vue
   sans `serializer_class` ni `@extend_schema` y apparaît (« unable to guess serializer »).
2. Lister toutes les routes du résolveur (`django.urls.get_resolver`, sur le modèle de
   `tests/fabriques_lot9.py:309`, `routes_admin_en_ecriture`) et les comparer aux chemins du schéma,
   **méthode par méthode**. Écrire la liste des manquantes dans le compte rendu (on en attend 18,
   peut-être plus après les lots 2 à 4).
3. Pour chaque route manquante ou mal décrite : ajouter `@extend_schema(summary=…, request=…,
   responses={…})` avec les **vrais** serializers (ceux que la vue utilise ; en créer un de réponse
   si la vue construit un dict à la main), `tags` du module, et les `OpenApiParameter` des paramètres
   de requête. Ne changer **aucun** comportement.
4. Couvrir en priorité les routes branchées dans ce lot : `reprogrammer/`, `historique-dates/`,
   `journal-reports/`, `motifs-report/`, `affectations/` (avec `zone`, `fonction_membre`),
   `equipes/…/membres/`, `sante/…`, `lots/import/`, `lots/modele/`.

## 3. Test

`apps/projets/tests/test_schema_openapi.py` :

- `test_schema_sans_avertissement_pour_projets` : générer le schéma en mémoire
  (`drf_spectacular.generators.SchemaGenerator().get_schema(request=None, public=True)`) et vérifier
  que **chaque** route du module projets (liste construite depuis le résolveur, préfixes `projets/`,
  `lots/`, `activites/`, `arrets-chantier/`, `referentiels/motifs-report/`) y figure avec ses méthodes.
- `test_reprogrammer_documente` : le chemin `…/reprogrammer/` a un `requestBody` qui cite
  `motif_id` et `justification`.

## 4. Définition de terminé

- [ ] Liste des routes manquantes dans le compte rendu ; toutes documentées ; aucun comportement changé.
- [ ] 2 tests verts ; aucun échec nouveau ; `ruff` propre.
- [ ] Commit : `docs(api): les routes du module projets declarees au schema OpenAPI`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
