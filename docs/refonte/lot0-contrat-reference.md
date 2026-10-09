# Lot 0 — Contrat de référence backend (rôles, collaborateurs, modules, permissions)

Établi le 9 octobre 2026 à partir du schéma OpenAPI généré (`manage.py spectacular`, urlconfs tenant et
public), de `docs/notes-changement-api.md` et de `docs/refonte/cahier-regles.md`. À relire avant chaque
lot frontend. Les routes sont relatives à `/api/v1`. Tenant = sous-domaine de l'entreprise ; plateforme =
domaine public (`apiAdministration` côté frontend).

## 1. Ce qui a changé de nature : le modèle de droits

Le backend ne raisonne plus en « niveau 0-3 » ni en « lecture / saisie / validation » (cahier A-03, A-04).

- **Une permission = un code `module.verbe`** (`projets.lire`, `chantier.rediger`, `chantier.valider`…).
  Le REGISTRE du code est la seule source (A-01) ; le module est le préfixe du code (A-02).
- **Les droits d'un rôle = une liste de codes à cocher par module** (A-04).
- **`permissions_modules` (rôle)** renvoie `{module: [codes]}` avec, pour compatibilité, des alias
  ajoutés à la suite des codes réels (`lecture`, `LECTURE`, `saisie`, `ECRITURE`…). Les alias sont
  transitoires (G-02) : le frontend lit les codes réels `module.verbe` et ignore les alias.
