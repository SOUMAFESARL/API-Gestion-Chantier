# B2 — Modifier l'échéance de l'abonnement d'un client (tâche 2.2)

Branche : `feature/lot2-echeance-abonnement`
Prérequis : B1 fusionnée (`exiger_superviseur` existe).
Jumelle frontend : `F2_echeance_abonnement.md`.

## 1. Contexte

L'écran « Modifier la date de fin » du back-office existe déjà
(`../Application-Gestion-Chantier/app/(admin)/admin/clients/ModaleFinAbonnement.tsx`) et
appelle `PATCH /api/v1/admins/clients/{id}/`. **Cette route répond 405** :
`FicheClientPlateformeView` (`apps/platform_admin/views/clients.py:153`) n'a qu'un `get`.

## 2. Contrat d'API — à tenir exactement

```
PATCH /api/v1/admins/clients/{client_id}/
Authorization: Bearer <jeton administration>
Content-Type: application/json

{
  "abonnement": { "date_fin": "2027-01-31" },
  "motif": "Geste commercial après l'incident de facturation du 10/10."
}
```

- `abonnement.date_fin` : obligatoire, date `AAAA-MM-JJ`.
- `motif` : obligatoire, chaîne ; **après `strip()`, 10 caractères au moins**, 500 au plus.
- Tout autre champ (y compris `abonnement.fin_essai`, que l'ancien frontend envoyait) est
  **ignoré sans erreur** : c'est le serveur qui décide de `fin_essai`.

**Réponse 200** : la fiche client complète, exactement comme `GET /api/v1/admins/clients/{id}/`
(`ClientPlateformeSerializer(formater_client_plateforme(ent))`).

**Erreurs** (dans cet ordre de contrôle) :

| Cas | Statut | Corps |
|---|---|---|
| Agent SUPPORT | 403 | message de `exiger_superviseur` |
| Entreprise introuvable, ou schéma `public` | 404 | `"Entreprise cliente introuvable."` |
| `abonnement` ou `abonnement.date_fin` absent / mal formé | 400 | erreur DRF standard sur le champ |
| `motif` absent ou < 10 caractères | 400 | champ `motif` : `"Le motif doit contenir au moins 10 caractères."` |
| `date_fin` < aujourd'hui (`timezone.localdate()`) | 400 | champ `date_fin` : `"La date de fin ne peut pas être antérieure à aujourd'hui."` |
| Aucun abonnement pour cette entreprise | 409 | `"Cette entreprise n'a aucun abonnement à prolonger."` |
| Abonnement `RESILIE` | 409 | `"Un abonnement résilié ne se prolonge pas : il faut en souscrire un nouveau."` |
| `date_fin` ≤ `date_debut` de l'abonnement | 400 | champ `date_fin` : `"La date de fin doit être postérieure à la date de début de l'abonnement."` |

Pour les 400 sur `date_fin` levés dans le service, lever
`rest_framework.exceptions.ValidationError({"date_fin": "<message>"})` : le gestionnaire
d'erreurs du produit les met dans `details.date_fin`, que le frontend affiche sous le champ.

## 3. Règles métier

1. **Quel abonnement** : le même que celui que la fiche affiche — d'abord l'abonnement `ACTIF`
   ou `ESSAI`, sinon le plus récent (`ent.abonnements.first()`, l'ordre du modèle est
   `-date_debut`). Reprendre exactement la sélection de `changer_plan_client_plateforme`
   (`services/clients.py:135-140`).
2. **Ce qui change** : `date_fin` ; et si `abonnement.statut == ESSAI`, `fin_essai` prend la
   même valeur (sinon l'essai expirerait avant l'échéance affichée). Rien d'autre : ni le
   statut, ni `renouvellement_auto`, ni le plan.
3. **Pas de réactivation automatique** : une entreprise `SUSPENDU` reste suspendue, un
   abonnement `IMPAYE` ou `SUSPENDU` garde son statut. (Décision 2.2 e.)
4. **Même date qu'avant** : accepter (200), mais **ne rien journaliser et ne pas écrire au
   DG** — il ne s'est rien passé.
5. **Traçabilité** (dans la même transaction que la modification) :
   - `journaliser_plateforme(action="MODIFICATION_ECHEANCE", acteur=..., entreprise=...,
     detail={...}, adresse_ip=..., appareil=...)` avec
     `detail = {"ancienne_date_fin": "...", "nouvelle_date_fin": "...",
     "ancienne_fin_essai": "..." | None, "nouvelle_fin_essai": "..." | None,
     "statut_abonnement": "...", "motif": "..."}` (dates en ISO) ;
   - `journaliser_tenant(entreprise=..., action="MODIFICATION", type_entite="Abonnement",
     entite_id=abonnement.id, valeur_apres={"date_fin": "...", "fin_essai": ...}, acteur=...,
     adresse_ip=..., appareil=...)`.
6. **Courriel au DG** : `notifier_dg_action_plateforme(entreprise=ent,
   sujet=SUJET_MODIFICATION_PLATEFORME, message=..., super_admin_email=...)`, avec ce message
   (le motif n'y figure **pas**, il est interne à l'éditeur) :
   ```
   Bonjour,

   La date de fin de votre abonnement a été modifiée par l'administration de la plateforme.
   Nouvelle date de fin : {date au format JJ/MM/AAAA}
   ```
   Il part après validation de la transaction (`transaction.on_commit`, déjà géré par la
   fonction) : il faut donc que la modification soit dans un `transaction.atomic()`.

## 4. Implémentation, couche par couche

### 4.1 Serializer — `apps/platform_admin/serializers/clients.py`

À côté de `ChangerPlanClientRequestSerializer` :

```python
class EcheanceAbonnementSerializer(serializers.Serializer):
    date_fin = serializers.DateField()


class ModifierEcheanceClientRequestSerializer(serializers.Serializer):
    """Corps de `PATCH /admins/clients/{id}/` : l'échéance, et pourquoi on la change."""

    abonnement = EcheanceAbonnementSerializer()
    motif = serializers.CharField(max_length=500, trim_whitespace=True)

    def validate_motif(self, valeur: str) -> str:
        if len(valeur) < 10:
            raise serializers.ValidationError("Le motif doit contenir au moins 10 caractères.")
        return valeur
```

Attention : un `CharField` vide lève déjà « Ce champ ne peut être vide » ; pour que le
frontend reçoive **toujours** le même message, déclarer
`motif = serializers.CharField(max_length=500, allow_blank=True, trim_whitespace=True)` et
laisser `validate_motif` refuser la chaîne vide avec le message ci-dessus. Pour un `motif`
absent, ajouter `error_messages={"required": "Le motif doit contenir au moins 10 caractères."}`.

L'exporter dans `__all__` si le module en a un.

### 4.2 Service — `apps/platform_admin/services/clients.py`

Nouvelle fonction, sur le modèle des trois existantes (même signature de traçabilité) :

```python
def modifier_echeance_client_plateforme(
    entreprise_id: uuid.UUID | str,
    date_fin: date,
    motif: str,
    admin_user=None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> dict:
```

Étapes :

1. Retrouver l'entreprise hors `public` (copier les lignes 32-35) → `NotFound`.
2. Sélectionner l'abonnement (règle 3.1) → `ErreurConflit` si aucun, ou si `RESILIE`.
3. `date_fin < timezone.localdate()` → `ValidationError({"date_fin": ...})`.
4. `date_fin <= abonnement.date_debut` → `ValidationError({"date_fin": ...})`. (La contrainte
   `chk_abonnement_dates` du modèle lèverait sinon une `IntegrityError` → 500.)
5. Si `date_fin == abonnement.date_fin` (et `fin_essai` déjà cohérent) : retourner
   `formater_client_plateforme(ent)` sans rien écrire.
6. Dans `with transaction.atomic():` — mettre à jour `date_fin` (et `fin_essai` si ESSAI),
   `save(update_fields=[..., "modifie_le"])`, journaliser (plateforme + tenant), notifier le DG.
7. `logger.info(...)` comme les autres fonctions, **sans le motif** dans le log applicatif
   (il est déjà au journal).
8. Retourner `formater_client_plateforme(ent)`.

Imports : `from datetime import date`, `from django.db import transaction`, et depuis
`apps.platform_admin.services.notifications` : `journaliser_plateforme`, `journaliser_tenant`,
`notifier_dg_action_plateforme`, `SUJET_MODIFICATION_PLATEFORME`. Vérifier qu'aucun import
circulaire n'apparaît (`notifications.py` n'importe pas `services/clients.py` : c'est sûr).

### 4.3 Vue — `apps/platform_admin/views/clients.py`

Ajouter une méthode `patch` à `FicheClientPlateformeView` (l. 153) :

```python
    @extend_schema(
        tags=["admins-clients"],
        summary="Modifier l'échéance de l'abonnement d'une entreprise cliente",
        description=(
            "Repousse ou avance la date de fin de l'abonnement en cours. Pendant un essai, "
            "la fin de l'essai suit. Motif obligatoire (10 caractères au moins), journalisé ; "
            "le Directeur Général est prévenu par courriel. Réservé au superviseur."
        ),
        parameters=[PARAM_CLIENT_ID],
        request=ModifierEcheanceClientRequestSerializer,
        responses={200: ClientPlateformeSerializer, 400: ErreurPlateformeResponseSerializer,
                   403: ErreurPlateformeResponseSerializer, 404: ErreurPlateformeResponseSerializer,
                   409: ErreurPlateformeResponseSerializer},
    )
    def patch(self, request, client_id):
        exiger_superviseur(request)
        serializer = ModifierEcheanceClientRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = modifier_echeance_client_plateforme(
            entreprise_id=client_id,
            date_fin=serializer.validated_data["abonnement"]["date_fin"],
            motif=serializer.validated_data["motif"],
            admin_user=request.user,
            adresse_ip=extraire_ip_client(request),
            appareil=request.headers.get("User-Agent", "")[:255],
        )
        return Response(ClientPlateformeSerializer(client).data, status=status.HTTP_200_OK)
```

Mettre à jour la docstring de la classe : `GET` **et** `PATCH`.

Aucune URL à ajouter : `admins/clients/<uuid:client_id>/` pointe déjà sur cette vue.

## 5. Tests

Nouveau fichier `apps/platform_admin/tests/test_echeance_client.py`. Fixtures copiées de
`test_clients_admin.py` (l. 27-128 : `autoriser_ip_locale`, `super_admin_user`,
`entreprise_test`, `client_api`) + un agent SUPPORT (`_agent(..., superviseur=False)`, voir
B1). L'abonnement de `entreprise_test` est `ACTIF`, `date_debut = aujourd'hui - 30 j`,
`date_fin = aujourd'hui + 335 j`.

Neutraliser l'envoi réel : `settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"`
et utiliser la fixture `django_capture_on_commit_callbacks(execute=True)` de pytest-django
pour exécuter les `on_commit` et lire `django.core.mail.outbox`.

| Test | Vérifie |
|---|---|
| `test_superviseur_repousse_l_echeance` | 200 ; `abonnement.date_fin` de la réponse = nouvelle date ; en base aussi ; statut inchangé |
| `test_echeance_journalisee_plateforme_et_tenant` | une ligne `JournalPlateforme` `MODIFICATION_ECHEANCE` avec `detail.motif`, `ancienne_date_fin`, `nouvelle_date_fin` ; une ligne `JournalAudit` `type_entite="Abonnement"` dans le schéma `demo` |
| `test_echeance_previent_le_dg_sans_le_motif` | un courriel dans `mail.outbox` (si `demo` a un DG actif ; sinon en créer un comme `test_suppression_definitive._entreprise_de_test`) ; le motif n'apparaît pas dans `body` |
| `test_en_essai_fin_essai_suit` | abonnement passé en `ESSAI` avec `fin_essai` ; après PATCH, `fin_essai == date_fin` |
| `test_date_passee_refusee` | `date_fin = hier` → 400, `details.date_fin` contient « antérieure à aujourd'hui » ; base inchangée |
| `test_motif_trop_court_refuse` | `motif = "court"` → 400 sur `motif` ; `motif` absent → 400 même message |
| `test_support_refuse` | SUPPORT → 403 ; base inchangée ; aucun journal |
| `test_entreprise_suspendue_reste_suspendue` | entreprise et abonnement `SUSPENDU` ; après PATCH : 200, toujours `SUSPENDU` |
| `test_abonnement_resilie_refuse` | statut `RESILIE` → 409 |
| `test_meme_date_sans_trace` | PATCH avec la date actuelle → 200, aucune ligne de journal créée |
| `test_fin_essai_envoyee_par_le_client_ignoree` | corps avec `abonnement.fin_essai` sur un abonnement `ACTIF` → 200, `fin_essai` reste `None` |

## 6. Pièges

- **Contrainte d'unicité** `uq_abonnement_actif` : ne jamais créer d'abonnement ici.
- **Fuseau** : comparer avec `timezone.localdate()`, pas `date.today()` (le serveur de
  production n'est pas forcément dans le fuseau de l'application).
- **`formater_client_plateforme` relit l'entreprise** : appeler après le `save`, hors du
  `atomic` ou dedans, peu importe, mais **après** l'écriture.

## 7. Définition de terminé

- [ ] `PATCH /admins/clients/{id}/` servi selon le contrat §2.
- [ ] 11 tests verts ; `ruff` propre ; aucun échec nouveau.
- [ ] Commit : `feat(platform_admin): modifier l'echeance de l'abonnement d'un client`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
