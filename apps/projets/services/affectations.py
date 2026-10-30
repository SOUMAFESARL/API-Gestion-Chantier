"""Services métier pour la gestion des affectations des collaborateurs au chantier (US-04).

Décisions v1.2 du découpage (§13bis) et règles du 29/10/2026 :

- **Le rôle est propre à l'affectation** : par défaut le rôle du collaborateur sur la plateforme,
  il peut différer d'un projet à l'autre.
- **Le périmètre est une ou plusieurs cases de l'arbre** ; aucune case : tout le projet. Les
  anciens champs `lot` et `zone` disparaissent.
- **Un rôle peut être unique sur un projet** (réglage du rôle, 30/10/2026 ; coché par défaut pour
  le chef de projet et le chef de chantier). En affecter un second est refusé ; pour en changer,
  `remplacer_titulaire` retire l'ancien (son affectation reste dans l'historique) et affecte le
  nouveau en un seul geste. Un rôle non unique se tient à autant qu'on veut.
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


class RoleUniqueDejaTenu(ErreurConflit):
    code_metier = "role_unique_deja_tenu"
    default_detail = (
        "Ce rôle est unique sur le projet et quelqu'un le tient déjà. Pour en changer, utilisez "
        "« Remplacer »."
    )


def _nom(utilisateur) -> str:
    return f"{utilisateur.prenom} {utilisateur.nom}".strip() or utilisateur.email


def role_de(code_role) -> Role | None:
    return Role.objects.filter(code__iexact=code_role or "", supprime_le__isnull=True).first()


def titulaires_en_cours(projet, code_role):
    """Les affectations actives et en cours qui tiennent ce rôle sur le projet."""
    from django.db.models import Q

    return (
        AffectationProjet.objects.filter(
            projet=projet,
            role_projet__iexact=code_role,
            est_actif=True,
            supprime_le__isnull=True,
        )
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=timezone.localdate()))
        .select_related("utilisateur")
    )


def verifier_role_unique(projet, utilisateur, role_projet, affectation_id=None) -> None:
    """Un rôle réglé « unique par projet » n'a qu'un titulaire à la fois (30/10/2026)."""
    role = role_de(role_projet)
    if role is None or not role.unique_par_projet:
        return
    autres = titulaires_en_cours(projet, role.code).exclude(utilisateur=utilisateur)
    if affectation_id:
        autres = autres.exclude(pk=affectation_id)
    existant = autres.first()
    if existant is not None:
        raise RoleUniqueDejaTenu(
            f"« {role.libelle} » est unique sur ce projet et {_nom(existant.utilisateur)} le "
            "tient déjà. Pour en changer, utilisez « Remplacer ».",
            details={
                "role": role.code,
                "titulaire_actuel": {
                    "affectation_id": str(existant.pk),
                    "utilisateur_id": str(existant.utilisateur_id),
                    "nom": _nom(existant.utilisateur),
                },
            },
        )


def projets_en_depassement(code_role) -> list[dict]:
    """Les projets où plusieurs personnes tiennent déjà ce rôle (au moment de le rendre unique)."""
    from django.db.models import Count, Q

    jour = timezone.localdate()
    lignes = (
        AffectationProjet.objects.filter(
            role_projet__iexact=code_role, est_actif=True, supprime_le__isnull=True
        )
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour))
        .values("projet_id", "projet__nom")
        .annotate(nombre=Count("id"))
        .filter(nombre__gt=1)
        .order_by("projet__nom")
    )
    return [
        {"projet_id": ligne["projet_id"], "projet_nom": ligne["projet__nom"], "nombre": ligne["nombre"]}
        for ligne in lignes
    ]


def affectations_en_cours_du_role(code_role) -> list[dict]:
    """Où un rôle est encore tenu : les projets et le nombre de personnes, pour refuser de le
    supprimer tant que ces affectations ne sont pas réglées."""
    from django.db.models import Count, Q

    jour = timezone.localdate()
    lignes = (
        AffectationProjet.objects.filter(
            role_projet__iexact=code_role, est_actif=True, supprime_le__isnull=True
        )
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour))
        .values("projet_id", "projet__nom")
        .annotate(nombre=Count("id"))
        .order_by("projet__nom")
    )
    return [
        {"projet_id": ligne["projet_id"], "projet_nom": ligne["projet__nom"], "nombre": ligne["nombre"]}
        for ligne in lignes
    ]


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
    verifier_role_unique(projet, utilisateur, role_projet)

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

        # La fiche du projet garde un chef de projet et un conducteur « principaux » (demande du
        # product owner) : le premier affecté le devient ; les suivants s'ajoutent à côté.
        if role_projet == RoleProjet.CONDUCTEUR_TRAVAUX and not projet.conducteur_travaux_id:
            projet.conducteur_travaux = utilisateur
            projet.save(update_fields=["conducteur_travaux", "modifie_le"])
        if role_projet == RoleProjet.CHEF_PROJET and not projet.chef_projet_id:
            projet.chef_projet = utilisateur
            projet.save(update_fields=["chef_projet", "modifie_le"])

    return affectation


def _principal(projet, champ, code_role, ancien, nouveau) -> None:
    """La fiche suit le remplacement : si l'ancien était le principal, le nouveau le devient."""
    if getattr(projet, f"{champ}_id") == ancien.utilisateur_id:
        setattr(projet, champ, nouveau)
        projet.save(update_fields=[champ, "modifie_le"])


