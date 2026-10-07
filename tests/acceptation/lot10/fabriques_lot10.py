"""Passerelle des tests HTTP du lot 10 (F-09, G-02) vers les fabriques réelles.

Contrat des tests d'acceptation du Lot 10.
"""
from contextlib import contextmanager
import itertools
from django_tenants.utils import get_public_schema_name, schema_context

_seq = itertools.count(10000)

PORTEES = {
    "DG": "ENTREPRISE",
    "AD": "ENTREPRISE",
    "DO": "ENTREPRISE",
    "DF": "PROJET",
    "CP": "PROJET",
    "CT": "PROJET",
    "CC": "PROJET",
    "MAG": "PROJET",
    "BAI": "PROJET",
    "VI": "PROJET",
}

NOMS = {
    "DG": "Directeur Général",
    "AD": "Administrateur Délégué",
    "DO": "Directeur des Opérations",
    "DF": "Directeur Financier",
    "CP": "Chef de Projet",
    "CT": "Conducteur de Travaux",
    "CC": "Chef de Chantier",
    "MAG": "Magasinier",
    "BAI": "Bailleur",
    "VI": "Visiteur",
}


def creer_entreprise(*, pays="CI", ville_siege="Abidjan"):
    """Crée ou configure une entreprise (schéma tenant compris) et la retourne."""
    with schema_context(get_public_schema_name()):
        from apps.core.enums import StatutEntreprise
        from apps.tenants.models import Domaine, Entreprise

        e = Entreprise.objects.filter(schema_name="demo").first()
        if not e:
            e = Entreprise(
                schema_name="demo",
                raison_sociale="Entreprise Démo",
                nom_commercial="Démo SARL",
                email_contact="dg@demo.ci",
                statut=StatutEntreprise.ACTIF,
            )
            e.save(verbosity=0)

        e.pays = pays
        e.ville = ville_siege
        e.save(update_fields=["pays", "ville"])

        Domaine.objects.get_or_create(
            domain="demo.localhost",
            defaults={"tenant": e, "is_primary": True},
        )

        try:
            from apps.platform_admin.services.catalogue import propager_roles_systeme
            propager_roles_systeme()
        except Exception:
            pass

        return e


def _obtenir_ou_creer_role(code, portee=None, libelle=None, est_systeme=True):
    from apps.accounts.models import Role

    r = Role.objects.filter(code=code, supprime_le__isnull=True).first()
    if r:
        return r
    return Role.objects.create(
        code=code,
        libelle=libelle or NOMS.get(code, code),
        portee=portee or PORTEES.get(code, "PROJET"),
        est_systeme=est_systeme,
        est_actif=True,
    )


def creer_utilisateur(entreprise, profil):
    """Crée un utilisateur de l'entreprise avec le profil demandé et le retourne."""
    schema = getattr(entreprise, "schema_name", "demo")
    with schema_context(schema):
        from apps.accounts.models import Role, Utilisateur
        from apps.core.enums import StatutUtilisateur

        n = next(_seq)
        email = f"user_l10_{profil.lower()}_{n}@demo.ci"

        if profil in ("DG", "AD", "DF", "CP"):
            role = _obtenir_ou_creer_role(profil, est_systeme=True)
            role_global = profil
        elif profil == "CHANTIER":
            role = _obtenir_ou_creer_role("CT", est_systeme=True)
            role_global = "CT"
        elif profil == "PERSONNALISE":
            role = Role.objects.create(
                code=f"PERSO_{n}",
                libelle=f"Rôle Perso {n}",
                portee="PROJET",
                est_systeme=False,
                est_actif=True,
            )
            role_global = role.code
        elif profil == "AUCUNE_PERMISSION":
            role = Role.objects.create(
                code=f"AUCUNE_PERM_{n}",
                libelle=f"Sans Permissions {n}",
                portee="PROJET",
                est_systeme=False,
                est_actif=True,
            )
            role_global = role.code
        else:
            role = _obtenir_ou_creer_role(profil, est_systeme=True)
            role_global = role.code

        u = Utilisateur(
            email=email,
            nom=f"Nom{n}",
            prenom="Test",
            role=role,
            role_global=role_global,
            statut=StatutUtilisateur.ACTIF,
        )
        u.set_password("MotDePasse!123")
        u.save()
        return u


def client_authentifie(utilisateur):
    """Retourne un client HTTP (APIClient) authentifié par jeton comme `utilisateur`."""
    from rest_framework.test import APIClient

    client = APIClient(headers={"host": "demo.localhost"})
    client.force_authenticate(user=utilisateur)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer test_token_{utilisateur.id}")
    return client


def client_anonyme(entreprise=None):
    """Retourne un client HTTP sans authentification."""
    from rest_framework.test import APIClient

    schema = getattr(entreprise, "schema_name", "demo") if entreprise else "demo"
    return APIClient(headers={"host": f"{schema}.localhost"})


def creer_projet(entreprise, *, ville):
    """Crée un projet situé dans `ville` et le retourne (avec `.id`)."""
    schema = getattr(entreprise, "schema_name", "demo")
    with schema_context(schema):
        from apps.projets.models import Projet

        n = next(_seq)
        return Projet.objects.create(
            nom=f"Projet {ville} {n}",
            reference=f"PRJ-L10-{n:04d}",
            ville=ville,
        )


def affecter(utilisateur, projet, *, debut):
    """Affecte `utilisateur` à `projet` à partir de la date `debut` (datetime.date)."""
    with schema_context("demo"):
        from apps.projets.models import AffectationProjet

        aff, _ = AffectationProjet.objects.update_or_create(
            utilisateur=utilisateur,
            projet=projet,
            defaults={
                "date_debut": debut,
                "est_actif": True,
                "role_projet": "CT",
            },
        )
        return aff


def desactiver_module(entreprise, code):
    """Désactive le module `code` (ex. « projets ») pour l'entreprise."""
    with schema_context(get_public_schema_name()):
        from apps.catalogue.models import EntrepriseModule

        EntrepriseModule.objects.filter(entreprise=entreprise, module__code=code).update(est_actif=False)
    with schema_context(getattr(entreprise, "schema_name", "demo")):
        from apps.accounts.models import Module

        Module.objects.filter(code=code).update(est_actif=False)


@contextmanager
def espion_fournisseur_meteo():
    """Neutralise le fournisseur météo externe et enregistre les villes demandées.

    Doit yield un objet avec un attribut `appels` (liste des villes passées au
    fournisseur, dans l'ordre). Aucun appel réseau réel ne doit partir.
    """
    class Espion:
        def __init__(self):
            self.appels = []

    espion = Espion()

    def mock_obtenir_meteo(ville, pays="CI", portee="CHANTIER"):
        espion.appels.append(ville)
        return {
            "disponible": True,
            "condition": "DEGAGE",
            "temperature": 28,
            "humidite": 65,
            "vent_kmh": 12,
            "alerte": None,
            "raison": None,
            "portee": portee,
            "ville": ville,
            "praticable": True,
        }

    from unittest.mock import patch

    with patch("apps.projets.views.meteo.obtenir_meteo", side_effect=mock_obtenir_meteo), \
         patch("apps.projets.services.meteo.obtenir_meteo", side_effect=mock_obtenir_meteo):
        yield espion
