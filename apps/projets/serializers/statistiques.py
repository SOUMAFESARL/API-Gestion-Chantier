from rest_framework import serializers


class StatistiquesProjetSerializer(serializers.Serializer):
    cases_count = serializers.IntegerField(help_text="Cases actives de l'arbre.")
    feuilles_count = serializers.IntegerField(help_text="Tâches du bas (feuilles) actives.")
    avancement_pondere = serializers.FloatField(
        allow_null=True,
        help_text="Physique du projet, pondéré par les montants ; nul quand il est indisponible.",
    )
    avancement_partiel = serializers.BooleanField(
        help_text="Vrai quand une partie des montants manque (calcul sur les cases chiffrées)."
    )
    ponderation = serializers.ChoiceField(choices=["MONTANT"])
    feuilles_en_retard = serializers.IntegerField()
