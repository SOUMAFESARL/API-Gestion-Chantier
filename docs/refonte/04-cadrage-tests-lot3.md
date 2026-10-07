# Cadrage des tests, LOT 3 : garde unique et filtrage par projet
Règles : D-04, D-05, D-06, D-08 (et D-01 en application).
Document pour Durel et Claude. Il n'est pas donné à Gemini.

---

## 1. Quatre corrections à apporter au relevé de Gemini et à la fiche du lot 3

### C1. Le relevé change des comportements, alors que le lot 3 doit les conserver
La fiche du lot 3 dit : « le comportement actuel est conservé ; les changements de droits viennent aux lots 5 et 6 ». Or la colonne « code cible » du relevé applique déjà des codes du lot 5 :

| Vue | Relevé propose | Problème |
|---|---|---|
| `ProjetListCreateView` (POST) | `projets.creer` | c'est E-04 (lot 5). Aujourd'hui l'écriture passe par `ECRITURE` |
| `AffectationProjet*` | `projets.affecter_membres` | c'est E-05 (lot 5) |
| `Equipe*` | `projets.gerer_equipes` | c'est E-03 (lot 5) |
| `ArretChantier*` | `chantier.rediger` / `lire` | non demandé par le cahier |

Équivalent exact à conserver au lot 3 : `ECRITURE` devient `projets.ecrire`, `LECTURE` devient `projets.lire`. Les vues gardées par la seule appartenance (`MembreDuProjet` seul) n'ont aucun code aujourd'hui : voir la décision **L3-5**.

### C2. `RoleRequis` ne peut pas disparaître au lot 3
Ses usages (`billing`, `onboarding`, `tenants`) ont pour cibles des codes `administration.*` des lots 4 et 8. La sortie de lot de la fiche (« zéro `RoleRequis` ») est donc impossible. Nouvelle sortie du lot 3 : zéro `PermissionModule`, zéro `MembreDuProjet` hors de `apps/core/permissions.py`, et `RoleRequis` seulement dans ces trois apps. La disparition totale se vérifie au lot 10. Le test `test_d08_roleRequis_limite_aux_apps_des_lots_suivants` le fait.

### C3. Option A de MotifReport : la route ne change pas
Le relevé propose `/api/v1/pilotage/motifs-report/`. G-02 interdit de renommer une route existante. La route reste `/api/v1/projets/motifs-report/` ; seul le module du garde change (`pilotage`).

### C4. `pilotage` n'a qu'une permission, `pilotage.lire`
Écrire un motif (POST) n'a donc plus de code après le déplacement. Décision **L3-7**.

---

## 2. Décisions à prendre

| # | Sujet | Trou | Recommandation `[D]` |
|---|---|---|---|
| **L3-1** | Nom de la garde | non testé : aucun test ne dépend d'un nom de classe | laisser Gemini choisir ; je ne verrouille que le comportement |
| **L3-2** | Forme de l'avertissement D-05 | non donnée par le cahier | `"avertissements": ["permission_globale_sur_role_projet"]` dans le corps 200 de la création ou modification du rôle |
| **L3-3** | MotifReport | module du garde | `pilotage`, route inchangée (C3) |
| **L3-4** | `ged` | portée | `PROJET`. À écrire dans I-07 |
| **L3-5** | Vues gardées par `MembreDuProjet` seul (`equipe`, `affectation`, `arret_chantier`, `sante`, `statistiques`) | quel code exiger au lot 3 ? | **Option (b)** : code `projets.lire` partout pour ces vues, plus la règle portée/affectation. Cela conserve le comportement (tout membre affecté passe). Les codes durs (`gerer_equipes`, `affecter_membres`) arrivent au lot 5, qui verrouille alors leurs tests. Option (a) rejetée : elle fait faire le lot 5 en avance dans six vues à la fois. |
| **L3-6** | `TableauDeBordProjetsView` (module `pilotage`, donne des chiffres par projet) | D-04 dit qu'un rôle PROJET voit tout un module global ; D-01 dit qu'il ne voit que ses projets | filtrer par projets accessibles (D-06) malgré le module global : la donnée **porte** un projet. À confirmer car c'est une vraie tension du cahier. |
| **L3-7** | POST d'un motif de report | aucun code `pilotage.ecrire` | **pas de nouveau code.** Écriture réservée aux rôles à portée ENTREPRISE qui ont `pilotage.lire`. À valider : c'est une règle nouvelle. |

