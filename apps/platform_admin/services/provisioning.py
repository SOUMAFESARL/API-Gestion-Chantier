"""Service d'auto-provisioning de la plateforme (Bootstrap temporaire pour déploiement cPanel).

Permet d'appliquer automatiquement la migration `platform_admin` et d'initialiser
le compte Super Admin `support@ccd-digital.ci` dès la première tentative de connexion
sur l'environnement de production, sans intervention manuelle par terminal SSH.
"""

from __future__ import annotations

import logging

from django.core.management import call_command
from django.db import connection
from django_tenants.utils import get_public_schema_name, schema_context

logger = logging.getLogger(__name__)

_PROVISIONING_EFFECTUE = False


def auto_provisionner_super_admin() -> None:
    """Vérifie et provisionne la table `journal_plateforme` et le compte Super Admin."""
    global _PROVISIONING_EFFECTUE
    if _PROVISIONING_EFFECTUE:
        return

    try:
        public_schema = get_public_schema_name()
        with schema_context(public_schema):
            # 1. Vérification et application automatique de la migration platform_admin sur le schéma public
            tables = connection.introspection.table_names()
            if "journal_plateforme" not in tables:
                logger.info("Auto-provisioning: application de la migration platform_admin sur %s...", public_schema)
                call_command("migrate", "platform_admin", schema_name=public_schema, interactive=False)

            # 2. Vérification et initialisation / mise à niveau du compte Super Admin
            from apps.accounts.models import Utilisateur
            from apps.core.enums import RoleGlobal, StatutUtilisateur

            super_admin = Utilisateur.objects.filter(
                email__iexact="support@ccd-digital.ci"
            ).first()

            if super_admin is None:
                logger.info("Auto-provisioning: création du Super Admin support@ccd-digital.ci...")
                Utilisateur.objects.create_superuser(
                    email="support@ccd-digital.ci",
                    password="SuperAdmin2026!",
                    nom="Support",
                    prenom="CCD",
                    role_global=RoleGlobal.ADMIN,
                    statut=StatutUtilisateur.ACTIF,
                )
            else:
                logger.info("Auto-provisioning: mise à niveau / vérification du Super Admin support@ccd-digital.ci...")
                super_admin.is_superuser = True
                super_admin.is_staff = True
                super_admin.is_active = True
                super_admin.statut = StatutUtilisateur.ACTIF
                super_admin.role_global = RoleGlobal.ADMIN
                super_admin.set_password("SuperAdmin2026!")
                super_admin.save()

        _PROVISIONING_EFFECTUE = True
        logger.info("Auto-provisioning Super Admin exécuté avec succès.")
    except Exception as exc:
        logger.exception("Erreur lors de l'auto-provisioning du Super Admin : %s", exc)