- **`habilitations` (profil)** reste un niveau 0-3 par module, déduit : compatibilité en lecture seule,
  jamais une source de décision (le serveur reste l'autorité).
- **Rôle unique** (B-01) : `role_global` est un alias en lecture seule du rôle ; `role_personnalise`
  n'existe plus en base. 10 rôles système : `DG AD DO DF CP CT CC MAG BAI VI`.
- **Portée d'un rôle** : `ENTREPRISE` (voit tous les projets) ou `PROJET` (voit ses projets affectés).
- **Surcharges de droits par projet : supprimées** (E-06). La route `projets/{id}/permissions-roles/`
  n'existe plus (lot 5 de la refonte, migration 0027). L'affectation ne porte plus de rôle.

## 2. Espace entreprise (tenant)

| Route | Entrée | Sortie | Codes / erreurs notables |
|---|---|---|---|
| `GET /modules/` | — | `[ModuleItem{id, code, libelle, description, ordre, icone, statut, acces_par_defaut, permissions[{id,code,libelle,description,ordre}], permissions_codes}]` | `niveaux_supportes` déprécié |
| `GET /parametres/roles/` | — | `[Role{id, code, libelle, description, est_systeme, est_actif, portee, nb_utilisateurs, modules, permissions_modules, avertissements}]` | 403 sans `administration.roles_gerer` |
| `GET /parametres/roles/{id}/` | — | `RoleDetail` = `Role` + `comptage{utilisateurs, affectations, total}` | idem |
| `POST /parametres/roles/` | `{code*, libelle*, description, portee (défaut PROJET), permissions_modules, permissions[codes]}` | `RoleDetail` (201) | 400 code déjà pris ; 403 `permission_hors_perimetre_ad` |
| `PATCH /parametres/roles/{id}/` | `{libelle, description, portee, confirmer, permissions_modules, permissions}` | `RoleDetail` | 403 `modification_role_systeme_interdite` (non-DG), rôle DG intouchable ; **409 `confirmation_requise` + `{personnes_touchees: N}`** si `portee` change sans `confirmer: true` |
| `POST /parametres/roles/{id}/supprimer/` | `{role_substitution_id \| role_reassignation_id \| reassigner_vers_role_id, supprimer_collaborateurs}` | objet de bilan | rôle système non supprimable |
| `/roles/…` | mêmes signatures | mêmes sorties | alias strict de `/parametres/roles/` (F-02) : n'utiliser que `/parametres/roles/` |
| `GET /parametres/collaborateurs/` | — | `[Collaborateur{id, email, nom, prenom, nom_complet, telephone, role_global, role_global_libelle, role_propose, role_personnalise, statut, is_owner, cree_le, projets[], lien_activation, avatar_url, derniere_connexion}]` | — |
| `POST /parametres/collaborateurs/` | `{email*, nom*, prenom, telephone, role_global \| role_personnalise_id}` | `Collaborateur` (201) | 400 `role_ambigu` si les deux rôles sont fournis ; 403 AD qui attribue DG/AD/DF ou hors périmètre |
| `GET /parametres/collaborateurs/{id}/` | — | `Collaborateur` | — |
| `PATCH /parametres/collaborateurs/{id}/` | `{role_global \| role_personnalise_id}` | `Collaborateur` | 403 sur DG, sur un AD par un AD |
| `POST …/{id}/suspendre/` · `…/reactiver/` | — | `Collaborateur` | 400 auto-suspension ; 403 DG/AD protégés ; 409 état identique |
| `DELETE …/{id}/` | — | bilan | 403 DG/AD protégés |
| `GET /auth/profil/` (= `/utilisateurs/moi/`) | — | `{id, email, nom, prenom, nom_complet, telephone, avatar_url, initiales, role_global, role_libelle, role_personnalise, is_dg, is_owner, statut, langue, schema, entreprise, habilitations, permissions…}` | `habilitations` : niveau 0-3 déduit |
| `POST /invitations/verifier/` · `/invitations/accepter/` | `{jeton}` · `{jeton, nom, prenom, mot_de_passe}` | `ContenuInvitation` · jetons + `utilisateur` | — |
| `GET /projets/{id}/affectations/` | — | affectations (PII omis sans `projets.affecter_membres`/`gerer_equipes`) | 403 `chantier_non_affecte` |
| `GET /projets/{id}/collaborateurs-affectables/` | — | `[{id, nom, role}]` | portée PROJET seulement |

## 3. Espace super admin (plateforme, préfixe `/admins/`, jamais les alias sans préfixe ni `/admin/`)

| Route | Entrée | Sortie | Codes |
|---|---|---|---|
| `POST /admins/connexion/` | `{email, mot_de_passe, origine}` | `{access, refresh, expire_dans, utilisateur}` | 401 |
| `POST /admins/mot-de-passe/demande/` | `{email}` | — | 202, 400 |
| `POST /admins/mot-de-passe/verifier/` | `{jeton}` | `{email, motif, expire_dans, url_connexion}` | 410 jeton expiré |
| `POST /admins/mot-de-passe/reinitialiser/` | `{jeton, mot_de_passe}` | `{message}` | 400, 410 |
| `GET/PATCH /admins/moi/` · `PATCH /admins/moi/photo/` · `POST /admins/moi/mot-de-passe/` | profil | `ProfilCompletAdmin{id, email, nom, prenom, telephone, photo_url, role_global, role_libelle, is_superuser, is_staff, langue, schema}` | 400 |
| `GET/POST /admins/comptes/` | `{prenom*, nom*, email*, role}` | `Compte{id, email, nom, prenom, nom_complet, telephone, role, statut, cree_le, derniere_connexion}` | — |
| `POST /admins/comptes/{id}/suspendre/` · `…/reactiver/` | — | `Compte` | 400 auto-suspension |
| `GET/POST /admins/modules/`, `GET/PATCH/DELETE …/{id}/` | `{code, libelle*, description, ordre, icone, est_actif, statut, permissions[codes], acces_par_defaut}` | `Module{id, code, libelle, description, ordre, icone, est_actif, statut, acces_par_defaut, permissions, permissions_codes, cree_le, modifie_le}` | — |
| `POST /admins/modules/{id}/desactiver/` · `…/reactiver/` | — | `Module` | 409 état identique |
| `PUT /admins/modules/{id}/permissions/` | `{permissions*}` | `Module` | — |
| `GET /admins/permissions/` · `GET …/{id}/` | — | `Permission{id, code, libelle, description, ordre, est_actif, modules, modules_codes, cree_le, modifie_le}` | — |
| `POST/PATCH/DELETE /admins/permissions/…`, `POST …/{id}/modules/` | — | — | **À vérifier au lot 6** : la règle A-01 (code inconnu du REGISTRE → 400) et A-02 (module = préfixe du code) limitent ce que le super admin peut faire. |
| `GET /admins/clients/` · `GET …/{id}/` | — | `Client{id, raison_sociale, nom_commercial, slug, pays, ville, email_contact, telephone_contact, statut, cree_le, active_le, nb_utilisateurs, nb_projets, abonnement}` | — |
| `POST /admins/clients/{id}/suspendre/` | `{motif*}` (≥ 3 car.) | `Client` | 409 déjà suspendu |
| `POST /admins/clients/{id}/reactiver/` | — | `Client` | 409 |
| `POST\|PATCH /admins/clients/{id}/abonnement/` | `{plan_code*}` | `Client` | 400 |
| `POST /admins/clients/{id}/modules/{module_id}/activer\|desactiver/` | — | — | 404 ; notifie le DG par e-mail (A-14) |
| `GET /admins/entreprises/{id}/utilisateurs/` · `POST …/assistance/` | `{motif*, utilisateur_id}` | utilisateurs · jetons d'assistance | session d'assistance en lecture seule : 403 `ecriture_interdite_assistance` |
| `GET /admins/indicateurs/`, `…/tendances/`, `…/evolution/` | — | indicateurs | — |

## 4. Décisions sur les routes douteuses du super admin

| Appel frontend | Constat | Décision |
|---|---|---|
| `POST /auth/mot-de-passe/oublie/` (`apiAdministration`) | N'existe nulle part. Le flux plateforme est `/admins/mot-de-passe/{demande,verifier,reinitialiser}/`. | **Corriger le frontend** : `demande` (202), puis `verifier` et `reinitialiser` par jeton. |
| `PUT /admins/parametres/tarifs/` | Aucun endpoint. Le modèle `billing.Plan` existe (prix mensuel/annuel en montant, `limite_projets`, `limite_utilisateurs`, `limite_stockage_mo`, `acces_ia`, `est_actif`) mais aucune écriture exposée, et les champs diffèrent de ceux du frontend (`limite_chantiers`, centimes, remise, avantages). | **Hors périmètre de ce plan**, noté comme lot 8 (backend d'abord). En attendant, la sauvegarde reste simulée avec la bannière de simulation en développement, et **désactivée avec un message explicite en production** : ne jamais afficher un succès qui n'écrit rien. |
| `PATCH /admins/parametres/identite/` | Aucun endpoint ni modèle d'identité de plateforme. | Même décision que les tarifs. |
| `PATCH /clients/{id}/abonnement/`, `POST /clients/{id}/suspendre/` (sans `/admins/`) | Alias existants mais redondants. | Utiliser `/admins/clients/...`. |

## 5. Écarts de documentation relevés

- `notes-changement-api.md` (lot 9) cite `/admins/modeles-roles/`, `/admins/catalogue-permissions/` et
  `/admins/assistance/connexion/` : absents de `platform_admin/urls.py` (l'assistance est sous
  `/admins/entreprises/{id}/assistance/`). Le code fait foi.
- `MANUEL_ENTREPRISE_ALIGNEMENT_FRONTEND.pdf` décrit `ProjetPermissionsRolesView` et la conversion
  `acces` ↔ `niveau` : la vue a été supprimée ensuite (E-06). Le test
  `apps/accounts/tests/test_alignement_entreprise_frontend.py` y fait encore référence : à vérifier au
  lot 7.
- Le catalogue entreprise (`GET /modules/`) n'expose que les modules actifs de l'entreprise (A-10/A-11) :
  la liste de modules du frontend doit en dépendre, pas d'une constante.
