# B3 — Seuls le DG et l'AD renomment un projet (US 3.2)

Branche : `feature/lot4-nom-projet`
Prérequis : B1, B2 fusionnées.
Jumelle frontend : `F4_nom_et_duree.md`.

## 1. La règle (décision 4.2)

> En tant que DG, je veux que le chef de projet ne puisse pas modifier le nom d'un projet, afin de
> préserver l'identification officielle du projet.

- **Peuvent renommer** : le Directeur Général (`apps.core.droits.est_dg(user)`, propriétaire
  compris) et l'administrateur de l'entreprise (rôle système `AD` : `user.role_global` ou
  `user.role.code` vaut `AD` — reprendre l'expression `is_cible_ad` déjà écrite dans
  `apps/accounts/views/collaborateur.py:715-718`, sans l'importer d'une vue : la sortir dans une
  fonction `est_administrateur(user)` de `apps/core/droits.py` à côté de `est_dg` et l'utiliser aux
  deux endroits).
- **Tous les autres** (CP, CT, DO…) : `PermissionDenied("Seuls le Directeur Général et l'administrateur de l'entreprise peuvent renommer un projet.")` (403).
- Le contrôle ne s'applique **qu'à un changement réel** : un `PATCH` qui renvoie le même nom passe.
- La **création** n'est pas concernée (celui qui crée nomme).
- Chaque renommage est journalisé : `journaliser(action=ActionAudit.MODIFICATION, type_entite="projet",
  entite_id=projet.pk, utilisateur_id=…, valeur_avant={"nom": ancien}, valeur_apres={"nom": nouveau}, …)`.

## 2. Où

`ProjetSerializer.validate` (`apps/projets/serializers/__init__.py:306+`, branche `self.instance`)
pour le refus ; la journalisation au même endroit que celle du budget (B1 §4.3).

Exposer la règle à l'écran : ajouter au payload du projet un champ calculé
`peut_renommer: bool` (vrai si l'utilisateur de la requête est DG ou AD), pour que l'écran grise
le champ sans dupliquer la règle.

## 3. Tests — `apps/projets/tests/test_nom_projet.py`

| Test | Vérifie |
|---|---|
| `test_dg_renomme` | 200, nom changé, une ligne `JournalAudit` avec ancien et nouveau nom |
| `test_ad_renomme` | 200 |
| `test_cp_ne_renomme_pas` | CP affecté : 403, message exact ; nom inchangé ; aucune ligne de journal |
| `test_meme_nom_accepte_pour_le_cp` | `PATCH` avec le nom actuel + un autre champ modifiable par le CP → 200 |
| `test_peut_renommer_dans_le_payload` | `true` pour DG et AD, `false` pour CP |

## 4. Définition de terminé

- [ ] Refus 403 hors DG / AD ; `est_administrateur` dans `core/droits.py` ; renommage journalisé ;
      `peut_renommer` exposé.
- [ ] 5 tests verts ; aucun échec nouveau ; `ruff` propre.
- [ ] Commit : `feat(projets): seuls le DG et l'administrateur renomment un projet`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
