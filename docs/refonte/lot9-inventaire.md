# Inventaire du Lot 9 : Propagation super admin, plateforme

Règles ciblées : A-05, A-06, A-07, A-08, A-09, A-10, A-11, A-14, H-01, H-02.

---

## P1.a — Toutes les routes d'écriture sous `/admins/` et `/admin/` avec journalisation actuelle

Inventaire exhaustif des routes sous `/admins/` et `/admin/` supportant les méthodes HTTP d'écriture (`POST`, `PUT`, `PATCH`, `DELETE`), avec leur vue associée et l'état actuel de leur journalisation dans `JournalPlateforme` :

| Méthode | Route URL | Vue DRF | Écrit dans `JournalPlateforme` ? | Action journalisée |
|---|---|---|---|---|
| POST | `/api/v1/admins/inscriptions/{pk}/approuver/` | `ApprouverInscriptionView` | OUI (`inscriptions.py:108`) | `APPROBATION_INSCRIPTION` |
| POST | `/api/v1/admins/inscriptions/{pk}/refuser/` | `RefuserInscriptionView` | OUI (`inscriptions.py:165`) | `REFUS_INSCRIPTION` |
| POST | `/api/v1/admins/connexion/` | `ConnexionAdminView` | OUI (`auth.py:121`) | `CONNEXION_SUPER_ADMIN` |
| POST | `/api/v1/admins/deconnexion/` | `DeconnexionAdminView` | OUI (`auth.py:190`) | `DECONNEXION_SUPER_ADMIN` |
| POST | `/api/v1/admins/token/refresh/` | `RenouvellementAdminView` | NON | Rotation JWT SimpleJWT |
| POST | `/api/v1/admins/mot-de-passe/demande/` | `DemandeReinitialisationAdminView` | OUI (`reinitialisation.py:73`) | `DEMANDE_REINITIALISATION_MDP` |
| POST | `/api/v1/admins/mot-de-passe/verifier/` | `VerificationJetonAdminView` | NON | Contrôle jeton temporaire |
| POST | `/api/v1/admins/mot-de-passe/reinitialiser/` | `ReinitialisationAdminView` | OUI (`reinitialisation.py:160`) | `REINITIALISATION_MDP_SUCCES` |
| POST | `/api/v1/admins/entreprises/{entreprise_id}/assistance/` | `DemarrerAssistanceView` | OUI (`impersonation.py:170`) | `CONNEXION_ASSISTANCE` |
| POST | `/api/v1/admins/assistance/deconnexion/` | `DeconnexionAssistanceView` | OUI (`impersonation.py:261`) | `DECONNEXION_ASSISTANCE` |
| POST | `/api/v1/admins/clients/{client_id}/suspendre/` | `SuspendreClientPlateformeView` | OUI (`clients.py:126`) | `SUSPENSION_CLIENT` |
| POST | `/api/v1/admins/clients/{client_id}/reactiver/` | `ReactiverClientPlateformeView` | OUI (`clients.py:197`) | `REACTIVATION_CLIENT` |
| PATCH / POST | `/api/v1/admins/clients/{client_id}/abonnement/` | `ChangerPlanClientPlateformeView` | OUI (`clients.py:276`) | `CHANGEMENT_PLAN_CLIENT` |
| POST | `/api/v1/admin/modules/` et `/admins/modules/` | `AdminModuleListCreateView` | NON | Création catalogue |
| PUT / PATCH / DELETE | `/api/v1/admin/modules/{pk}/` et `/admins/modules/{pk}/` | `AdminModuleDetailUpdateDeleteView` | NON | Modif / Soft delete catalogue |
| POST | `/api/v1/admin/modules/{pk}/permissions/` et `/admins/modules/{pk}/permissions/` | `AdminModuleAffecterPermissionsView` | NON | Rattachement permissions |
| POST | `/api/v1/admin/modules/{pk}/desactiver/` et `/admins/modules/{pk}/desactiver/` | `AdminModuleDesactiverView` | NON | Désactivation globale plateforme |
| POST | `/api/v1/admin/modules/{pk}/reactiver/` et `/admins/modules/{pk}/reactiver/` | `AdminModuleReactiverView` | NON | Réactivation globale plateforme |
| POST | `/api/v1/admin/permissions/` et `/admins/permissions/` | `AdminPermissionListCreateView` | NON | Création catalogue |
| PUT / PATCH / DELETE | `/api/v1/admin/permissions/{pk}/` et `/admins/permissions/{pk}/` | `AdminPermissionDetailUpdateDeleteView` | NON | Modif / Soft delete catalogue |
| POST | `/api/v1/admin/permissions/{pk}/modules/` et `/admins/permissions/{pk}/modules/` | `AdminPermissionAffecterModulesView` | NON | Rattachement modules |
| POST | `/api/v1/admins/comptes/` | `ComptesAdministrateursListCreateView` | OUI (`comptes.py:84`) | `CREATION_COMPTE_ADMIN` |
| POST | `/api/v1/admins/comptes/{pk}/suspendre/` | `SuspendreCompteAdministrateurView` | OUI (`comptes.py:150`) | `SUSPENSION_COMPTE_ADMIN` |
| POST | `/api/v1/admins/comptes/{pk}/reactiver/` | `ReactiverCompteAdministrateurView` | OUI (`comptes.py:210`) | `REACTIVATION_COMPTE_ADMIN` |
| POST / DELETE | `/api/v1/admins/moi/photo/` | `AdminPhotoMoiView` | NON | Mise à jour avatar staff |
| POST | `/api/v1/admins/moi/mot-de-passe/` | `AdminChangerMotDePasseMoiView` | OUI (`comptes.py:260`) | `CHANGEMENT_MDP_ADMIN` |

