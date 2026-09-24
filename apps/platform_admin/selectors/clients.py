"""Sélecteurs pour la liste des entreprises clientes et leurs métriques."""

import logging
import uuid
from datetime import timedelta

from django.db.models import Q
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.exceptions import NotFound

from apps.accounts.models import Utilisateur
from apps.billing.models import Abonnement, PaiementAbonnement, Plan
from apps.core.enums import StatutEntreprise, StatutUtilisateur
from apps.projets.models import Projet
from apps.tenants.models import DemandeInscription, Entreprise

logger = logging.getLogger(__name__)

MAP_PLAN_BACKEND_VERS_FRONTEND = {
    "BATISSEUR": "DECOUVERTE",
    "STARTER": "DECOUVERTE",
    "MAITRE_OEUVRE": "PRO",
    "PRO": "PRO",
    "PROMOTEUR": "ENTREPRISE",
    "ENTERPRISE": "ENTREPRISE",
}

MAP_PLAN_FRONTEND_VERS_BACKEND = {
    "DECOUVERTE": Plan.Code.BATISSEUR,
    "PRO": Plan.Code.MAITRE_OEUVRE,
    "ENTREPRISE": Plan.Code.PROMOTEUR,
}


def formater_client_plateforme(ent: Entreprise) -> dict:
    """Formate une entreprise cliente selon le schéma attendu par l'interface d'administration."""
    # Trouver l'abonnement actif ou en essai, sinon le dernier abonnement créé
    abonnement = (
        ent.abonnements.filter(
            statut__in=[Abonnement.Statut.ACTIF, Abonnement.Statut.ESSAI]
        ).first()
        or ent.abonnements.first()
    )

    ref_transaction = ""
    if abonnement:
        dernier_paiement = (
            PaiementAbonnement.objects.filter(
                facture__abonnement=abonnement,
                statut=PaiementAbonnement.Statut.CONFIRME,
            )
            .order_by("-cree_le")
            .first()
        )
        if dernier_paiement and dernier_paiement.reference_transaction:
            ref_transaction = dernier_paiement.reference_transaction
        else:
            ref_transaction = f"TXN-{abonnement.id.hex[:8].upper()}"

    montant_mensuel = 0
    code_plan_brut = "BATISSEUR"
    if abonnement and abonnement.plan:
        code_plan_brut = abonnement.plan.code
        montant_mensuel = abonnement.plan.prix_mensuel_montant or 0

    code_plan = code_plan_brut

    date_debut_iso = (
        abonnement.date_debut.isoformat() if abonnement else ent.date_inscription.date().isoformat()
    )
    date_fin_iso = (
        abonnement.date_fin.isoformat()
        if abonnement
        else (ent.date_inscription.date() + timedelta(days=14)).isoformat()
    )

    charge_abonnement = {
        "statut": abonnement.statut if abonnement else "ESSAI",
        "plan_code": code_plan,
        "reference_transaction": ref_transaction,
        "montant_mensuel_centimes": montant_mensuel,
        "date_debut": date_debut_iso,
        "date_fin": date_fin_iso,
        "fin_essai": (
            abonnement.fin_essai.isoformat() if (abonnement and abonnement.fin_essai) else None
        ),
        "renouvellement_auto": (abonnement.renouvellement_auto if abonnement else True),
    }

    nb_utilisateurs = 0
    nb_projets = 0
    active_le = None

    if ent.schema_name and ent.schema_name != "public":
        try:
            with schema_context(ent.schema_name):
                nb_utilisateurs = Utilisateur.objects.filter(statut=StatutUtilisateur.ACTIF).count()
                nb_projets = Projet.objects.filter(supprime_le__isnull=True).count()
                premier_connecte = (
                    Utilisateur.objects.filter(last_login__isnull=False)
                    .order_by("last_login")
                    .first()
                )
                if premier_connecte and premier_connecte.last_login:
                    active_le = premier_connecte.last_login.isoformat()
        except Exception as e:
            logger.warning(
                "Impossible de compter les ressources pour le tenant %s : %s",
                ent.schema_name,
                e,
            )

    # Si pas de date de login dans le schéma, vérifier la demande d'inscription
    if not active_le:
        demande = DemandeInscription.objects.filter(
            entreprise=ent, utilise_le__isnull=False
        ).first()
        if demande and demande.utilise_le:
            active_le = demande.utilise_le.isoformat()

    statut_client = ent.statut
    if ent.statut == StatutEntreprise.ESSAI and not active_le and nb_utilisateurs <= 1:
        statut_client = "EN_ATTENTE"

    return {
        "id": str(ent.id),
        "raison_sociale": ent.raison_sociale,
        "nom_commercial": ent.nom_commercial or ent.raison_sociale,
        "slug": ent.schema_name,
        "pays": ent.pays,
        "ville": ent.ville,
        "email_contact": ent.email_contact,
        "telephone_contact": ent.telephone_contact,
        "statut": statut_client,
        "cree_le": ent.date_inscription.isoformat(),
        "active_le": active_le,
        "nb_utilisateurs": nb_utilisateurs,
        "nb_projets": nb_projets,
        "abonnement": charge_abonnement,
    }


def lister_clients_plateforme(terme_recherche: str | None = None) -> list[dict]:
    """Retourne la liste des clients de la plateforme avec abonnements et compteurs."""
    public_schema = get_public_schema_name()
    qs = (
        Entreprise.objects.exclude(schema_name=public_schema)
        .prefetch_related("abonnements__plan", "abonnements__factures__paiements")
        .order_by("-date_inscription")
    )

    if terme_recherche:
        terme = terme_recherche.strip()
        qs = qs.filter(
            Q(raison_sociale__icontains=terme)
            | Q(nom_commercial__icontains=terme)
            | Q(schema_name__icontains=terme)
            | Q(email_contact__icontains=terme)
            | Q(ville__icontains=terme)
        )

    return [formater_client_plateforme(ent) for ent in qs]


def obtenir_fiche_client(client_id: uuid.UUID | str) -> dict:
    """Retourne la fiche détaillée d'une entreprise cliente."""
    public_schema = get_public_schema_name()
    ent = Entreprise.objects.filter(pk=client_id).exclude(schema_name=public_schema).first()
    if not ent:
        raise NotFound("Entreprise cliente introuvable.")
    return formater_client_plateforme(ent)
