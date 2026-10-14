# B4 — Journal de la plateforme : filtres et pagination (tâche 2.6)

Branche : `feature/lot2-journal-plateforme`
Prérequis : B1 à B3 fusionnées.
Jumelle frontend : `F5_journal_plateforme.md`.

## 1. Contexte

`GET /api/v1/admins/journal-plateforme/` existe :
`JournalPlateformeListView` (`apps/platform_admin/views/impersonation.py:168`). Elle :

- filtre par `entreprise_id` et `action` ;
- **tronque à 200 lignes** (l. 212) sans le dire — au-delà, l'historique est invisible ;
- renvoie un **tableau nu** ;
- affiche pour l'agent son **UUID** dès que l'action n'est pas une assistance
  (`JournalPlateformeSerializer.get_utilisateur_nom`, `serializers/impersonation.py:93` : il
  ne lit que `detail.super_admin_nom`).

Le modèle : `apps/platform_admin/models/journal.py` — `id` (BigAutoField), `utilisateur_id`
(UUID), `entreprise_id` (UUID), `action` (≤ 50 car.), `detail` (JSON), `adresse_ip`,
`appareil`, `horodatage` (indexé). Il est **à insertion seule** : ne jamais ajouter d'écriture.

## 2. Contrat d'API cible

```
GET /api/v1/admins/journal-plateforme/
    ?du=2026-10-01          (facultatif, date incluse)
    &au=2026-10-14          (facultatif, date incluse)
    &utilisateur_id=<uuid>  (facultatif : l'agent)
    &entreprise_id=<uuid>   (facultatif)
    &action=SUSPENSION_CLIENT (facultatif, code exact)
    &page=1&taille_page=100 (pagination standard du produit, 20 par défaut, 100 au plus)
```

Réponse 200 — **le format paginé standard** (`apps/core/pagination.py`, `PaginationStandard`) :

```json
{
  "total": 1342,
  "page": 1,
  "nombre_pages": 14,
  "suivant": "http://.../?page=2&taille_page=100",
  "precedent": null,
  "resultats": [
    {
      "id": 5512,
      "utilisateur_id": "…",
      "utilisateur_nom": "Awa Koné",
      "entreprise_id": "…",
      "entreprise_nom": "Demo BTP",
      "action": "SUSPENSION_CLIENT",
      "detail": {"motif": "…"},
      "adresse_ip": "127.0.0.1",
      "appareil": "Mozilla/5.0 …",
      "horodatage": "2026-10-14T09:12:44.120Z"
    }
  ]
}
```

Tri : `-horodatage`, puis `-id` (deux lignes de la même milliseconde gardent un ordre stable
d'une page à l'autre).

Erreurs 400 (format DRF standard, `details` par champ) :

| Cas | Champ | Message |
|---|---|---|
| `du` ou `au` illisible | `du` / `au` | `"Date invalide : format attendu AAAA-MM-JJ."` |
| `du` > `au` | `au` | `"La date de fin doit être postérieure ou égale à la date de début."` |
| `utilisateur_id` ou `entreprise_id` pas un UUID | le champ | `"Identifiant invalide."` |

Nouvelle route — la liste des codes d'action, pour le menu de filtre :

```
GET /api/v1/admins/journal-plateforme/actions/
→ 200 {"actions": ["ACTIVATION_MODULE", "CHANGEMENT_PLAN", …]}   (distincts, triés)
```

Les deux routes : `IsAuthenticated, EstSuperAdminPlateforme` (SUPERVISEUR **et** SUPPORT).

## 3. Implémentation

### 3.1 Un serializer de filtres — `apps/platform_admin/serializers/impersonation.py`

```python
class FiltresJournalPlateformeSerializer(serializers.Serializer):
    du = serializers.DateField(required=False, error_messages={"invalid": "Date invalide : format attendu AAAA-MM-JJ."})
    au = serializers.DateField(required=False, error_messages={"invalid": "Date invalide : format attendu AAAA-MM-JJ."})
    utilisateur_id = serializers.UUIDField(required=False, error_messages={"invalid": "Identifiant invalide."})
    entreprise_id = serializers.UUIDField(required=False, error_messages={"invalid": "Identifiant invalide."})
    action = serializers.CharField(required=False, max_length=50)

    def validate(self, donnees):
        du, au = donnees.get("du"), donnees.get("au")
        if du and au and du > au:
            raise serializers.ValidationError(
                {"au": "La date de fin doit être postérieure ou égale à la date de début."}
            )
        return donnees
```

