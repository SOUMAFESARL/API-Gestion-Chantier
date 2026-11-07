#!/usr/bin/env python
"""Utilitaire en ligne de commande de Django.

Une base vide se monte par `python manage.py monter_base` (migrations, contrôle de l'isolation,
ensemencement).
"""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django est introuvable. L'environnement virtuel est-il activé ? "
            "(backend/.venv/Scripts/activate)"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
