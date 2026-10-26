# Refonte du découpage d'un projet en arbre : plan par lots

| | |
|---|---|
| Décisions | [`decisions-v1.2.md`](decisions-v1.2.md), copie de `04_Conception/specifications_fonctionnelles/F1_gestion_projets/F1_Decoupage_Projet_decisions_v1.2.md` |
| Prototype | [`prototype_decoupage.html`](prototype_decoupage.html), à ouvrir dans un navigateur : création, projet, journal, alertes, règles en images |
| Démarrage | 26/10/2026, décision du développeur : « on démarre tout de suite » |
| Dépôts | backend `API-Gestion-Chantier` et frontend `Application-Gestion-Chantier` |

**La source des décisions est la note de `04_Conception`** ; la copie de ce dossier sert à les relire
dans les mêmes revues que le code. Les références « §N » de ce plan renvoient à cette note.

---

## 1. Ce que la refonte change

Le découpage figé **Lot → Activité** est remplacé par un **arbre d'éléments d'une seule nature**,
dont les niveaux (Phase, Ouvrage, Lot, Activité… ou tout autre) sont les libellés d'un gabarit
(§1, §2). Autour de cet arbre : modèles et listes de valeurs dynamiques (§3, §4), tableau de
démarrage (§5, §6), modification par gestes (§12), F3 généralisée (§9), dates à trois couches et
avenants (§11, §11bis), permissions exercées dans un périmètre (§13bis), journal unique à plusieurs
mains (§13ter), modes d'exécution définis par l'entreprise (§13quater), hors connexion
(§13quater-bis), alertes sans bruit (§13quater-ter), compléments du suivi (§13quinquies).

## 2. Règles de conduite du chantier

### 2.1 Branches et déploiement

Un push sur `develop` **déploie en production**, au backend comme au frontend. La refonte supprime
`Lot` et `Activite` : un lot fusionné seul dans `develop` casserait le frontend en production.

1. **Une branche d'intégration par dépôt** : `feature/decoupage-arbre`, créée depuis `develop`.
2. **Un lot = une branche** `decoupage/lot-N-<objet>`, créée depuis l'intégration et fusionnée
   dans l'intégration (`git merge --no-ff`) quand sa sortie de lot est atteinte.
3. **L'intégration ne rejoint `develop` qu'au lot 9 (bascule)**, backend et frontend ensemble.
4. L'intégration est régulièrement mise à jour depuis `develop`, pour que les corrections en cours
   de production n'y divergent pas.
5. Les pushes sur les branches de lot et d'intégration ne déploient rien ; ils se font quand le
   développeur le demande. Jamais de `--force` sur `develop` ni `main`.

### 2.2 Règles qui coûtent cher (rappel de `CLAUDE.md` et `AGENTS.md`)

- **`SHARED_APPS` ou `TENANT_APPS`** : ce qui est fourni par la plateforme (listes, modèles, modes
  plateforme) va dans le schéma `public` (`apps.catalogue`) ; tout le reste dans le schéma de
  l'entreprise (`apps.projets`, `apps.chantier`). Irrattrapable après la première migration.
- **`models/` et `views/` sont des paquets** : un fichier frère `models.py` ou `views.py` est ignoré
  sans message.
- **Une tâche Celery n'hérite pas du schéma** : `schema_context` obligatoire (recalculs, alertes,
  photographies hebdomadaires).
- **Socle commun** non négociable : suppression logique, journal d'audit immuable, formats, charte
  des messages, performance.
- **Frontend** : lire son `CLAUDE.md` ; valider par `npm run lint` et `npm run typecheck`.
- **Aucune règle ne dépend du nom d'un rôle** (§13bis) : toute garde passe par une permission du
  registre, exercée dans le périmètre.

### 2.3 Sortie de lot (définition commune)

Un lot est fusionné dans l'intégration quand :

1. ses **tests** (pytest) sont verts, avec les tests d'acceptation du lot ;
2. `ruff` est propre au backend ; `npm run lint` et `npm run typecheck` au frontend ;
3. la **documentation d'API** du lot est écrite ou mise à jour dans `docs/` ;
4. le **scénario de recette** du lot, rejoué à la main, donne le même résultat que le prototype ;
5. le tableau d'avancement du §6 est mis à jour.

## 3. Ce que touche la refonte (inventaire initial)

