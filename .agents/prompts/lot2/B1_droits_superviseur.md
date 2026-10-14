# B1 — Réserver au superviseur les actions sensibles du back-office (tâche 2.0)

Branche : `feature/lot2-droits-superviseur`
Jumelle frontend : `F1_role_reel.md` (à faire juste après).

## 1. Contexte

Le back-office a deux rôles (voir `README.md` §2.6) :

- **SUPERVISEUR** : `is_superuser = True` ;
- **SUPPORT** : `is_staff = True`, `is_superuser = False`.

La permission DRF `EstSuperAdminPlateforme` (`apps/platform_admin/permissions.py:10`) laisse
passer **les deux** rôles. Seules quelques vues ajoutent un second contrôle,
`_exiger_superviseur(request)` (`apps/platform_admin/views/parametres.py:26`) : tarifs,
identité, messagerie, suppression définitive.

**Le défaut** : un agent SUPPORT peut aujourd'hui suspendre une entreprise, changer son
forfait, **créer un compte SUPERVISEUR** (élévation de privilège), modifier le catalogue des
modules et des permissions. Le frontend grise les boutons, mais n'importe quel appel direct à
l'API passe.

## 2. Ce qu'il faut faire

### 2.1 Déplacer le contrôle dans `permissions.py`

Dans `apps/platform_admin/permissions.py`, ajouter à la fin :

```python
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import PermissionDenied


MESSAGE_SUPERVISEUR = _("Seul un superviseur de la plateforme peut effectuer cette action.")


def exiger_superviseur(request) -> None:
    """Le SUPPORT lit le back-office ; seul le superviseur le modifie.

    Appelée en tête de chaque méthode d'écriture réservée : un contrôle par méthode, et non
    une classe de permission, parce que la même vue sert souvent la lecture (ouverte au
    SUPPORT) et l'écriture (fermée).
    """
    if not getattr(request.user, "is_superuser", False):
        raise PermissionDenied(MESSAGE_SUPERVISEUR)
```

