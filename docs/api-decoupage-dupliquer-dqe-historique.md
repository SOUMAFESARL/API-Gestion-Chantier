# Dupliquer une branche, importer un DQE, historique d'une case — contrat d'API

| | |
|---|---|
| Décisions | `docs/decoupage/decisions-v1.2.md`, §11bis, §12.2, §12.4 et §13quinquies.1 |
| Lot | 5 du plan de découpage en arbre |
| Vues | `apps/projets/views/decoupage.py` (`ElementDupliquerView`, `ProjetDqeView`, `ProjetDqeAppliquerView`, `ElementHistoriqueView`) |
| Services | `services/arbre.py` (`dupliquer_branche`), `services/import_dqe.py`, `services/import_export.py`, `selectors/historique.py` |

Toutes les routes sont sous `/api/v1/`. Format d'erreur unique :
`{"erreur": {"code", "message", "details", "trace_id"}}`.

| HTTP | `code` | Quand |
|---|---|---|
| 400 | `validation` | Corps invalide, motif manquant ; `details` porte le champ en faute |
| 403 | `acces_refuse` | Permission manquante, ou case hors du périmètre |
| 404 | `introuvable` | Projet ou case inconnu, ou invisible pour cette personne |
| 409 | `conflit` | Intitulé déjà porté par une case sœur (A-6) |
| 409 | `projet_clos` | Projet résilié, archivé ou désactivé (écritures seulement) |
| 422 | `regle_metier` | Règle de l'arbre : niveau sauté (A-1), mélange de niveaux (A-2), tâche commencée (A-5)… |

---

## 1. Dupliquer une branche — `POST elements/{id}/dupliquer/`

Copie la case et toute sa branche **active** (§13quinquies.1).

| Copié | Non copié |
|---|---|
| La structure (niveaux, intitulés, ordre des enfants) | Les mesures : quantité réalisée, pourcentage déclaré, clôture |
| Mode de mesure, unité, quantité prévue (qui devient aussi la quantité initiale) | Les dates prévues, les baselines, les dates réelles, les jours accordés |
| Montant (devenu aussi montant initial) et enveloppe | Les affectations (périmètres) et les équipes |
| Mode d'exécution, type de bordereau, titulaire | Le **code libre** : il numérote une ligne du bordereau du client |
| | Les cases désactivées de la branche ; la suspension |

**Permission** : `projets.decouper` dans le périmètre, sur la case copiée **et** sur la destination
(sur tout le projet pour une copie à la racine).

```json
{"parent_id": "…", "libelle": "Bâtiment B", "motif": ""}
```

| Champ | Requis | Règle |
|---|---|---|
| `parent_id` | non | **Absent** : la copie se pose à côté de l'original (même parent). **`null`** : à la racine (seulement pour une case du premier niveau). Sinon, une case du même projet |
| `libelle` | non | Intitulé de la copie. Absent ou vide : « Intitulé (copie) », puis « (copie 2) »… le premier libre parmi les sœurs |
| `motif` | selon le cas | Au moins 10 caractères si la destination est **commencée** : c'est un ajout sous une case commencée, modification tracée (§12.2) |

La destination suit les règles d'un déplacement (§12.4) : un parent du niveau juste au-dessus ou du
même niveau (récursion), jamais dans la branche copiée, jamais une tâche commencée (A-5), jamais
parmi des sœurs d'un autre niveau (A-2). Une destination qui était une feuille non commencée
devient un parent : son montant devient son enveloppe (§8).

**201** :

```json
{"case": {"id": "…", "libelle": "Gros œuvre (copie)", "…": "…"}, "cases_copiees": 3}
```

| Champ | Sens |
|---|---|
| `case` | La copie, telle que `GET elements/{id}/` la rend (avancement, montants selon `projets.voir_montants`, etc.) |
| `cases_copiees` | Nombre de cases créées, la copie comprise |

**Erreurs.** 400 `validation` (`details.motif`) si le motif manque sous une case commencée ;
409 `conflit` si `libelle` est déjà pris (`details: {libelle, existant}`) ; 422 `regle_metier`
pour une destination interdite ou une case désactivée ; 403 hors périmètre.

**Trace.** Deux entrées au journal d'audit : `DUPLICATION` sur la copie (`source`,
`cases_copiees`) et `DUPLIQUEE` sur l'original (`copie`, `cases_copiees`), avec le motif.

---

## 2. Importer un DQE sur un projet déjà découpé

### 2.1 Le fichier

`.xlsx` ou `.csv` (séparateur `;` ou `,`, UTF-8 ou Windows-1252), 5 Mo et 5 000 lignes au plus.
**Même format que l'import du tableau de démarrage** (`POST projets/{id}/decoupage/importer/`) :

