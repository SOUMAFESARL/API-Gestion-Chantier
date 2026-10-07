# Cahier des règles : refonte rôles / permissions / modules (Gestion_Chantier)

Version 1.0
Statut : GELÉ
Exceptions au gel : C-04 (levée au lot 8) et H-01 (levée au lot 9).

**Légende**
- `[V]` : validé explicitement par Durel.
- `[D]` : défaut retenu (délégué à Claude, ou proposé sans objection). À relire.
- `CA` : critère d'acceptation, vérifiable par un test.

**Règle d'or pour Gemini** : il n'ajoute, ne retire et n'interprète aucune règle. En cas d'ambiguïté, il s'arrête et pose la question. Il ne devine pas.

---

## 0. Contraintes générales

**G-01 [V] Périmètre : backend uniquement.** Gemini ne modifie que `API-Gestion-Chantier`. Le dépôt `Application-Gestion-Chantier` n'est jamais modifié (lecture seule).
- CA : `git status` du dépôt front reste propre après chaque lot.

**G-02 [D] Compatibilité de l'API avec le front actuel.** Tant que le front n'est pas adapté :
- `GET /profil/` continue de renvoyer `role_global` (alias en lecture seule du rôle unique), `habilitations` (niveau 0 à 3 par module, déduit des permissions effectives) et `permissions` (codes effectifs).
- Aucune route existante n'est renommée ni supprimée, sauf celles listées dans ce cahier (E-06, E-13).
- Les entrées `role_global` et `role_personnalise_id` restent acceptées par l'API et sont traduites vers le rôle unique (MOA vers BAI, MOE vers VI).
- Le champ `rang` reste dans le REGISTRE uniquement pour calculer `habilitations`. Il ne décide plus d'aucun accès.
- Limite connue : un rôle qui n'a que `valider` apparaît au front comme niveau 3. Le serveur reste l'autorité.
- CA : un test lit `GET /profil/` pour un DG, un AD, un CP et un rôle personnalisé et vérifie la présence et la forme des trois champs.

**G-03 [D] Notes de changement API.** Gemini tient à jour `docs/notes-changement-api.md` : champs retirés, routes supprimées, nouveaux refus (403, 400, 409) et nouveaux codes d'erreur, pour l'équipe front.
- CA : le fichier existe et chaque lot qui change le contrat y ajoute une entrée.

**G-04 [V] Pas de production.** Les migrations s'appliquent à la base de développement (schémas `demo` et autres). Aucune période de compatibilité de données n'est nécessaire.
- CA : `migrate_schemas` passe sur tous les schémas de développement.

**G-05 [V] Méthode.** Branche backend `refonte-droits`, un commit par lot. Tests d'acceptation écrits avant le code et verrouillés. Gemini ne modifie jamais une assertion de ces tests. Il peut adapter seulement les fixtures.
- CA : le diff d'un lot ne touche aucun fichier de test d'acceptation verrouillé.
- Gemini ne modifie un test existant que s'il figure dans l'inventaire I-08 validé, et seulement comme le cahier le demande (A-12, E-08). Tout autre test existant qui échoue est un arrêt : question à Durel.

---

## A. Catalogue et propagation (super admin)

**A-01 [V] Source unique des permissions.** Le REGISTRE (code) est la seule source. Une commande de synchronisation alimente `CataloguePermission` à chaque déploiement. Le super admin ne peut pas créer un code absent du REGISTRE.
- CA : créer un code inconnu renvoie 400 ; la synchronisation est idempotente.

**A-02 [V] Module d'une permission.** Le module est le préfixe du code (`projets.lire` appartient à `projets`). Le super admin ne le modifie pas.

**A-03 [V] Nettoyage du catalogue.** Après migration, les 4 verbes génériques (`LECTURE`, `ECRITURE`, `VALIDATION`, `SUPPRESSION`) sortent du catalogue. On ne garde que la relation `permissions_catalogue` sur `RoleModulePermission`. La relation `permissions` vers `accounts.Permission` est supprimée.
- CA : aucun code générique dans `CataloguePermission` ; le modèle n'a plus qu'une relation M2M de permissions.

