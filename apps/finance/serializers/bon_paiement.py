"""Serializers pour la gestion des bons de paiement et signatures."""

from rest_framework import serializers

from apps.finance.models import BonPaiement, SignatureBon


class SignatureBonSerializer(serializers.ModelSerializer):
    """Détail d'une signature apposée sur un bon de paiement."""

    signataire_nom = serializers.SerializerMethodField()

    class Meta:
        model = SignatureBon
        fields = [
            "id",
            "signataire",
            "signataire_nom",
            "niveau_requis",
            "signe_le",
            "commentaire",
        ]

    def get_signataire_nom(self, obj: SignatureBon) -> str:
        if obj.signataire:
            return f"{obj.signataire.prenom} {obj.signataire.nom}".strip() or obj.signataire.email
        return ""


class BonPaiementSerializer(serializers.ModelSerializer):
    """Lecture détaillée d'un bon de paiement."""

    projet_nom = serializers.CharField(source="projet.nom", read_only=True)
    lot_libelle = serializers.CharField(source="lot.libelle", read_only=True, default=None)
    beneficiaire_nom = serializers.CharField(source="beneficiaire.raison_sociale", read_only=True)
    statut_libelle = serializers.CharField(source="get_statut_display", read_only=True)
    mode_paiement_libelle = serializers.CharField(
        source="get_mode_paiement_display", read_only=True
    )
    signatures = SignatureBonSerializer(many=True, read_only=True)

    montant_brut_fcfa = serializers.SerializerMethodField()
    montant_net_fcfa = serializers.SerializerMethodField()

    class Meta:
        model = BonPaiement
        fields = [
            "id",
            "numero",
            "projet",
            "projet_nom",
            "lot",
            "lot_libelle",
            "beneficiaire",
            "beneficiaire_nom",
            "corps_etat",
            "periode_debut",
            "periode_fin",
            "montant_brut",
            "montant_brut_fcfa",
            "deduction_avance",
            "deduction_penalite",
            "montant_net",
            "montant_net_fcfa",
            "statut",
            "statut_libelle",
            "mode_paiement",
            "mode_paiement_libelle",
            "reference_paiement",
            "paye_le",
            "signatures",
            "cree_le",
            "modifie_le",
        ]

    def get_montant_brut_fcfa(self, obj: BonPaiement) -> int:
        return int(obj.montant_brut // 100) if obj.montant_brut else 0

    def get_montant_net_fcfa(self, obj: BonPaiement) -> int:
        return int(obj.montant_net // 100) if obj.montant_net else 0


class BonPaiementCreationSerializer(serializers.ModelSerializer):
    """Création ou modification d'un bon de paiement."""

    class Meta:
        model = BonPaiement
        fields = [
            "numero",
            "projet",
            "lot",
            "beneficiaire",
            "corps_etat",
            "periode_debut",
            "periode_fin",
            "montant_brut",
            "deduction_avance",
            "deduction_penalite",
            "mode_paiement",
            "reference_paiement",
        ]


class SignerBonPaiementRequestSerializer(serializers.Serializer):
    """Paramètres pour signer et valider un bon de paiement."""

    commentaire = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Commentaire ou mention facultative apposée lors de la signature.",
    )


class SignerBonPaiementResponseSerializer(serializers.Serializer):
    """Réponse confirmant la signature et le changement de statut du bon."""

    succes = serializers.BooleanField(
        help_text="Indique si la signature a été apposée avec succès."
    )
    message = serializers.CharField(help_text="Message informatif.")
    id = serializers.UUIDField(help_text="Identifiant unique du bon de paiement.")
    numero = serializers.CharField(help_text="Numéro / référence du bon de paiement.")
    statut = serializers.CharField(help_text="Nouveau statut du bon (ex: SIGNE).")
    signe_le = serializers.DateTimeField(help_text="Horodatage UTC de la signature.")