- la première ligne porte les en-têtes ;
- **les colonnes des niveaux du projet, dans l'ordre** (sinon 400 : « Les colonnes doivent
  reprendre les niveaux du projet, dans l'ordre : … ») ;
- puis, facultatives et dans n'importe quel ordre :

| Colonne | En-têtes reconnus (sans accents ni majuscules) | Contenu |
|---|---|---|
| Unité | `Unité`, `U` | `m2`, `m²`, `m3`, `ml`, `kg`, `u`, `ff`, `ens`, ou un code (`M2`, `ML`, `M3`, `KG`, `U`, `FORFAIT`) |
| Quantité | `Quantité`, `Quantité prévue`, `Qté` | Nombre, virgule ou point décimal |
| Prix unitaire | `Prix unitaire`, `PU`, `P.U.`, `Prix unitaire (FCFA)` | **En FCFA**. Sert seulement à calculer le montant ; n'est pas conservé |
| Montant | `Montant`, `Montant (FCFA)`, `Montant HT`, `Valeur` | **En FCFA** |
| Début, Fin | `Début`, `Date de début`, `Fin`, `Date de fin` | `AAAA-MM-JJ`, `JJ/MM/AAAA`, `JJ/MM/AA` ou `JJ-MM-AAAA` |

**Montant d'une ligne** : la colonne Montant si elle est remplie ; sinon Quantité × Prix unitaire.
Les deux remplis et différents d'au moins 1 FCFA : le montant est retenu, un avertissement
`PU` le signale. Les montants passent en **centimes** dans les réponses, comme partout dans l'API.

> **Changement du lot 5** — l'import et l'export Excel du tableau (`…/decoupage/importer/`,
> `…/decoupage/exporter/`) lisent et écrivent désormais eux aussi les montants **en FCFA**
> (l'export écrivait des centimes sous l'en-tête « Montant (FCFA) »). Ils reconnaissent la même
> colonne « Prix unitaire ».

### 2.2 Le rapprochement par chemin

Chaque ligne désigne une case par la suite de ses intitulés (comparés sans accents, casse ni
espaces superflus), jusqu'à sa dernière cellule remplie.

| La ligne… | Effet |
|---|---|
| mène à une **feuille** | **Mise à jour** de son unité, de sa quantité prévue, de son montant (§11bis) ; ses dates si elle n'en a pas encore |
| mène à une case **parente** | Refusée si elle porte des valeurs (`case_parente`) ; sans valeurs, inchangée |
| ne mène à **aucune case** | **Nouvelle branche**, rattachée à la case existante la plus profonde de son chemin (ou à la racine) |
| porte les mêmes valeurs que la feuille | Inchangée |

**Une feuille absente du fichier n'est jamais touchée.** Aucune case n'est supprimée, renommée
ni déplacée par un import.

**Règles d'une mise à jour (§11bis).**
- Feuille **commencée** : changer sa quantité ou son montant est une modification tracée — le
  bilan dit `motif_requis`, et l'application exige un motif.
- La quantité prévue **ne descend pas sous le réalisé** (`quantite_sous_realise`).
- L'unité d'une feuille commencée **ne change plus** (`unite_figee`).
- **Dates** : une feuille sans dates est planifiée, dans le cadre de ses parents
  (`dates_hors_parent` sinon : le fichier ne prolonge jamais un parent) ; une feuille déjà datée
  garde les siennes (`dates_deja_fixees` : elles se reprogramment dans la vue en arbre, avec
  motif et justification, RG-11).

**Permissions, dans le périmètre de chaque case.** `projets.chiffrer` pour l'unité, la quantité et
le montant ; `projets.planifier` pour les dates ; `projets.decouper` sur la case de rattachement
d'une nouvelle branche (plus `chiffrer` et `planifier` si la ligne porte des valeurs ou des dates).
Une ligne hors de ces droits est refusée (`hors_perimetre`), les autres passent. Pour appeler les
routes, il faut `projets.chiffrer` ou `projets.decouper` quelque part sur le projet (sinon 403).

### 2.3 Le bilan — `POST projets/{id}/decoupage/dqe/`

**Rien n'est écrit.** Deux formes d'entrée :

- `multipart/form-data`, champ `fichier` : le fichier du DQE ;
- `application/json`, `{"lignes": [...]}` : des lignes déjà lues (celles rendues par un premier
  bilan, éventuellement filtrées), pour refaire le bilan sans renvoyer le fichier.

**200** :

