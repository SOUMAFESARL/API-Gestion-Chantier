"""Application « notifications »

Notifications in-app, email et push, et leurs préférences.

Tables       : d'entreprise (`ModeleEntreprise`)
Module CDC   : Transverse
Entités MCD  : Notification, PreferenceNotification
MLD          : 04_Conception/architecture_base_donnees/MLD_CCD_Digital.md §5.5
"""

from apps.notifications.models.notification import Notification
from apps.notifications.models.preference_notification import PreferenceNotification

__all__ = ["Notification", "PreferenceNotification"]