---

## 3. Faits encore manquants

| # | Fait | Utilisé par |
|---|---|---|
| G1 | Route réelle de `GlobalJournalReportsView` (`git grep -n "journal-reports" apps/projets/urls.py`) | `url_journal_reports()` |
| G2 | Route des lots (`/projets/{id}/lots/` ?) | `url_lots()` |
| G3 | Champs obligatoires de `Projet`, `HistoriqueDate`, `AffectationProjet` (le champ `role` est-il obligatoire ?) | fabriques |
| G4 | Tableau I-07 **final** (module → portée, aucun `A_CONFIRMER`) | tests D-04, D-05 |
| G5 | Fabriques du lot 1 : comment définir les permissions exactes d'un rôle, et corps d'un PATCH de rôle | `definir_permissions`, `corps_permissions` |
| G6 | Rôles système CP et DO : portée réelle à la fin du lot 2 (ENTREPRISE pour DO, PROJET pour CP) | cas de la matrice D-08 |

---

## 4. Dry-run obligatoire avant tout verrouillage

Je n'ai pu ni exécuter ces tests ni lire le code. Comme les marqueurs `caracterisation` décrivent des comportements qui existent déjà, ils vérifient mes hypothèses sans coûter un lot :

1. Placer les fichiers (§5) sur la branche **à la fin du lot 2**, sans poser de tag.
2. `pytest tests/acceptation/lot3 -m caracterisation -q` doit être **entièrement vert** (18 tests).
   - Un échec 404 : route fausse (G1, G2).
   - Une erreur dans `fabriques_lot3.py` : nom de champ faux (G3). Corriger, relancer.
   - Un 403 là où l'on attend un accès : soit un comportement réel que je n'avais pas vu (à discuter), soit une portée mal migrée au lot 2 (à signaler).
3. `pytest tests/acceptation/lot3 -m nouveau --deselect test_d04_d05_EN_ATTENTE -q` doit être **entièrement rouge**, pour des raisons d'assertion et non d'erreur de fabrique (10 tests).
4. Seulement alors : commit, tag `verrouille-lot3`.

---

## 5. Où placer les fichiers

```
tests/
├── fabriques_lot3.py                       adaptable (noms réels uniquement)
└── acceptation/lot3/
    ├── conftest.py                         verrouillé
    ├── test_d08_garde_unique.py            verrouillé
    ├── test_d01_d06_filtrage.py            verrouillé
    └── test_d04_d05_EN_ATTENTE.py          NE PAS DÉPOSER avant levée du bandeau
```

Tests prêts à verrouiller après dry-run : 28 sur 34. Les 6 tests D-04 et D-05 attendent G4, G5 et les décisions L3-3 et L3-7.

---

## 6. Couverture

| Règle | Tests | État |
|---|---|---|
| D-08 | matrice 8 cas × lecture et écriture, 2 tests de portée lue à chaque requête, 3 comptages statiques | prêt |
| D-01 | 5 tests (entreprise, projet, sans affectation, affectation inactive, bascule de portée) | prêt |
| D-06 | 4 tests sur le journal des reports (CA du cahier compris) | prêt, G1 à confirmer |
| D-04 | 3 tests | en attente |
| D-05 | 3 tests | en attente |
| Dashboard (L3-6) | aucun | attend la décision |
| Vues par appartenance seule (L3-5) | non testées au lot 3 | le lot 5 les verrouille |

**Non couvert, à décider** : `tiers` est-il un module global ou par projet (I-07) ? Si global, ajouter un test « rôle PROJET sans affectation lit `/tiers/` avec `tiers.lire` ». Je l'écris dès que G4 est connu.