**A-04 [V] Liste à cocher.** Les permissions d'un rôle sont une liste à cocher par module. Aucun niveau ne décide d'un accès.
- CA : `permissions_effectives()` lit la liste cochée ; un rôle avec seulement `chantier.valider` ne reçoit ni `chantier.lire` ni `chantier.rediger`.

**A-05 [V] Nouvelle permission.** Une nouvelle permission (code synchronisé) devient cochable par les DG. Elle n'est pas ajoutée aux rôles.

**A-06 [V] Permission retirée ou désactivée.** Elle disparaît immédiatement des permissions effectives de tous les rôles de toutes les entreprises.
- CA : après désactivation, `permissions_effectives()` ne contient plus le code, pour au moins deux entreprises de test.

**A-07 [V] Nouveau rôle système.** Il est propagé à toutes les entreprises, existantes comprises, sans modifier aucun rôle existant.

**A-08 [V] Modification d'un rôle système existant.** Elle ne touche pas les entreprises déjà inscrites. Les rôles sont des copies. Elle ne vaut que pour les nouvelles inscriptions.

**A-09 [V] Conflit de nom ou de code.** Le rôle système l'emporte. Le rôle personnalisé en conflit est renommé automatiquement et garde ses collaborateurs et ses droits.
- CA : un rôle personnalisé de même code qu'un nouveau rôle système est renommé ; ses collaborateurs et ses permissions sont inchangés.

**A-10 [V] Module désactivé.** Ses permissions sont ignorées pour toute l'entreprise. Les rôles sont conservés. À la réactivation, ils sont retrouvés tels quels.

**A-11 [V] Activation d'un nouveau module pour une entreprise existante (option A).** Copie unique : les rôles système reçoivent les permissions par défaut du module, les rôles personnalisés reçoivent une ligne vide explicite. Le DG est prévenu par e-mail (A-14). Rien n'est lu dans le modèle à l'exécution.
- CA : après activation, chaque rôle a une ligne explicite pour le module ; les rôles personnalisés n'ont aucune permission du module.

**A-12 [V] Pas de repli sur le modèle, pas de plafond.** `ModeleRoleModule.niveau_max` n'intervient nulle part (retrait à tous les endroits de l'inventaire I-01 validé par Durel). Le modèle ne sert qu'au contenu par défaut à l'inscription et à l'activation d'un module (A-11).
- CA : modifier un modèle dans le schéma public ne change aucune permission effective d'une entreprise existante.

**A-13 [V] Aucun écrasement.** `appliquer_modeles_roles()` n'est plus appelée sur une entreprise existante. Elle est remplacée par une fonction qui crée seulement les rôles système manquants et ne modifie jamais un rôle existant. Les appels paresseux dans les GET (`RoleListCreateView`, `ParametresRoleListCreateView`) sont supprimés.
- CA : un GET sur la liste des rôles n'écrit rien en base ; un rôle système modifié par le DG n'est pas écrasé par la fonction de création.

**A-14 [V] Notification du DG.** Toute modification du super admin sur une entreprise (modules, permissions, rôles système) est journalisée dans l'audit et déclenche un e-mail au DG. L'e-mail part après validation de la transaction (`transaction.on_commit`), en tâche de fond. Si la transaction est annulée, aucun e-mail.
- CA : un changement validé crée une entrée d'audit et un e-mail ; un changement annulé ne crée aucun e-mail.

**A-15 [V] Module GED.** L'application `apps/ged` est vide (confirmé). Le module reste au catalogue mais désactivé par défaut. Aucun code `ged.*` n'est créé.
- CA : une nouvelle entreprise n'a pas GED parmi ses modules actifs ; le REGISTRE ne contient aucun code `ged.*`.

