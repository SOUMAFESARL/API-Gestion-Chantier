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

Une fois par serveur PostgreSQL, en superutilisateur, créez le rôle de la portée plateforme :
```bash
psql -U postgres -f scripts/sql/roles_rls.sql
```

Puis, sur une base vide, une seule commande :
```bash
python manage.py monter_base --demo demo beta
```

Elle applique les migrations, vérifie l'isolation (RLS), ensemence le catalogue de la
plateforme et les jours fériés, puis crée et peuple deux entreprises de démonstration :
* comptes `*@demo.ci` et `*@beta.ci` (`admin@`, `cp.kone@`, `ct.yao@`, `cc.coulibaly@`…) ;
* mot de passe commun : `Demo1234!`.

`--super-admin <email>` crée en plus le compte du personnel CCD Digital, avec le mot de passe
lu dans la variable d'environnement `CCD_SUPER_ADMIN_MOTDEPASSE`.

---

## ▶️ 6. Lancer le serveur

Démarrez le serveur Django :
```bash
python manage.py runserver 0.0.0.0:8000
```

Le backend est prêt et écoute sur :
* **Point d'accès API (Domaine Unique) :** `http://localhost:8000`
* **Documentation Swagger :** `http://localhost:8000/api/v1/docs/`
* **Console d'administration :** `http://localhost:8000/admin/`

> 💡 **Architecture Domaine Unique (Option A) :**  
> Toutes les requêtes (plateforme et tenant) s'adressent à `http://localhost:8000`.  
> Le schéma PostgreSQL du client est automatiquement résolu par le token JWT (`Authorization: Bearer <token>`).


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

Pour configurer les mises à jour automatiques du serveur depuis GitHub, voir le
[guide de déploiement cPanel](docs/deploiement-cpanel.md).
Si vous rencontrez une erreur ou avez une question, contactez l'équipe technique SOUMAFE SARL.
