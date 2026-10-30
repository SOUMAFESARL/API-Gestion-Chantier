"""Services métier pour l'application chantier — gestion des rapports journaliers.

Architecture selectors/services : toutes les règles métier et écritures
en base sont concentrées ici.
"""

from datetime import date

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import Utilisateur
from apps.chantier.models import RapportJournalier
from apps.chantier.selectors.rapport_journalier import rapport_existe
from apps.core.enums import Meteo, StatutRapport
from apps.core.exceptions import ErreurMetier, RapportDejaExistant, RapportNonModifiable
from apps.projets.models import Projet
from apps.projets.services.sante_declencheur import declencher_recalcul_sante

__all__ = [
    "creer_rapport_journalier",
    "modifier_rapport_journalier",
    "rejeter_rapport_journalier",
    "soumettre_rapport_journalier",
    "valider_rapport_journalier",
]


def _verifier_route_historique(rapport):
    """Les rapports du nouveau journal passent par son circuit CC/CT/CP."""
    from apps.chantier.models import JournalChantier

    if JournalChantier.objects.filter(rapport_id=rapport.pk).exists():
        raise RapportNonModifiable(
            "Utilisez les routes /api/v1/chantier/rapports/ pour ce journal."
        )


@transaction.atomic
def creer_rapport_journalier(
    *,
    projet: Projet,
    auteur: Utilisateur,
    date_rapport: date,
    meteo: str = Meteo.ENSOLEILLE,
    effectif_regie: int = 0,
    effectif_tacherons: int = 0,
    effectif_present: int | None = None,
    observations: str = "",
    blocages_critiques: int = 0,
    statut: str = StatutRapport.SOUMIS,
    origine: str = "WEB",
    cree_par: Utilisateur | None = None,
) -> RapportJournalier:
    """Crée un rapport journalier en validant l'unicité et les règles métier."""
    from apps.chantier.services.journal import tient_fonction

    # Seul le chef de chantier du projet écrit le rapport du jour (29/10/2026).
    if not tient_fonction(projet, auteur, "CC"):
        raise PermissionDenied("Seul le chef de chantier du projet écrit le journal.")
    # Règle RG-02 / US-038 : un seul rapport par projet et par jour (un seul chef de chantier)
    if rapport_existe(projet_id=projet.id, date_rapport=date_rapport):
        raise RapportDejaExistant()

    # Calcul d'effectif total si non fourni
    if effectif_present is None or effectif_present == 0:
        effectif_present = (effectif_regie or 0) + (effectif_tacherons or 0)

    est_soumis = statut == StatutRapport.SOUMIS
    soumis_le = timezone.now() if est_soumis else None

    rapport = RapportJournalier.objects.create(
        projet=projet,
        auteur=auteur,
        date_rapport=date_rapport,
        meteo=meteo,
        effectif_regie=effectif_regie,
        effectif_tacherons=effectif_tacherons,
        effectif_present=effectif_present,
        observations=observations,
        blocages_critiques=blocages_critiques,
        statut=statut,
        soumis_le=soumis_le,
        origine=origine,
        cree_par=cree_par or auteur,
    )

    if est_soumis:
        declencher_recalcul_sante(
            projet_id=projet.id,
            declencheur_type="RAPPORT_SOUMISSION",
            declencheur_id=rapport.id,
        )

    return rapport


@transaction.atomic
def modifier_rapport_journalier(
    *,
    rapport: RapportJournalier,
    modifie_par: Utilisateur,
    **champs,
) -> RapportJournalier:
    """Met à jour partiellement ou totalement un rapport de chantier."""
    _verifier_route_historique(rapport)
    # Règle US-042 / MLD §6.7 : un rapport approuvé ne peut plus être modifié
    if rapport.statut == StatutRapport.APPROUVE:
        raise RapportNonModifiable()

    nouvelle_date = champs.get("date_rapport", rapport.date_rapport)
    nouveau_projet = champs.get("projet", rapport.projet)

    # Vérification d'unicité si la date ou le projet a changé
    change = nouvelle_date != rapport.date_rapport or nouveau_projet != rapport.projet
    if change and rapport_existe(
        projet_id=nouveau_projet.id,
        date_rapport=nouvelle_date,
        exclure_id=rapport.id,
    ):
        raise RapportDejaExistant()

    # Application des modifications
    champs_modifiables = [
        "projet",
        "date_rapport",
        "meteo",
        "effectif_regie",
        "effectif_tacherons",
        "effectif_present",
        "observations",
        "blocages_critiques",
        "origine",
    ]

    for champ in champs_modifiables:
        if champ in champs:
            setattr(rapport, champ, champs[champ])

    # Re-calcul effectif_present si non spécifié explicitement
    if "effectif_present" not in champs:
        rapport.effectif_present = (rapport.effectif_regie or 0) + (rapport.effectif_tacherons or 0)

    rapport.save()
    return rapport


@transaction.atomic
def soumettre_rapport_journalier(
    *,
    rapport: RapportJournalier,
    utilisateur: Utilisateur,
) -> RapportJournalier:
    """Passe un rapport du statut BROUILLON ou REJETE à SOUMIS."""
    _verifier_route_historique(rapport)
    if rapport.statut == StatutRapport.APPROUVE:
        raise RapportNonModifiable("Un rapport déjà approuvé ne peut plus être re-soumis.")

    rapport.statut = StatutRapport.SOUMIS
    rapport.soumis_le = timezone.now()
    rapport.save(update_fields=["statut", "soumis_le", "modifie_le"])

    declencher_recalcul_sante(
        projet_id=rapport.projet_id,
        declencheur_type="RAPPORT_SOUMISSION",
        declencheur_id=rapport.id,
    )
    return rapport


@transaction.atomic
def valider_rapport_journalier(
    *,
    rapport: RapportJournalier,
    utilisateur: Utilisateur,
    commentaire: str = "",
) -> RapportJournalier:
    """Valide et approuve le rapport journalier (action Conducteur de Travaux)."""
    _verifier_route_historique(rapport)
    rapport.statut = StatutRapport.APPROUVE
    rapport.valide_par = utilisateur
    rapport.valide_le = timezone.now()
    rapport.commentaire_validation = commentaire
    rapport.save(
        update_fields=[
            "statut",
            "valide_par",
            "valide_le",
            "commentaire_validation",
            "modifie_le",
        ]
    )
    return rapport


@transaction.atomic
def rejeter_rapport_journalier(
    *,
    rapport: RapportJournalier,
    utilisateur: Utilisateur,
    motif: str,
) -> RapportJournalier:
    """Rejette le rapport journalier avec motif obligatoire >= 20 caractères."""
    _verifier_route_historique(rapport)
    if rapport.statut == StatutRapport.APPROUVE:
        raise RapportNonModifiable("Un rapport déjà approuvé ne peut plus être rejeté.")

    motif_nettoye = (motif or "").strip()
    if len(motif_nettoye) < 20:
        raise ErreurMetier(
            "Le motif de rejet doit obligatoirement comporter au moins 20 caractères.",
            details={"motif": "minimum_20_caracteres_requis"},
        )

    rapport.statut = StatutRapport.REJETE
    rapport.valide_par = utilisateur
    rapport.valide_le = timezone.now()
    rapport.commentaire_validation = motif_nettoye
    rapport.save(
        update_fields=[
            "statut",
            "valide_par",
            "valide_le",
            "commentaire_validation",
            "modifie_le",
        ]
    )

    declencher_recalcul_sante(
        projet_id=rapport.projet_id,
        declencheur_type="RAPPORT_REJET",
        declencheur_id=rapport.id,
    )
    return rapport
