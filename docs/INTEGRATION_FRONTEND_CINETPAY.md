# Guide d'Intégration Frontend — Paiement CinetPay & Abonnements SaaS BTP

Ce document explique comment connecter l'application Frontend aux APIs de paiement et d'abonnement développées sur le Backend.

---

## 1. Vue d'Ensemble du Parcours Utilisateur

Le parcours de paiement utilise le **Guichet Hébergé CinetPay** (le moyen le plus simple et sécurisé pour encaisser Wave, Orange Money, MTN MoMo et Carte bancaire) :

```text
[Page Forfaits] 
       │
       ▼ (1) Clic sur "Choisir ce forfait"
[Appel API Backend : POST /api/v1/cinetpay/initier/]
       │
       ▼ (2) Le backend renvoie { payment_url, transaction_id }
[Redirection du navigateur vers payment_url]
       │
       ▼ (3) L'utilisateur paie sur CinetPay (Wave, Orange, MTN, Carte)
[CinetPay redirige vers le Frontend : /abonnements/statut?transaction_id=TX...]
       │
       ▼ (4) La page interroge GET /api/v1/cinetpay/statut/:transaction_id/
[Écran de confirmation avec Facture OHADA & Accès Débloqué !]
```

---

## 2. Les 3 Endpoints Backend à Utiliser

L'URL de base du backend est :
- En développement local : `http://localhost:8000`
- En production : `https://api.votre-domaine.com`

---

### Endpoint 1 : Récupérer le catalogue des forfaits BTP
Permet d'afficher la grille tarifaire (mensuelle ou annuelle) sur votre page de tarification.

* **Méthode** : `GET`
* **Route** : `/api/v1/plans/`
* **Authentification** : Aucune (Endpoint public)
* **Exemple de Réponse (`200 OK`)** :
```json
[
  {
    "id": 1,
    "code": "BATISSEUR",
    "nom": "Bâtisseur",
    "description": "Idéal pour les artisans et petites entreprises du bâtiment.",
    "prix_mensuel_fcfa": 19000,
    "prix_annuel_fcfa": 190000,
    "max_projets": 3,
    "max_utilisateurs": 5,
    "stockage_max_go": 2,
    "fonctionnalites_ia": false
  },
  {
    "id": 2,
    "code": "MAITRE_OEUVRE",
    "nom": "Maître d'Œuvre",
    "description": "Pour les cabinets d'architecture et PME de construction.",
    "prix_mensuel_fcfa": 49000,
    "prix_annuel_fcfa": 490000,
    "max_projets": 50,
    "max_utilisateurs": 25,
    "stockage_max_go": 10,
    "fonctionnalites_ia": true
  },
  {
    "id": 3,
    "code": "PROMOTEUR",
    "nom": "Promoteur",
    "description": "Pour les grandes entreprises, promoteurs et majors du BTP.",
    "prix_mensuel_fcfa": 119000,
    "prix_annuel_fcfa": 1190000,
    "max_projets": null,
    "max_utilisateurs": null,
    "stockage_max_go": null,
    "fonctionnalites_ia": true
  }
]
```
> *Note : `null` pour `max_projets`, `max_utilisateurs` ou `stockage_max_go` signifie **Illimité**.*

---

### Endpoint 2 : Initier une session de paiement (Protection Anti-Double Débit)
Appelé lorsque l'utilisateur sélectionne un forfait et clique sur **"Procéder au paiement"**.

