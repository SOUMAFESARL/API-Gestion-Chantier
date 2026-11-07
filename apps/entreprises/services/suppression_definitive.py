"""Suppression définitive d'une entreprise cliente — phase de test du MVP (D9, R-12).

Sous le multi-schéma, `DROP SCHEMA` emportait tout d'un coup. Dans le schéma unique, l'entreprise
se supprime **par son `entreprise_id`, dans une transaction** : ce qui réussit entier, ou ne laisse
rien.

**Le périmètre se calcule, il ne s'écrit pas.** Une liste de tables tenue à la main oublierait la
prochaine table d'entreprise ; la suppression échouerait alors à la validation, sur une clé
étrangère, ou — pire — laisserait des lignes. `perimetre()` lit les modèles :

1. **les porteurs** : tout modèle qui a une clé étrangère vers `Entreprise` (les `ModeleEntreprise`,
   mais aussi l'abonnement, les factures, les demandes d'inscription…) ;
2. **leurs dépendants** : les tables sans entreprise qui pointent vers une ligne supprimée — tables
   de liaison des `ManyToManyField`, paiements d'une facture, rappels d'un abonnement. Supprimés
   si la clé est obligatoire ou en cascade ; **mis à nul** sinon (`cree_par` d'une ligne du
   catalogue, par exemple) ;
3. **le journal d'audit** de l'entreprise (`entreprise_id` sans clé étrangère) — sauvegardé avec
   le reste, puis supprimé, comme le faisait `DROP SCHEMA`. Le journal de la plateforme, lui,
   reste : c'est lui qui consigne la suppression.

Les clés étrangères de Django sont différées : l'ordre des `DELETE` est libre dans la transaction,
et `SET CONSTRAINTS ALL IMMEDIATE`, à la fin, fait remonter ici une référence oubliée plutôt qu'au
`COMMIT`.

Le Socle §3.1 (suppression logique) continue de régir les données métier : cette purge est un
outil de l'éditeur, derrière un interrupteur (`SUPPRESSION_ENTREPRISE_ACTIVEE`).
"""

import logging
from dataclasses import dataclass, field
from functools import reduce
from operator import or_
from typing import Any

from django.apps import apps
from django.core.files.storage import default_storage
from django.db import connection, models, transaction

from apps.core.contexte import contexte_entreprise, portee_plateforme

logger = logging.getLogger(__name__)

# Entreprises qui ne se suppriment jamais : la démonstration.
SLUGS_PROTEGES = frozenset({"demo"})

# Réglage de session lu par le déclencheur d'immuabilité de `historique_date` : il n'autorise la
# suppression que des lignes de l'entreprise purgée, sous le rôle de la portée plateforme.
REGLAGE_PURGE = "ccd.purge_entreprise"


class EntrepriseProtegee(Exception):
    """L'entreprise fait partie des entreprises système (`demo`) : elle ne se supprime jamais."""


def est_protegee(entreprise) -> bool:
    return entreprise.slug.lower() in SLUGS_PROTEGES


# --------------------------------------------------------------------------
# Le périmètre
# --------------------------------------------------------------------------
@dataclass
class Perimetre:
    """Les lignes que la suppression emporte, et celles qu'elle détache."""

    entreprise: Any
    porteurs: list[tuple[type[models.Model], models.QuerySet]] = field(default_factory=list)
    dependants: list[tuple[type[models.Model], models.QuerySet]] = field(default_factory=list)
    detachements: list[tuple[type[models.Model], str, models.QuerySet]] = field(
        default_factory=list
    )

    def a_supprimer(self) -> list[tuple[type[models.Model], models.QuerySet]]:
        """Dépendants d'abord : leurs sous-requêtes lisent les porteurs encore présents."""
        return [*self.dependants, *self.porteurs]


def _cles_vers(modele, cibles) -> list[models.ForeignKey]:
    return [
        f for f in modele._meta.concrete_fields
        if f.is_relation and f.many_to_one and f.related_model in cibles
    ]


