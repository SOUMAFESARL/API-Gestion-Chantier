# Listes de valeurs et modèles de découpage — contrat d'API

| | |
|---|---|
| Décisions | `docs/decoupage/decisions-v1.2.md`, §3 (modèles) et §4 (listes) |
| Lot | 1 du plan de découpage en arbre (référentiel et back-office des listes et modèles) |
| Entreprise | `apps/projets/views/decoupage.py`, services `apps/projets/services/listes_modeles.py` |
| Back-office | `apps/platform_admin/views/decoupage.py`, service `apps/platform_admin/services/decoupage.py` |

Toutes les routes sont sous `/api/v1/`. Les erreurs suivent le format unique de l'API :

```json
{"erreur": {"code": "regle_metier", "message": "…", "details": {}, "trace_id": "…"}}
```

| HTTP | `code` | Quand |
|---|---|---|
| 400 | `validation` | Corps invalide ; `details` porte les champs en faute |
| 403 | `acces_refuse` | Permission manquante (entreprise) ; écriture par un agent SUPPORT (back-office) |
| 404 | `introuvable` | Liste, valeur ou modèle inconnu ou retiré |
| 409 | `libelle_en_double` | Libellé déjà présent (comparaison sans accents, casse ni espaces superflus) |
| 422 | `regle_metier` | Règle de gestion : modèle plateforme non modifiable par l'entreprise, C-1 à C-4, liste encore utilisée… |

---

## 1. Ce qui change dans l'ancien référentiel

