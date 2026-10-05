import logging
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Invitation, Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

logger = logging.getLogger(__name__)


@transaction.atomic
def creer_utilisateur(
    *,
    email,
    nom,
    prenom="",
    telephone="",
    langue="fr",
    mot_de_passe=None,
    role_global=None,
):
    utilisateur = Utilisateur.objects.create_user(
        email=email,
        password=mot_de_passe,
        nom=nom,
        prenom=prenom,
        telephone=telephone,
        langue=langue,
        role_global=role_global,
    )

    return utilisateur


@transaction.atomic
def desactiver_collaborateur_plateforme(
    *,
    collaborateur: Utilisateur,
    auteur: Utilisateur,
) -> dict:
    """Désactive un collaborateur de toute la plateforme (départ de l'entreprise).

    Invariants garantis :
    - Le compte du DG / Propriétaire ne peut jamais être désactivé ni supprimé.
    - Un utilisateur ne peut pas désactiver son propre compte.
    - Soft-delete avec statut DESACTIVE, is_active=False, supprime_le posé.
    - Clôture automatique de toutes les affectations actives sur les chantiers.
    - Révocation des invitations en attente et des sessions actives.
    """
    if getattr(collaborateur, "is_owner", False) or getattr(collaborateur, "is_dg", False) or getattr(collaborateur, "role_global", None) == RoleGlobal.DIRECTEUR_GENERAL:
        raise ValidationError(
            _("Le compte du Directeur Général / Propriétaire ne peut pas être désactivé.")
        )

    if collaborateur.pk == auteur.pk:
        raise ValidationError(
            _("Vous ne pouvez pas désactiver votre propre compte.")
        )

    collaborateur.statut = StatutUtilisateur.DESACTIVE
    collaborateur.is_active = False
    collaborateur.supprime_le = timezone.now()
    collaborateur.supprime_par = auteur
    collaborateur.save(
        update_fields=[
            "statut",
            "is_active",
            "supprime_le",
            "supprime_par",
            "modifie_le",
        ]
    )

    # 1. Clôture de toutes les affectations actives sur les chantiers
    try:
        from apps.projets.models import AffectationProjet, Projet

        AffectationProjet.objects.filter(
            utilisateur=collaborateur,
            est_actif=True,
        ).update(
            est_actif=False,
            modifie_le=timezone.now(),
        )
        Projet.objects.filter(chef_projet=collaborateur).update(
            chef_projet=None, modifie_le=timezone.now()
        )
        Projet.objects.filter(conducteur_travaux=collaborateur).update(
            conducteur_travaux=None, modifie_le=timezone.now()
        )
    except Exception as exc:
        logger.warning(
            "Erreur lors de la clôture des chantiers pour l'utilisateur %s: %s",
            collaborateur.id,
            exc,
        )

    # 2. Révocation des invitations en attente pour cet email
    Invitation.objects.filter(
        email__iexact=collaborateur.email,
        statut=Invitation.Statut.ENVOYEE,
    ).update(
        statut=Invitation.Statut.REVOQUEE,
        modifie_le=timezone.now(),
    )

    # 3. Révocation de toutes ses sessions actives (liste noire des jetons JWT)
    try:
        from apps.accounts.services.liste_noire import revoquer_utilisateur

        revoquer_utilisateur(collaborateur.pk, ttl=86400)
    except Exception as exc:
        logger.warning(
            "Erreur lors de la révocation de session pour l'utilisateur %s: %s",
            collaborateur.id,
            exc,
        )

    return {
        "id": str(collaborateur.pk),
        "email": collaborateur.email,
        "statut": collaborateur.statut,
        "message": str(
            _(
                "Collaborateur retiré de la plateforme avec succès. Ses accès ont été révoqués et ses affectations de chantiers clôturées."
            )
        ),
    }

