"""[G-02] Contrat de GET /api/v1/auth/profil/ attendu par le frontend, pour les profils types.

Tests de caractérisation (lot 9 clos) : le contrat figé au lot 2 ne doit pas avoir bougé.
"""
import pytest

URL_PROFIL = "/api/v1/auth/profil/"
CHAMPS = {"role_global", "role_libelle", "role_personnalise", "habilitations", "permissions"}
PERMISSIONS_ADMINISTRATION = (
    "administration.roles_gerer",
    "administration.collaborateurs_gerer",
    "administration.factures_voir",
)
PROFILS = ["DG", "AD", "DF", "CP", "PERSONNALISE"]

pytestmark = [pytest.mark.carac, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def entreprise(fabriques):
    return fabriques.creer_entreprise()


def _profil(fabriques, entreprise, profil):
    client = fabriques.client_authentifie(fabriques.creer_utilisateur(entreprise, profil))
    reponse = client.get(URL_PROFIL)
    assert reponse.status_code == 200, reponse.content
    return reponse.json()


@pytest.mark.parametrize("profil", PROFILS)
def test_g02_champs_et_types_du_contrat(profil, fabriques, entreprise):
    """[G-02] Les cinq champs du contrat sont présents avec les bons types."""
    corps = _profil(fabriques, entreprise, profil)
    assert CHAMPS <= set(corps), f"Champs manquants : {CHAMPS - set(corps)}"
    assert isinstance(corps["role_global"], str) and corps["role_global"]
    assert isinstance(corps["role_libelle"], str) and corps["role_libelle"]
    assert corps["role_personnalise"] is None or isinstance(corps["role_personnalise"], dict)
    assert isinstance(corps["habilitations"], dict)
    assert isinstance(corps["permissions"], list)


@pytest.mark.parametrize("profil", PROFILS)
def test_g02_habilitations_entre_0_et_3(profil, fabriques, entreprise):
    """[G-02] Chaque habilitation est un entier de 0 à 3 (jamais un booléen)."""
    habilitations = _profil(fabriques, entreprise, profil)["habilitations"]
    for module, info in habilitations.items():
        niveau = info.get("niveau") if isinstance(info, dict) else info
        assert isinstance(niveau, int) and not isinstance(niveau, bool), (module, niveau)
        assert 0 <= niveau <= 3, (module, niveau)


@pytest.mark.parametrize("profil", PROFILS)
def test_g02_permissions_sont_des_codes_texte_sans_doublon(profil, fabriques, entreprise):
    """[G-02] `permissions` est une liste de codes texte « module.action », sans doublon."""
    permissions = _profil(fabriques, entreprise, profil)["permissions"]
    assert all(isinstance(p, str) and "." in p for p in permissions)
    assert len(permissions) == len(set(permissions))


@pytest.mark.parametrize("profil", ["DG", "AD"])
def test_g02_dg_et_ad_ont_les_permissions_d_administration(profil, fabriques, entreprise):
    """[G-02] DG et AD exposent les trois permissions d'administration."""
    permissions = _profil(fabriques, entreprise, profil)["permissions"]
    for code in PERMISSIONS_ADMINISTRATION:
        assert code in permissions, f"{code} absent pour {profil}"


@pytest.mark.parametrize("profil", ["DF", "CP", "PERSONNALISE"])
def test_g02_autres_profils_n_ont_aucune_permission_d_administration(profil, fabriques, entreprise):
    """[G-02] DF, CP et un rôle personnalisé n'exposent aucune des trois permissions d'administration."""
    permissions = _profil(fabriques, entreprise, profil)["permissions"]
    for code in PERMISSIONS_ADMINISTRATION:
        assert code not in permissions, f"{code} ne doit pas être exposé pour {profil}"


def test_g02_role_personnalise_est_signale(fabriques, entreprise):
    """[G-02] Un rôle personnalisé a role_personnalise renseigné ; un rôle système à None."""
    assert _profil(fabriques, entreprise, "PERSONNALISE")["role_personnalise"] is not None
    for profil in ("DG", "AD", "DF", "CP"):
        assert _profil(fabriques, entreprise, profil)["role_personnalise"] is None, profil


def test_g02_profil_non_authentifie_est_refuse(fabriques, entreprise):
    """[G-02] Sans jeton, le profil répond 401."""
    assert fabriques.client_anonyme(entreprise).get(URL_PROFIL).status_code == 401
