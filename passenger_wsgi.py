"""Point d'entree WSGI pour Setup Python App (cPanel/Passenger)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.cpanel")

import logging
from django.core.wsgi import get_wsgi_application  # noqa: E402

logger = logging.getLogger("passenger_wsgi")

# Exécution automatique des migrations (django-tenants) au démarrage Passenger
def _auto_migrate():
    lock_path = Path(__file__).resolve().parent / "tmp" / "migration.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = None
    try:
        try:
            import fcntl
            lock_file = open(lock_path, "w")
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, AttributeError):
            lock_file = None

        import django
        django.setup()
        from django.core.management import call_command
        call_command("migrate_schemas", interactive=False)

        if lock_file:
            try:
                import fcntl
                fcntl.flock(lock_file, fcntl.LOCK_UN)
                lock_file.close()
            except Exception:
                pass
    except (BlockingIOError, OSError):
        # Un autre processus Passenger est déjà en train de migrer
        pass
    except Exception as exc:
        logger.error("Erreur lors de l'auto-migration Passenger : %s", exc)

_auto_migrate()

application = get_wsgi_application()
