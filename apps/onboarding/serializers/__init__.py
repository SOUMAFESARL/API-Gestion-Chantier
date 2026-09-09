"""Forme de la progression de configuration — contrat T-024 §5.1.

**Tout est en lecture seule.** `pourcentage` est calculé (R-90), et les quatre
autres champs ne se modifient que par les endpoints d'action du §5.2 à §5.4 :
la ressource n'accepte ni `PUT` ni `PATCH`. Un champ calculé accepté en
écriture finit par diverger de ce qu'il compte.
"""

from rest_framework import serializers

from apps.onboarding.models import ETAPES, ProgressionConfiguration

__all__ = ["EtapeSerializer", "ProgressionSerializer"]


class EtapeSerializer(serializers.Serializer):
    """Une étape du catalogue — franchie ou non.

    `mode` et `franchie_le` sont nuls tant qu'elle ne l'est pas : c'est la
    forme qui distingue « pas encore » de « passée ».
    """

    code = serializers.CharField()
    mode = serializers.CharField(allow_null=True)
    franchie_le = serializers.DateTimeField(allow_null=True)


class ProgressionSerializer(serializers.ModelSerializer):
    """La progression complète, telle que la lit le wizard et le tableau de bord."""

    pourcentage = serializers.IntegerField(read_only=True)
    etapes = serializers.SerializerMethodField()

    class Meta:
        model = ProgressionConfiguration
        fields = ["statut", "etape_courante", "pourcentage", "demarre_le", "terminee_le", "etapes"]
        read_only_fields = fields

    def get_etapes(self, progression) -> list[dict]:
        """**Les trois étapes, toujours, dans l'ordre, même non franchies.**

        Conventions §4.2 pose que `resultats` est toujours un tableau, jamais
        `null` ; le même principe s'applique ici. Un client qui doit deviner
        les étapes manquantes finit par les écrire en dur — et l'on retrouve
        le catalogue dupliqué que le contrat §2.2 cherche à éviter.
        """
        franchies = {etape.code: etape for etape in progression.etapes.all()}
        return [
            EtapeSerializer(
                {
                    "code": code,
                    "mode": getattr(franchies.get(code), "mode", None),
                    "franchie_le": getattr(franchies.get(code), "franchie_le", None),
                }
            ).data
            for code in ETAPES
        ]
