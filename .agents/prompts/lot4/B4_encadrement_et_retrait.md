# B4 — L'encadrement passe par les affectations ; retirer un collaborateur d'un projet (phase B)

Branche : `feature/lot4-encadrement-retrait`
Prérequis : toute la phase A fusionnée.
Jumelle frontend : `F5_encadrement.md`.

## 1. Le constat

- L'écran gère « l'équipe d'encadrement » (chef de projet, conducteurs de travaux, chefs de chantier
  avec leur **zone**, « autres membres » avec leur **fonction** : financier, ingénieur,
  documentaliste, métreur, QHSE, autre) par `POST /projets/{id}/encadrement/` et
  `DELETE /projets/{id}/encadrement/{fonction}/{utilisateur}/` — **ces routes n'existent pas**
  (404 : ajouter ou retirer quelqu'un échoue aujourd'hui).
- Le serveur porte cela dans `AffectationProjet` (`apps/projets/models/projet.py:171`) :
  `utilisateur`, `projet`, `role_projet` (`RoleProjet` : CP, CT, CC, MOA, MOE, VI —
  `apps/core/enums.py:29`), `date_debut`, `date_fin`, `est_actif`, et la contrainte
  `uq_affectation_utilisateur_projet` (**une seule affectation par personne et par projet**, sans
  condition sur `supprime_le`).
- Routes servies : `GET/POST /projets/{projet_id}/affectations/`,
  `GET/PATCH/DELETE /projets/{projet_id}/affectations/{pk}/` (`views/affectation.py`), et
  `GET /projets/{projet_id}/collaborateurs-affectables/`.
- Le projet renvoie déjà son encadrement construit depuis les affectations (lot 1, tâche 1.2 bis,
  commit `9c81f33`) : `chef_projet`, `conducteurs_travaux`, `chefs_chantier`. **Vérifier** les
  noms exacts dans `ProjetSerializer` / le sélecteur qui les construit avant d'écrire.

## 2. Ce qu'il faut faire

### 2.1 Deux champs sur `AffectationProjet` (décision 4.10)

```python
    # Le périmètre d'un chef de chantier : « Lot 02 — Gros œuvre », « Bâtiment B ». Vide : tout le chantier.
    zone = models.CharField(_("zone"), max_length=120, blank=True, default="")
    # Ce que fait un « autre membre » de l'encadrement, porté par le rôle consultant (VI).
    fonction_membre = models.CharField(
        _("fonction"), max_length=20, blank=True, default="",
        choices=[("FINANCIER", _("Financier")), ("INGENIEUR", _("Ingénieur")),
                 ("DOCUMENTALISTE", _("Documentaliste")), ("METREUR", _("Métreur")),
                 ("QHSE", _("QHSE")), ("AUTRE", _("Autre"))],
    )
```

Migration `makemigrations projets` (application tenant → `migrate_schemas`). Règles de validation
dans `AffectationProjetCreateSerializer` / `UpdateSerializer` (`serializers/affectation.py:70, 114`) :

- `zone` n'est accepté qu'avec `role_projet == "CC"` (sinon 400 `zone` :
  `"La zone ne concerne qu'un chef de chantier."`) ;
- `fonction_membre` n'est accepté qu'avec `role_projet == "VI"` ; pour `VI` sans fonction, la
  valeur par défaut est `AUTRE`.

`AffectationProjetResponseSerializer` (l. 11) renvoie aussi `zone` et `fonction_membre`.

### 2.2 L'encadrement du projet

Dans le payload du projet (là où `chefs_chantier` est construit) :

- chaque élément de `chefs_chantier` porte `zone` (chaîne vide → `null`) ;
- ajouter `autres_membres` : les affectations actives `VI`, chacune
  `{id, nom, prenom, nom_complet, …mêmes champs que les autres intervenants…, fonction: fonction_membre, affectation_id}` ;
- **chaque intervenant de l'encadrement porte son `affectation_id`** : l'écran en a besoin pour
  modifier ou retirer.

### 2.3 Le retrait (décisions du 15/10/2026)

`DELETE /api/v1/projets/{projet_id}/affectations/{pk}/` (`views/affectation.py:175`) :

