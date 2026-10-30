"""Les rôles système, gérés par le super admin — gabarits `ModeleRole` du catalogue.

Arbitrage du 16/10/2026 et du 19/10/2026 :
- **création** (19/10/2026) : le super admin saisit uniquement code, libellé et description.
  La portée est forcée à PROJET et aucun module n'est associé. C'est le DG de chaque
  entreprise qui attribue les permissions dans son propre éditeur de rôles. Le gabarit
  est créé puis propagé à toutes les entreprises (`propager_roles_systeme`, qui gère
  les conflits avec les rôles personnalisés et prévient le DG par courriel) ;
- **modification** (19/10/2026) : seuls le libellé et la description sont modifiables et
  réécrits dans toutes les entreprises ; la portée et les modules ne sont plus modifiables,
  les réglages de permissions faits par chaque DG étant souverains ;
- **suppression** : le gabarit disparaît et, dans chaque entreprise, le rôle
  devient personnalisé — personne ne perd ses droits, le DG le supprime ensuite.

Tous les rôles système se modifient et se suppriment, y compris les rôles du
socle, à l'exception unique du gabarit DG : sans gabarit DG, une entreprise créée
ensuite n'aurait plus de rôle pour son administrateur (`appliquer_modeles_roles`
ne crée que les gabarits actifs et `core/permissions.py` résout les droits par
`Role.objects.filter(code=user.role_global)`).
"""

from typing import Any

from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Role
from apps.catalogue.models import ModeleRole, ModeleRoleModule
from apps.core.exceptions import ErreurMetier
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


def creer_role_systeme(
    *,
    code: str,
    libelle: str,
    description: str = "",
    unique_par_projet: bool = False,
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
                portee="PROJET",
                unique_par_projet=unique_par_projet,
                est_actif=True,
            )

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
    with schema_context("public"), transaction.atomic():
        # `unique_par_projet` n'est qu'une valeur de départ : les entreprises existantes gardent
        # le réglage qu'elles ont choisi.
        for champ in ("libelle", "description"):
            if champ in donnees:
                setattr(modele, champ, str(donnees[champ]).strip())
        if "unique_par_projet" in donnees:
            modele.unique_par_projet = bool(donnees["unique_par_projet"])
        modele.save()

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
    if (modele.code or "").upper() == "DG":
        raise ErreurMetier(
            "Le rôle DG ne se supprime pas : chaque entreprise en a besoin "
            "pour son administrateur."
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
