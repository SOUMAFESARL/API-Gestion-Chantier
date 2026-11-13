from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.entreprises.models import Entreprise


def activer_demande(demande):
    """Called inside a transaction with the registration request locked."""
    if demande.entreprise_id:
        return demande.entreprise
    try:
        with transaction.atomic():
            entreprise = Entreprise.objects.create(
                slug=demande.slug_reserve,
                raison_sociale=demande.raison_sociale,
                pays=demande.pays,
                email_contact=demande.email,
                statut='ESSAI',
            )
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.__cause__, 'diag', None), 'constraint_name', '')
        if constraint in {'entreprise_slug_key', 'uq_entreprise_email_contact'}:
            raise ValidationError('Une entreprise utilise déjà cet email ou cet identifiant.') from exc
        raise
    demande.entreprise = entreprise
    demande.statut = 'ACTIVEE'
    demande.decision_le = timezone.now()
    demande.save()
    return entreprise
