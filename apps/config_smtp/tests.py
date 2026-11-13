from unittest.mock import patch

from django.test import TestCase

from .models import ConfigSMTP
from .services import send_mail


class SMTPServiceTests(TestCase):
    def setUp(self):
        self.config = ConfigSMTP.objects.create(
            nom='Test', hote='smtp.example.com', port=587,
            utilisateur='smtp-user', mot_de_passe='test-only',
            email_expediteur='sender@example.com', nom_expediteur='API Chantier',
            est_active=True,
        )

    @patch('apps.config_smtp.services.EmailBackend')
    def test_database_configuration_used(self, backend):
        backend.return_value.send_messages.return_value = 1
        self.assertEqual(send_mail('Subject', 'Body', 'ignored@example.com', ['recipient@example.com'], html_message='<p>Body</p>'), 1)
        options = backend.call_args.kwargs
        self.assertEqual(options['host'], self.config.hote)
        self.assertEqual(options['username'], self.config.utilisateur)
        self.assertEqual(options['password'], self.config.mot_de_passe)
        self.assertTrue(options['use_tls'])
        message = backend.return_value.send_messages.call_args.args[0][0]
        self.assertEqual(message.from_email, 'API Chantier <sender@example.com>')
        self.assertEqual(message.to, ['recipient@example.com'])
        self.assertEqual(message.alternatives[0].content, '<p>Body</p>')

    @patch('apps.config_smtp.services.EmailBackend')
    def test_smtp_failure_is_propagated(self, backend):
        backend.return_value.send_messages.side_effect = RuntimeError('SMTP unavailable')
        with self.assertRaises(RuntimeError):
            send_mail('Subject', 'Body', None, ['recipient@example.com'])

    @patch('apps.config_smtp.services.django_send_mail', return_value=1)
    def test_inactive_or_deleted_configuration_uses_fallback(self, fallback):
        self.config.est_active = False
        self.config.save()
        self.assertEqual(send_mail('Subject', 'Body', None, ['recipient@example.com']), 1)
        fallback.assert_called_once()
