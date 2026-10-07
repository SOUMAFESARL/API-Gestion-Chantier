# Cadrage des tests, LOT 8 : collaborateurs, registre global, abonnement, lectures
Règles : C-01, C-02, C-03, C-04, C-05 (puce 1), F-03, F-04, F-05, F-06, F-07, F-08.
Marqueurs : `carac` (doit déjà passer à la fin du lot 7) et `regle` (introduit par le lot 8, échoue avant).
Document pour Durel et Claude. Il n'est pas donné à Gemini.

---

## 1. Réponses aux six questions du relevé

| # | Question | Décision |
|---|---|---|
| Q1 | Libérer l'e-mail au départ | À la désactivation, l'e-mail du compte est **renommé** en `ancien+{uuid}@depart.invalide`. L'adresse d'origine est conservée dans un champ `email_origine` (nullable) pour l'historique. Le compte reste en base, désactivé, avec `supprime_le` renseigné. La ligne du registre global est supprimée. |
| Q2 | Indicateur « sans chef de projet » | Champ booléen **stocké** `sans_chef_projet` (défaut `False`) sur `Projet`, exposé en lecture dans la liste et le détail d'un projet (aucun droit particulier au-delà de `projets.lire`). Mis à `True` au départ d'un collaborateur qui était `chef_projet` **ou** `conducteur_travaux`. Remis à `False` quand un nouveau `chef_projet` est affecté. |
| Q3 | Alerte au DG | **Un e-mail** au DG, un seul par départ, listant tous les projets devenus orphelins, envoyé après validation de la transaction (`transaction.on_commit`). Aucun e-mail si aucun projet n'est touché. Pas de nouveau modèle de notification. |
| Q4 | Registre global | Modèle `RegistreEmail` dans le schéma **public** (application `tenants`) : `email` (minuscules, unique), `entreprise` (clé étrangère PROTECT), `cree_le`. Alimenté dans la **même transaction** que la création d'un `Utilisateur` (inscription, invitation, création par un administrateur). Purgé au départ. Commande idempotente `remplir_registre_global` pour les données de développement. |
| Q5 | Dépassement du quota de projets | **Même enveloppe que le quota d'utilisateurs** (même exception `QuotaPlanAtteint`, même statut, même `erreur.code`), avec `details.ressource = "projets"`, `details.limite`, `details.utilises`. Le test lit l'enveloppe du quota utilisateurs au moment de l'exécution et exige l'égalité de statut et de code : aucune valeur n'est devinée. |
| Q6 | Ordre des contrôles en abonnement expiré | **L'abonnement passe en premier** : toute écriture hors chemins ouverts reçoit `abonnement_suspendu`, quel que soit le rôle. Raison : F-03 donne déjà `est_expire` à tout utilisateur connecté, donc cet ordre ne révèle rien de plus. |

Décisions complémentaires :

