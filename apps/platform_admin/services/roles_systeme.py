"""Les rôles système, gérés par le super admin — gabarits `ModeleRole` du catalogue.

Arbitrage du 16/10/2026 :
- **création** : le gabarit est créé puis propagé à toutes les entreprises
  (`propager_roles_systeme`, qui gère les conflits avec les rôles personnalisés) ;
- **modification** : libellé et description sont réécrits dans toutes les
  entreprises ; les modules ne valent que pour les entreprises à venir — les
  réglages de permissions faits par chaque DG sont préservés ;
- **suppression** : le gabarit disparaît et, dans chaque entreprise, le rôle
  devient personnalisé — personne ne perd ses droits, le DG le supprime ensuite.

Les dix rôles du socle (`CODES_ROLES_SYSTEME`) portent la logique métier
(affectations CP/CT/CC, propriété du DG) : ils se modifient, ils ne se
suppriment pas.
"""

from typing import Any

from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Role
from apps.accounts.services.roles import CODES_ROLES_SYSTEME
from apps.catalogue.models import CatalogueModule, ModeleRole, ModeleRoleModule
from apps.platform_admin.services.catalogue import propager_roles_systeme
from apps.platform_admin.services.notifications import journaliser_plateforme, journaliser_tenant
from apps.tenants.models import Entreprise

__all__ = [
    "creer_role_systeme",
    "modifier_role_systeme",
    "supprimer_role_systeme",
]


def _entreprises() -> list[Entreprise]:
    with schema_context("public"):
        return list(Entreprise.objects.exclude(schema_name="public"))


def _poser_modules(modele: ModeleRole, codes: list[str]) -> None:
    """Remplace les modules du gabarit (schéma public)."""
    codes = sorted({c.strip().lower() for c in codes if c and c.strip()})
    connus = {
        m.code.lower(): m
        for m in CatalogueModule.objects.filter(supprime_le__isnull=True)
    }
    inconnus = [c for c in codes if c not in connus]
    if inconnus:
        raise ValidationError({"modules": f"Modules inconnus : {', '.join(inconnus)}."})
    # Suppression logique (Socle commun) : l'index unique ne porte que sur les lignes actives.
    ModeleRoleModule.objects.filter(modele_role=modele).update(supprime_le=timezone.now())
    for code in codes:
        ModeleRoleModule.objects.create(modele_role=modele, module=connus[code], module_code=code)


def creer_role_systeme(
    *,
    code: str,
    libelle: str,
    description: str = "",
    portee: str = "PROJET",
    modules: list[str],
    acteur=None,
) -> ModeleRole:
    code = code.strip().upper()
    with schema_context("public"):
        if ModeleRole.objects.filter(code__iexact=code, supprime_le__isnull=True).exists():
            raise ValidationError({"code": "Un rôle système porte déjà ce code."})
        with transaction.atomic():
            modele = ModeleRole.objects.create(
                code=code,
                libelle=libelle.strip(),
                description=description.strip(),
                portee=portee,
                est_actif=True,
            )
            _poser_modules(modele, modules)

    resultat = propager_roles_systeme(acteur=acteur)
    journaliser_plateforme(
        action="CREATION_ROLE_SYSTEME",
        acteur=acteur,
        detail={"code": code, "libelle": modele.libelle, **resultat},
    )
    return modele


def modifier_role_systeme(
    modele: ModeleRole,
    *,
    donnees: dict[str, Any],
    acteur=None,
) -> ModeleRole:
    avant = {"libelle": modele.libelle, "description": modele.description}
    with schema_context("public"):
        with transaction.atomic():
            for champ in ("libelle", "description", "portee"):
                if champ in donnees:
                    setattr(modele, champ, str(donnees[champ]).strip())
            modele.save()
            if "modules" in donnees:
                _poser_modules(modele, donnees["modules"])

    apres = {"libelle": modele.libelle, "description": modele.description}
    if apres != avant:
        for entreprise in _entreprises():
            with schema_context(entreprise.schema_name):
                roles = Role.objects.filter(
                    code__iexact=modele.code, est_systeme=True, supprime_le__isnull=True
                )
                for role in roles:
                    role.libelle = modele.libelle
                    role.description = modele.description
                    role.save(update_fields=["libelle", "description", "modifie_le"])
                    journaliser_tenant(
                        entreprise=entreprise,
                        action="MODIFICATION",
                        type_entite="Role",
                        entite_id=role.id,
                        valeur_apres={"origine": "PLATEFORME", "avant": avant, "apres": apres},
                        acteur=acteur,
                    )

    journaliser_plateforme(
        action="MODIFICATION_ROLE_SYSTEME",
        acteur=acteur,
        detail={"code": modele.code, "avant": avant, "apres": apres},
    )
    return modele


def supprimer_role_systeme(modele: ModeleRole, *, acteur=None) -> dict:
    if modele.code.upper() in CODES_ROLES_SYSTEME:
        raise ValidationError(
            {"detail": "Les rôles du socle se modifient mais ne se suppriment pas."}
        )

    with schema_context("public"):
        maintenant = timezone.now()
        with transaction.atomic():
            ModeleRoleModule.objects.filter(modele_role=modele).update(supprime_le=maintenant)
            modele.supprime_le = maintenant
            modele.est_actif = False
            modele.save(update_fields=["supprime_le", "est_actif", "modifie_le"])

    convertis = 0
    for entreprise in _entreprises():
        with schema_context(entreprise.schema_name):
            roles = list(
                Role.objects.filter(
                    code__iexact=modele.code, est_systeme=True, supprime_le__isnull=True
                )
            )
            for role in roles:
                role.est_systeme = False
                role.save(update_fields=["est_systeme", "modifie_le"])
                convertis += 1
                journaliser_tenant(
                    entreprise=entreprise,
                    action="MODIFICATION",
                    type_entite="Role",
                    entite_id=role.id,
                    valeur_apres={
                        "origine": "PLATEFORME",
                        "message": "Rôle système retiré du catalogue : devenu personnalisé.",
                    },
                    acteur=acteur,
                )

    journaliser_plateforme(
        action="SUPPRESSION_ROLE_SYSTEME",
        acteur=acteur,
        detail={"code": modele.code, "roles_convertis": convertis},
    )
    return {"roles_convertis": convertis}
