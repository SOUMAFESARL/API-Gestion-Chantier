# B5 — Suppression définitive d'une entreprise : motif, suspension préalable, sauvegarde (tâche 2.4, US 1.1)

Branche : `feature/lot2-suppression-entreprise`
Prérequis : B1 à B4 fusionnées.
Jumelle frontend : `F7_suppression_entreprise.md`.

> **C'est l'action la plus dangereuse du produit.** Elle détruit un schéma PostgreSQL entier.
> Chaque contrôle de ce fichier est obligatoire, **dans l'ordre donné**. En cas de doute :
> s'arrêter et demander.

## 1. Contexte — ce qui existe

- `GET /api/v1/admins/clients/{id}/suppression/apercu/` — `ApercuSuppressionClientView`
  (`apps/platform_admin/views/suppression.py:43`) : renvoie `slug`, `raison_sociale`,
  `protegee`, `nb_utilisateurs`, `nb_projets`, `nb_paiements`, `adresses`, `dirigeants`,
  `suppression_activee`.
- `POST /api/v1/admins/clients/{id}/supprimer-definitivement/` —
  `SupprimerClientDefinitivementView` (l. 55) : superviseur, refus `public`/`demo`
  (`est_protegee`), interrupteur `SUPPRESSION_ENTREPRISE_ACTIVEE`, nom technique retapé
  (`confirmation`), puis `supprimer_definitivement(entreprise)`
  (`apps/tenants/services/suppression_definitive.py:122`) et une ligne `JournalPlateforme`
  `SUPPRESSION_DEFINITIVE_ENTREPRISE`.
- Tests : `apps/platform_admin/tests/test_suppression_definitive.py` (2 tests, à garder verts).

**Ce qui manque** (décisions 2.4 a–d du `README.md`) :

1. aucun motif ;
2. une entreprise **active** peut être supprimée d'un coup ;
3. **aucune sauvegarde** : une erreur de clic est irréversible ;
4. le DG n'est pas prévenu ;
5. l'interrupteur est **allumé par défaut** (`config/settings/base.py:58`,
   `default=True`, et `.env.example:120` `=True`) — contraire à la décision « coupée en
   production tant que le développeur ne l'allume pas ».

## 2. Contrat d'API cible

### 2.1 Aperçu — enrichi

`GET /api/v1/admins/clients/{id}/suppression/apercu/` ajoute trois champs :

```json
{
  "...": "champs actuels inchangés",
  "suspendue": true,
  "motif_longueur_min": 20,
  "sauvegarde_conservee_jours": 30
}
```

`suspendue` = `entreprise.statut == StatutEntreprise.SUSPENDU`. Ouvert au SUPPORT (lecture).

### 2.2 Suppression — nouveau corps

```
POST /api/v1/admins/clients/{id}/supprimer-definitivement/
{
  "confirmation": "nom_technique_de_l_entreprise",
  "motif": "Demande écrite du client du 12/10/2026, contrat résilié, données exportées."
}
```

Contrôles, **dans cet ordre exact** (le premier qui échoue répond) :

| # | Contrôle | Statut | `erreur.code` | `erreur.message` |
|---|---|---|---|---|
| 1 | `exiger_superviseur` | 403 | `permission_refusee` (code standard du gestionnaire) | message de B1 |
| 2 | Entreprise introuvable / `public` | 404 | standard | standard |
| 3 | `est_protegee` (`public`, `demo`) | 403 | `entreprise_protegee` | `"Cette entreprise est protégée : elle ne peut pas être supprimée."` (inchangé) |
| 4 | Interrupteur éteint | 403 | `suppression_desactivee` | `"La suppression définitive est désactivée sur ce serveur."` (inchangé) |
| 5 | Entreprise non suspendue | 409 | `entreprise_non_suspendue` | `"Suspendez d'abord l'entreprise : seule une entreprise suspendue peut être supprimée."` |
| 6 | Motif < 20 caractères (après `strip`) | 400 | `motif_invalide` | `"Le motif doit contenir au moins 20 caractères."` |
| 7 | Confirmation ≠ nom technique | 400 | `confirmation_invalide` | `"Le nom saisi ne correspond pas à celui de l'entreprise."` (inchangé) |
| 8 | Sauvegarde impossible | 503 | `sauvegarde_impossible` | `"La sauvegarde de l'entreprise a échoué : la suppression n'a pas été faite. Prévenez l'équipe technique."` |

