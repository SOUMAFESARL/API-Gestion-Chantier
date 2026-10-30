"""Le circuit de signature d'un rapport : tous les signataires attendus signent (30/10/2026).

- **Qui est attendu.** À la soumission, la plateforme fige deux listes : ceux qui ont
  `chantier.valider` sur le projet, puis ceux qui ont `chantier.approuver`, dont la partie du
  projet recouvre celle du rapport (`fonctions`). L'auteur en fait partie si son rôle a la
  permission : c'est l'entreprise qui règle ses rôles.
- **Tous signent**, une étape après l'autre : tous les validateurs, puis tous les approbateurs.
- **La liste est figée**, à une exception : quelqu'un qui n'a plus la fonction sur le projet
  (retiré, remplacé, rôle changé) n'est plus attendu. Personne n'est ajouté après coup.
- **Une étape sans personne** : la validation est sautée ; l'approbation, elle, reste en attente
  — le rapport est « validé », et l'écran signale qu'aucun approbateur n'est affecté.
- **Un refus** renvoie le rapport à son auteur et efface toutes les signatures.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.chantier.services.fonctions import (
    APPROUVER,
    VALIDER,
    chemins_des_cases,
    titulaires,
)
from apps.core.exceptions import ErreurMetier

__all__ = [
    "APPROBATION",
    "VALIDATION",
    "attendus_restants",
    "attendus_effectifs",
    "figer_signataires",
    "reevaluer",
    "reevaluer_journaux_du_projet",
    "signer",
]

VALIDATION = "VALIDATION"
APPROBATION = "APPROBATION"
PERMISSION_DE = {VALIDATION: VALIDER, APPROBATION: APPROUVER}


def _nom(utilisateur) -> str:
    return f"{utilisateur.prenom} {utilisateur.nom}".strip() or utilisateur.email


def chemins_du_rapport(journal) -> tuple[str, ...]:
    return chemins_des_cases(journal.perimetre_ids)


def figer_signataires(journal) -> None:
    """Fige les signataires attendus et repart d'un circuit vierge (soumission ou re-soumission)."""
    projet = journal.rapport.projet
    chemins = chemins_du_rapport(journal)
    journal.signataires_attendus = {
        etape: [
            str(t.utilisateur.pk) for t in titulaires(projet, permission) if t.concerne(chemins)
        ]
        for etape, permission in PERMISSION_DE.items()
    }
    journal.signatures = []
    journal.valide_ct_par = None
    journal.valide_ct_le = None
    journal.commentaire_ct = ""


def etape_en_cours(journal) -> str | None:
    rapport = journal.rapport
    if rapport.statut != "SOUMIS":
        return None
    return APPROBATION if journal.valide_ct_le else VALIDATION


def attendus_effectifs(journal, etape) -> list[str]:
    """La liste figée, moins ceux qui n'ont plus la fonction sur le projet."""
    figes = (journal.signataires_attendus or {}).get(etape, [])
    if not figes:
        return []
    actuels = {
        str(t.utilisateur.pk) for t in titulaires(journal.rapport.projet, PERMISSION_DE[etape])
    }
    return [u for u in figes if u in actuels]


def signes(journal, etape) -> set[str]:
    return {s["utilisateur_id"] for s in journal.signatures or [] if s["etape"] == etape}


def attendus_restants(journal, etape=None) -> list[str]:
    etape = etape or etape_en_cours(journal)
    if etape is None:
        return []
    deja = signes(journal, etape)
    return [u for u in attendus_effectifs(journal, etape) if u not in deja]


def _clore_validation(journal, dernier=None, commentaire="") -> None:
    journal.valide_ct_par = dernier
    journal.valide_ct_le = timezone.now()
    journal.commentaire_ct = commentaire


def _clore_approbation(journal, dernier, commentaire="") -> None:
    rapport = journal.rapport
    rapport.statut = "APPROUVE"
    rapport.valide_par = dernier
    rapport.valide_le = timezone.now()
    rapport.commentaire_validation = commentaire
    rapport.save()


def reevaluer(journal, *, dernier=None, commentaire="") -> bool:
    """Clôt l'étape en cours quand plus personne n'est attendu. Rend True si le statut change.

    La validation sans validateur se saute ; l'approbation sans approbateur attend.
    """
    change = False
    if etape_en_cours(journal) == VALIDATION and not attendus_restants(journal, VALIDATION):
        _clore_validation(journal, dernier, commentaire)
        change = True
        dernier, commentaire = None, ""
    if etape_en_cours(journal) == APPROBATION:
        effectifs = attendus_effectifs(journal, APPROBATION)
        if effectifs and not attendus_restants(journal, APPROBATION):
            _clore_approbation(journal, dernier, commentaire)
            change = True
    return change


def signer(journal, utilisateur, etape, commentaire="") -> None:
    """La signature d'une personne attendue à l'étape en cours."""
    en_cours = etape_en_cours(journal)
    if en_cours != etape:
        attendu = "SOUMIS" if etape == VALIDATION else "VALIDE_CT"
        raise ErreurMetier(f"La signature exige le statut {attendu}.")
    moi = str(utilisateur.pk)
    if moi in signes(journal, etape):
        raise ErreurMetier("Vous avez déjà signé ce rapport.")
    if moi not in attendus_effectifs(journal, etape):
        raise PermissionDenied(
            "Vous n'êtes pas attendu pour signer ce rapport : votre rôle sur le projet n'a pas la "
            "permission, ou votre partie du projet ne couvre pas ce rapport."
        )
    journal.signatures = [
        *(journal.signatures or []),
        {
            "etape": etape,
            "utilisateur_id": moi,
            "nom": _nom(utilisateur),
            "signe_le": timezone.now().isoformat(),
            "commentaire": commentaire,
        },
    ]
    reevaluer(journal, dernier=utilisateur, commentaire=commentaire)


def peut_refuser(journal, utilisateur) -> bool:
    etape = etape_en_cours(journal)
    return bool(etape) and str(utilisateur.pk) in attendus_effectifs(journal, etape)


def reevaluer_journaux_du_projet(projet) -> int:
    """Après un départ ou un remplacement : les rapports qui n'attendaient plus que lui avancent."""
    from apps.chantier.models import JournalChantier

    avances = 0
    for journal in JournalChantier.objects.select_related("rapport", "rapport__projet").filter(
        rapport__projet=projet, rapport__statut="SOUMIS", rapport__supprime_le__isnull=True
    ):
        if reevaluer(journal):
            journal.save()
            avances += 1
    return avances
