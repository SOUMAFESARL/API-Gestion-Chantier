# Contrat d'API Frontend — Gestion Documentaire (GED / F6)

> **Objet :** Contrat REST consommé par `Application-Gestion-Chantier/features/ged/adaptateur.ts`
> (tâches Frontend `3.5`, `3.7`, `3.10`, `3.12` de **ZANFACK Durel**).
> **Cible Backend :** à implémenter dans `apps/ged/views/`, `apps/ged/serializers/`, `apps/ged/filters.py`
> et `apps/ged/urls.py` par **ZRAN Sévérin** (tâches `3.3`, `3.6`, `3.8`, `3.9`, `3.11`), en s'appuyant
> sur les modèles, permissions et services déjà livrés dans `apps/ged/models/`, `apps/ged/permissions.py`
> et `apps/ged/services/documents.py` (`1.1`, `1.2`, `3.1`, `3.2`, `3.4`).

Toutes les routes authentifiées sont préfixées par `/api/v1/` (Bearer JWT, contexte entreprise D9).
Format d'erreur standard : `{"erreur": {"code", "message", "details", "trace_id"}}`.

---

## 1. Catégories & Origines

| Champ | Valeurs |
|---|---|
| `categorie` | `PLANS`, `CONTRATS`, `RAPPORTS`, `ADMINISTRATIF`, `PHOTOS`, `DIVERS` |
| `origine` | `MANUEL`, `F1_CONTRAT`, `F2_RAPPORT`, `F9_BRV` |

---

## 2. Format d'un document (`DocumentGed`)

```json
{
  "id": "uuid",
  "projet_id": "uuid",
  "projet_nom": "Immeuble Plateau",
  "projet_reference": "PRJ-2026-001",
  "categorie": "PLANS",
  "nom": "Plan de masse — Bâtiment administratif",
  "description": "Plan général d'implantation",
  "est_reference": true,
  "est_automatique": false,
  "origine": "MANUEL",
  "source_liaison": {
    "type_source": "F1_CONTRAT",
    "objet_id": "uuid"
  },
  "version_active": {
    "id": "uuid",
    "numero_version": 2,
    "numero": "v2",
    "nom_fichier": "plan_masse_v2.pdf",
    "taille": 3984588,
    "mime_type": "application/pdf",
    "hash_sha256": "a3f1...9c02",
    "commentaire": "Mise à jour cotes du hall administratif",
    "auteur": {
      "id": "uuid",
      "nom_complet": "Moussa Diallo"
    },
    "cree_le": "2026-11-20T14:22:00Z"
  },
  "nombre_versions": 2,
  "createur": {
    "id": "uuid",
    "nom_complet": "Moussa Diallo"
  },
  "cree_le": "2026-11-10T10:15:00Z",
  "modifie_le": "2026-11-20T14:22:00Z"
}
```

- `source_liaison` vaut `null` lorsque `est_automatique` est `false`.
- Tri par défaut : `est_reference DESC`, `modifie_le DESC` (documents de référence épinglés en tête).

---

## 3. Routes attendues (tâches Backend 3.3, 3.6, 3.8, 3.9, 3.11)

### 3.1 Lister & rechercher les documents — `GET /api/v1/ged/documents/` (3.3, 3.8, 3.11)

Filtre automatiquement selon les affectations projet et les droits `ged.voir_<categorie>` du rôle.

**Paramètres query (tous facultatifs, combinables) :**
- `projet` : UUID du projet
- `categorie` : `PLANS` | `CONTRATS` | `RAPPORTS` | `ADMINISTRATIF` | `PHOTOS` | `DIVERS`
- `origine` : `MANUEL` | `F1_CONTRAT` | `F2_RAPPORT` | `F9_BRV`
- `est_reference` : `true` | `false`
- `q` : recherche plein texte sur `nom`, `description`, nom de fichier
- `date_debut`, `date_fin` : dates ISO `YYYY-MM-DD` (filtre sur `cree_le`)

**Réponse `200` :** tableau paginé standard `{ "count": 12, "next": null, "previous": null, "results": [DocumentGed] }` (ou liste directe).

### 3.2 Déposer un document — `POST /api/v1/ged/documents/` (3.3)

`multipart/form-data` — exige `ged.deposer_<categorie>` sur le projet.
- `projet` (UUID, requis)
- `categorie` (string, requis)
- `nom` (string, requis)
- `description` (string, facultatif)
- `commentaire` (string, facultatif — note v1)
- `est_reference` (`true`/`false`, défaut `false`)
- `fichier` (binaire, requis, ≤ 50 Mo, `.pdf .jpg .jpeg .png .doc .docx .xls .xlsx`)

**Réponse `201` :** `DocumentGed`.

### 3.3 Détail d'un document — `GET /api/v1/ged/documents/{id}/` (3.8)

Exige `ged.voir_<categorie>`. Enregistre une entrée de consultation dans le journal d'audit GED.

