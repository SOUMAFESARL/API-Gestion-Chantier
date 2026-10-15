# B2 — Dates obligatoires et contenues : projet → lot → activité (US 3.6, 3.7)

Branche : `feature/lot4-dates`
Prérequis : B1 fusionnée.
Jumelle frontend : `F2_dates.md`.

## 1. Les user stories

> **US 3.6** — Un projet n'a pas de date de début et de fin renseignées ; l'utilisateur tente de
> créer ou de suivre un lot ; l'opération est refusée, et un message invite à renseigner d'abord
> les dates du projet.
>
> **US 3.7** — Même chose entre un lot et ses activités.

Décision 4.6 : « suivre » = **activer** (`PATCH /lots/{id}/activation/ {"est_actif": true}`,
`/activites/{id}/activation/`). Et les dates d'un lot sont **contenues** dans celles du projet.

## 2. Ce qui existe

- Projet : `date_debut_prevue`, `date_fin_prevue` facultatives ; contrôle « fin > début » strict
  (`serializers/__init__.py`, après l. 420 : `if debut and fin and fin <= debut`). **US 3.5 : rien à
  changer côté serveur** (le début dans le passé est accepté).
- Lot : contrôle « fin ≥ début » (`serializers/lot.py:57-60`), **aucun** contrôle par rapport au
  projet ; une modification de date passe par la reprogrammation (RG-11, l. 79-84) ; un lot ne
  peut pas exclure ses activités (l. 90-100).
- Activité : `date_debut_prevue` bornée par celle du lot si elle existe (`serializers/activite.py:191-196`) ;
  vérifier si la fin l'est aussi.
- Reprogrammation : `apps/projets/services/reprogrammation.py:25`, `reprogrammer_date_instance`
  (projet, lot, activité), appelée par `…/reprogrammer/`.

## 3. Les règles

| # | Règle | Message (`ValidationError`, champ indiqué) |
|---|---|---|
| D1 | Créer un lot (formulaire, création du projet avec ses lots, import Excel) exige les **deux** dates du projet | `lots` / `non_field_errors` : `"Renseignez d'abord les dates de début et de fin du projet : un lot se cadre dans le calendrier du projet."` |
| D2 | Activer un lot exige les deux dates du projet | idem, via `RequeteRefusee` (400) |
| D3 | Créer ou activer une activité exige les **deux** dates de son lot | `"Renseignez d'abord les dates de début et de fin du lot : une activité se cadre dans le calendrier du lot."` |
| D4 | Les dates d'un lot, si elles sont données, sont dans `[début projet, fin projet]` | `date_debut_prevue` : `"Le lot ne peut pas commencer avant le début du projet ({date})."` ; `date_fin_prevue` : `"Le lot ne peut pas finir après la fin du projet ({date})."` |
| D5 | Les dates d'une activité, si elles sont données, sont dans celles du lot (début **et** fin) | `"L'activité ne peut pas commencer avant le début du lot ({date})."` / `"L'activité ne peut pas finir après la fin du lot ({date})."` (reprendre le texte existant de l. 194-196 s'il est déjà ainsi) |
| D6 | Reprogrammer un **lot** hors des dates du projet est refusé ; reprogrammer une **activité** hors de son lot aussi | mêmes messages que D4 / D5, suivis de `" Reprogrammez d'abord le projet."` ou `" Reprogrammez d'abord le lot."` |
| D7 | Reprogrammer un **projet** pour qu'il ne contienne plus un de ses lots est refusé ; idem lot / activités | `"Le lot {code} sortirait du calendrier du projet : reprogrammez-le d'abord."` / `"L'activité {libelle} sortirait du calendrier du lot : reprogrammez-la d'abord."` |

Dates au format `JJ/MM/AAAA` dans les messages (`date.strftime("%d/%m/%Y")`).

D2 et D3 (activation) : ne s'appliquent qu'au passage à `est_actif=True`. Désactiver reste possible.

## 4. Implémentation

