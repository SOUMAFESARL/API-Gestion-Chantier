"""Les lignes que `peupler_donnees_test` ne crée pas, et que des routes désignent.

Sans elles, une route est sautée (« aucune ligne de B ») : elle n'est pas éprouvée. Chaque
ligne porte un libellé ou une référence `ETANCHEITE` qui la rend idempotente.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

MARQUE = "ETANCHEITE"


def completer(slug: str) -> None:
    """Complète l'entreprise `slug` ; rejouable."""
    from apps.core.contexte import contexte_entreprise, portee_plateforme
    from apps.tenants.models import Entreprise

    with portee_plateforme(motif="suite d'étanchéité : complément du jeu de test"):
        entreprise = Entreprise.objects.get(schema_name=slug)
        _facturation(entreprise, slug)
        _demande_inscription(entreprise, slug)
    with contexte_entreprise(entreprise):
        _projets(slug)


def _projets(slug: str) -> None:
    from apps.chantier.models.synthese import SynthesePeriodique
    from apps.projets.models import (
        Avenant,
        Dependance,
        Element,
        ExceptionCalendrier,
        ListeValeursEntreprise,
        ModeleDecoupageEntreprise,
        Projet,
        ValeurListeEntreprise,
    )

    aujourdhui = timezone.localdate()
    projet = Projet.objects.get(reference="TEST-2026-002")

    if not Avenant.objects.filter(numero=MARQUE).exists():
        Avenant.objects.create(
            projet=projet, numero=MARQUE, date_signature=aujourdhui, objet="Avenant de test"
        )
    if not ExceptionCalendrier.objects.filter(motif=MARQUE).exists():
        ExceptionCalendrier.objects.create(
            date=aujourdhui + timedelta(days=400), ouvre=False, motif=MARQUE
        )
    liste = ListeValeursEntreprise.objects.filter(libelle=MARQUE).first()
    if liste is None:
        liste = ListeValeursEntreprise.objects.create(libelle=MARQUE)
    if not ValeurListeEntreprise.objects.filter(libelle=MARQUE).exists():
        ValeurListeEntreprise.objects.create(liste_entreprise=liste, libelle=MARQUE)
    if not ModeleDecoupageEntreprise.objects.filter(nom=MARQUE).exists():
        ModeleDecoupageEntreprise.objects.create(nom=MARQUE)
    if not SynthesePeriodique.objects.filter(projet=projet).exists():
        SynthesePeriodique.objects.create(
            projet=projet,
            type="HEBDOMADAIRE",
            date_debut=aujourdhui - timedelta(days=13),
            date_fin=aujourdhui - timedelta(days=7),
        )
    if not Dependance.objects.filter(projet=projet).exists():
        feuilles = list(
            Element.objects.filter(projet=projet, enfants__isnull=True).order_by("ordre", "pk")[:2]
        )
        Dependance.objects.create(projet=projet, predecesseur=feuilles[0], successeur=feuilles[1])


def _facturation(entreprise, slug: str) -> None:
    from apps.billing.models import Abonnement, Facture, PaiementAbonnement, Plan

    aujourdhui = timezone.localdate()
    abonnement = Abonnement.objects.filter(entreprise=entreprise).first()
    if abonnement is None:
        abonnement = Abonnement.objects.create(
            entreprise=entreprise,
            plan=Plan.objects.order_by("code").first(),
            statut=Abonnement.Statut.ACTIF,
            date_debut=aujourdhui - timedelta(days=30),
            date_fin=aujourdhui + timedelta(days=335),
        )
    numero = f"FAC-{MARQUE}-{slug}"
    facture = Facture.objects.filter(numero=numero).first()
    if facture is None:
        facture = Facture.objects.create(
            numero=numero,
            abonnement=abonnement,
            entreprise=entreprise,
            periode_debut=abonnement.date_debut,
            periode_fin=abonnement.date_fin,
            montant_ht=10_000,
            montant_tva=1_800,
            montant_ttc=11_800,
            date_echeance=aujourdhui,
        )
    reference = f"CMD-{MARQUE}-{slug}"
    if not PaiementAbonnement.objects.filter(reference_commande=reference).exists():
        PaiementAbonnement.objects.create(
            facture=facture,
            reference_commande=reference,
            reference_transaction=f"TX-{MARQUE}-{slug}",
            montant=11_800,
        )


def _demande_inscription(entreprise, slug: str) -> None:
    from apps.tenants.models import DemandeInscription

    if DemandeInscription.objects.filter(entreprise=entreprise).exists():
        return
    maintenant = timezone.now()
    DemandeInscription.objects.create(
        raison_sociale=entreprise.raison_sociale,
        pays="CI",
        email=f"inscription@{slug}.ci",
        slug_reserve=slug,
        empreinte=f"{MARQUE}-{slug}",
        expire_le=maintenant + timedelta(days=1),
        cgu_version="1",
        cgu_acceptees_le=maintenant,
        statut=DemandeInscription.Statut.ACTIVEE,
        entreprise=entreprise,
    )
