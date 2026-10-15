# B5 — Équipes de chantier : membres, nature, une équipe par activité (phase B, décision 4.11)

Branche : `feature/lot4-equipes`
Prérequis : B4 fusionnée.
Jumelle frontend : `F6_equipes.md`.

## 1. Le constat

Le frontend garde les équipes **simulées même en production** (`EQUIPES_SIMULEES = routesSimulees(false)`,
`features/projets/adaptateur.ts:72`). Le serveur sert pourtant :

| Route | Vue (`apps/projets/views/equipe.py`) |
|---|---|
| `GET/POST /projets/{pk}/equipes/` | `ProjetEquipeListCreateView` (l. 42) |
| `GET/DELETE /projets/{pk}/equipes/{equipe_id}/` | `ProjetEquipeDetailView` (l. 102) |
| `GET/POST /projets/{pk}/equipes/affectations/` | `ProjetEquipeAffectationView` (l. 173) — équipe ↔ activité |
| `DELETE /projets/{pk}/equipes/affectations/{affectation_id}/` | l. 274 |
| `GET /projets/{pk}/equipes/statistiques/` | l. 302 |

Modèles (`apps/projets/models/equipe.py`) : `EquipeChantier` (`nom`, `nature`, `corps_etat`,
`chef_utilisateur`, `chef_nom`, `est_actif`), `MembreEquipeChantier` (`utilisateur` ou `nom`,
`fonction` libre, défaut `OUVRIER`), `AffectationEquipeActivite` (unique `(equipe, activite)`).

Écarts avec l'écran :

| Sujet | Serveur | Écran |
|---|---|---|
| Nature | `SOUS_TRAITANTE` | `SOUS_TRAITANT` |
| Chef | deux colonnes (`chef_utilisateur`, `chef_nom`), **pas de ligne membre** : pas d'`id` | un membre `CHEF_EQUIPE` avec `id`, qu'on peut changer de rôle |
| Fonction d'un membre | texte libre | `CHEF_EQUIPE`, `OUVRIER_QUALIFIE`, `OUVRIER`, `MANOEUVRE`, `CONDUCTEUR_ENGIN`, `APPRENTI` |
| Membres après création | **aucune route** | ajoute, change de rôle, retire |
| Équipes d'une activité | plusieurs | **une** |

**Contrat à préserver** (`tests/acceptation/lot5/test_e03_e07_ecritures_et_equipes.py:256-275`) :
la création accepte `{"nom", "nature": "INTERNE", "corps_etat", "chef": {"nom": …}, "membres": [{"utilisateur_id", "fonction": "OUVRIER"}]}`
et refuse en 400 un membre non affecté au projet ; l'affectation d'équipe répond 201
(l. 125-152). **On étend le serveur, on ne casse pas ce contrat.**

## 2. Ce qu'il faut faire

### 2.1 Modèle et données

1. `MembreEquipeChantier.fonction` : choix fermés `CHEF_EQUIPE`, `OUVRIER_QUALIFIE`, `OUVRIER`,
   `MANOEUVRE`, `CONDUCTEUR_ENGIN`, `APPRENTI` ; ajout de `prenom` (`CharField(100, blank=True)`)
   pour une personne sans compte. Contrainte : **un seul `CHEF_EQUIPE` actif par équipe**
   (`UniqueConstraint(fields=["equipe"], condition=Q(fonction="CHEF_EQUIPE", supprime_le__isnull=True), name="uq_membre_equipe_chef")`).
2. **Le chef devient un membre** : migration de données — pour chaque équipe dont
   `chef_utilisateur` ou `chef_nom` est renseigné, créer un `MembreEquipeChantier(fonction="CHEF_EQUIPE")`.
   Les colonnes `chef_utilisateur` et `chef_nom` **restent** (pas de suppression de colonne), ne
   sont plus lues, et sont tenues à jour par le service pour compatibilité (§2.3). Une fonction
   libre existante qui n'est pas dans la liste devient `OUVRIER` (la migration le compte et
   l'affiche).
3. `EquipeChantier.nature` : valeur `SOUS_TRAITANT` ; migration de données
   `SOUS_TRAITANTE → SOUS_TRAITANT`. L'**entrée** accepte encore `SOUS_TRAITANTE` comme alias
   (convertie), pour ne casser aucun client.

### 2.2 Représentation — `EquipeResponseSerializer` (`serializers/equipe.py:94`)

Garder les champs actuels **et** ajouter, pour l'écran :

```json
{
  "projet_id": "…",
  "specialite": "Gros Œuvre",            // = corps_etat
  "chef": {"id": "…", "collaborateur_id": "…" | null, "prenom": "…", "nom": "…", "role": "CHEF_EQUIPE"} | null,
  "membres": [{"id": "…", "collaborateur_id": "…" | null, "prenom": "…", "nom": "…", "role": "OUVRIER"}],
  "effectif": 5
}
```

- `membres` **exclut** le chef ; `effectif` = nombre de membres actifs, chef compris (plus le
  `1 +` fixe actuel, l. 152, qui comptait un chef même absent).
