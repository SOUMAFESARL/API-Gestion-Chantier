# B1 — Collaborateurs et rôles : des refus lisibles, et des gestes journalisés (3.1, 3.3)

Branche : `feature/lot3-erreurs-collaborateurs-roles`
Jumelles frontend : `F1_collaborateurs_reels.md`, `F3_roles_reels.md`.

## 1. Le défaut

Le frontend ne lit qu'un format d'erreur : `{"erreur": {"code", "message", "details", "trace_id"}}`
(`../Application-Gestion-Chantier/lib/api/erreurs.ts`, `depuisReponse`). Ce format est produit
par le gestionnaire `apps.core.exceptions.gestionnaire_erreurs` — **pour les exceptions levées
seulement**.

Or `apps/accounts/views/collaborateur.py` et `apps/accounts/views/role.py` **renvoient**
directement `Response({"detail": "…"}, status=403|400|409)`. Ces réponses court-circuitent le
gestionnaire : l'écran reçoit un corps sans `erreur`, et affiche « Une erreur est survenue » à la
place de « Le compte du Directeur Général / Propriétaire ne peut pas être suspendu. ».

Même effet, plus discret, pour `raise ValidationError({"detail": msg})` : le gestionnaire met le
message dans `details.detail` et affiche le texte générique « Certains champs sont invalides. ».

Second défaut : la suspension, la réactivation et la suppression d'un collaborateur **ne laissent
aucune trace** dans le journal d'audit de l'entreprise, alors que le Socle Commun exige un journal
immuable de ces gestes.

## 2. Ce qu'il faut faire

### 2.1 Une exception pour les refus 400 — `apps/core/exceptions.py`

Après `ErreurConflit` (l. 84) :

```python
class RequeteRefusee(ErreurMetier):
    """Une règle refuse la requête, et le code HTTP historique de la route est 400.

    Existe pour ne pas changer les statuts des routes déjà consommées : une règle métier
    répond d'ordinaire 422 (`ErreurMetier`), mais ces routes répondaient 400, et le
    frontend comme les tests d'acceptation s'y fient.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    code_metier = "requete_refusee"
```

### 2.2 Les remplacements — **dans ces deux fichiers seulement**

| Forme actuelle | Remplacer par |
|---|---|
| `return Response({"detail": X}, status=status.HTTP_403_FORBIDDEN)` | `raise PermissionDenied(X)` (`rest_framework.exceptions`) — le gestionnaire garde le texte d'un 403 explicite (`_motif_explicite`, `exceptions.py:222`) |
| `return Response({"detail": X}, status=status.HTTP_409_CONFLICT)` | `raise ErreurConflit(X)` |
| `return Response({"detail": X}, status=status.HTTP_400_BAD_REQUEST)` | `raise RequeteRefusee(X)` |
| `raise ValidationError({"detail": msg}) from exc` | `raise RequeteRefusee(msg) from exc` |

Occurrences à traiter (relevé du 14/10, à revérifier avec
`grep -n '{"detail"' apps/accounts/views/collaborateur.py apps/accounts/views/role.py`) :

- `collaborateur.py` : l. 281, 515, 523, 566, 580, 680, 709, 720, 726, 733, 806, 813 ;
- `role.py` : l. 131, 195, 200, 244, 317, 374, 438, 443, 487.

**Ne pas toucher** :

- les réponses qui portent déjà `{"erreur": {"code": …, "message": …}}` (par exemple
  `role_dg_non_attribuable`, `email_deja_utilise`, `suppression_dg_interdite`,
  `confirmation_requise`) : le frontend les lit déjà, et certaines portent des `details` que
  l'écran exploite (la confirmation de changement de portée) ;
- l'erreur de champ `{"role_personnalise_id": …}` (`collaborateur.py:255`) : c'est une vraie
  erreur de validation, qui doit rester sous le champ ;
- les messages : **le texte de chaque `X` reste identique**, au caractère près.

Les codes HTTP ne changent pas. Seul le corps change.

### 2.3 Journaliser les trois gestes

Dans `apps/accounts/views/collaborateur.py`, **après** l'écriture réussie :

