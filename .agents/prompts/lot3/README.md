# Lot 3 — Paramétrage et accès de l'entreprise : prompts pour l'agent d'implémentation (backend)

Rédigé le 14/10/2026 par l'agent de cadrage (Claude) après validation du développeur, pour être
exécuté par un autre agent (Gemini sur Antigravity). **Toutes les décisions sont prises** : en cas
de doute, s'arrêter et demander au développeur, ne jamais inventer une règle.

Le frontend a son dossier jumeau : `../Application-Gestion-Chantier/.agents/prompts/lot3/`.

> **Prérequis absolu : le lot 2 est entièrement fusionné dans `develop` des deux dépôts.** La tâche
> F8 de ce lot modifie un fichier que la tâche F8 du lot 2 crée
> (`lib/api/simulationParametresPublics.ts`). Vérifier :
> `git log --oneline develop | grep -i "lot2\|back-office n'a plus de simulation"`.

---

## 1. Ordre d'exécution — impératif

| Ordre | Tâche | Dépôt | Point validé |
|---|---|---|---|
| 1 | `B1_erreurs_et_journal.md` | backend | 3.1, 3.3 |
| 2 | `F1_collaborateurs_reels.md` | frontend | 3.1 |
| 3 | `B2_renvoi_invitation.md` | backend | 3.2 |
| 4 | `F2_renvoi_invitation.md` | frontend | 3.2 |
| 5 | `F3_roles_reels.md` | frontend | 3.3, 3.4 |
| 6 | `B3_telephones_entreprise.md` | backend | 3.5 (US 2.1) |
| 7 | `F4_telephones_entreprise.md` | frontend | 3.5 (US 2.1) |
| 8 | `F5_logo_telephone.md` | frontend | 3.6 (US 2.2) |
| 9 | `F6_mot_de_passe_profil.md` | frontend | 3.7 |
| 10 | `F7_controle_inscription.md` | frontend (+ backend si écart) | 3.8 |
| 11 | `F8_cloture.md` | frontend | 3.9, 3.10 |

`PROMPT_DE_LANCEMENT.md` donne le message à coller dans Antigravity.

---

## 2. Règles communes

**Identiques à celles du lot 2** : relire `../lot2/README.md` §2 (lectures obligatoires, Git,
environnement Windows, vérifications avant commit, conventions). En résumé :

- branche `feature/lot3-<nom>` partie de `develop` à jour ; `git add <fichiers>` seulement ;
  fusion `--no-ff` ; branche supprimée ;
- **jamais `git push`** — pousser `develop` déploie en production ;
- relever les échecs de `pytest apps/ -q` et `pytest tests/acceptation -q` **sur `develop` avant
  la tâche** ; aucun échec nouveau après (`tests/acceptation/lot10` `verrou[9]` échoue sous Windows
  à cause des CRLF : connu, sans rapport) ;
- `ruff check` propre sur les applications touchées ;
- messages d'erreur **en français, mot pour mot** comme dans les fichiers de tâche.

Règles propres à ce dépôt qu'il faut avoir en tête pour ce lot :

- `apps.tenants` est dans `SHARED_APPS` : ses tables vivent dans le schéma **`public`**.
  `apps.accounts` est dans les deux (écart E1, voir `config/settings/base.py` l. 73-130) : les
  collaborateurs, rôles et invitations d'une entreprise vivent dans **son schéma**.
- `ModeleBase` (`apps/core/models/__init__.py:36`) donne `id`, `cree_le`, `modifie_le`,
  `cree_par`, `supprime_le`, `supprime_par`, et les gestionnaires `objects` (actifs) /
  `tous_objets`. **Suppression logique seulement** (Socle Commun).
- Journal d'audit de l'entreprise : `apps.audit.services.journaliser(action=, type_entite=,
  entite_id=, utilisateur_id=, valeur_avant=, valeur_apres=, adresse_ip=, appareil=)`, avec
  `action` pris dans `apps.core.enums.ActionAudit`. Exemple d'appel :
  `apps/accounts/services/invitations.py:232-245`. Il ne fait jamais échouer l'action.
- Adresse IP du client : `apps.core.ip_restriction.extraire_ip_client(request)`.

---

## 3. Décisions validées par le développeur le 14/10/2026

| # | Décision |
|---|---|
| 3.1 | Collaborateurs : simulation retirée **et** erreurs au format du produit **et** suspension, réactivation, suppression journalisées |
| 3.2 | Renvoi d'une invitation : nouvelle route + bouton ; l'ancien lien est révoqué |
| 3.3 | Rôles : simulation retirée, erreurs au format du produit |
| 3.4 | Droits d'un rôle par projet : **reportés**. Le composant mort et sa simulation sont supprimés ; le MLD (v1.7, §5.2.5) le dit déjà |
| 3.5 | **Plusieurs numéros par entreprise** : table `telephone_entreprise` (public) — libellé, numéro, principal ; 5 au plus, un seul principal ; `telephone_contact` suit le principal ; **format international E.164 validé pour tous les pays** (serveur et écran) ; affichés dans la configuration (lecture, saisie) et la fiche client du back-office (lecture) ; PDF : le principal seul ; modifiés avec la permission `administration.entreprise_modifier` |
| 3.6 | Logo : aussi sur téléphone dans l'en-tête ; l'initiale reste le visuel par défaut ; pas de marque blanche |
| 3.7 | Changer son mot de passe depuis le profil |
| 3.8 | Inscription : contrôle du contrat et de la chaîne à l'écran, code seulement si écart |
| 3.9 | Identité de la plateforme : branche simulée retirée (les tarifs simulés restent jusqu'au lot 6) |
| 3.10 | Non branchés, par décision : assistant de configuration, `/entreprise/`, liste et détail des invitations |

Précision de cadrage sur 3.5 : l'écran de configuration **propose déjà** un numéro fixe et des
numéros secondaires (`telephone_fixe`, `telephones_secondaires`) que **le serveur ignore sans
erreur** — ils sont perdus à chaque enregistrement. Le libellé `FIXE` est donc ajouté à la liste
validée (Mobile, WhatsApp, Standard, Comptabilité, Autre) pour reprendre ce que l'écran sait déjà
saisir.

Le MLD a été mis à jour par Claude (v1.7) dans `../../04_Conception/architecture_base_donnees/MLD_CCD_Digital.md`
— §4.1, §4.1.1 et §5.2.5. **Le lire avant B3** : il fait foi pour la table.

---

## 4. Fin du lot

Quand les onze tâches sont fusionnées (sans push) : compte rendu au développeur, tâche par
tâche (livré, tests, échecs avant / après, vérifié à l'écran ou non), puis **s'arrêter**.
Relecture par Claude (`revue-backend`, `revue-frontend`), puis push unique par le développeur.
