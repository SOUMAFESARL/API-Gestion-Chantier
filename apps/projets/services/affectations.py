"""Services métier pour la gestion des affectations des collaborateurs au chantier (US-04).

Décisions v1.2 du découpage (§13bis) et règles du 29/10/2026 :

- **Le rôle est propre à l'affectation** : par défaut le rôle du collaborateur sur la plateforme,
  il peut différer d'un projet à l'autre.
- **Le périmètre est une ou plusieurs cases de l'arbre** ; aucune case : tout le projet. Les
  anciens champs `lot` et `zone` disparaissent.
- **Un seul chef de chantier par projet** : c'est lui, et lui seul, qui écrit le journal. En
  affecter un second est refusé ; pour en changer, `changer_chef_chantier` retire l'ancien
  (son affectation reste dans l'historique) et affecte le nouveau en un seul geste.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Role, Utilisateur
from apps.core.droits import a_permission, est_dg
from apps.core.enums import RoleProjet
from apps.core.exceptions import (
    ChefProjetProtege,
    DgNonAssignableCommeCp,
    ErreurConflit,
    RequeteRefusee,
)
from apps.core.permissions import obtenir_portee_role
from apps.projets.models import AffectationProjet, Element, Projet


def verifier_affectable(utilisateur: Utilisateur | None) -> None:
    """Le Directeur Général ne tient aucune fonction sur un chantier.

    Décision du 14/10/2026 : le DG a ses attributions, chaque fonction de
    chantier a les siennes, et il ne se substitue à aucune. Il voit tous les
    chantiers sans affectation (portée entreprise) ; une affectation ne lui
    donnerait qu'une fonction qu'il n'a pas à tenir.

    **Seul point de contrôle** : la création de projet, sa modification et les
    routes d'affectation passent toutes par ici.
    """
    if utilisateur is not None and est_dg(utilisateur):
        raise DgNonAssignableCommeCp()


def peut_gerer_chef_projet(utilisateur, request=None) -> bool:
    """Qui peut retirer, désactiver, rétrograder ou nommer un chef de projet.

    Décision du 22/10/2026 : le chef de projet est protégé. Seuls le DG et les rôles de
    portée ENTREPRISE qui détiennent `projets.affecter_membres` y touchent ; un conducteur
    de travaux, même affecté au chantier, ne le peut pas.
    """
    if not utilisateur or not getattr(utilisateur, "is_authenticated", False):
        return False
    if utilisateur.is_superuser or est_dg(utilisateur):
        return True
    return obtenir_portee_role(utilisateur) == "ENTREPRISE" and a_permission(
        utilisateur, "projets.affecter_membres", request=request
    )


def verifier_peut_gerer_chef_projet(utilisateur, request=None) -> None:
    """Lève `ChefProjetProtege` (403) si l'utilisateur ne peut pas toucher au chef de projet."""
    if not peut_gerer_chef_projet(utilisateur, request=request):
        raise ChefProjetProtege()


def est_chef_projet(role_projet) -> bool:
    return (role_projet or "").upper() == RoleProjet.CHEF_PROJET


class ChefChantierDejaAffecte(ErreurConflit):
    code_metier = "chef_chantier_deja_affecte"
    default_detail = (
        "Ce projet a déjà un chef de chantier : un seul par projet. Pour en changer, utilisez "
        "« Changer le chef de chantier »."
    )


def verifier_chef_chantier_unique(projet, utilisateur, role_projet, affectation_id=None) -> None:
    """Un seul chef de chantier actif par projet (règle du 29/10/2026)."""
    if (role_projet or "").upper() != RoleProjet.CHEF_CHANTIER:
        return
    autre = (
        AffectationProjet.objects.filter(
            projet=projet,
            role_projet=RoleProjet.CHEF_CHANTIER,
            est_actif=True,
            supprime_le__isnull=True,
        )
        .exclude(utilisateur=utilisateur)
        .select_related("utilisateur")
    )
    if affectation_id:
        autre = autre.exclude(pk=affectation_id)
    existant = autre.first()
    if existant is not None:
        raise ChefChantierDejaAffecte(
            details={
                "chef_chantier_actuel": {
                    "affectation_id": str(existant.pk),
                    "utilisateur_id": str(existant.utilisateur_id),
                    "nom": f"{existant.utilisateur.prenom} {existant.utilisateur.nom}".strip(),
                }
            }
        )


