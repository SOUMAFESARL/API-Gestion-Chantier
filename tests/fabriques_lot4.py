"""
FABRIQUES DU LOT 4. Elles s'appuient sur fabriques_lot3.py, déjà adapté aux noms réels.

SEUL fichier du lot 4 que Gemini peut adapter, et UNIQUEMENT pour un nom réel
(modèle, champ, route, forme d'un corps de requête) : protocole 1.4.
"""
import fabriques_lot3 as _b
from fabriques_lot3 import (  # noqa: F401  (réexportés pour les tests)
    API,
    HOST,
    affecter,
    changer_portee,
    client_pour,
    creer_projet,
    creer_role_personnalise,
    creer_utilisateur,
    definir_permissions,
    ids_de,
    liste_de,
    obtenir_dg,
    role_systeme,
    utilisateur_avec_role,
)

_schema = _b._schema

FAMILLES = ("/roles/", "/parametres/roles/")

# Les six droits d'administration fixes de l'AD (B-04) et les deux réservés au DG.
ADMIN_AD = (
    "administration.collaborateurs_voir",
    "administration.collaborateurs_gerer",
    "administration.roles_gerer",
    "administration.abonnement_voir",
    "administration.factures_voir",
    "administration.onboarding_suivre",
)
ADMIN_DG_SEUL = (
    "administration.entreprise_modifier",
    "administration.abonnement_gerer",
)


# --------------------------------------------------------------------------- routes
def url_liste_roles(famille):
    return f"{API}{famille}"


def url_role(famille, role):
    return f"{API}{famille}{role.pk}/"


def url_supprimer_role(famille, role):
    return f"{API}{famille}{role.pk}/supprimer/"


def url_collaborateur(utilisateur):
    return f"{API}/parametres/collaborateurs/{utilisateur.pk}/"


def url_suspendre(utilisateur):
    return f"{url_collaborateur(utilisateur)}suspendre/"


def url_profil():
    return f"{API}/auth/profil/"


# --------------------------------------------------------------------------- acteurs
def acteur(nom):
    """'DG', un code de rôle système, ou 'perso_entreprise' (rôle personnalisé vide, portée ENTREPRISE)."""
    if nom == "DG":
        return obtenir_dg()
    if nom == "perso_entreprise":
        return creer_utilisateur(creer_role_personnalise(portee="ENTREPRISE"))
    return utilisateur_avec_role(nom)


# --------------------------------------------------------------------------- lecture d'état
def profil(utilisateur):
    r = client_pour(utilisateur).get(url_profil())
    assert r.status_code == 200, r.content
    return r.json()


def permissions_de(utilisateur):
    return set(profil(utilisateur)["permissions"])


def permissions_du_role(code):
    """Permissions effectives d'un rôle système, lues par le profil d'un utilisateur qui le porte."""
    return permissions_de(acteur(code))


def role_code_de(utilisateur):
    from apps.accounts.models import Utilisateur

    with _schema():
        return Utilisateur.objects.filter(pk=utilisateur.pk).values_list("role__code", flat=True).first()


def statut_de(utilisateur):
    from apps.accounts.models import Utilisateur

    with _schema():
        return Utilisateur.objects.filter(pk=utilisateur.pk).values_list("statut", flat=True).first()


def existe_et_non_supprime(utilisateur):
    from apps.accounts.models import Utilisateur

    with _schema():
        ligne = Utilisateur._base_manager.filter(pk=utilisateur.pk).values_list("supprime_le", flat=True).first()
    return ligne is None and Utilisateur._base_manager.filter(pk=utilisateur.pk).exists()


def role_par_nom(nom):
    from apps.accounts.models import Role

    with _schema():
        return (
            Role.objects.filter(code=nom, supprime_le__isnull=True).first()
            or Role.objects.filter(libelle=nom, supprime_le__isnull=True).first()
        )


def nombre_de_roles():
    from apps.accounts.models import Role

    with _schema():
        return Role.objects.count()


def supprimer_role_sans_utilisateur(code):
    """Supprime en base un rôle système qui n'a aucun porteur (pour A-13)."""
    from apps.accounts.models import Role

    with _schema():
        Role.objects.filter(code=code).delete()


def ecritures_sql_pendant(fonction):
    """Exécute fonction() et renvoie les requêtes INSERT / UPDATE / DELETE émises."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        fonction()
    return [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]


# --------------------------------------------------------------------------- corps de requêtes
def corps_inoffensif():
    """Corps de PATCH sans effet de fond : sert aux tests qui ne vérifient que la garde."""
    return {"description": "mise à jour de test", "confirmer": True}


def corps_role(nom, portee="PROJET", codes=()):
    """Corps de création ou de modification d'un rôle cochant exactement ces codes."""
    return {
        "code": (nom or "PERSO")[:50].upper(),
        "libelle": nom,
        "description": "Rôle de test",
        "portee": portee,
        "permissions": list(codes),
        "confirmer": True,
    }


def creer_role_par_api(client, nom, portee="PROJET", codes=(), famille="/parametres/roles/"):
    return client.post(url_liste_roles(famille), corps_role(nom, portee, codes), format="json")


def modifier_role_par_api(client, role, codes, portee=None, famille="/parametres/roles/"):
    corps = {
        "libelle": getattr(role, "libelle", str(role)),
        "portee": portee or getattr(role, "portee", "PROJET"),
        "permissions": list(codes),
        "confirmer": True,
    }
    return client.patch(url_role(famille, role), corps, format="json")


def a_passe_la_garde(reponse):
    """Vrai si la requête n'a été refusée ni par l'authentification, ni par les droits, ni par la route."""
    return reponse.status_code not in (401, 403, 404)