Relevé le 26/10/2026 ; le lot 0 le complète.

**Backend, modèles.** `projets.Lot`, `projets.Activite` (disparaissent) ; `AffectationProjet.lot` et
`.zone` (deviennent des périmètres) ; `AffectationEquipeActivite` (devient une affectation d'équipe
à un élément) ; `HistoriqueDate.lot/.activite`, `MiseAJourInline.activite`, `AlerteRetard.lot`,
`chantier.RapportJournalier.lot`, `chantier.Blocage.lot` (pointent vers un élément) ;
`catalogue.ReferentielPlateforme` et `projets.ReferentielEntreprise` (catégorie `LOT` → listes de
valeurs ; `MODE_EXECUTION` → modes dynamiques) ; `JournalChantier.saisie` et `.photographie` (JSON
fondés sur `activite_id` et `lots_travailles`).

**Backend, services et vues.** `projets/services/` : `avancement`, `sante_calculs`,
`indicateurs_temporels`, `indice_sante`, `alertes_retard`, `machine_etats`, `reprogrammation`,
`lots` (import Excel), `referentiels`, `affectations` ; `projets/views/` : `lot`, `activite`,
`planning`, `tableau_de_bord`, `statistiques`, `sante` ; `projets/permissions.py`
(`PeutRetirerDuProjet`, codé sur le rôle « CT ») ; `chantier/services/journal.py`,
`chantier/selectors/journal.py` (sections par mode de base, circuit codé « CC/CT/CP »),
`rapport_journalier.py` ; `core/registre_permissions.py`, `core/droits.py` ; commandes
`creer_tenant_demo` et `evaluer_f3_nuit`.

**Frontend.** `features/projets` (adaptateur, écrans lots et activités, planning), `features/chantier`
(`FormulaireRapport.tsx`, `brouillonLocal.ts`), tableau de bord, administration des référentiels et
des collaborateurs.

**Tests.** Les tests des lots et activités, du journal, de F3 et des alertes sont réécrits ; les
tests d'acceptation `tests/acceptation/` touchant lot ou activité sont repris au lot concerné.

## 4. Les lots

Les estimations sont en **jours de développement**, backend et frontend compris, pour un
développeur ; elles servent au chiffrage du §17.3 et seront révisées à la fin de chaque lot.

### Lot 0 — Conception et cadrage *(≈ 2 j)*

- **MLD v1.4** : tables décrites au lot 1, retrait de `lot` et `activite`, liens réorientés.
- **Erratum F3 v1.0.2** : formules 2 à 6 (§9), statuts (§10), alertes (§13quater-ter).
- **Choix technique de l'arbre** : chemin matérialisé (colonne `chemin` indexée) ou type `ltree`
  de PostgreSQL ; critère : requêtes de sous-arbre et d'ancêtres en une requête, déplacement d'une
  branche en une mise à jour.
- **Inventaire complet** (§3) et **confrontation au CDC, au MVP et au backlog** (§17.1) : rien
  d'exigé n'est perdu ; chaque écart est consigné avec sa raison.
- Création des deux branches d'intégration.
- *Sortie* : MLD et erratum dans `04_Conception`, recopiés pour revue ; inventaire relu.

### Lot 1 — Modèle de données de l'arbre *(≈ 6 j)*

- **Public** (`apps.catalogue`) : listes de valeurs plateforme et leurs valeurs ; modèles de
  découpage plateforme (niveaux, lignes, types de projet, version) ; modes d'exécution plateforme.
