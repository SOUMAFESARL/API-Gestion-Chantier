# B1 — Cohérence des budgets projet / lot / activité ; budget du projet journalisé (US 3.4, 3.9)

Branche : `feature/lot4-budgets`
Jumelle frontend : `F1_budgets.md`.

## 1. Les user stories

> **US 3.4** — Quand le budget d'une activité dépasse celui de son lot, ou celui d'un lot celui du
> projet, l'enregistrement est refusé côté Backend et Frontend, et un message indique le plafond
> autorisé.
>
> **US 3.9** — Le chef de projet ou le DG modifie le budget d'un projet ; les contrôles de
> cohérence avec les budgets des lots restent appliqués.

## 2. Ce qui existe

- `budget_initial_montant` (BigInteger, centimes, nullable) sur `Projet`
  (`apps/projets/models/projet.py:48`), `Lot` (`models/lot.py:47`) et `Activite`
  (`models/activite.py:80`).
- Chaque serializer valide le **montant seul** (`validate_budget_initial_montant` →
  `valider_ecriture_montant`) : `serializers/__init__.py:300` (projet), `serializers/lot.py:37`,
  `serializers/activite.py:138`. **Aucune** comparaison entre niveaux.
- Le frontend contrôle aujourd'hui chaque lot **isolément** contre le projet : dix lots à 90 % du
  projet passent. La règle validée est la **somme**.

## 3. La règle (décision 4.4)

Pour un parent **qui a un budget** (non nul) :

