"""Suppression définitive d'une entreprise cliente — phase de test du MVP.

Détruit le schéma de l'entreprise et tout ce qui la référence, et libère ses adresses e-mail.
S'appuie sur `nettoyage.supprimer_entreprise_proprement` (schéma + dépendances du schéma public)
et ajoute ce qu'il ne couvrait pas : le registre global des e-mails, les invitations, les demandes
d'inscription par adresse, les comptes publics et les fichiers stockés.
"""

import logging
from typing import Any

from django.core.files.storage import default_storage
from django.db import connection, transaction
from django_tenants.utils import get_public_schema_name, schema_context

from apps.accounts.models import Utilisateur
from apps.billing.models import PaiementAbonnement
from apps.projets.models import Projet
from apps.projets.models.contrat import ProjetContrat
from apps.projets.storage import StockageContrats
from apps.tenants.models import Entreprise, RegistreEmail
from apps.tenants.services.nettoyage import SCHEMAS_PROTEGES, supprimer_entreprise_proprement

logger = logging.getLogger(__name__)


class EntrepriseProtegee(Exception):
    """Le schéma fait partie des schémas système (public, demo) : il ne se supprime jamais."""


def est_protegee(entreprise: Entreprise) -> bool:
    return entreprise.schema_name.lower() in SCHEMAS_PROTEGES


def _lire_schema(entreprise: Entreprise) -> dict[str, Any]:
    """Adresses, fichiers, dirigeants et compteurs lus dans le schéma de l'entreprise."""
    resultat: dict[str, Any] = {
        "emails": set(), "avatars": [], "contrats": [], "dirigeants": [],
        "nb_utilisateurs": 0, "nb_projets": 0,
    }
    try:
        with schema_context(entreprise.schema_name):
            lignes = list(
                Utilisateur._base_manager.values(
                    "email", "nom", "prenom", "is_owner", "avatar", "role__code"
                )
            )
            resultat["nb_utilisateurs"] = Utilisateur.objects.count()
            resultat["nb_projets"] = Projet.objects.filter(supprime_le__isnull=True).count()
            resultat["contrats"] = [
                c for c in ProjetContrat._base_manager.values_list("fichier", flat=True) if c
            ]
    except Exception:  # noqa: BLE001 — un schéma orphelin ou illisible n'empêche pas la purge
        logger.warning("Schéma illisible : %s", entreprise.schema_name, exc_info=True)
        return resultat
    for ligne in lignes:
        resultat["emails"].add(ligne["email"].strip().lower())
        if ligne["avatar"]:
            resultat["avatars"].append(ligne["avatar"])
        if ligne["is_owner"] or ligne["role__code"] == "DG":
            resultat["dirigeants"].append(
                {"nom": f"{ligne['prenom']} {ligne['nom']}".strip(), "email": ligne["email"]}
            )
    return resultat


def _emails_du_registre(entreprise: Entreprise) -> set[str]:
    with schema_context(get_public_schema_name()):
        return {
            e.strip().lower()
            for e in RegistreEmail._base_manager.filter(entreprise=entreprise).values_list(
                "email", flat=True
            )
        }


def _adresses(entreprise: Entreprise, lecture: dict[str, Any]) -> list[str]:
    adresses = lecture["emails"] | _emails_du_registre(entreprise)
    adresses.add(entreprise.email_contact.strip().lower())
    adresses.discard("")
    return sorted(adresses)


def apercu_suppression(entreprise: Entreprise) -> dict[str, Any]:
    """Ce que la suppression emporterait — pour que le super admin sache ce qu'il confirme."""
    lecture = _lire_schema(entreprise)
    with schema_context(get_public_schema_name()):
        nb_paiements = PaiementAbonnement._base_manager.filter(
            facture__entreprise=entreprise
        ).count()
    return {
        "slug": entreprise.schema_name,
        "raison_sociale": entreprise.raison_sociale,
        "protegee": est_protegee(entreprise),
        "nb_utilisateurs": lecture["nb_utilisateurs"],
        "nb_projets": lecture["nb_projets"],
        "nb_paiements": nb_paiements,
        "adresses": _adresses(entreprise, lecture),
        "dirigeants": lecture["dirigeants"],
    }


def _supprimer_fichiers(avatars: list[str], contrats: list[str]) -> dict[str, int]:
    """Après le succès de la base : un fichier supprimé ne se restaure pas."""
    compte = {"avatars": 0, "contrats": 0, "echecs": 0}
    for nom in avatars:
        try:
            default_storage.delete(nom)
            compte["avatars"] += 1
        except Exception:  # noqa: BLE001
            compte["echecs"] += 1
    stockage = StockageContrats()
    for nom in contrats:
        try:
            stockage.delete(nom)
            compte["contrats"] += 1
        except Exception:  # noqa: BLE001
            compte["echecs"] += 1
    return compte


def supprimer_definitivement(entreprise: Entreprise) -> dict[str, Any]:
    """Supprime l'entreprise, son schéma, ses comptes, et libère ses adresses e-mail.

    Atomique : `DROP SCHEMA` est transactionnel sous PostgreSQL, donc tout est supprimé ou rien.
    """
    if est_protegee(entreprise):
        raise EntrepriseProtegee(entreprise.schema_name)

    # Relevé avant que le schéma disparaisse.
    lecture = _lire_schema(entreprise)
    adresses = _adresses(entreprise, lecture)

    with transaction.atomic():
        with connection.cursor() as cursor:
            # PostgreSQL refuse de détruire une table qui a des vérifications de clés étrangères
            # différées en attente (écritures faites plus tôt dans la même transaction).
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE;")
            # Le registre référence l'entreprise : à retirer avant elle.
            cursor.execute(
                "DELETE FROM public.registre_email WHERE entreprise_id = %s OR lower(email) = ANY(%s);",
                [str(entreprise.id), adresses],
            )
        rapport = supprimer_entreprise_proprement(str(entreprise.id))
        with connection.cursor() as cursor:
            for table in ("invitation", "demande_inscription"):
                cursor.execute("SELECT to_regclass(%s) IS NOT NULL;", [f"public.{table}"])
                if cursor.fetchone()[0]:
                    cursor.execute(
                        f"DELETE FROM public.{table} WHERE lower(email) = ANY(%s);", [adresses]
                    )
            cursor.execute(
                "DELETE FROM public.utilisateur "
                "WHERE lower(email) = ANY(%s) AND is_staff = FALSE AND is_superuser = FALSE;",
                [adresses],
            )

    fichiers = _supprimer_fichiers(lecture["avatars"], lecture["contrats"])
    logger.warning("Entreprise %s supprimée définitivement (%s adresses libérées)", entreprise.schema_name, len(adresses))
    return {
        "schema": rapport.get("schema_supprime"),
        "adresses_liberees": adresses,
        "tables_nettoyees": rapport.get("tables_nettoyees", {}),
        "fichiers_supprimes": fichiers,
        "nb_utilisateurs": lecture["nb_utilisateurs"],
        "nb_projets": lecture["nb_projets"],
    }
