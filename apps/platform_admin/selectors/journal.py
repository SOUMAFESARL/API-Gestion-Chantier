"""Sélecteurs pour le journal d'audit de la plateforme."""

from django_tenants.utils import get_public_schema_name, schema_context

from apps.platform_admin.models import JournalPlateforme


def journal_plateforme(
    *,
    du=None,
    au=None,
    utilisateur_id=None,
    entreprise_id=None,
    action=None,
):
    """Le journal filtré, du plus récent au plus ancien — un QuerySet, non évalué."""
    with schema_context(get_public_schema_name()):
        qs = JournalPlateforme.objects.all()

        if du is not None:
            qs = qs.filter(horodatage__date__gte=du)
        if au is not None:
            qs = qs.filter(horodatage__date__lte=au)
        if utilisateur_id is not None:
            qs = qs.filter(utilisateur_id=utilisateur_id)
        if entreprise_id is not None:
            qs = qs.filter(entreprise_id=entreprise_id)
        if action:
            qs = qs.filter(action=action)

        return qs.order_by("-horodatage", "-id")


def codes_actions_journal() -> list[str]:
    """Retourne la liste triée des codes d'action distincts présents au journal."""
    with schema_context(get_public_schema_name()):
        return sorted(
            set(JournalPlateforme.objects.values_list("action", flat=True).distinct())
        )
