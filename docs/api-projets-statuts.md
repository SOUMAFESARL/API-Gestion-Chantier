# Statuts du projet et cycle de vie chantier

Ce document décrit le fonctionnement des statuts de chantier, les permissions requises pour les transitions et l'impact de l'état du projet sur les écritures (Règles E-08, E-09, E-10).

---

## 1. Énumération des statuts

Le modèle `Projet` expose le champ `statut` avec les valeurs suivantes :
- **Opérationnels :** `EN_ATTENTE` (par défaut à la création), `EN_COURS`, `EN_RETARD`, `CRITIQUE`, `SUSPENDU`, `BLOQUE`.
- **Achevés :** `RECEPTIONNE`, `TERMINE`.
- **Fin de vie (clos) :** `RESILIE`, `ARCHIVE`, `DESACTIVE`.

---

## 2. Modification du statut et séparation des permissions (E-08)

Le statut d'un projet se modifie via `PATCH /api/v1/projets/{id}/` avec le payload :
```json
{
  "statut": "NOUVEAU_STATUT"
}
```

### Suppression de l'exception historique
L'ancienne règle permettant à tout membre affecté de modifier le statut avec la seule permission `projets.lire` a été **supprimée**. Toute modification de statut est soumise à un contrôle strict de permissions fines.

### Contrôles d'accès RBAC
- **Statuts opérationnels et achèvement :** Exige la permission **`projets.changer_statut`** (détenue par DG, AD, DO, CP).
  - Un utilisateur sans cette permission (ex: CT, CC, VI, BAI) reçoit **HTTP 403 Forbidden**.
- **Statuts de fin de vie et réouverture :** Le passage vers `RESILIE`, `ARCHIVE` ou `DESACTIVE`, ainsi que la sortie d'un état clos vers un état actif, exige la permission **`projets.resilier_archiver`** (réservée à DG, AD, DO).
  - Le Chef de Projet (CP) ne possède pas cette permission et reçoit **HTTP 403 Forbidden**.
- **Requêtes mixtes (statut + autres champs) :** La modification d'autres attributs du projet requiert la permission **`projets.ecrire`** en complément.

---

## 3. Protection du statut CRITIQUE (E-09)

- Le statut `CRITIQUE` peut être positionné manuellement par tout utilisateur disposant de `projets.changer_statut` (ex: CP, DO, AD, DG).
- **Protection contre l'écrasement automatique :** La tâche de fond d'évaluation quotidienne (`executer_evaluation_quotidienne_schema`) n'écrase jamais un projet au statut `CRITIQUE`. Le statut manuel reste maintenu jusqu'à ce qu'un utilisateur habilité le modifie explicitement.

---

## 4. Effets des statuts sur les écritures (E-10)

L'état d'avancement du chantier conditionne les opérations d'écriture autorisées.

### Projets en fin de vie (`RESILIE`, `ARCHIVE`, `DESACTIVE`)
Le projet devient en **lecture seule absolue** :
- La consultation (`GET`) reste autorisée pour les membres habilités.
- Toute tentative d'écriture (création de rapport journalier, création/modification/suppression de lot, d'activité, d'équipe, d'affectation, reprogrammation, ou modification du projet hors réouverture) est immédiatement rejetée avec **HTTP 409 Conflict** et le code d'erreur standard :
  ```json
  {
    "code": "projet_clos",
    "detail": "Le projet est clos (résilié, archivé ou désactivé). Aucune écriture n'est autorisée."
  }
  ```

### Projets achevés (`RECEPTIONNE`, `TERMINE`)
- La création de nouveaux rapports journaliers (`POST /api/v1/rapports/`) est interdite (**HTTP 409 Conflict**, code `projet_clos`).
- Les reprogrammations de calendrier (`POST /api/v1/projets/{id}/reprogrammer/`) sont interdites (**HTTP 409 Conflict**, code `projet_clos`).
- Les modifications de structure et de composition d'équipe restent autorisées si nécessaires.

### Projets en arrêt opérationnel (`SUSPENDU`, `BLOQUE`)
- Toutes les écritures habituelles restent permises (**HTTP 201 / 200**), permettant de renseigner des rapports, consigner des blocages ou adapter le planning pendant la suspension.

### Priorité des gardes (Ordre d'évaluation)
1. **Contrôle d'accès RBAC (HTTP 403) :** Vérifié en premier. Un acteur sans permission d'écriture reçoit un refus 403 même si le projet est clos.
2. **État du projet (HTTP 409 `projet_clos`) :** Vérifié dès que l'acteur dispose des droits requis mais que l'état du chantier l'interdit.
3. **Validation métier / intégrité des données (HTTP 400).**
