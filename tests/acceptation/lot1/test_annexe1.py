"""Tests d'acceptation de la matrice de l'Annexe 1 (rôles système et défauts des codes projets)."""

import pytest
from django_tenants.utils import schema_context

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA_TEST = "demo"

pytestmark = pytest.mark.django_db

ATTENDU = {
    "projets.creer": {"DG", "AD", "DO"},
    "projets.changer_statut": {"DG", "AD", "DO", "CP"},
    "projets.resilier_archiver": {"DG", "AD", "DO"},
    "projets.affecter_membres": {"DG", "AD", "CP"},
    "projets.gerer_equipes": {"DG", "AD", "CP", "CT"},
    "projets.voir_montants": {"DG", "DO", "DF", "CP"},
}
ROLES = ["DG", "AD", "DO", "DF", "CP", "CT", "CC", "MAG", "BAI", "VI"]


@pytest.mark.parametrize("code_permission,roles_autorises", ATTENDU.items())
def test_annexe1_matrice_roles_systeme(client_tenant, code_permission, roles_autorises):
    """[Annexe 1] Pour chaque code nouveau, vérifie sa présence ou absence stricte selon la matrice."""
    with schema_context(SCHEMA_TEST):
        for code_role in ROLES:
            role_obj = Role.objects.filter(code=code_role, supprime_le__isnull=True).first()
            if not role_obj:
                continue

            user, _ = Utilisateur.tous_objets.get_or_create(
                email=f"test.annexe1.{code_role.lower()}@demo.ci",
                defaults={
                    "nom": f"Nom_{code_role}",
                    "prenom": "Annexe1",
                    "role_global": getattr(RoleGlobal, code_role, RoleGlobal.VISITEUR),
                    "statut": StatutUtilisateur.ACTIF,
                },
            )
            if code_role == "DG":
                user.is_owner = True
            else:
                user.is_owner = False
            user.save()

            client_tenant.force_authenticate(user=user)
            rep = client_tenant.get("/api/v1/auth/profil/")
            assert rep.status_code == 200
            perms_effectives = set(rep.data.get("permissions", []))

            if code_role in roles_autorises:
                assert code_permission in perms_effectives, (
                    f"Rôle {code_role} devrait posséder {code_permission}"
                )
            else:
                assert code_permission not in perms_effectives, (
                    f"Rôle {code_role} ne devrait PAS posséder {code_permission}"
                )


def test_annexe1_roles_perso_sans_les_six_codes(client_tenant):
    """[Annexe 1] Les rôles personnalisés préexistants ne reçoivent aucun des six codes nouveaux."""
    with schema_context(SCHEMA_TEST):
        role_perso, _ = Role.objects.get_or_create(
            code="ANCIEN_PERSO",
            defaults={"libelle": "Ancien Rôle Perso", "est_systeme": False, "est_actif": True},
        )
        user_perso, _ = Utilisateur.tous_objets.get_or_create(
            email="user.ancien.perso@demo.ci",
            defaults={
                "nom": "Ancien",
                "prenom": "Perso",
                "role_global": RoleGlobal.VISITEUR,
                "role_personnalise": role_perso,
                "statut": StatutUtilisateur.ACTIF,
            },
        )
        user_perso.role_personnalise = role_perso
        user_perso.save()

    client_tenant.force_authenticate(user=user_perso)
    rep = client_tenant.get("/api/v1/auth/profil/")
    assert rep.status_code == 200
    perms_effectives = set(rep.data.get("permissions", []))

    for code_nouveau in ATTENDU.keys():
        assert code_nouveau not in perms_effectives, (
            f"Le rôle personnalisé ne doit pas recevoir par défaut le code nouveau {code_nouveau}"
        )
