from unittest.mock import patch

from django.contrib.auth.hashers import check_password
from django.db import models
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import DemandeInscription
from .serializers import DemandeInscriptionSerializer


class DemandeInscriptionTests(SimpleTestCase):
    def test_password_is_hashed_and_never_returned(self):
        serializer = DemandeInscriptionSerializer()
        encoded = serializer.validate_password('Un secret de test')
        self.assertTrue(check_password('Un secret de test', encoded))
        demande = DemandeInscription(password=encoded)
        self.assertNotIn('password', DemandeInscriptionSerializer(demande).data)
        self.assertEqual(serializer.validate_password(''), '')

    def test_save_normalises_and_refreshes_audit_timestamp(self):
        demande = DemandeInscription(raison_sociale='  BTP   Exemple  ', email=' CONTACT@EXAMPLE.COM ')
        previous = demande.modifie_le
        with patch.object(models.Model, 'save') as save:
            demande.save(update_fields=['raison_sociale', 'email'])
        self.assertEqual(demande.raison_sociale, 'BTP Exemple')
        self.assertEqual(demande.email, 'contact@example.com')
        self.assertGreaterEqual(demande.modifie_le, previous)
        self.assertIn('modifie_le', save.call_args.kwargs['update_fields'])

    def test_routes(self):
        self.assertEqual(reverse('depot-demande-inscription'), '/api/v1/inscription/')


class DepotDemandeInscriptionTests(APITestCase):
    def setUp(self):
        self.url = reverse('depot-demande-inscription')
        self.payload = {'raison_sociale': ' BTP   Exemple ', 'pays': 'ci', 'email': 'CONTACT@EXAMPLE.COM'}

    def start(self):
        from django.core import mail
        from urllib.parse import urlparse, parse_qs
        response = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        url = next(line for line in mail.outbox[-1].body.splitlines() if line.startswith('http'))
        self.assertIn('CCD Digital', mail.outbox[-1].body)
        self.assertIn('48 heures', mail.outbox[-1].body)
        self.assertEqual(mail.outbox[-1].alternatives[0].mimetype, 'text/html')
        self.assertIn('Activer mon espace', mail.outbox[-1].alternatives[0].content)
        return parse_qs(urlparse(url).query)['token'][0]

    def test_full_flow_and_single_use(self):
        import hashlib
        token = self.start()
        demande = DemandeInscription.objects.get()
        self.assertEqual(demande.empreinte, hashlib.sha256(token.encode()).hexdigest())
        self.assertIsNone(demande.cgu_acceptees_le)
        self.assertEqual(demande.password, '')
        url = reverse('configurer-inscription')
        self.assertEqual(self.client.get(url, {'token': token}).status_code, 200)
        data = {'token': token, 'nom': 'Kone', 'prenom': 'Awa', 'password': 'Chantier!9Secret246', 'cgu_version': '1.0', 'cgu_acceptees': True}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        demande.refresh_from_db()
        self.assertEqual(demande.statut, 'ACTIVEE')
        self.assertIsNotNone(demande.entreprise_id)
        self.assertEqual(demande.entreprise.email_contact, demande.email)
        self.assertEqual(demande.entreprise.statut, 'ESSAI')
        self.assertEqual(response.data['entreprise'], demande.entreprise_id)
        self.assertTrue(check_password(data['password'], demande.password))
        self.assertIsNotNone(demande.cgu_acceptees_le)
        self.assertIsNotNone(demande.utilise_le)
        self.assertNotIn('password', response.data)
        self.assertNotIn('empreinte', response.data)
        self.assertEqual(self.client.post(url, data, format='json').status_code, 400)

    def test_invalid_expired_and_incomplete_requests(self):
        from django.utils import timezone
        from datetime import timedelta
        token = self.start()
        url = reverse('configurer-inscription')
        self.assertEqual(self.client.get(url, {'token': 'invalid'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'token': token}, format='json').status_code, 400)
        DemandeInscription.objects.update(expire_le=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(url, {'token': token}).status_code, 400)

    def test_duplicates_and_mail_failure(self):
        self.start()
        self.assertEqual(self.client.post(self.url, self.payload, format='json').status_code, 400)
        with patch('apps.demandes_inscription.views.send_mail', side_effect=RuntimeError('SMTP unavailable')):
            response = self.client.post(self.url, {**self.payload, 'email': 'other@example.com'}, format='json')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(DemandeInscription.objects.count(), 1)

    def test_completion_requires_consent_and_strong_password(self):
        token = self.start()
        data = {'token': token, 'nom': 'Kone', 'prenom': 'Awa', 'password': 'Chantier!9Secret246', 'cgu_version': '1.0', 'cgu_acceptees': True}
        for changes in [{'password': '123'}, {'cgu_acceptees': False}]:
            response = self.client.post(reverse('configurer-inscription'), {**data, **changes}, format='json')
            self.assertEqual(response.status_code, 400)
        demande = DemandeInscription.objects.get()
        self.assertIsNone(demande.utilise_le)
        self.assertEqual(demande.statut, 'EN_ATTENTE')