- Pour un membre avec compte : `prenom` / `nom` du compte ; sans compte : ses colonnes.
- Les anciens champs (`utilisateur_id`, `fonction`, `chef_nom`, `chef_utilisateur`) restent dans
  la réponse : un ajout ne casse personne.

### 2.3 Les routes des membres (nouvelles)

| Route | Corps | Réponse |
|---|---|---|
| `POST /projets/{pk}/equipes/{equipe_id}/membres/` | `{collaborateur_id?, prenom?, nom?, role}` (un compte **ou** un nom, comme `PersonneEquipeSerializer`) | 201, l'équipe complète |
| `PATCH /projets/{pk}/equipes/{equipe_id}/membres/{membre_id}/` | `{role}` | 200, l'équipe complète |
| `DELETE /projets/{pk}/equipes/{equipe_id}/membres/{membre_id}/` | — | 204 |

Règles :

- permission : `projets.gerer_equipes` (comme la création, `views/equipe.py:24`) ;
- un compte ajouté doit être **affecté au projet** (même contrôle que la création, l. 42-55 du
  serializer) → 400 `"Collaborateur non affecté à ce projet."` ; pas deux fois la même personne →
  400 `"Une personne ne peut apparaître deux fois."` ; 100 personnes au plus ;
- `role = "CHEF_EQUIPE"` sur un membre : l'ancien chef devient `OUVRIER_QUALIFIE` ; un chef qui
  prend un autre rôle laisse l'équipe sans chef (même règle que `changerRoleMembre`,
  `../Application-Gestion-Chantier/features/projets/regles.ts:1193-1223`) ; tenir
  `chef_utilisateur` / `chef_nom` à jour ;
- suppression **logique** des membres (ModeleBase) ;
- un membre d'une autre équipe ou d'un autre projet → 404.

La création (`POST /equipes/`) accepte aussi, en plus du format actuel, `specialite` (alias de
`corps_etat`), `chef: {collaborateur_id?, prenom?, nom?}` et `membres[].{collaborateur_id, prenom, nom, role}` ;
`role` est l'alias de `fonction`. **Le format actuel reste accepté tel quel.**

### 2.4 Une équipe par activité

`ProjetEquipeAffectationView.post` (l. 247) : si l'activité a **déjà une autre équipe**,
l'affectation existante est **remplacée** (supprimée, puis la nouvelle créée, dans une transaction) ;
réponse 201 inchangée. Même équipe : erreur actuelle conservée.

Le payload des activités (`serializers/activite.py`, sortie) gagne
`equipe_chantier: {"id", "nom", "effectif", "affectation_id"} | null`. **Attention** : le champ
`equipe_ids` existant désigne les **collaborateurs** de l'activité (M2M `equipe` vers
`Utilisateur`, l. 23, 113, 227), pas les équipes de chantier — ne pas le toucher, et l'écrire dans
un commentaire, car l'écran s'y est trompé.

## 3. Tests — `apps/projets/tests/test_equipes_membres.py` (et compléter `test_equipes_chantier_api.py`)

| Test | Vérifie |
|---|---|
| `test_creation_format_actuel_toujours_accepte` | le corps de `test_e07` (avec un membre affecté) → 201 |
| `test_creation_format_ecran` | `specialite`, `chef.collaborateur_id`, `membres[].role` → 201 ; réponse au format §2.2 |
| `test_sous_traitante_converti` | entrée `SOUS_TRAITANTE` → stockée et rendue `SOUS_TRAITANT` |
| `test_migration_chef_devient_membre` | appeler la fonction de migration : une équipe avec `chef_nom` a un membre `CHEF_EQUIPE` |
| `test_ajouter_membre` / `test_membre_non_affecte_refuse` / `test_doublon_refuse` | 201 / 400 / 400 |
| `test_nommer_chef_retrograde_l_ancien` | l'ancien chef devient `OUVRIER_QUALIFIE` ; un seul chef |
| `test_chef_qui_change_de_role_laisse_la_place` | `chef` est `null` ensuite |
| `test_retirer_membre` | 204 ; supprimé logiquement ; `effectif` décrémenté |
| `test_effectif_sans_chef` | une équipe sans chef de 3 membres a `effectif == 3` |
| `test_une_equipe_par_activite` | affecter B à une activité qui a A → 201 ; l'activité n'a plus que B ; `equipe_chantier` rendu |
| `test_membres_reserves_a_gerer_equipes` | un VI affecté → 403 |

Et lancer `pytest tests/acceptation/lot5 -q` : **zéro échec nouveau**.

## 4. Définition de terminé

- [ ] Chef = membre ; fonctions fermées ; nature `SOUS_TRAITANT` ; migrations de données réversibles.
- [ ] Routes des membres ; une équipe par activité ; `equipe_chantier` dans les activités.
- [ ] 14 tests verts ; acceptation `lot5` intacte ; `ruff` propre.
- [ ] Commit : `feat(projets): membres d'equipe, chef membre, une equipe par activite`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
