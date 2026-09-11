"""Point d'entree WSGI pour Setup Python App (cPanel/Passenger)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.cpanel")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
