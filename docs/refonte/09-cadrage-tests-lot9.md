# Cadrage des tests, LOT 9 : propagation super admin, plateforme
Règles : A-05, A-06, A-07, A-08, A-09, A-10, A-11, A-14, H-01, H-02.
Marqueurs : `carac` (doit déjà passer à la fin du lot 8) et `regle` (introduit par le lot 9, échoue avant).
Document pour Durel et Claude.

---

## 1. Réponses aux sept questions

| # | Décision |
|---|---|
| **Q1** Propagation d'un rôle système (A-07) | **Un seul service** `propager_roles_systeme()`, idempotent, appelé de deux façons : (a) par la **commande** `python manage.py propager_roles_systeme` (déploiements, rattrapage) ; (b) automatiquement à la création d'un `ModeleRole` par l'API super admin, si cette route existe (P1). Pour chaque entreprise existante, il crée **seulement les rôles système manquants** (jamais de modification d'un rôle existant). Le rôle reçoit : code, nom, portée et `est_systeme = True` du modèle ; et, pour chaque module **actif dans cette entreprise**, les permissions par défaut de `ModeleRoleModule`. Les modules inactifs n'ont aucune ligne (ils en recevront une à leur activation, A-11). |
| **Q2** Conflit de code ou de nom (A-09) | Le rôle système l'emporte. Le rôle **personnalisé** en conflit est renommé : code `{code}_perso` (puis `{code}_perso2`, `_perso3`… si pris), nom `{nom} (personnalisé)` (puis `(personnalisé 2)`…). Conflit sur le code seul, le nom seul (comparaison insensible à la casse) ou les deux : même renommage des deux champs. Identifiant, collaborateurs, portée et permissions : **inchangés**. Le renommage est mentionné dans l'e-mail et l'audit du DG. |
| **Q3** Activation d'un module (A-11) | Routes : `POST /api/v1/admins/clients/{client_id}/modules/{module_id}/activer/` et `.../desactiver/` (on reprend la route existante si P1 en trouve une). **Règle unique de copie : pour chaque rôle qui n'a pas encore de ligne pour ce module** ; un rôle système reçoit les défauts du modèle, un rôle personnalisé reçoit une ligne **explicite vide**. Un rôle qui a déjà une ligne n'est pas touché : c'est ce qui rend la **réactivation** sans effet et l'**idempotence** gratuite. Le DG est calculé et ne reçoit pas de ligne. |
| **Q4** Désactivation (A-10) | Oui : permissions ignorées immédiatement par `permissions_effectives()`, lignes `RoleModulePermission` **intactes**, retrouvées identiques à la réactivation (sans nouvelle copie). Les autres entreprises ne sont pas affectées. |
| **Q5** Nouvelle permission (A-05, A-06) | Oui : une permission synchronisée devient **cochable** par le DG et n'est ajoutée à **aucun rôle stocké**, y compris AD (le code historique de `catalogue.py` qui l'ajoutait au DG et à l'AD doit disparaître). Le DG, rôle calculé (B-03), la possède de fait. Désactivée (`est_actif = False`), elle disparaît **immédiatement** des permissions effectives de tous les rôles de toutes les entreprises (comportement du lot 1 : non-régression). |
| **Q6** E-mails au DG (A-14, H-01) | Destinataire : l'utilisateur actif pour lequel `est_dg` est vrai **dans le schéma de l'entreprise concernée**. Déclencheurs : (a) début de session d'assistance, (b) activation ou désactivation d'un module d'une entreprise, (c) propagation d'un rôle système dans l'entreprise (avec les renommages d'A-09), (d) désactivation d'une permission du catalogue par l'API super admin. **Un seul e-mail par entreprise et par action**, envoyé par `transaction.on_commit`, zéro e-mail si la transaction est annulée. Sujets fixes : « Session d'assistance ouverte sur votre espace » (a) ; « Modification de votre espace par l'administration de la plateforme » (b, c, d). Corps : nature du changement, module, rôles, permissions concernées, e-mail du super admin acteur. |
| **Q7** Un seul niveau (H-02) | Oui. `is_staff` **ou** `is_superuser` d'un utilisateur du schéma public suffit : aucun traitement différencié. Toute **écriture** de l'API `/admins/` (POST, PUT, PATCH, DELETE), ainsi que le début et la fin d'une assistance, crée **exactement une** entrée de `JournalPlateforme` (acteur, action, cible, détails, date). Les lectures et les requêtes refusées (401, 403, 400) ne sont pas journalisées. |

