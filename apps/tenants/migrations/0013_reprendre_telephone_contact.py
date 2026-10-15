import re

from django.db import migrations

E164_REGEX = re.compile(r"^\+[1-9][0-9]{7,14}$")
SEPARATEURS_REGEX = re.compile(r"[\s().\-/]")


def _normaliser_telephone(valeur: str) -> str:
    """Normalise un numéro de téléphone sans inventer d'indicatif."""
    if not valeur:
        return ""
    valeur = SEPARATEURS_REGEX.sub("", valeur.strip())
    if valeur.startswith("00"):
        valeur = "+" + valeur[2:]
    return valeur


def reprendre_telephone_contact(apps, schema_editor):
    Entreprise = apps.get_model("tenants", "Entreprise")
    TelephoneEntreprise = apps.get_model("tenants", "TelephoneEntreprise")

    repris = 0
    illisibles = 0

    for ent in Entreprise.objects.all():
        brut = ent.telephone_contact
        if not brut:
            continue
        normalise = _normaliser_telephone(brut)
        if E164_REGEX.match(normalise):
            TelephoneEntreprise.objects.create(
                entreprise=ent,
                libelle="STANDARD",
                numero=normalise,
                est_principal=True,
                ordre=0,
            )
            if ent.telephone_contact != normalise:
                ent.telephone_contact = normalise
                ent.save(update_fields=["telephone_contact"])
            repris += 1
        else:
            illisibles += 1

    print(f"{repris} numéros repris, {illisibles} illisibles laissés tels quels")


def annuler_reprise(apps, schema_editor):
    TelephoneEntreprise = apps.get_model("tenants", "TelephoneEntreprise")
    TelephoneEntreprise.objects.filter(
        libelle="STANDARD",
        est_principal=True,
        ordre=0,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0012_telephoneentreprise"),
    ]

    operations = [
        migrations.RunPython(reprendre_telephone_contact, reverse_code=annuler_reprise),
    ]