Toutes ces erreurs passent par le helper `_erreur(request, code, message, statut)` déjà présent
(`views/suppression.py:23`), pour garder le même format.

**Aucune** de ces erreurs n'écrit au journal, n'envoie de courriel, ni ne crée de fichier
de sauvegarde (en cas d'échec 8, le fichier partiel est effacé).

Réponse 200 — inchangée, plus le nom du fichier de sauvegarde :

```json
{"statut": "supprimee", "id": "…", "slug": "…", "sauvegarde": "acme_20261014_101500.dump", "...": "rapport"}
```

## 3. Implémentation

### 3.1 L'interrupteur éteint par défaut

- `config/settings/base.py:58` : `default=False`.
- `.env.example:120` : `SUPPRESSION_ENTREPRISE_ACTIVEE=False`, avec au-dessus un commentaire :
  `# Suppression définitive d'une entreprise (back-office). Laisser à False en production tant que la Direction ne l'a pas décidé.`
- **Ne pas toucher au `.env` local** du développeur (fichier non versionné). Le signaler dans le
  compte rendu : pour tester à l'écran en local, il faudra mettre `True` dans `.env`.
- Les deux tests existants posent `settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True` eux-mêmes :
  ils restent verts.

Ajouter dans `config/settings/base.py`, à côté :

```python
# Sauvegarde d'un schéma avant sa suppression définitive (tâche 2.4).
SAUVEGARDES_SUPPRESSION_DIR = config(
    "SAUVEGARDES_SUPPRESSION_DIR", default=str(BASE_DIR / "sauvegardes" / "suppressions")
)
SAUVEGARDES_SUPPRESSION_JOURS = config("SAUVEGARDES_SUPPRESSION_JOURS", default=30, cast=int)
PG_DUMP_CHEMIN = config("PG_DUMP_CHEMIN", default="pg_dump")
```

(Vérifier le nom de la variable de base du projet — `BASE_DIR` ou autre — en lisant le haut de
`base.py`.) Les reporter dans `.env.example` avec un commentaire. Ajouter `sauvegardes/` à
`.gitignore`.

### 3.2 Le service de sauvegarde — nouveau fichier `apps/tenants/services/sauvegarde_schema.py`

```python
"""Sauvegarde d'un schéma d'entreprise avant sa suppression définitive.

Une suppression sans sauvegarde transforme une erreur de clic en perte définitive : la
suppression est refusée si la sauvegarde n'a pas abouti.
"""

class SauvegardeImpossible(Exception):
    """`pg_dump` a échoué, est introuvable, ou a produit un fichier vide."""


NOM_SCHEMA_SUR = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def sauvegarder_schema(entreprise: Entreprise, *, complement: dict) -> Path:
    """Écrit `<schema>_<AAAAMMJJ_HHMMSS>.dump` (format custom de pg_dump, restaurable par
    pg_restore) et, à côté, `<même nom>.json` : les lignes du schéma public qui la concernent
    et que le dump du schéma ne contient pas. Retourne le chemin du `.dump`."""
```

Étapes :

1. **Valider le nom du schéma** avec `NOM_SCHEMA_SUR` ; sinon `SauvegardeImpossible`. (Le nom
   finit dans une ligne de commande : on ne fait confiance à rien, cf. le piège d'injection du
   nom de schéma relevé au Sprint 1 dans `CLAUDE.md`.)
2. `dossier = Path(settings.SAUVEGARDES_SUPPRESSION_DIR)`, `mkdir(parents=True, exist_ok=True)`.
3. `horodatage = timezone.localtime().strftime("%Y%m%d_%H%M%S")` ;
   `chemin = dossier / f"{schema}_{horodatage}.dump"`.
4. Commande — **une liste, jamais `shell=True`** :
   ```python
   base = settings.DATABASES["default"]
   commande = [
       settings.PG_DUMP_CHEMIN, "--format=custom", "--no-owner",
       f"--schema={schema}", f"--file={chemin}",
       f"--host={base['HOST']}", f"--port={base['PORT']}", f"--username={base['USER']}",
       base["NAME"],
   ]
   env = {**os.environ, "PGPASSWORD": base["PASSWORD"] or ""}
   subprocess.run(commande, env=env, check=True, capture_output=True, timeout=600)
   ```
5. Toute exception (`FileNotFoundError`, `subprocess.CalledProcessError`,
   `subprocess.TimeoutExpired`, `OSError`) ou un fichier absent / de taille 0 : effacer
   `chemin` s'il existe (`missing_ok=True`), journaliser l'erreur avec `logger.error` (**sans**
   le mot de passe ; `stderr` décodé tronqué à 500 caractères), lever `SauvegardeImpossible`.
6. Écrire le JSON compagnon (`chemin.with_suffix(".json")`, UTF-8, `ensure_ascii=False`,
   `indent=2`, `default=str`) : `{"entreprise": {...champs de Entreprise...}, "abonnements":
   [...values() des abonnements...], "complement": complement, "sauvegarde_le": iso}`. Si
   l'écriture du JSON échoue : effacer le `.dump` et lever `SauvegardeImpossible`.
7. Retourner `chemin`.

### 3.3 La purge à 30 jours — nouvelle commande

`apps/tenants/management/commands/purger_sauvegardes_suppression.py` :

- `--jours` (défaut `settings.SAUVEGARDES_SUPPRESSION_JOURS`), `--appliquer` (sans lui : la
  commande **décrit** ce qu'elle supprimerait, sans rien supprimer — même convention que
  `retirer_dg_des_chantiers`).
- Supprime les `*.dump` et `*.json` du dossier dont `st_mtime` est plus ancien que `--jours`.
- Affiche chaque fichier et un total.

À planifier plus tard (cron cPanel) : le noter dans le compte rendu, ne pas le configurer.

### 3.4 La vue — `apps/platform_admin/views/suppression.py`

Réécrire `SupprimerClientDefinitivementView.post` dans l'ordre du tableau §2.2 :

```python
    def post(self, request, client_id):
        exiger_superviseur(request)
        entreprise = _entreprise_cliente(client_id)
        if est_protegee(entreprise): ...                       # 3
        if not settings.SUPPRESSION_ENTREPRISE_ACTIVEE: ...    # 4
        if entreprise.statut != StatutEntreprise.SUSPENDU: ... # 5 → 409
        motif = str(request.data.get("motif", "")).strip()
        if len(motif) < MOTIF_LONGUEUR_MIN: ...                # 6 → 400
        saisie = ...                                           # 7 (inchangé)

        apercu = apercu_suppression(entreprise)
        try:
            sauvegarde = sauvegarder_schema(entreprise, complement=apercu)
        except SauvegardeImpossible:
            return _erreur(request, "sauvegarde_impossible", "...", 503)   # 8

        _prevenir_dg_avant_suppression(entreprise)             # §3.5

        identifiant, schema, raison = ...
        rapport = supprimer_definitivement(entreprise)
        journal: detail = {... champs actuels ..., "motif": motif, "sauvegarde": sauvegarde.name}
        return Response({"statut": "supprimee", "id": ..., "slug": ..., "sauvegarde": sauvegarde.name, **rapport})
```

Constantes en tête du module : `MOTIF_LONGUEUR_MIN = 20`. L'aperçu (`ApercuSuppressionClientView.get`)
ajoute `suspendue`, `motif_longueur_min` et `sauvegarde_conservee_jours` (§2.1).

Remplacer l'import `from apps.platform_admin.views.parametres import _exiger_superviseur` par
`from apps.platform_admin.permissions import exiger_superviseur`.

### 3.5 Le courriel au DG, avant la suppression

Le schéma va disparaître : on ne peut pas compter sur `transaction.on_commit` (l'envoi aurait
lieu quand le DG n'existe plus, et `trouver_dg_actif_entreprise` lit son schéma). Donc :

```python
def _prevenir_dg_avant_suppression(entreprise: Entreprise) -> None:
    """Le DG apprend la suppression avant qu'elle ait lieu — sans le motif, interne à l'éditeur."""
    dg = trouver_dg_actif_entreprise(entreprise)
    if not dg or not dg.email:
        logger.info("Suppression de %s : aucun DG actif à prévenir.", entreprise.schema_name)
        return
    envoye = envoyer(
        "notification_plateforme",
        SUJET_SUPPRESSION_ENTREPRISE,
        dg.email,
        {"sujet": SUJET_SUPPRESSION_ENTREPRISE, "message": message, "raison_sociale": entreprise.raison_sociale},
    )
    if not envoye:
        logger.error("Suppression de %s : le courriel au DG n'est pas parti.", entreprise.schema_name)
```

- `SUJET_SUPPRESSION_ENTREPRISE = "Suppression de votre espace CCD Digital"`, à déclarer dans
  `apps/platform_admin/services/notifications.py` à côté des deux autres sujets.
- `message` :
  ```
  Bonjour,

  L'espace de {raison_sociale} sur CCD Digital va être supprimé définitivement par
  l'administration de la plateforme. Les comptes de vos collaborateurs et les données de vos
  projets ne seront plus accessibles.

  Pour toute question, répondez à ce courriel.
  ```
- **Un courriel qui ne part pas ne bloque pas la suppression** (la décision ne porte que sur la
  sauvegarde) : on le journalise et on continue.
- Imports : `envoyer` depuis `apps.core.emails`, `trouver_dg_actif_entreprise` depuis
  `apps.platform_admin.services.notifications`.

## 4. Tests

Compléter `apps/platform_admin/tests/test_suppression_definitive.py` (garder ses helpers
`_agent`, `_entreprise_de_test`, `_schema_existe`).

**La sauvegarde est simulée dans les tests** (pas de `pg_dump` sur la CI ni forcément sur la
machine) : `monkeypatch.setattr("apps.platform_admin.views.suppression.sauvegarder_schema", faux)`
où `faux` écrit un petit fichier dans `tmp_path` et le retourne. Et
`settings.SAUVEGARDES_SUPPRESSION_DIR = str(tmp_path)`.

Les deux tests existants doivent être **adaptés** : l'entreprise de test doit être suspendue
(`ent.statut = StatutEntreprise.SUSPENDU; ent.save(update_fields=["statut"])` dans
`_entreprise_de_test`), le corps doit porter un `motif` de 20 caractères et plus, et la
sauvegarde doit être simulée.

| Test | Vérifie |
|---|---|
| `test_entreprise_active_non_supprimable` | entreprise `ACTIF` → 409 `entreprise_non_suspendue` ; schéma toujours là ; aucune sauvegarde appelée |
| `test_motif_trop_court_refuse` | `motif` de 19 caractères → 400 `motif_invalide` ; schéma toujours là |
| `test_sauvegarde_en_echec_bloque_la_suppression` | `faux` lève `SauvegardeImpossible` → 503 `sauvegarde_impossible` ; **schéma toujours là** ; aucune ligne `SUPPRESSION_DEFINITIVE_ENTREPRISE` ; aucun courriel |
| `test_suppression_journalise_motif_et_sauvegarde` | 200 ; `detail.motif` et `detail.sauvegarde` présents au journal ; la réponse porte `sauvegarde` |
| `test_dg_prevenu_avant_suppression_sans_motif` | `EMAIL_BACKEND` locmem ; un courriel au DG dans `mail.outbox`, sujet `SUJET_SUPPRESSION_ENTREPRISE`, le motif absent du corps |
| `test_interrupteur_eteint_par_defaut` | lire le texte de `config/settings/base.py` (`Path(settings.BASE_DIR) / "config" / "settings" / "base.py"`, adapter au nom réel de la variable) et vérifier par expression régulière que la ligne `SUPPRESSION_ENTREPRISE_ACTIVEE = config(` contient `default=False`. (La valeur effective dépend du `.env` local : on teste le défaut écrit, pas la valeur courante.) |
| `test_apercu_dit_suspendue_et_regles` | l'aperçu porte `suspendue`, `motif_longueur_min == 20`, `sauvegarde_conservee_jours == 30` |
| `test_ordre_des_controles` | entreprise **active** et motif court : la réponse est le 409 (contrôle 5), pas le 400 (contrôle 6) |

Tests du service, nouveau fichier `apps/tenants/tests/test_sauvegarde_schema.py`
(créer `apps/tenants/tests/__init__.py` s'il n'existe pas) :

| Test | Vérifie |
|---|---|
| `test_nom_de_schema_dangereux_refuse` | entreprise factice (objet simple avec `schema_name = "a; DROP SCHEMA public"`) → `SauvegardeImpossible`, `subprocess.run` **jamais appelé** |
| `test_pg_dump_introuvable` | `settings.PG_DUMP_CHEMIN = "pg_dump_inexistant_xyz"` → `SauvegardeImpossible`, aucun fichier laissé |
| `test_fichier_vide_refuse` | `subprocess.run` simulé qui crée un fichier vide → `SauvegardeImpossible`, fichier effacé |
| `test_commande_sans_shell_et_sans_mot_de_passe_en_argument` | `subprocess.run` simulé qui capture ses arguments : `shell` absent ou `False` ; le mot de passe n'apparaît dans **aucun** argument, seulement dans `env["PGPASSWORD"]` |
| `test_json_compagnon_ecrit` | après succès simulé, le `.json` existe et contient `entreprise.schema_name` |
| `test_purge_decrit_sans_appliquer` | fichiers vieux de 31 jours (`os.utime`) : sans `--appliquer` ils restent ; avec, ils partent ; un fichier de 2 jours reste |

## 5. Pièges

- **Le contrôle 5 avant le motif** : un superviseur qui n'a pas suspendu doit lire la vraie
  raison (« suspendez d'abord »), pas une remarque sur la longueur de son motif.
- **`pg_dump` en production (cPanel)** : il n'est peut-être pas installé, ou pas sur le `PATH`.
  C'est **voulu** que la suppression échoue alors (503) : mieux vaut ne pas supprimer que
  supprimer sans filet. Le noter dans le compte rendu : avant d'allumer l'interrupteur en
  production, vérifier `PG_DUMP_CHEMIN` sur le serveur.
- **Version de `pg_dump`** : elle doit être ≥ à celle du serveur PostgreSQL (16). Pas de test
  à écrire, mais à noter dans le compte rendu.
- **Ne pas mettre la sauvegarde dans `supprimer_definitivement`** : ce service est aussi appelé
  ailleurs (commandes de nettoyage) ; la règle « pas de sauvegarde, pas de suppression » est une
  règle du back-office, posée dans la vue.

## 6. Définition de terminé

- [ ] Interrupteur éteint par défaut ; `.env.example` et `.gitignore` à jour.
- [ ] Contrôles 1 à 8 dans l'ordre ; sauvegarde bloquante ; DG prévenu avant ; motif et
      sauvegarde au journal.
- [ ] Commande de purge.
- [ ] 8 + 6 tests verts, les 2 existants adaptés ; `ruff` propre ; aucun échec nouveau.
- [ ] Commit : `feat(platform_admin): suppression d'une entreprise suspendue, avec motif et sauvegarde prealable`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
