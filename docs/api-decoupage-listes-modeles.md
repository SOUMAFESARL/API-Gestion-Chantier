# Listes de valeurs et modèles de découpage — contrat d'API

| | |
|---|---|
| Décisions | `docs/decoupage/decisions-v1.2.md`, §3 (modèles) et §4 (listes), amendement du 23/11/2026 |
| Lot | 1 & 2 du plan de découpage en arbre (référentiel, consolidation plateforme → entreprises et back-office Super Admin) |
| Entreprise | `apps/projets/views/decoupage.py`, services `apps/projets/services/listes_modeles.py` |
| Back-office | `apps/platform_admin/views/decoupage.py`, service `apps/platform_admin/services/decoupage.py` |

Toutes les routes sont sous `/api/v1/`. Les erreurs suivent le format unique de l'API :

```json
{"erreur": {"code": "regle_metier", "message": "…", "details": {}, "trace_id": "…"}}
```

| HTTP | `code` | Quand |
|---|---|---|
| 400 | `validation` | Corps invalide (ex. `par_defaut_pour` hors `types_projet`, type inconnu) ; `details` porte les champs en faute |
| 403 | `acces_refuse` | Permission manquante (entreprise) ; écriture par un agent SUPPORT (back-office) |
| 404 | `introuvable` | Liste, valeur ou modèle inconnu ou retiré |
| 409 | `libelle_en_double` | Libellé déjà présent (comparaison sans accents, casse ni espaces superflus) |
| 422 | `regle_metier` | Règle de gestion : modèle plateforme non modifiable par l'entreprise, C-1 à C-4, liste encore utilisée (plateforme, modèles entreprise ou projets)… |

---

## 1. Ce qui change dans l'ancien référentiel

La catégorie **`lots`** de l'ancien référentiel est retirée (décisions v1.2, §4.2) : les noms de
lot sont les valeurs de la liste **« Lots »** du découpage, seule source désormais.

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

Une entreprise voit **deux sources fusionnées** : les listes et modèles actifs de la plateforme
(lus sans copie) et les siens. Une liste ou un modèle se désigne donc par
`{origine, id}` — `origine` vaut `PLATEFORME` ou `ENTREPRISE` —, jamais par son nom.

| Méthode et route | Permission | Effet |
|---|---|---|
| `GET decoupage/listes/` | `projets.lire` | Toutes les listes actives de la plateforme, puis celles de l'entreprise |
| `POST decoupage/listes/` | `projets.modeles_gerer` | Créer une liste de l'entreprise |
| `GET decoupage/listes/modele-excel/` | `projets.lire` | Télécharger le gabarit Excel d'import de valeurs |
| `GET decoupage/listes/{origine}/{id}/` | `projets.lire` | Une liste et ses valeurs |
| `PATCH decoupage/listes/ENTREPRISE/{id}/` | `projets.modeles_gerer` | Renommer ou décrire une liste créée par l'entreprise |
| `DELETE decoupage/listes/ENTREPRISE/{id}/` | `projets.modeles_gerer` | Retirer une liste créée par l'entreprise (suppression logique) |
| `POST decoupage/listes/{origine}/{id}/valeurs/` | `projets.modeles_gerer` | Ajouter des valeurs (en masse) |
| `POST decoupage/listes/{origine}/{id}/valeurs/importer/` | `projets.modeles_gerer` | Importer des valeurs depuis un fichier `.xlsx` ou `.csv` |
| `DELETE decoupage/valeurs/{id}/` | `projets.modeles_gerer` | Retirer une valeur ajoutée par l'entreprise |
| `GET decoupage/modeles/` | `projets.lire` | Tous les modèles actifs, ceux du type demandé en tête |
| `POST decoupage/modeles/` | `projets.modeles_gerer` | Enregistrer comme nouveau modèle |
| `GET decoupage/modeles/modele-excel/` | `projets.lire` | Télécharger le gabarit Excel d'un modèle de découpage |
| `POST decoupage/modeles/importer-fichier/` | `projets.modeles_gerer` | Extraire `{niveaux, lignes}` d'un fichier `.xlsx` ou `.csv` |
| `GET decoupage/modeles/{origine}/{id}/` | `projets.lire` | Un modèle, avec son gabarit et ses lignes types |
| `PUT decoupage/modeles/ENTREPRISE/{id}/` | `projets.modeles_gerer` | Mettre à jour ce modèle (remplacement complet) |
| `PATCH decoupage/modeles/ENTREPRISE/{id}/` | `projets.modeles_gerer` | Mettre à jour partiellement ce modèle |
| `DELETE decoupage/modeles/ENTREPRISE/{id}/` | `projets.modeles_gerer` | Supprimer ce modèle (suppression logique cascadée sur ses niveaux et lignes) |
| `POST decoupage/modeles/PLATEFORME/{id}/personnaliser/` | `projets.modeles_gerer` | Personnaliser un modèle de la plateforme (`PLATEFORME` insensible à la casse) |