**Constat d'alignement avec Q7 / H-02 :**
Pour satisfaire H-02 (« Toute écriture de l'API `/admins/` crée exactement une entrée de `JournalPlateforme` »), les routes de gestion du catalogue (`modules` et `permissions`), ainsi que les futures routes d'activation/désactivation de modules par client, doivent toutes journaliser leur écriture dans `JournalPlateforme`.

---

## P1.b — Routes d'assistance et comportement du renouvellement de jeton

1. **Début d'assistance (`H-01`) :**
   - Route : `POST /api/v1/admins/entreprises/{entreprise_id}/assistance/`
   - Vue : `DemarrerAssistanceView` (`apps/platform_admin/views/impersonation.py:35`)
   - Service : `demarrer_session_assistance()` (`apps/platform_admin/services/impersonation.py:96`)
   - Jeton émis : SimpleJWT `AccessToken` (durée 1 heure stricte) avec claims `is_impersonation=True`, `read_only=True`, `sid`, `impersonateur_id`, `schema`.
   - **Aucun `RefreshToken` n'est émis.**
   - Traçabilité existante : `JournalPlateforme` (`action="CONNEXION_ASSISTANCE"`) dans `public` et `JournalAudit` (`action="ASSISTANCE"`) dans le schéma du tenant.
   - **Manque actuel :** Aucun e-mail envoyé au DG à l'ouverture de session (requis par H-01 / I-04).

2. **Fin d'assistance (`H-01`) :**
   - Route : `POST /api/v1/admins/assistance/deconnexion/`
   - Vue : `DeconnexionAssistanceView` (`apps/platform_admin/views/impersonation.py:166`)
   - Service : `clore_session_assistance()` (`apps/platform_admin/services/impersonation.py:251`)
   - Traçabilité existante : `JournalPlateforme` (`action="DECONNEXION_ASSISTANCE"`) et `JournalAudit` (`action="DECONNEXION"`).

3. **Renouvellement de jeton (`L9-6`) :**
   - Routes de rafraîchissement : `POST /api/v1/admins/token/refresh/` et `POST /api/v1/auth/token/refresh/`.
   - Ces routes attendent un champ `refresh` (`RefreshToken`).
   - Comme la session d'assistance n'émet qu'un `AccessToken`, le renouvellement est intrinsèquement impossible.
   - De surcroît, le middleware `LectureSeuleAssistanceMiddleware` intercepte toute requête d'écriture en mode assistance, et un `AccessToken` d'assistance passé comme `refresh` est rejeté en 401 par le serializer SimpleJWT.

---

## P1.c — Routes admin pour : modules par client, modèles de rôles, permissions catalogue

1. **Modules par client (`A-10`, `A-11`) :**
   - **Constat :** Il n'existe actuellement **aucune route** sous `/api/v1/admins/clients/{client_id}/` pour activer ou désactiver un module pour une entreprise spécifique.
   - **Décision Claude Q3 :** Introduction des routes dédiées :
     - `POST /api/v1/admins/clients/{client_id}/modules/{module_id}/activer/`
     - `POST /api/v1/admins/clients/{client_id}/modules/{module_id}/desactiver/`
   - Ces routes manipuleront `EntrepriseModule` (`catalogue_entreprise_module`), appliqueront la règle A-11 (copie unique par défaut pour rôles système, ligne vide pour rôles personnalisés, rien pour le DG calculé), et enverront la notification par e-mail au DG (`A-14`).

2. **Modèles de rôles (`ModeleRole`, `ModeleRoleModule`) :**
   - **Constat :** Il n'existe **aucune route d'API** sous `/admins/` pour administrer les modèles de rôles. Ils sont peuplés par la migration de données `0004_peupler_modeles_roles.py`.
   - **Décision Claude Q1 :** Le service idempotent `propager_roles_systeme()` sera exposé via la commande Django `python manage.py propager_roles_systeme`.

3. **Permissions du catalogue (`A-05`, `A-06`) :**
   - Routes existantes :
     - `GET`, `POST /api/v1/admins/permissions/` (`AdminPermissionListCreateView`)
     - `GET`, `PUT`, `PATCH`, `DELETE /api/v1/admins/permissions/{pk}/` (`AdminPermissionDetailUpdateDeleteView`)
     - `POST /api/v1/admins/permissions/{pk}/modules/` (`AdminPermissionAffecterModulesView`)

---

## P1.d — Fonctions de `catalogue.py` qui ajoutent aux rôles (à supprimer/adapter selon A-05 / R2)

Dans `apps/platform_admin/services/catalogue.py` :
1. `propager_creation_permission` (lignes 483-490) :
   ```python
   roles_direction = Role.objects.filter(code__in=["DG", "DIRECTEUR_GENERAL"], supprime_le__isnull=True)
   for role in roles_direction:
       for rmp in RoleModulePermission.objects.filter(role=role, module__in=mods_tenant, supprime_le__isnull=True):
           rmp.permissions.add(perm_tenant)
   ```
   -> **À SUPPRIMER IMPÉRATIVEMENT** : Enfreint directement la règle A-05 (« Une nouvelle permission devient cochable par les DG. Elle n'est pas ajoutée aux rôles. »).
2. `propager_creation_module` (lignes 180-186) :
   Injectait également les permissions au rôle DG dans `RoleModulePermission`. Le DG ayant désormais ses droits calculés dynamiquement (`est_dg`, règle B-03), cette logique obsolète doit être retirée.

---

## P1.e — Commande et fonction de synchronisation du catalogue

- Commande : `apps/catalogue/management/commands/synchroniser_catalogue_permissions.py` (`python manage.py synchroniser_catalogue_permissions`).
- Source unique : `apps.core.registre_permissions.REGISTRE`.
- Comportement :
  - Opère exclusivement dans le schéma `public`.
  - Crée ou met à jour les entrées de `CataloguePermission`.
  - Désactive (`est_actif=False`) les permissions qui ne figurent plus dans le `REGISTRE` (A-06).
  - Ne modifie **aucun rôle** dans aucun tenant (respecte A-05).
  - Idempotente.
  - Conforme à L9-3 : écrit dans `JournalPlateforme`, n'envoie aucun e-mail aux DG.

---

## P1.f — Tests existants à adapter ou supprimer (G-05)

1. `apps/platform_admin/tests/test_admin_permissions.py:73` (`test_creer_permission_et_propagation_ciblee_dg_admin`) :
   - Ce test vérifiait que la création d'une permission l'attribuait automatiquement au rôle stocké du DG dans `RoleModulePermission` (`assert rmp.permissions.filter(code="AUDIT").exists()`).
   - **Adaptation requise par A-05 / R2 :** Le test doit être adapté pour vérifier l'exact inverse : la permission n'est ajoutée à **aucun rôle stocké** (`assert not rmp.permissions.filter(code="AUDIT").exists()`), mais le DG y a accès par calcul dynamique (`est_dg(u)`), tandis que l'AD et les autres rôles ne l'ont pas tant qu'elle n'est pas cochée.
