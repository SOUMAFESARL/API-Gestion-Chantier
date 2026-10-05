# Gabarit : docs/refonte/inventaire-lot0.md

Gemini copie ce gabarit vers `docs/refonte/inventaire-lot0.md`, remplace chaque `<...>` par un fait relevé dans le code, et supprime ces consignes.

**Règles de remplissage (les tests les vérifient)**
1. Une référence s'écrit `chemin/relatif/depuis/la/racine.py:LIGNE`. Elle doit exister. Le numéro de ligne est celui du fichier tel qu'il est au commit `base-refonte`.
2. Interdit dans ce fichier : `TODO`, `TBD`, `à compléter`, `probablement`, `sans doute`, `je suppose`, `il semble`, `peut-être`, `vraisemblablement`, et le point d'interrogation. Un doute va dans `docs/refonte/questions-ouvertes.md`, jamais ici.
3. Quand une chose n'existe pas dans le code, écrire `ABSENT` à la place des références. Ne jamais déduire ni imaginer.
4. Les numéros `I-01` à `I-10` et les formats de ligne ne changent pas.
5. Ne citer que des règles du cahier (identifiants `A-01` à `H-02`).

---

## I-01 Occurrences de `niveau_max` (A-12)

Commande de départ : parcourir tous les `.py` hors dossiers `migrations`. Lister **chaque** ligne qui contient `niveau_max`, tests compris.
Format : `- chemin:ligne | ce que fait cette ligne, en une phrase`

- <chemin:ligne> | <description>

Total : <N>

## I-02 Conditions copiées de test « est le DG » (B-03)

Lister chaque endroit où le code teste si un utilisateur est le DG par une condition écrite à la main.
Format : `- chemin:ligne | condition recopiée telle quelle`

- <chemin:ligne> | <condition>

Total : <N>

## I-03 Facturation et limites du plan (C-04)

Format : `- Clé : constat en une phrase | refs ou ABSENT`

- Limite collaborateurs actifs : <constat> | <chemin:ligne ou ABSENT>
- Limite projets : <constat> | <chemin:ligne ou ABSENT>
- Erreur dédiée à la limite : <constat> | <chemin:ligne ou ABSENT>
- Abonnement expiré (lecture seule) : <constat> | <chemin:ligne ou ABSENT>
- Actions de paiement : <constat> | <chemin:ligne ou ABSENT>

## I-04 Impersonation (H-01)

- Claim read_only émis : <constat> | <chemin:ligne ou ABSENT>
- Middleware lecteur du claim : <constat> | <chemin:ligne ou ABSENT>
- Méthodes bloquées : <liste exacte des méthodes HTTP bloquées> | <chemin:ligne ou ABSENT>
- Journalisation début de session : <constat> | <chemin:ligne ou ABSENT>
- Journalisation fin de session : <constat> | <chemin:ligne ou ABSENT>
- E-mail au DG : <constat> | <chemin:ligne ou ABSENT>

## I-05 Statut CRITIQUE (E-09)

Écrire d'abord un test dans `tests/caracterisation/test_statut_critique.py` qui décrit ce que fait AUJOURD'HUI `executer_evaluation_quotidienne_schema` sur un projet CRITIQUE. Le test doit passer sur le code actuel. Ne pas corriger le code.
Valeurs permises : `CONSERVE`, `ECRASE`, `STATUT_ABSENT`.

- Comportement actuel du statut CRITIQUE : <valeur> | tests/caracterisation/test_statut_critique.py:<ligne>

## I-06 REGISTRE des permissions (A-01, A-02)

Une seule ligne `Fichier du REGISTRE`, puis **tous** les codes du REGISTRE, un par ligne : `- code | module`. Le module est le préfixe du code. Ne pas lister `ged` ici (aucun code `ged.*`).

- Fichier du REGISTRE : REGISTRE | <chemin:ligne>
- <module>.<verbe> | <module>

Total : <N>

## I-07 Modules et portée proposée (D-04)

Un module par ligne, d'après les modules de I-06. Valeurs : `PROJET`, `GLOBALE`, `A_CONFIRMER`. Mettre `A_CONFIRMER` dès qu'une seule donnée du module n'est pas clairement rattachée à un projet. Ajouter la ligne `ged | A_CONFIRMER` si le module GED figure au catalogue.
Format : `- module | PORTEE`

- <module> | <PROJET|GLOBALE|A_CONFIRMER>

## I-08 Tests existants à adapter (A-12, E-08)

Lister les tests existants qui testent `niveau_max` (A-12) et les tests de statuts (E-08). Doivent figurer : `test_statuts_crud.py` et `test_statuts_projet.py`.
Format : `- chemin:ligne | pourquoi il devra changer`

- <chemin:ligne> | <raison>

Total : <N>

## I-09 Comptages de départ

Nombre de **lignes** contenant le mot (mot entier), dans les fichiers `.py` de production : hors `migrations`, hors dossiers `tests`/`test`, hors `test_*.py` et `conftest.py`.
Format : `- Mot : N`

- PermissionModule : <N>
- MembreDuProjet : <N>
- RoleRequis : <N>
- RoleGlobal : <N>
- role_global : <N>
- ROLES_DIRECTION : <N>
- ROLES_GESTION_CHANTIER : <N>
- ROLES_VALIDATION_CHANTIER : <N>
- ContexteCreationProjetView : <N>
- ProjetRoleModuleOverride : <N>
- appliquer_modeles_roles : <N>

## I-10 Tâche de fond, e-mail, audit (A-14, H-01)

- Tâche de fond (mécanisme) : <nom du mécanisme réellement utilisé> | <chemin:ligne ou ABSENT>
- Envoi d'e-mail existant : <fonction ou classe qui envoie un e-mail> | <chemin:ligne ou ABSENT>
- Journal d'audit existant : <modèle ou fonction d'audit> | <chemin:ligne ou ABSENT>
