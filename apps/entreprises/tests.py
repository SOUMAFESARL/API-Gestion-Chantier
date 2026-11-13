from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .models import TelephoneEntreprise


class TelephoneEntrepriseTests(SimpleTestCase):
    def test_e164_numbers(self):
        field = TelephoneEntreprise._meta.get_field('numero')
        for numero in ['+2250700000000', '+12345678', '+123456789012345']:
            with self.subTest(numero=numero):
                self.assertEqual(field.clean(numero, None), numero)
        for numero in ['0700000000', '+012345678', '+1234567', '+1234567890123456', '+225 0700000000']:
            with self.subTest(numero=numero), self.assertRaises(ValidationError):
                field.clean(numero, None)

    def test_order_must_be_nonnegative_smallint(self):
        field = TelephoneEntreprise._meta.get_field('ordre')
        for ordre in [-1, 32768]:
            with self.subTest(ordre=ordre), self.assertRaises(ValidationError):
                field.clean(ordre, None)
        self.assertEqual(field.clean(0, None), 0)
