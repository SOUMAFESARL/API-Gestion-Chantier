"""Service métier pour la gestion du profil utilisateur post-authentification.

Gère :
- La consultation du profil enrichi (coordonnées, entreprise, habilitations par module)
- La mise à jour partielle sécurisée des coordonnées personnelles
- Le changement de mot de passe avec révocation des sessions et réémission de jetons
- Le téléversement, redimensionnement carré WebP et suppression de l'avatar
"""

import contextlib
import io
import uuid

from django.contrib.auth.password_validation import validate_password
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name
from PIL import Image
from rest_framework import status

from apps.accounts.models import Role, Utilisateur
from apps.accounts.services.authentification import duree_acces_en_secondes, emettre_jetons
from apps.accounts.services.liste_noire import revoquer_utilisateur
from apps.audit.services import journaliser
from apps.core.enums import ActionAudit, ModuleChoix, RoleGlobal
from apps.core.exceptions import ErreurMetier
from apps.tenants.models import Entreprise

__all__ = [
    "AncienMotDePasseInvalide",
    "FichierTropVolumineux",
    "FormatFichierInvalide",
    "NouveauMotDePasseIdentique",
    "changer_mot_de_passe",
    "enregistrer_avatar",
    "mettre_a_jour_profil",
    "obtenir_donnees_profil",
    "supprimer_avatar",
]

TAILLE_MAX_AVATAR = 10 * 1024 * 1024  # 10 Mo (autorise les photos HD et logos, compressés en 256x256 WebP)
DIMENSION_AVATAR = (256, 256)
FORMATS_ACCEPTES = {"JPEG", "JPG", "PNG", "WEBP"}


class AncienMotDePasseInvalide(ErreurMetier):
    status_code = status.HTTP_400_BAD_REQUEST
    code_metier = "ancien_mot_de_passe_incorrect"
    default_detail = _("L'ancien mot de passe est incorrect.")


class NouveauMotDePasseIdentique(ErreurMetier):
    status_code = status.HTTP_400_BAD_REQUEST
    code_metier = "mot_de_passe_identique"
    default_detail = _("Le nouveau mot de passe doit être différent de l'ancien.")


class FichierTropVolumineux(ErreurMetier):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code_metier = "fichier_trop_volumineux"
    default_detail = _("Le fichier dépasse la taille maximale autorisée de 10 Mo.")


class FormatFichierInvalide(ErreurMetier):
    status_code = status.HTTP_400_BAD_REQUEST
    code_metier = "format_fichier_invalide"
    default_detail = _("Le fichier doit être une image valide (JPEG, PNG ou WebP).")


