from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import Entreprise


class EntrepriseSerializer(serializers.ModelSerializer):
    email_contact = serializers.EmailField(max_length=254, validators=[UniqueValidator(queryset=Entreprise.objects.all(), lookup='iexact')])

    class Meta:
        model = Entreprise
        fields = '__all__'
        read_only_fields = ['id', 'date_inscription']

    def validate_email_contact(self, value):
        return value.strip().lower()
