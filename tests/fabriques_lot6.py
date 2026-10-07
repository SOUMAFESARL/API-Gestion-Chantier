"""
FABRIQUES DU LOT 6. Elles s'appuient sur fabriques_lot5.py.
Construit pour supporter la matrice de tests du LOT 6 (E-08, E-09, E-10).
"""
from datetime import date, timedelta
from django.utils import timezone

import fabriques_lot5 as _b
from fabriques_lot5 import (  # noqa: F401
    API,
    HOST,
    acteur,
    affecter,
    changer_portee,
    client_pour,
    corps_affectation,
    corps_equipe,
    corps_lot,
    corps_projet,
    corps_role,
    creer_activite,
    creer_lot,
    creer_projet,
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
    url_activites,
    url_affectation_detail,
    url_affectations,
    url_arret_detail,
    url_arrets,
    url_collaborateurs_affectables,
    url_equipe_affectations,
    url_equipe_detail,
    url_equipe_membres,
    url_equipes,
    url_lots,
    url_lots_import,
    url_projet_detail,
    url_projets,
    utilisateur_avec_role,
)

_schema = _b._schema


# --------------------------------------------------------------------------- Routes Lot 6
def url_reprogrammer_projet(projet):
    return f"{API}/projets/{projet.pk}/reprogrammer/"


def url_rapports():
    return f"{API}/rapports/"


def url_rapport_detail(rapport):
    return f"{API}/rapports/{rapport.pk}/"


# --------------------------------------------------------------------------- Corps de requêtes
def corps_statut(statut: str):
    return {"statut": statut}


def corps_reprogrammation(
    date_fin=None,
    motif_id=None,
    commentaire="Report calendrier suite intempéries",
):
    if not date_fin:
        date_fin = (timezone.localdate() + timedelta(days=60)).isoformat()
    c = {
        "nouvelle_date_fin": str(date_fin),
        "commentaire": commentaire,
    }
    if motif_id:
        c["motif_id"] = str(motif_id)
    return c


def corps_rapport(
    projet,
    lot=None,
    date_rapport=None,
    meteo="ENSOLEILLE",
    observations="Rapport normal",
):
    if not date_rapport:
        date_rapport = timezone.localdate().isoformat()
    c = {
        "projet_id": str(projet.pk),
        "date_rapport": str(date_rapport),
        "meteo": meteo,
        "observations": observations,
        "effectif_regie": 5,
        "effectif_tacherons": 2,
    }
    if lot:
        c["lot_id"] = str(lot.pk)
    return c


# --------------------------------------------------------------------------- Helpers de données
def definir_statut_projet_base(projet, statut: str):
    """Positionne directement le statut du projet en base pour préparer un test."""
    from apps.projets.models import Projet

    with _schema():
        Projet.objects.filter(pk=projet.pk).update(statut=statut)
        projet.refresh_from_db()
        return projet
