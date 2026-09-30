"""Migration de données : initialisation des motifs de report par défaut et rétro-remplissage des baselines."""

from django.db import migrations


def seed_motifs_et_baselines(apps, schema_editor):
    MotifReport = apps.get_model("projets", "MotifReport")
    Projet = apps.get_model("projets", "Projet")
    Lot = apps.get_model("projets", "Lot")

    # 1. Motifs de report par défaut
    motifs_defaut = [
        {"code": "INTEMPERIES", "libelle": "Intempéries", "ordre": 1, "description": "Fortes pluies, inondations ou intempéries bloquantes."},
        {"code": "CLIENT", "libelle": "Client", "ordre": 2, "description": "Retard de validation, modification des plans ou demande client."},
        {"code": "TECHNIQUE", "libelle": "Technique", "ordre": 3, "description": "Aléa géotechnique, panne matérielle ou contrainte structurelle."},
        {"code": "ADMINISTRATIF", "libelle": "Administratif", "ordre": 4, "description": "Attente d'autorisation administrative ou permis."},
        {"code": "AUTRE", "libelle": "Autre", "ordre": 5, "description": "Autre motif exceptionnel tracé et justifié."},
    ]

    for m in motifs_defaut:
        MotifReport.objects.get_or_create(
            code=m["code"],
            defaults={
                "libelle": m["libelle"],
                "ordre": m["ordre"],
                "description": m["description"],
                "est_actif": True,
            },
        )

    # 2. Rétro-remplissage des baselines v0 pour les projets existants
    for p in Projet.objects.all():
        updated = False
        if p.date_debut_baseline is None and p.date_debut_prevue:
            p.date_debut_baseline = p.date_debut_prevue
            updated = True
        if p.date_fin_baseline is None and p.date_fin_prevue:
            p.date_fin_baseline = p.date_fin_prevue
            updated = True
        if updated:
            p.save(update_fields=["date_debut_baseline", "date_fin_baseline"])

    # 3. Rétro-remplissage des baselines v0 pour les lots existants
    for l in Lot.objects.all():
        updated = False
        if l.date_debut_baseline is None and l.date_debut_prevue:
            l.date_debut_baseline = l.date_debut_prevue
            updated = True
        if l.date_fin_baseline is None and l.date_fin_prevue:
            l.date_fin_baseline = l.date_fin_prevue
            updated = True
        if updated:
            l.save(update_fields=["date_debut_baseline", "date_fin_baseline"])


def revert_seed(apps, schema_editor):
    MotifReport = apps.get_model("projets", "MotifReport")
    MotifReport.objects.filter(code__in=["INTEMPERIES", "CLIENT", "TECHNIQUE", "ADMINISTRATIF", "AUTRE"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("projets", "0010_lot_date_debut_baseline_lot_date_fin_baseline_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_motifs_et_baselines, reverse_code=revert_seed),
    ]