---

## 2. Décisions complémentaires `[D]`

| # | Sujet | Décision |
|---|---|---|
| L9-1 | Journal du tenant | Chaque action qui **modifie une entreprise** (b, c, d, début et fin d'assistance) crée exactement **une** entrée de `JournalAudit` dans le schéma de cette entreprise. |
| L9-2 | Modification d'un modèle (A-08) | Ne touche aucune entreprise : ni audit de tenant, ni e-mail. Seul `JournalPlateforme` enregistre l'écriture. |
| L9-3 | Commande de synchronisation du catalogue (déploiement) | Écrit dans `JournalPlateforme` seulement. **Aucun e-mail** aux DG : seules les actions délibérées d'un super admin notifient. |
| L9-4 | DG absent ou désactivé | Pas d'e-mail, pas d'erreur ; l'action réussit et l'audit est écrit. |
| L9-5 | Fin d'une session d'assistance | = déconnexion explicite (`/api/v1/admins/assistance/deconnexion/`). L'expiration à une heure sans déconnexion n'écrit **pas** d'entrée de fin ; l'entrée de début porte l'heure d'expiration. Limite assumée. |
| L9-6 | Renouvellement de jeton d'assistance | Interdit : le jeton d'assistance ne peut être renouvelé. |
| L9-7 | Activation d'un module déjà actif ou désactivation d'un module déjà inactif | 200, aucun changement, **aucun** e-mail, aucune entrée d'audit. |
| L9-8 | Client ou module inexistant | 404. Non super admin : 403, même pour un DG. |

---

## 3. Texte de H-01 porté dans le cahier (levée de l'exception au gel)

> **H-01 [V] Impersonation (session d'assistance).**
> - Le super admin ouvre une session d'assistance sur une entreprise. Le jeton porte `is_impersonation` et `read_only`, vaut une heure et n'est pas renouvelable.
> - Toute requête POST, PUT, PATCH ou DELETE faite avec ce jeton est refusée en 403, code `ecriture_interdite_assistance`, sauf la déconnexion d'assistance. Les lectures passent.
> - Le début et la fin (déconnexion explicite) de la session sont journalisés dans `JournalPlateforme` et dans le `JournalAudit` de l'entreprise. L'expiration sans déconnexion n'écrit pas d'entrée de fin.
> - Au début de la session, un e-mail part au DG de l'entreprise (après validation de la transaction, A-14).
> - CA : une session ouverte produit une entrée de début, un e-mail au DG, et un refus 403 `ecriture_interdite_assistance` sur POST, PUT, PATCH et DELETE ; une session terminée produit une entrée de fin.

---

## 4. Prérequis

| # | Prérequis | Auteur | Statut |
|---|---|---|---|
| P1 | `docs/refonte/lot9-inventaire.md` | Gemini | FAIT |
| P2 | Tâches de fond synchrones en test et `mail.outbox` utilisable | Gemini | CONFIRMÉ |
| P3 | Fixture de deux entreprises réelles (A et B) | Gemini | À FOURNIR DANS `fabriques_lot9.py` |
| P4 | Décisions des sections 1 et 2 validées | Durel | VALIDÉ |
| P5 | H-01 inscrit dans `cahier-regles.md` | Gemini / Durel | FAIT |
