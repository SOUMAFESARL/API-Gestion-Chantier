"""Service métier pour la gestion des équipes de chantier et de leurs membres."""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleProjet, StatutUtilisateur
from apps.core.exceptions import RequeteRefusee
from apps.projets.models import AffectationProjet, EquipeChantier, MembreEquipeChantier


def collaborateurs_autorises_projet(projet) -> set:
    """Les identifiants des utilisateurs autorisés à figurer dans les équipes du projet."""
    autorises = set(
        AffectationProjet.objects.filter(
            projet=projet,
            est_actif=True,
            utilisateur__supprime_le__isnull=True,
        ).values_list("utilisateur_id", flat=True)
    )
    if projet.chef_projet_id:
        autorises.add(projet.chef_projet_id)
    if projet.conducteur_travaux_id:
        autorises.add(projet.conducteur_travaux_id)
    return autorises


def message_collaborateur_non_affecte(utilisateur) -> str:
    nom = f"{utilisateur.prenom} {utilisateur.nom}".strip() or utilisateur.nom
    return (
        f"{nom} n'est pas affecté à ce projet : affectez-le d'abord au projet, "
        "puis ajoutez-le à une équipe."
    )


def verifier_affectation_collaborateur(projet, utilisateur):
    """Vérifie qu'un collaborateur est affecté au projet avant de l'ajouter dans une équipe.

    `RequeteRefusee` plutôt qu'une `ValidationError` : le message de la seconde ne parvient
    pas à l'écran, celui-ci doit dire quoi faire.
    """
    if utilisateur and utilisateur.pk not in collaborateurs_autorises_projet(projet):
        raise RequeteRefusee(message_collaborateur_non_affecte(utilisateur))


def candidats_equipes_projet(projet) -> list[dict]:
    """Les collaborateurs actifs que l'on peut proposer pour une équipe du projet.

    Ce sont exactement ceux que `verifier_affectation_collaborateur` accepte, restreints aux
    comptes actifs, avec le rôle qu'ils tiennent sur le projet et les équipes du projet dont
    ils sont déjà membres (une personne peut appartenir à plusieurs équipes).
    """
    autorises = collaborateurs_autorises_projet(projet)
    utilisateurs = {
        u.pk: u
        for u in Utilisateur.objects.filter(
            pk__in=autorises,
            is_active=True,
            statut=StatutUtilisateur.ACTIF,
            supprime_le__isnull=True,
        )
    }
    roles = dict(
        AffectationProjet.objects.filter(
            projet=projet, est_actif=True, utilisateur_id__in=utilisateurs
        ).values_list("utilisateur_id", "role_projet")
    )
    if projet.chef_projet_id in utilisateurs:
        roles.setdefault(projet.chef_projet_id, RoleProjet.CHEF_PROJET.value)
    if projet.conducteur_travaux_id in utilisateurs:
        roles.setdefault(projet.conducteur_travaux_id, RoleProjet.CONDUCTEUR_TRAVAUX.value)

    equipes_par_utilisateur: dict = {}
    participations = (
        MembreEquipeChantier.objects.filter(
            equipe__projet=projet,
            equipe__supprime_le__isnull=True,
            equipe__est_actif=True,
            utilisateur_id__in=utilisateurs,
        )
        .select_related("equipe")
        .order_by("equipe__cree_le", "equipe__id")
    )
    for membre in participations:
        equipes = equipes_par_utilisateur.setdefault(membre.utilisateur_id, {})
        equipes[membre.equipe_id] = {"id": membre.equipe_id, "nom": membre.equipe.nom}

    resultats = [
        {
            "id": u.pk,
            "nom_complet": f"{u.prenom} {u.nom}".strip() or u.nom,
            "role_projet": roles.get(u.pk, ""),
            "equipes": list(equipes_par_utilisateur.get(u.pk, {}).values()),
        }
        for u in utilisateurs.values()
    ]
    return sorted(resultats, key=lambda r: r["nom_complet"].casefold())


