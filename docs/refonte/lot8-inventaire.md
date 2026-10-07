# Inventaire et Prérequis du Lot 8 : Collaborateurs, Registre Global, Abonnement, Lectures

Document établi par Gemini en application des prérequis **P1 à P4** du cadrage du Lot 8 (`docs/refonte/08-cadrage-tests-lot8.md`).

---

## 1. P1 (a) Routes sous `/billing/` et `/cinetpay/`

Fichier de routage : `apps/billing/urls.py` monté sous `/api/v1/` dans `config/urls_tenant.py`.

| Méthode | URL | Vue | Garde Actuelle (`permission_classes`) | Cible Lot 8 (F-03, F-04, F-05, C-04) |
|---|---|---|---|---|
| `GET` | `/api/v1/abonnement/` | `AbonnementView` (`apps/billing/views/abonnement.py:20`) | `[IsAuthenticated]` | **F-03** : Tout utilisateur connecté ne reçoit que `jours_essai_restants` et `est_expire`. Le détail complet (plan, quotas, échéances) exige `administration.abonnement_voir`. |
| `GET` | `/api/v1/abonnement/notifications/` | `NotificationsExpirationView` (`apps/billing/views/expiration.py:15`) | `[IsAuthenticated, RoleRequis.pour(*ROLES_FACTURATION)]` (`ROLES_FACTURATION = [AD, DG, DF]`) | **F-04** : Exige `administration.abonnement_voir` (DG, AD). Suppression de `RoleRequis` et de la constante `ROLES_FACTURATION`. |
| `GET` | `/api/v1/factures/` | `FactureListeView` (`apps/billing/views/facture.py:69`) | `[IsAuthenticated, RoleRequis.pour(ADMIN, DIRECTEUR_GENERAL)]` | **F-04** : Exige `administration.factures_voir` (DG, AD). Suppression de `RoleRequis`. |
| `GET` | `/api/v1/factures/<uuid:pk>/` | `FactureDetailView` (`apps/billing/views/facture.py:93`) | `[IsAuthenticated, RoleRequis.pour(ADMIN, DIRECTEUR_GENERAL)]` | **F-04** : Exige `administration.factures_voir` (DG, AD). 403 avant 404 (L8-9). Suppression de `RoleRequis`. |
| `GET` | `/api/v1/factures/<uuid:pk>/pdf/` | `FacturePDFView` (`apps/billing/views/facture.py:106`) | `[IsAuthenticated, RoleRequis.pour(ADMIN, DIRECTEUR_GENERAL)]` | **F-04** : Exige `administration.factures_voir` (DG, AD). Suppression de `RoleRequis`. |
| `GET` | `/api/v1/plans/` | `PlansCatalogueView` (`apps/billing/views/cinetpay.py:39`) | `[AllowAny]` | Inchangé (catalogue public des forfaits). |
| `POST` | `/api/v1/cinetpay/initier/` | `InitierPaiementView` (`apps/billing/views/cinetpay.py:55`) | `[IsAuthenticated]` | **F-05** : Exige `administration.abonnement_gerer` (DG seul). |
| `POST` | `/api/v1/cinetpay/annuler/` | `AnnulerPaiementView` (`apps/billing/views/cinetpay.py:122`) | `[IsAuthenticated]` | **F-05** : Exige `administration.abonnement_gerer` (DG seul). |
| `GET` | `/api/v1/cinetpay/statut/<str:transaction_id>/` | `StatutPaiementView` (`apps/billing/views/cinetpay.py:242`) | `[IsAuthenticated]` | **F-05** : Exige `administration.abonnement_gerer` (DG seul). |
| `POST` | `/api/v1/cinetpay/webhook/` | `CinetPayWebhookView` (`apps/billing/views/cinetpay.py:177`) | `[AllowAny]`, vérification HMAC `x-token` | Inchangé (webhook public sécurisé par signature). |
| `POST` | `/api/v1/billing/cinetpay/webhook/` | `CinetPayWebhookView` (`apps/billing/views/cinetpay.py:177`) | `[AllowAny]`, vérification HMAC `x-token` | Inchangé (alias de webhook). |

> **Note sur le changement de plan (R1 / L8-5) :** Il n'existe pas d'autre route dédiée « changer de plan » que `POST /api/v1/cinetpay/initier/` qui prend `plan_code` dans son payload (`InitierPaiementRequestSerializer`). Toute initiation de plan passe par cette route.