```json
{
  "lignes": [
    {"cellules": ["Bâtiment A", "Gros œuvre", "Murs RDC"], "unite": "M2", "quantite": "450", "montant": 2475000000}
  ],
  "bilan": {
    "mises_a_jour": [
      {
        "ligne": 1,
        "chemin": ["Bâtiment A", "Gros œuvre", "Murs RDC"],
        "element_id": "…",
        "commencee": true,
        "modification_tracee": true,
        "changements": {
          "quantite_prevue": {"avant": "400.000", "apres": "450"},
          "montant": {"avant": 2000000000, "apres": 2475000000}
        }
      }
    ],
    "nouvelles_branches": [
      {
        "ligne": 5,
        "chemin": ["Bâtiment A", "Peinture", "Peinture extérieure"],
        "rattachement": {"id": "…", "libelle": "Peinture"},
        "rattachement_devient_parent": false,
        "cases_a_creer": 1,
        "feuille": {"unite": "M2", "quantite_prevue": "300", "montant": 75000000}
      }
    ],
    "refus": [
      {"ligne": 3, "code": "ligne_invalide", "regle": "C-2", "message": "Ligne 3 : même chemin que la ligne 1."},
      {"ligne": 7, "chemin": ["…"], "code": "valeur_invalide", "message": "Ligne 7 : unité inconnue (M2, ML, M3, KG, U, FORFAIT)."}
    ],
    "inchangees": [2],
    "avertissements": [{"regle": "PU", "ligne": 4, "message": "…"}],
    "motif_requis": true,
    "resume": {"lignes": 7, "mises_a_jour": 1, "nouvelles_feuilles": 1, "refus": 2, "inchangees": 1}
  }
}
```