def synchroniser_chef_equipe(equipe: EquipeChantier):
    """Tient à jour les colonnes chef_utilisateur et chef_nom d'après ses membres."""
    chef_membre = (
        equipe.membres.filter(
            fonction="CHEF_EQUIPE",
            supprime_le__isnull=True,
        )
        .select_related("utilisateur")
        .first()
    )

    if chef_membre:
        equipe.chef_utilisateur = chef_membre.utilisateur
        if chef_membre.utilisateur:
            equipe.chef_nom = (
                f"{chef_membre.utilisateur.prenom} {chef_membre.utilisateur.nom}".strip()
            )
        else:
            equipe.chef_nom = chef_membre.nom or ""
    else:
        equipe.chef_utilisateur = None
        equipe.chef_nom = ""

    equipe.save(update_fields=["chef_utilisateur", "chef_nom"])


@transaction.atomic
def ajouter_membre_equipe(
    equipe: EquipeChantier,
    *,
    utilisateur=None,
    prenom: str = "",
    nom: str = "",
    role: str = "OUVRIER",
    createur=None,
) -> MembreEquipeChantier:
    """Ajoute un membre dans une équipe avec vérification des règles métier."""
    membres_actifs = equipe.membres.filter(supprime_le__isnull=True)
    if membres_actifs.count() >= 100:
        raise serializers.ValidationError("Maximum 100 personnes, chef compris.")

    if utilisateur:
        verifier_affectation_collaborateur(equipe.projet, utilisateur)
        if membres_actifs.filter(utilisateur=utilisateur).exists():
            raise serializers.ValidationError("Une personne ne peut apparaître deux fois.")
    else:
        nom_complet = f"{prenom.strip()} {nom.strip()}".strip().casefold()
        for m in membres_actifs:
            m_nom = (
                f"{m.prenom.strip()} {m.nom.strip()}".strip().casefold()
                if not m.utilisateur
                else ""
            )
            if m_nom and m_nom == nom_complet:
                raise serializers.ValidationError("Une personne ne peut apparaître deux fois.")

    if role == "CHEF_EQUIPE":
        ancien_chef = membres_actifs.filter(fonction="CHEF_EQUIPE").first()
        if ancien_chef:
            ancien_chef.fonction = "OUVRIER_QUALIFIE"
            ancien_chef.save(update_fields=["fonction"])

    membre = MembreEquipeChantier.objects.create(
        equipe=equipe,
        utilisateur=utilisateur,
        prenom=prenom.strip(),
        nom=nom.strip(),
        fonction=role,
        cree_par=createur,
    )

    synchroniser_chef_equipe(equipe)
    return membre


@transaction.atomic
def modifier_role_membre(membre: MembreEquipeChantier, nouveau_role: str) -> MembreEquipeChantier:
    """Modifie le rôle d'un membre. Si nommé chef, rétrograde l'ancien en OUVRIER_QUALIFIE."""
    if membre.fonction == nouveau_role:
        return membre

    equipe = membre.equipe
    if nouveau_role == "CHEF_EQUIPE":
        ancien_chef = (
            equipe.membres.filter(
                fonction="CHEF_EQUIPE",
                supprime_le__isnull=True,
            )
            .exclude(pk=membre.pk)
            .first()
        )
        if ancien_chef:
            ancien_chef.fonction = "OUVRIER_QUALIFIE"
            ancien_chef.save(update_fields=["fonction"])

    membre.fonction = nouveau_role
    membre.save(update_fields=["fonction"])

    synchroniser_chef_equipe(equipe)
    return membre


@transaction.atomic
def retirer_membre_equipe(membre: MembreEquipeChantier) -> None:
    """Supprime logiquement un membre d'une équipe et met à jour le chef si nécessaire."""
    equipe = membre.equipe
    membre.supprime_le = timezone.now()
    membre.save(update_fields=["supprime_le"])
    synchroniser_chef_equipe(equipe)
