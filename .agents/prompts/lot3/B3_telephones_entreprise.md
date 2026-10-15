# B3 — Plusieurs numéros de contact par entreprise (3.5, US 2.1)

Branche : `feature/lot3-telephones-entreprise`
Prérequis : B1 et B2 fusionnées.
Jumelle frontend : `F4_telephones_entreprise.md`.
**Référence de la table : MLD v1.7 §4.1.1** (`../../04_Conception/architecture_base_donnees/MLD_CCD_Digital.md`). Le lire d'abord.

## 1. La user story

> En tant qu'administrateur, je veux ajouter plusieurs numéros de contact à une entreprise, afin
> de pouvoir la joindre par différents canaux. *Then* tous les numéros sont enregistrés et rattachés
> à l'entreprise ; *And* ils sont affichés dans la fiche de l'entreprise. (Sprint Review du 10/10/2026.)

Décision du développeur (14/10/2026) : **format international validé pour tous les pays**.

## 2. Ce qui existe

- `Entreprise.telephone_contact` (`apps/tenants/models/__init__.py:87`), `CharField(20)`, **sans
  aucun contrôle de format** (`EntrepriseSerializer`, `apps/tenants/serializers/__init__.py:229`).
  Il est lu par la facturation (`apps/billing/services/facture.py:28`), par le paiement CinetPay
  (`apps/billing/services/paiement.py:255`, `customer_phone`) et par le back-office
  (`apps/platform_admin/selectors/clients.py:143`).
- Lecture / écriture de l'entreprise : `GET` / `PATCH` / `POST /api/v1/parametres/configuration/`
  (`ConfigurationEntrepriseView`, `apps/tenants/views/__init__.py:410`) et son doublon
  `/api/v1/entreprise/` (l. 366), qui passent tous deux par `_sauvegarder_entreprise` (l. 306).
  L'écriture exige `administration.entreprise_modifier`. Elle arrive en **JSON**, ou en
  **multipart** quand un logo est envoyé.
- **L'écran envoie déjà `telephone_fixe` et `telephones_secondaires` : le serializer ne les
  déclare pas et les jette sans erreur.** La saisie est perdue à chaque enregistrement.

## 3. Le modèle — `apps/tenants/models/__init__.py`

Après `RegistreEmail` :

```python
class TelephoneEntreprise(ModeleBase):
    """Un numéro de contact d'une entreprise — MLD §4.1.1 (v1.7).

    `cree_par` et `supprime_par` restent nuls : les utilisateurs d'une entreprise vivent dans son
    schéma, pas dans `public.utilisateur`, et une clé étrangère vers eux casserait à l'écriture.
    L'auteur est dans le journal d'audit de l'entreprise.
    """

    class Libelle(models.TextChoices):
        MOBILE = "MOBILE", _("Mobile")
        FIXE = "FIXE", _("Fixe")
        WHATSAPP = "WHATSAPP", _("WhatsApp")
        STANDARD = "STANDARD", _("Standard")
        COMPTABILITE = "COMPTABILITE", _("Comptabilité")
        AUTRE = "AUTRE", _("Autre")

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name="telephones")
    libelle = models.CharField(_("libellé"), max_length=20, choices=Libelle.choices)
    numero = models.CharField(_("numéro"), max_length=16)
    est_principal = models.BooleanField(_("principal"), default=False)
    ordre = models.PositiveSmallIntegerField(_("ordre"), default=0)

    class Meta:
        db_table = "telephone_entreprise"
        ordering = ["-est_principal", "ordre", "cree_le"]
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise"],
                condition=models.Q(est_principal=True, supprime_le__isnull=True),
                name="uq_telephone_entreprise_principal",
            ),
            models.UniqueConstraint(
                fields=["entreprise", "numero"],
                condition=models.Q(supprime_le__isnull=True),
                name="uq_telephone_entreprise_numero",
            ),
            models.CheckConstraint(
                condition=models.Q(numero__regex=r"^\+[1-9][0-9]{7,14}$"),
                name="chk_telephone_entreprise_e164",
            ),
        ]
```

Vérifier l'ordre réel des colonnes / `related_name` avec ce que fait `RegistreEmail` dans le même
fichier, et l'exporter dans `__all__` si le module en a un.

### 3.1 Migrations

1. `python manage.py makemigrations tenants` → `0012_telephoneentreprise` (ou le numéro suivant).
   **Vérifier** que la migration ne touche rien d'autre.
