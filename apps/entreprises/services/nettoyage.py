"""Services d'inspection et de nettoyage des entreprises.

- `lister_entreprises_avec_directeurs` : l'inventaire des entreprises et de leurs dirigeants ;
- `supprimer_entreprise_proprement` : la suppression définitive, par UUID ou slug — elle délègue
  à `suppression_definitive`, seule purge de la plateforme (D9) ;
- `activer_ou_renouveler_abonnement` : la remise en service d'un abonnement.

`demo` est protégée : elle ne se supprime jamais.
"""

import contextlib
import logging
import uuid
from typing import Any

from apps.accounts.models import Utilisateur
from apps.core.contexte import contexte_entreprise
from apps.core.enums import RoleGlobal
from apps.entreprises.models import DemandeInscription, Entreprise
from apps.entreprises.services.suppression_definitive import SLUGS_PROTEGES

logger = logging.getLogger(__name__)


def lister_entreprises_avec_directeurs() -> dict[str, Any]:
    """Liste exhaustivement toutes les entreprises, leurs directeurs généraux et les demandes."""
    entreprises_data = []

    for ent in Entreprise.objects.order_by("raison_sociale"):
        directeurs = []
        try:
            with contexte_entreprise(ent):
                # Récupérer les directeurs généraux
                dgs = Utilisateur.objects.filter(role_global=RoleGlobal.DIRECTEUR_GENERAL)
                for dg in dgs:
                    directeurs.append(
                        {
                            "id": str(dg.id),
                            "email": dg.email,
                            "nom": dg.nom,
                            "prenom": dg.prenom,
                            "telephone": dg.telephone,
                            "statut": dg.statut,
                            "is_active": dg.is_active,
                            "is_owner": dg.is_owner,
                            "cree_le": str(dg.cree_le) if hasattr(dg, "cree_le") else None,
                        }
                    )
        except Exception as exc:
            logger.warning(
                "Impossible d'interroger les utilisateurs de l'entreprise %s : %s",
                ent.slug,
                exc,
            )
            directeurs.append({"erreur": f"Entreprise inaccessible : {exc}"})

        entreprises_data.append(
            {
                "id": str(ent.id),
                "slug": ent.slug,
                "raison_sociale": ent.raison_sociale,
                "nom_commercial": ent.nom_commercial,
                "email_contact": ent.email_contact,
                "telephone_contact": ent.telephone_contact,
                "statut": ent.statut,
                "date_inscription": str(ent.date_inscription),
                "est_protege": ent.slug in SLUGS_PROTEGES,
                "directeurs_generaux": directeurs,
            }
        )

    # Demandes d'inscription
    demandes_data = []
    for d in DemandeInscription.objects.all().order_by("-cree_le"):
        demandes_data.append(
            {
                "id": str(d.id),
                "email": d.email,
                "nom": d.nom,
                "prenom": d.prenom,
                "telephone": getattr(d, "telephone", ""),
                "raison_sociale": d.raison_sociale,
                "slug_reserve": d.slug_reserve,
                "statut": d.statut,
                "entreprise_id": str(d.entreprise_id) if d.entreprise_id else None,
                "cree_le": str(d.cree_le),
            }
        )

    return {
        "total_entreprises": len(entreprises_data),
        "entreprises": entreprises_data,
        "total_demandes": len(demandes_data),
        "demandes_inscription": demandes_data,
    }


def supprimer_entreprise_proprement(identifiant: str) -> dict[str, Any]:
    """Supprime une entreprise désignée par son UUID ou son slug — commande et maintenance.

    Une seule purge sur la plateforme : celle de `suppression_definitive` (par `entreprise_id`,
    dans une transaction, D9). Il n'y a plus de schéma orphelin à détruire.

    Lève:
        ValueError: si l'entreprise est protégée (`demo`) ou introuvable.
    """
    from apps.entreprises.services.suppression_definitive import supprimer_definitivement

    identifiant_str = str(identifiant).strip().lower()
    if identifiant_str in SLUGS_PROTEGES:
        raise ValueError(
            f"Suppression interdite : « {identifiant_str} » est une entreprise protégée."
        )

    entreprise = None
    with contextlib.suppress(ValueError, AttributeError):
        entreprise = Entreprise.objects.filter(id=uuid.UUID(identifiant_str)).first()
    if entreprise is None:
        entreprise = Entreprise.objects.filter(slug__iexact=identifiant_str).first()
    if entreprise is None:
        raise ValueError(f"Aucune entreprise trouvée avec l'identifiant « {identifiant} ».")
    if entreprise.slug.lower() in SLUGS_PROTEGES:
        raise ValueError(
            f"Suppression interdite : « {entreprise.slug} » est une entreprise protégée."
        )

    rapport = supprimer_definitivement(entreprise)
    return {
        "identifiant_demande": identifiant,
        "slug_supprime": entreprise.slug,
        "entreprise_trouvee": True,
        "tables_nettoyees": rapport["tables_nettoyees"],
        "adresses_liberees": rapport["adresses_liberees"],
    }