def obtenir_donnees_profil(utilisateur: Utilisateur, request=None) -> dict:
    """Construit la représentation complète et sécurisée du profil utilisateur."""
    schema_name = getattr(connection, "schema_name", "public")

    # 1. URL de l'avatar
    avatar_url = None
    if utilisateur.avatar and hasattr(utilisateur.avatar, "url"):
        try:
            avatar_url = (
                request.build_absolute_uri(utilisateur.avatar.url)
                if request
                else utilisateur.avatar.url
            )
        except Exception:
            avatar_url = utilisateur.avatar.url

    # 2. Informations de l'entreprise (tenant)
    entreprise_info = None
    tenant = getattr(connection, "tenant", None)
    if tenant and getattr(tenant, "schema_name", "") != get_public_schema_name():
        entreprise = (
            tenant
            if hasattr(tenant, "pk")
            else Entreprise.objects.filter(schema_name=tenant.schema_name).first()
        )
        if entreprise:
            logo_url = None
            if getattr(entreprise, "logo", None) and hasattr(entreprise.logo, "url"):
                try:
                    logo_url = (
                        request.build_absolute_uri(entreprise.logo.url)
                        if request
                        else entreprise.logo.url
                    )
                except Exception:
                    logo_url = entreprise.logo.url

            entreprise_info = {
                "id": str(entreprise.pk),
                "raison_sociale": getattr(entreprise, "raison_sociale", ""),
                "schema_name": entreprise.schema_name,
                "logo_url": logo_url,
            }

    # 3. Matrice des habilitations par module
    habilitations = {}
    role = (
        utilisateur.role_personnalise or Role.objects.filter(code=utilisateur.role_global).first()
    )
    if role:
        for perm in role.permissions_modules.all():
            habilitations[perm.module] = {
                "libelle": perm.get_niveau_display(),
                "niveau": perm.niveau,
            }

    # Accès de secours pour DG / Admin ou modules non configurés
    est_plein_droit = utilisateur.is_dg or utilisateur.role_global == RoleGlobal.ADMIN
    for mod_code, _mod_label in ModuleChoix.choices:
        if mod_code not in habilitations:
            habilitations[mod_code] = {
                "libelle": "Validation" if est_plein_droit else "Lecture",
                "niveau": 3 if est_plein_droit else 1,
            }

    # 4. Rôle personnalisé
    role_perso_info = None
    if utilisateur.role_personnalise:
        role_perso_info = {
            "id": str(utilisateur.role_personnalise.id),
            "code": utilisateur.role_personnalise.code,
            "libelle": utilisateur.role_personnalise.libelle,
        }

    return {
        "id": str(utilisateur.pk),
        "email": utilisateur.email,
        "nom": utilisateur.nom,
        "prenom": utilisateur.prenom,
        "nom_complet": utilisateur.nom_complet,
        "telephone": utilisateur.telephone,
        "avatar_url": avatar_url,
        "initiales": utilisateur.initiales,
        "role_global": utilisateur.role_global,
        "role_libelle": utilisateur.get_role_global_display(),
        "role_personnalise": role_perso_info,
        "is_dg": utilisateur.is_dg,
        "is_owner": utilisateur.is_owner,
        "statut": utilisateur.statut,
        "double_authentification_active": utilisateur.double_authentification,
        "doit_changer_mot_de_passe": utilisateur.doit_changer_mot_de_passe,
        "langue": utilisateur.langue,
        "schema": schema_name,
        "entreprise": entreprise_info,
        "habilitations": habilitations,
        "derniere_connexion": utilisateur.last_login.isoformat()
        if utilisateur.last_login
        else None,
        "cree_le": utilisateur.cree_le.isoformat() if utilisateur.cree_le else None,
        "modifie_le": utilisateur.modifie_le.isoformat() if utilisateur.modifie_le else None,
    }


@transaction.atomic
def mettre_a_jour_profil(
    utilisateur: Utilisateur,
    donnees: dict,
    ip: str | None = None,
    appareil: str = "",
) -> Utilisateur:
    """Met à jour les informations modifiables du profil."""
    champs_autorises = {"nom", "prenom", "telephone", "langue"}
    champs_modifies = []
    valeur_avant = {}
    valeur_apres = {}

    for champ in champs_autorises:
        if champ in donnees:
            anc = getattr(utilisateur, champ)
            nouv = donnees[champ]
            if anc != nouv:
                valeur_avant[champ] = anc
                valeur_apres[champ] = nouv
                setattr(utilisateur, champ, nouv)
                champs_modifies.append(champ)

    if champs_modifies:
        champs_modifies.append("modifie_le")
        utilisateur.save(update_fields=champs_modifies)

        journaliser(
            action=ActionAudit.MODIFICATION,
            type_entite="utilisateur",
            entite_id=utilisateur.pk,
            utilisateur_id=utilisateur.pk,
            valeur_avant=valeur_avant,
            valeur_apres=valeur_apres,
            adresse_ip=ip,
            appareil=appareil[:255],
        )

    return utilisateur