| Vue | Appel |
|---|---|
| `ParametresCollaborateurSuspendreView.post` (l. 697), après le `save` | `journaliser(action=ActionAudit.MODIFICATION, type_entite="utilisateur", entite_id=collaborateur.pk, utilisateur_id=request.user.pk, valeur_avant={"statut": ancien_statut}, valeur_apres={"statut": StatutUtilisateur.DESACTIVE, "geste": "SUSPENSION"}, adresse_ip=extraire_ip_client(request), appareil=request.headers.get("User-Agent", "")[:255])` |
| `ParametresCollaborateurReactiverView.post` (l. 789), après le `save` | même appel, `valeur_apres={"statut": StatutUtilisateur.ACTIF, "geste": "REACTIVATION"}` |
| `ParametresCollaborateurDetailView.delete` (l. 635), après `desactiver_collaborateur_plateforme` | `action=ActionAudit.SUPPRESSION`, `valeur_avant={"email": collaborateur.email, "statut": ancien_statut}`, `valeur_apres={"geste": "RETRAIT"}` |

(`ancien_statut` : lire `collaborateur.statut` **avant** de le modifier.) Imports :
`from apps.audit.services import journaliser`, `from apps.core.enums import ActionAudit`,
`from apps.core.ip_restriction import extraire_ip_client`.

Vérifier d'abord que `desactiver_collaborateur_plateforme` (`apps/accounts/services/utilisateurs.py:38`)
ne journalise pas déjà : s'il le fait, ne pas doubler la trace.

## 3. Tests

Nouveau fichier `apps/accounts/tests/test_erreurs_collaborateurs_roles.py`. Fixtures : reprendre
celles de `apps/accounts/tests/test_alignement_entreprise_frontend.py` (l. 22-104 : `SCHEMA="demo"`,
`HOTE="demo.localhost"`, `client_tenant`, `dg_user`, `admin_user`, `collab_user`, `_auth`).

| Test | Vérifie |
|---|---|
| `test_suspendre_le_dg_dit_pourquoi` | AD suspend le DG → 403 ; `json()["erreur"]["message"]` contient « Directeur Général » ; pas de clé `detail` à la racine |
| `test_suspendre_deux_fois_conflit_lisible` | 2ᵉ suspension → 409, `erreur.code == "conflit"`, message « déjà suspendu » |
| `test_suspendre_son_propre_compte_400_lisible` | le DG se suspend lui-même → 400, `erreur.code == "requete_refusee"`, message « propre compte » (adapter si la règle B-06 répond 403 avant : alors 403 et le message de B-06) |
| `test_reactiver_un_actif_conflit_lisible` | 409, message « déjà actif » |
| `test_role_portee_dg_403_lisible` | modifier la portée du rôle DG → 403, message « portée » |
| `test_suspension_journalisee` | une ligne `JournalAudit` (schéma `demo`) `type_entite="utilisateur"`, `entite_id=collab_user.id`, `valeur_apres.geste == "SUSPENSION"`, `utilisateur_id` = l'auteur |
| `test_reactivation_journalisee` | idem `REACTIVATION` |
| `test_retrait_journalise` | `DELETE` → une ligne `SUPPRESSION`, `valeur_avant.email` |
| `test_refus_ne_journalise_pas` | une suspension refusée (403) ne crée aucune ligne |

Puis lancer **toute** la suite `apps/accounts/tests/` : des tests existants peuvent lire
`reponse.data["detail"]` (aucun au relevé du 14/10, mais `rep.data.get("detail")` ou une
comparaison de texte peut exister). Les adapter pour lire `reponse.json()["erreur"]["message"]`.
**Ne jamais modifier un test de `tests/acceptation/`** sans l'accord du développeur ; au relevé,
`tests/acceptation/lot2/test_b03_dg.py:129-136` ne contrôle que le code HTTP.

## 4. Pièges

- **`raise` au lieu de `return`** : vérifier qu'aucune écriture n'a eu lieu avant le refus (les
  refus actuels sont tous en tête de méthode ; ne pas en déplacer).
- **`PermissionDenied` d'un texte vide** retomberait sur le message générique : toujours passer le
  texte.
- **Le gestionnaire ne réécrit que ce qui est levé** : une `Response` construite à la main reste
  telle quelle. C'est la leçon de cette tâche ; ne pas en ajouter de nouvelle.

## 5. Définition de terminé

- [ ] `RequeteRefusee` ajoutée ; plus aucun `{"detail"` dans `collaborateur.py` ni `role.py`.
- [ ] Trois gestes journalisés ; 9 tests verts ; suite `apps/accounts` et `tests/acceptation` sans
      échec nouveau ; `ruff` propre.
- [ ] Commit : `fix(accounts): refus des collaborateurs et des roles au format du produit, gestes journalises`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