2. Une migration de données `0013_reprendre_telephone_contact` (`RunPython`, avec une fonction
   inverse qui supprime les lignes créées) : pour chaque `Entreprise` dont `telephone_contact` est
   non vide, le **normaliser** (fonction recopiée **dans** la migration, pas importée — une
   migration ne doit pas dépendre du code applicatif qui changera) ; s'il est valide E.164, créer
   une ligne `libelle="STANDARD"`, `est_principal=True`, `ordre=0`, et réécrire
   `telephone_contact` normalisé ; sinon, ne rien créer et laisser `telephone_contact` tel quel.
   Afficher à la fin `print(f"{n} numéros repris, {m} illisibles laissés tels quels")`.
3. Les migrations d'un `SHARED_APP` s'appliquent par `python manage.py migrate_schemas --shared`.
   Vérifier en local que la table n'apparaît **que** dans `public` :
   `SELECT schemaname FROM pg_tables WHERE tablename = 'telephone_entreprise';`.

### 3.2 La suppression définitive

`apps/tenants/services/nettoyage.py` efface les tables publiques **en SQL brut, une par une**
(l. 200-265). Ajouter, **avant** la ligne `DELETE FROM public.entreprise_cliente` (l. 262) :

```python
            cursor.execute("DELETE FROM public.telephone_entreprise WHERE entreprise_id = ANY(%s);", [ent_ids])
            rapport["tables_nettoyees"]["telephone_entreprise"] = cursor.rowcount
```

Sans cela, la suppression d'une entreprise qui a des numéros échoue sur la clé étrangère.

## 4. Les règles — nouveau fichier `apps/tenants/services/telephones.py`

```python
E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
NOMBRE_MAX = 5
SEPARATEURS = re.compile(r"[\s().\-/]")


def normaliser_telephone(valeur: str) -> str:
    """`+225 07 00-00.00 00` → `+2250700000000` ; `00225…` → `+225…`. N'invente pas d'indicatif."""


def est_e164(valeur: str) -> bool: ...


def remplacer_telephones(entreprise, telephones: list[dict], *, auteur_id=None, adresse_ip=None, appareil="") -> list[TelephoneEntreprise]:
    """Remplace la liste des numéros d'une entreprise, et recopie le principal dans `telephone_contact`."""
```

`telephones` : liste de `{"id": <uuid|None>, "libelle": str, "numero": str (déjà normalisé), "principal": bool}`
dans l'ordre d'affichage. Règles, contrôlées **avant toute écriture** (lever
`rest_framework.exceptions.ValidationError({"telephones": "<message>"})`) :

| Règle | Message |
|---|---|
| liste vide | `"Renseignez au moins un numéro de contact."` |
| plus de 5 | `"Cinq numéros au plus par entreprise."` |
| aucun ou plusieurs `principal` | `"Désignez un, et un seul, numéro principal."` |
| deux fois le même numéro | `"Le numéro {numero} figure deux fois."` |
| un `id` qui n'est pas un numéro actif de **cette** entreprise | `"Numéro introuvable : rechargez la page."` |

Écriture, dans `transaction.atomic()` et dans `schema_context("public")` :

1. Lire les lignes actives de l'entreprise (`select_for_update`).
2. **Retirer d'abord le principal actuel** (`est_principal=False`) si le principal change — sinon
   la contrainte `uq_telephone_entreprise_principal` refuse l'écriture du nouveau.
3. Mettre à jour les lignes dont l'`id` est fourni ; créer les autres ; supprimer **logiquement**
   (`supprime_le = timezone.now()`) les lignes absentes de la liste. `ordre` = position dans la liste.
4. `entreprise.telephone_contact = <numéro principal>` ; `save(update_fields=["telephone_contact"])`.
5. Journaliser **dans le schéma de l'entreprise** (la requête y est déjà ; sinon
   `schema_context(entreprise.schema_name)`) : `journaliser(action=ActionAudit.MODIFICATION,
   type_entite="telephone_entreprise", entite_id=entreprise.pk, utilisateur_id=auteur_id,
   valeur_avant=[...], valeur_apres=[...], ...)` — listes de `{libelle, numero, principal}` ;
   **seulement si quelque chose a changé**.

Une seconde fonction pour l'ancien chemin :

