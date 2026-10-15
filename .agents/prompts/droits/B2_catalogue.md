# B2 — Le service du back-office travaille sur le catalogue

Branche : `feature/droits-b2`
Prérequis : `README.md` §3 lu ; relevé des tests d'acceptation lot1 à lot4 fait (177 passent).

## 1. Le constat (vérifié le 16/10/2026, sondes en base de test)

Deux modèles de permissions coexistent :

| Modèle | Schéma | Codes | Rôle |
|---|---|---|---|
| `apps.catalogue.CatalogueModule` / `CataloguePermission` | `public` seul | `projets.lire`, `projets.creer`… (minuscules, préfixés par le module) | **la source** : ce que `permissions_effectives` (`apps/core/droits.py`), `GET /modules/` et la matrice des rôles (`RoleModulePermission.permissions_catalogue`) lisent |
| `apps.accounts.Module` / `Permission` | `public` et chaque tenant | `LECTURE`, `ECRITURE`, `VALIDATION`, `SUPPRESSION` | **l'ancien référentiel**. Ses quatre codes sont supprimés logiquement du catalogue |

Les vues du back-office (`apps/platform_admin/views/modules.py`, `views/permissions.py`) lisent et
renvoient le **catalogue** (identifiants de `CataloguePermission`). Mais le service
`apps/platform_admin/services/catalogue.py` résout encore les codes et les identifiants dans
**l'ancien** référentiel. Résultat, mesuré :

| Appel | Attendu | Obtenu |
|---|---|---|
| `POST /admins/permissions/{id de projets.voir_montants}/modules/ {"modules": ["projets"]}` | 200 | **400 « Permission introuvable. »** — l'identifiant est cherché dans `accounts.Permission` |
| `PATCH /admins/modules/{id de projets}/permissions/ {"permissions": [les 8 codes réels du module]}` | 200, les 8 codes | **200, `permissions_codes: []`** — le module perd toutes ses permissions : `_resoudre_permissions_codes` met les codes en **majuscules** (`PROJETS.LIRE`), introuvables |
| `DELETE /admins/permissions/{id d'une permission du catalogue}/` | 200 | **400** — même cause que la première ligne |
| `POST /admins/permissions/ {"code": "projets.lire", …}` (rétablir une permission du REGISTRE) | code `projets.lire` | code enregistré **`PROJETS.LIRE`** (`propager_creation_permission`, `code.strip().upper()`) |

La garde `bf3ae8d` a déjà retiré l'effet de `acces_par_defaut` (il traduisait l'accès en
`LECTURE`… et remplaçait les permissions fines du module). Ne pas y revenir.

## 2. Les règles à faire tenir

1. **Le catalogue est la source.** Toute résolution de permission (code ou identifiant) se fait dans
   `CataloguePermission` (`supprime_le__isnull=True`), toute résolution de module dans
   `CatalogueModule`. L'ancien référentiel n'est plus mis à jour que « au mieux » (voir §3.6).
2. **Un code se compare sans tenir compte de la casse, et s'enregistre tel que le catalogue (ou le
   REGISTRE) l'écrit**, en minuscules. Jamais de `.upper()` sur un code de permission.
3. **D2 — une permission `x.action` ne se rattache qu'au module `x`.** Rattacher `chantier.lire` au
   module `projets` est refusé, en 400 :
   `« La permission « chantier.lire » appartient au module « chantier » : elle ne peut pas être rattachée au module « projets ». »`
4. **Un code inconnu du catalogue est refusé**, en 400 (et rien n'est modifié) :
   `« Permission inconnue : « projets.inexistante ». »` (plusieurs codes : les citer tous, séparés par
   des virgules, dans le même message).
5. **Retirer une permission d'un module la retire de tous les rôles, dans toutes les entreprises,
   sur ce module** (comportement déjà voulu par le code, qui plantait ou ne trouvait rien) :
   `RoleModulePermission.permissions_catalogue.remove(...)` pour les lignes du module.
6. **Ajouter une permission à un module ne l'accorde à personne** (règle A-05, déjà écrite :
   « aucune attribution automatique aux rôles stockés »). Le DG l'a d'office
   (`permissions_effectives`), les autres rôles la reçoivent par l'écran des rôles.
