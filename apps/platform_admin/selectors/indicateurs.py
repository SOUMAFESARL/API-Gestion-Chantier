"""Sélecteurs pour les indicateurs de pilotage de la plateforme Super Admin."""

from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from django.utils import timezone
from django_tenants.utils import get_public_schema_name

from apps.billing.models import Abonnement, PaiementAbonnement
from apps.core.enums import StatutEntreprise
from apps.tenants.models import Entreprise


def obtenir_indicateurs_plateforme() -> dict:
    """Calcule les métriques clés globales consolidées du parc de clients."""
    public_schema = get_public_schema_name()
    qs_clients = Entreprise.objects.exclude(schema_name=public_schema)

    total_clients = qs_clients.count()
    clients_actifs = qs_clients.filter(statut=StatutEntreprise.ACTIF).count()
    clients_essai = qs_clients.filter(statut=StatutEntreprise.ESSAI).count()
    clients_impayes = (
        qs_clients.filter(abonnements__statut=Abonnement.Statut.IMPAYE).distinct().count()
    )

    # Revenu mensuel récurrent (MRR) en centimes FCFA : somme des tarifs des abonnements actifs
    mrr_centimes = (
        Abonnement.objects.filter(
            entreprise__in=qs_clients,
            statut=Abonnement.Statut.ACTIF,
        ).aggregate(total=Sum("plan__prix_mensuel_montant"))["total"]
        or 0
    )

    return {
        "nb_clients": total_clients,
        "nb_clients_actifs": clients_actifs,
        "nb_clients_en_essai": clients_essai,
        "nb_clients_impayes": clients_impayes,
        "revenu_mensuel_centimes": mrr_centimes,
    }


def obtenir_tendances_indicateurs() -> list[dict]:
    """Génère la série de sparkline (5 points) et la variation relative en % d'un mois à l'autre."""
    public_schema = get_public_schema_name()
    qs_clients = Entreprise.objects.exclude(schema_name=public_schema)

    maintenant = timezone.now()
    aujourdhui = maintenant.date()

    # Déterminer les 5 jalons mensuels (M-4, M-3, M-2, M-1, M0)
    jalons = [aujourdhui - relativedelta(months=i) for i in reversed(range(5))]

    series: dict[str, list[int]] = {
        "nb_clients": [],
        "nb_clients_actifs": [],
        "nb_clients_en_essai": [],
        "nb_clients_impayes": [],
        "revenu_mensuel_centimes": [],
    }

    for jalon in jalons[:-1]:
        date_pivot = timezone.make_aware(
            timezone.datetime.combine(jalon, timezone.datetime.max.time().replace(microsecond=0))
        )

        nb_c = qs_clients.filter(date_inscription__lte=date_pivot).count()
        nb_act = qs_clients.filter(
            statut=StatutEntreprise.ACTIF, date_inscription__lte=date_pivot
        ).count()
        nb_ess = qs_clients.filter(
            statut=StatutEntreprise.ESSAI, date_inscription__lte=date_pivot
        ).count()
        nb_imp = (
            qs_clients.filter(
                abonnements__statut=Abonnement.Statut.IMPAYE,
                date_inscription__lte=date_pivot,
            )
            .distinct()
            .count()
        )
        mrr = (
            Abonnement.objects.filter(
                entreprise__in=qs_clients,
                statut=Abonnement.Statut.ACTIF,
                cree_le__lte=date_pivot,
            ).aggregate(total=Sum("plan__prix_mensuel_montant"))["total"]
            or 0
        )

        series["nb_clients"].append(nb_c)
        series["nb_clients_actifs"].append(nb_act)
        series["nb_clients_en_essai"].append(nb_ess)
        series["nb_clients_impayes"].append(nb_imp)
        series["revenu_mensuel_centimes"].append(mrr)

    # Le 5ème point est exactement l'indicateur actuel consolidé
    courant = obtenir_indicateurs_plateforme()
    for cle in series:
        series[cle].append(courant[cle])

    resultats = []
    for cle, points in series.items():
        val_actuelle = points[-1]
        val_precedente = points[-2] if len(points) >= 2 else 0

        if val_precedente > 0:
            variation = round(((val_actuelle - val_precedente) / val_precedente) * 100)
        elif val_actuelle > 0:
            variation = 100
        else:
            variation = 0

        resultats.append(
            {
                "cle": cle,
                "points": points,
                "variation_pourcent": int(variation),
            }
        )

    return resultats


def obtenir_evolution_abonnements(nb_jours: int = 90) -> list[dict]:
    """Génère la série chronologique sur nb_jours des abonnements renouvelés vs non renouvelés."""
    public_schema = get_public_schema_name()
    qs_clients = Entreprise.objects.exclude(schema_name=public_schema)

    aujourdhui = timezone.localdate()
    debut = aujourdhui - timedelta(days=nb_jours - 1)

    renouveles_par_date: dict = {}

    # Paiements confirmés sur la période pour les clients
    paiements_confirmes = (
        PaiementAbonnement.objects.filter(
            facture__abonnement__entreprise__in=qs_clients,
            statut=PaiementAbonnement.Statut.CONFIRME,
            cree_le__date__gte=debut,
            cree_le__date__lte=aujourdhui,
        )
        .values("cree_le__date")
        .annotate(total=Sum(1))
    )
    for p in paiements_confirmes:
        d = p["cree_le__date"]
        renouveles_par_date[d] = p["total"]

    # Abonnements actifs démarrés sur la période
    abonnements_actifs = (
        Abonnement.objects.filter(
            entreprise__in=qs_clients,
            statut=Abonnement.Statut.ACTIF,
            date_debut__gte=debut,
            date_debut__lte=aujourdhui,
        )
        .values("date_debut")
        .annotate(total=Sum(1))
    )
    for a in abonnements_actifs:
        d = a["date_debut"]
        renouveles_par_date[d] = max(renouveles_par_date.get(d, 0), a["total"])

    # Abonnements échus non renouvelés
    echus_non_renouveles = (
        Abonnement.objects.filter(
            entreprise__in=qs_clients,
            date_fin__gte=debut,
            date_fin__lte=aujourdhui,
            renouvellement_auto=False,
        )
        .values("date_fin")
        .annotate(total=Sum(1))
    )
    non_renouveles_par_date = {e["date_fin"]: e["total"] for e in echus_non_renouveles}

    points = []
    for i in range(nb_jours):
        d = debut + timedelta(days=i)
        points.append(
            {
                "date": d.isoformat(),
                "renouveles": renouveles_par_date.get(d, 0),
                "non_renouveles": non_renouveles_par_date.get(d, 0),
            }
        )

    return points
