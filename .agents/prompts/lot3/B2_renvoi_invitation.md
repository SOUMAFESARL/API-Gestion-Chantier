# B2 — Renvoyer l'invitation d'un collaborateur (3.2)

Branche : `feature/lot3-renvoi-invitation`
Prérequis : B1 fusionnée (`RequeteRefusee`, journalisation).
Jumelle frontend : `F2_renvoi_invitation.md`.

## 1. Contexte

Inviter un collaborateur (`POST /api/v1/parametres/collaborateurs/`,
`ParametresCollaborateurListCreateView.post`, `apps/accounts/views/collaborateur.py:223-391`) :

1. crée (ou réutilise) un `Utilisateur` au statut `INVITE`, sans mot de passe utilisable ;
2. appelle `creer_invitation(...)` (`apps/accounts/services/invitations.py:41`), qui crée une ligne
   `Invitation` (empreinte SHA-256 du jeton, `expire_le = maintenant + DUREE_INVITATION`, **72 h**)
   et envoie le courriel avec le lien `…/invitation#jeton=<jeton>` ;
3. renvoie `lien_activation` (chemin relatif) que l'écran peut copier.

**Au bout de 72 h, le lien est mort et rien ne permet d'en refaire un** : il faut supprimer le
collaborateur puis le réinviter. `accepter_invitation` (l. 154) refuse toute invitation dont
`est_utilisable` est faux (`models/__init__.py:405` : non utilisée, statut `ENVOYEE`, non expirée).

## 2. Contrat d'API

```
POST /api/v1/parametres/collaborateurs/{id}/renvoyer-invitation/
Corps : {}  (aucun)
→ 200 : le collaborateur, au même format que la réponse de création
         (CollaborateurResponseSerializer), avec "lien_activation" rempli
         et un champ supplémentaire "email_envoye": true | false
```

| Cas | Statut | Corps |
|---|---|---|
| Pas la permission de gérer les collaborateurs | 403 | celui de `_autoriser_parametres_collaborateurs` (l. 78) |
| Collaborateur introuvable ou supprimé | 404 | standard |
| La cible est administrateur (AD) et le demandeur n'est pas le DG | 403 | `PermissionDenied("Seul le Directeur Général a autorité pour inviter un administrateur.")` |
| Statut ≠ `INVITE` | 409 | `ErreurConflit("Ce collaborateur a déjà activé son compte : il n'y a pas d'invitation à renvoyer.")` |
| Une invitation a été créée pour cette adresse il y a moins de 60 secondes | 409 | `ErreurConflit("Une invitation vient d'être envoyée à cette adresse : patientez une minute avant de la renvoyer.")` |

Le quota du plan **n'est pas** revérifié (`verifier_quota=False`) : le collaborateur est déjà
compté depuis sa première invitation.

## 3. Implémentation

### 3.1 Service — `apps/accounts/services/invitations.py`

```python
DELAI_ENTRE_RENVOIS = timedelta(seconds=60)


@transaction.atomic
def renvoyer_invitation(collaborateur: Utilisateur, *, emetteur: Utilisateur, hote: str | None = None) -> Invitation:
    """Révoque les invitations encore ouvertes de cette adresse et en émet une nouvelle.

    L'ancien lien doit cesser de valoir : deux liens valides pour un même compte, c'est deux
    personnes qui peuvent l'activer.
    """
```

Étapes :

1. `ouvertes = Invitation.objects.select_for_update().filter(email__iexact=collaborateur.email, statut=Invitation.Statut.ENVOYEE, utilise_le__isnull=True)`.
2. Si l'une d'elles a `cree_le > timezone.now() - DELAI_ENTRE_RENVOIS` → `ErreurConflit(...)`
   (message §2).
3. `ouvertes.update(statut=Invitation.Statut.REVOQUEE, modifie_le=timezone.now())`.
4. Reprendre le rôle proposé et le nom comme à la création (`collaborateur.py:342-349`) :
   `role_propose = collaborateur.role.code if collaborateur.role else (collaborateur.role_global or "VISITEUR")`,
   `nom = f"{collaborateur.prenom} {collaborateur.nom}".strip()`.
5. `invitation = creer_invitation(email=collaborateur.email, role_propose=..., nom=..., emetteur=emetteur, hote=hote, verifier_quota=False)`.
6. `journaliser(action=ActionAudit.MODIFICATION, type_entite="invitation", entite_id=invitation.pk, utilisateur_id=emetteur.pk, valeur_apres={"geste": "RENVOI", "email": collaborateur.email, "invitations_revoquees": <nombre>})`.
7. Retourner `invitation` (elle porte `jeton_clair` et `email_envoye`, posés par `creer_invitation`).

