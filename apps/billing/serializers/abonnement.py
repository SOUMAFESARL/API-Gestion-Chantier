"""Sérialiseurs pour l'abonnement et le plan — MLD §4.3 et §4.4."""

from rest_framework import serializers

from apps.billing.models import Abonnement, Plan

__all__ = ["AbonnementSerializer", "PlanResumeSerializer"]


class PlanResumeSerializer(serializers.ModelSerializer):
    """Résumé du plan souscrit."""

    class Meta:
        model = Plan
        fields = [
            "code",
            "libelle",
            "limite_projets",
            "limite_utilisateurs",
            "limite_stockage_mo",
            "acces_ia",
        ]


class AbonnementSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la lecture de l'abonnement du tenant — T-025 §8."""

    plan = PlanResumeSerializer(read_only=True)
    jours_essai_restants = serializers.IntegerField(read_only=True)
    est_expire = serializers.SerializerMethodField()
    lecture_seule = serializers.SerializerMethodField()

    class Meta:
        model = Abonnement
        fields = [
            "id",
            "statut",
            "plan",
            "date_debut",
            "date_fin",
            "fin_essai",
            "jours_essai_restants",
            "est_expire",
            "lecture_seule",
            "renouvellement_auto",
        ]

    def get_est_expire(self, obj: Abonnement) -> bool:
        """Indique si la période d'essai est échue."""
        if obj.statut == Abonnement.Statut.ESSAI:
            restants = obj.jours_essai_restants
            return restants is not None and restants <= 0
        return False

    def get_lecture_seule(self, obj: Abonnement) -> bool:
        """Indique si l'espace est restreint en lecture seule."""
        return obj.lecture_seule_depuis is not None or self.get_est_expire(obj)
