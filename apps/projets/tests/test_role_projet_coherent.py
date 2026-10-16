"""Règle du 16/10/2026 : sur un projet, on tient le rôle qu'on a sur la plateforme."""

from datetime import date

import pytest
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, RoleProjet, StatutProjet, StatutUtilisateur
from apps.projets.models import Projet
from apps.projets.serializers.affectation import AffectationProjetCreateSerializer

SCHEMA = "demo"

pytestmark = pytest.mark.django_db


def _utilisateur(email, role):
    u, _ = Utilisateur.tous_objets.get_or_create(
        email=email,
        defaults={"nom": "Test", "prenom": "R", "role_global": role},
    )
    u.role_global, u.role, u.statut, u.is_active = role, None, StatutUtilisateur.ACTIF, True
    u.save()
    return u


def _valide(user, role_projet) -> bool:
    serializer = AffectationProjetCreateSerializer(
        data={"utilisateur_id": str(user.id), "role_projet": role_projet}
    )
    return serializer.is_valid()


def test_un_ct_ne_s_affecte_que_comme_ct():
    with schema_context(SCHEMA):
        Projet.objects.get_or_create(
            reference="PRJ-ROLE-01",
            defaults={
                "nom": "Chantier rôle",
                "ville": "Abidjan",
                "date_debut_prevue": date(2026, 1, 1),
                "date_fin_prevue": date(2026, 12, 31),
                "statut": StatutProjet.EN_COURS,
            },
        )
        ct = _utilisateur("ct.coherent@demo.ci", RoleGlobal.CONDUCTEUR_TRAVAUX)
        assert _valide(ct, RoleProjet.CONDUCTEUR_TRAVAUX)
        assert not _valide(ct, RoleProjet.CHEF_PROJET)
        assert not _valide(ct, RoleProjet.CHEF_CHANTIER)
        assert not _valide(ct, RoleProjet.VISITEUR)