---

## B. Rôles et identité

**B-01 [V] Rôle unique.** Chaque collaborateur a un seul champ de rôle (clé vers la table des rôles, système ou personnalisé). `role_global` cesse d'être une source (voir G-02). Migration : MOA vers BAI, MOE vers VI.
- CA : un utilisateur DF a `role` = DF et `GET /profil/` renvoie `role_global` = `DF`.

**B-02 [V] Codes de rôles système.** DG, AD, DO, DF, CP, CT, CC, MAG, BAI, VI. L'enum `RoleGlobal` n'est plus une source de vérité.

**B-03 [V] Le DG.**
- Un par entreprise, non attribuable à un autre, non transférable pour l'instant.
- Son rôle est calculé : toutes les permissions des modules activés plus toutes les permissions d'administration.
- Personne, pas même lui, ne modifie son rôle ni sa matrice. Il ne peut être ni suspendu ni supprimé.
- Une seule fonction `est_dg(utilisateur)` remplace toutes les conditions copiées (inventaire I-02 validé par Durel).
- CA : un AD et le DG lui-même reçoivent un refus sur chaque action visant le DG ; `grep` ne trouve plus la condition copiée.

**B-04 [V] Droits d'administration de l'AD.** Liste fixe dans le code, hors des cases à cocher : `administration.collaborateurs_voir`, `collaborateurs_gerer`, `roles_gerer`, `abonnement_voir`, `factures_voir`, `onboarding_suivre`.
- L'AD n'a pas `entreprise_modifier` ni `abonnement_gerer` (DG seul).
- Le DG ne peut pas retirer un droit d'administration à un AD.

**B-05 [V] Permissions d'administration non cochables.** Aucune permission `administration.*` ne peut être cochée dans un rôle (personnalisé ou système). Un marqueur `reservee_administration` dans le REGISTRE est vérifié côté serveur.
- CA : cocher une permission d'administration dans un rôle renvoie 400, test dédié.

**B-06 [V] L'AD et les autres AD.** Un AD ne peut ni ajouter, ni changer le rôle, ni suspendre, ni supprimer un autre AD ni lui-même. Seul le DG gère les AD.
- CA : un AD qui change le rôle de, suspend ou supprime un AD (y compris lui-même) reçoit 403.

**B-07 [V] L'AD et les rôles système.** Un AD ne modifie pas les permissions des rôles système.
- CA : PATCH d'un rôle système par un AD renvoie 403.

**B-08 [V] « L'AD ne donne que ce qu'il possède ».** Pour créer ou modifier un rôle, l'appelant ne peut accorder que des permissions qu'il possède lui-même.
- CA : un AD qui coche `projets.voir_montants` (qu'il n'a pas) reçoit 403.

**B-09 [V] Attribution d'un rôle par l'AD.** L'AD n'attribue qu'un rôle dont toutes les permissions font partie des siennes. Il n'attribue ni AD ni DG. Conséquence : il ne peut pas attribuer DF.
- CA : un AD qui attribue DF, AD ou DG reçoit 403.

**B-10 [V] Pouvoirs du DG sur les rôles.** Le DG modifie les permissions de n'importe quel rôle sauf le sien, système compris, parmi les permissions des modules activés pour son entreprise (modèle A).

**B-11 [V] Un rôle par collaborateur, effet immédiat.** Les droits sont recalculés à chaque requête. Le JWT ne porte aucune permission et le claim `role_global` n'est jamais lu pour décider d'un accès.

**B-12 [V] Rôles personnalisés.** Une entreprise peut créer des rôles personnalisés.

---

## C. Collaborateurs et abonnement

**C-01 [V] Ajout en deux temps.** D'abord dans l'entreprise avec un rôle (DG ou AD), ensuite affectation à un ou plusieurs projets. L'affectation n'est jamais automatique, sauf pour le créateur d'un projet (E-04).

