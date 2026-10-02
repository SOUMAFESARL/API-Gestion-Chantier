"""Tests de la commande de management provisionner_inscriptions."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.tenants.models import DemandeInscription


@pytest.mark.django_db
def test_commande_sans_demande_en_attente():
    """Vérifie le message quand aucune inscription n'est en statut PROVISIONNEMENT."""
    out = StringIO()
    call_command("provisionner_inscriptions", stdout=out)
    assert "Aucune demande d'inscription en attente de provisionnement." in out.getvalue()


@pytest.mark.django_db
def test_commande_avec_demande_id_inconnu():
    """Vérifie le message quand l'UUID fourni n'existe pas en statut PROVISIONNEMENT."""
    out = StringIO()
    call_command("provisionner_inscriptions", demande_id="00000000-0000-0000-0000-000000000000", stdout=out)
    assert "Aucune demande en statut PROVISIONNEMENT trouvée" in out.getvalue()


@pytest.mark.django_db
def test_commande_execute_provisionnement_pour_demande_en_attente():
    """Vérifie que la commande appelle le service provisionner pour les demandes éligibles."""
    from apps.tenants.services.inscription import deposer

    demande = deposer(
        identifiant=None,
        raison_sociale="Entreprise Test CLI",
        pays="CI",
        email="test-cli@entreprise.ci",
    )
    demande.statut = DemandeInscription.Statut.PROVISIONNEMENT
    demande.save(update_fields=["statut"])

    out = StringIO()
    with patch("apps.tenants.management.commands.provisionner_inscriptions.provisionner") as mock_prov:
        def fake_provisionner(pk):
            DemandeInscription.objects.filter(pk=pk).update(statut=DemandeInscription.Statut.ACTIVEE)

        mock_prov.side_effect = fake_provisionner

        call_command("provisionner_inscriptions", demande_id=str(demande.pk), stdout=out)

        mock_prov.assert_called_once_with(demande.pk)
        demande.refresh_from_db()
        assert demande.statut == DemandeInscription.Statut.ACTIVEE
        assert "Succès" in out.getvalue()