| # | Sujet | Décision |
|---|---|---|
| L8-1 | Erreur d'e-mail déjà pris (invitation, création, inscription) | 400, code `email_deja_utilise`, **même réponse** que l'e-mail appartienne à la même entreprise ou à une autre (ne pas révéler laquelle). Comparaison insensible à la casse. |
| L8-2 | Projets comptés dans le quota | Tous les projets **hors fin de vie** (`RESILIE`, `ARCHIVE`, `DESACTIVE`). Refus si le nombre atteint `limite_projets` ; `null` = illimité. |
| L8-3 | Collaborateurs comptés | Ceux déjà comptés par `verifier_quota_avant_invitation()` : non modifié. Un départ libère une place. |
| L8-4 | Invitation par un AD | Autorisée (`administration.collaborateurs_gerer`), avec les règles de B-09 : l'AD n'invite qu'avec un rôle dont toutes les permissions sont dans les siennes, jamais AD ni DG. Même refus (403) que pour un changement de rôle. |
| L8-5 | Chemins ouverts en abonnement expiré | Préfixes `/api/v1/cinetpay/`, `/api/v1/billing/` et `/api/v1/auth` restent ouverts au **middleware**. Chaque route sous ces préfixes doit alors être protégée par `administration.abonnement_gerer` (F-05), sinon un non-DG paierait ou changerait de plan. |
| L8-6 | Conducteur parti, chef en place | `sans_chef_projet = True` (le cahier dit « chef de projet ou conducteur »). Limite assumée : seul le réaffectation d'un chef le remet à `False`. |
| L8-7 | `RoleRequis` | Disparaît **entièrement** au lot 8 (billing, onboarding, tenants). Test statique : zéro occurrence hors `apps/core/permissions.py`. |
| L8-8 | Écriture de `/entreprise/` | PATCH et PUT : `administration.entreprise_modifier` (DG seul). L'AD, qui passe aujourd'hui, reçoit 403. |
| L8-9 | Facture inexistante pour un acteur autorisé | 404 ; pour un acteur non autorisé : 403 (la permission est vérifiée avant l'objet). |

---

## 2. Texte de C-04 à porter dans le cahier (levée de l'exception au gel)

> **C-04 [V] Limites du plan et expiration.**
> - Quota de collaborateurs : déjà appliqué (`verifier_quota_avant_invitation`, exception `QuotaPlanAtteint`). Inchangé.
> - Quota de projets : nouveau. Refus à la création (`POST /projets/`) avec la même enveloppe que le quota de collaborateurs, `details.ressource = "projets"`. Les projets en fin de vie ne comptent pas. `limite_projets` nul = illimité.
> - Abonnement expiré ou suspendu : toute écriture (POST, PUT, PATCH, DELETE) est refusée avec `abonnement_suspendu`, sauf sous `/api/v1/cinetpay/`, `/api/v1/billing/` et `/api/v1/auth`. Les routes ouvertes du billing exigent `administration.abonnement_gerer` (DG seul).
> - Le contrôle d'abonnement précède le contrôle de permission.
> - CA : un DG au quota reçoit 403 `quota_plan_atteint` ; un CP en abonnement expiré reçoit 403 `abonnement_suspendu` sur toute écriture.

---

## 3. Corrections au relevé

| # | Constat | Conséquence |
|---|---|---|
| R1 | F-05 dit « tout changement de plan ». Le relevé ne cite que `cinetpay/initier` et `statut`. | Inventaire obligatoire des routes sous `/billing/` et `/cinetpay/` et de leur garde actuelle et leur méthode (prérequis P1). |
| R2 | Les invitations ne figuraient pas dans les tests du lot 4. | B-09 (rôles attribuables) et B-03 (un seul DG) sont testés ici pour `POST /invitations/` et `POST /parametres/collaborateurs/`. |
| R3 | Le relevé place `RoleRequis` en F-07, billing, onboarding. | Lot 8 solde la dette D-08 laissée aux lots 3 et 4 (L8-7). |
| R4 | Le départ existant clôt les affectations par `.update(est_actif=False)` sans toucher à `supprime_le`. | Les tests ne vérifient que `est_actif = False` ; le lot 5 a déjà fixé la convention d'historique. |

---

## 4. Prérequis (avant d'écrire les tests)

| # | Prérequis | Auteur |
|---|---|---|
| P1 | `docs/refonte/lot8-inventaire.md` : (a) routes sous `/billing/` et `/cinetpay/` avec leur garde actuelle et leur méthode ; (b) routes sous `/configuration/` (onboarding) ; (c) tous les endroits qui créent ou suppriment un `Utilisateur` ; (d) tests existants à supprimer ou adapter (G-05) | Gemini, puis validation Durel |
| P2 | Réglage des tests : les tâches de fond s'exécutent-elles en mode synchrone ? Backend e-mail de test ? | Gemini (I-10) |
| P3 | Route de connexion, corps de `POST /invitations/` et de `POST /parametres/collaborateurs/`, route des factures et de leur PDF | Durel ou Gemini |
| P4 | Relevé des champs `Plan` et du moyen de rendre l'abonnement expiré en test | Gemini |
| P5 | Décisions de la section 1 validées par Durel | Durel |

---

## 5. Matrice de tests

Acteurs : DG, AD, DO, CP, DF, CT, VI et `perso_entreprise` (rôle personnalisé vide à portée ENTREPRISE).

### C-01 Ajout en deux temps
| Test | Attendu | Type |
|---|---|---|
| DG invite par `/invitations/` puis par `/parametres/collaborateurs/` | 2xx ; compte créé ; **aucune** `AffectationProjet` | carac |
| DO, CP, DF, CT, VI, `perso_entreprise` invitent | 403 | carac |
| AD invite avec rôle VI et avec rôle BAI | 2xx, deux routes | regle |
| AD invite avec DF, DO, CP, AD, DG (sous-ensemble de permissions non respecté) | 403, aucun compte créé | regle |
| DG invite avec le rôle DG | 403 (B-03) | regle |
| Les deux routes donnent les mêmes statuts, pour chaque acteur | égalité | regle |

### C-05 puce 1 Lectures réservées
| Test | Attendu | Type |
|---|---|---|
| DG liste collaborateurs et invitations | 200 | carac |
| AD liste collaborateurs et invitations | 200 | regle |
| DO, CP, DF, CT, VI, `perso_entreprise` | 403 sur les deux | regle |

### C-02 Départ
| Test | Attendu | Type |
|---|---|---|
| DG supprime un CC | compte `DESACTIVE`, `is_active = False`, `supprime_le` renseigné, ligne encore présente | carac |
| Même départ | ses affectations ont `est_actif = False` | carac |
| Même départ | il ne peut plus se connecter | carac |
| Départ d'un CP chef de projet de p1 et conducteur de p2 | `chef_projet` et `conducteur_travaux` à `None` ; `sans_chef_projet = True` pour p1 **et** p2 | carac pour les `None`, regle pour l'indicateur |
| Autres projets du même départ | `sans_chef_projet = False` | regle |
| Projet neuf | `sans_chef_projet = False` | regle |
| Affectation d'un nouveau chef sur p1 | `sans_chef_projet = False` | regle |
| Indicateur visible dans `GET /projets/` et `GET /projets/{id}/` pour un VI affecté | présent, booléen | regle |
| Après départ : création d'un collaborateur avec la même adresse | 2xx ; ancien compte `email != original` ; `email_origine = original` | regle |
| Adresse en majuscules à la réutilisation | 2xx | regle |
| E-mail d'alerte (avec `transaction.on_commit` exécuté) | un seul message, destinataire = DG, cite p1 et p2 | regle |
| Départ d'un CC sans projet | aucun e-mail | regle |
| Départ annulé (transaction annulée) | aucun e-mail | regle |
| Un départ libère une place du quota de collaborateurs | invitation possible à nouveau | carac |
| AD supprime un AD, ou DG supprime le DG | 403 (lots 2 et 4, non-régression) | carac |

### C-03 Registre global
| Test | Attendu | Type |
|---|---|---|
| Création d'un collaborateur | une ligne `RegistreEmail` (e-mail en minuscules, entreprise = demo) | regle |
| Invitation d'une adresse présente dans le registre pour une autre entreprise (`entreprise_fantome`) | 400 `email_deja_utilise`, aucun compte créé, deux routes | regle |
| Même adresse en casse différente | 400 identique | regle |
| Adresse déjà présente dans la même entreprise | 400 `email_deja_utilise` | regle |
| Le message d'erreur est identique dans les deux cas | égalité | regle |
| Départ : ligne purgée ; réinvitation : nouvelle ligne | présentes/absentes comme attendu | regle |
| Connexion d'un utilisateur de demo | 200 | carac |
| On supprime sa ligne du registre : connexion | refusée comme un mauvais mot de passe | regle |
| On la rétablit : connexion | 200 | regle |
| E-mail inconnu et mot de passe faux | statut et corps identiques | carac |
| Doublon d'e-mail inséré directement dans le registre | `IntegrityError`, casse comprise | regle |
| `remplir_registre_global` lancé deux fois | une ligne par e-mail de la base, aucun changement au second passage | regle |
| Statique | aucune occurrence de `Entreprise.objects` dans le service d'authentification | regle |

### C-04 Limites et expiration
| Test | Attendu | Type |
|---|---|---|
| Quota collaborateurs atteint : invitation par le DG | 403, enveloppe `Q` relevée à l'exécution | carac |
| Quota projets atteint (limite 2, deux projets vivants) : `POST /projets/` par le DG | statut et `erreur.code` égaux à `Q`, `details.ressource = "projets"` | regle |
| Limite 2, un projet vivant et un `ARCHIVE` | création acceptée | regle |
| `limite_projets` nul | création acceptée | regle |
| CP sans `projets.creer`, quota atteint | 403 de **permission**, pas de quota | regle |
| Abonnement expiré : écriture par DG et par CP (lot, équipe, collaborateur) | 403 `abonnement_suspendu` | carac |
| Abonnement expiré : lectures | 200 | carac |
| Abonnement expiré : connexion et renouvellement de jeton | non bloqués | carac |
| Abonnement expiré : DG appelle `cinetpay/initier` avec un corps vide | 400 (il a passé middleware et permission) | regle |
| Abonnement expiré : AD, CP, DO appellent `cinetpay/initier` | 403 avec `erreur.code` **différent** de `abonnement_suspendu` | regle |
| Idem pour chaque route d'écriture de l'inventaire P1 sous `/billing/` | mêmes résultats | regle |

### F-03 Abonnement
| Test | Attendu | Type |
|---|---|---|
| CP, DO, VI, DF lisent `GET /abonnement/` | **exactement** les clés `jours_essai_restants` et `est_expire` | regle |
| DG et AD | clés ⊇ ces deux et au moins une de plus (plan, quotas, échéances) | carac pour DG, regle pour AD |
| Abonnement expiré | `est_expire = True` pour tous | carac |

### F-04 Factures
| Test | Attendu | Type |
|---|---|---|
| DG et AD : liste, détail, PDF | passent la garde | carac |
| DF, DO, CP, VI, `perso_entreprise` : liste, détail, PDF | 403 | carac |
| Facture inexistante pour un non autorisé / pour DG | 403 / 404 (L8-9) | carac |
| `GET /abonnement/notifications/` : DG, AD | 200 | carac |
| Même route : DO, CP, DF, VI, `perso_entreprise` | 403 | regle |

### F-05 Paiement
| Test | Attendu | Type |
|---|---|---|
| `POST /cinetpay/initier/` corps vide : DG | 400 (garde passée) | carac |
| Même requête : AD, DO, CP, DF, VI | 403 | regle |
| `GET /cinetpay/statut/{id}/` : DG | ≠ 403 | carac |
| Même requête : AD et autres | 403 | regle |
| Changement de plan (route de P1) : DG / tous les autres | garde passée / 403 | regle |

### F-06 Modules
| Test | Attendu | Type |
|---|---|---|
| VI : tout code de permission présent dans la réponse | appartient aux permissions de `GET /auth/profil/` du VI | regle |
| VI : un module dont il n'a aucune permission | absent | regle |
| DG : toutes ses permissions de profil se retrouvent | inclusion | carac |
| Deux utilisateurs de rôles différents | réponses différentes | regle |

### F-07 Entreprise
| Test | Attendu | Type |
|---|---|---|
| `GET /entreprise/` et `/parametres/configuration/` : tous les rôles | 200 | carac |
| PATCH et PUT : DG | passe la garde | carac |
| PATCH et PUT : AD, DO, CP, DF, VI | 403 | regle |

### F-08 Onboarding
| Test | Attendu | Type |
|---|---|---|
| Chaque route GET de `/configuration/` (liste de P1) : DG, AD | passent la garde | carac |
| Mêmes routes : DO, CP, DF, CT, VI | 403 | carac |

### Statiques (non-régression et dette D-08)
| Test | Attendu | Type |
|---|---|---|
| `RoleRequis` | zéro occurrence hors `apps/core/permissions.py` | regle |
| `PermissionModule`, `MembreDuProjet` | zéro hors `apps/core/permissions.py` | carac |
| Constantes `ROLES_FACTURATION` et équivalents | absentes | regle |

---

## 6. Contrat des fabriques (`tests/fabriques_lot8.py`, construit sur `fabriques_lot7`)

Gemini ne l'adapte que pour des **noms réels**, jamais pour modifier une signature ou un retour.

| Fonction | Rôle |
|---|---|
| `url_invitations()`, `url_collaborateurs()`, `url_collaborateur(u)` | routes |
| `corps_invitation(email, role_global=None, role_personnalise_id=None)` | corps réel |
| `inviter(client, email, role_global, route)` | POST et réponse |
| `se_connecter(email, mot_de_passe)` | réponse de la route de connexion |
| `entreprise_fantome(nom)` | ligne `Entreprise` sans schéma réel (`auto_create_schema = False`) |
| `declarer_dans_registre(email, entreprise)`, `registre_ligne(email)`, `supprimer_du_registre(email)`, `nombre_dans_registre()` | accès au `RegistreEmail` |
| `fixer_limites_plan(utilisateurs=None, projets=None)` | modifie le plan de l'entreprise de test |
| `expirer_abonnement()`, `restaurer_abonnement()` | état d'expiration |
| `creer_facture()` | facture de test |
| `projet_avec_chef(utilisateur)`, `projet_avec_conducteur(utilisateur)` | projets orphelins potentiels |
| `courriels_envoyes()` | messages capturés (`mail.outbox`) |
| `valider_transaction()` | exécute les rappels `on_commit` |
| `enveloppe_quota_utilisateurs()` | statut et `erreur.code` relevés à l'exécution |

---

## 7. Ordre, dry-run, sortie

1. Gemini produit `lot8-inventaire.md` (P1) ; Durel le valide et valide la section 1.
2. Claude écrit `tests/acceptation/lot8/` et `fabriques_lot8.py`.
3. **Dry-run** sur la branche à la fin du lot 7 : `pytest tests/acceptation/lot8 -m carac` entièrement vert ; `-m regle` entièrement rouge, par assertion et non par erreur de fabrique.
4. Commit, verrouillage (`verifier_verrouillage.py`), tag `verrouille-lot8`.
5. Sortie de lot : `RoleRequis` à zéro ; `migrate_schemas` OK (migrations nouvelles : `RegistreEmail`, `email_origine`, `sans_chef_projet`, remplissage du registre) ; `pytest -q` complet sans régression sur les 385 tests des lots 1 à 7 ; `notes-changement-api.md` à jour (champs masqués, nouveaux 403 et 400, indicateur ajouté, e-mail libéré).