@transaction.atomic
def remplacer_titulaire(
    *,
    projet: Projet,
    role_projet: str,
    utilisateur: Utilisateur,
    affectation_remplacee_id=None,
    perimetres_ids=None,
    date_changement=None,
    modifie_par: Utilisateur | None = None,
) -> dict:
    """Remplace la personne qui tient un rôle sur le projet, en un seul geste (30/10/2026).

    L'ancien perd sa fonction ce jour : son affectation est close (date de fin, inactive) et reste
    dans l'historique ; le nouveau est affecté avec le même rôle. Pour un rôle unique, l'ancien
    est son titulaire ; sinon il faut dire qui est remplacé (`affectation_remplacee_id`).
    """
    role = role_de(role_projet)
    if role is None:
        raise RequeteRefusee("Le rôle de projet spécifié n'est pas valide.")
    jour = date_changement or timezone.localdate()
    titulaires = titulaires_en_cours(projet, role.code).select_for_update(of=("self",))
    if affectation_remplacee_id:
        ancien = titulaires.filter(pk=affectation_remplacee_id).first()
        if ancien is None:
            raise RequeteRefusee("Cette personne ne tient pas ce rôle sur le projet.")
    elif role.unique_par_projet:
        ancien = titulaires.exclude(utilisateur=utilisateur).first()
    else:
        raise RequeteRefusee(
            f"« {role.libelle} » n'est pas unique sur le projet : précisez qui est remplacé."
        )
    if ancien is not None:
        if ancien.utilisateur_id == utilisateur.pk:
            raise RequeteRefusee("Cette personne tient déjà ce rôle sur le projet.")
        ancien.est_actif = False
        ancien.date_fin = jour
        ancien.save(update_fields=["est_actif", "date_fin", "modifie_le"])
    nouveau = affecter_collaborateur_projet(
        projet=projet,
        utilisateur=utilisateur,
        role_projet=role.code,
        date_debut=jour,
        perimetres_ids=perimetres_ids if perimetres_ids is not None else [],
        modifie_par=modifie_par,
    )
    if ancien is not None:
        if role.code.upper() == RoleProjet.CHEF_PROJET:
            _principal(projet, "chef_projet", role.code, ancien, utilisateur)
        if role.code.upper() == RoleProjet.CONDUCTEUR_TRAVAUX:
            _principal(projet, "conducteur_travaux", role.code, ancien, utilisateur)
        from apps.chantier.services.signatures import reevaluer_journaux_du_projet

        reevaluer_journaux_du_projet(projet)
    from apps.audit.services import journaliser
    from apps.core.enums import ActionAudit

    journaliser(
        action=ActionAudit.MODIFICATION,
        type_entite="Projet",
        entite_id=projet.pk,
        utilisateur_id=getattr(modifie_par, "pk", None),
        valeur_avant={"role": role.code, "titulaire": str(ancien.utilisateur_id) if ancien else None},
        valeur_apres={"evenement": "REMPLACEMENT", "role": role.code, "titulaire": str(utilisateur.pk)},
    )
    return {"ancien": ancien, "nouveau": nouveau}


