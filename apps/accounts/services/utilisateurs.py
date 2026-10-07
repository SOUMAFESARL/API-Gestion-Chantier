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

    email_original = collaborateur.email
    import uuid
    collaborateur.email_origine = email_original
    collaborateur.email = f"ancien+{uuid.uuid4()}@depart.invalide"
    collaborateur.statut = StatutUtilisateur.DESACTIVE
    collaborateur.is_active = False
    collaborateur.supprime_le = timezone.now()
    collaborateur.supprime_par = auteur
    collaborateur.save(
        update_fields=[
            "email",
            "email_origine",
            "statut",
            "is_active",
            "supprime_le",
            "supprime_par",
            "modifie_le",
        ]
    )

    # 1. Clôture de toutes les affectations actives et gestion des projets orphelins
    projets_touches = []
    try:
        from apps.projets.models import AffectationProjet, Projet

        AffectationProjet.objects.filter(
            utilisateur=collaborateur,
            est_actif=True,
        ).update(
            est_actif=False,
            modifie_le=timezone.now(),
        )

        projets_chef = list(Projet.objects.filter(chef_projet=collaborateur))
        projets_conducteur = list(Projet.objects.filter(conducteur_travaux=collaborateur))
        projets_touches_ids = {p.id for p in projets_chef} | {p.id for p in projets_conducteur}
        projets_touches = list(Projet.objects.filter(id__in=projets_touches_ids))

        if projets_touches:
            Projet.objects.filter(id__in=projets_touches_ids).update(
                sans_chef_projet=True,
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

    # 2. Purge de la table RegistreEmail (schéma public)
    try:
        from django_tenants.utils import schema_context
        from apps.tenants.models import RegistreEmail

        with schema_context("public"):
            RegistreEmail.objects.filter(email__iexact=email_original.strip().lower()).delete()
    except Exception as exc:
        logger.warning("Erreur lors de la purge de RegistreEmail: %s", exc)

    # 3. Révocation des invitations en attente pour cet email
    Invitation.objects.filter(
        email__in=[email_original.lower(), collaborateur.email.lower()],
        statut=Invitation.Statut.ENVOYEE,
    ).update(
        statut=Invitation.Statut.REVOQUEE,
        modifie_le=timezone.now(),
    )

    # 4. Révocation de toutes ses sessions actives (liste noire des jetons JWT)
    try:
        from apps.accounts.services.liste_noire import revoquer_utilisateur

        revoquer_utilisateur(collaborateur.pk, ttl=86400)
    except Exception as exc:
        logger.warning(
            "Erreur lors de la révocation de session pour l'utilisateur %s: %s",
            collaborateur.id,
            exc,
        )

    # 5. Alerte par e-mail au DG si des projets sont devenus orphelins (on_commit)
    if projets_touches:
        dg = (
            Utilisateur.objects.filter(
                role_global=RoleGlobal.DIRECTEUR_GENERAL, supprime_le__isnull=True
            ).first()
            or Utilisateur.objects.filter(is_owner=True, supprime_le__isnull=True).first()
        )
        if dg and dg.email:
            dg_email = dg.email
            infos_projets = [(p.reference, p.nom) for p in projets_touches]
            nom_collab = f"{collaborateur.prenom} {collaborateur.nom}".strip() or email_original

            def _envoyer_alerte():
                from django.core.mail import send_mail

                lignes = "\n".join([f"- {ref} : {nom}" for ref, nom in infos_projets])
                sujet = "Alerte : Projets orphelins suite au départ d'un collaborateur"
                message = (
                    f"Bonjour,\n\n"
                    f"Suite au départ de {nom_collab}, les projets suivants se retrouvent sans chef de projet ou conducteur :\n"
                    f"{lignes}\n\n"
                    f"Veuillez réaffecter de nouveaux responsables."
                )
                send_mail(
                    subject=sujet,
                    message=message,
                    from_email=None,
                    recipient_list=[dg_email],
                    fail_silently=True,
                )

            transaction.on_commit(_envoyer_alerte)

    return {
        "id": str(collaborateur.pk),
        "email": collaborateur.email,
        "email_origine": email_original,
        "statut": collaborateur.statut,
        "message": str(
            _(
                "Collaborateur retiré de la plateforme avec succès. Ses accès ont été révoqués et ses affectations de chantiers clôturées."
            )
        ),
    }