* **Méthode** : `POST`
* **Route** : `/api/v1/cinetpay/initier/`
* **Authentification** : `Bearer <token_jwt>` (Administrateur d'entreprise).
* **Corps de la requête (`JSON`)** :
```json
{
  "plan_code": "MAITRE_OEUVRE",
  "cycle": "MENSUEL"
}
```
> Valeurs acceptées pour `cycle` : `"MENSUEL"` ou `"ANNUEL"`.

* **Cas nominal (`200 OK`)** :
```json
{
  "payment_url": "https://api-checkout.cinetpay.com/v2/payment/...",
  "payment_token": "a1b2c3d4...",
  "transaction_id": "TX202609111416559E094A",
  "numero_facture": "FAC-2026-09-0001",
  "montant_fcfa": 49000,
  "forfait": "Maître d'Œuvre",
  "cycle": "MENSUEL",
  "mode_simulation": false
}
```

* **Cas de verrouillage actif (`409 Conflict`)** :
Si une session a déjà été initiée il y a moins de 10 minutes pour cette entreprise, l'API protège contre le double débit et renvoie :
```json
{
  "detail": "Un paiement de 49 000 FCFA est déjà en cours pour cette entreprise...",
  "code": "PAIEMENT_EN_COURS",
  "transaction_en_cours": {
    "transaction_id": "TX202609111416559E094A",
    "reference_facture": "FAC-2026-09-0001",
    "montant_fcfa": 49000,
    "forfait": "Maître d'Œuvre",
    "statut": "INITIE",
    "secondes_restantes": 480,
    "cree_le": "2026-09-14T18:00:00Z"
  }
}
```
> **Action UI recommandée en 409** : Afficher un dialogue avec compte à rebours : *"Un paiement est déjà en cours. Veuillez confirmer sur votre téléphone ou annuler pour recommencer."*, avec un bouton **"Annuler la tentative"** branché sur l'Endpoint 3.

---

### Endpoint 3 : Annuler une tentative en cours (Abandon Explicite)
Permet à l'utilisateur d'annuler sa session en attente pour débloquer immédiatement une nouvelle tentative (ou changer d'opérateur).

* **Méthode** : `POST`
* **Route** : `/api/v1/cinetpay/annuler/`
* **Authentification** : `Bearer <token_jwt>`
* **Corps de la requête (`JSON`)** :
```json
{
  "transaction_id": "TX202609111416559E094A",
  "motif": "Changement de moyen de paiement"
}
```
* **Réponse (`200 OK`)** :
```json
{
  "statut": "ANNULE",
  "transaction_id": "TX202609111416559E094A",
  "message": "La tentative de paiement a été annulée avec succès."
}
```
> **Filet de sécurité (Règle C1)** : Si le compte Mobile Money du client a quand même été débité par l'opérateur après l'annulation, notre backend réactivera automatiquement la transaction en `CONFIRME` dès notification et prolongera son abonnement sans perte.

---

### Endpoint 4 : Vérifier le statut du paiement
Utilisé sur votre page de retour frontend (`/abonnements/statut`) ou pour vérifier une transaction en cours.

* **Méthode** : `GET`
* **Route** : `/api/v1/cinetpay/statut/:transaction_id/`  
* **Authentification** : `Bearer <token_jwt>`
* **Exemple de Réponse (`200 OK`)** :
```json
{
  "transaction_id": "TX202609111416559E094A",
  "statut": "CONFIRME",
  "statut_affichage": "Confirmé",
  "mode_paiement": "Wave",
  "moyen_paiement": "Wave",
  "montant_fcfa": 49000,
  "numero_facture": "FAC-2026-09-0001",
  "reference_facture": "FAC-2026-09-0001",
  "paye_le": "2026-09-14T18:02:15Z",
  "abonnement_actif": true,
  "est_valide": true,
  "date_fin": "2026-10-14",
  "abonnement_expire_le": "2026-10-14T18:00:00Z",
  "entreprise": "Cabinet Architecture & BTP",
  "plan": "Maître d'Œuvre"
}
```

#### Les valeurs possibles pour `statut` :
| Statut | Signification | Action UI recommandée |
| :--- | :--- | :--- |
| **`CONFIRME`** | Paiement certifié, abonnement activé. | Badge vert de succès, facture OHADA et bouton *"Accéder à mon espace"*. |
| **`EN_ATTENTE_OPERATEUR`** / **`INITIE`** | Demande envoyée à l'opérateur (push USSD/OTP en attente). | Afficher message pédagogique, spinner et compte à rebours. Polling toutes les 3s (1 min) puis 10s. |
| **`ANNULE`** | Annulation explicite demandée par le client. | Message d'information avec possibilité de relancer un paiement. |
| **`EXPIRE`** | Délai de confirmation dépassé (> 24h). | Inviter le client à initier une nouvelle session. |
| **`ECHOUE`** | Rejet opérateur (solde insuffisant, code PIN erroné). | Afficher le motif d'échec et proposer un nouvel essai. |

---

### Endpoint 5 : Consultation de l'abonnement & Paiement en cours
Permet de savoir dès le chargement du Dashboard ou de la page Tarifs si un paiement Mobile Money est en attente.

* **Méthode** : `GET`
* **Route** : `/api/v1/abonnement/`
* **Authentification** : `Bearer <token_jwt>`
* **Champ enrichi `paiement_en_cours`** :
```json
{
  "id": "...",
  "statut": "ESSAI",
  "plan": { "code": "MAITRE_OEUVRE", "libelle": "Maître d'Œuvre" },
  "paiement_en_cours": {
    "transaction_id": "TX202609111416559E094A",
    "reference_facture": "FAC-2026-09-0001",
    "montant_fcfa": 49000,
    "forfait": "Maître d'Œuvre",
    "statut": "INITIE",
    "secondes_restantes": 510,
    "cree_le": "2026-09-14T18:00:00Z"
  }
}
```
> Si aucun paiement n'est en attente, `"paiement_en_cours": null`.

---

## 3. Exemple d'Intégration Frontend (React / Next.js)

### A. Fichier de service API (`src/services/billing.js`)

```javascript
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// 1. Récupérer la liste des plans
export async function getPlans() {
  const res = await fetch(`${API_BASE_URL}/api/v1/plans/`);
  return res.json();
}

// 2. Lancer un paiement
export async function initierPaiement(planCode, cycle, authToken) {
  const res = await fetch(`${API_BASE_URL}/api/v1/cinetpay/initier/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authToken}`,
    },
    body: JSON.stringify({
      plan_code: planCode,
      cycle: cycle, // "MENSUEL" ou "ANNUEL"
    }),
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Erreur lors de l'initialisation du paiement");
  }

  return res.json();
}

// 3. Vérifier l'état du paiement
export async function verifierStatutPaiement(transactionId, authToken) {
  const res = await fetch(`${API_BASE_URL}/api/v1/cinetpay/statut/${transactionId}/`, {
    headers: {
      'Authorization': `Bearer ${authToken}`,
    },
  });
  return res.json();
}
```

---

### B. Bouton d'achat sur la page des tarifs (`PlansPage.jsx`)

```jsx
import React, { useState } from 'react';
import { initierPaiement } from '@/services/billing';

export function PlanCard({ plan, cycle, authToken }) {
  const [loading, setLoading] = useState(false);

  const handleSouscrire = async () => {
    try {
      setLoading(true);
      const res = await initierPaiement(plan.code, cycle, authToken);
      // Redirection automatique vers le guichet de paiement CinetPay
      window.location.href = res.payment_url;
    } catch (err) {
      alert("Impossible de lancer le paiement : " + err.message);
      setLoading(false);
    }
  };

  return (
    <div className="border p-6 rounded-lg shadow">
      <h3>{plan.nom}</h3>
      <p className="text-2xl font-bold">
        {cycle === 'MENSUEL' ? plan.prix_mensuel_fcfa : plan.prix_annuel_fcfa} FCFA
      </p>
      <button 
        onClick={handleSouscrire} 
        disabled={loading}
        className="btn-primary mt-4"
      >
        {loading ? "Connexion sécurisée..." : "Payer par Mobile Money / Carte"}
      </button>
    </div>
  );
}
```

---

### C. Page de confirmation de retour (`/abonnements/statut/page.jsx`)

Lorsque CinetPay termine le paiement, il redirige l'utilisateur vers :  
`http://localhost:3000/abonnements/statut?transaction_id=TX2026...`

```jsx
import React, { useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { verifierStatutPaiement } from '@/services/billing';

export default function StatutPaiementPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const transactionId = searchParams.get('transaction_id');

  const [etat, setEtat] = useState(null);
  const [chargement, setChargement] = useState(true);

  useEffect(() => {
    if (!transactionId) return;

    const token = localStorage.getItem('access_token');
    
    // Vérification auprès de l'API backend
    verifierStatutPaiement(transactionId, token)
      .then((data) => {
        setEtat(data);
        setChargement(false);
      })
      .catch(() => setChargement(false));
  }, [transactionId]);

  if (chargement) {
    return <div className="p-8 text-center">Vérification de votre paiement en cours...</div>;
  }

  if (!etat || etat.statut === 'ECHOUE') {
    return (
      <div className="p-8 text-center text-red-600">
        <h2>Paiement non finalisé</h2>
        <p>Le paiement n'a pas pu être validé ou a été annulé.</p>
        <button onClick={() => router.push('/tarifs')}>Réessayer</button>
      </div>
    );
  }

  return (
    <div className="p-8 text-center text-green-700">
      <h2 className="text-3xl font-bold">Félicitations ! Votre abonnement est actif 🎉</h2>
      <p className="mt-2">Forfait activé : <strong>{etat.plan}</strong></p>
      <p>Facture générée : <strong>{etat.reference_facture}</strong></p>
      <p>Moyen utilisé : <strong>{etat.moyen_paiement}</strong></p>
      <button 
        onClick={() => router.push('/tableau-de-bord')}
        className="mt-6 px-6 py-2 bg-green-600 text-white rounded"
      >
        Accéder à mon espace de travail
      </button>
    </div>
  );
}
```

---

## 4. Test en Local (Mode Simulation / Hors-Ligne)

Pour tester l'interface frontend en local **sans dépenser d'argent réel** et même sans connexion Internet :
- Le backend bascule automatiquement en mode simulation si les serveurs distants ne répondent pas.
- La `payment_url` retournée redirige immédiatement vers votre page de statut locale avec un paiement simulé réussi.
- Vous pouvez également valider n'importe quelle transaction manuellement avec la commande backend :
  ```powershell
  python manage.py simuler_webhook_cinetpay --moyen=WAVE
  ```

---

## 5. Contact & Support
En cas d'erreur de statut HTTP (401 Unauthorized, 400 Bad Request), vérifiez que :
1. Le token JWT d'authentification est bien envoyé dans les en-têtes `Authorization: Bearer <token>`.
2. L'utilisateur connecté possède bien le rôle Administrateur de l'entreprise.
