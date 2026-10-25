"""Point d'entree WSGI pour Setup Python App (cPanel/Passenger)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.cpanel")

from django.core.wsgi import get_wsgi_application

# Aucune migration ici. Passenger relance un processus après 2 à 4 minutes
# d'inactivité, et en ajoute un pour chaque requête simultanée en trop : migrer
# au démarrage faisait payer les migrations de tous les tenants, plus quatre
# commandes de synchronisation, à chacun de ces démarrages — 7 à 10 s mesurées
# en production le 25/10/2026, dont les deux tiers pour ce seul bloc.
# Les migrations passent au déploiement, par l'endpoint `maintenance/migrer-bd/`.
application = get_wsgi_application()
