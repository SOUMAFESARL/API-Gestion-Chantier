"""Changement de portée sur une connexion réutilisée, sans serveur PostgreSQL."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from apps.core.contexte import contexte_entreprise, portee_plateforme
from apps.core.rls import appliquer_contexte_rls, diagnostic_isolation


def test_session_plateforme_refermee_et_restauree(settings):
    settings.CCD_PLATEFORME_SANS_ROLE = True
    brut = Mock()
    connexion = SimpleNamespace(etat_rls=None)
    contexte = {"connection": connexion, "cursor": SimpleNamespace(cursor=brut)}
    execute = Mock()

    def requete():
        appliquer_contexte_rls(execute, "SELECT 1", [], False, contexte)
        return brut.execute.call_args.args[1]

    assert requete()[1:] == ["", "none", "ccd.portee_plateforme", "off"]
    with portee_plateforme(motif="test session"):
        assert requete()[1:] == ["", "none", "ccd.portee_plateforme", "on"]
        with contexte_entreprise("00000000-0000-0000-0000-000000000001"):
            valeurs = requete()
            assert valeurs[1] == "00000000-0000-0000-0000-000000000001"
            assert valeurs[-1] == "off"
        assert requete()[-1] == "on"
    assert requete()[-1] == "off"


def test_role_absent_accepte_uniquement_en_mode_session(settings):
    connexion = MagicMock()
    curseur = connexion.cursor.return_value.__enter__.return_value
    curseur.fetchone.side_effect = [("app", False, False), None]
    settings.CCD_PLATEFORME_SANS_ROLE = True
    assert diagnostic_isolation(connexion, tables=False) == []
    curseur.fetchone.side_effect = [("app", False, False), None]
    settings.CCD_PLATEFORME_SANS_ROLE = False
    assert len(diagnostic_isolation(connexion, tables=False)) == 1