---

## 2. P1 (b) Routes sous `/configuration/` (Onboarding)

Fichier de routage : `apps/onboarding/urls.py` monté sous `/api/v1/` dans `config/urls_tenant.py`.

| Méthode | URL | Vue | Garde Actuelle | Cible Lot 8 (F-08) |
|---|---|---|---|---|
| `GET` | `/api/v1/configuration/` | `ConfigurationView` (`apps/onboarding/views/__init__.py:51`) | `[AdministrateurSeul]` (`RoleRequis(ADMIN, DG)`) | **F-08** : Exige `administration.onboarding_suivre` (DG, AD). Suppression de `RoleRequis`. |
| `POST` | `/api/v1/configuration/etapes/<str:code>/valider/` | `FranchirEtapeView` (`apps/onboarding/views/__init__.py:71`) | `[AdministrateurSeul]` (`RoleRequis(ADMIN, DG)`) | **F-08** : Exige `administration.onboarding_suivre` (DG, AD). Suppression de `RoleRequis`. |
| `POST` | `/api/v1/configuration/etapes/<str:code>/passer/` | `PasserEtapeView` (`apps/onboarding/views/__init__.py:98`) | `[AdministrateurSeul]` (`RoleRequis(ADMIN, DG)`) | **F-08** : Exige `administration.onboarding_suivre` (DG, AD). Suppression de `RoleRequis`. |
| `GET` | `/api/v1/configuration/recapitulatif/` | `RecapitulatifView` (`apps/onboarding/views/__init__.py:126`) | `[AdministrateurSeul]` (`RoleRequis(ADMIN, DG)`) | **F-08** : Exige `administration.onboarding_suivre` (DG, AD). Suppression de `RoleRequis`. |
| `POST` | `/api/v1/configuration/terminer/` | `TerminerView` (`apps/onboarding/views/__init__.py:155`) | `[AdministrateurSeul]` (`RoleRequis(ADMIN, DG)`) | **F-08** : Exige `administration.onboarding_suivre` (DG, AD). Suppression de `RoleRequis`. |

---

## 3. P1 (c) Emplacements de Création et de Suppression d'un `Utilisateur`

### A. Créations d'`Utilisateur` (Production)
1. **`apps/tenants/services/inscription.py:505` (`provisionner_schema_entreprise`) :**
   - Crée le premier utilisateur (DG) lors de la création d'une entreprise/tenant.
   - **Action Lot 8 :** Doit enregistrer l'e-mail dans le nouveau modèle public `RegistreEmail`.
2. **`apps/accounts/services/invitations.py:202` (`accepter_invitation`) :**
   - Crée le compte réel du collaborateur lors de l'activation/acceptation du lien d'invitation.
   - **Action Lot 8 :** Doit garantir la présence de la ligne dans `RegistreEmail`.
3. **`apps/accounts/views/collaborateur.py:320` (`ParametresCollaborateurListCreateView.post` et `InvitationListCreateView.post`) :**
   - Crée le collaborateur au statut `INVITE` lors de l'émission d'une invitation ou d'un ajout direct.
   - **Action Lot 8 :** Vérifie `RegistreEmail` avant création (renvoie 400 `email_deja_utilise` si présent). Enregistre dans `RegistreEmail` dans la même transaction.
4. **`apps/accounts/services/utilisateurs.py:24` (`creer_collaborateur_entreprise`) :**
   - Service direct de création d'utilisateur dans un tenant.
   - **Action Lot 8 :** Enregistre dans `RegistreEmail`.
