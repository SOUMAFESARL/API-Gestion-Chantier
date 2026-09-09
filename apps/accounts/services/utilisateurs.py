from django.db import transaction

from apps.accounts.models import Utilisateur


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