def perimetre(entreprise, adresses: list[str] | None = None) -> Perimetre:
    """Calcule le périmètre de suppression de `entreprise` — sans rien lire encore.

    Les querysets sont paresseux, et passent par `_base_manager` : ils ne s'évaluent qu'en
    portée plateforme, où ni le gestionnaire ni la RLS ne filtrent.
    """
    from apps.audit.models import JournalAudit
    from apps.entreprises.models import DemandeInscription, Entreprise

    resultat = Perimetre(entreprise=entreprise)
    selection: dict[type[models.Model], models.QuerySet] = {}

    for modele in apps.get_models():
        if modele is Entreprise:
            continue
        cles = _cles_vers(modele, {Entreprise})
        if not cles:
            continue
        condition = reduce(or_, (models.Q(**{cle.name: entreprise.pk}) for cle in cles))
        if modele is DemandeInscription:
            # Les demandes par adresse et par slug aussi : sans elles, l'adresse et le nom
            # resteraient réservés après la suppression.
            condition |= models.Q(slug_reserve__iexact=entreprise.slug)
            if adresses:
                condition |= models.Q(email__in=adresses)
        selection[modele] = modele._base_manager.filter(condition)

    resultat.porteurs = [
        *selection.items(),
        (JournalAudit, JournalAudit._base_manager.filter(entreprise_id=entreprise.pk)),
    ]

    for modele in apps.get_models(include_auto_created=True):
        if modele is Entreprise or modele in selection:
            continue
        conditions_suppression = []
        for cle in _cles_vers(modele, set(selection)):
            parents = selection[cle.related_model].values(cle.target_field.attname)
            condition = models.Q(**{f"{cle.name}__in": parents})
            if cle.null and cle.remote_field.on_delete is not models.CASCADE:
                resultat.detachements.append(
                    (modele, cle.attname, modele._base_manager.filter(condition))
                )
            else:
                conditions_suppression.append(condition)
        if conditions_suppression:
            resultat.dependants.append(
                (modele, modele._base_manager.filter(reduce(or_, conditions_suppression)))
            )

    return resultat


# --------------------------------------------------------------------------
# Lecture : ce que l'écran de confirmation montre
# --------------------------------------------------------------------------
def _lire_entreprise(entreprise) -> dict[str, Any]:
    """Adresses, fichiers, dirigeants et compteurs de l'entreprise — lus dans son contexte."""
    from apps.accounts.models import Utilisateur
    from apps.projets.models import Projet
    from apps.projets.models.contrat import ProjetContrat

    with contexte_entreprise(entreprise):
        lignes = list(
            Utilisateur.objects.values("email", "nom", "prenom", "is_owner", "avatar", "role__code")
        )
        nb_projets = Projet.objects.filter(supprime_le__isnull=True).count()
        contrats = [c for c in ProjetContrat.objects.values_list("fichier", flat=True) if c]

    resultat: dict[str, Any] = {
        "emails": set(), "avatars": [], "contrats": contrats, "dirigeants": [],
        "nb_utilisateurs": len(lignes), "nb_projets": nb_projets,
    }
    for ligne in lignes:
        resultat["emails"].add(ligne["email"].strip().lower())
        if ligne["avatar"]:
            resultat["avatars"].append(ligne["avatar"])
        if ligne["is_owner"] or ligne["role__code"] == "DG":
            resultat["dirigeants"].append(
                {"nom": f"{ligne['prenom']} {ligne['nom']}".strip(), "email": ligne["email"]}
            )
    return resultat


def _adresses(entreprise, lecture: dict[str, Any]) -> list[str]:
    adresses = set(lecture["emails"])
    adresses.add(entreprise.email_contact.strip().lower())
    adresses.discard("")
    return sorted(adresses)


