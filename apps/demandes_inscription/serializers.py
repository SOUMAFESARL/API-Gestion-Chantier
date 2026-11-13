import secrets
from types import SimpleNamespace

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import DemandeInscription, STATUTS_RESERVES


class DemandeInscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DemandeInscription
        fields = '__all__'
        read_only_fields = ['id', 'cree_le', 'modifie_le', 'cree_par', 'modifie_par', 'supprime_par']
        extra_kwargs = {'password': {'write_only': True, 'trim_whitespace': False}}
        # Conditional uniqueness must also be checked when only the status changes.
        validators = []

    def validate_email(self, value):
        return value.strip().lower()

    def validate_password(self, value):
        return make_password(value) if value else ''

    def validate(self, attrs):
        instance = self.instance
        statut = attrs.get('statut', instance.statut if instance else 'EN_ATTENTE')
        if statut in STATUTS_RESERVES:
            demandes = DemandeInscription.objects.filter(statut__in=STATUTS_RESERVES)
            if instance:
                demandes = demandes.exclude(pk=instance.pk)
            errors = {}
            for field, lookup in [('slug_reserve', 'slug_reserve'), ('email', 'email__iexact')]:
                value = attrs.get(field, getattr(instance, field, None))
                if value is not None and demandes.filter(**{lookup: value}).exists():
                    errors[field] = 'Cette valeur est déjà réservée par une demande en cours.'
            if errors:
                raise serializers.ValidationError(errors)
        return attrs


class DepotDemandeInscriptionSerializer(DemandeInscriptionSerializer):
    class Meta:
        model = DemandeInscription
        fields = ['id', 'raison_sociale', 'pays', 'email', 'statut', 'cree_le', 'expire_le', 'entreprise']
        read_only_fields = ['id', 'statut', 'cree_le', 'expire_le', 'entreprise']
        validators = []

    def validate_pays(self, value):
        if len(value) != 2 or not value.isascii() or not value.isalpha():
            raise serializers.ValidationError('Utilisez un code pays de deux lettres.')
        return value.upper()

    def validate(self, attrs):
        from django.utils.text import slugify
        from apps.entreprises.models import Entreprise

        attrs = super().validate(attrs)
        if Entreprise.objects.filter(email_contact__iexact=attrs['email']).exists():
            raise serializers.ValidationError({'email': 'Cette adresse est déjà utilisée.'})
        base = slugify(attrs['raison_sociale'])[:27] or 'entreprise'
        attrs['slug_reserve'] = f'{base}-{secrets.token_hex(6)}'
        return attrs


class CompleterInscriptionSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, max_length=128)
    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    cgu_version = serializers.CharField(max_length=20)
    cgu_acceptees = serializers.BooleanField()

    def validate_cgu_acceptees(self, value):
        if not value:
            raise serializers.ValidationError('Vous devez accepter les CGU.')
        return value

    def validate(self, attrs):
        demande = self.context['demande']
        validate_password(attrs['password'], user=SimpleNamespace(
            username=demande.email, email=demande.email,
            first_name=attrs['prenom'], last_name=attrs['nom'],
        ))
        attrs['password'] = make_password(attrs['password'])
        return attrs