1. Un module `apps/projets/services/calendrier.py` avec des fonctions pures, testables seules :
   `exiger_dates_projet(projet)`, `exiger_dates_lot(lot)`, `verifier_lot_dans_projet(projet, debut, fin)`,
   `verifier_activite_dans_lot(lot, debut, fin)`, `verifier_enfants_contenus(parent, debut, fin)`.
2. Les appeler :
   - `creer_lots` (`services/lots.py:29`) : D1 puis D4 pour chaque ligne **avant** toute création ;
   - `ProjetCreationSerializer` (lots à la création) : D1 contre les dates envoyées dans la même
     requête ; D4 idem ;
   - `LotCreationSerializer` / `LotModificationSerializer` : D4 ;
   - `LotActivationView.patch` (`views/lot.py`, ~l. 307) et la vue d'activation d'activité : D2 / D3 ;
   - création d'activité (`serializers/activite.py:150`) : D3, D5 ;
   - modification d'activité (l. 234) : D5 ;
   - `reprogrammer_date_instance` : D6 pour un lot / une activité, D7 pour un projet / un lot.
3. Les erreurs se **lèvent** ; aucune `Response` construite à la main.

## 5. Données existantes

Des lots ou activités peuvent déjà violer D4 / D5 en base locale (et en production). **Ne rien
migrer** : les règles ne s'appliquent qu'aux écritures nouvelles. Ajouter une commande de relevé
`python manage.py relever_dates_hors_cadre [--schema demo]` qui **liste** (sans rien modifier) les
lots hors projet et les activités hors lot, par schéma. Le compte rendu donne son résultat en local.

## 6. Tests

`apps/projets/tests/test_calendrier.py` :

| Test | Vérifie |
|---|---|
| `test_lot_refuse_sans_dates_projet` | `POST /projets/{id}/lots/` → 400, message D1 |
| `test_import_refuse_sans_dates_projet` | import Excel → 400 D1, aucun lot créé |
| `test_creation_projet_avec_lots_sans_dates` | → 400 D1 |
| `test_activation_lot_refusee_sans_dates_projet` | `PATCH …/activation/ {"est_actif": true}` → 400 ; `false` → 200 |
| `test_activite_refusee_sans_dates_lot` | → 400 D3 |
| `test_lot_hors_projet_refuse` | début avant / fin après le projet → 400 D4 sur le bon champ |
| `test_activite_hors_lot_refusee` | début avant / fin après → 400 D5 |
| `test_reprogrammer_lot_hors_projet` | → 400 D6 « Reprogrammez d'abord le projet. » |
| `test_reprogrammer_projet_qui_exclut_un_lot` | → 400 D7 avec le code du lot |
| `test_debut_dans_le_passe_accepte` | projet débutant il y a 6 mois → 201/200 (US 3.5, non-régression) |
| `test_fin_egale_debut_refusee_pour_un_projet` | → 400 (non-régression) |
| `test_commande_releve` | la commande liste un lot forcé hors cadre, sans le modifier |

## 7. Pièges

- **Les tests existants** créent peut-être des lots sur des projets sans dates (fabriques). Les
  adapter en donnant des dates au projet, **jamais** en affaiblissant la règle. Vérifier
  particulièrement `tests/fabriques_lot5.py` et les tests d'acceptation `lot5` : si une fabrique
  d'acceptation crée un lot sans dates de projet, **s'arrêter et le signaler** (on ne modifie pas un
  test d'acceptation sans accord).
- Un lot sans dates reste permis (D4 ne s'applique qu'aux dates données) ; c'est l'**activité**
  qui exige les dates du lot.

## 8. Définition de terminé

- [ ] Règles D1 à D7 ; commande de relevé ; aucune donnée modifiée.
- [ ] 12 tests verts ; aucun échec nouveau (acceptation comprise) ; `ruff` propre.
- [ ] Commit : `feat(projets): dates obligatoires et contenues du projet au lot et a l'activite`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