5. **`apps/projets/serializers/__init__.py:645, 662` (`ProjetCreationSerializer`) :**
   - Crée des utilisateurs à la volée s'ils n'existent pas lors de la création d'un projet (`chef_projet_invite` / `conducteur_travaux_invite`).
   - **Action Lot 8 (C-01) :** Conforme à C-01 (l'ajout doit se faire en deux temps dans l'entreprise d'abord) ; tout collaborateur ainsi créé doit vérifier et peupler `RegistreEmail`.
6. **Commandes de gestion :**
   - `apps/accounts/management/commands/creer_super_admin.py:60` (super-administrateur dans le schéma public, hors tenant).
   - `apps/tenants/management/commands/creer_tenant_demo.py:91, 185` (fixtures de démonstration).

### B. Suppressions et Départs d'`Utilisateur` (Production)
1. **`apps/accounts/services/utilisateurs.py:38` (`desactiver_collaborateur_plateforme`) :**
   - **Point central unique du départ (C-02).**
   - Comportement actuel : passe `statut = DESACTIVE`, `is_active = False`, `supprime_le = timezone.now()`. Clôture les affectations chantiers (`est_actif = False`). Détache `chef_projet = None` et `conducteur_travaux = None`.
   - **Modifications C-02 & Q1/Q2/Q3/Q4 pour le Lot 8 :**
     - **Q1 (Libération e-mail) :** Conserver `email_origine = collaborateur.email` puis renommer `email = f"ancien+{collaborateur.id}@depart.invalide"`.
     - **Q4 (Registre global) :** Supprimer la ligne de `RegistreEmail` dans le schéma public.
     - **Q2 & L8-6 (Indicateur sans chef) :** Positionner `sans_chef_projet = True` sur tous les projets dont il était chef de projet **ou** conducteur de travaux.
     - **Q3 (Alerte DG) :** Si au moins un projet est orphelin, envoyer un e-mail au DG via `transaction.on_commit`.
2. **`apps/accounts/views/collaborateur.py:650` (`ParametresCollaborateurDetailView.delete`) :**
   - Route `DELETE /api/v1/parametres/collaborateurs/{pk}/` (et `/api/v1/invitations/{pk}/`).
   - Appelle `desactiver_collaborateur_plateforme()`.
3. **`apps/accounts/services/roles.py:650` (`supprimer_role_personnalise`) :**
   - Si l'option choisie est de désactiver les utilisateurs liés au rôle personnalisé supprimé, appelle `desactiver_collaborateur_plateforme()`.

---

## 4. P1 (d) Tests Existants à Adapter ou Supprimer (Règle G-05)

Les tests existants suivants reflètent un comportement antérieur et doivent être adaptés selon G-05 :

1. **`apps/tenants/tests/test_entreprise_view.py:122` (`test_modification_entreprise_par_role`) :**
   - *Ancien comportement :* `(RoleGlobal.ADMIN, status.HTTP_200_OK)` autorisait l'administrateur (AD) à modifier l'entreprise via PATCH `/api/v1/entreprise/`.
   - *Règle F-07 & L8-8 :* L'écriture exige `administration.entreprise_modifier` (détenue par le **DG seul**). L'AD doit désormais recevoir **403**.
   - *Action :* Adapter l'assertion pour AD à `status.HTTP_403_FORBIDDEN`.
2. **`apps/tenants/tests/test_configuration_entreprise_view.py:80` (`test_post_configuration_entreprise_par_admin`) :**
   - *Ancien comportement :* Un administrateur (AD) pouvait enregistrer la configuration d'entreprise en `POST /api/v1/parametres/configuration/` (HTTP 200).
   - *Règle F-07 & L8-8 :* Écriture réservée au DG seul. L'AD doit recevoir **403**.
   - *Action :* Adapter le test pour vérifier le refus 403 pour l'AD (ou exécuter le test autorisé avec `dg_demo`).
3. **`apps/billing/tests/test_cinetpay.py` (fixture `entreprise_et_admin:58` et tests associés) :**
   - *Ancien comportement :* La fixture crée `admin` avec `role_global = RoleGlobal.ADMIN`, et les tests appellent `POST /api/v1/cinetpay/initier/` avec succès.
   - *Règle F-05 :* `cinetpay/initier` exige `administration.abonnement_gerer` (détenu par le **DG seul** ; refus 403 pour AD).
   - *Action :* Adapter la fixture pour que l'utilisateur appelant les endpoints CinetPay possède le rôle de Directeur Général (`role_global = RoleGlobal.DIRECTEUR_GENERAL` / `is_owner = True`).
4. **`apps/billing/tests/test_factures.py:23` (fixture `facture_api`) :**
   - *Ancien comportement :* Utilise `entreprise_et_admin["admin"]` (AD) pour initier un paiement CinetPay et créer une facture.
   - *Règle F-05 :* Réservé au DG.
   - *Action :* Adapter l'authentification de la fixture vers le DG.
5. **`apps/referentiels/tests/test_api_modules.py:61-120` (`TestApiCatalogueModules`) :**
   - *Ancien comportement :* Un collaborateur ordinaire (`RoleGlobal.CONDUCTEUR_TRAVAUX`) recevait l'intégralité des 5 modules du catalogue et toutes leurs permissions.
   - *Règle F-06 :* `GET /api/v1/modules/` ne renvoie à chacun que ses propres modules et permissions effectifs (filtrage par rôle effectif de l'utilisateur).
   - *Action :* Adapter les assertions pour vérifier les modules et permissions réels du profil, ou faire tester le catalogue complet par un DG.
6. **`tests/acceptation/lot3/test_d08_garde_unique.py:159` :**
   - *Ancien constat :* Tolérait `RoleRequis` dans `billing`, `onboarding`, `tenants`.
   - *Règle L8-7 :* `RoleRequis` disparaît totalement du code applicatif (0 occurrence hors `apps/core/permissions.py`).

---

## 5. P2 Réglage des Tests (Tâches de fond et Courriels)

Vérifié dans `config/settings/test.py` :
- **Tâches de fond Celery :** `CELERY_TASK_ALWAYS_EAGER = True` (ligne 11). Toutes les tâches Celery s'exécutent de façon synchrone dans le fil d'exécution du test.
- **Backend d'e-mail :** `EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"` (ligne 12).
- **Interception des courriels en test :** Tous les courriels émis sont collectés en mémoire dans `django.core.mail.outbox`.
- **Rappels de transaction (`transaction.on_commit`) :** En test unitaire Django standard (`TestCase` ou `pytest.mark.django_db`), les hooks `transaction.on_commit` ne sont exécutés que si la transaction est validée ou si la fabrique invoque `django.db.transaction.on_commit` manuellement ou utilise `CaptureOnCommitCallbacks`.

---

## 6. P3 Formats des Requêtes et Routes

- **Connexion :**
  - Route : `POST /api/v1/auth/token/`
  - Corps : `{"email": "...", "mot_de_passe": "..."}`
  - Réponse succès : `200 OK` avec `{"access": "...", "refresh": "..."}`
- **Invitations et Création Collaborateurs :**
  - Routes : `POST /api/v1/invitations/` et `POST /api/v1/parametres/collaborateurs/`
  - Corps :
    ```json
    {
      "email": "collab@entreprise.ci",
      "nom": "Kouassi",
      "prenom": "Affoué",
      "telephone": "+2250102030405",
      "role_global": "VI"
    }
    ```
    (ou `"role_personnalise_id": "<uuid>"`)
- **Factures :**
  - Liste : `GET /api/v1/factures/`
  - Détail : `GET /api/v1/factures/{pk}/`
  - Téléchargement PDF : `GET /api/v1/factures/{pk}/pdf/`

---

## 7. P4 Relevé des Champs `Plan` et État d'Expiration

### A. Modèle `Plan` (`apps/billing/models/__init__.py:27`)
- `code` : BATISSEUR, MAITRE_OEUVRE, PROMOTEUR, STARTER, PRO, ENTERPRISE
- `libelle` : CharField(100)
- `limite_projets` : IntegerField (null=True -> illimité)
- `limite_utilisateurs` : IntegerField (null=True -> illimité)
- `limite_stockage_mo` : IntegerField (null=True -> illimité)
- `acces_ia` : BooleanField(default=False)
- `est_actif` : BooleanField(default=True)

### B. Activation de l'État Expiré en Test
Dans `apps/billing/middleware.py:117-129` (`LectureSeuleAbonnementMiddleware.en_lecture_seule`), l'abonnement est considéré comme expiré si :
1. `abonnement.lecture_seule_depuis is not None`
2. Ou `abonnement.statut in (Abonnement.Statut.SUSPENDU, Abonnement.Statut.RESILIE, Abonnement.Statut.IMPAYE)`
3. Ou `abonnement.statut == Abonnement.Statut.ESSAI` et `abonnement.fin_essai < timezone.localdate()`.

Pour la fabrique `expirer_abonnement()` :
```python
abonnement.statut = Abonnement.Statut.SUSPENDU
abonnement.lecture_seule_depuis = timezone.now()
abonnement.save(update_fields=["statut", "lecture_seule_depuis"])
```
Pour la fabrique `restaurer_abonnement()` :
```python
abonnement.statut = Abonnement.Statut.ACTIF
abonnement.lecture_seule_depuis = None
abonnement.save(update_fields=["statut", "lecture_seule_depuis"])
```
