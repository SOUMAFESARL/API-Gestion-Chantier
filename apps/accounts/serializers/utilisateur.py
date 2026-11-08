from rest_framework import serializers

from apps.accounts.models import Utilisateur


class UtilisateurSerializer(serializers.ModelSerializer):
    nom_complet = serializers.ReadOnlyField()
    est_bloque = serializers.ReadOnlyField()
    tentatives_restantes = serializers.ReadOnlyField()
    is_dg = serializers.ReadOnlyField()
    role_libelle = serializers.CharField(source="get_role_global_display", read_only=True)

    class Meta:
        model = Utilisateur
        fields = [
            "id",
            "email",
            "nom",
            "prenom",
            "nom_complet",
            "telephone",
            "role_global",
            "role_libelle",
            "is_dg",
            "is_owner",
            "statut",
            "tentatives_echouees",
            "bloque_le",
            "double_authentification",
            "langue",
            "is_staff",
            "is_active",
            "est_bloque",
            "tentatives_restantes",
            "cree_le",
            "modifie_le",
        ]

        read_only_fields = [
            "id",
            "nom_complet",
            "role_libelle",
            "is_dg",
            "is_owner",
            "tentatives_echouees",
            "bloque_le",
            "est_bloque",
            "tentatives_restantes",
            "is_staff",
            "is_active",
            "cree_le",
            "modifie_le",
        ]


