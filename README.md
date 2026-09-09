# 🏗️ API - Gestion de Chantier (Backend)

Bienvenue sur le dépôt backend de l'application de gestion de chantier BTP.  
Ce projet est développé avec **Python 3.12+**, **Django 5.2** et **Django REST Framework**.  
Il utilise une architecture SaaS multi-tenant avec PostgreSQL.

Ce guide est fait pour vous aider à lancer le projet sur votre machine en quelques minutes.

---

## 📋 1. Prérequis

Avant de commencer, vérifiez que vous avez installé sur votre ordinateur :
* **Python 3.12** (ou supérieur)
* **Git**
* **PostgreSQL 16** (ou Docker)
* **Redis** (optionnel en local)

---

## 🚀 2. Installation pas à pas

### Étape 1 : Cloner le projet
Ouvrez votre terminal et tapez :
```bash
git clone https://github.com/SOUMAFESARL/API-Gestion-Chantier.git
cd API-Gestion-Chantier
```

### Étape 2 : Créer et activer l'environnement virtuel Python

**Sur Windows (PowerShell) :**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**Sur Linux ou Mac :**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Étape 3 : Installer les dépendances
Installez tous les paquets nécessaires au développement :
```bash
pip install --upgrade pip
pip install -r requirements/local.txt
```

---

## ⚙️ 3. Configuration des variables d'environnement

Copiez le fichier d'exemple pour créer votre fichier `.env` local :

**Sur Windows :**
```powershell
copy .env.example .env
```

**Sur Linux ou Mac :**
```bash
cp .env.example .env
```

Ouvrez le fichier `.env` :
1. Générez une clé secrète Django en tapant cette commande :
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
2. Collez la clé obtenue dans `DJANGO_SECRET_KEY` dans votre `.env`.
3. Vérifiez le mot de passe et l'utilisateur de votre PostgreSQL (`POSTGRES_USER` et `POSTGRES_PASSWORD`).

---

## 🗄️ 4. Base de données

### Option A : Vous utilisez Docker (le plus simple)
Lancez PostgreSQL, Redis et Mailpit en arrière-plan :
```bash
docker compose up -d
```

### Option B : Vous avez PostgreSQL installé en local
Créez simplement une base de données vide nommée `ccd_digital` avec votre utilisateur PostgreSQL.

---

## 🔄 5. Migrations et Données de Démo

Exécutez les commandes suivantes dans l'ordre :

1. **Appliquer les migrations de la base de données :**
   ```bash
   python manage.py migrate_schemas --shared
   python manage.py migrate_schemas
   ```

2. **Créer l'entreprise et les utilisateurs de démo :**
   ```bash
   python manage.py creer_tenant_demo
   ```

Cette commande prépare automatiquement :
* Le schéma client de test (`demo`)
* Le compte administrateur :
  * **Email :** `admin@demo.ci`
  * **Mot de passe :** `Demo1234!`

---

## ▶️ 6. Lancer le serveur

Démarrez le serveur Django :
```bash
python manage.py runserver 0.0.0.0:8000
```

Le backend est prêt et écoute sur :
* **API Publique :** `http://localhost:8000`
* **Espace Client Démo :** `http://demo.localhost:8000`
* **Console d'administration :** `http://localhost:8000/admin/`

> 💡 **Astuce sur les domaines :**  
> Tous les navigateurs modernes résolvent automatiquement `*.localhost` vers `127.0.0.1`.  
> Vous n'avez pas besoin de modifier votre fichier hosts pour ouvrir `http://demo.localhost:8000`.

---

## 🧪 7. Commandes utiles au quotidien

* **Lancer la suite de tests :**
  ```bash
  pytest
  ```
* **Vérifier et formater le code (Ruff) :**
  ```bash
  ruff check .
  ruff format .
  ```
* **Voir les emails envoyés en local :**
  Par défaut, les emails s'affichent directement dans la console Django.  
  Si vous utilisez Docker avec Mailpit, ouvrez `http://localhost:8025`.

---

## 🤝 Besoin d'aide ?
Si vous rencontrez une erreur ou avez une question, contactez l'équipe technique SOUMAFE SARL.