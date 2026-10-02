"""Services métier pour la gestion des affectations d'équipe au chantier (US-04).

Rôles supportés :
- Conducteur de travaux (CT)
- Chef de Chantier (CC)
- Consultant lecture (VI / CL)
- Maître d'Œuvre (MOE)
- Maître d'Ouvrage (MOA)
- Chef de Projet (CP)
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Role, Utilisateur
from apps.core.enums import RoleProjet
from apps.projets.models import AffectationProjet, Projet


def lister_affectations_projet(projet: Projet, actifs_seulement: bool = False):
    """Renvoie les affectations du projet avec chargement optimisé des relations."""
    qs = (
        AffectationProjet.objects.filter(projet=projet, supprime_le__isnull=True)
        .select_related("utilisateur", "role")
        .order_by("role_projet", "utilisateur__nom", "utilisateur__prenom")
    )
    if actifs_seulement:
        qs = qs.filter(est_actif=True)
    return qs


def affecter_collaborateur_projet(
    *,
    projet: Projet,
    utilisateur: Utilisateur,
    role_projet: str,
    date_debut=None,
    date_fin=None,
    role_personnalise: Role | None = None,
    modifie_par: Utilisateur | None = None,
) -> AffectationProjet:
    """Affecte ou réactive un collaborateur sur un chantier avec un rôle spécifique."""
    if role_projet not in RoleProjet.values:
        raise ValidationError(_("Le rôle de projet spécifié n'est pas valide."))

    if date_debut and date_fin and date_fin < date_debut:
        raise ValidationError(_("La date de fin ne peut pas être antérieure à la date de début."))

    date_debut_effective = date_debut or timezone.now().date()

    with transaction.atomic():
        affectation = AffectationProjet.tous_objets.filter(
            projet=projet,
            utilisateur=utilisateur,
        ).first()

        if affectation:
            # Réactivation et mise à jour du rôle
            affectation.role_projet = role_projet
            if role_personnalise is not None:
                affectation.role = role_personnalise
            affectation.date_debut = date_debut_effective
            affectation.date_fin = date_fin
            affectation.est_actif = True
            affectation.supprime_le = None
            affectation.supprime_par = None
            affectation.save(
                update_fields=[
                    "role_projet",
                    "role",
                    "date_debut",
                    "date_fin",
                    "est_actif",
                    "supprime_le",
                    "supprime_par",
                    "modifie_le",
                ]
            )
        else:
            affectation = AffectationProjet.objects.create(
                projet=projet,
                utilisateur=utilisateur,
                role_projet=role_projet,
                role=role_personnalise,
                date_debut=date_debut_effective,
                date_fin=date_fin,
                est_actif=True,
                cree_par=modifie_par,
            )

        # Synchronisation automatique du champ conducteur_travaux sur le Projet si CT
        if role_projet == RoleProjet.CONDUCTEUR_TRAVAUX and projet.conducteur_travaux_id != utilisateur.id:
            projet.conducteur_travaux = utilisateur
            projet.save(update_fields=["conducteur_travaux", "modifie_le"])

        # Synchronisation automatique du champ chef_projet si CHEF_PROJET
        if role_projet == RoleProjet.CHEF_PROJET:
            # Désactiver tout autre CP actif éventuel pour préserver l'unicité
            AffectationProjet.objects.filter(
                projet=projet,
                role_projet=RoleProjet.CHEF_PROJET,
                est_actif=True,
                supprime_le__isnull=True,
            ).exclude(utilisateur=utilisateur).update(est_actif=False)
            if projet.chef_projet_id != utilisateur.id:
                projet.chef_projet = utilisateur
                projet.save(update_fields=["chef_projet", "modifie_le"])

    return affectation


def verifier_invariant_chef_projet(projet: Projet, affectation_a_exclure_id=None):
    """Vérifie la cohérence du Chef de Projet : au maximum un seul CP actif simultanément (0 CP autorisé)."""
    qs = AffectationProjet.objects.filter(
        projet=projet,
        role_projet=RoleProjet.CHEF_PROJET,
        est_actif=True,
        supprime_le__isnull=True,
    )
    if affectation_a_exclure_id:
        qs = qs.exclude(id=affectation_a_exclure_id)
    if qs.count() > 1:
        raise ValidationError(
            _("Un chantier ne peut pas comporter plus d'un Chef de Projet actif simultanément.")
        )


def modifier_affectation_projet(
    *,
    affectation: AffectationProjet,
    donnees: dict,
    modifie_par: Utilisateur | None = None,
) -> AffectationProjet:
    """Met à jour le rôle, dates ou statut d'une affectation avec synchronisation CP."""
    nouveau_actif = donnees.get("est_actif")
    nouveau_role = donnees.get("role_projet")

    # Si on désactive ou change le rôle d'un CP, détacher du projet si c'était lui
    if affectation.role_projet == RoleProjet.CHEF_PROJET:
        if nouveau_actif is False or (nouveau_role and nouveau_role != RoleProjet.CHEF_PROJET):
            if affectation.projet.chef_projet_id == affectation.utilisateur_id:
                affectation.projet.chef_projet = None
                affectation.projet.save(update_fields=["chef_projet", "modifie_le"])
    elif nouveau_role == RoleProjet.CHEF_PROJET and (nouveau_actif is True or (nouveau_actif is None and affectation.est_actif)):
        # Promotion en Chef de Projet : désactiver l'ancien CP actif
        AffectationProjet.objects.filter(
            projet=affectation.projet,
            role_projet=RoleProjet.CHEF_PROJET,
            est_actif=True,
            supprime_le__isnull=True,
        ).exclude(id=affectation.id).update(est_actif=False)
        affectation.projet.chef_projet = affectation.utilisateur
        affectation.projet.save(update_fields=["chef_projet", "modifie_le"])

    champs = ["modifie_le"]
    for c in ["role_projet", "date_debut", "date_fin", "est_actif"]:
        if c in donnees:
            setattr(affectation, c, donnees[c])
            champs.append(c)

    if "role" in donnees:
        affectation.role = donnees["role"]
        champs.append("role")

    affectation.save(update_fields=champs)
    verifier_invariant_chef_projet(affectation.projet)
    return affectation


def revoquer_affectation_projet(
    *,
    affectation: AffectationProjet,
    suppression_physique: bool = False,
    modifie_par: Utilisateur | None = None,
):
    """Révoque (soft-delete est_actif=False) ou supprime une affectation."""
    if affectation.role_projet == RoleProjet.CHEF_PROJET:
        if affectation.projet.chef_projet_id == affectation.utilisateur_id:
            affectation.projet.chef_projet = None
            affectation.projet.save(update_fields=["chef_projet", "modifie_le"])

    if suppression_physique:
        affectation.supprimer_definitivement()
    else:
        affectation.est_actif = False
        affectation.save(update_fields=["est_actif", "modifie_le"])
        affectation.delete(utilisateur=modifie_par)
