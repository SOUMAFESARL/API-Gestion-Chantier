"""Service métier pour la gestion des équipes de chantier et de leurs membres."""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

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


def verifier_affectation_collaborateur(projet, utilisateur):
    """Vérifie qu'un collaborateur est affecté au projet avant de l'ajouter dans une équipe."""
    if utilisateur and utilisateur.pk not in collaborateurs_autorises_projet(projet):
        raise serializers.ValidationError("Collaborateur non affecté à ce projet.")


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