**C-02 [V] Départ d'un collaborateur.**
- Le compte est désactivé (historique conservé) et l'e-mail est libéré.
- Ses affectations sont désactivées.
- Les projets dont il était chef de projet ou conducteur sont signalés « sans chef de projet » et le DG est alerté.
- CA : après un départ, l'e-mail est réutilisable, les affectations sont inactives et le projet porte l'indicateur.

**C-03 [V] Une personne = une seule entreprise.** Registre global dans le schéma public (e-mail vers entreprise), vérifié à l'inscription et à l'invitation. La connexion l'utilise à la place de la boucle sur les entreprises. L'e-mail est libéré au départ. Pas de sous-domaine par entreprise.
- CA : inviter un e-mail déjà présent dans une autre entreprise est refusé ; la connexion ne parcourt plus les schémas.

**C-04 [V] Limites du plan et expiration.** Les limites (collaborateurs actifs, projets) sont refusées à la création avec une erreur dédiée. Abonnement expiré : lecture seule pour tous, sauf les actions de paiement et d'abonnement du DG.
- À vérifier d'abord : ce qui existe déjà dans `billing`. Aucune hypothèse.

**C-05 [V] Lectures réservées.**
- `GET /parametres/collaborateurs/` et `GET /invitations/` : `administration.collaborateurs_voir` (DG, AD).
- Liste réduite pour l'affectation : identifiant, nom, rôle ; rôles à portée PROJET uniquement ; exige `projets.affecter_membres` ; aucun e-mail ni téléphone.
- `GET /projets/{id}/affectations/` : nom et fonction pour tout membre ; e-mail et téléphone seulement pour DG, AD et titulaires de `affecter_membres` ou `gerer_equipes`.

---

## D. Portée

**D-01 [V] Portée d'un rôle.** ENTREPRISE (voit tous les projets, futurs compris) ou PROJET (voit seulement ses projets affectés, mêmes droits dans tous). Sans projet : accès à rien.

**D-02 [V] Qui fixe la portée.** Le super admin pour les rôles système, le DG pour les rôles de son entreprise.

**D-03 [V] Changer la portée.** Exige une confirmation explicite. Sans confirmation, l'API renvoie le nombre de personnes touchées. Passer à ENTREPRISE efface les affectations des personnes concernées.

**D-04 [V] Portée d'un module.** Fixe (par projet ou globale), fixée par le super admin. Un module mixte est séparé (`MotifReport` vers un module global, `pilotage`). Dans un module par projet, une donnée sans projet n'est visible que des rôles ENTREPRISE. Dans un module global, un rôle PROJET voit tout le module s'il a la permission.

**D-05 [V] Avertissement.** L'API renvoie un avertissement quand une permission d'un module global est cochée dans un rôle à portée PROJET.

**D-06 [V] Filtrage centralisé.** Une seule méthode de requête commune filtre par projet. `GlobalJournalReportsView` (journal-reports) est filtré par les projets accessibles.
- CA : un CP voit uniquement les reports de ses projets.

**D-07 [D] Migration de la portée.** ENTREPRISE pour les rôles qui ont `projets.voir_tous` aujourd'hui (DG, AD, DO) ; PROJET pour les autres, DF compris. `projets.voir_tous` disparaît du REGISTRE.

**D-08 [V] Garde unique.** Une action est autorisée si le code de permission est détenu ET (portée ENTREPRISE OU affectation active au projet). Cette garde remplace `PermissionModule`, `MembreDuProjet` et `RoleRequis`.
- CA : plus aucune vue n'utilise `PermissionModule`, `MembreDuProjet` seul ou `RoleRequis` ; `grep` le prouve.

---

## E. Projets

**E-01 [V] Permissions du module projets.** `lire`, `ecrire`, `creer`, `changer_statut`, `resilier_archiver`, `affecter_membres`, `gerer_equipes`, `voir_montants`. Défauts : voir l'annexe 1.