def apercu_suppression(entreprise) -> dict[str, Any]:
    """Ce que la suppression emporterait — pour que le super admin sache ce qu'il confirme."""
    from apps.billing.models import PaiementAbonnement

    lecture = _lire_entreprise(entreprise)
    nb_paiements = PaiementAbonnement._base_manager.filter(facture__entreprise=entreprise).count()
    return {
        "slug": entreprise.slug,
        "raison_sociale": entreprise.raison_sociale,
        "protegee": est_protegee(entreprise),
        "nb_utilisateurs": lecture["nb_utilisateurs"],
        "nb_projets": lecture["nb_projets"],
        "nb_paiements": nb_paiements,
        "adresses": _adresses(entreprise, lecture),
        "dirigeants": lecture["dirigeants"],
    }


# --------------------------------------------------------------------------
# La suppression
# --------------------------------------------------------------------------
def _supprimer_fichiers(avatars: list[str], contrats: list[str]) -> dict[str, int]:
    """Après le succès de la base : un fichier supprimé ne se restaure pas."""
    from apps.projets.storage import StockageContrats

    compte = {"avatars": 0, "contrats": 0, "echecs": 0}
    for nom in avatars:
        try:
            default_storage.delete(nom)
            compte["avatars"] += 1
        except Exception:
            compte["echecs"] += 1
    stockage = StockageContrats()
    for nom in contrats:
        try:
            stockage.delete(nom)
            compte["contrats"] += 1
        except Exception:
            compte["echecs"] += 1
    return compte


def supprimer_definitivement(entreprise) -> dict[str, Any]:
    """Supprime l'entreprise et toutes ses lignes, et libère ses adresses e-mail.

    Atomique : tout est supprimé, ou rien. Les fichiers (avatars, contrats) ne partent qu'après.
    """
    if est_protegee(entreprise):
        raise EntrepriseProtegee(entreprise.slug)

    lecture = _lire_entreprise(entreprise)
    adresses = _adresses(entreprise, lecture)
    plan = perimetre(entreprise, adresses)
    lignes: dict[str, int] = {}

    with portee_plateforme(motif="suppression définitive d'une entreprise"), transaction.atomic():
        with connection.cursor() as curseur:
            # Local à la transaction : il disparaît avec elle.
            curseur.execute(
                "SELECT set_config(%s, %s, true)", [REGLAGE_PURGE, str(entreprise.pk)]
            )
        for modele, attribut, queryset in plan.detachements:
            nombre = queryset.update(**{attribut: None})
            if nombre:
                lignes[f"{modele._meta.db_table}.{attribut} (mis à nul)"] = nombre
        for modele, queryset in plan.a_supprimer():
            # `_raw_delete` : un `DELETE` SQL, sans le collecteur de Django — ni cascade
            # applicative, ni suppression logique de `ModeleBase`, ni signal. Le périmètre a déjà
            # tout recensé.
            nombre = queryset._raw_delete(queryset.db)
            if nombre:
                lignes[modele._meta.db_table] = lignes.get(modele._meta.db_table, 0) + nombre
        type(entreprise)._base_manager.filter(pk=entreprise.pk)._raw_delete(connection.alias)
        with connection.cursor() as curseur:
            # Une référence oubliée échoue ici, avec son nom, et annule tout.
            curseur.execute("SET CONSTRAINTS ALL IMMEDIATE")

    fichiers = _supprimer_fichiers(lecture["avatars"], lecture["contrats"])
    logger.warning(
        "Entreprise %s supprimée définitivement (%s lignes, %s adresses libérées)",
        entreprise.slug, sum(lignes.values()), len(adresses),
    )
    return {
        "slug": entreprise.slug,
        "adresses_liberees": adresses,
        "tables_nettoyees": lignes,
        "fichiers_supprimes": fichiers,
        "nb_utilisateurs": lecture["nb_utilisateurs"],
        "nb_projets": lecture["nb_projets"],
    }