`{origine}` s'écrit en majuscules ou en minuscules. Une liste ou un modèle inconnu ou retiré,
désigné dans l'URL, répond **404**. Chaque écriture côté entreprise est journalisée dans
`JournalAudit`.

### 2.1 Une liste

`GET decoupage/listes/` (paramètre `?valeurs=false` pour ne pas rendre les valeurs) rend un
tableau de listes (seules les listes plateforme avec `est_actif=true` y sont proposées, suivies
des listes de l'entreprise) ; `GET decoupage/listes/{origine}/{id}/` en rend une.
Une liste plateforme désactivée (`est_actif=false`) continue de se résoudre lorsqu'elle est déjà
référencée par un modèle d'entreprise ou un projet existant, afin de ne jamais casser l'existant.

```json
{
  "origine": "PLATEFORME",
  "id": "5d1c…",
  "libelle": "Lots",
  "description": "",
  "modifiable": false,
  "nombre_valeurs": 59,
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
| `nombre_valeurs` | entier | Nombre total de valeurs (plateforme + entreprise) |
| `valeurs[]` | tableau | Valeurs de la plateforme puis celles ajoutées par l'entreprise, chacune triée par `ordre` puis `libelle` |
| `valeurs[].id` | UUID | À passer à `DELETE decoupage/valeurs/{id}/` |
| `valeurs[].groupe` | texte | Titre de groupe dans la liste déroulante (le corps d'état d'un lot) ; peut être vide |
| `valeurs[].ordre` | entier | Rang d'affichage |
| `valeurs[].origine` | `PLATEFORME` \| `ENTREPRISE` | Une valeur `PLATEFORME` ne se retire pas ici |

### 2.2 Créer une liste — `POST decoupage/listes/`

```json
{"libelle": "Zones du site", "description": "", "valeurs": ["Zone A", "Zone B"]}
```

| Champ | Requis | Règle |
|---|---|---|
| `libelle` | oui | 100 caractères au plus ; deux listes (plateforme ou entreprise) ne portent pas le même nom (`cle_comparaison`) |
| `description` | non | Texte libre |
| `valeurs` | non | Libellés de 200 caractères au plus ; les doublons sont ignorés |

**201** : la liste (§2.1). **422** `regle_metier` si une liste porte déjà ce nom.

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

### 2.4 Retirer une valeur — `DELETE decoupage/valeurs/{id}/`

**204**. Suppression logique : la valeur n'est plus proposée ; aucune case déjà saisie ne
change (§4.8). **422** si la valeur est celle de la plateforme ; **404** si elle est inconnue.

### 2.5 Un modèle et la règle de priorité Plateforme vs Entreprise

`GET decoupage/modeles/?type_projet=BATIMENT_RESIDENTIEL` rend tous les modèles actifs (§3.9).

**Règle de priorité pour `modele_par_defaut(type_projet)` (amendement 23/11/2026) :**
Le modèle plateforme par défaut reste prioritaire tant que l'entreprise n'a pas explicitement
coché un de ses modèles dans `par_defaut_pour` :
1. Modèle `ENTREPRISE` contenant `type_projet` dans `par_defaut_pour` ;
2. Modèle `PLATEFORME` (`est_actif=True`) contenant `type_projet` dans `par_defaut_pour` ;
3. Modèle `PLATEFORME` (`est_actif=True`) contenant `type_projet` dans `types_projet` ;
4. Modèle `ENTREPRISE` contenant `type_projet` dans `types_projet` ;
5. Repli : premier modèle `PLATEFORME` (`est_actif=True`), sinon premier modèle `ENTREPRISE`.

**Tri de `GET decoupage/modeles/` :**
`(not par_defaut, not pour_ce_type, origine != "PLATEFORME", nom_affiche)` : le modèle par défaut
d'abord, puis ceux conçus pour ce type, puis les modèles de la plateforme avant ceux de
l'entreprise, puis par nom affiché.

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
  "est_personnalise": true,
  "origine_plateforme_id": "…",
  "original_supprime": false,
  "original_modifie": false
}
```

| Champ | Sens |
|---|---|
| `nom_affiche` | « Nom (personnalisé) » pour une copie d'un modèle plateforme ; « Nom (entreprise) » pour un modèle de l'entreprise qui porte le nom d'un modèle plateforme (§3.7) |
| `types_projet` | Codes du référentiel `TYPE_PROJET` pour lesquels le modèle est conçu |
| `par_defaut_pour` | Sous-ensemble de `types_projet` dont ce modèle pré-remplit le tableau de démarrage |
| `niveaux` | **En liste** : les libellés des niveaux. **En détail** : tableau d'objets `{libelle, liste, alerter}` |
| `modifiable` | Vrai pour un modèle de l'entreprise |
| `pour_ce_type` / `par_defaut` | Selon `?type_projet` |
| `est_personnalise` | Vrai si le modèle d'entreprise est issu de la personnalisation d'un modèle plateforme (`bool(origine_id)`) |
| `origine_plateforme_id` | UUID du modèle plateforme d'origine s'il est actif et non supprimé, sinon `null` (évite tout lien 404 cassé) |
| `original_supprime` | Vrai si le modèle est une copie personnalisée (`origine_id` non nul) mais que le modèle plateforme d'origine a été supprimé ou désactivé |
| `original_modifie` | Vrai si l'original plateforme est disponible et sa `version` dépasse `version_origine` (§3.6) |

`GET decoupage/modeles/{origine}/{id}/` ajoute le **gabarit** (`niveaux` détaillés et `lignes`).

### 2.6 Enregistrer ou modifier un modèle — `POST decoupage/modeles/`, `PUT`/`PATCH decoupage/modeles/ENTREPRISE/{id}/`

| Champ | Requis (`POST`/`PUT`) | Requis (`PATCH`) | Règle |
|---|---|---|---|
| `nom` | oui | non | 150 caractères au plus ; unique par `cle_comparaison` parmi les modèles de même nature |
| `description` | non | non | Texte libre |
| `types_projet` | non | non | Codes connus du référentiel `TYPE_PROJET` (plateforme + entreprise) |
| `par_defaut_pour` | non | non | **Doit être un sous-ensemble de `types_projet`** (sinon **400** `validation` sur `par_defaut_pour`). Un type n'a qu'un modèle d'entreprise par défaut : le donner à celui-ci le retire aux autres |
| `niveaux[]` | oui | non | `libelle` (60 caractères), `liste` (`{origine, id}` ou `null`), `alerter` |
| `lignes[]` | oui (peut être vide) | non | Une ligne = une liste de cellules, ou un objet `{"cellules": [...]}` |

Vérification **C-1 à C-4** (§6). **422** `regle_metier` avec `details.bloquants`.
**201** (`POST`) ou **200** (`PUT`/`PATCH`) : le modèle en détail (§2.5).

### 2.7 Personnaliser — `POST decoupage/modeles/PLATEFORME/{id}/personnaliser/`

Sans corps (`PLATEFORME` accepté quelle que soit la casse). Crée une copie de l'entreprise, liée à
l'original par identifiant (§3.5), avec `cree_par=request.user`.
**201** : la copie (§2.5). **422** si une copie existe déjà, avec
`details.modele = {"origine": "ENTREPRISE", "id": "…"}` ; **404** si le modèle est inconnu,
retiré ou inactif.

---

## 3. Routes du back-office (`/api/v1/admins/decoupage/*`)

Ce qui s'écrit ici est lu **aussitôt par toutes les entreprises, sans copie** (§3.3, §4.1).

**Droits.** Compte du back-office (`EstSuperAdminPlateforme`) : la **lecture** est ouverte aux
rôles `SUPERVISEUR` et `SUPPORT` ; **l'écriture** (`POST`, `PATCH`, `PUT`, `DELETE`) est réservée
au `SUPERVISEUR` — un agent SUPPORT reçoit **403**.

**Trace.** Chaque écriture entre au journal de la plateforme (`GET admins/journal-plateforme/`) :
- Listes : `DECOUPAGE_LISTE_CREATION`, `DECOUPAGE_LISTE_MODIFICATION`, `DECOUPAGE_LISTE_ACTIVATION`, `DECOUPAGE_LISTE_DESACTIVATION`, `DECOUPAGE_LISTE_RETRAIT` ;
- Valeurs : `DECOUPAGE_VALEURS_AJOUT`, `DECOUPAGE_VALEURS_IMPORT`, `DECOUPAGE_VALEUR_MODIFICATION`, `DECOUPAGE_VALEUR_RETRAIT` ;
- Modèles : `DECOUPAGE_MODELE_CREATION`, `DECOUPAGE_MODELE_MODIFICATION`, `DECOUPAGE_MODELE_ACTIVATION`, `DECOUPAGE_MODELE_DESACTIVATION`, `DECOUPAGE_MODELE_DUPLICATION`, `DECOUPAGE_MODELE_RETRAIT`.

| Méthode et route | Effet |
|---|---|
| `GET admins/decoupage/listes/` | Les listes de la plateforme (`?valeurs=true\|false`, `?est_actif=true\|false`, `?recherche=<texte>`) |
| `POST admins/decoupage/listes/` | Créer une liste |
| `GET admins/decoupage/listes/modele-excel/` | Télécharger le gabarit Excel d'import de liste de valeurs |
| `GET admins/decoupage/listes/{id}/` | Une liste et ses valeurs |
| `PATCH admins/decoupage/listes/{id}/` | Renommer, décrire, réordonner ou modifier `est_actif` |
| `POST admins/decoupage/listes/{id}/activer/` | Activer la liste (`est_actif = true`) |
| `POST admins/decoupage/listes/{id}/desactiver/` | Désactiver la liste (`est_actif = false`) |
| `DELETE admins/decoupage/listes/{id}/` | Retirer (suppression logique ; **422** si utilisée par un modèle plateforme, un modèle entreprise ou un projet) |
| `POST admins/decoupage/listes/{id}/valeurs/` | Ajouter des valeurs en masse |
| `POST admins/decoupage/listes/{id}/valeurs/importer/` | Importer des valeurs depuis un fichier `.xlsx` ou `.csv` |
| `PATCH admins/decoupage/valeurs/{id}/` | Corriger une valeur |
| `DELETE admins/decoupage/valeurs/{id}/` | Retirer une valeur (suppression logique) |
| `GET admins/decoupage/modeles/` | Les modèles de la plateforme (`?recherche=<texte>`, `?type_projet=<code>`, `?est_actif=true\|false`) |
| `POST admins/decoupage/modeles/` | Créer un modèle (`version = 1`) |
| `GET admins/decoupage/modeles/modele-excel/` | Télécharger le gabarit Excel d'un modèle de découpage |
| `POST admins/decoupage/modeles/importer-fichier/` | Extraire `{niveaux, lignes}` d'un fichier `.xlsx` ou `.csv` |
| `GET admins/decoupage/modeles/{id}/` | Un modèle, avec son gabarit, ses lignes types et `nombre_copies_entreprises` |
| `PUT admins/decoupage/modeles/{id}/` | Remplacer un modèle (versioning sélectif : `version` augmente uniquement si `niveaux` ou `lignes` changent) |
| `PATCH admins/decoupage/modeles/{id}/` | Modifier partiellement un modèle (versioning sélectif) |
| `POST admins/decoupage/modeles/{id}/activer/` | Activer un modèle (`est_actif = true`, sans incrémenter `version`) |
| `POST admins/decoupage/modeles/{id}/desactiver/` | Désactiver un modèle (`est_actif = false`, sans incrémenter `version`) |
| `POST admins/decoupage/modeles/{id}/dupliquer/` | Dupliquer un modèle plateforme (`201`, nom unique `{nom} (copie)`, `version = 1`, `par_defaut_pour = []`) |
| `DELETE admins/decoupage/modeles/{id}/` | Retirer un modèle (suppression logique cascadée sur ses niveaux et lignes) |

### 3.1 Une liste de la plateforme

```json
{
  "id": "…",
  "libelle": "Lots",
  "description": "",
  "ordre": 1,
  "est_actif": true,
  "nombre_valeurs": 58,
  "nombre_utilisations_plateforme": 3,
  "nombre_utilisations_entreprises": 14,
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
| `est_actif` | Faux : la liste n'est plus proposée aux nouvelles liaisons, mais reste résolue sur les modèles et projets existants |
| `nombre_valeurs` | Valeurs actives de la plateforme |
| `nombre_utilisations_plateforme` | Nombre de niveaux actifs de modèles plateforme liés à cette liste |
| `nombre_utilisations_entreprises` | Nombre total de niveaux actifs (modèles d'entreprise + projets) liés à cette liste à travers les entreprises |
| `modeles[]` | Modèles de la plateforme (non retirés) dont un niveau puise dans cette liste |
| `valeurs[]` | Valeurs d'origine `PLATEFORME` ; absent avec `?valeurs=false` |

### 3.2 Créer, modifier, activer/désactiver une liste

- **`POST admins/decoupage/listes/`** : `libelle` (requis, 100 caractères), `description`, `valeurs`. **201** : la liste (§3.1). **409** `libelle_en_double` si une liste de la plateforme porte déjà ce nom.
- **`PATCH admins/decoupage/listes/{id}/`** : `libelle`, `description`, `ordre`, `est_actif` (tous facultatifs). **200** : la liste (§3.1).
- **`POST admins/decoupage/listes/{id}/activer/`** et **`/desactiver/`** : bascule `est_actif` à `true` ou `false`. **200** : la liste (§3.1).

### 3.3 Retirer une liste — `DELETE admins/decoupage/listes/{id}/`

**204** si la liste n'est utilisée nulle part.
**422** `regle_metier` dès qu'au moins un niveau actif (modèle plateforme, modèle d'entreprise ou
projet) y puise, avec :

```json
{
  "usages_plateforme": 1,
  "usages_modeles_entreprise": 2,
  "usages_projets": 5,
  "modeles": [{"id": "…", "nom": "…"}]
}
```

Le message indique les compteurs et invite à désactiver la liste (`est_actif=False`) plutôt que la
supprimer.

### 3.4 Un modèle de la plateforme

`GET admins/decoupage/modeles/` rend les modèles sans leur gabarit (filtrables par `?recherche=`,
`?type_projet=`, `?est_actif=true|false`) ; `GET …/{id}/`, `POST`, `PUT`, `PATCH`, `/activer/`,
`/desactiver/` et `/dupliquer/` rendent le modèle complet avec son gabarit.

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
  "nombre_copies_entreprises": 4,
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
| `version` | Version du gabarit. **Versioning sélectif** : n'augmente que lorsque `niveaux` ou `lignes` changent réellement ; modifier `nom`, `description`, `types_projet`, `par_defaut_pour` ou `est_actif` ne l'incrémente pas |
| `est_actif` | Faux : le modèle n'est plus proposé aux entreprises, sans être retiré |
| `niveaux_libelles` | Les libellés des niveaux (présent en liste comme en détail) |
| `nombre_lignes` | Nombre de lignes types actives |
| `nombre_copies_entreprises` | Nombre de copies personnalisées actives (`ModeleDecoupageEntreprise`) liées à ce modèle via `origine_id` (présent en liste comme en détail) |
| `niveaux`, `lignes` | Le gabarit, comme côté entreprise (§2.5) ; absents de la liste |

### 3.5 Créer, mettre à jour, activer/désactiver, dupliquer ou retirer un modèle

- **`POST admins/decoupage/modeles/`** : crée un modèle (`version = 1`).
- **`PUT admins/decoupage/modeles/{id}/`** et **`PATCH admins/decoupage/modeles/{id}/`** : mise à jour complète ou partielle. `par_defaut_pour` doit être un sous-ensemble de `types_projet` (**400** `validation` sinon). `version` n'est incrémentée que si le gabarit normalisé (`niveaux`, `lignes`) a changé.
- **`POST admins/decoupage/modeles/{id}/activer/`** et **`/desactiver/`** : bascule `est_actif` sans incrémenter `version`. **200** : le modèle complet (§3.4).
- **`POST admins/decoupage/modeles/{id}/dupliquer/`** : clone le modèle sous un nom unique (`{nom} (copie)`, `{nom} (copie 2)`…), `version = 1`, `est_actif = true`, `par_defaut_pour = []`, mêmes niveaux et lignes. **201** : le modèle cloné complet (§3.4).
- **`DELETE admins/decoupage/modeles/{id}/`** : **204**. Suppression logique cascadée sur le modèle, ses niveaux et ses lignes. Les copies personnalisées côté entreprise restent autonomes et exposent `original_supprime = true` et `origine_plateforme_id = null`.