**E-02 [V] Autres modules.** `chantier.lire`, `rediger`, `valider` ; `tiers.lire`, `ecrire` ; `pilotage.lire`. La migration traduit chaque niveau actuel en codes (rang inférieur ou égal au niveau). Chacun garde ses droits réels d'aujourd'hui, hors les codes nouveaux de l'annexe 1.
- CA : pour chaque rôle de la base de dev, l'ensemble des codes avant migration est inclus dans celui d'après, aux écarts listés en annexe 1 près.

**E-03 [V] Écritures protégées par codes.**
- Lots (création, import, modification), activités, reprogrammation : `projets.ecrire`.
- Équipes (création, modification, suppression, affectations d'équipe) : `projets.gerer_equipes`.
- Plus aucune écriture n'est protégée par la seule appartenance au projet.
- CA : un VI et un BAI affectés reçoivent 403 sur PATCH statut, POST lot, POST import, POST équipe, DELETE équipe (requêtes réelles). Un non-affecté reçoit 403 comme avant.

**E-04 [V] Créer un projet.** `projets.creer`. Le créateur à portée PROJET est affecté automatiquement au projet créé. Cela donne la visibilité sans le désigner chef de projet.
- CA : un CP à qui le DG a coché `creer` crée un projet et le voit dans `GET /projets/`.

**E-05 [V] Affectation.**
- Un seul point d'entrée : `POST` et `DELETE` sur `/projets/{id}/affectations/`.
- Il exige `projets.affecter_membres` et (portée ENTREPRISE ou affecté au projet).
- La personne choisie est active, appartient à l'entreprise et a un rôle à portée PROJET, vérifié côté serveur.
- Le garde par étiquette `role_projet == CHEF_PROJET` est supprimé.
- CA : affecter un DO (portée ENTREPRISE) renvoie 400 ; un CT sans `affecter_membres` reçoit 403.

**E-06 [V] Rôle de l'affectation.**
- `role_projet` est une étiquette (fonction affichée) sans aucun droit. Il continue de synchroniser `projet.chef_projet` et `projet.conducteur_travaux`. MOA et MOE restent des fonctions affichables.
- La clé `AffectationProjet.role` est supprimée. `ProjetRoleModuleOverride` est supprimé (modèle, migration, services, vue, route `permissions-roles`).
- CA : un CC affecté avec `role_projet = CT` garde les droits d'un CC sur les objets du projet.

**E-07 [V] Équipes.** On compose une équipe avec des personnes déjà affectées au projet (déjà exigé par le serveur).

**E-08 [V] Changement de statut.**
- `projets.changer_statut` : suspendre, reprendre, bloquer, réceptionner, terminer et autres changements courants.
- `projets.resilier_archiver` : RESILIE, ARCHIVE, DESACTIVE et toute sortie de ces états.
- L'exception « PATCH statut seul = appartenance au projet » est supprimée.
- Les tests `test_statuts_crud.py` et `test_statuts_projet.py` sont inversés. `docs/api-projets-statuts.md` est réécrite.
- CA : un VI reçoit 403, un CP obtient 200 pour SUSPENDU, un CP reçoit 403 pour RESILIE, un DO obtient 200 pour RESILIE.

**E-09 [D] Statut CRITIQUE.** Statut manuel protégé. Il est ajouté à l'ensemble des statuts fixes que la tâche nocturne n'écrase jamais, et relève de `changer_statut`. À confirmer par le test de Gemini sur le comportement actuel.
- CA : après `executer_evaluation_quotidienne_schema`, un projet CRITIQUE reste CRITIQUE.

**E-10 [V] Effet des statuts sur les écritures.**
- Fin de vie (RESILIE, ARCHIVE, DESACTIVE) : lecture seule totale, y compris les rapports en brouillon, soumis ou en attente. Seul `resilier_archiver` peut sortir de cet état.
- Achèvement (RECEPTIONNE, TERMINE) : plus de nouveaux rapports journaliers ni de reprogrammation [D]. Permis : lots et activités, équipes, validation ou rejet des rapports déjà soumis.
- Arrêt (SUSPENDU, BLOQUE) : tout reste permis.
- Un refus pour cause de statut renvoie 409 avec le code `projet_clos` (distinct du 403).
- CA : POST d'un rapport sur un projet RESILIE renvoie 409 `projet_clos` ; la même requête sur un projet SUSPENDU renvoie 201.

**E-11 [V] Montants.**
- `projets.voir_montants` (DG, DF, DO, CP) : sans ce droit, tous les champs de montants sont absents de la réponse de l'API (projet, lot, activité, statistiques, tableau de bord).
- Pour écrire un montant (projet, lot, activité), il faut `voir_montants` plus le droit d'écrire la ressource. Sinon 400 « champ non accepté ».
- CA : un AD qui crée un projet avec `budget_initial_montant` reçoit 400 ; un CP l'enregistre ; un VI ne reçoit aucun champ de montant.

**E-12 [V] Champs sans source réelle.** Retrait de l'API : `budget_consomme_montant` (22,5 % inventé), `budget_engage_montant`, `bons_a_signer_montant`, `budget_activites_montant` et la consommation par projet du tableau de bord.
- CA : aucun de ces champs n'apparaît dans une réponse. Voir G-03 : le front lit `budget_consomme_montant` avec un repli à 0.

**E-13 [V] Vue supprimée.** `ContexteCreationProjetView` : vue, route, serializer et tests supprimés.

---

## F. Lectures et vues

**F-01 [V] Rôles.** `GET /roles/`, `GET /roles/{id}/`, `GET /parametres/roles/`, `GET /parametres/roles/{id}/` exigent `administration.roles_gerer`.

**F-02 [V] Unification.** Les deux familles de routes de rôles appliquent exactement les mêmes règles (`/roles/` reste comme alias, voir G-02).

**F-03 [V] Abonnement.** Tout utilisateur connecté reçoit seulement `jours_essai_restants` et `est_expire`. Le détail (plan, quotas, échéances) exige `administration.abonnement_voir`.

**F-04 [V] Factures et expiration.** `GET /factures/` (liste, détail, PDF) exige `administration.factures_voir`. `GET /abonnement/notifications/` exige `administration.abonnement_voir`.

**F-05 [V] Paiement.** `POST /cinetpay/initier/`, `GET /cinetpay/statut/...` et tout changement de plan exigent `administration.abonnement_gerer` (DG seul).

**F-06 [V] Modules.** `GET /modules/` ne renvoie à chacun que ses propres modules et permissions.

**F-07 [V] Entreprise.** `GET /entreprise/` et `GET /parametres/configuration/` sont ouverts à tout utilisateur connecté. L'écriture exige `administration.entreprise_modifier` (DG seul).

**F-08 [V] Onboarding.** Les routes sous `/configuration/` exigent `administration.onboarding_suivre` (DG, AD). Elles ne modifient aucune donnée métier.

**F-09 [V] Inchangé.** Météo et villes ne changent pas.

**F-10 [V] Nettoyage.** Constantes mortes `ROLES_DIRECTION`, `ROLES_GESTION_CHANTIER`, `ROLES_VALIDATION_CHANTIER` supprimées. Docstrings « DF » corrigés dans `facture.py` et `expiration.py`. Paragraphe « Apprentissage » retiré de `docs/api-projets-statuts.md`.

---

## H. Plateforme (super admin)

**H-01 [V] Impersonation (session d'assistance).**
- Le super admin ouvre une session d'assistance sur une entreprise. Le jeton porte `is_impersonation` et `read_only`, vaut une heure et n'est pas renouvelable.
- Toute requête POST, PUT, PATCH ou DELETE faite avec ce jeton est refusée en 403, code `ecriture_interdite_assistance`, sauf la déconnexion d'assistance. Les lectures passent.
- Le début et la fin (déconnexion explicite) de la session sont journalisés dans `JournalPlateforme` et dans le `JournalAudit` de l'entreprise. L'expiration sans déconnexion n'écrit pas d'entrée de fin.
- Au début de la session, un e-mail part au DG de l'entreprise (après validation de la transaction, A-14).
- CA : une session ouverte produit une entrée de début, un e-mail au DG, et un refus 403 `ecriture_interdite_assistance` sur POST, PUT, PATCH et DELETE ; une session terminée produit une entrée de fin.

**H-02 [D] Niveaux de super admin.** Un seul niveau. Toutes les actions sont journalisées.

---

## Annexe 1 : défauts des codes nouveaux ou modifiés (rôles système)

Les autres codes viennent de la traduction des niveaux actuels (E-02). Le DG a tout par calcul.

| Code | DG | AD | DO | DF | CP | CT | CC | MAG | BAI | VI |
|---|---|---|---|---|---|---|---|---|---|---|
| `projets.creer` | oui | oui | oui | non | non | non | non | non | non | non |
| `projets.changer_statut` | oui | oui | oui | non | oui | non | non | non | non | non |
| `projets.resilier_archiver` | oui | oui | oui | non | non | non | non | non | non | non |
| `projets.affecter_membres` | oui | oui | non | non | oui | non | non | non | non | non |
| `projets.gerer_equipes` | oui | oui | non | non | oui | oui | non | non | non | non |
| `projets.voir_montants` | oui | non | oui | oui | oui | non | non | non | non | non |

Ces six codes sont donnés par cette matrice explicite, jamais par traduction d'un niveau. `projets.voir_tous` et `pilotage.voir_montants` disparaissent.

Les rôles personnalisés existants reçoivent les codes issus de leur niveau (E-02), sans aucun des six codes de cette annexe.

---

## Annexe 2 : reportés (comportement par défaut)

- **Portée du DF :** PROJET (règle D-07).
- **Perte ou départ du DG :** aucun changement.
- **Transfert du rôle DG :** aucun changement.
- **Niveaux de super admin :** un seul niveau (H-02).
- **GED :** module désactivé (A-15).
- **DF et factures d'abonnement :** pas d'accès (le code actuel n'autorise que DG et AD).

---

## Annexe 3 : notes pour l'équipe front (jamais exécutées par Gemini)

- Utiliser les codes de `GET /profil/` (`permissions`) plutôt que les niveaux et les noms de rôle pour les menus et les boutons.
- Bouton « nouveau projet » : afficher selon `projets.creer`.
- Masquer la zone budget (carte « Budget », alerte « budget non défini », bouton « cadrer ») pour les utilisateurs sans `projets.voir_montants`.
- Masquer la tuile « Dépensé » (le champ disparaît).
- Remplacer `/projets/{id}/suspendre/` et `/reprendre/` par `PATCH /projets/{id}/` avec `statut`.
- Remplacer `/projets/{id}/encadrement/` par `/projets/{id}/affectations/`.
- Corriger `POST /projets/{id}/activites/` (la route exige le lot) et les autres appels sans route recensés.
- Supprimer les codes de rôles fantômes `CA`, `CS`, `BE` dans `regles.ts` et les listes `DIRECTION`, `GESTION_CHANTIER`.
- Supprimer les fichiers orphelins de l'override : `ProjetPermissionsSection.tsx`, `obtenirMatriceProjet`, `sauvegarderMatriceProjet`, mocks de `simulationRoles.ts`.
- Masquer le menu `/documents` tant que la GED n'existe pas.
- Gérer l'erreur 409 `projet_clos`.
- Pour la liste des membres à affecter, utiliser la liste réduite (C-05) au lieu de `GET /parametres/collaborateurs/`.
