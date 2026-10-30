# Dépendances entre tâches — contrat d'API

| | |
|---|---|
| Décisions | `docs/decoupage/decisions-v1.2.md`, §11 et §13quinquies.5 ; décisions du développeur du 30/10/2026 |
| Lot | 10 du plan de découpage en arbre |
| Modèle | `projets.Dependance` (table `dependance_element`, schéma de l'entreprise, migration `projets/0050_dependances`) |
| Service | `apps/projets/services/dependances.py` |
| Vues | `apps/projets/views/dependances.py` ; reprogrammation (`views/reprogrammation.py`), planification (`views/decoupage.py`), planning (`views/planning.py`) |

Toutes les routes sont sous `/api/v1/`. Format d'erreur unique :
`{"erreur": {"code", "message", "details", "trace_id"}}`.

## 1. Les règles

| Règle | Détail |
|---|---|
| Un seul type de lien | **B commence après la fin de A** (fin → début), **sans délai** |
| « Après la fin » | B commence **au plus tôt le lendemain** de la fin prévue de A. Une date de fin compte comme un jour de travail jusqu'au soir |
| Plusieurs prédécesseurs | B commence après la fin du **plus tardif** de ses prédécesseurs |
| Entre feuilles | Un lien relie deux **tâches du bas** (feuilles) actives d'un même projet, d'une même branche ou de **deux branches** |
| Pas de boucle | Un lien qui ferait qu'une tâche se suive elle-même est refusé |
| Dates manquantes | Une tâche sans date de fin (A) ou sans date de début (B) ne contraint rien |
| Planifier B trop tôt | **Refusé**, avec un message qui nomme le prédécesseur (`dependance_non_respectee`) |
| Reprogrammer A plus tard | Les successeurs qui commenceraient trop tôt sont listés, « décaler aussi » coché par défaut ; **seuls ceux confirmés sont décalés** (durée conservée), sinon le report est refusé. Jamais de décalage silencieux |
| Avancer A | Aucun successeur n'est avancé |
| Le décalage suit le §11 | Le parent du successeur encadre ; s'il faut le prolonger, `prolongation_requise` ; prolonger le projet ou une case commencée exige `projets.prolonger` |
| Détailler une feuille liée | Chaque nouvelle sous-tâche hérite de ses prédécesseurs ; ses successeurs attendent toutes les sous-tâches. De même quand une feuille liée reçoit des sous-tâches autrement (ajout, copie dessous, tableau, import DQE) |
| Désactiver, supprimer | Les liens des tâches de la branche sont retirés, avec une trace au journal d'audit. Réactiver ne les rétablit pas |
| Déplacer | Les liens restent |

**Permissions.** Créer ou retirer un lien : `projets.planifier` **dans le périmètre des deux
tâches**. Lire les liens : voir la case en entier (`projets.lire` dans le périmètre). Décaler un
successeur : `projets.planifier` dans son périmètre.

## 2. Codes d'erreur propres aux dépendances

| HTTP | `code` | Quand | `details` |
|---|---|---|---|
| 422 | `dependance_non_respectee` | Une tâche commencerait avant la fin d'un de ses prédécesseurs (planifier, reprogrammer, lier, détailler) | `predecesseur: {id, libelle, date_fin_prevue}`, `date_debut_au_plus_tot` |
| 422 | `successeurs_a_decaler` | Le report ferait commencer des successeurs trop tôt et ils ne sont pas (tous) confirmés | `successeurs: [décalage]` (§4.2), `non_confirmes: [id]` |
| 409 | `dependance_boucle` | Le lien fermerait une boucle | `boucle: [id, …]` (de B à B en passant par A) |
| 409 | `conflit` | Le lien existe déjà | |
| 422 | `regle_metier` | Tâche parente, désactivée, ou de deux projets différents ; une tâche liée à elle-même | |
| 400 | `validation` | Ni ou les deux de `predecesseur_id` et `successeur_id` | |
| 403 | `acces_refuse` | `projets.planifier` manque sur l'une des deux tâches | |

Exemple de `dependance_non_respectee` :

```json
{
  "erreur": {
    "code": "dependance_non_respectee",
    "message": "« Murs RDC » ne peut pas commencer le 15/11/2026 : elle suit « Fondations », qui finit le 20/11/2026. Elle commence au plus tôt le 21/11/2026.",
    "details": {
      "predecesseur": {"id": "…", "libelle": "Fondations", "date_fin_prevue": "2026-11-20"},
      "date_debut_au_plus_tot": "2026-11-21"
    },
    "trace_id": "…"
  }
}
```

## 3. Les liens d'une tâche

### 3.1 Lister — `GET elements/{id}/dependances/`

**200** :

```json
{
  "element_id": "…",
  "predecesseurs": [
    {
      "lien_id": "…",
      "id": "…",
      "visible": true,
      "libelle": "Fondations",
      "date_debut_prevue": "2026-11-02",
      "date_fin_prevue": "2026-11-20",
      "respectee": true
    }
  ],
  "successeurs": [
    {"lien_id": "…", "id": "…", "visible": false, "respectee": true}
  ]
}
```

| Champ | Sens |
|---|---|
| `lien_id` | À passer à `DELETE dependances/{id}/` |
| `id` | La tâche liée |
| `visible` | Faux : la tâche liée est hors du périmètre de lecture ; seuls `lien_id`, `id`, `respectee` sont donnés |
| `libelle`, `date_debut_prevue`, `date_fin_prevue` | Si `visible` |
| `respectee` | Vrai : B commence après la fin de A ; faux : non (données antérieures) ; `null` : une date manque |

**403** si l'on ne voit de cette case que son intitulé ; **404** si elle est invisible.

### 3.2 Ajouter — `POST elements/{id}/dependances/`

La case de l'URL est l'une des deux tâches ; l'autre est donnée par **un seul** des deux champs :

```json
{"predecesseur_id": "…"}
```

| Champ | Sens |
|---|---|
| `predecesseur_id` | La case de l'URL **suit** cette tâche |
| `successeur_id` | La case de l'URL **précède** cette tâche |

Si les deux tâches sont déjà datées et que B commence avant la fin de A, le lien est refusé
(`dependance_non_respectee`) : reprogrammer B d'abord.

**201** :

```json
{
  "id": "…",
  "predecesseur": {"id": "…", "libelle": "Fondations", "date_fin_prevue": "2026-11-20"},
  "successeur": {"id": "…", "libelle": "Murs RDC", "date_debut_prevue": "2026-11-23"},
  "respectee": true
}
```

**Trace** : `LIEN_AJOUT` à l'historique des deux tâches.

### 3.3 Retirer — `DELETE dependances/{id}/`

**204**. Suppression logique. **Trace** : `LIEN_RETRAIT` à l'historique des deux tâches.

## 4. Dates et dépendances

### 4.1 Planifier — `POST elements/{id}/planifier/`

Première saisie des dates (inchangée, voir le contrat du découpage), avec deux effets :

- un début avant la fin d'un prédécesseur est **refusé** (`dependance_non_respectee`) ;
- une fin qui ferait commencer trop tôt un successeur déjà daté répond `successeurs_a_decaler` ;
  on confirme par `decaler_successeurs` (identifiants), **avec `motif_id` et `justification`**
  (décaler une tâche datée est un report, RG-11).

```json
{
  "date_debut_prevue": "2026-11-02",
  "date_fin_prevue": "2026-11-30",
  "decaler_successeurs": ["…"],
  "motif_id": "…",
  "justification": "Au moins trente caractères pour expliquer le report…"
}
```

**200** : `{"case": {…}, "prolongations": [...], "decalages": [...]}` — `decalages` comme en §4.3.

### 4.2 L'aperçu d'un report — `POST elements/{id}/reprogrammer/` avec `apercu: true`

**Rien n'est écrit.** `motif_id` et `justification` sont facultatifs pour un aperçu.

```json
{"date_fin_prevue": "2026-11-30", "apercu": true}
```

**200** :

```json
{
  "date_debut_prevue": "2026-11-02",
  "date_fin_prevue": "2026-11-30",
  "date_debut_avant": "2026-11-02",
  "date_fin_avant": "2026-11-20",
  "prolongations": [],
  "successeurs_a_decaler": [
    {
      "id": "…",
      "libelle": "Murs RDC",
      "date_debut_avant": "2026-11-23",
      "date_fin_avant": "2026-12-15",
      "date_debut_apres": "2026-12-01",
      "date_fin_apres": "2026-12-23",
      "jours": 8,
      "apres": {"id": "…", "libelle": "Fondations"},
      "decaler_aussi": true,
      "prolongations": []
    },
    {
      "id": "…",
      "libelle": "Peinture intérieure",
      "date_debut_avant": "2026-12-16",
      "date_fin_avant": "2027-01-10",
      "date_debut_apres": "2026-12-24",
      "date_fin_apres": "2027-01-18",
      "jours": 8,
      "apres": {"id": "…", "libelle": "Murs RDC"},
      "decaler_aussi": true,
      "prolongations": []
    }
  ],
  "refus": []
}
```

| Champ | Sens |
|---|---|
| `prolongations` | Les cases parentes (et le projet) que le report obligerait à prolonger (§11) |
| `successeurs_a_decaler` | Les tâches qui commenceraient trop tôt, **de proche en proche** (le successeur d'un successeur décalé y figure aussi), avec leurs nouvelles dates : début le lendemain de la fin la plus tardive de leurs prédécesseurs, durée conservée |
| `…[].apres` | Le prédécesseur qui impose la nouvelle date |
| `…[].decaler_aussi` | Toujours vrai : la case « décaler aussi » est cochée par défaut |
| `…[].prolongations` | Les parents de ce successeur qu'il faudrait prolonger s'il est décalé |
| `refus` | Ce qui refuserait le report : `{code: "dependance_non_respectee", message, details}` (un prédécesseur finit après le nouveau début), `{code: "enfants_hors_cadre", message}` (un enfant sortirait du cadre) |

L'aperçu vaut aussi pour `POST projets/{id}/reprogrammer/` (sans successeurs ni prolongations).

### 4.3 Reprogrammer — `POST elements/{id}/reprogrammer/`

Corps habituel (`date_debut_prevue`, `date_fin_prevue`, `motif_id`, `justification` d'au moins 30
caractères, `prolonger`), plus :

| Champ | Sens |
|---|---|
| `decaler_successeurs` | Identifiants des successeurs à décaler aussi (ceux restés cochés). Absent ou `null` : rien n'est confirmé |

- Le nouveau début est vérifié contre les prédécesseurs (`dependance_non_respectee`).
- Si des successeurs commenceraient trop tôt et que **l'un d'eux** manque à
  `decaler_successeurs`, le report est **refusé** (`successeurs_a_decaler`, `details.non_confirmes`) :
  décocher un successeur, c'est renoncer au report tel quel (ou retirer le lien d'abord).
- Chaque successeur décalé est reprogrammé : historique des dates avec le motif du report
  d'origine et la justification « Décalée par le report de « A » : … », prolongation de ses
  parents selon le §11 (confirmée par le même `prolonger`), trace `DECALAGE_SUCCESSEUR` à son
  historique. Il faut `projets.planifier` sur chacun (403 sinon, en le nommant).

**200** : la réponse habituelle, plus :

```json
{
  "decalages": [
    {
      "id": "…",
      "libelle": "Murs RDC",
      "date_debut_avant": "2026-11-23",
      "date_fin_avant": "2026-12-15",
      "date_debut_apres": "2026-12-01",
      "date_fin_apres": "2026-12-23",
      "jours": 8,
      "apres": {"id": "…", "libelle": "Fondations"},
      "decaler_aussi": true,
      "prolongations": []
    }
  ]
}
```

## 5. Ce que les autres routes rendent

**La case (tiroir)** — `GET elements/{id}/`, `GET projets/{id}/arbre/` et la réponse des gestes :
deux champs de plus sur une case vue en entier, `predecesseurs` et `successeurs`, de la même forme
qu'en §3.1. Une case vue par son seul chemin ne les porte pas.

**Le planning** — `GET projets/{id}/planning/` : un tableau `dependances` à côté de `cases`, pour
dessiner les flèches.

```json
{
  "aujourdhui": "2026-10-30",
  "cases": ["…"],
  "dependances": [
    {"id": "…", "predecesseur_id": "…", "successeur_id": "…", "respectee": true}
  ]
}
```

Seuls les liens dont les deux tâches sont visibles en entier y figurent. `respectee` se lit sur
les dates prévues ; les barres du planning, elles, montrent la baseline quand elle est complète.

**L'import DQE** (`docs/api-decoupage-dupliquer-dqe-historique.md`) : une ligne qui daterait une
feuille avant la fin d'un prédécesseur est refusée (`dependance_non_respectee`) ; une ligne dont
la fin ferait commencer trop tôt un successeur aussi (`successeurs_a_decaler` : la planifier dans
la vue en arbre, qui propose le décalage).

**L'historique d'une case** (`GET elements/{id}/historique/`) : nouveaux gestes.

| `geste` | `geste_libelle` |
|---|---|
| `LIEN_AJOUT` | Dépendance ajoutée (`apres.predecesseur` ou `apres.successeur`, `apres.lien`) |
| `LIEN_RETRAIT` | Dépendance retirée (`avant.…`) |
| `LIENS_HERITES_DETAIL` | Dépendances reportées sur les sous-tâches (`avant.liens`, `apres.feuilles`, `apres.liens`) |
| `LIENS_RETIRES_DESACTIVATION` | Dépendances retirées (désactivation) (`avant.liens`) |
| `LIENS_RETIRES_SUPPRESSION` | Dépendances retirées (suppression) (`avant.liens`) |
| `DECALAGE_SUCCESSEUR` | Décalée après une tâche qui la précède (avant, après, `apres.apres`) |