- **Entreprise** (`apps.projets`) : listes et valeurs d'entreprise (y compris ajoutées aux listes
  plateforme) ; modèles d'entreprise (lien `origine` vers un modèle plateforme, version d'origine) ;
  modes d'exécution d'entreprise ; **niveaux du projet** (ordre, libellé, liste, « alerter à ce
  niveau ») ; **élément** (§7, §11bis : parent, niveau, intitulé, code libre, ordre, mode de mesure,
  unité, quantités initiale / courante / réalisée, pourcentage, montants initial / courant,
  enveloppe, dates prévues, baseline v0, baseline contractuelle, dates réelles, clôture,
  suspension, actif, titulaire, mode d'exécution, type de bordereau) ; dépendances entre feuilles ;
  avenants et leurs éléments ; photographies d'avancement.
- Contraintes en base : A-1, A-2 (contrôlées par service), **A-6** (contrainte d'unicité sur le
  parent et l'intitulé normalisé, élément actif non supprimé).
- Retrait de `Lot`, `Activite`, `AffectationEquipeActivite` ; migrations ; reprise des liens des
  autres tables vers l'élément.
- `creer_tenant_demo` reconstruit sur la démonstration du prototype (4 niveaux, une récursion,
  deux jalons, enveloppes, sept collaborateurs, trois équipes).
- *Recette* : la démonstration du prototype existe en base, à l'identique.

### Lot 2 — Permissions, affectations, équipes, visibilité *(≈ 5 j)*

- **Registre** : `projets.voir_tout`, `projets.decouper`, `projets.chiffrer`, `projets.planifier`,
  `projets.prolonger`, `projets.avenants_gerer`, `projets.mesurer`, `projets.rouvrir`,
  `projets.modes_gerer`, `projets.alertes_voir`, `projets.alertes_traiter`,
  `projets.retirer_membres`, `chantier.viser` ; paquets par défaut des rôles (§13bis).
- **Affectation** : rôle propre à l'affectation (défaut : rôle de plateforme), périmètres = 0..n
  éléments ; retrait de `lot` et `zone` ; seuil personnel d'alerte.
- **Garde unique** « permission dans le périmètre » et **filtrage de lecture** (`voir_tout`, sinon
  périmètre + chemin) ; `voir_montants` appliqué aux réponses.
- Suppression des règles par nom de rôle (`PeutRetirerDuProjet`, refus « CC » sur la mise à jour
  d'avancement, destinataires d'alerte).
- **Équipes** affectées à un élément, héritées, la plus précise l'emportant.
- *Frontend* : écran des affectations (rôle, périmètres, seuil) ; boutons grisés avec la permission
  manquante.
- *Recette* : « Je suis Traoré » du prototype : il ne voit que sa branche, montants masqués.

### Lot 3 — Listes, modèles et tableau de démarrage *(≈ 6 j)*

- API des **listes de valeurs** (plateforme / entreprise, ajout en masse, `cle_comparaison`) et des
  **modèles** (création depuis le tableau, mise à jour, personnalisation liée, homonymie, type de
  projet en tête, listes plateforme seules pour un modèle plateforme).
- **Création d'un projet par le tableau** : une ligne = une feuille, regroupement par chemin, règles
  C-1 à C-7 (bloquants et avertissements), import et export Excel.
- *Frontend* : onglet de création du prototype (listes, modèles, tableau, menu déroulant par
  niveau, récapitulatif des avertissements).
- *Recette* : scénarios de l'onglet 1 du prototype.

### Lot 4 — Vue en arbre et gestes de modification *(≈ 7 j)*

- API de l'**arbre** (lecture filtrée par périmètre) et des gestes : ajouter, renommer, déplacer
  avec **aperçu des effets**, détailler (« Réalisé avant détail »), insérer un niveau, dupliquer,
  supprimer ou désactiver, suspendre, clôturer, rouvrir ; titulaire et mode hérités.
- **Modifications tracées** (motif, historique, journal d'audit) dès qu'un élément est commencé.
- *Frontend* : vue en arbre et panneau de détail du prototype (onglet 2).
- *Recette* : détailler « Murs RDC » sans changer l'avancement ; déplacer « Chaînages » et lire
  l'aperçu.

### Lot 5 — Dates, engagements, avenants, dépendances, jalons *(≈ 6 j)*

- Planification et reprogrammation (RG-11) : encadrement vers le bas, alerte et prolongation vers
  le haut, `projets.prolonger` sur le projet et les éléments commencés.
- **Trois couches de dates** ; dérive mesurée sur la baseline contractuelle ; **avenants**.
- Montant et quantité initiaux / courants ; quantité prévue refusée sous le réalisé, unité figée.
- **Dépendances** (plusieurs prédécesseurs, « décaler aussi »), **jalons**, **dates réelles**.
- *Frontend* : sections Dates, Métré, Montant, Avenant du panneau de détail.
- *Recette* : prolonger « Chaînages » comme conducteur (refusé) puis comme CP (accepté).

### Lot 6 — F3 sur l'arbre, historique, import DQE *(≈ 6 j)*

- Poids « montant connu le plus précis », physique, temporel pondéré, écart, statuts (§9, §10) ;
  « indisponible » ; indice de santé « partiel ».
- **Photographies** à chaque approbation et chaque semaine (tâche Celery, `schema_context`) ;
  tendance et fin estimée.
- **Import DQE** (aperçu puis application, rapprochement par chemin) ; dépassement signalé.
- Tableau de bord, statistiques et planning relus sur l'arbre.
- *Recette* : chiffres du prototype (Gros œuvre à 55,7 %, etc.) retrouvés à l'identique.

### Lot 7 — Journal à plusieurs mains et modes d'exécution *(≈ 9 j)*

- **Un journal par projet et par jour** ; parties par rédacteur (périmètre le plus précis) ;
  parties communes ; feuilles actives ; ligne adaptée à la feuille (quantité, pourcentage, jalon).
- **Circuit par permissions** : prête, soumission, **visa par partie**, rejet d'une partie,
  approbation et report des mesures sur la chaîne d'ancêtres ; relance et rapports attendus.
- **Modes d'exécution dynamiques** : mesure, briques, rémunération, cohérence, RG-03 sur l'arbre.
- **Hors connexion** : synchronisation par partie avec version, refus signalés, préparation en
  cache, intentions en attente.
- *Frontend* : `FormulaireRapport` refondu par parties ; `brouillonLocal` par partie.
- *Recette* : scénarios de l'onglet 3 du prototype, dont le conflit de synchronisation.

### Lot 8 — Alertes de retard *(≈ 3 j)*

- Alertes aux niveaux cochés et sur le projet ; jalon manqué ; causes classées ; déduplication
  avec escalade ; destinataires par `projets.alertes_voir` dans le périmètre et seuil personnel.
- *Frontend* : écran des alertes, réglage « Alerter à ce niveau ».
- *Recette* : scénarios de l'onglet 4 du prototype.

### Lot 9 — Bascule *(≈ 3 j)*

- Recette complète ; tests d'acceptation repris ; documentation d'API à jour.
- **Vidage de la base de production : uniquement avec l'accord explicite du développeur, demandé à
  ce moment-là** (§14).
- Fusion des deux intégrations dans `develop`, backend et frontend ensemble ; déploiement.

## 5. Ordre et dépendances

```
0 ─► 1 ─► 2 ─► 3 ─► 4 ─► 5 ─► 6 ─► 7 ─► 8 ─► 9
               └──────────────► (3 et 4 peuvent avancer en parallèle après 2)
```

- **1 avant tout** : sans élément, rien ne se branche.
- **2 tôt** : toutes les gardes des lots suivants passent par « permission dans le périmètre ».
- **5 avant 6** : le temporel se lit sur la baseline contractuelle.
- **6 avant 7** : l'approbation du journal recalcule la chaîne et photographie.
- **7 avant 8** : les causes d'une alerte lisent le journal du périmètre.

## 6. Chiffrage et échéance

| Lot | Jours |
|---|---|
| 0 | 2 |
| 1 | 6 |
| 2 | 5 |
| 3 | 6 |
| 4 | 7 |
| 5 | 6 |
| 6 | 6 |
| 7 | 9 |
| 8 | 3 |
| 9 | 3 |
| **Total** | **≈ 53 jours** |

Du 27/10 au 31/12/2026, il reste environ **46 jours ouvrés**. La refonte seule ne tient donc pas
dans l'échéance pour un développeur, sans compter les modules métier restants (A1). **À arbitrer
par la Direction** : renfort, échéance, ou périmètre de la bascule (par exemple livrer le
hors connexion et l'import DQE après la bascule).

## 7. Avancement

| Lot | Branche | État | Fusionné le |
|---|---|---|---|
| 0 | `decoupage/lot-0-conception` | à faire | |
| 1 | `decoupage/lot-1-modele` | à faire | |
| 2 | `decoupage/lot-2-permissions` | à faire | |
| 3 | `decoupage/lot-3-creation` | à faire | |
| 4 | `decoupage/lot-4-arbre` | à faire | |
| 5 | `decoupage/lot-5-dates` | à faire | |
| 6 | `decoupage/lot-6-f3` | à faire | |
| 7 | `decoupage/lot-7-journal` | à faire | |
| 8 | `decoupage/lot-8-alertes` | à faire | |
| 9 | `feature/decoupage-arbre` → `develop` | à faire | |
