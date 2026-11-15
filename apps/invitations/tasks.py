from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(name="invitations.send_invitation_email")
def send_invitation_email(invitation_id: str, raw_token: str) -> None:
    """
    Send an invitation email to the invitee.

    The raw token is passed as a task argument so it never needs to be stored
    in the database (only the hash is persisted).  In production, raw_token is
    obtained from the create endpoint and must be treated as a secret.

    Dev uses the console email backend; configure EMAIL_BACKEND in settings for
    production (e.g. django.core.mail.backends.smtp.EmailBackend).
    """
    from apps.invitations.models import Invitation  # local import avoids circular deps

    try:
        invitation = Invitation.objects.select_related("tenant").get(id=invitation_id)
    except Invitation.DoesNotExist:
        return  # Already deleted or ID wrong — nothing to send.

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    accept_link = f"{frontend_url}/accept-invite?token={raw_token}"
    subject = f"You're invited to join {invitation.tenant.name}"
    body = (
        f"Hello,\n\n"
        f"You have been invited to join {invitation.tenant.name} as {invitation.role}.\n\n"
        f"Accept your invitation here:\n{accept_link}\n\n"
        f"This invitation expires in {getattr(settings, 'INVITATION_EXPIRY_DAYS', 7)} days.\n\n"
        f"If you did not expect this, you can ignore this email.\n"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    send_mail(subject, body, from_email, [invitation.email], fail_silently=False)