7. **Tout passe ou rien ne passe** côté `public` : envelopper la partie `public` de chaque
   fonction dans `transaction.atomic()` (aujourd'hui, un échec dans la boucle des tenants laissait
   `public` déjà modifié).

## 3. Couche par couche — `apps/platform_admin/services/catalogue.py`

### 3.1 Deux fonctions privées, en tête du fichier (remplacent `_resoudre_permissions_codes`)

```python
def _permissions_du_catalogue(permissions_input) -> list[CataloguePermission]:
    """Les permissions du catalogue désignées par une liste de codes ou d'identifiants.

    Un identifiant (UUID) se cherche par `id`, un code par `code__iexact`, toujours parmi les
    permissions non supprimées. Lève `ValidationError` (« Permission inconnue : … ») si un élément
    ne correspond à rien. Accepte aussi des dictionnaires `{"code": …}` ou `{"id": …}`.
    Renvoie une liste sans doublon, triée par (ordre, code).
    """

def _verifier_prefixes(module_code: str, permissions: list[CataloguePermission]) -> None:
    """D2 : chaque permission `x.action` appartient au module `x`. Lève `ValidationError`."""
```

`_resoudre_permissions_codes` disparaît (`grep -n "_resoudre_permissions_codes" -r apps` : plus aucun
appel). `_resoudre_modules_codes` reste, mais résout les UUID dans `CatalogueModule` et non dans
`accounts.Module`.

### 3.2 `propager_creation_module`

- Les permissions passées (`permissions`) sont résolues par `_permissions_du_catalogue`, puis
  `_verifier_prefixes(code, …)` : un module **nouveau** n'a en pratique aucune permission (son préfixe
  n'existe pas encore au REGISTRE) — la liste vide est le cas normal, et elle est acceptée.
- `cat_mod.permissions.set(perms_catalogue)`.
- Dans chaque tenant : `RoleModulePermission` créé pour chaque rôle, **vide** pour tous sauf le DG ;
  pour le DG, `permissions_catalogue.set(perms_catalogue)` (et non plus « toutes les permissions
  actives de la plateforme » quand la liste est vide : un module vide ne donne rien, même au DG —
  le DG reçoit de toute façon tout par `permissions_effectives`).
- Ne plus appeler `Permission.objects.filter(code__in=…)` (ancien référentiel) pour décider de quoi
  que ce soit.

### 3.3 `propager_modification_module` (et donc `propager_affectation_permissions_module`)

Quand `permissions is not None` :

1. Dans `public`, sous `transaction.atomic()` :
   - `nouvelles = _permissions_du_catalogue(permissions)` ; `_verifier_prefixes(cat_mod.code, nouvelles)` ;
   - `anciennes_codes = set(cat_mod.permissions.filter(supprime_le__isnull=True).values_list("code", flat=True))` ;
   - `cat_mod.permissions.set(nouvelles)` ;
   - `retirees = anciennes_codes - {p.code for p in nouvelles}`.
2. Dans chaque tenant, sous `transaction.atomic()` : si `retirees`, pour chaque
   `RoleModulePermission` du module (`module__code=cat_mod.code` **ou** `module_catalogue=cat_mod`,
   `supprime_le__isnull=True`) : `rmp.permissions_catalogue.remove(*CataloguePermission.objects.filter(code__in=retirees))`.
3. L'identifiant reçu par la vue est celui du **`CatalogueModule`** (la vue lit le catalogue). Le
   module de l'ancien référentiel se retrouve par **code**, s'il existe (il porte en général le même
   identifiant, mais ne pas en dépendre).

Les métadonnées (`libelle`, `description`, `ordre`, `icone`, `est_actif`) continuent de se recopier
dans `CatalogueModule`, dans `accounts.Module` de `public` et dans chaque tenant, comme aujourd'hui.

