"""Services d'inspection et de nettoyage souverain des entreprises et de leurs schémas.

Garantit la suppression propre et atomique d'une entreprise :
1. Suppression physique du schéma PostgreSQL (DROP SCHEMA IF EXISTS ... CASCADE).
2. Nettoyage exhaustif et ordonné de toutes les références dans le schéma public :
   - Paiements et factures (paiement_abonnement, facture)
   - Abonnements et rappels / relances (rappel_expiration_abonnement, relance_essai, abonnement)
   - Modules catalogue souscrits (catalogue_entreprise_module)
   - Demandes d'inscription associées (demande_inscription)
   - Domaines rattachés (domaine)
   - Entrée principale dans entreprise_cliente
   - Comptes utilisateurs résiduels dans public.utilisateur rattachés à ce contact (hors staff)
3. Protection absolue : 'public' et 'demo' sont sanctuarisés et ne peuvent jamais être supprimés.
"""

import logging
import uuid
from typing import Any

from django.conf import settings
from django.db import connection
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal
from apps.tenants.models import DemandeInscription, Entreprise

logger = logging.getLogger(__name__)

# Schémas strictement protégés contre toute suppression
SCHEMAS_PROTEGES = frozenset({"public", "demo"})


def lister_entreprises_avec_directeurs() -> dict[str, Any]:
    """Liste exhaustivement toutes les entreprises, leurs directeurs généraux et les demandes."""
    entreprises_data = []

    for ent in Entreprise.objects.exclude(schema_name=settings.PUBLIC_SCHEMA_NAME).order_by(
        "raison_sociale"
    ):
        directeurs = []
        try:
            with schema_context(ent.schema_name):
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
                "Impossible d'interroger les utilisateurs du schéma %s : %s",
                ent.schema_name,
                exc,
            )
            directeurs.append({"erreur": f"Schéma inaccessible: {exc}"})

        # Domaines associés
        domaines = list(ent.domains.values_list("domain", flat=True))

        entreprises_data.append(
            {
                "id": str(ent.id),
                "schema_name": ent.schema_name,
                "raison_sociale": ent.raison_sociale,
                "nom_commercial": ent.nom_commercial,
                "email_contact": ent.email_contact,
                "telephone_contact": ent.telephone_contact,
                "statut": ent.statut,
                "date_inscription": str(ent.date_inscription),
                "domaines": domaines,
                "est_protege": ent.schema_name in SCHEMAS_PROTEGES,
                "directeurs_generaux": directeurs,
            }
        )

    # Demandes d'inscription dans public
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
    """Supprime une entreprise de manière propre et atomique (schéma + dépendances public).

    Arguments:
        identifiant: Nom du schéma (schema_name) ou UUID de l'entreprise (id).

    Lève:
        ValueError: Si le schéma fait partie des schémas protégés (public, demo) ou si introuvable.
    """
    identifiant_str = str(identifiant).strip().lower()

    if identifiant_str in SCHEMAS_PROTEGES:
        raise ValueError(
            f"Suppression interdite : le schéma « {identifiant_str} » fait partie "
            "des schémas système protégés (public, demo)."
        )

    # 1. Identifier l'entreprise et son schéma
    entreprise = None
    schema_nom = None

    # Tenter par UUID
    try:
        val_uuid = uuid.UUID(identifiant_str)
        entreprise = Entreprise.objects.filter(id=val_uuid).first()
    except (ValueError, AttributeError):
        pass

    # Tenter par schema_name si pas trouvé par UUID
    if not entreprise:
        entreprise = Entreprise.objects.filter(schema_name__iexact=identifiant_str).first()

    # Si l'entreprise existe en base
    if entreprise:
        schema_nom = entreprise.schema_name
    else:
        # Vérifier si c'est un schéma orphelin existant directement dans PostgreSQL
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s;",
                [identifiant_str],
            )
            row = cursor.fetchone()
            if row:
                schema_nom = row[0]

    if not entreprise and not schema_nom:
        raise ValueError(
            f"Aucune entreprise ni schéma trouvé avec l'identifiant « {identifiant} »."
        )

    if schema_nom in SCHEMAS_PROTEGES:
        raise ValueError(
            f"Suppression interdite : le schéma « {schema_nom} » fait partie "
            "des schémas système protégés (public, demo)."
        )

    rapport: dict[str, Any] = {
        "identifiant_demande": identifiant,
        "schema_supprime": schema_nom,
        "entreprise_trouvee": bool(entreprise),
        "tables_nettoyees": {},
    }

    ent_id_str = str(entreprise.id) if entreprise else None
    ent_email = entreprise.email_contact if entreprise else None

    # 2. Exécution atomique
    with connection.cursor() as cursor:
        # A. DROP SCHEMA CASCADE
        if schema_nom:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_nom}" CASCADE;')
            rapport["schema_drop"] = True

        # B. Nettoyage dans public
        ent_ids = [ent_id_str] if ent_id_str else []

        # Retrouver aussi d'éventuels IDs orphelins liés au schema_name
        if schema_nom and not ent_ids:
            cursor.execute(
                "SELECT id FROM public.entreprise_cliente WHERE schema_name = %s;",
                [schema_nom],
            )
            for r in cursor.fetchall():
                ent_ids.append(str(r[0]))

        if ent_ids:
            # catalogue_entreprise_module
            cursor.execute(
                "DELETE FROM public.catalogue_entreprise_module WHERE entreprise_id = ANY(%s);",
                [ent_ids],
            )
            rapport["tables_nettoyees"]["catalogue_entreprise_module"] = cursor.rowcount

            # factures & paiements
            cursor.execute(
                """
                DELETE FROM public.paiement_abonnement
                WHERE facture_id IN (
                    SELECT id FROM public.facture WHERE entreprise_id = ANY(%s)
                );
            """,
                [ent_ids],
            )
            rapport["tables_nettoyees"]["paiement_abonnement"] = cursor.rowcount

            cursor.execute("DELETE FROM public.facture WHERE entreprise_id = ANY(%s);", [ent_ids])
            rapport["tables_nettoyees"]["facture"] = cursor.rowcount

            # abonnements & rappels / relances
            cursor.execute(
                """
                DELETE FROM public.rappel_expiration_abonnement
                WHERE abonnement_id IN (
                    SELECT id FROM public.abonnement WHERE entreprise_id = ANY(%s)
                );
            """,
                [ent_ids],
            )
            rapport["tables_nettoyees"]["rappel_expiration_abonnement"] = cursor.rowcount

            cursor.execute(
                """
                DELETE FROM public.relance_essai
                WHERE abonnement_id IN (
                    SELECT id FROM public.abonnement WHERE entreprise_id = ANY(%s)
                );
            """,
                [ent_ids],
            )
            rapport["tables_nettoyees"]["relance_essai"] = cursor.rowcount

            cursor.execute(
                "DELETE FROM public.abonnement WHERE entreprise_id = ANY(%s);", [ent_ids]
            )
            rapport["tables_nettoyees"]["abonnement"] = cursor.rowcount

            # domaines
            cursor.execute("DELETE FROM public.domaine WHERE tenant_id = ANY(%s);", [ent_ids])
            rapport["tables_nettoyees"]["domaine"] = cursor.rowcount

            # demandes_inscription liées
            cursor.execute(
                "DELETE FROM public.demande_inscription WHERE entreprise_id = ANY(%s);",
                [ent_ids],
            )
            rapport["tables_nettoyees"]["demande_inscription_par_entreprise"] = cursor.rowcount

            # entreprise_cliente
            cursor.execute("DELETE FROM public.entreprise_cliente WHERE id = ANY(%s);", [ent_ids])
            rapport["tables_nettoyees"]["entreprise_cliente"] = cursor.rowcount

        # C. Nettoyage complémentaire des demandes par slug_reserve
        if schema_nom:
            cursor.execute(
                "DELETE FROM public.demande_inscription WHERE slug_reserve = %s;",
                [schema_nom],
            )
            nb_dem = cursor.rowcount
            if nb_dem > 0:
                rapport["tables_nettoyees"]["demande_inscription_par_slug"] = nb_dem

            # Domaines orphelins portant le nom du schéma (ex: schema.localhost)
            cursor.execute(
                "DELETE FROM public.domaine WHERE domain ILIKE %s;",
                [f"{schema_nom}.%"],
            )
            nb_dom = cursor.rowcount
            if nb_dom > 0:
                rapport["tables_nettoyees"]["domaine_par_nom"] = nb_dom

        # D. Nettoyage éventuel des comptes temporaires de public.utilisateur non-staff
        if ent_email:
            cursor.execute(
                """
                DELETE FROM public.utilisateur
                WHERE email = %s
                  AND is_staff = FALSE
                  AND is_superuser = FALSE;
            """,
                [ent_email],
            )
            if cursor.rowcount > 0:
                rapport["tables_nettoyees"]["utilisateur_public"] = cursor.rowcount

    logger.info(
        "Entreprise « %s » (schéma: %s) purgée avec succès : %s",
        identifiant,
        schema_nom,
        rapport["tables_nettoyees"],
    )
    return rapport


def activer_ou_renouveler_abonnement(
    identifiant: str,
    plan_code: str = "MAITRE_OEUVRE",
    duree_jours: int = 365,
) -> dict[str, Any]:
    """Active ou renouvelle un abonnement annuel ou personnalisé pour une entreprise dans le schéma public.

    Identifiant accepté :
    - schema_name (ex: 'e_3at_btp')
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
        ent = Entreprise.objects.filter(schema_name__iexact=str(identifiant).strip()).first()

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
        for candidate in Entreprise.objects.exclude(schema_name=settings.PUBLIC_SCHEMA_NAME):
            try:
                with schema_context(candidate.schema_name):
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
        ent.schema_name,
        plan_obj.code,
        abonnement.date_fin,
        duree_jours,
    )

    return {
        "statut": "succes",
        "entreprise_id": str(ent.id),
        "schema_name": ent.schema_name,
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