(Regrouper les imports en tête de fichier, selon l'ordre de `ruff`.)

Dans `apps/platform_admin/views/parametres.py`, **remplacer** la définition de
`_exiger_superviseur` (lignes 26-29) par un alias, pour ne casser aucun import existant
(`views/messagerie.py:13`, `views/suppression.py:14`) :

```python
from apps.platform_admin.permissions import EstSuperAdminPlateforme, exiger_superviseur

_exiger_superviseur = exiger_superviseur
```

Le message change légèrement (« effectuer cette action » au lieu de « modifier ce réglage ») :
c'est voulu, il sert désormais à toutes les actions. Chercher dans les tests
(`grep -rn "modifier ce réglage" apps tests`) et adapter les assertions qui portent sur
l'ancien texte.

### 2.2 Poser le contrôle sur chaque écriture réservée

Ajouter `exiger_superviseur(request)` **en première ligne** de chacune de ces méthodes
(import : `from apps.platform_admin.permissions import exiger_superviseur`).

| Fichier | Classe | Méthode(s) |
|---|---|---|
| `views/clients.py` | `SuspendreClientPlateformeView` (l. 197) | `post` |
| `views/clients.py` | `ReactiverClientPlateformeView` (l. 268) | `post` |
| `views/clients.py` | `ChangerPlanClientPlateformeView` (l. 329) | `patch` (le `post` délègue à `patch` : un seul contrôle suffit) |
| `views/comptes.py` | `ComptesAdministrateursListCreateView` (l. 38) | `post` uniquement — **le `get` reste ouvert au SUPPORT** |
| `views/comptes.py` | `SuspendreCompteAdministrateurView` (l. 93) | `post` |
| `views/comptes.py` | `ReactiverCompteAdministrateurView` (l. 119) | `post` |
| `views/modules.py` | `AdminModuleListCreateView` (l. 39) | `post` uniquement |
| `views/modules.py` | `AdminModuleDetailUpdateDeleteView` (l. 92) | `patch`, `delete` |
| `views/modules.py` | `AdminModuleAffecterPermissionsView` (l. 167) | `put` |
| `views/modules.py` | `AdminModuleDesactiverView` (l. 199) | `post` |
| `views/modules.py` | `AdminModuleReactiverView` (l. 224) | `post` |
| `views/permissions.py` | `AdminPermissionListCreateView` (l. 36) | `post` uniquement |
| `views/permissions.py` | `AdminPermissionDetailUpdateDeleteView` (l. 86) | `patch`, `delete` |
| `views/permissions.py` | `AdminPermissionAffecterModulesView` (l. 153) | `post` |

**Ne PAS toucher** (restent ouverts au SUPPORT) :

- toutes les méthodes `get` ;
- `ActiverModuleClientPlateformeView.post` et `DesactiverModuleClientPlateformeView.post`
  (`views/clients.py` l. 432 et l. 544) : activer un module pour un client est un geste de
  support courant ;
- `views/comptes.py` : `AdminProfilMoiView`, `AdminPhotoMoiView`,
  `AdminChangerMotDePasseMoiView` (chacun gère **son propre** profil) ;
- les vues d'assistance (`views/impersonation.py`) : l'assistance est reportée à un lot dédié.

Les vues de `views/parametres.py`, `views/messagerie.py` et `views/suppression.py` ont déjà le
contrôle : vérifier simplement qu'il y est toujours.

### 2.3 Le profil dit le vrai rôle (déjà le cas, à garantir par un test)

`serializers/auth.py:64` expose `role` (`SUPERVISEUR` / `SUPPORT`) et `is_superuser` dans la
réponse de connexion ; `serializers/comptes.py:103` fait de même pour `GET /admins/moi/`. Le
frontend (F1) va lire ce champ. Ne rien changer, mais le couvrir par un test.

## 3. Tests à écrire

Nouveau fichier `apps/platform_admin/tests/test_droits_superviseur.py`.

Reprendre les fixtures de `apps/platform_admin/tests/test_clients_admin.py` (lignes 27-128) :
`autoriser_ip_locale` (autouse), `entreprise_test`, `client_api`, `SCHEMA_CLIENT = "demo"`,
`HOTE_PLATEFORME = "localhost"`. Créer deux agents dans le schéma public, sur le modèle de
`_agent()` de `apps/platform_admin/tests/test_suppression_definitive.py:25` :

```python
def _agent(email: str, superviseur: bool) -> Utilisateur:
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email=email).delete()
        fabrique = (
            Utilisateur.objects.create_superuser if superviseur else Utilisateur.objects.create_user
        )
        return fabrique(
            email=email, password="MotDePasse12345!", nom="Agent", prenom="Plateforme",
            role_global=RoleGlobal.ADMIN, statut=StatutUtilisateur.ACTIF,
            **({} if superviseur else {"is_staff": True}),
        )
```

Tests (noms exacts) :

1. `test_support_ne_peut_pas_ecrire_sur_les_actions_reservees` — **paramétré** par
   `pytest.mark.parametrize` sur des tuples `(methode, url, corps)` couvrant **chaque ligne**
   du tableau §2.2 (URL sous `/api/v1/admins/...` ; pour les identifiants de module /
   permission / compte, un `uuid.uuid4()` quelconque suffit : le contrôle de rôle passe
   **avant** la recherche de l'objet, donc on attend 403 et non 404). Attendu : `403`, et
   `reponse.json()["erreur"]["message"]` contient « superviseur ». Vérifier aussi qu'**aucune
   ligne `JournalPlateforme` n'a été créée** pendant l'appel (compter avant / après).
2. `test_support_lit_le_back_office` — le SUPPORT obtient `200` sur `GET /api/v1/admins/clients/`,
   `GET /api/v1/admins/clients/{id}/`, `GET /api/v1/admins/comptes/`,
   `GET /api/v1/admins/modules/`, `GET /api/v1/admins/permissions/`,
   `GET /api/v1/admins/journal-plateforme/`, `GET /api/v1/admins/parametres/messagerie/`.
3. `test_support_active_et_desactive_un_module_client` — le SUPPORT obtient `200` sur
   `POST /api/v1/admins/clients/{id}/modules/{module_id}/desactiver/` puis `/activer/` pour un
   module du catalogue **autre que `projets`** (prendre
   `CatalogueModule.objects.exclude(code__iexact="projets").filter(est_actif=True).first()` ;
   `pytest.skip` si aucun).
4. `test_superviseur_suspend_toujours` — le superviseur suspend l'entreprise de test : `200`,
   statut `SUSPENDU` (non-régression).
5. `test_support_ne_cree_pas_de_compte_superviseur` — `POST /api/v1/admins/comptes/` avec
   `{"email": "...", "nom": "X", "prenom": "Y", "role": "SUPERVISEUR"}` par le SUPPORT : `403`,
   et aucun utilisateur de cet e-mail n'existe ensuite dans le schéma public.
6. `test_profil_expose_le_role_support` — `GET /api/v1/admins/moi/` par le SUPPORT :
   `role == "SUPPORT"` et `is_superuser is False`.

## 4. Pièges

- **`ChangerPlanClientPlateformeView.post` appelle `self.patch`** : mettre le contrôle dans
  `patch` le couvre ; le mettre dans les deux ferait deux contrôles, sans danger mais inutile.
- **Le contrôle doit précéder toute lecture de l'objet** : sinon un SUPPORT apprend par un
  404 / 200 qu'un identifiant existe. D'où « première ligne de la méthode ».
- **Les tests d'acceptation** (`tests/acceptation/lot1/conftest.py:41`) utilisent un super
  admin `is_superuser=True` : ils ne doivent pas casser. Si un test d'acceptation casse,
  c'est qu'il se connecte en SUPPORT pour écrire — le signaler au développeur, ne pas
  modifier le test d'acceptation sans son accord.

## 5. Définition de terminé

- [ ] `exiger_superviseur` dans `permissions.py`, alias dans `parametres.py`.
- [ ] Les 16 méthodes du tableau §2.2 contrôlées, aucune autre.
- [ ] 6 tests ajoutés, verts.
- [ ] `ruff` propre ; aucun échec nouveau dans `apps/platform_admin/tests` ni
      `tests/acceptation` (comparer au relevé fait sur `develop`).
- [ ] Commit : `feat(platform_admin): les actions sensibles du back-office sont reservees au superviseur`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