### 3.4 `propager_creation_permission`

- **Ne plus mettre le code en majuscules** : `code = code.strip()` ; le serializer garantit déjà que
  le code est au REGISTRE (`AdminPermissionCreateSerializer.validate_code`), en minuscules.
- Le module se déduit du préfixe : `module_code = code.split(".")[0]`. Si `modules` est fourni et
  contient autre chose que ce module → 400 (règle D2, même message qu'au §2.3). Si `modules` est vide,
  la permission est rattachée **à son module** (`module_code`), s'il existe au catalogue ; sinon 400 :
  `« Le module « {module_code} » n'existe pas au catalogue : créez-le d'abord. »`
- `CataloguePermission` : si une permission **supprimée** porte déjà ce code, la **rétablir**
  (`supprime_le=None`, `supprime_par=None`, `est_actif=True`, libellé et description mis à jour) au
  lieu d'en créer une seconde ; sinon la créer. Son identifiant reste celui qu'elle avait : des
  rôles le référencent peut-être encore.
- Aucune attribution aux rôles (A-05).

### 3.5 `propager_affectation_modules_permission`, `propager_modification_permission`, `propager_suppression_permission`

- La permission se cherche par `CataloguePermission.objects.filter(id=permission_id, supprime_le__isnull=True)`.
  Introuvable → `ValidationError(_("Permission introuvable."))` (message inchangé).
- **Affectation de modules** : `modules` résolus dans `CatalogueModule` ; D2 s'applique (seul le module
  du préfixe est admis) ; donc la liste valide est `[]` ou `[module_du_prefixe]`. Retirer le module
  (`[]`) retire la permission de tous les rôles de toutes les entreprises sur ce module (§2.5).