L'exporter dans `__all__` du module s'il en a un.

### 3.2 Vue — `apps/accounts/views/collaborateur.py`

Nouvelle classe, après `ParametresCollaborateurReactiverView`, sur son modèle exact (mêmes
`permission_classes`, même contrôle `_autoriser_parametres_collaborateurs`, même construction de
`reponse_data` — **factoriser** cette construction dans une fonction `_charge_collaborateur(collaborateur, request, lien_activation=None)`
si elle est recopiée une troisième fois ; sinon, la recopier) :

```python
class ParametresCollaborateurRenvoyerInvitationView(APIView):
    """`POST /api/v1/parametres/collaborateurs/{id}/renvoyer-invitation/` — un nouveau lien, l'ancien révoqué."""
```

- Contrôles dans l'ordre du tableau §2 ; le statut se compare à `StatutUtilisateur.INVITE`.
- Le contrôle « AD » reprend l'expression `is_cible_ad` des vues voisines (l. 715-718) et
  `est_dg(request.user)`.
- `lien_activation = f"/invitation#jeton={invitation.jeton_clair}"` (même forme qu'à la création,
  l. 361).
- `"email_envoye": bool(getattr(invitation, "email_envoye", False))` ajouté à la réponse : si le
  serializer de réponse ne déclare pas ce champ, l'ajouter au dict **après** `.data`.
- `@extend_schema(summary="Renvoyer l'invitation d'un collaborateur", request=None, responses={200: CollaborateurResponseSerializer})`.

### 3.3 URL — `apps/accounts/urls.py`

À côté de `suspendre/` et `reactiver/` (l. ~100-110) :

```python
    path(
        "parametres/collaborateurs/<uuid:pk>/renvoyer-invitation/",
        ParametresCollaborateurRenvoyerInvitationView.as_view(),
        name="parametres-collaborateur-renvoyer-invitation",
    ),
```

## 4. Tests

Nouveau fichier `apps/accounts/tests/test_renvoi_invitation.py` (fixtures comme B1). Créer
l'invité **par l'API** (`POST /api/v1/parametres/collaborateurs/` en DG) pour avoir un état
réaliste. Courriels : `settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"`.

| Test | Vérifie |
|---|---|
| `test_renvoi_emet_un_nouveau_lien` | 200 ; `lien_activation` différent de celui de la création ; un 2ᵉ courriel dans `mail.outbox` |
| `test_ancien_lien_revoque` | l'ancienne `Invitation` est `REVOQUEE` ; `POST /api/v1/invitations/accepter/` avec l'ancien jeton échoue ; avec le nouveau, réussit |
| `test_renvoi_trop_rapproche_refuse` | deux renvois immédiats → le 2ᵉ en 409, message « patientez » (pour le 1ᵉʳ, vieillir l'invitation de création : `Invitation.objects.filter(...).update(cree_le=timezone.now() - timedelta(minutes=5))`) |
| `test_invitation_expiree_se_renvoie` | invitation vieillie de 4 jours (`expire_le` passé) → 200, le nouveau lien fonctionne |
| `test_compte_actif_refuse` | collaborateur `ACTIF` → 409 « déjà activé » |
| `test_renvoi_journalise` | une ligne `JournalAudit` `type_entite="invitation"`, `valeur_apres.geste == "RENVOI"` |
| `test_ad_ne_renvoie_pas_l_invitation_d_un_ad` | un AD demande le renvoi pour un invité AD → 403 |
| `test_quota_non_reverifie` | avec le quota du plan atteint (voir comment `verifier_quota_avant_invitation` se teste dans `test_invitations.py`), le renvoi passe |

## 5. Pièges

- **Révoquer avant de créer, dans la même transaction** : sinon une panne entre les deux laisse
  deux liens valides, ou aucun.
- **`email__iexact`** : les adresses sont stockées en minuscules, mais pas forcément toutes les
  anciennes lignes.
- Le courriel part **dans** `creer_invitation` (pas en `on_commit`) : c'est le comportement
  existant, ne pas le changer ici.

## 6. Définition de terminé

- [ ] Route servie selon §2 ; ancien lien révoqué ; renvoi journalisé.
- [ ] 8 tests verts ; aucun échec nouveau ; `ruff` propre.
- [ ] Commit : `feat(accounts): renvoyer l'invitation d'un collaborateur, l'ancien lien revoque`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
