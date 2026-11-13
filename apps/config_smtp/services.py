from email.utils import formataddr

from django.core.mail import EmailMultiAlternatives, send_mail as django_send_mail
from django.core.mail.backends.smtp import EmailBackend

from .models import ConfigSMTP


def send_mail(subject, message, from_email, recipient_list, *, fail_silently=False, html_message=None):
    """Use the active database configuration, falling back to Django mail settings."""
    config = ConfigSMTP.objects.filter(est_active=True, supprime_le__isnull=True).first()
    if config is None:
        return django_send_mail(subject, message, from_email, recipient_list, fail_silently=fail_silently, html_message=html_message)

    connection = EmailBackend(
        alias='config_smtp',
        host=config.hote,
        port=config.port,
        username=config.utilisateur,
        password=config.mot_de_passe,
        use_tls=config.utiliser_tls,
        use_ssl=config.utiliser_ssl,
        timeout=config.delai_connexion,
        fail_silently=fail_silently,
    )
    sender = formataddr((config.nom_expediteur, config.email_expediteur))
    email = EmailMultiAlternatives(subject=subject, body=message, from_email=sender, to=recipient_list)
    if html_message:
        email.attach_alternative(html_message, 'text/html')
    with connection:
        sent = connection.send_messages([email])
    if sent != 1 and not fail_silently:
        raise RuntimeError("Le serveur SMTP n'a pas accepté le message.")
    return sent