@transaction.atomic
def changer_mot_de_passe(
    utilisateur: Utilisateur,
    ancien_mot_de_passe: str,
    nouveau_mot_de_passe: str,
    ip: str | None = None,
    appareil: str = "",
    origine: str = "WEB",
) -> dict:
    """Change le mot de passe, révoque les sessions distantes et réémet les jetons."""
    if not utilisateur.check_password(ancien_mot_de_passe):
        raise AncienMotDePasseInvalide()

    if ancien_mot_de_passe == nouveau_mot_de_passe:
        raise NouveauMotDePasseIdentique()

    # Valide les règles Django (longueur, similarité, complexité)
    validate_password(nouveau_mot_de_passe, user=utilisateur)

    utilisateur.set_password(nouveau_mot_de_passe)
    champs = ["password", "modifie_le"]
    if utilisateur.doit_changer_mot_de_passe:
        utilisateur.doit_changer_mot_de_passe = False
        champs.append("doit_changer_mot_de_passe")
    utilisateur.save(update_fields=champs)

    # Révoque immédiatement tous les anciens tokens de l'utilisateur (époque Redis)
    revoquer_utilisateur(utilisateur.pk, ttl=24 * 3600)

    # Émet de nouveaux jetons valides avec un nouvel horodatage
    jetons = emettre_jetons(utilisateur, origine=origine)

    journaliser(
        action=ActionAudit.MODIFICATION,
        type_entite="utilisateur",
        entite_id=utilisateur.pk,
        utilisateur_id=utilisateur.pk,
        valeur_apres={"action": "changement_mot_de_passe"},
        adresse_ip=ip,
        appareil=appareil[:255],
    )

    return {
        "message": _("Votre mot de passe a été modifié avec succès."),
        "access": jetons["access"],
        "refresh": jetons["refresh"],
        "expire_dans": duree_acces_en_secondes(),
    }


def enregistrer_avatar(utilisateur: Utilisateur, fichier_image, request=None) -> str:
    """Traite, redimensionne en carré 256x256 WebP et enregistre l'avatar."""
    if fichier_image.size > TAILLE_MAX_AVATAR:
        raise FichierTropVolumineux()

    try:
        image = Image.open(fichier_image)
        format_origine = image.format
        if format_origine not in FORMATS_ACCEPTES:
            raise FormatFichierInvalide()
    except Exception as exc:
        if isinstance(exc, ErreurMetier):
            raise
        raise FormatFichierInvalide() from exc

    # Rognage centré au format carré
    largeur, hauteur = image.size
    min_side = min(largeur, hauteur)
    gauche = (largeur - min_side) // 2
    haut = (hauteur - min_side) // 2
    droite = gauche + min_side
    bas = haut + min_side
    image_carree = image.crop((gauche, haut, droite, bas))

    # Redimensionnement optimisé
    image_redimensionnee = image_carree.resize(DIMENSION_AVATAR, Image.Resampling.LANCZOS)

    # Conversion en WebP
    tampon = io.BytesIO()
    if image_redimensionnee.mode in ("RGBA", "LA") or (
        image_redimensionnee.mode == "P" and "transparency" in image_redimensionnee.info
    ):
        image_redimensionnee.save(tampon, format="WEBP", quality=85)
    else:
        image_rgb = image_redimensionnee.convert("RGB")
        image_rgb.save(tampon, format="WEBP", quality=85)
    tampon.seek(0)

    # Suppression de l'ancien avatar physique
    if utilisateur.avatar:
        with contextlib.suppress(Exception):
            utilisateur.avatar.delete(save=False)

    nom_fichier = f"avatar_{utilisateur.id}_{uuid.uuid4().hex[:8]}.webp"
    utilisateur.avatar.save(nom_fichier, ContentFile(tampon.getvalue()), save=True)

    if request:
        return request.build_absolute_uri(utilisateur.avatar.url)
    return utilisateur.avatar.url


def supprimer_avatar(utilisateur: Utilisateur) -> None:
    """Supprime le fichier d'avatar de l'utilisateur."""
    if utilisateur.avatar:
        with contextlib.suppress(Exception):
            utilisateur.avatar.delete(save=False)
        utilisateur.avatar = None
        utilisateur.save(update_fields=["avatar", "modifie_le"])
