"""
[C-05 puces 2 et 3] Protection des données personnelles des collaborateurs affectés et route de la liste réduite.
Règles :
- GET /affectations/ :
  * Si l'acteur a projets.affecter_membres, projets.gerer_equipes ou est DG/AD : email et téléphone présents.
  * Si l'acteur n'a ni l'un ni l'autre (ex: VI, CC, DO) : email et téléphone strictement absents (pas de clé 'email'/'telephone'/'phone').
  * Si l'acteur n'est pas affecté et pas DG/AD : 403.
- GET /collaborateurs-affectables/ :
  * Exige projets.affecter_membres plus (ENTREPRISE ou affecté).
  * 200 pour CP affecté ou DG ; 403 pour CT affecté, VI affecté, DO.
  * Clés strictement limitées aux métadonnées publiques (id, nom, role) ; sans email ni téléphone.
  * Ne contient ni DG/AD/DO (rôles ENTREPRISE), ni utilisateurs suspendus.
"""
import pytest

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau


def _trouver_cles_interdites(data, interdits=("mail", "phone", "telephone")):
    """Inspecte récursivement data et renvoie toute clé contenant un terme interdit."""
    cles_trouvees = []
    if isinstance(data, dict):
        for k, v in data.items():
            k_lower = k.lower()
            if any(terme in k_lower for terme in interdits):
                cles_trouvees.append(k)
            cles_trouvees.extend(_trouver_cles_interdites(v, interdits))
    elif isinstance(data, list):
        for item in data:
            cles_trouvees.extend(_trouver_cles_interdites(item, interdits))
    return cles_trouvees


@NOUVEAU
def test_c05_affectations_vi_pii_masquees(fab):
    """[C-05] GET /affectations/ par un VI affecté : nom et rôle présents, zéro clé email/phone/telephone."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    # Membre dont les coordonnées doivent être masquées pour le VI
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")

    client_vi = fab.client_pour(vi)
    r = client_vi.get(fab.url_affectations(projet))
    assert r.status_code == 200, f"VI affecté doit pouvoir lire les affectations, reçu {r.status_code}"

    items = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
    assert len(items) >= 2, "Au moins 2 affectations doivent être listées"

    # Vérification stricte : aucune clé email ou téléphone
    interdits = _trouver_cles_interdites(items)
    assert not interdits, f"Des clés personnelles ont fuité pour le VI : {interdits}"


@NOUVEAU
def test_c05_affectations_acteurs_autorises_voient_pii(fab):
    """[C-05] GET /affectations/ par CP, CT, DG, AD : email et téléphone présents."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    cible = fab.acteur("CC")
    fab.affecter(projet, cible, role_projet="CC")

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    ct = fab.acteur("CT")
    fab.affecter(projet, ct, role_projet="CT")

    # 1. CP affecté (a projets.affecter_membres)
    client_cp = fab.client_pour(cp)
    r_cp = client_cp.get(fab.url_affectations(projet))
    assert r_cp.status_code == 200
    cles_cp = _trouver_cles_interdites(r_cp.data)
    assert len(cles_cp) > 0, "Le CP doit voir les informations de contact (email / téléphone)"

    # 2. CT affecté (a projets.gerer_equipes)
    client_ct = fab.client_pour(ct)
    r_ct = client_ct.get(fab.url_affectations(projet))
    assert r_ct.status_code == 200
    cles_ct = _trouver_cles_interdites(r_ct.data)
    assert len(cles_ct) > 0, "Le CT doit voir les informations de contact pour animer les équipes"

    # 3. DG non affecté
    client_dg = fab.client_pour(dg)
    r_dg = client_dg.get(fab.url_affectations(projet))
    assert r_dg.status_code == 200
    cles_dg = _trouver_cles_interdites(r_dg.data)
    assert len(cles_dg) > 0, "Le DG doit voir les informations de contact"