def changer_chef_chantier(*, projet: Projet, utilisateur: Utilisateur, **options) -> dict:
    """« Changer le chef de chantier » : le remplacement appliqué au rôle CC."""
    return remplacer_titulaire(
        projet=projet, role_projet=RoleProjet.CHEF_CHANTIER, utilisateur=utilisateur, **options
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

    # Le périmètre et l'unicité du rôle se vérifient avant toute écriture.
    perimetres = None
    if "perimetres_ids" in donnees:
        perimetres = resoudre_perimetres(affectation.projet, donnees["perimetres_ids"])
    actif_final = donnees.get("est_actif", affectation.est_actif)
    if actif_final:
        verifier_role_unique(
            affectation.projet, affectation.utilisateur, role_final, affectation_id=affectation.pk
        )

    quitte_role = nouveau_actif is False or (
        nouveau_role and nouveau_role.upper() != (affectation.role_projet or "").upper()
    )

    champs = ["modifie_le"]
    for c in ["role_projet", "date_debut", "date_fin", "est_actif", "fonction_membre"]:
        if c in donnees:
            setattr(affectation, c, donnees[c])
            champs.append(c)
    if perimetres is not None:
        affectation.perimetres.set(perimetres)

    affectation.save(update_fields=champs)
    projet = affectation.projet
    if quitte_role:
        _recaler_principaux(projet)
        from apps.chantier.services.signatures import reevaluer_journaux_du_projet

        reevaluer_journaux_du_projet(projet)
    elif (role_final or "").upper() == RoleProjet.CHEF_PROJET and not projet.chef_projet_id:
        projet.chef_projet = affectation.utilisateur
        projet.save(update_fields=["chef_projet", "modifie_le"])
    return affectation


def _recaler_principaux(projet) -> None:
    """Le principal d'une fiche qui a quitté son rôle laisse la place au titulaire suivant."""
    for champ, code in (
        ("chef_projet", RoleProjet.CHEF_PROJET),
        ("conducteur_travaux", RoleProjet.CONDUCTEUR_TRAVAUX),
    ):
        actuel = getattr(projet, f"{champ}_id")
        titulaires = list(titulaires_en_cours(projet, code).order_by("cree_le"))
        if actuel and any(a.utilisateur_id == actuel for a in titulaires):
            continue
        suivant = titulaires[0].utilisateur if titulaires else None
        if (suivant.pk if suivant else None) != actuel:
            setattr(projet, champ, suivant)
            projet.save(update_fields=[champ, "modifie_le"])


def revoquer_affectation_projet(
    *,
    affectation: AffectationProjet,
    suppression_physique: bool = False,
    modifie_par: Utilisateur | None = None,
):
    """Révoque (soft-delete est_actif=False) ou supprime une affectation."""
    projet = affectation.projet

    if suppression_physique:
        affectation.supprimer_definitivement()
    else:
        affectation.est_actif = False
        affectation.save(update_fields=["est_actif", "modifie_le"])
        affectation.delete(utilisateur=modifie_par)
    _recaler_principaux(projet)
    from apps.chantier.services.signatures import reevaluer_journaux_du_projet

    reevaluer_journaux_du_projet(projet)
