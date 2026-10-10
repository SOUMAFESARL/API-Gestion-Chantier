# Plan d'alignement frontend → backend (rôles, collaborateurs, modules, permissions)

Créé le 9 octobre 2026. Périmètre : espace entreprise (tenant) et espace super admin.

**Principe :** le backend est la référence. Le frontend (`Application-Gestion-Chantier`) lit les champs
tels que l'API les renvoie. Les alias de compatibilité ajoutés côté backend (codes minuscules `saisie`,
`lecture`, routes en double) sont retirés à la fin, une fois le frontend aligné.

**Règle de travail :** l'édition du frontend par l'agent est autorisée pour cette tâche (décision du
9 octobre 2026). `git push` reste interdit sur le frontend, **et aucun commit local non plus** (décision du 9 octobre 2026) : les modifications restent dans l'arbre de travail pour relecture.

## Constats de départ

| # | Constat | Conséquence |
|---|---|---|
| 1 | `permissions_modules` renvoie des codes doublés (`ECRITURE` + `saisie`, `LECTURE` + `lecture`). Le frontend ne lit que les minuscules (`accesNormalises`, `features/roles/regles.ts`). | Retirer les alias backend vide toutes les cases. |
| 2 | `permissionsNormalisees` boucle sur les 12 modules en dur de `MODULES_CCD`. Le backend a un catalogue dynamique. | Un module créé par le super admin n'apparaît jamais. |
| 3 | Jamais appelés par le frontend : `GET /modules/`, `/admins/permissions*`, `/admins/clients/{id}/modules/{id}/activer\|desactiver`, `/admins/entreprises/{id}/utilisateurs/`. | Routes backend sans écran. |
| 4 | Rôles : liste sur `/parametres/roles/`, détail et suppression sur `/roles/{id}/`. | Deux familles de routes pour une ressource. |
| 5 | `SIMULATION_ACTIVE` (`NEXT_PUBLIC_API_SIMULE=1` en dev) simule collaborateurs, détail des rôles, super admin. | Le vrai branchement n'est pas exercé en dev. |
| 6 | Commentaires périmés (« `/utilisateurs/moi/` pas livrée », routes suspendre « inexistantes »). | À retirer avec les branches simulées. |
| 7 | `administration/adaptateur.ts` appelle `/auth/mot-de-passe/oublie/` et `/admins/parametres/tarifs/\|identite/`, absents de `platform_admin/urls.py`. À confirmer. | Possible 404. |
| 8 | `AccesModule` ignore `SUPPRESSION` ; le niveau cumulatif 0-3 est encore lu en repli. | Permission backend inconnue du frontend, ignorée sans erreur. |

## Lots (révisés après le lot 0)

Le lot 0 (`lot0-contrat-reference.md`) a changé le plan : le backend raisonne en **codes de permission
`module.verbe`** (liste à cocher par module), plus en niveaux ; les **surcharges par projet n'existent plus**.
Ordre : 1 → 2 → 3 → 4 → 5 → 6 → 7. Chaque lot est vérifiable seul.

- [x] **Lot 0 — Contrat de référence.** Fait : `lot0-contrat-reference.md`. Décisions : mot de passe
  oublié admin → `/admins/mot-de-passe/{demande,verifier,reinitialiser}/` ; tarifs et identité de
  plateforme = hors périmètre (lot 8 backend), désactivés en production.