```python
def definir_telephone_principal(entreprise, numero: str, **trace) -> None:
    """Pour un client qui n'envoie que `telephone_contact` : met à jour (ou crée, libellé
    STANDARD) le numéro principal, en gardant les autres."""
```

## 5. Le contrat — `EntrepriseSerializer` (`apps/tenants/serializers/__init__.py:195`)

### 5.1 Écriture

```
PATCH /api/v1/parametres/configuration/
{ ..., "telephones": [
    {"id": "uuid-existant", "libelle": "MOBILE", "numero": "+225 07 00 00 00 00", "principal": true},
    {"libelle": "WHATSAPP", "numero": "+33 6 12 34 56 78", "principal": false}
] }
```

- En **multipart** (envoi de logo), `telephones` arrive comme **une chaîne JSON** de cette liste.
- Champ à écrire : `ChampListeTelephones(serializers.Field)` dans le même fichier, qui accepte une
  liste **ou** une chaîne JSON (`json.loads`, erreur `"Liste de numéros illisible."`), puis valide
  chaque élément par un `TelephoneEntrepriseEcritureSerializer` :
  - `id` : `UUIDField(required=False, allow_null=True)` ;
  - `libelle` : `ChoiceField(choices=TelephoneEntreprise.Libelle.choices)`, message
    `"Choisissez à quoi sert ce numéro."` ;
  - `numero` : `CharField(max_length=30)` → `normaliser_telephone` → s'il n'est pas E.164 :
    `"Saisissez le numéro au format international : + suivi de l'indicatif du pays et du numéro, par exemple +225 07 00 00 00 00."` ;
  - `principal` : `BooleanField()`.
  Les erreurs d'un élément remontent sous `telephones.<index>.<champ>` (format DRF des listes) :
  le frontend les pose sous la bonne ligne.
- `telephone_contact` reste accepté (anciens clients) : normalisé, validé E.164 avec le même
  message. **Si `telephones` est présent, il l'emporte** et `telephone_contact` envoyé est ignoré.
- `telephone_fixe` et `telephones_secondaires` : **non déclarés** (le frontend cesse de les
  envoyer en F4).

Dans `_sauvegarder_entreprise` (`views/__init__.py:306`) :

- remplacer `return Response({"detail": _("Aucun tenant résolu.")}, …400)` par
  `raise RequeteRefusee(_("Aucun tenant résolu."))` ;
- sortir `telephones` de `donnees` comme `fichier_logo` (l. 322), puis après le `save` de
  l'entreprise : `remplacer_telephones(tenant, telephones, auteur_id=request.user.pk, adresse_ip=extraire_ip_client(request), appareil=…)` ;
  sinon, si `telephone_contact` est dans `donnees` : `definir_telephone_principal(...)` (et ne pas
  le `setattr` directement) ;
- envelopper l'ensemble dans `transaction.atomic()`.

### 5.2 Lecture

`EntrepriseSerializer` renvoie en plus :

```json
"telephones": [
  {"id": "…", "libelle": "MOBILE", "libelle_affiche": "Mobile", "numero": "+2250700000000", "principal": true},
  {"id": "…", "libelle": "WHATSAPP", "libelle_affiche": "WhatsApp", "numero": "+33612345678", "principal": false}
]
```

(lignes actives, ordre du modèle). `telephone_contact` reste dans la réponse.

### 5.3 Back-office

- `apps/platform_admin/selectors/clients.py`, `formater_client_plateforme` (l. 134) :
  `"telephones": [{"libelle": t.libelle, "libelle_affiche": t.get_libelle_display(), "numero": t.numero, "principal": t.est_principal} for t in ent.telephones.filter(supprime_le__isnull=True)]`.
- `lister_clients_plateforme` (l. ~180) : ajouter
  `Prefetch("telephones", queryset=TelephoneEntreprise.objects.all())` (le gestionnaire `objects`
  exclut déjà les supprimés — **vérifier** `ManagerActif`) et lire `ent.telephones.all()` dans le
  formateur, pour ne pas faire une requête par client.
- `apps/platform_admin/serializers/clients.py` : `ClientPlateformeSerializer` reçoit
  `telephones = TelephoneClientSerializer(many=True)` (champs ci-dessus, lecture seule).

## 6. Tests

Nouveau fichier `apps/tenants/tests/test_telephones_entreprise.py` (`apps/tenants/tests/__init__.py`
à créer s'il n'existe pas ; fixtures : un DG du schéma `demo` et `APIClient(headers={"host": "demo.localhost"})`,
sur le modèle de `apps/accounts/tests/test_alignement_entreprise_frontend.py`).

