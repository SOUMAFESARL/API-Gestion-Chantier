# Lot 4 — Gestion de projet : prompts pour l'agent d'implémentation (backend)

Rédigé le 15/10/2026 par l'agent de cadrage (Claude), après validation du développeur. **Toutes les
décisions sont prises** : en cas de doute, s'arrêter et demander, ne jamais inventer une règle.

Jumeau frontend : `../Application-Gestion-Chantier/.agents/prompts/lot4/`.

> **Prérequis : le lot 3 est entièrement fusionné dans `develop` des deux dépôts** (B1 du lot 3
> change le format des erreurs des vues ; ce lot s'appuie dessus). Vérifier
> `git log --oneline develop | grep lot3` dans les deux dépôts.

---

## 1. Deux phases, enchaînées sans arrêt

Décision du développeur : un seul lot, deux phases, **sans point de relecture entre elles**. La
phase A porte les user stories du DG (Sprint Review du 10/10/2026), la phase B l'alignement des
équipes et de l'encadrement. Passer de A à B dès que la dernière tâche A est fusionnée.

| Ordre | Tâche | Dépôt | Objet |
|---|---|---|---|
| **Phase A** | | | |
| 1 | `B1_budgets.md` | backend | US 3.4, 3.9 — cohérence des budgets, budget du projet journalisé |
| 2 | `F1_budgets.md` | frontend | US 3.3, 3.4, 3.9 |
| 3 | `B2_dates.md` | backend | US 3.6, 3.7 — dates obligatoires et contenues |
| 4 | `F2_dates.md` | frontend | US 3.5, 3.6, 3.7 |
| 5 | `F3_reprogrammation.md` | frontend | US 3.8 — projet, lot, activité, historique |
| 6 | `B3_nom_projet.md` | backend | US 3.2 |
| 7 | `F4_nom_et_duree.md` | frontend | US 3.2, vérification US 3.1 |
| **Phase B** | | | |
| 8 | `B4_encadrement_et_retrait.md` | backend | Encadrement par les affectations ; retrait d'un collaborateur |
| 9 | `F5_encadrement.md` | frontend | Encadrement réel ; retrait ; confirmation du dernier CP |
| 10 | `B5_equipes.md` | backend | Membres d'équipe, nature, une équipe par activité |
| 11 | `F6_equipes.md` | frontend | Équipes réelles, fin de la simulation |
| 12 | `B6_openapi.md` | backend | Les 18 routes absentes du schéma OpenAPI |
| 13 | `F7_sante_et_import.md` | frontend | Santé du projet ; import des lots par le serveur |
| 14 | `F8_cloture.md` | frontend | Plan d'alignement à jour |

`PROMPT_DE_LANCEMENT.md` donne le message à coller dans Antigravity.

---

## 2. Règles communes

**Identiques aux lots 2 et 3** : relire `../lot2/README.md` §2. En résumé : branche
`feature/lot4-<nom>` partie de `develop` à jour ; `git add <fichiers>` seulement ; fusion `--no-ff` ;
**jamais `git push`** ; relevé des échecs de `pytest apps/ -q` et `pytest tests/acceptation -q`
sur `develop` **avant** chaque tâche, aucun échec nouveau après ; `ruff` propre ; messages
d'erreur en français **mot pour mot**.

Règles de ce dépôt qui comptent dans ce lot :

- `apps.projets` est une application **tenant** : ses migrations se créent par `makemigrations
  projets` et s'appliquent par `migrate_schemas` (tous les schémas). Toute migration de données
  passe par `RunPython` avec une fonction inverse, et n'importe pas le code applicatif.
- **Les montants sont des entiers de centimes de FCFA** (`apps/core/fields.py`, décision D5).
  Un message qui cite un montant l'affiche en francs, groupés par espaces : « 12 000 000 FCFA ».
  Écrire une fonction `formater_fcfa(centimes: int) -> str` dans `apps/core/fields.py` si aucune
  n'existe (`grep -rn "def formater" apps/core`), et l'utiliser partout.
- Les montants sont **masqués** à qui n'a pas `projets.voir_montants`
  (`apps/core/purger_montants.py`, `valider_ecriture_montant`). Un message d'erreur qui cite un
  plafond ne part que vers quelqu'un qui peut écrire le montant : c'est déjà le cas, ne pas
  l'affaiblir.
- Journal d'audit : `apps.audit.services.journaliser(...)` (exemple :
  `apps/accounts/services/invitations.py:232-245`).