La catégorie **`lots`** de l'ancien référentiel est retirée (décisions v1.2, §4.2) : les noms de
lot sont les valeurs de la liste **« Lots »** du découpage, seule source désormais (semée par
`catalogue/migrations/0014_peupler_decoupage.py` à partir de l'ancienne catégorie).

| Route retirée | Remplacée par |
|---|---|
| `GET`/`POST /referentiels/lots/` | `GET /decoupage/listes/` (liste « Lots »), `POST /decoupage/listes/PLATEFORME/{id}/valeurs/` |
| `DELETE /referentiels/lots/{code}/` | `DELETE /decoupage/valeurs/{id}/` (valeurs ajoutées par l'entreprise) |
| `GET`/`POST /admins/referentiels/lots/` | `GET /admins/decoupage/listes/{id}/`, `POST /admins/decoupage/listes/{id}/valeurs/` |
| `PATCH`/`DELETE /admins/referentiels/lots/{id}/` | `PATCH`/`DELETE /admins/decoupage/valeurs/{id}/` |

Une de ces anciennes URL répond désormais **404**. Les catégories `types-projet` et
`modes-execution` restent, aux mêmes routes et avec les mêmes réponses.

Les entrées `LOT` déjà en base (`catalogue_referentiel`, `referentiel_entreprise`) ne sont pas
supprimées : plus aucune route ne les expose.

---

## 2. Routes de l'entreprise

Une entreprise voit **deux sources fusionnées** : les listes et modèles de la plateforme (lus
sans copie dans le schéma public) et les siens. Une liste ou un modèle se désigne donc par
`{origine, id}` — `origine` vaut `PLATEFORME` ou `ENTREPRISE` —, jamais par son nom.

| Méthode et route | Permission | Effet |
|---|---|---|
| `GET decoupage/listes/` | `projets.lire` | Toutes les listes, plateforme d'abord |
| `POST decoupage/listes/` | `projets.modeles_gerer` | Créer une liste de l'entreprise |
| `GET decoupage/listes/{origine}/{id}/` | `projets.lire` | Une liste et ses valeurs |
| `POST decoupage/listes/{origine}/{id}/valeurs/` | `projets.modeles_gerer` | Ajouter des valeurs (en masse) |
| `DELETE decoupage/valeurs/{id}/` | `projets.modeles_gerer` | Retirer une valeur ajoutée par l'entreprise |
| `GET decoupage/modeles/` | `projets.lire` | Tous les modèles, ceux du type demandé en tête |
| `POST decoupage/modeles/` | `projets.modeles_gerer` | Enregistrer comme nouveau modèle |
| `GET decoupage/modeles/{origine}/{id}/` | `projets.lire` | Un modèle, avec son gabarit et ses lignes types |
| `PUT decoupage/modeles/ENTREPRISE/{id}/` | `projets.modeles_gerer` | Mettre à jour ce modèle |
| `DELETE decoupage/modeles/ENTREPRISE/{id}/` | `projets.modeles_gerer` | Supprimer ce modèle (suppression logique) |
| `POST decoupage/modeles/PLATEFORME/{id}/personnaliser/` | `projets.modeles_gerer` | Personnaliser un modèle de la plateforme |

`{origine}` s'écrit en majuscules ou en minuscules. Une liste inconnue ou retirée, désignée dans
l'URL, répond **400** `validation` avec `details.liste` (« Cette liste est introuvable. ») ; un
modèle inconnu répond **404**.

### 2.1 Une liste

`GET decoupage/listes/` (paramètre `?valeurs=false` pour ne pas rendre les valeurs) rend un
tableau de listes ; `GET decoupage/listes/{origine}/{id}/` en rend une.

```json
{
  "origine": "PLATEFORME",
  "id": "5d1c…",
  "libelle": "Lots",
  "description": "",
  "modifiable": false,
  "valeurs": [
    {"id": "…", "libelle": "Gros œuvre", "groupe": "Bâtiment", "ordre": 1, "origine": "PLATEFORME"},
    {"id": "…", "libelle": "Étanchéité spéciale", "groupe": "", "ordre": 59, "origine": "ENTREPRISE"}
  ]
}
```

| Champ | Type | Sens |
|---|---|---|
| `origine` | `PLATEFORME` \| `ENTREPRISE` | Qui a créé la liste |
| `id` | UUID | Identifiant de la liste dans sa source |
| `libelle` | texte | Nom de la liste |
| `description` | texte | Peut être vide |
| `modifiable` | booléen | Vrai pour une liste de l'entreprise |
| `valeurs[]` | tableau | Valeurs de la plateforme puis celles ajoutées par l'entreprise, chacune triée par `ordre` puis `libelle` |
| `valeurs[].id` | UUID | À passer à `DELETE decoupage/valeurs/{id}/` |
| `valeurs[].groupe` | texte | Titre de groupe dans la liste déroulante (le corps d'état d'un lot) ; peut être vide |
| `valeurs[].ordre` | entier | Rang d'affichage (nouveau champ, ajouté au lot 1) |
| `valeurs[].origine` | `PLATEFORME` \| `ENTREPRISE` | Une valeur `PLATEFORME` ne se retire pas ici |

### 2.2 Créer une liste — `POST decoupage/listes/`

```json
{"libelle": "Zones du site", "description": "", "valeurs": ["Zone A", "Zone B"]}
```

| Champ | Requis | Règle |
|---|---|---|
| `libelle` | oui | 100 caractères au plus ; deux listes (plateforme ou entreprise) ne portent pas le même nom |
| `description` | non | Texte libre |
| `valeurs` | non | Libellés de 200 caractères au plus ; les doublons sont ignorés |

**201** : la liste (§2.1). **422** `regle_metier` si une liste porte déjà ce nom
(« Une liste porte déjà ce nom : « Lots ». »).

### 2.3 Ajouter des valeurs — `POST decoupage/listes/{origine}/{id}/valeurs/`

L'entreprise ajoute ses valeurs à ses listes **et aux listes de la plateforme** (§4.1).

```json
{"valeurs": ["Étanchéité spéciale", "gros oeuvre"], "groupe": ""}
```

| Champ | Requis | Règle |
|---|---|---|
| `valeurs` | oui, au moins une | 200 caractères au plus chacune |
| `groupe` | non | 100 caractères au plus, appliqué à toutes les valeurs ajoutées |

**201** :

```json
{
  "ajoutees": [{"id": "…", "libelle": "Étanchéité spéciale", "groupe": "", "ordre": 59}],
  "ignorees": ["gros oeuvre"]
}
```

`ignorees` : les valeurs déjà présentes dans la liste (plateforme ou entreprise), comparées sans
accents, casse ni espaces superflus. Une valeur vide est ignorée sans être citée.

### 2.4 Retirer une valeur — `DELETE decoupage/valeurs/{id}/`

**204**. Suppression logique : la valeur n'est plus proposée ; aucune case déjà saisie ne
change (§4.8). **422** si la valeur est celle de la plateforme ; **404** si elle est inconnue.

### 2.5 Un modèle

`GET decoupage/modeles/?type_projet=BATIMENT_RESIDENTIEL` rend tous les modèles actifs (§3.9),
**le modèle par défaut du type d'abord, puis ceux conçus pour ce type**, puis les autres par nom
affiché.

```json
{
  "origine": "ENTREPRISE",
  "id": "…",
  "nom": "Bâtiment — Phase, ouvrage, lot, activité",
  "nom_affiche": "Bâtiment — Phase, ouvrage, lot, activité (personnalisé)",
  "description": "…",
  "types_projet": ["BATIMENT_RESIDENTIEL"],
  "par_defaut_pour": [],
  "niveaux": ["Phase", "Ouvrage", "Lot", "Activité"],
  "nombre_lignes": 12,
  "modifiable": true,
  "pour_ce_type": true,
  "par_defaut": false,
  "origine_plateforme_id": "…",
  "original_modifie": false
}
```

| Champ | Sens |
|---|---|
| `nom_affiche` | « Nom (personnalisé) » pour une copie d'un modèle plateforme ; « Nom (entreprise) » pour un modèle de l'entreprise qui porte le nom d'un modèle plateforme (§3.7) |
| `types_projet` | Codes du référentiel `TYPE_PROJET` pour lesquels le modèle est conçu |
| `par_defaut_pour` | Types de projet dont ce modèle pré-remplit le tableau de démarrage |
| `niveaux` | **En liste** : les libellés des niveaux. **En détail** : voir ci-dessous |
| `modifiable` | Vrai pour un modèle de l'entreprise |
| `pour_ce_type` / `par_defaut` | Selon `?type_projet` |
| `origine_plateforme_id` | (entreprise) Le modèle plateforme dont il est la copie, ou `null` |
| `original_modifie` | (entreprise) Vrai si la plateforme a changé l'original depuis la copie : signalé, jamais appliqué (§3.6) |

`GET decoupage/modeles/{origine}/{id}/` ajoute le **gabarit** ; `niveaux` y devient un tableau
d'objets et `lignes` apparaît :

```json
{
  "niveaux": [
    {"libelle": "Phase", "liste": {"origine": "PLATEFORME", "id": "…", "libelle": "Phases"}, "alerter": false},
    {"libelle": "Lot", "liste": {"origine": "PLATEFORME", "id": "…", "libelle": "Lots"}, "alerter": true},
    {"libelle": "Activité", "liste": null, "alerter": false}
  ],
  "lignes": [["Infrastructure", "Gros œuvre", "Fouilles en rigoles"]]
}
```

Chaque ligne a autant de cellules que de niveaux ; les dernières peuvent être vides.

### 2.6 Enregistrer un modèle — `POST decoupage/modeles/`, `PUT decoupage/modeles/ENTREPRISE/{id}/`

```json
{
  "nom": "Mon modèle",
  "description": "",
  "types_projet": ["BATIMENT_RESIDENTIEL"],
  "par_defaut_pour": [],
  "niveaux": [
    {"libelle": "Zone", "liste": {"origine": "ENTREPRISE", "id": "…"}, "alerter": false},
    {"libelle": "Lot", "liste": {"origine": "PLATEFORME", "id": "…"}, "alerter": true}
  ],
  "lignes": [["Zone A", "Gros œuvre"], {"cellules": ["Zone B", "Peinture"]}]
}
```

| Champ | Requis | Règle |
|---|---|---|
| `nom` | oui | 150 caractères au plus ; unique parmi les modèles de l'entreprise |
| `types_projet`, `par_defaut_pour` | non | Codes de types de projet. Un type n'a qu'un modèle d'entreprise par défaut : le donner à celui-ci le retire aux autres |
| `niveaux[]` | oui | `libelle` (60 caractères), `liste` (`{origine, id}` ou `null`), `alerter` |
| `lignes[]` | oui (peut être vide) | Une ligne = une liste de cellules, ou un objet `{"cellules": [...]}` |

Vérification **C-1 à C-4** (§6) : cellule vide au milieu, ligne en double, niveau sans libellé,
deux niveaux au même libellé. **422** `regle_metier` avec `details.bloquants`
(`[{regle, ligne?, niveau?, message}]`). Les lignes vides et les lignes « sans effet » sont
écartées sans erreur. **201** (`POST`) ou **200** (`PUT`) : le modèle en détail (§2.5).

`PUT` ou `DELETE` sur un modèle `PLATEFORME` : **422** (« Un modèle de la plateforme ne se modifie
pas : personnalisez-le… »). Supprimer ou modifier un modèle ne change aucun projet déjà créé
(§3.11).

### 2.7 Personnaliser — `POST decoupage/modeles/PLATEFORME/{id}/personnaliser/`

Sans corps. Crée une copie de l'entreprise, liée à l'original par identifiant (§3.5).
**201** : la copie (§2.5). **422** si une copie existe déjà, avec
`details.modele = {"origine": "ENTREPRISE", "id": "…"}` ; **404** si le modèle est inconnu,
retiré ou inactif.

---

## 3. Routes du back-office

Ce qui s'écrit ici est lu **aussitôt par toutes les entreprises, sans copie** (§3.3, §4.1). Tout
se passe dans le schéma `public`.

**Droits.** Compte du back-office (`EstSuperAdminPlateforme`) : la **lecture** est ouverte aux
rôles `SUPERVISEUR` et `SUPPORT` ; **l'écriture** (`POST`, `PATCH`, `PUT`, `DELETE`) est réservée
au `SUPERVISEUR` — un agent SUPPORT reçoit **403** (« Seul un superviseur de la plateforme peut
effectuer cette action. »).

**Trace.** Chaque écriture entre au journal de la plateforme (`GET admins/journal-plateforme/`),
avec l'auteur et le détail : `DECOUPAGE_LISTE_CREATION`, `DECOUPAGE_LISTE_MODIFICATION`,
`DECOUPAGE_LISTE_RETRAIT`, `DECOUPAGE_VALEURS_AJOUT`, `DECOUPAGE_VALEUR_MODIFICATION`,
`DECOUPAGE_VALEUR_RETRAIT`, `DECOUPAGE_MODELE_CREATION`, `DECOUPAGE_MODELE_MODIFICATION`,
`DECOUPAGE_MODELE_RETRAIT`.

| Méthode et route | Effet |
|---|---|
| `GET admins/decoupage/listes/` | Les listes de la plateforme (`?valeurs=false` pour les alléger) |
| `POST admins/decoupage/listes/` | Créer une liste |
| `GET admins/decoupage/listes/{id}/` | Une liste et ses valeurs |
| `PATCH admins/decoupage/listes/{id}/` | Renommer, décrire, réordonner |
| `DELETE admins/decoupage/listes/{id}/` | Retirer (suppression logique) |
| `POST admins/decoupage/listes/{id}/valeurs/` | Ajouter des valeurs en masse |
| `PATCH admins/decoupage/valeurs/{id}/` | Corriger une valeur |
| `DELETE admins/decoupage/valeurs/{id}/` | Retirer une valeur (suppression logique) |
| `GET admins/decoupage/modeles/` | Les modèles de la plateforme, actifs ou non |
| `POST admins/decoupage/modeles/` | Créer un modèle |
| `GET admins/decoupage/modeles/{id}/` | Un modèle, avec son gabarit et ses lignes types |
| `PUT admins/decoupage/modeles/{id}/` | Mettre à jour un modèle (sa version augmente) |
| `DELETE admins/decoupage/modeles/{id}/` | Retirer un modèle (suppression logique) |

### 3.1 Une liste de la plateforme

```json
{
  "id": "…",
  "libelle": "Lots",
  "description": "",
  "ordre": 1,
  "nombre_valeurs": 58,
  "modeles": [{"id": "…", "nom": "Bâtiment — Phase, ouvrage, lot, activité"}],
  "modifie_le": "2026-10-30T21:04:11.512Z",
  "valeurs": [
    {"id": "…", "libelle": "Gros œuvre", "groupe": "Bâtiment", "ordre": 1, "origine": "PLATEFORME"}
  ]
}
```

| Champ | Sens |
|---|---|
| `ordre` | Rang de la liste dans les menus |
| `nombre_valeurs` | Valeurs de la plateforme (les ajouts des entreprises ne sont pas visibles ici) |
| `modeles[]` | Modèles de la plateforme (non retirés) dont un niveau puise dans cette liste |
| `valeurs[]` | Comme côté entreprise (§2.1), toutes d'origine `PLATEFORME` ; absent avec `?valeurs=false` |

### 3.2 Créer une liste — `POST admins/decoupage/listes/`

Même corps que côté entreprise (§2.2) : `libelle` (requis, 100 caractères), `description`,
`valeurs`. **201** : la liste (§3.1). **409** `libelle_en_double` si une liste de la plateforme
porte déjà ce nom (`details: {libelle, existant}`).

### 3.3 Modifier une liste — `PATCH admins/decoupage/listes/{id}/`

```json
{"libelle": "Lots du bâtiment", "description": "…", "ordre": 2}
```

Tous les champs sont facultatifs. **200** : la liste. **409** `libelle_en_double`. Les niveaux qui
la citent la suivent : le lien passe par l'identifiant, jamais par le nom (§4.3).

### 3.4 Retirer une liste — `DELETE admins/decoupage/listes/{id}/`

**204**. **422** tant qu'un modèle de la plateforme y puise, avec
`details.modeles = [{id, nom}]` : changer d'abord la liste de ces niveaux, ou retirer ces
modèles. Les niveaux de projets et les modèles d'entreprise qui la citent la gardent ; elle
n'est plus proposée (§3.11, §4.8). Une liste retirée répond ensuite **404**.

### 3.5 Ajouter des valeurs — `POST admins/decoupage/listes/{id}/valeurs/`

Même corps et même réponse que côté entreprise (§2.3) ; les valeurs deviennent celles de la
plateforme, proposées à toutes les entreprises. Les doublons ne sont cherchés que parmi les
valeurs de la plateforme.

### 3.6 Corriger une valeur — `PATCH admins/decoupage/valeurs/{id}/`

```json
{"libelle": "Gros œuvre (structure)", "groupe": "Bâtiment", "ordre": 3}
```

Tous les champs sont facultatifs. **200** :

```json
{"id": "…", "liste_id": "…", "libelle": "Gros œuvre (structure)", "groupe": "Bâtiment", "ordre": 3, "origine": "PLATEFORME"}
```

**409** `libelle_en_double` si la liste a déjà ce libellé. Les cases déjà saisies ne changent
pas : une valeur choisie est recopiée dans l'intitulé de la case (§4.6).

### 3.7 Retirer une valeur — `DELETE admins/decoupage/valeurs/{id}/`

**204**. Suppression logique : la valeur n'est plus proposée. **404** si elle est inconnue.

### 3.8 Un modèle de la plateforme

`GET admins/decoupage/modeles/` rend les modèles sans leur gabarit ; `GET …/{id}/`, `POST` et
`PUT` l'ajoutent.

```json
{
  "id": "…",
  "nom": "Route — Section, lot",
  "description": "",
  "types_projet": ["TP_ROUTE"],
  "par_defaut_pour": [],
  "version": 2,
  "est_actif": true,
  "niveaux_libelles": ["Section", "Lot"],
  "nombre_lignes": 1,
  "modifie_le": "2026-10-30T21:06:42.010Z",
  "niveaux": [
    {"libelle": "Section", "liste": {"origine": "PLATEFORME", "id": "…", "libelle": "Zones"}, "alerter": false},
    {"libelle": "Lot", "liste": null, "alerter": true}
  ],
  "lignes": [["Nord", "Gros œuvre"]]
}
```

| Champ | Sens |
|---|---|
| `version` | Augmente à chaque `PUT` : les copies personnalisées signalent alors `original_modifie` (§3.6) |
| `est_actif` | Faux : le modèle n'est plus proposé aux entreprises, sans être retiré |
| `niveaux_libelles` | Les libellés des niveaux (présent en liste comme en détail) |
| `niveaux`, `lignes` | Le gabarit, comme côté entreprise (§2.5) ; absents de la liste |

### 3.9 Créer ou mettre à jour — `POST admins/decoupage/modeles/`, `PUT admins/decoupage/modeles/{id}/`

Même corps que côté entreprise (§2.6), plus `est_actif` (facultatif, vrai par défaut).

| Règle | Erreur |
|---|---|
| Nom unique parmi les modèles de la plateforme (sans accents, casse ni espaces) | 422 |
| Un modèle plateforme **ne puise que dans des listes plateforme** (§3.8) | 422, `details.niveau` |
| `types_projet` et `par_defaut_pour` : codes du référentiel `TYPE_PROJET` de la plateforme | 400, `details.types_projet` |
| C-1 à C-4 | 422, `details.bloquants` |

Un type n'a qu'un modèle plateforme par défaut : le donner à celui-ci le retire aux autres.
**201** (`POST`) ou **200** (`PUT`) : le modèle (§3.8). Aucun projet déjà créé n'est touché
(§3.11).

### 3.10 Retirer un modèle — `DELETE admins/decoupage/modeles/{id}/`

**204**. Suppression logique : il disparaît des modèles proposés aux entreprises. Les projets
qui en sont issus gardent leur gabarit ; les copies personnalisées restent celles des
entreprises.