**Réponse `200` :** `DocumentGed` enrichi avec `versions: [VersionDocument]` (triées par `numero_version DESC`).

### 3.4 Épingler / désépingler un document de référence — `PATCH /api/v1/ged/documents/{id}/` (3.3)

Exige `ged.deposer_<categorie>`.
Corps JSON : `{ "est_reference": true }` (ou mise à jour `nom` / `description` sur document manuel).

**Réponse `200` :** `DocumentGed`.

### 3.5 Supprimer un document — `DELETE /api/v1/ged/documents/{id}/` (3.3, 3.8)

Exige `peut_supprimer_document` (AD ou CP + `ged.supprimer_<categorie>` + `est_automatique=false`).
Corps JSON facultatif : `{ "motif": "…" }`. Enregistre la suppression dans le journal d'audit GED.

**Réponse `204`** (ou `403` / `422` `document_automatique_non_supprimable`).

### 3.6 Versions d'un document (3.6)

- **`GET /api/v1/ged/documents/{id}/versions/`** → liste `[VersionDocument]` triée par `numero_version DESC`.
- **`POST /api/v1/ged/documents/{id}/versions/`** (`multipart/form-data`, exige `ged.deposer_<categorie>`) :
  - `fichier` (binaire, requis)
  - `commentaire` (string, **obligatoire**, non vide)
  - `est_reference` (`true`/`false`, facultatif)
  - **Réponse `201` :** `VersionDocument`.

### 3.7 Téléchargement direct (3.8, 3.12)

- **`GET /api/v1/ged/documents/{id}/telecharger/`** : télécharge la version active (binaire `Content-Disposition: attachment`) et trace la consultation.
- **`GET /api/v1/ged/documents/{id}/versions/{version_id}/telecharger/`** : télécharge une version précise et trace la consultation.

### 3.8 Suivi des consultations & suppressions — `GET /api/v1/ged/documents/{id}/historique/` (3.8)

**Réponse `200` :** liste d'événements d'audit (consultations, téléchargements, dépôts, nouvelles versions, épinglages, partages, suppressions) :

```json
[
  {
    "id": "uuid",
    "action": "CONSULTATION",
    "action_libelle": "Consultation",
    "utilisateur": { "id": "uuid", "nom_complet": "Amina Koné" },
    "details": "Téléchargement v2",
    "cree_le": "2026-11-25T09:14:00Z"
  }
]
```

*(Route globale facultative pour l'onglet Journal GED : `GET /api/v1/ged/historique/?projet=<uuid>` renvoyant les mêmes entrées avec `document_id` et `document_nom`.)*

### 3.9 Partage externe temporaire 72 h (3.9)

- **`GET /api/v1/ged/documents/{id}/partages/`** : liste des liens actifs/expirés/révoqués du document.
- **`POST /api/v1/ged/documents/{id}/partages/`** (JSON facultatif : `{ "destinataire": "Bureau de contrôle", "note": "Pour visa" }`) : crée un lien expirant exactement à **+72 h**.
  **Réponse `201` :**
  ```json
  {
    "id": "uuid",
    "jeton": "tok_secure_random",
    "url_publique": "/partage/tok_secure_random",
    "destinataire": "Bureau de contrôle",
    "note": "Pour visa",
    "cree_par": { "id": "uuid", "nom_complet": "Moussa Diallo" },
    "cree_le": "2026-11-25T10:00:00Z",
    "expire_le": "2026-11-28T10:00:00Z",
    "revoque": false,
    "consultations": 0
  }
  ```
- **`DELETE /api/v1/ged/partages/{partage_id}/`** : révoque immédiatement le lien (`204`).

### 3.10 Consultation publique sans compte (3.9)

Routes anonymes (via `apiPlateforme`, sans JWT) :
- **`GET /api/v1/public/partages/{jeton}/`** → `200` :
  ```json
  {
    "jeton": "tok_secure_random",
    "expire_le": "2026-11-28T10:00:00Z",
    "destinataire": "Bureau de contrôle",
    "note": "Pour visa",
    "entreprise_nom": "SOUMAFE BTP",
    "projet_nom": "Immeuble Plateau",
    "projet_reference": "PRJ-2026-001",
    "document": {
      "nom": "Plan de masse — Bâtiment administratif",
      "categorie": "PLANS",
      "description": "Plan général d'implantation",
      "version": "v2",
      "nom_fichier": "plan_masse_v2.pdf",
      "taille": 3984588,
      "mime_type": "application/pdf",
      "hash_sha256": "a3f1...9c02",
      "depose_le": "2026-11-20T14:22:00Z"
    }
  }
  ```
  *(Renvoie `410` code `partage_expire` si expiré/révoqué, `404` si inconnu.)*
- **`GET /api/v1/public/partages/{jeton}/telecharger/`** → téléchargement direct du fichier de la version active (incrémente le compteur de consultations).