def resoudre_perimetres(projet: Projet, ids) -> list[Element]:
    """Les cases d'un périmètre, vérifiées : du projet, vivantes. Liste vide : tout le projet."""
    if not ids:
        return []
    cases = list(Element.objects.filter(pk__in=ids, projet=projet))
    if len(cases) != len(set(map(str, ids))):
        raise RequeteRefusee("Une case du périmètre n'appartient pas à ce projet ou a été supprimée.")
    return cases


def role_par_defaut(utilisateur) -> str:
    """Le rôle du collaborateur sur la plateforme : le rôle proposé par défaut sur un projet."""
    role = getattr(utilisateur, "role", None)
    if role is not None and getattr(role, "code", ""):
        return role.code.upper()
    return (getattr(utilisateur, "role_global", "") or RoleProjet.VISITEUR).upper()


def retirer_dg_des_chantiers(*, appliquer: bool = False) -> list[str]:
    """Met les données antérieures à la règle en conformité : le DG quitte ses fonctions.

    À appeler dans le schéma de l'entreprise. Pour chaque DG désigné chef de
    projet ou conducteur de travaux d'un chantier, ou affecté à un chantier :
    la désignation est retirée (le chantier passe « sans chef de projet ») et
    l'affectation désactivée — la même chose que la désactivation d'un
    collaborateur (`accounts.services.utilisateurs`). Rien n'est supprimé.

    Sans `appliquer`, ne fait que décrire ce qui changerait.
    """
    from apps.audit.services import journaliser
    from apps.core.enums import ActionAudit

    affectations = AffectationProjet.objects.filter(est_actif=True, supprime_le__isnull=True)
    candidats = (
        set(affectations.values_list("utilisateur_id", flat=True))
        | set(Projet.objects.exclude(chef_projet=None).values_list("chef_projet_id", flat=True))
        | set(
            Projet.objects.exclude(conducteur_travaux=None).values_list(
                "conducteur_travaux_id", flat=True
            )
        )
    )
    constats = []
    for dg in Utilisateur.objects.filter(pk__in=candidats).select_related("role"):
        if not est_dg(dg):
            continue
        chef_de = list(Projet.objects.filter(chef_projet=dg).values_list("reference", flat=True))
        conducteur_de = list(
            Projet.objects.filter(conducteur_travaux=dg).values_list("reference", flat=True)
        )
        affecte = affectations.filter(utilisateur=dg)
        constats.append(
            f"{dg.email} : chef de projet de {chef_de or 'aucun chantier'}, "
            f"conducteur de travaux de {conducteur_de or 'aucun chantier'}, "
            f"{affecte.count()} affectation(s) active(s)"
        )
        if not appliquer:
            continue
        with transaction.atomic():
            maintenant = timezone.now()
            affecte.update(est_actif=False, modifie_le=maintenant)
            Projet.objects.filter(chef_projet=dg).update(
                chef_projet=None, sans_chef_projet=True, modifie_le=maintenant
            )
            Projet.objects.filter(conducteur_travaux=dg).update(
                conducteur_travaux=None, modifie_le=maintenant
            )
            journaliser(
                action=ActionAudit.MODIFICATION,
                type_entite="Utilisateur",
                entite_id=dg.id,
                valeur_avant={"chef_projet_de": chef_de, "conducteur_travaux_de": conducteur_de},
                valeur_apres={"evenement": "DG_RETIRE_DES_FONCTIONS_DE_CHANTIER"},
            )
    return constats


def lister_affectations_projet(projet: Projet, actifs_seulement: bool = False):
    """Renvoie les affectations du projet avec chargement optimisé des relations."""
    qs = (
        AffectationProjet.objects.filter(projet=projet, supprime_le__isnull=True)
        .select_related("utilisateur")
        .prefetch_related("perimetres")
        .order_by("role_projet", "utilisateur__nom", "utilisateur__prenom")
    )
    if actifs_seulement:
        qs = qs.filter(est_actif=True)
    return qs


