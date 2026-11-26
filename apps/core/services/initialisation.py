"""Seed plateforme idempotent exécuté au déploiement (notamment cPanel sans SSH).

Garantit qu'une base vide (ou réinitialisée) reçoit toutes les données de
référence indispensables à la création de compte et au fonctionnement de la
plateforme :
- catalogue plateforme (modules, permissions, modèles de rôles, référentiels,
  listes et modèles de découpage, plans d'abonnement, identité plateforme) ;
- plans BTP actifs requis par l'inscription ;
- jours fériés de Côte d'Ivoire (année en cours et suivante) ;
- synchronisation du registre de permissions et propagation des rôles système ;
- compte Super Admin initial uniquement si aucun super-utilisateur n'existe.

Strictement idempotent : sur une base déjà en production, aucun catalogue en
usage, aucun tarif modifié ni aucun mot de passe existant n'est écrasé.
"""

from __future__ import annotations

import os
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

VAR_SUPER_ADMIN_EMAIL = "CCD_SUPER_ADMIN_EMAIL"
VAR_SUPER_ADMIN_MOTDEPASSE = "CCD_SUPER_ADMIN_MOTDEPASSE"


def ensemencer_base_plateforme(
    out: StringIO,
    *,
    stderr: StringIO | None = None,
    super_admin_email: str | None = None,
    super_admin_mot_de_passe: str | None = None,
) -> None:
    """Peuple les tables de référence manquantes et le Super Admin initial."""
    from apps.accounts.models import Utilisateur
    from apps.billing.models import Plan
    from apps.catalogue.models import (
        ListeValeursPlateforme,
        ModeleDecoupagePlateforme,
        ModeleRole,
    )
    from apps.entreprises.models import Entreprise

    io_kwargs: dict[str, StringIO] = {"stdout": out}
    if stderr is not None:
        io_kwargs["stderr"] = stderr

    # 1. Catalogue complet de la plateforme (389 objets sur une base neuve).
    if not ModeleRole._base_manager.exists() and not Entreprise.objects.exists():
        call_command("ensemencer_plateforme", **io_kwargs)
    elif (
        not ModeleDecoupagePlateforme._base_manager.exists()
        or not ListeValeursPlateforme._base_manager.exists()
    ):
        call_command("synchroniser_catalogue_decoupage", **io_kwargs)
    else:
        out.write("Catalogue de la plateforme déjà présent : conservé tel quel.\n")

    # 2. Plans d'abonnement requis à l'activation d'un compte (sans écraser les tarifs en prod).
    plan_essai_present = Plan.objects.filter(
        code__in=[Plan.Code.MAITRE_OEUVRE, Plan.Code.PRO]
    ).exists()
    if not plan_essai_present or not Plan.objects.filter(est_actif=True).exists():
        call_command("peupler_plans", **io_kwargs)

    # 3. Jours fériés légaux CI (année en cours + suivante, idempotent).
    annee = timezone.localdate().year
    call_command("charger_jours_feries", annees=[annee, annee + 1], **io_kwargs)

    # 4. Alignement du registre de permissions et propagation des rôles système.
    call_command("synchroniser_catalogue_permissions", **io_kwargs)
    call_command("propager_roles_systeme", **io_kwargs)

    # 5. Super Admin initial : créé uniquement si aucun super-utilisateur n'existe en base.
    email = (super_admin_email or os.environ.get(VAR_SUPER_ADMIN_EMAIL) or "").strip().lower()
    mot_de_passe = super_admin_mot_de_passe or os.environ.get(VAR_SUPER_ADMIN_MOTDEPASSE) or ""
    if Utilisateur.objects.filter(is_superuser=True).exists():
        out.write("Super Admin déjà présent : aucun compte recréé ni mot de passe modifié.\n")
    elif email and mot_de_passe:
        call_command(
            "creer_super_admin",
            email=email,
            motdepasse=mot_de_passe,
            **io_kwargs,
        )