- Les erreurs se **lèvent** (`ValidationError`, `PermissionDenied`, `ErreurConflit`,
  `RequeteRefusee` du lot 3) ; jamais `return Response({"detail": …})` (leçon du lot 3, B1).
- **Tests d'acceptation de la CI à ne pas casser** (`tests/acceptation/lot5/`) :
  - `test_e05_affectation.py` — un CT reçoit 403 sur `POST` et `PATCH` d'une affectation, un DO
    sur `DELETE` ; le DG non affecté révoque ;
  - `tests/acceptation/lot1/test_annexe1.py:17` — `projets.affecter_membres` = {DG, AD, CP}, **le
    CT ne l'a pas** ;
  - `test_e03_e07_ecritures_et_equipes.py` — création d'équipe au format actuel (`corps_etat`,
    `chef: {"nom": …}`, `membres: [{"utilisateur_id", "fonction"}]`), affectation d'équipe en 201.
  Une tâche qui casserait l'un d'eux s'arrête et le signale.

---

## 3. Décisions validées par le développeur (14 et 15/10/2026)

| # | Décision |
|---|---|
| 4.0 | Un lot, deux phases (A puis B), enchaînées sans point d'arrêt |
| 4.1 | US 3.1 durée : déjà affichée ; vérification à l'écran, PDF compris |
| 4.2 | US 3.2 : seuls le **DG et l'AD** renomment un projet ; refus 403 pour les autres ; renommage journalisé |
| 4.3 | US 3.3 : budget d'activité dans le tableau des activités et son export |
| 4.4 | US 3.4 : **somme** des budgets des lots ≤ budget du projet ; **somme** des budgets des activités d'un lot ≤ budget du lot ; un parent ne descend pas sous la somme de ses enfants ; le message donne le disponible ; **un parent sans budget ne borne rien** ; serveur **et** écran |
| 4.5 | US 3.5 : début dans le passé accepté (déjà) ; fin **strictement** après le début pour le projet |
| 4.6 | US 3.6 / 3.7 : pas de lot (création, import, activation) sans les deux dates du projet ; pas d'activité (création, activation) sans les deux dates de son lot ; **les dates d'un lot sont contenues dans celles du projet** (comme celles d'une activité dans son lot) |
| 4.7 | US 3.8 : reprogrammation branchée (motif + justification) pour le **projet, le lot et l'activité**, historique affiché |
| 4.8 | US 3.9 : budget du projet modifiable, borné par la somme des lots, **journalisé** (ancien / nouveau), sans motif |
| 4.10 | Encadrement : aligné sur les affectations ; `zone` (chef de chantier) et `fonction_membre` (« autre membre », rôle VI) ajoutés au serveur ; le projet expose son encadrement par fonction |
| 4.11 | Équipes : routes des membres côté serveur, nature `SOUS_TRAITANT`, fin de la simulation |
| Retrait | Retirer un collaborateur **d'un projet** : DG et AD sur tous les projets ; CP et CT sur les projets où ils sont affectés ; **personne ne se retire soi-même** ; **effacement physique** de l'affectation (choix assumé pour l'environnement de tests, contre le Socle Commun) ; chaque retrait journalisé ; l'écran confirme explicitement le retrait du **dernier CP** |

Décisions de cadrage prises par Claude sur ce que la discussion n'a pas tranché, à respecter :

- **Une personne tient une seule fonction par projet** : c'est la contrainte du serveur
  (`uq_affectation_utilisateur_projet`). L'écran cesse d'en proposer plusieurs.
- **Une équipe par activité** : l'écran le suppose à 41 endroits ; le serveur l'adopte (une
  nouvelle affectation remplace la précédente).
- **Non branchés dans ce lot, par décision** : l'activation / désactivation d'un lot ou d'une
  activité (aucun écran ne la demande), le détail et la modification d'un tiers (l'écran Tiers
  est un squelette « à construire » : c'est un module à part), le référentiel des villes (le
  frontend embarque une liste générée depuis le même fichier serveur), les statistiques d'équipes
  (l'écran les calcule).

---

## 4. Fin du lot

Compte rendu par tâche, puis **s'arrêter**. Relecture par Claude, puis push par le développeur.