def activer_ou_renouveler_abonnement(
    identifiant: str,
    plan_code: str = "MAITRE_OEUVRE",
    duree_jours: int = 365,
) -> dict[str, Any]:
    """Active ou renouvelle un abonnement annuel ou personnalisé pour une entreprise.

    Identifiant accepté :
    - slug (ex: 'e_3at_btp')
    - UUID entreprise
    - email du contact entreprise ou du directeur général
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.billing.models import Abonnement, Plan
    from apps.core.enums import StatutEntreprise

    ent = None
    # 1. Tentative par UUID
    try:
        uuid_val = uuid.UUID(str(identifiant).strip())
        ent = Entreprise.objects.filter(pk=uuid_val).first()
    except (ValueError, AttributeError):
        pass

    # 2. Tentative par nom de schéma
    if not ent:
        ent = Entreprise.objects.filter(slug__iexact=str(identifiant).strip()).first()

    # 3. Tentative par email entreprise
    if not ent:
        ent = Entreprise.objects.filter(email_contact__iexact=str(identifiant).strip()).first()

    # 4. Tentative par email de demande d'inscription
    if not ent:
        demande = DemandeInscription.objects.filter(email__iexact=str(identifiant).strip()).first()
        if demande and demande.entreprise:
            ent = demande.entreprise

    # 5. Tentative par recherche dans les utilisateurs des schémas
    if not ent:
        for candidate in Entreprise.objects.all():
            try:
                with contexte_entreprise(candidate):
                    if Utilisateur.objects.filter(email__iexact=str(identifiant).strip()).exists():
                        ent = candidate
                        break
            except Exception:
                continue

    if not ent:
        raise ValueError(f"Entreprise introuvable pour l'identifiant '{identifiant}'.")

    # Recherche du plan
    plan_obj = Plan.objects.filter(code=plan_code).first()
    if not plan_obj:
        plan_obj = Plan.objects.filter(code__iexact=plan_code).first()
    if not plan_obj:
        plan_obj = Plan.objects.filter(est_actif=True).first()
    if not plan_obj:
        raise ValueError(f"Plan '{plan_code}' introuvable.")

    aujourdhui = timezone.localdate()
    date_fin_calculee = aujourdhui + timedelta(days=int(duree_jours))

    abonnement = ent.abonnements.first()
    if abonnement:
        abonnement.plan = plan_obj
        abonnement.statut = Abonnement.Statut.ACTIF
        abonnement.date_debut = aujourdhui
        abonnement.date_fin = date_fin_calculee
        abonnement.fin_essai = None
        abonnement.lecture_seule_depuis = None
        abonnement.renouvellement_auto = True
        abonnement.save(
            update_fields=[
                "plan",
                "statut",
                "date_debut",
                "date_fin",
                "fin_essai",
                "lecture_seule_depuis",
                "renouvellement_auto",
                "modifie_le",
            ]
        )
    else:
        abonnement = Abonnement.objects.create(
            entreprise=ent,
            plan=plan_obj,
            date_debut=aujourdhui,
            date_fin=date_fin_calculee,
            fin_essai=None,
            statut=Abonnement.Statut.ACTIF,
            renouvellement_auto=True,
        )

    # Réactiver le statut de l'entreprise si nécessaire
    ent.statut = StatutEntreprise.ACTIF
    ent.save(update_fields=["statut"])

    logger.info(
        "Abonnement de l'entreprise %s activé avec succès : Plan %s, jusqu'au %s (%d jours)",
        ent.slug,
        plan_obj.code,
        abonnement.date_fin,
        duree_jours,
    )

    return {
        "statut": "succes",
        "entreprise_id": str(ent.id),
        "slug": ent.slug,
        "raison_sociale": ent.raison_sociale,
        "email_contact": ent.email_contact,
        "plan_code": plan_obj.code,
        "plan_libelle": plan_obj.libelle,
        "date_debut": str(abonnement.date_debut),
        "date_fin": str(abonnement.date_fin),
        "statut_abonnement": abonnement.statut,
        "duree_jours": duree_jours,
        "lecture_seule": False,
    }

