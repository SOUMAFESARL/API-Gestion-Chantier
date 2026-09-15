"""Service de gestion des invitations — workflow T1 & MLD §5.2."""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import connection, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import status

from apps.accounts.models import Invitation, Utilisateur
from apps.accounts.services.authentification import emettre_jetons, profil_de_connexion
from apps.billing.services.quota import verifier_quota_avant_invitation
from apps.core.emails import envoyer
from apps.core.enums import StatutUtilisateur
from apps.core.exceptions import ErreurMetier

logger = logging.getLogger(__name__)

DUREE_INVITATION = timedelta(hours=72)

__all__ = [
    "DUREE_INVITATION",
    "JetonInvitationExpire",
    "accepter_invitation",
    "creer_invitation",
    "obtenir_invitation_par_jeton",
]


class JetonInvitationExpire(ErreurMetier):
    """Lien d'invitation expiré, consommé ou invalide — 410 GONE."""

    status_code = status.HTTP_410_GONE
    code_metier = "jeton_expire"
    default_detail = _("Cette invitation n'est plus valable ou a déjà été utilisée.")


@transaction.atomic
def creer_invitation(
    email: str,
    role_propose: str,
    nom: str = "",
    emetteur: Utilisateur | None = None,
    hote: str | None = None,
    nom_projet: str | None = None,
    projet_id: str | uuid.UUID | None = None,
) -> Invitation:
    """Crée une invitation avec son empreinte SHA-256 (MLD §5.2) et expédie le lien.

    **Le quota du plan est vérifié d'abord.** Refuser après création laisserait
    une ligne morte en base et un email déjà parti — et c'est le sens du critère
    de US-013 : la limite se dit au moment de l'invitation, pas au moment de
    l'activation, quand il n'y a plus personne à qui le dire.
    """
    verifier_quota_avant_invitation()

    jeton = uuid.uuid4()
    empreinte = Invitation.empreinte_de(jeton)

    invitation = Invitation.objects.create(
        email=email.strip().lower(),
        nom=nom.strip(),
        role_propose=role_propose,
        empreinte=empreinte,
        emetteur=emetteur,
        expire_le=timezone.now() + DUREE_INVITATION,
    )
    # Conservation en mémoire éphémère pour le code appelant éventuel
    invitation.jeton_clair = jeton

    # Construction du lien d'activation (avec fragment #jeton=... selon contrats R-30 / R-41)
    base_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    if not base_url:
        if hote:
            protocole = "http" if "localhost" in hote else "https"
            hote_sans_port = hote.split(":")[0]
            port = ":3000" if "localhost" in hote_sans_port else ""
            base_url = f"{protocole}://{hote_sans_port}{port}"
        else:
            base_url = "http://localhost:3000"

    if projet_id:
        lien = (
            f"{base_url}/invitation?projet_id={projet_id}&next=/projets/{projet_id}#jeton={jeton}"
        )
    else:
        lien = f"{base_url}/invitation#jeton={jeton}"

    # Le nom de l'entreprise vient du tenant courant : l'invitation est créée
    # dans son schéma, et `connection.tenant` est ce que le middleware y a posé.
    tenant = getattr(connection, "tenant", None)
    raison_sociale = getattr(tenant, "raison_sociale", "") if tenant else ""

    if nom_projet:
        sujet = f"Invitation au chantier {nom_projet} sur CCD Digital"
    elif raison_sociale:
        sujet = f"Invitation à rejoindre {raison_sociale} sur CCD Digital"
    else:
        sujet = "Invitation à rejoindre votre espace CCD Digital"

    envoyer(
        "invitation",
        sujet,
        invitation.email,
        {
            "destinataire": invitation.nom or "",
            "raison_sociale": raison_sociale,
            "nom_projet": nom_projet or "",
            "role_libelle": invitation.get_role_propose_display(),
            "lien": lien,
            "heures_validite": int(DUREE_INVITATION.total_seconds() // 3600),
        },
    )

    return invitation


@transaction.atomic
def accepter_invitation(
    cible: Invitation | str | uuid.UUID,
    *,
    nom: str = "",
    prenom: str = "",
    mot_de_passe: str = "",
    ip: str | None = None,
    appareil: str = "",
) -> dict | bool:
    """Consomme une invitation valide (MLD §5.2) et active le collaborateur.

    Supporte l'appel unitaire simple (avec seulement l'instance `Invitation`)
    et l'appel complet d'activation (avec `mot_de_passe` et données d'identité).
    """
    schema_courant = getattr(connection, "schema_name", "public")
    from django_tenants.utils import get_public_schema_name, schema_context
    public_schema = get_public_schema_name()

    if isinstance(cible, Invitation):
        invitation = cible
    else:
        empreinte = Invitation.empreinte_de(cible)
        invitation = Invitation.objects.select_for_update().filter(empreinte=empreinte).first()
        if invitation is None and schema_courant == public_schema:
            from apps.tenants.models import Entreprise

            for entreprise in Entreprise.objects.exclude(schema_name=public_schema):
                connection.set_tenant(entreprise)
                candidat = (
                    Invitation.objects.select_for_update().filter(empreinte=empreinte).first()
                )
                if candidat is not None:
                    invitation = candidat
                    break
            else:
                connection.set_schema_to_public()

    if invitation is None or not invitation.est_utilisable:
        if invitation and invitation.est_expiree:
            invitation.statut = Invitation.Statut.EXPIREE
            invitation.save(update_fields=["statut", "modifie_le"])
        if not mot_de_passe:
            return False
        raise JetonInvitationExpire()

    # Si mot de passe non fourni (cas d'appel simple/historique)
    if not mot_de_passe:
        invitation.statut = Invitation.Statut.ACCEPTEE
        invitation.utilise_le = timezone.now()
        invitation.save(update_fields=["statut", "utilise_le", "modifie_le"])
        return True

    # Validation de la complexité du mot de passe
    validate_password(mot_de_passe)

    email = invitation.email.strip().lower()
    utilisateur = Utilisateur.objects.select_for_update().filter(email__iexact=email).first()

    nom_final = (
        nom.strip() or (invitation.nom.strip() if invitation.nom else "") or email.split("@")[0]
    )
    prenom_final = prenom.strip()

    # **Le rôle activé est celui de l'invitation**, et rien d'autre.
    #
    # *Les deux branches posaient `RoleGlobal.ADMIN` en dur — « pour le moment,
    # accès à tous les modules », disait le commentaire. Ce n'était pas un
    # défaut d'affichage : toute personne invitée devenait réellement
    # administratrice de l'entreprise, quel que soit le rôle choisi à
    # l'invitation. Un conducteur de travaux obtenait la gestion des comptes,
    # et la matrice de permissions de T-029 devenait décorative.*
    #
    # Le rôle a été validé à l'émission — un admin délégué ne peut proposer ni
    # `AD` ni `DG` (T-S1-01), et `DG` n'est attribuable à personne. Le relire
    # ici est donc sûr : il ne peut pas porter plus de droits que l'invitant.
    role_active = invitation.role_propose

    if utilisateur is not None:
        utilisateur.nom = nom_final
        if prenom_final:
            utilisateur.prenom = prenom_final
        utilisateur.statut = StatutUtilisateur.ACTIF
        utilisateur.is_active = True
        utilisateur.role_global = role_active
        utilisateur.set_password(mot_de_passe)
        utilisateur.save()
    else:
        utilisateur = Utilisateur.objects.create_user(
            email=email,
            password=mot_de_passe,
            nom=nom_final,
            prenom=prenom_final,
            role_global=role_active,
            statut=StatutUtilisateur.ACTIF,
        )

    # Consommation de l'invitation
    invitation.statut = Invitation.Statut.ACCEPTEE
    invitation.utilise_le = timezone.now()
    invitation.save(update_fields=["statut", "utilise_le", "modifie_le"])

    # Activation des affectations projet éventuelles
    try:
        from django.apps import apps as registre

        AffectationProjet = registre.get_model("projets", "AffectationProjet")
        if AffectationProjet:
            AffectationProjet.objects.filter(utilisateur=utilisateur).update(est_actif=True)
    except Exception:
        pass

    # Émission des jetons JWT et constitution du profil
    tokens = emettre_jetons(utilisateur, origine="WEB")
    profil = profil_de_connexion(utilisateur)

    # Journalisation d'audit
    from apps.audit.services import journaliser
    from apps.core.enums import ActionAudit

    journaliser(
        action=ActionAudit.CONNEXION,
        type_entite="utilisateur",
        entite_id=utilisateur.pk,
        utilisateur_id=utilisateur.pk,
        valeur_apres={"origine": "WEB", "motif": "INVITATION_ACCEPTEE"},
        adresse_ip=ip,
        appareil=appareil[:255] if appareil else "",
    )

    return {
        "invitation": invitation,
        "utilisateur": utilisateur,
        "tokens": tokens,
        "profil": profil,
    }


def obtenir_invitation_par_jeton(jeton: str | uuid.UUID) -> Invitation | None:
    """Recherche une invitation via l'empreinte de son jeton en clair."""
    empreinte = Invitation.empreinte_de(jeton)
    schema_courant = getattr(connection, "schema_name", "public")
    from django_tenants.utils import get_public_schema_name, schema_context

    public_schema = get_public_schema_name()

    invitation = Invitation.objects.filter(empreinte=empreinte).first()
    if invitation is None and schema_courant == public_schema:
        from apps.tenants.models import Entreprise

        for entreprise in Entreprise.objects.exclude(schema_name=public_schema):
            connection.set_tenant(entreprise)
            candidat = Invitation.objects.filter(empreinte=empreinte).first()
            if candidat is not None:
                candidat._schema_name = entreprise.schema_name
                return candidat
        connection.set_schema_to_public()
    return invitation