| Test | Vérifie |
|---|---|
| `test_normaliser_telephone` | espaces, points, tirets, parenthèses retirés ; `00225…` → `+225…` ; rien d'autre n'est inventé |
| `test_e164_tous_pays` | `+2250700000000`, `+33612345678`, `+14155552671`, `+8613800138000` valides ; `0700000000`, `+0225…`, `+22`, 16 chiffres invalides |
| `test_enregistrer_trois_numeros` | `PATCH` JSON avec 3 numéros → 200 ; `GET` les renvoie dans l'ordre, principal d'abord ; `telephone_contact` = le principal |
| `test_multipart_avec_logo_et_numeros` | `PATCH` multipart avec `telephones` en chaîne JSON et un petit PNG → 200, numéros enregistrés |
| `test_changer_de_principal` | le principal passe d'un numéro à l'autre → 200 (pas d'erreur de contrainte) ; `telephone_contact` suit |
| `test_retrait_logique` | un numéro retiré de la liste a `supprime_le` non nul et n'est plus renvoyé |
| `test_six_numeros_refuses` | 400, `details.telephones` « Cinq numéros au plus » ; rien n'a changé en base |
| `test_sans_principal_refuse` / `test_deux_principaux_refuses` | 400, message « un, et un seul » |
| `test_doublon_refuse` | 400, message « figure deux fois » |
| `test_numero_invalide_sous_sa_ligne` | `telephones[1].numero` invalide → 400, l'erreur est sous `telephones` → index `1` → `numero` |
| `test_ancien_client_telephone_contact_seul` | `PATCH {"telephone_contact": "+225 01 02 03 04 05"}` → le principal est mis à jour, les autres numéros restent |
| `test_telephone_contact_invalide_refuse` | `PATCH {"telephone_contact": "12"}` → 400 |
| `test_sans_permission_refuse` | un collaborateur sans `administration.entreprise_modifier` → 403 |
| `test_journal_audit` | une ligne `type_entite="telephone_entreprise"` dans `demo` après un changement ; aucune après un `PATCH` identique |
| `test_fiche_back_office_expose_les_numeros` | `GET /api/v1/admins/clients/{id}/` (superviseur, hôte `localhost`, IP autorisée comme dans `apps/platform_admin/tests/test_clients_admin.py:31`) → `telephones` présent |
| `test_suppression_definitive_avec_numeros` | dans `apps/platform_admin/tests/test_suppression_definitive.py`, l'entreprise de test reçoit un numéro avant suppression → la suppression réussit (§3.2) |
| `test_migration_reprend_l_ancien_numero` | appeler directement la fonction de la migration de données sur une entreprise dont `telephone_contact = "+225 07 00 00 00 00"` → une ligne principale `+2250700000000` |

## 7. Pièges

- **La table vit dans `public`, la requête vient d'un tenant** : le serializer et le service
  lisent `Entreprise` et `TelephoneEntreprise` dans `schema_context("public")` (ou par la relation
  depuis `request.tenant`, qui est une `Entreprise` du public) ; le **journal**, lui, s'écrit dans le
  schéma de l'entreprise. Deux schémas dans une même opération : le dire dans les commentaires.
- **`cree_par` / `supprime_par` jamais renseignés** (voir la docstring du modèle).
- **Ordre des écritures du principal** (§4, étape 2) — sinon `IntegrityError` → 500.
- **`telephone_contact` doit rester E.164** : CinetPay le reçoit tel quel.
- **Un `SHARED_APP`** : `makemigrations` puis `migrate_schemas --shared` ; ne jamais créer cette
  table dans les schémas des entreprises.

## 8. Définition de terminé

- [ ] Table, contraintes, migration de reprise ; nettoyage de la suppression définitive à jour.
- [ ] Contrat §5 servi (JSON et multipart) ; back-office à jour ; `{"detail"}` retiré de `_sauvegarder_entreprise`.
- [ ] 18 tests verts ; aucun échec nouveau ; `ruff` propre.
- [ ] Commit : `feat(tenants): plusieurs numeros de contact par entreprise, au format international`
- [ ] Fusion `--no-ff` dans `develop`, branche supprimée, **pas de push**.
- [ ] Compte rendu : nombre de numéros repris / illisibles par la migration sur la base locale.
