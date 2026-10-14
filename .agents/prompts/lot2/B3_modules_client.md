# B3 — Modules d'un client : le module Projets ne se désactive jamais (tâche 2.3)

Branche : `feature/lot2-modules-client`
Prérequis : B1 fusionnée.
Jumelle frontend : `F3_modules_client.md`.

## 1. Contexte — ce qui existe déjà

Tout est servi, sauf une règle :

| Route | Vue | État |
|---|---|---|
| `GET /api/v1/admins/clients/{id}/` | `FicheClientPlateformeView` | Renvoie déjà `modules: [{id, code, libelle, actif}]` (`selectors/clients.py:154`, `modules_du_client`) |
| `POST /api/v1/admins/clients/{id}/modules/{module_id}/activer/` | `ActiverModuleClientPlateformeView` (`views/clients.py:432`) | Active, crée les lignes de droits des rôles, journalise, prévient le DG |
| `POST /api/v1/admins/clients/{id}/modules/{module_id}/desactiver/` | `DesactiverModuleClientPlateformeView` (`views/clients.py:544`) | Désactive, journalise, prévient le DG |

Les deux actions restent **ouvertes au SUPPORT** (décision B1). Les données du module ne sont
**jamais** effacées par une désactivation : seul l'accès est coupé
(`EntrepriseModule.est_actif = False`, lu par `core.droits._obtenir_modules_actifs`).

**Ce qui manque** : rien n'empêche de désactiver le module `projets`, socle de tout l'espace
d'une entreprise (le journal de chantier, les finances et les stocks se rattachent à un
projet). Désactivé, l'espace devient vide sans qu'aucun message ne dise pourquoi.

## 2. Ce qu'il faut faire

### 2.1 La règle, en un seul endroit

Dans `apps/platform_admin/views/clients.py`, au niveau module (après les imports) :

```python
# Le socle de l'espace d'une entreprise : sans lui, plus aucun module n'a de quoi s'accrocher.
MODULES_SOCLE = frozenset({"projets"})
```

Dans `DesactiverModuleClientPlateformeView.post`, **juste après** avoir obtenu `module`
(ligne ~553, avant toute écriture) :

```python
            if module.code.lower() in MODULES_SOCLE:
                raise ErreurConflit(
                    detail=(
                        f"Le module {module.libelle} est le socle de l'espace d'une entreprise : "
                        "il ne peut pas être désactivé."
                    )
                )
```

(`from apps.core.exceptions import ErreurConflit`.) Réponse : **409**, code `conflit`.

Rien n'est écrit, rien n'est journalisé, aucun courriel ne part.

### 2.2 Exposer la règle au frontend

Pour que l'écran puisse griser l'interrupteur au lieu d'attendre le 409, ajouter un champ
`desactivable` à chaque module de la fiche :

- `apps/platform_admin/selectors/clients.py`, `modules_du_client` (l. 154) : ajouter
  `"desactivable": m.code.lower() not in MODULES_SOCLE` au dict.
- **Ne pas importer `MODULES_SOCLE` depuis la vue dans le sélecteur** (un sélecteur
  n'importe pas une vue). Déplacer la constante dans
  `apps/platform_admin/selectors/clients.py` et l'importer **depuis là** dans la vue.
- `apps/platform_admin/serializers/clients.py` : `ModuleClientSerializer` (cherché par
  `grep -n "class ModuleClientSerializer"`) reçoit
  `desactivable = serializers.BooleanField(help_text="Faux pour un module socle, qui ne se désactive jamais.")`.

### 2.3 Rendre les réponses des deux actions utiles

Aujourd'hui elles renvoient `{"detail": "Module X activé avec succès..."}`. Le frontend doit
pouvoir rafraîchir la fiche sans deuxième requête. **Remplacer** la réponse 200 des deux vues
par la fiche complète :

```python
        from apps.platform_admin.selectors.clients import obtenir_fiche_client  # déjà importé en tête
        return Response(
            ClientPlateformeSerializer(obtenir_fiche_client(client_id)).data,
            status=status.HTTP_200_OK,
        )
```

Mettre à jour les `@extend_schema` : `responses={200: ClientPlateformeSerializer, 404: ..., 409: ...}`.

**Avant de changer le corps de réponse**, chercher qui lit `"detail"` dans ces réponses :

```bash
grep -rn "modules/.*activer\|desactiver/" apps tests --include=*.py
```

Adapter les assertions des tests existants qui lisaient `["detail"]` (ce sont des tests
unitaires du dépôt, pas des tests d'acceptation ; si un test d'**acceptation** lit `detail`,
**s'arrêter et le signaler**).

## 3. Tests

Ajouter à `apps/platform_admin/tests/test_clients_admin.py` (mêmes fixtures) :

| Test | Vérifie |
|---|---|
| `test_module_projets_ne_se_desactive_pas` | `POST .../modules/{id_projets}/desactiver/` → 409 ; `EntrepriseModule` de `projets` inchangé (ou toujours absent) ; aucune ligne `JournalPlateforme` `DESACTIVATION_MODULE` créée |
| `test_fiche_dit_quels_modules_sont_desactivables` | dans `GET` fiche, le module `projets` a `desactivable is False`, les autres `True` |
| `test_desactiver_puis_activer_renvoie_la_fiche` | sur un module non socle : la réponse 200 contient `id`, `modules`, et le module visé a `actif` à `False` puis `True` |
| `test_desactivation_conserve_les_donnees` | créer un projet dans `demo` (ou compter les projets existants), désactiver un module non socle, le réactiver : le nombre de projets est identique |

Le module `projets` du catalogue : `CatalogueModule.objects.filter(code__iexact="projets").first()`
dans le schéma public ; `pytest.skip("catalogue non peuplé")` s'il est absent.

## 4. Pièges

- **Comparer en minuscules** : les codes du catalogue sont comparés avec `__iexact` partout
  dans ce fichier ; `module.code` peut être `PROJETS` sur une base ancienne.
- **Le 409 doit partir avant `em.save`** : sinon le module est coupé et l'erreur arrive
  quand même.
- L'activation crée des lignes `RoleModulePermission` vides pour les rôles personnalisés
  (l. 497) : c'est **voulu** (décision 2.3 b), ne pas y toucher.

## 5. Définition de terminé

- [ ] 409 sur `projets` ; champ `desactivable` dans la fiche ; réponses = fiche complète.
- [ ] 4 tests verts ; tests existants adaptés ; `ruff` propre ; aucun échec nouveau.
- [ ] Commit : `feat(platform_admin): le module Projets ne se desactive pas, la fiche dit pourquoi`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