- **Modification** : la recherche dans l'ancien référentiel et la création d'un `Permission` « miroir »
  (lignes 553-563 aujourd'hui) disparaissent ; seuls `CataloguePermission` et, au mieux, le
  `Permission` de même code dans chaque tenant sont mis à jour. La journalisation et la notification
  au DG quand `est_actif` passe à `False` restent telles quelles.
- **Suppression** : `CataloguePermission` supprimée logiquement (`supprime_le`, `supprime_par`,
  `est_actif=False`) ; dans chaque tenant, la retirer de **tous** les `permissions_catalogue` des
  rôles (une permission supprimée ne doit plus apparaître dans aucune matrice). L'ancien référentiel
  de même code est supprimé logiquement au mieux.

### 3.6 L'ancien référentiel, « au mieux »

Partout où le service écrit encore dans `accounts.Module` / `accounts.Permission` (public ou tenant),
le faire **par code, sans `.upper()`**, et ne jamais lever d'erreur parce qu'une ligne de l'ancien
référentiel manque : `filter(...).first()`, et si `None`, passer. Ces tables ne décident plus d'aucun
droit ; elles ne sont gardées que pour les écrans et commandes qui les lisent encore.

### 3.7 Les vues

- `apps/platform_admin/views/modules.py` : rien à changer, sauf si un `prefetch_related("permissions")`
  doit filtrer les permissions supprimées. **Le faire** : `Prefetch("permissions",
  queryset=CataloguePermission.objects.filter(supprime_le__isnull=True).order_by("ordre", "code"))`
  dans les quatre lectures (`get` de la liste, `post`, `get`/`patch` du détail, `put` des permissions),
  pour que `permissions` et `permissions_codes` ne montrent jamais une permission supprimée.
- `apps/platform_admin/views/permissions.py` : rien à changer (elle lit déjà le catalogue).

## 4. Tests

Nouveau fichier `apps/platform_admin/tests/test_catalogue_b2.py`. Modèle de fixtures :
`apps/accounts/tests/test_droits_b1.py`, test `test_rattachement_des_permissions_d_un_module_en_patch`
(superviseur créé par `create_superuser` dans `public`, `settings.SUPER_ADMIN_IPS = ["127.0.0.1"]`,
`APIClient(HTTP_HOST="localhost")`). Ajouter la fixture `schema_demo` (et
`initialiser_roles_par_defaut()` dans `demo`) aux tests qui regardent un rôle.

Les permissions et modules réels du catalogue existent dans la base de test (graines des
migrations) : `projets`, `chantier`, `projets.voir_montants`… Les y chercher, ne pas les recréer.

| Test | Vérifie |
|---|---|
| `test_patch_permissions_module_avec_ses_codes_reels` | `PATCH /admins/modules/{projets}/permissions/` avec les codes actuels du module → 200, `permissions_codes` = ces codes (**c'était `[]`**) |
| `test_codes_compares_sans_casse` | `["PROJETS.LIRE", "projets.ecrire"]` → 200, codes renvoyés en minuscules |
| `test_code_inconnu_refuse` | `["projets.inexistante"]` → 400, message §2.4 mot pour mot, module inchangé |
| `test_prefixe_d_un_autre_module_refuse` | `projets` + `["chantier.lire"]` → 400, message §2.3, module inchangé |
| `test_retrait_revoque_les_roles` | le rôle CP de `demo` a `projets.voir_montants` ; on le retire du module → 200 ; le CP ne l'a plus (`RoleModulePermission.permissions_catalogue`) ; on le remet au module → le CP **ne le récupère pas** (A-05) |
| `test_affecter_modules_a_une_permission_du_catalogue` | `POST /admins/permissions/{projets.voir_montants}/modules/ {"modules": ["projets"]}` → 200 (**c'était 400**) ; `{"modules": ["chantier"]}` → 400 (D2) |
| `test_supprimer_une_permission_du_catalogue` | `DELETE /admins/permissions/{id}/` → 200 ; la permission n'apparaît plus dans `GET /admins/modules/` ni dans la matrice d'aucun rôle de `demo` |
| `test_retablir_une_permission_du_registre` | supprimer `projets.voir_montants`, puis `POST /admins/permissions/ {"code": "projets.voir_montants", "libelle": "…"}` → 201, code **en minuscules**, **même identifiant** qu'avant, rattachée à `projets` |
| `test_acces_par_defaut_sans_effet` | `PATCH /admins/modules/{projets}/ {"acces_par_defaut": ["lecture"]}` → permissions du module inchangées (garde `bf3ae8d`) |

### Les tests unitaires existants du back-office

`apps/platform_admin/tests/test_admin_modules.py` et `test_admin_permissions.py` échouent **déjà**
sur `develop` (11 échecs : ils lisent `rmp.permissions`, relation supprimée, et attendent les codes
`LECTURE`…). Ce ne sont pas des tests d'acceptation : **les réécrire** sur le catalogue (mêmes noms
de tests, mêmes intentions, assertions sur `permissions_catalogue` et sur des codes réels). Ne pas
les supprimer. Ne toucher à **aucun** fichier de `tests/acceptation/`.

## 5. Vérification

1. `pytest apps/platform_admin/tests apps/accounts/tests/test_droits_b1.py -q` : tout passe.
2. Garde-fou du README §3 : les 177 tests d'acceptation lot1 à lot4 passent.
3. `ruff check` sur les fichiers touchés : **aucune erreur nouvelle** (comparer à `git show develop:<fichier> | ruff check --stdin-filename <fichier> -`).

## 6. Définition de terminé

- [ ] Plus aucun `.upper()` sur un code de permission dans `services/catalogue.py`.
- [ ] Plus aucune résolution de permission ou de module dans l'ancien référentiel pour décider d'un rattachement.
- [ ] D2 appliquée ; codes inconnus refusés ; retrait = révocation ; ajout = aucune attribution.
- [ ] Les 9 tests du §4 et les deux fichiers réécrits passent ; 177 tests d'acceptation passent.
- [ ] Commit : `fix(back-office): le service de catalogue travaille sur le catalogue des permissions`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