| Qui | Peut retirer |
|---|---|
| DG, AD | n'importe qui, sur **tout** projet de l'entreprise |
| CP | sur les projets où il est **affecté** (c'est déjà le cas par `projets.affecter_membres` + `GardePermissionProjet`) |
| CT | sur les projets où il est **affecté comme CT** — **nouvelle règle propre au retrait** |
| Les autres | 403 |
| **Personne** | ne se retire soi-même : 403 `"Vous ne pouvez pas vous retirer vous-même d'un projet."` |

**Le CT ne reçoit pas `projets.affecter_membres`** : `tests/acceptation/lot1/test_annexe1.py:17`
fige cette permission à {DG, AD, CP}, et `test_e05_affectation.py` exige le refus du CT sur `POST`
et `PATCH`. Le droit du CT au retrait vit **dans la vue `DELETE` seule** :

```python
class PeutRetirerDuProjet(BasePermission):
    """Retirer quelqu'un d'un chantier : qui peut affecter (DG, AD, CP affecté), et le CT affecté.

    Le CT n'a pas `projets.affecter_membres` (Annexe 1, tests d'acceptation) : il ne fait pas entrer,
    mais il peut faire sortir quelqu'un de son chantier.
    """
```

`get_permissions` de `ProjetAffectationDetailView` : pour `DELETE`, `[IsAuthenticated(), PeutRetirerDuProjet()]` ;
`PATCH` et `PUT` gardent `projets.affecter_membres`. La permission objet reprend
`GardePermissionProjet.pour("projets.affecter_membres")` **ou** « affectation active `CT` de
l'utilisateur sur ce projet ».

**Effacement physique** (décision du développeur, contraire au Socle Commun, assumée pour
l'environnement de tests) : `DELETE` efface la ligne **par défaut**. Le paramètre `?hard=` est
conservé pour compatibilité, mais la valeur par défaut devient `true` ; `?hard=false` garde l'ancien
comportement (révocation). Écrire ce choix et sa raison dans la docstring de la vue. La contrainte
`uq_affectation_utilisateur_projet` étant sans condition, c'est aussi ce qui permet de réaffecter
la même personne plus tard. Vérifié le 15/10/2026 : `test_e05_affectation.py:304-307` n'exige que
`200` ou `204` après le `DELETE` du DG — le changement de défaut ne le casse pas. Les tests
**unitaires** qui lisent l'affectation révoquée après un `DELETE` sont à adapter (`?hard=false`, ou
vérifier l'absence de la ligne).

**Journal** : avant d'effacer, `journaliser(action=ActionAudit.SUPPRESSION, type_entite="affectation_projet",
entite_id=affectation.pk, utilisateur_id=request.user.pk, valeur_avant={"projet_id", "projet_reference",
"utilisateur_id", "utilisateur_email", "role_projet", "zone", "fonction_membre"},
valeur_apres={"physique": True|False}, adresse_ip=…, appareil=…)`.

Retirer le **dernier CP** reste permis côté serveur (`revoquer_affectation_projet` vide
`projet.chef_projet`) : c'est l'écran qui le fait confirmer.

Corriger au passage les `raise ValidationError({"detail": msg})` de `views/affectation.py`
(l. ~90, ~160, ~197) en `RequeteRefusee(msg)` (lot 3, B1).

## 3. Tests — `apps/projets/tests/test_encadrement_retrait.py`

| Test | Vérifie |
|---|---|
| `test_chef_chantier_avec_zone` | `POST` affectation CC + `zone` → 201 ; le projet renvoie la zone dans `chefs_chantier` |
| `test_zone_refusee_hors_cc` | CT + `zone` → 400 |
| `test_autre_membre` | VI + `fonction_membre="QHSE"` → 201 ; `autres_membres` contient la personne, fonction QHSE, `affectation_id` |
| `test_dg_retire_partout` | DG non affecté → 204 ; ligne **absente** de la base ; une ligne `JournalAudit` |
| `test_ad_retire_partout` | idem AD |
| `test_cp_retire_sur_son_projet` / `test_cp_refuse_ailleurs` | 204 / 403 |
| `test_ct_retire_sur_son_projet` | CT affecté CT → 204 |
| `test_ct_ne_retire_pas_ailleurs` | 403 |
| `test_ct_toujours_refuse_en_post_et_patch` | non-régression E-05 |
| `test_personne_ne_se_retire` | CP qui se vise → 403, message exact |
| `test_retrait_dernier_cp_vide_le_chef_projet` | `projet.chef_projet` nul ensuite |
| `test_reaffecter_apres_retrait` | retirer puis réaffecter la même personne → 201 |
| `test_hard_false_garde_la_revocation` | `?hard=false` → révoqué logiquement, pas effacé |

## 4. Définition de terminé

- [ ] `zone`, `fonction_membre` (migration) ; encadrement complet dans le projet, avec `affectation_id`.
- [ ] Règles de retrait, effacement physique par défaut, journal ; aucun test d'acceptation cassé.
- [ ] 14 tests verts ; `ruff` propre.
- [ ] Commit : `feat(projets): encadrement par les affectations, retrait d'un collaborateur journalise`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