| Champ | Sens |
|---|---|
| `lignes` | Les lignes lues, montants en centimes, **à renvoyer** à l'application. Le numéro d'une ligne est son rang dans cette liste (1 = première ligne sous les en-têtes) |
| `mises_a_jour[].changements` | Par champ changé (`unite`, `quantite_prevue`, `montant`, `date_debut_prevue`, `date_fin_prevue`) : `avant` et `apres`. Sans `projets.voir_montants`, les montants valent `null` |
| `mises_a_jour[].modification_tracee` | Feuille commencée dont la quantité ou le montant change : motif exigé |
| `nouvelles_branches[].rattachement` | La case existante sous laquelle la branche se crée ; `null` : à la racine |
| `nouvelles_branches[].rattachement_devient_parent` | Le rattachement était une feuille (non commencée) : son montant deviendra son enveloppe (§8) |
| `nouvelles_branches[].cases_a_creer` | Cases nouvelles sur ce chemin (les intermédiaires partagés par plusieurs lignes ne sont créés qu'une fois) |
| `nouvelles_branches[].feuille` | Ce que portera la nouvelle feuille |
| `refus[]` | `ligne`, `code`, `message` (et `chemin`, ou `regle` pour une ligne invalide) |
| `inchangees` | Numéros des lignes sans effet sur leur feuille |
| `avertissements` | Ceux du tableau (C-5, C-6, C-7, `SANS_EFFET` : ligne dont la dernière case a des enfants sur d'autres lignes, ignorée) et `PU` |
| `motif_requis` | Vrai si au moins une mise à jour est une modification tracée |

**Codes de refus** (stables) :

| `code` | Raison |
|---|---|
| `ligne_invalide` | Bloquant du tableau sur la ligne : cellule vide au milieu (C-1), plus de cellules que de niveaux, même chemin qu'une ligne précédente (C-2) |
| `valeur_invalide` | Unité inconnue, nombre ou date illisible, fin avant le début |
| `hors_perimetre` | La permission nécessaire manque sur cette case |
| `case_desactivee` | La case (ou son rattachement) est désactivée |
| `case_parente` | La ligne porte des valeurs sur une case qui a des sous-tâches |
| `unite_figee` | Changer l'unité d'une feuille commencée |
| `quantite_sous_realise` | Quantité prévue sous la quantité réalisée |
| `dates_deja_fixees` | Dates différentes de celles, déjà fixées, de la feuille |
| `dates_hors_parent` | Dates qui obligeraient à prolonger une case parente ou le projet |
| `feuille_commencee` | Nouvelle branche sous une tâche commencée (A-5) : la détailler d'abord |
| `niveau_incompatible` | Nouvelle branche parmi des sœurs d'un autre niveau (A-2), sous une case en récursion |

**Erreurs de la route.** 400 sur un fichier illisible, sans ligne de tâche, ou dont les colonnes ne
reprennent pas les niveaux du projet ; 422 si le projet n'est pas encore découpé (« importez le
fichier dans le tableau de démarrage »).

### 2.4 L'application — `POST projets/{id}/decoupage/dqe/appliquer/`

```json
{"lignes": ["… les lignes rendues par le bilan …"], "motif": "DQE révisé du client, version du 28/10"}
```

| Champ | Requis | Règle |
|---|---|---|
| `lignes` | oui | 1 à 5 000 lignes, sous la forme rendue par le bilan (liste de cellules, ou objet portant `cellules`) |
| `motif` | si `motif_requis` | Au moins 10 caractères ; sinon **400** (`details.motif`), et rien n'est écrit |

Le bilan est **refait** sur les lignes reçues, puis appliqué **ligne par ligne** : une mise à jour
refusée à ce moment (l'arbre a changé depuis le bilan) est rendue dans `refus`, sans empêcher les
autres. Les nouvelles branches sont créées ensemble, comme par le tableau ; si leur création
échoue, elles sont toutes rendues dans `refus` et les mises à jour restent faites.

**200** :

```json
{
  "mises_a_jour": [1, 4],
  "nouvelles_feuilles": [5, 6],
  "cases_creees": 4,
  "refus": [{"ligne": 3, "code": "ligne_invalide", "message": "…"}],
  "inchangees": [2],
  "resume": {"mises_a_jour": 2, "nouvelles_feuilles": 2, "cases_creees": 4, "refus": 1, "inchangees": 1},
  "arbre": {"projet_id": "…", "niveaux": ["…"], "cases": ["…"]}
}
```

| Champ | Sens |
|---|---|
| `mises_a_jour` | Numéros des lignes appliquées à une feuille existante |
| `nouvelles_feuilles` | Numéros des lignes devenues de nouvelles feuilles |
| `cases_creees` | Cases créées, intermédiaires compris |
| `refus` | Comme dans le bilan ; un refus survenu à l'application porte le code de l'erreur métier rencontrée |
| `arbre` | L'arbre du projet après l'import, comme `GET projets/{id}/arbre/` |

**Trace.** Chaque feuille mise à jour reçoit une entrée `IMPORT_DQE` (avant, après, motif) à son
historique ; le projet reçoit une entrée `IMPORT_DQE` (comptes) ; les nouvelles branches, l'entrée
`AJOUT_EN_MASSE` du tableau. L'avancement est recalculé une fois, à la fin.

---

## 3. Historique des modifications d'une case — `GET elements/{id}/historique/`

Lu dans le **journal d'audit immuable** : chaque geste sur une case y écrit une entrée. Aucune
table de plus. Les reports de dates ont leur propre historique, plus détaillé (motif de la liste,
justification, écart en jours) : `GET elements/{id}/historique-dates/`.

**Permission** : `projets.lire` dans le périmètre. Une case dont on ne voit que l'intitulé (le
chemin qui mène à son périmètre) répond **403** ; une case invisible, **404**.

**Pagination standard** : `?page=2&taille_page=50` (20 par défaut, 100 au plus). Les entrées vont
de la plus récente à la plus ancienne.

**200** :

```json
{
  "total": 3,
  "page": 1,
  "nombre_pages": 1,
  "suivant": null,
  "precedent": null,
  "resultats": [
    {
      "id": 4182,
      "horodatage": "2026-10-30T21:40:12.118Z",
      "action": "MODIFICATION",
      "geste": "IMPORT_DQE",
      "geste_libelle": "Import du DQE",
      "motif": "DQE révisé du client, version du 28/10",
      "auteur": {"id": "…", "nom": "Awa Koné"},
      "avant": {"montant": 2000000000, "quantite_prevue": "400.000"},
      "apres": {"montant": 2475000000, "quantite_prevue": "450"}
    }
  ]
}
```

| Champ | Sens |
|---|---|
| `id` | Rang de l'entrée au journal (séquentiel) |
| `horodatage` | UTC, ISO 8601 |
| `action` | Action du journal (`MODIFICATION` pour les gestes de l'arbre) |
| `geste` | Le geste : voir la table ci-dessous ; un code inconnu s'affiche tel quel |
| `geste_libelle` | Son nom à afficher |
| `motif` | Le motif saisi, ou vide |
| `auteur` | `{id, nom}`, ou `null` pour une action du système |
| `avant`, `apres` | Les valeurs changées, quand le geste en a (sinon `null`). Sans `projets.voir_montants`, `montant`, `montant_initial`, `enveloppe` et `poids` valent `null` |

| `geste` | `geste_libelle` |
|---|---|
| `MODIFICATION` | Modification (renommer, chiffrer, métrer, régler l'exécution d'une case commencée ou avec motif) |
| `AJOUT_SOUS_CASE_COMMENCEE` | Ajout sous une case commencée |
| `DEPLACEMENT` | Déplacement (`avant.parent`, `apres.parent`) |
| `DETAIL` | Détail en sous-tâches |
| `SUPPRESSION`, `DESACTIVATION`, `REACTIVATION` | Suppression, désactivation, réactivation |
| `SUSPENSION`, `REPRISE` | Suspension, reprise |
| `CLOTURE`, `REOUVERTURE` | Clôture, réouverture |
| `DUPLICATION`, `DUPLIQUEE` | Créée par copie (`apres.source`), copiée (`apres.copie`) |
| `IMPORT_DQE` | Import du DQE |
