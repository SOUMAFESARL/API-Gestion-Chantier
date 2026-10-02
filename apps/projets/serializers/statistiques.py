from rest_framework import serializers


class StatistiquesProjetSerializer(serializers.Serializer):
    lots_count = serializers.IntegerField()
    activites_count = serializers.IntegerField()
    avancement_pondere = serializers.FloatField(help_text="Pourcentage réalisé, de 0 à 100.")
    ponderation = serializers.ChoiceField(choices=["BUDGET", "UNIFORME"])
    activites_en_retard = serializers.IntegerField()
    budget_activites_montant = serializers.IntegerField(help_text="Centimes FCFA.")