1. **Somme des budgets des lots actifs non supprimés d'un projet ≤ budget du projet.**
2. **Somme des budgets des activités actives non supprimées d'un lot ≤ budget du lot.**
3. Un parent **ne descend pas** sous la somme de ses enfants (modifier le budget d'un projet ou
   d'un lot).
4. **Un parent sans budget (`NULL`) ne borne rien** ; un enfant sans budget compte pour **zéro**
   dans la somme.
5. Un enfant **modifié** se compare à `somme des autres enfants + sa nouvelle valeur`.

Messages (champ `budget_initial_montant`, `ValidationError`) — montants par `formater_fcfa` :

| Cas | Message |
|---|---|
| lot trop cher | `"Le budget des lots dépasserait celui du projet : il reste {disponible} sur un budget projet de {plafond}."` |
| activité trop chère | `"Le budget des activités dépasserait celui du lot : il reste {disponible} sur un budget lot de {plafond}."` |
| projet sous ses lots | `"Le budget du projet ne peut pas être inférieur à la somme de ses lots ({somme})."` |
| lot sous ses activités | `"Le budget du lot ne peut pas être inférieur à la somme de ses activités ({somme})."` |

`{disponible}` = plafond − somme des **autres** enfants (jamais négatif : `max(0, …)`).

## 4. Implémentation

### 4.1 Le service — nouveau fichier `apps/projets/services/budgets.py`

```python
def somme_budgets(qs) -> int:
    """Somme des budgets (centimes) d'un QuerySet de lots ou d'activités ; `NULL` compte zéro."""
    return qs.aggregate(total=Coalesce(Sum("budget_initial_montant"), 0))["total"]


def verifier_budget_lot(projet, montant: int | None, *, lot_exclu=None) -> None: ...
def verifier_budget_activite(lot, montant: int | None, *, activite_exclue=None) -> None: ...
def verifier_budget_projet(projet, montant: int | None) -> None: ...      # règle 3
def verifier_budget_parent_lot(lot, montant: int | None) -> None: ...     # règle 3
def verifier_budgets_lots_a_creer(projet, montants: list[int | None]) -> None: ...  # création en lot (import, création du projet avec ses lots)
```

- Les QuerySets filtrent `est_actif=True, supprime_le__isnull=True` (vérifier les noms réels des
  champs dans les modèles ; le gestionnaire `objects` exclut déjà les supprimés).
- Lever `rest_framework.exceptions.ValidationError({"budget_initial_montant": message})`.
- **Verrou** : l'appelant tient déjà `select_for_update` du projet pour la création de lots
  (`services/lots.py:29`, docstring). Pour la modification d'un lot ou d'une activité, prendre
  `Projet.objects.select_for_update().get(pk=…)` dans la transaction **avant** de calculer la somme,
  pour que deux écritures simultanées ne passent pas chacune sous le plafond.

### 4.2 Où appeler les contrôles

| Écriture | Où | Contrôle |
|---|---|---|
| Création d'un lot | là où `creer_lots` est appelé pour `POST /projets/{id}/lots/` (`views/lot.py`) et dans `creer_lots` lui-même (`services/lots.py:29`) | `verifier_budgets_lots_a_creer(projet, [d.get("budget_initial_montant") for d in donnees])` — **avant** toute création |
| Import Excel des lots | `ProjetLotImportView` → `creer_lots` | idem (passe par `creer_lots`) |
| Création d'un projet avec ses lots | `ProjetCreationSerializer` (`serializers/__init__.py:251`, champ `lots`) | idem, contre le budget **envoyé** dans la même requête |
| Modification d'un lot | `LotModificationSerializer.validate` (`serializers/lot.py:71`) | `verifier_budget_lot(projet, nouveau, lot_exclu=lot)` et `verifier_budget_parent_lot(lot, nouveau)` |
| Création d'une activité | `serializers/activite.py:150` (`validate`) | `verifier_budget_activite(lot, montant)` |
| Modification d'une activité | `serializers/activite.py:234` | `verifier_budget_activite(lot, nouveau, activite_exclue=activite)` |
| Modification du budget du projet | `ProjetSerializer.validate` avec `self.instance` (`serializers/__init__.py:306+`) | `verifier_budget_projet(projet, nouveau)` |

Ne contrôler que si `budget_initial_montant` est **dans** la requête (un `PATCH` qui ne touche pas
au budget ne doit pas échouer sur un état ancien déjà incohérent).

### 4.3 Journal du budget du projet (US 3.9)

Après l'enregistrement, si `budget_initial_montant` a changé : `journaliser(action=ActionAudit.MODIFICATION,
type_entite="projet", entite_id=projet.pk, utilisateur_id=request.user.pk,
valeur_avant={"budget_initial_montant": ancien}, valeur_apres={"budget_initial_montant": nouveau},
adresse_ip=…, appareil=…)`. Le faire dans la méthode `update` du serializer ou la vue `PATCH`
(`views/__init__.py`, `ProjetDetailView`), là où la requête est disponible. Pas de motif exigé.

## 5. Tests

Nouveau fichier `apps/projets/tests/test_budgets_coherents.py`. S'appuyer sur les fabriques
existantes des tests du module (`grep -ln "def creer_projet\|fabrique" apps/projets/tests tests/`)
ou créer projet / lots / activités directement dans le schéma `demo`, avec un DG authentifié
(`APIClient(headers={"host": "demo.localhost"})`, `force_authenticate`).

| Test | Vérifie |
|---|---|
| `test_somme_des_lots_bornee_par_le_projet` | projet 100 M, lots 60 M + 30 M ; un 3ᵉ lot de 20 M → 400, message « il reste 10 000 000 FCFA » ; 10 M → 201 |
| `test_lot_modifie_compare_aux_autres` | lots 60 M + 30 M ; passer le second à 40 M → 200 ; à 41 M → 400 |
| `test_somme_des_activites_bornee_par_le_lot` | même principe sur un lot de 10 M |
| `test_projet_ne_descend_pas_sous_ses_lots` | `PATCH` projet 80 M avec 90 M de lots → 400 « somme de ses lots (90 000 000 FCFA) » |
| `test_lot_ne_descend_pas_sous_ses_activites` | idem lot / activités |
| `test_parent_sans_budget_ne_borne_rien` | projet sans budget : lots quelconques acceptés |
| `test_enfant_sans_budget_compte_zero` | lot sans budget ne change pas la somme |
| `test_lots_supprimes_ignores` | un lot supprimé logiquement ne compte pas |
| `test_import_refuse_en_bloc` | import Excel dont la somme dépasse → 400 et **aucun** lot créé |
| `test_creation_projet_avec_lots` | `POST /projets/` avec un budget et des lots qui le dépassent → 400 |
| `test_patch_sans_budget_ne_controle_pas` | état incohérent préexistant (forcé en base) ; `PATCH` du nom → 200 |
| `test_budget_projet_journalise` | une ligne `JournalAudit` avec ancien et nouveau montants ; aucune si inchangé |
| `test_formater_fcfa` | `formater_fcfa(1_200_000_000) == "12 000 000 FCFA"` |

## 6. Pièges

- **Centimes partout** : 12 000 000 FCFA = `1_200_000_000`. Les tests le rappellent.
- **Espace insécable** : si `formater_fcfa` utilise l'espace insécable fine (U+202F) comme le
  frontend, les tests doivent comparer la même chaîne. Choisir l'espace **ordinaire** côté serveur
  (le message part en JSON et l'écran l'affiche tel quel) et le documenter.
- La règle « un parent sans budget ne borne rien » rend le **premier** budget d'un projet sans lots
  budgétés toujours acceptable : c'est voulu.

## 7. Définition de terminé

- [ ] Service `budgets.py` ; contrôles aux sept écritures du §4.2 ; budget du projet journalisé.
- [ ] 13 tests verts ; aucun échec nouveau ; `ruff` propre.
- [ ] Commit : `feat(projets): budgets coherents entre projet, lots et activites ; budget du projet journalise`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