@NOUVEAU
def test_c05_affectations_do_ne_voit_pas_pii(fab):
    """[C-05 / L5-6] Le DO n'a ni affecter_membres ni gerer_equipes : email et téléphone sont absents."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    do = fab.acteur("DO")
    client_do = fab.client_pour(do)
    r = client_do.get(fab.url_affectations(projet))
    assert r.status_code == 200, f"DO doit pouvoir lire les affectations du projet, reçu {r.status_code}"

    cles_do = _trouver_cles_interdites(r.data)
    assert not cles_do, f"Le DO ne doit pas voir les données de contact, trouvé: {cles_do}"


@CARAC
def test_c05_affectations_non_affecte_refuse(fab):
    """[C-05] GET /affectations/ par un utilisateur non affecté (ex: VI non affecté) renvoie 403."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    vi = fab.acteur("VI")  # non affecté

    client = fab.client_pour(vi)
    r = client.get(fab.url_affectations(projet))
    assert r.status_code == 403


@NOUVEAU
def test_c05_route_collaborateurs_affectables_acces_et_champs(fab):
    """[C-05 / L5-1] GET /collaborateurs-affectables/ par CP affecté : 200, clés limitées à id, nom, role."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    # Création d'un candidat CC actif
    cc = fab.acteur("CC")

    client_cp = fab.client_pour(cp)
    r = client_cp.get(fab.url_collaborateurs_affectables(projet))
    assert r.status_code == 200, f"CP affecté doit pouvoir consulter les collaborateurs affectables, reçu {r.status_code}"

    items = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
    assert len(items) > 0, "La liste ne doit pas être vide"

    # Vérification des clés autorisées et absence totale de coordonnées
    assert not _trouver_cles_interdites(items), "Aucune donnée de contact (email/téléphone) dans la liste réduite"
    premier = items[0]
    assert "id" in premier
    assert "nom" in premier or "nom_complet" in premier
    assert "role" in premier or "role_nom" in premier or "role_code" in premier


@NOUVEAU
def test_c05_collaborateurs_affectables_filtrage_candidats(fab):
    """[C-05 / L5-1] La liste réduite ne contient ni porteurs de rôles ENTREPRISE (DG, AD, DO), ni suspendus."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    # Candidats non affectables
    do = fab.acteur("DO")
    ad = fab.acteur("AD")
    suspendu = fab.acteur("VI")
    fab.suspendre_utilisateur(suspendu)

    # Candidat affectable
    cc = fab.acteur("CC")

    client_cp = fab.client_pour(cp)
    r = client_cp.get(fab.url_collaborateurs_affectables(projet))
    assert r.status_code == 200
    items = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
    ids = [str(item["id"]) for item in items]

    assert str(cc.pk) in ids, "Le CC actif doit être dans la liste"
    assert str(do.pk) not in ids, "Le DO (portée ENTREPRISE) ne doit pas être dans la liste"
    assert str(ad.pk) not in ids, "L'AD (portée ENTREPRISE) ne doit pas être dans la liste"
    assert str(dg.pk) not in ids, "Le DG (portée ENTREPRISE) ne doit pas être dans la liste"
    assert str(suspendu.pk) not in ids, "L'utilisateur inactif ne doit pas être dans la liste"


@NOUVEAU
def test_c05_collaborateurs_affectables_refus_pour_non_habilites(fab):
    """[C-05 / L5-1] GET /collaborateurs-affectables/ renvoie 403 pour CT affecté, VI affecté et DO."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)

    ct = fab.acteur("CT")
    fab.affecter(projet, ct, role_projet="CT")

    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")

    do = fab.acteur("DO")

    assert fab.client_pour(ct).get(fab.url_collaborateurs_affectables(projet)).status_code == 403
    assert fab.client_pour(vi).get(fab.url_collaborateurs_affectables(projet)).status_code == 403
    assert fab.client_pour(do).get(fab.url_collaborateurs_affectables(projet)).status_code == 403
