"""
FABRIQUES DU LOT 5. Elles s'appuient sur fabriques_lot4.py, déjà adapté aux règles du projet.
Construit pour supporter la matrice de tests du LOT 5 (E-13, E-06, E-05, E-03, E-04, E-07, C-05).
"""
import fabriques_lot4 as _b
from fabriques_lot4 import (  # noqa: F401  (réexportés pour les tests)
    API,
    HOST,
    acteur,
    changer_portee,
    client_pour,
    corps_role,
    creer_role_par_api,
    creer_role_personnalise,
    creer_utilisateur,
    definir_permissions,
    ids_de,
    liste_de,
    modifier_role_par_api,
    nombre_de_roles,
    obtenir_dg,
    permissions_de,
    permissions_du_role,
    profil,
    role_code_de,
    role_par_nom,
    role_systeme,
    statut_de,
    utilisateur_avec_role,
)

_schema = _b._schema


# --------------------------------------------------------------------------- routes Lot 5
def url_contexte_creation():
    return f"{API}/projets/contexte-creation/"


def url_projets():
    return f"{API}/projets/"


def url_projet_detail(projet):
    return f"{API}/projets/{projet.pk}/"


def url_permissions_roles(projet):
    return f"{API}/projets/{projet.pk}/permissions-roles/"


def url_affectations(projet):
    return f"{API}/projets/{projet.pk}/affectations/"


def url_affectation_detail(projet, aff):
    return f"{API}/projets/{projet.pk}/affectations/{aff.pk}/"


def url_collaborateurs_affectables(projet):
    return f"{API}/projets/{projet.pk}/collaborateurs-affectables/"


def url_equipes(projet):
    return f"{API}/projets/{projet.pk}/equipes/"


def url_equipe_detail(projet, equipe):
    return f"{API}/projets/{projet.pk}/equipes/{equipe.pk}/"


def url_equipe_membres(projet, equipe):
    return f"{API}/projets/{projet.pk}/equipes/{equipe.pk}/membres/"


def url_equipe_affectations(projet):
    return f"{API}/projets/{projet.pk}/equipes/affectations/"


def url_lots(projet):
    return f"{API}/projets/{projet.pk}/lots/"


def url_lots_import(projet):
    return f"{API}/projets/{projet.pk}/lots/import/"


def url_activites(lot):
    return f"{API}/lots/{lot.pk}/activites/"


def url_arrets(projet):
    return f"{API}/projets/{projet.pk}/arrets-chantier/"


def url_arret_detail(arret):
    return f"{API}/arrets-chantier/{arret.pk}/"


# --------------------------------------------------------------------------- corps de requêtes
def corps_projet(nom="Chantier Lot 5", ville="Abidjan", maitre_ouvrage="Client Test", type_projet="BATIMENT_RESIDENTIEL"):
    return {
        "nom": nom,
        "type_projet": type_projet,
        "ville": ville,
        "maitre_ouvrage": maitre_ouvrage,
    }


def corps_equipe(nom="Équipe Maçonnerie", nature="INTERNE", corps_etat="Gros Œuvre", chef=None, membres=None):
    c = {
        "nom": nom,
        "nature": nature,
        "corps_etat": corps_etat,
    }
    if chef:
        c["chef"] = chef
    if membres is not None:
        c["membres"] = membres
    return c


def corps_affectation(utilisateur, role_projet="CT", date_debut=None, date_fin=None):
    payload = {
        "utilisateur_id": str(utilisateur.pk),
        "role_projet": role_projet,
    }
    if date_debut:
        payload["date_debut"] = str(date_debut)
    if date_fin:
        payload["date_fin"] = str(date_fin)
    return payload


def corps_lot(nom="Lot Gros Œuvre", mode_execution="REGIE", type_bordereau="PRIX_UNITAIRE"):
    return {
        "nom": nom,
        "mode_execution": mode_execution,
        "type_bordereau": type_bordereau,
    }


import itertools
_n_projet = itertools.count(200)


def creer_projet(createur=None, nom=None, **kwargs):
    from apps.projets.models import Projet

    n = next(_n_projet)
    nom_final = nom or f"Projet test {n}"
    ref = f"PRJ-{n:04d}"
    with _schema():
        return Projet.objects.create(
            nom=nom_final,
            reference=ref,
            ville="Abidjan",
            cree_par=createur,
            **kwargs,
        )


def affecter(*args, role_projet="CP", **kwargs):
    from apps.projets.models import AffectationProjet, Projet
    from apps.projets.services.affectations import affecter_collaborateur_projet

    if len(args) == 2:
        if isinstance(args[0], Projet):
            projet, utilisateur = args[0], args[1]
        else:
            utilisateur, projet = args[0], args[1]
    else:
        projet = kwargs.pop("projet")
        utilisateur = kwargs.pop("utilisateur")

    with _schema():
        try:
            return affecter_collaborateur_projet(
                projet=projet,
                utilisateur=utilisateur,
                role_projet=role_projet,
                date_debut=kwargs.get("date_debut"),
                date_fin=kwargs.get("date_fin"),
                role_personnalise=kwargs.get("role_personnalise"),
            )
        except Exception:
            aff, _ = AffectationProjet.objects.update_or_create(
                projet=projet,
                utilisateur=utilisateur,
                defaults={
                    "est_actif": kwargs.get("est_actif", True),
                    "role_projet": role_projet,
                },
            )
            return aff


# --------------------------------------------------------------------------- créations de données directes
def creer_lot(projet, code="LOT-01", libelle="Gros Œuvre"):
    from apps.projets.models import Lot

    with _schema():
        return Lot.objects.create(
            projet=projet,
            code=code,
            libelle=libelle,
        )


def creer_activite(lot, libelle="Coulage Béton", quantite=10):
    from apps.projets.models import Activite

    with _schema():
        return Activite.objects.create(
            lot=lot,
            libelle=libelle,
            quantite_prevue=quantite,
        )


def creer_equipe(projet, nom="Équipe Démo"):
    from apps.projets.models import EquipeChantier

    with _schema():
        return EquipeChantier.objects.create(
            projet=projet,
            nom=nom,
            nature="INTERNE",
            corps_etat="Maçonnerie",
        )


def corps_arret(date_debut="2026-10-01", date_fin=None, motif="Intempéries et fortes pluies"):
    c = {
        "date_debut": str(date_debut),
        "motif": motif,
    }
    if date_fin:
        c["date_fin"] = str(date_fin)
    return c


def creer_arret(projet, declare_par=None, motif="Intempéries", date_debut="2026-10-01", date_fin=None):
    from apps.projets.models import ArretChantier

    with _schema():
        if declare_par is None:
            declare_par = projet.cree_par or obtenir_dg()
        return ArretChantier.objects.create(
            projet=projet,
            motif=motif,
            date_debut=date_debut,
            date_fin=date_fin,
            declare_par=declare_par,
        )


def suspendre_utilisateur(utilisateur):
    from apps.core.enums import StatutUtilisateur

    with _schema():
        utilisateur.statut = StatutUtilisateur.DESACTIVE
        utilisateur.save(update_fields=["statut"])
