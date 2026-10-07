"""Fabriques du lot 9 (propagation super admin, plateforme).

Construit sur les fabriques des lots 7 et 8.
Respecte le contrat de la section 7 du cadrage Claude.
"""

import itertools
import sys
from pathlib import Path
from typing import Any

from django.core import mail
from django.db import connection, transaction
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from fabriques_lot8 import ClientLot8, FabriqueLot8, HOST, API, obtenir_dg

_n_seq = itertools.count(9000)

HOTE_PLATEFORME = "localhost"
HOTE_CLIENT_A = "demo.localhost"
HOTE_CLIENT_B = "tenant-b.localhost"


class ClientLot9(ClientLot8):
    """Client API adapté pour le lot 9 (support requêtes plateforme et tenant)."""
    pass


class FabriqueLot9(FabriqueLot8):
    """Contrat utilisé par les tests du lot 9."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------ clients
    def client_pour(self, role_code):
        """Retourne un client authentifié pour un utilisateur ayant le rôle demandé."""
        if role_code == "DG":
            dg = obtenir_dg()
            return self.client(dg)
        u = self.utilisateur(role_code)
        return self.client(u)

    # ------------------------------------------------------------------ super admin
    def client_super_admin(self, staff=True, superuser=False):
        """Retourne un client authentifié avec un super admin du schéma public."""
        with schema_context(get_public_schema_name()):
            from apps.accounts.models import Utilisateur
            from apps.core.enums import RoleGlobal, StatutUtilisateur

            email = f"admin_l9_{next(_n_seq)}@plateforme.local"
            admin_user = Utilisateur.objects.create_user(
                email=email,
                password="AdminPassword123!",
                nom="Super",
                prenom="Admin",
                role_global=RoleGlobal.ADMIN,
                statut=StatutUtilisateur.ACTIF,
                is_staff=staff,
                is_superuser=superuser,
            )

        client = ClientLot9(HTTP_HOST=HOTE_PLATEFORME)
        client.force_authenticate(user=admin_user)
        client.admin_user = admin_user
        return client

    # ------------------------------------------------------------------ entreprises réelles (P3)
    def entreprise_a(self):
        """Entreprise A (schéma demo)."""
        with schema_context(get_public_schema_name()):
            from apps.tenants.models import Entreprise
            from apps.catalogue.models import CatalogueModule, EntrepriseModule

            e = Entreprise.objects.filter(schema_name="demo").first()
            if not e:
                e = Entreprise(
                    schema_name="demo",
                    raison_sociale="Entreprise Démo",
                    nom_commercial="Démo SARL",
                    email_contact="dg@demo.ci",
                )
                e.save(verbosity=0)

            for mod in CatalogueModule.objects.filter(supprime_le__isnull=True):
                EntrepriseModule.objects.get_or_create(
                    entreprise=e,
                    module=mod,
                    defaults={"est_actif": True},
                )
            return e

    def entreprise_b(self):
        """Entreprise B (schéma tenant_b)."""
        with schema_context(get_public_schema_name()):
            from apps.tenants.models import Entreprise
            from apps.catalogue.models import CatalogueModule, EntrepriseModule

            e = Entreprise.objects.filter(schema_name="tenant_b").first()
            if not e:
                e = Entreprise(
                    schema_name="tenant_b",
                    raison_sociale="Entreprise B Test",
                    nom_commercial="Entreprise B",
                    email_contact="contact@tenant-b.ci",
                )
                e.save(verbosity=0)

            for mod in CatalogueModule.objects.filter(supprime_le__isnull=True):
                EntrepriseModule.objects.get_or_create(
                    entreprise=e,
                    module=mod,
                    defaults={"est_actif": True},
                )
            return e

    # ------------------------------------------------------------------ catalogue & rôles
    def creer_modele_role(self, code: str, nom: str, portee: str = "PROJET", defauts: dict[str, list[str]] | None = None):
        """Crée un ModeleRole et ses ModeleRoleModule dans le schéma public."""
        with schema_context(get_public_schema_name()):
            from apps.catalogue.models import ModeleRole, ModeleRoleModule, CatalogueModule

            modele, _ = ModeleRole.objects.update_or_create(
                code=code,
                defaults={
                    "libelle": nom,
                    "description": f"Modèle {nom}",
                    "portee": portee,
                    "est_actif": True,
                },
            )

            if defauts:
                for mod_code, perms in defauts.items():
                    mod = CatalogueModule.objects.filter(code=mod_code).first()
                    mrm, _ = ModeleRoleModule.objects.update_or_create(
                        modele_role=modele,
                        module_code=mod_code,
                        defaults={
                            "module": mod,
                        },
                    )
            return modele

    def creer_module_catalogue(self, code: str, permissions: list[str] | None = None, defauts_par_role: dict[str, list[str]] | None = None):
        """Crée un module au catalogue avec ses permissions dans le schéma public."""
        with schema_context(get_public_schema_name()):
            from apps.catalogue.models import CatalogueModule, CataloguePermission, ModeleRole, ModeleRoleModule

            module, _ = CatalogueModule.objects.update_or_create(
                code=code.lower(),
                defaults={
                    "libelle": f"Module {code.capitalize()}",
                    "description": f"Description {code}",
                    "ordre": 10,
                    "est_actif": True,
                },
            )

            if permissions:
                for p_code in permissions:
                    perm, _ = CataloguePermission.objects.update_or_create(
                        code=p_code,
                        defaults={
                            "libelle": f"Perm {p_code}",
                            "description": f"Description {p_code}",
                            "est_actif": True,
                        },
                    )
                    perm.modules.add(module)

            if defauts_par_role:
                for role_code, perms in defauts_par_role.items():
                    m_role = ModeleRole.objects.filter(code=role_code).first()
                    if m_role:
                        ModeleRoleModule.objects.update_or_create(
                            modele_role=m_role,
                            module_code=code.lower(),
                            defaults={"module": module},
                        )

            return module

    def creer_role_perso(self, entreprise, code: str, nom: str, permissions: list[str] | None = None):
        """Crée un rôle personnalisé dans le schéma de l'entreprise."""
        with schema_context(entreprise.schema_name):
            from apps.accounts.models import Role, RoleModulePermission
            from apps.catalogue.models import CatalogueModule, CataloguePermission

            role = Role.objects.create(
                code=code,
                libelle=nom,
                description=f"Rôle personnalisé {nom}",
                portee="ENTREPRISE",
                est_actif=True,
                est_systeme=False,
            )

            if permissions:
                # Regrouper les permissions par module
                perms_par_module = {}
                for p_code in permissions:
                    mod_code = (p_code.split(".")[0] if "." in p_code else "projets").lower()
                    perms_par_module.setdefault(mod_code, []).append(p_code)

                from apps.accounts.models import Module
                for mod_code, p_list in perms_par_module.items():
                    mod_cat = CatalogueModule.objects.filter(code__iexact=mod_code).first()
                    mod_local = Module.objects.filter(code__iexact=mod_code).first()
                    rmp = RoleModulePermission.objects.create(
                        role=role,
                        module=mod_local,
                        module_catalogue=mod_cat,
                    )
                    all_variants = [p.lower() for p in p_list] + [p.upper() for p in p_list]
                    cat_perms = list(CataloguePermission.objects.filter(code__in=all_variants))
                    rmp.permissions_catalogue.set(cat_perms)

            return role

    def propager(self):
        """Appelle le service de propagation des rôles système."""
        try:
            from apps.platform_admin.services.catalogue import propager_roles_systeme
            return propager_roles_systeme()
        except ImportError:
            from django.core.management import call_command
            return call_command("propager_roles_systeme")

    # ------------------------------------------------------------------ activation / désactivation
    def activer_module(self, client, entreprise, module):
        """Active un module pour une entreprise via l'API super admin."""
        url = f"/api/v1/admins/clients/{entreprise.id}/modules/{module.id}/activer/"
        return client.post(url, format="json")

    def desactiver_module(self, client, entreprise, module):
        """Désactive un module pour une entreprise via l'API super admin."""
        url = f"/api/v1/admins/clients/{entreprise.id}/modules/{module.id}/desactiver/"
        return client.post(url, format="json")

    # ------------------------------------------------------------------ inspections
    def lignes_du_module(self, entreprise, module):
        """Retourne les lignes RoleModulePermission d'une entreprise pour ce module."""
        with schema_context(entreprise.schema_name):
            from apps.accounts.models import RoleModulePermission
            return list(RoleModulePermission.objects.filter(module_catalogue=module))

    def permissions_effectives_de(self, role, entreprise):
        """Retourne les permissions effectives calculées pour un porteur de ce rôle dans l'entreprise."""
        with schema_context(entreprise.schema_name):
            from apps.accounts.models import Utilisateur
            from apps.core.droits import permissions_effectives

            u = Utilisateur.objects.filter(role=role, supprime_le__isnull=True).first()
            if not u:
                u = Utilisateur.objects.create_user(
                    email=f"temp_{role.code.lower()}_{next(_n_seq)}@test.local",
                    password="TempPassword123!",
                    nom="Temp",
                    prenom="User",
                    role=role,
                )
            return permissions_effectives(u)

    def courriels_envoyes(self):
        """Retourne les courriels présents dans mail.outbox."""
        return list(mail.outbox)

    def valider_transaction(self):
        """Exécute tous les rappels on_commit en attente (simule la validation de la transaction)."""
        from django.db import connections

        conn = connections["default"]
        while conn.run_on_commit:
            en_attente = list(conn.run_on_commit)
            conn.run_on_commit[:] = []
            for _sids, func, _robust in en_attente:
                func()

    def entrees_audit(self, entreprise):
        """Retourne les entrées de JournalAudit dans le schéma de l'entreprise."""
        with schema_context(entreprise.schema_name):
            from apps.audit.models import JournalAudit
            return list(JournalAudit.objects.all().order_by("-horodatage"))

    def entrees_journal_plateforme(self):
        """Retourne les entrées de JournalPlateforme dans le schéma public."""
        with schema_context(get_public_schema_name()):
            from apps.platform_admin.models import JournalPlateforme
            return list(JournalPlateforme.objects.all().order_by("-horodatage"))

    def demarrer_assistance(self, client, entreprise, motif="Test assistance super admin"):
        """Démarre une session d'assistance."""
        url = f"/api/v1/admins/entreprises/{entreprise.id}/assistance/"
        return client.post(url, {"motif": motif}, format="json")

    def terminer_assistance(self, client):
        """Termine la session d'assistance."""
        url = "/api/v1/admins/assistance/deconnexion/"
        return client.post(url, format="json")

    def routes_admin_en_ecriture(self):
        """Introspection du résolveur d'URL pour lister toutes les routes d'écriture sous /admins/ et /admin/."""
        from django.urls import get_resolver
        resolver = get_resolver()

        routes = []

        def _explorer(patterns, prefix=""):
            for p in patterns:
                if hasattr(p, "url_patterns"):
                    _explorer(p.url_patterns, prefix + str(p.pattern))
                elif hasattr(p, "callback") and hasattr(p.callback, "view_class"):
                    route_path = prefix + str(p.pattern)
                    if route_path.startswith("api/v1/admins/") or route_path.startswith("api/v1/admin/"):
                        view_class = p.callback.view_class
                        for m in ["post", "put", "patch", "delete"]:
                            if hasattr(view_class, m):
                                routes.append((m.upper(), "/" + route_path.lstrip("/")))
                                break

        _explorer(resolver.url_patterns)
        return routes


fabrique_lot9 = FabriqueLot9()