### 3.2 Un sélecteur — nouveau fichier `apps/platform_admin/selectors/journal.py`

```python
def journal_plateforme(*, du=None, au=None, utilisateur_id=None, entreprise_id=None, action=None):
    """Le journal filtré, du plus récent au plus ancien — un QuerySet, non évalué."""
```

- `JournalPlateforme.objects.all()` dans `schema_context(get_public_schema_name())` — **la
  requête doit être évaluée dans ce contexte** : la vue appelle la pagination à l'intérieur du
  même `with` (voir 3.4).
- `du` → `horodatage__date__gte=du` ; `au` → `horodatage__date__lte=au` (le `__date` de Django
  convertit dans le fuseau courant : c'est ce que l'utilisateur entend par « le 14 »).
- `.order_by("-horodatage", "-id")`.

Et :

```python
def codes_actions_journal() -> list[str]:
    return sorted(set(JournalPlateforme.objects.values_list("action", flat=True).distinct()))
```

### 3.3 Les noms des agents et des entreprises, sans N+1

Dans le serializer `JournalPlateformeSerializer` :

- `get_utilisateur_nom` : d'abord `self.context.get("noms_agents", {}).get(str(obj.utilisateur_id))`,
  puis le repli actuel (`detail.super_admin_nom`, `super_admin_email`, l'UUID).
- `get_entreprise_nom` : d'abord `self.context.get("noms_entreprises", {}).get(str(obj.entreprise_id))`,
  puis le repli actuel (`detail.entreprise_nom`, `detail.entreprise_schema`, `detail.raison_sociale`,
  l'UUID). **Ajouter `detail.raison_sociale` au repli** : c'est ce que la suppression définitive
  écrit, et l'entreprise n'existe plus pour la retrouver.

Dans la vue, **après** la pagination (seulement pour les lignes de la page) :

```python
ids_agents = {e.utilisateur_id for e in page if e.utilisateur_id}
ids_entreprises = {e.entreprise_id for e in page if e.entreprise_id}
noms_agents = {
    str(u.id): (f"{u.prenom} {u.nom}".strip() or u.email)
    for u in Utilisateur.tous_objets.filter(id__in=ids_agents).only("id", "prenom", "nom", "email")
}
noms_entreprises = {
    str(e.id): (e.nom_commercial or e.raison_sociale)
    for e in Entreprise.objects.filter(id__in=ids_entreprises).only("id", "nom_commercial", "raison_sociale")
}
```

(`tous_objets` : un agent supprimé logiquement doit garder son nom dans l'historique.)

### 3.4 La vue — `apps/platform_admin/views/impersonation.py:168`

Réécrire `get` :

```python
    def get(self, request):
        verifier_super_admin(request.user)
        filtres = FiltresJournalPlateformeSerializer(data=request.query_params)
        filtres.is_valid(raise_exception=True)

        with schema_context(get_public_schema_name()):
            qs = journal_plateforme(**filtres.validated_data)
            pagination = PaginationStandard()
            page = pagination.paginate_queryset(qs, request, view=self)
            contexte = {"noms_agents": ..., "noms_entreprises": ...}   # §3.3
            donnees = JournalPlateformeSerializer(page, many=True, context=contexte).data
            return pagination.get_paginated_response(donnees)
```

- Supprimer la troncature à 200.
- Mettre à jour `@extend_schema` : ajouter les paramètres `du`, `au`, `utilisateur_id`,
  `page`, `taille_page`, et `responses={200: JournalPlateformeSerializer(many=True)}` —
  drf-spectacular enveloppe dans le schéma paginé si on passe par
  `PaginationStandard().get_paginated_response_schema` ; à défaut, décrire la réponse dans
  `description`. Ne pas perdre de temps là-dessus : le contrat §2 fait foi.
- Mettre à jour la description : « Consulte le journal… paginé, 20 par page par défaut ».

Nouvelle vue dans le même fichier :

```python
class ActionsJournalPlateformeView(APIView):
    """`GET /api/v1/admins/journal-plateforme/actions/` — les codes d'action présents au journal."""

    permission_classes = [IsAuthenticated, EstSuperAdminPlateforme]

    def get(self, request):
        verifier_super_admin(request.user)
        with schema_context(get_public_schema_name()):
            return Response({"actions": codes_actions_journal()}, status=status.HTTP_200_OK)
```

L'ajouter à `__all__` de `views/impersonation.py`, à l'import de `views/__init__.py` si les
autres y sont réexportées, et dans `apps/platform_admin/urls.py` **avant** la route existante :

```python
    path(
        "admins/journal-plateforme/actions/",
        ActionsJournalPlateformeView.as_view(),
        name="journal-plateforme-actions",
    ),
```

### 3.5 Le test existant qui lit un tableau

`apps/platform_admin/tests/test_impersonation.py:230` fait
`[entree["action"] for entree in rep_journal.data]`. Le remplacer par
`rep_journal.data["resultats"]`. C'est le seul consommateur (vérifié : le frontend n'appelle
pas encore cette route ; `tests/acceptation/lot9/test_a07_a08_propagation_roles_systeme.py:152`
ne fait qu'un `POST` refusé, il n'est pas concerné).

## 4. Tests

Nouveau fichier `apps/platform_admin/tests/test_journal_plateforme.py`. Fixtures : un
superviseur et un SUPPORT (`_agent`, voir B1), `autoriser_ip_locale`, `client_api` sur
`localhost`. Créer les lignes directement :
`JournalPlateforme.objects.create(utilisateur_id=..., entreprise_id=..., action=..., detail={})`
dans le schéma public, puis **forcer** leur `horodatage` par
`JournalPlateforme.objects.filter(pk=...).update(horodatage=...)` (`auto_now_add` empêche de
le passer à la création).

| Test | Vérifie |
|---|---|
| `test_journal_pagine_au_format_standard` | 25 lignes créées → `total >= 25`, `len(resultats) == 20`, `nombre_pages >= 2`, clés `suivant`/`precedent` présentes |
| `test_taille_page_plafonnee_a_100` | `taille_page=500` → au plus 100 résultats |
| `test_filtre_par_periode_bornes_incluses` | lignes le 01/10, 05/10, 10/10 ; `du=2026-10-05&au=2026-10-10` → exactement les deux dernières |
| `test_filtre_par_agent` | deux agents ; `utilisateur_id=<A>` → seulement les lignes de A |
| `test_filtre_par_entreprise_et_action` | combinaison des deux filtres |
| `test_periode_inversee_refusee` | `du > au` → 400, `details.au` |
| `test_date_illisible_refusee` | `du=14/10/2026` → 400, `details.du` |
| `test_nom_de_l_agent_resolu` | `utilisateur_nom` = « Prénom Nom » de l'agent, pas son UUID |
| `test_nom_d_entreprise_supprimee_lu_dans_le_detail` | ligne avec `entreprise_id` inconnu et `detail={"raison_sociale": "Ancienne SARL"}` → `entreprise_nom == "Ancienne SARL"` |
| `test_ordre_stable_a_horodatage_egal` | deux lignes de même horodatage : l'`id` le plus grand vient d'abord |
| `test_support_lit_le_journal` | SUPPORT → 200 |
| `test_liste_des_actions_distinctes_triees` | `GET .../actions/` → liste triée sans doublon, contient les actions créées |
| `test_nombre_de_requetes_constant` | avec `django_assert_max_num_queries(8)` : une page de 20 lignes de 20 agents différents ne fait pas 20 requêtes |

Pour les dates, utiliser des `datetime` **aware** :
`timezone.make_aware(datetime(2026, 10, 5, 12, 0))`.

## 5. Pièges

- **Évaluer le QuerySet dans `schema_context("public")`** : la vue tourne sur le domaine de la
  plateforme, donc déjà en `public` en pratique, mais un appel depuis un sous-domaine lirait
  le mauvais schéma sans erreur.
- **`horodatage__date` et le fuseau** : ne pas remplacer par une comparaison
  `horodatage__gte=datetime(du)` naïve, qui décalerait la borne de l'écart UTC.
- **Ne pas paginer avant de filtrer** : `paginate_queryset` reçoit le QuerySet filtré et trié.

## 6. Définition de terminé

- [ ] Contrat §2 servi, troncature supprimée, route `actions/` ajoutée.
- [ ] 13 tests verts ; `test_impersonation.py` adapté ; `ruff` propre ; aucun échec nouveau.
- [ ] Commit : `feat(platform_admin): journal de la plateforme filtre par periode et par agent, pagine`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