def affecter_collaborateur_projet(
    *,
    projet: Projet,
    utilisateur: Utilisateur,
    role_projet: str | None = None,
    date_debut=None,
    date_fin=None,
    fonction_membre: str = "",
    perimetres_ids=None,
    modifie_par: Utilisateur | None = None,
    **kwargs,
) -> AffectationProjet:
    """Affecte ou réactive un collaborateur sur un chantier, avec un rôle et un périmètre."""
    verifier_affectable(utilisateur)
    role_projet = (role_projet or role_par_defaut(utilisateur)).upper()
    # Tout rôle de la table `role` (CP, CT, CC, VI, ou créé depuis) — plus de liste figée.
    if role_projet not in RoleProjet.values and not Role.objects.filter(
        code__iexact=role_projet, est_actif=True
    ).exists():
        raise ValidationError(_("Le rôle de projet spécifié n'est pas valide."))

    if date_debut and date_fin and date_fin < date_debut:
        raise ValidationError(_("La date de fin ne peut pas être antérieure à la date de début."))

    date_debut_effective = date_debut or timezone.now().date()
    perimetres = resoudre_perimetres(projet, perimetres_ids)
    verifier_chef_chantier_unique(projet, utilisateur, role_projet)

    with transaction.atomic():
        affectation = AffectationProjet.tous_objets.filter(
            projet=projet,
            utilisateur=utilisateur,
        ).first()

        if affectation:
            # Réactivation et mise à jour du rôle
            affectation.role_projet = role_projet
            affectation.date_debut = date_debut_effective
            affectation.date_fin = date_fin
            affectation.fonction_membre = fonction_membre
            affectation.est_actif = True
            affectation.supprime_le = None
            affectation.supprime_par = None
            affectation.save(
                update_fields=[
                    "role_projet",
                    "date_debut",
                    "date_fin",
                    "fonction_membre",
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
                date_debut=date_debut_effective,
                date_fin=date_fin,
                fonction_membre=fonction_membre,
                est_actif=True,
                cree_par=modifie_par,
            )
        if perimetres_ids is not None:
            affectation.perimetres.set(perimetres)

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


@transaction.atomic
def changer_chef_chantier(
    *,
    projet: Projet,
    utilisateur: Utilisateur,
    perimetres_ids=None,
    date_changement=None,
    modifie_par: Utilisateur | None = None,
) -> dict:
    """Change le chef de chantier en un seul geste (validé le 29/10/2026).

    L'ancien chef perd sa fonction ce jour : son affectation est close (date de fin, inactive)
    et reste dans l'historique ; le nouveau est affecté comme chef de chantier.
    """
    jour = date_changement or timezone.localdate()
    ancien = (
        AffectationProjet.objects.select_for_update()
        .filter(
            projet=projet,
            role_projet=RoleProjet.CHEF_CHANTIER,
            est_actif=True,
            supprime_le__isnull=True,
        )
        .exclude(utilisateur=utilisateur)
        .select_related("utilisateur")
        .first()
    )
    if ancien is not None:
        ancien.est_actif = False
        ancien.date_fin = jour
        ancien.save(update_fields=["est_actif", "date_fin", "modifie_le"])
    nouveau = affecter_collaborateur_projet(
        projet=projet,
        utilisateur=utilisateur,
        role_projet=RoleProjet.CHEF_CHANTIER,
        date_debut=jour,
        perimetres_ids=perimetres_ids if perimetres_ids is not None else [],
        modifie_par=modifie_par,
    )
    from apps.audit.services import journaliser
    from apps.core.enums import ActionAudit

    journaliser(
        action=ActionAudit.MODIFICATION,
        type_entite="Projet",
        entite_id=projet.pk,
        utilisateur_id=getattr(modifie_par, "pk", None),
        valeur_avant={"chef_chantier": str(ancien.utilisateur_id) if ancien else None},
        valeur_apres={"evenement": "CHANGEMENT_CHEF_CHANTIER", "chef_chantier": str(utilisateur.pk)},
    )
    return {"ancien": ancien, "nouveau": nouveau}


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
    role_final = nouveau_role or affectation.role_projet

    # Le périmètre et l'unicité du chef de chantier se vérifient avant toute écriture.
    perimetres = None
    if "perimetres_ids" in donnees:
        perimetres = resoudre_perimetres(affectation.projet, donnees["perimetres_ids"])
    actif_final = donnees.get("est_actif", affectation.est_actif)
    if actif_final:
        verifier_chef_chantier_unique(
            affectation.projet, affectation.utilisateur, role_final, affectation_id=affectation.pk
        )

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
    for c in ["role_projet", "date_debut", "date_fin", "est_actif", "fonction_membre"]:
        if c in donnees:
            setattr(affectation, c, donnees[c])
            champs.append(c)
    if perimetres is not None:
        affectation.perimetres.set(perimetres)

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