- [x] **Lot 1 — Droits par codes de permission (fait le 9 octobre 2026).** Les droits d'un compte sont
  `profil.permissions` (codes `module.verbe`, calculés par le serveur) : `Droits.permissions` est une liste
  de codes et `peut(code)` remplace `peut(module, acces)`. Constantes dans
  `features/habilitations/permissions.ts` (`PERMISSIONS`). 9 écrans migrés vers le code précis qu'ils
  protègent (`projets.creer`, `projets.ecrire`, `projets.changer_statut`, `projets.affecter_membres`,
  `projets.gerer_equipes`, `projets.voir_montants`, `chantier.valider`). Bug corrigé au passage : les
  clés de `profil.habilitations` sont en MAJUSCULES (`PROJETS`) alors que le frontend cherchait des
  minuscules, donc un non-DG n'avait aucun droit. `RoleItem.permissions` (codes réels, sans alias) ajouté
  à côté de l'ancien `permissions_modules`, qui reste pour l'interface des rôles jusqu'au lot 3.
  `typecheck` (hors `.next/` périmé) et `eslint` propres.
  **Restes pour les lots suivants :** `AccesModule`, `ACCES_MODULE`, `NiveauAcces`, `MODULES_CCD` et
  `permissionsNormalisees` vivent encore pour la matrice des rôles (lots 2-3) ; la portée du profil
  (`PERSONNE` pour tout non-DG) ignore la portée `ENTREPRISE` des rôles AD/DO (à traiter au lot 3 : le
  profil n'expose pas la portée du rôle, à demander au backend) ; les modules finance, achats, stocks,
  rh, equipements, qhse, contrats, ged n'existent pas dans le REGISTRE : leurs écrans restent
  réservés à la direction.
- [x] **Lot 2 — Menu et routes dynamiques (fait le 9 octobre 2026).** Décision de Durel : seuls les modules
  du backend s'affichent, et seulement ceux auxquels le rôle a accès. La source unique est
  `profil.permissions` (le serveur y met, pour le DG, toutes les permissions des modules actifs de
  l'entreprise + administration ; pour les autres, celles de leur rôle) : inutile d'appeler `/modules/`
  pour le menu. Le raccourci « direction ouvre tout » est retiré de `peut()`. Routes : `projets`, `planning`
  → `projets.lire` ; `rapports` → `chantier.lire` ; `tiers` → `tiers.lire` ; `/parametres` → une des
  permissions d'administration, ses sous-pages et `/abonnement` → `administration.*` précises
  (`collaborateurs_voir`, `roles_gerer`, `entreprise_modifier`, `abonnement_voir`, `factures_voir`) ; finance,
  achats, stocks, rh, equipements, qhse, contrats, documents → condition `AUCUN` (fermées à tous, direction
  comprise). `typecheck` et `eslint` propres ; **pas vérifié dans le navigateur contre le vrai backend**.
  **Restes (lot 7) :** le JSX des entrées de menu des modules absents reste dans `layout.tsx` (jamais
  affiché) ainsi que leurs dossiers `app/(entreprise)/{finance,achats,stocks,rh,equipements,qhse,contrats,documents}`
  et les blocs finance/qhse du tableau de bord ; à supprimer. `GET /modules/` sert au lot 3 (matrice des rôles).
- [x] **Lot 3 — Rôles (fait le 9 octobre 2026).** Page `/parametres/roles` refaite : le tableau montre, par
  module du catalogue (`GET /modules/`, `features/roles/catalogue.ts`), « n/m » permissions et la portée ;
  la modification se fait dans `ModalRole` (création et édition, une case par permission via
  `ChampPermissions`, portée `ENTREPRISE`/`PROJET`, copie depuis un rôle existant). Tout passe par
  `/parametres/roles/` ; écriture par `permissions` (codes) ; le 409 `confirmation_requise` ouvre une
  confirmation (`personnes_touchees`) puis renvoie `confirmer: true` ; les `alert()` deviennent des toasts ;
  `lib/api/erreurs.ts` lit désormais les réponses d'erreur « à plat » (`{code, message, …}`). Supprimés :
  `simulationRoles`, `ModalNouveauRole`, `ModalModificationRole`, `ProjetPermissionsSection` (jamais
  affichée) et les types `MODULES_CCD`, `PermissionsModules`, `ProjetRoleMatrice` — **donc la partie
  « surcharges retirées » du lot 5 est faite**. Droits d'édition : rôle du DG intouchable ; rôles système et
  portée réservés au DG ; un AD voit la page (`administration.roles_gerer`) et crée des rôles.
  `typecheck` et `eslint` propres ; **à vérifier serveur lancé** : que les permissions de `GET /modules/` ont
  bien des codes `module.verbe` (le filtre écarte tout code sans point), et le flux 409.
  Restes : `SelecteurAcces`/`AccesModule` servent encore à `ListeModules` du back-office (lot 6) ; les clés
  `roles.modules.*` de `messages/fr.json` ne sont plus lues ; la portée du profil (voir lot 1) reste à traiter.
- [x] **Lot 4 — Collaborateurs (fait le 9 octobre 2026).** `simulationCollaborateurs` supprimé : liste,
  fiche, suspension, réactivation, suppression et ajout appellent le vrai serveur. L'ajout choisit un
  **rôle de l'entreprise** (liste `GET /parametres/roles/`, plus la liste fixe AD/CP/CT/CC/MOA/MOE/VI) et
  envoie `role_personnalise_id` = l'identifiant du rôle (un seul champ de rôle, pas de 400 `role_ambigu`).
  `rolesAttribuables` : jamais DG ; seul le DG nomme un AD ; un AD ne donne que ses propres permissions
  (B-06, B-08, B-09). `suspensionPossible` & co prennent un `ActeurCollaborateurs` : un AD ne gère ni un
  AD ni le DG ; les libellés de rôle sont ceux du serveur. Les erreurs 400/403/409 s'affichent avec le
  message du serveur (gestion déjà en place dans `useGestionCollaborateur`). `typecheck` et `eslint`
  propres ; **à vérifier serveur lancé** : création avec `role_personnalise_id`, libellé de rôle renvoyé
  pour un rôle personnalisé. Restes : clés `gestionCollaborateurs.roleOptions.*` de `fr.json` inutilisées ;
  le changement de rôle d'un collaborateur (`PATCH`) n'a pas d'écran ; invitations (`/invitations/`) non
  touchées (l'écran d'acceptation utilise `features/invitations/api.ts`, à relire au lot 7).
- [x] **Lot 5 — Surcharges retirées et affectations (fait le 9 octobre 2026).** L'équipe d'encadrement d'un
  chantier est maintenant celle des **affectations** du serveur : lecture par
  `GET /projets/{id}/affectations/?actifs_seulement=true` (fusionnée dans `lireProjet`), ajout par
  `POST` (`utilisateur_id`, `role_projet`), retrait par `DELETE …/affectations/{id}/` (l'identifiant se
  retrouve par la liste). Correspondance : chef de projet = CP, conducteur = CT, chef de chantier = CC ;
  les « autres membres » deviennent maître d'ouvrage (MOA), maître d'œuvre (MOE), consultant lecture seule
  (VI) — les anciennes fonctions FINANCIER / INGENIEUR / DOCUMENTALISTE / METREUR / QHSE / AUTRE n'existent
  pas côté serveur et sont retirées, de même que la **zone** du chef de chantier (non enregistrée) et le
  signataire « directeur financier » de la fiche PDF (affiché « — »). Les listes de choix ne demandent plus
  `GET /parametres/collaborateurs/` (droit d'administration) : l'encadrement propose
  `collaborateurs-affectables` (portée PROJET seulement), la composition d'équipe propose les personnes déjà
  affectées (règle E-07). Les surcharges par projet avaient déjà été retirées au lot 3.
  `typecheck` et `eslint` propres ; **à vérifier serveur lancé** : réponse de `…/affectations/` (clé
  `utilisateur`, dates), effet de `actifs_seulement`, et que le DELETE désactive bien l'affectation.
  Restes : `simulationProjets`/`simulationLots` gardent l'ancien modèle (zone nulle) tant que les projets ne
  sont pas branchés (lot 7) ; clés `projets.encadrement.ajout.*zone*` et `fonctionAutreMembre` anciennes de
  `fr.json` à nettoyer ; un chef de projet déjà en poste n'est pas remplacé côté frontend (le serveur décide).
- [x] **Lot 6 — Super admin (fait le 9 octobre 2026).** `features/administration/adaptateur.ts` : plus de
  branche simulée pour le profil, la photo, le mot de passe, les comptes, les modules, les clients et les
  indicateurs ; routes canoniques `/admins/...` partout (clients et indicateurs n'utilisent plus les alias
  sans préfixe). **Mot de passe oublié** : `/admins/mot-de-passe/demande/`, et nouvel écran
  `/admin/mot-de-passe/definir` (cible du lien du serveur, qui n'existait pas) en réutilisant
  `EcranDefinition` avec `espace="administration"` → `verifier` / `reinitialiser`. **Modules** : les « accès par
  défaut » (lecture/saisie/validation) deviennent les **permissions du module** (`permissions_codes`, écriture
  par `permissions`), choisies parmi les permissions du catalogue dont le code commence par celui du module ;
  une création n'en propose aucune (elles viennent du code du serveur, A-01/A-02). **Catalogue des
  permissions** : nouvelle section sous la liste des modules, en lecture, avec activation/désactivation
  (`PATCH est_actif`) — ni création, ni suppression, ni changement de module (refusés par le serveur).
  **Tarifs et identité de plateforme** : hors simulation, l'enregistrement répond une erreur explicite
  « pas encore disponible » (aucune route serveur : lot 8). `typecheck` et `eslint` propres ;
  **à vérifier serveur lancé** : connexion admin et rôle affiché, `permissions_codes` des modules, effet de
  `PATCH est_actif`, jeton de réinitialisation de bout en bout.
  **Écarts backend relevés :** (1) `GET /admins/moi/` renvoie `role_global="AD"` figé : le frontend en déduit
  toujours SUPERVISEUR, un agent SUPPORT apparaît donc comme superviseur (à corriger côté profil : exposer
  `role`) ; (2) aucun moyen de lister les modules activés d'un client : l'activation par client
  (`/admins/clients/{id}/modules/{id}/activer|desactiver`) n'a donc pas d'écran, son état n'étant pas lisible ;
  (3) `ClientPlateforme` n'expose pas les modules souscrits.
  Restes : `simulationAdministration.ts` garde des méthodes mortes (nettoyage au lot 7) ; clés `fr.json`
  `colonneAccesParDefaut` / `formulaire.accesParDefaut` inutilisées.
- [x] **Lot 7 — Nettoyage et bascule (fait le 9 octobre 2026).**
  **Backend, deux écarts du lot 6 corrigés :** (1) le rôle plateforme réel (`role` = SUPERVISEUR / SUPPORT)
  est exposé par la connexion admin et par `GET /admins/moi/` ; (2) la fiche client expose `modules`
  (`id, code, libelle, actif`, selon `EntrepriseModule`). En chemin, un défaut plus grave : la connexion
  exigeait `is_superuser`, donc **un agent SUPPORT créé par `/admins/comptes/` ne pouvait jamais se
  connecter** ; elle accepte désormais `is_superuser` ou `is_staff`, et `is_superuser` n'est plus figé à
  `True` dans la réponse. Les alias de compatibilité de `permissions_modules` (`lecture`, `saisie`,
  `LECTURE`, `ECRITURE`…) sont retirés : le rôle ne renvoie plus que des codes `module.verbe`.
  **Frontend :** `versRole` lit `role` (repli SUPPORT, moindre droit) ; la fiche client a une section
  « Modules » (`ModulesClient`, cases activer/désactiver, relit la fiche) ; supprimés : les 8 écrans et
  entrées de menu des modules absents du serveur (finance, achats, stocks, rh, équipements, qhse, contrats,
  documents), `features/finance`, les blocs finance/qhse du tableau de bord (+ 3 composants) et la condition
  `AUCUN`. `eslint .` et `tsc --noEmit` propres sur tout le frontend.
  **Tests backend :** 4 nouveaux (modules du client, rôle du profil, connexion SUPPORT) + 3 anciens mis au
  contrat réel (rôles sans alias, DG intouchable en 403). Sur `accounts`, `platform_admin`, `referentiels` :
  44 échecs avant, 41 après, **aucun nouveau** ; les 41 restants existaient déjà (erreur 500 sur
  `/admin/modules/`, tests `test_roles_dg` / `test_suppression_role_cascade…` en erreur de teardown, etc.) :
  à traiter à part.
  **Non fait, volontairement :** `NEXT_PUBLIC_API_SIMULE` n'est pas modifié (fichiers `.env` ignorés par git ;
  projets, lots, tableau de bord, abonnement, chantier restent simulés tant que leur backend n'est pas
  branché) ; les routes en double `/roles/` et `/admin/…` restent (parité exigée par F-02) ; `acces_par_defaut`
  des modules reste accepté en entrée côté serveur ; `habilitations` du profil reste (G-02) mais n'est plus lu.
  Restes `fr.json` : clés `roles.modules.*`, `gestionCollaborateurs.roleOptions.*`, anciennes clés de zone et
  de fonctions d'autres membres, `colonneAccesParDefaut`.
- [x] **Lot 8 (backend + frontend) — Tarifs et identité de la plateforme (fait le 9 octobre 2026).**
  Backend : `GET /plateforme/tarifs/` et `GET /plateforme/identite/` (publics, sans connexion) ;
  `PUT|PATCH /admins/parametres/tarifs/` (JSON, tous les forfaits d'un coup, validé : prix > 0, remise 0-100,
  quotas ≥ 1 ou illimité, trois forfaits vendables seulement, transaction) et `PATCH
  /admins/parametres/identite/` (multipart : nom, logo ≤ 2 Mo PNG/JPEG/WebP/SVG, `retirer_logo`),
  **réservés au superviseur** (403 pour un agent SUPPORT) et journalisés (`MODIFICATION_TARIFS`,
  `MODIFICATION_IDENTITE_PLATEFORME`). Stockage : `billing.Plan` (prix en centimes, `limite_projets`,
  `limite_utilisateurs`, `limite_stockage_mo` = Go × 1024) ; remise annuelle et avantages dans
  `Plan.limites_avancees` ; nouveau modèle singleton `IdentitePlateforme` (migration
  `platform_admin/0002_identite_plateforme`, **à appliquer : `migrate_schemas`**). 10 tests backend verts.
  Frontend : `modifierTarifs` / `modifierIdentite` appellent le serveur (plus de simulation ni d'erreur
  « indisponible »), `features/plateforme` lit les routes publiques sans branche simulée.
  Restes : `lib/api/simulationAdministration.ts` n'est plus lu que par la simulation de l'abonnement ;
  clé `administration.erreurs.indisponible` inutilisée ; un forfait au prix non tranché (`NULL`) n'est pas
  listé publiquement ; stockage illimité (`NULL`) se lit « 0 Go » (le champ du formulaire exige ≥ 1).

## Vérification à chaque lot

- Frontend : `npm run typecheck` et `npm run lint`.
- Backend (si touché) : `pytest apps/accounts apps/platform_admin apps/referentiels`.
- Effet réel : appel contre le vrai backend, pas seulement un code 200.

## Vérification de bout en bout (9 octobre 2026)

Backend local sur `localhost:8000` (base de dev migrée : `platform_admin.0002`), frontend en mode réel
(`NEXT_PUBLIC_API_SIMULE=0`, `NEXT_PUBLIC_DOMAINE_PRINCIPAL=localhost`), scénario HTTP rejouable
(équivalent d'une collection Postman) + parcours dans le navigateur.

**Scénario API : 37 vérifications sur 38.** Seul écart : création d'un collaborateur refusée en 403
`quota_plan_atteint` (l'entreprise de démo a 58 utilisateurs pour 53 de quota) — règle métier voulue, le
frontend affiche le message du serveur ; avec le quota levé temporairement, la création, la suspension, la
réactivation (409 sur répétition), le flux 409 `confirmation_requise` → `confirmer` et les affectations
(POST / liste `actifs_seulement` / DELETE) passent.

**Navigateur (vérifié) :** menu DG limité aux modules du serveur ; matrice des rôles (compteurs n/m,
portée) ; édition d'un rôle (cases, portée, dialogue de confirmation) ; liste de rôles dynamique à l'ajout d'un
collaborateur ; désignation d'un chef de projet sur un chantier (affectation créée et relue) ; connexion admin
d'un agent SUPPORT (rôle appliqué : actions désactivées) ; modules + catalogue des permissions ; fiche client
et activation/désactivation d'un module (~2 s, toast) ; enregistrement des tarifs ; réinitialisation du mot de
passe admin de bout en bout.

**Défauts trouvés et corrigés :**
1. Réinitialisation du mot de passe : un agent SUPPORT ne pouvait pas l'obtenir (filtre `is_superuser`
   seul, comme la connexion) — corrigé + test.
2. `gestionCollaborateurs.filtreSuspendus` manquait dans `fr.json` (IntlError à chaque rendu).
3. Liste des projets en échec : le serveur réel n'envoie pas `client` (il envoie `maitre_ouvrage`, une
   chaîne) ; `versProjet` tolère maintenant l'absence.
4. Module « Administration » proposé à l'activation par client alors qu'aucun client ne peut s'en passer :
   masqué.
5. Message du dialogue de portée mal formulé pour 0 personne : reformulé (pluriel complet).

**Pièges d'environnement (pas des bugs de code) :** `.env.local` fixe `NEXT_PUBLIC_DOMAINE_PRINCIPAL=soumafe.com` ;
l'espace admin appelle donc `http://soumafe.com:8000` en local et échoue (« Connexion au serveur impossible »)
— lancer avec `NEXT_PUBLIC_DOMAINE_PRINCIPAL=localhost`. Un cache `.next` périmé a fait renvoyer des 404 sur
`/admin/parametres/*` : supprimer `.next` et relancer. Python ne résout pas `*.localhost` : joindre
`127.0.0.1` avec l'en-tête `Host: demo.localhost:8000`.

**Restes (lot 9 proposé) :** le domaine **Projets** n'a jamais été aligné sur le serveur réel (contrat simulé) :
`chef_projet` n'est renvoyé qu'en `chef_projet_id`, `conducteur_travaux_id`, pas de `client`, `avancement_theorique`,
`statistiques` imbriquées, etc. ; le tableau de bord, les lots/activités, l'abonnement et le chantier restent
aussi sur la simulation. Tests backend : 42 échecs sur `accounts` + `platform_admin` + `referentiels`
(baseline avant lot : 44 ; aucun nouvel échec ; les 42 restants préexistent) à traiter à part.

## Lot 9 — Domaine Projets aligné sur le serveur réel (9 octobre 2026)

Contrats relevés sur l'OpenAPI et par appels réels, vérifiés ensuite dans le navigateur (backend local).

**Vocabulaires remplacés par ceux du serveur** (types, listes de choix, libellés `fr.json`, tons) : statuts de
projet (+ `RECEPTIONNE`, `BLOQUE`, `DESACTIVE`, `RESILIE`) ; types de projet (`BATIMENT_COMMERCIAL`, `TP_ROUTE`,
`TP_GENIE_CIVIL`, `VRD`, `INFRASTRUCTURE_INDUSTRIELLE`, `BATIMENT_RESIDENTIEL`) ; mode d'exécution `REGIE` ;
bordereau `FORFAIT | PRIX_UNITAIRE | MIXTE` ; unités `M2 ML M3 KG U FORFAIT` ; nature d'équipe `SOUS_TRAITANTE`.

**Projets :** `versProjet` lit le vrai payload (`maitre_ouvrage` en chaîne, `chef_projet_id`,
`avancement_reel` en %, plus de `client` ni de `chef_projet` objet) ; l'avancement théorique est **calculé** des dates
prévues ; la consommation budgétaire n'existe pas côté serveur (reste 0 — à ne pas présenter comme une mesure) ;
la création n'envoie plus `reference` (calculée par le serveur, qui répond 400 sinon — champ désormais en lecture
seule) ; suspendre / reprendre = `PATCH statut` (`SUSPENDU` / `EN_COURS`), plus de routes dédiées ; planning et
budget par `PATCH` ; chef de projet de la liste résolu par le tableau de bord, celui de la fiche par les
affectations puis `collaborateurs-affectables`.
**Lots et activités :** activités sous `/lots/{id}/activites/`, lot avec `date_*_prevue`, code d'activité composé
(`L-01.01`), `quantite_prevue` décimal en chaîne ; **l'équipe d'une activité se lit dans
`/projets/{id}/equipes/affectations/`** (le champ `equipe_ids` de l'activité ne reflète pas les affectations — défaut
trouvé en test) et s'écrit par POST/DELETE sur cette même liste. Plus de champ « dépendance » (inexistant).
**Équipes :** lecture/création conformes (`corps_etat`, chef et membres = collaborateur OU nom libre) ; le serveur
n'a **aucune route** pour modifier la composition après création : ajout, changement de rôle et retrait de membre
supprimés de l'interface (3 fenêtres + boutons de `FicheEquipe`).
**Nettoyage :** `simulationProjets`, `simulationLots`, `simulationTableauDeBord` supprimés (et la validation de bons
de paiement, qui visait des routes d'un module absent).

**Vérifié dans le navigateur :** liste des projets (nouveaux statuts), création d'un projet, fiche, création de lot,
lots/activités affichés avec codes/dates/budgets, équipes et affectation d'une équipe à une activité, fiche d'équipe,
suspension puis reprise. **Non vérifié à l'écran** (vérifié par API seulement) : fixation du planning/budget par le chef
de projet, création d'équipe depuis le tiroir, modification d'un projet.
**Restes connus :** avancement/consommation budgétaires (aucune donnée serveur), échéances/alertes/QHSE du tableau de
bord (le serveur n'envoie que `metriques`, `projets`, `bons_paiement_a_valider`, `receptions_materiaux`, `meteo`) ;
`quartier` absent ; le domaine « chantier » (rapports) garde sa simulation (`simulationJournal`).

## Règle unique des modules actifs (10 octobre 2026)

Décision de Durel : **tout module actif du catalogue est disponible pour une entreprise, sauf ceux que le super admin
a désactivés explicitement pour elle** (la règle de `core.droits._obtenir_modules_actifs`, déjà celle des droits réels).
`GET /modules/` (catalogue du tenant, donc matrice des rôles) et la section « Modules » de la fiche client
(`modules_du_client`) la reprennent au lieu de lire seulement les souscriptions explicites ; « Administration »
(module système) reste hors du catalogue du tenant. Effet : une entreprise en essai sans ligne de souscription voit tous
les modules, partout, de la même façon. Test : `TestRegleUniqueDesModulesActifs` (échoue avec l'ancien code).
À noter : `_obtenir_modules_actifs` applique encore le repli « table Module du tenant » quand il n'y a aucune ligne de
souscription, et le module GED (désactivé par défaut, A-15) devient actif dès qu'une ligne existe ; sans permission
associée, cela n'a aucun effet sur les droits.
