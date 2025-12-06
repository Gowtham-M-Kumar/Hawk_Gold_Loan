import random
from datetime import timedelta

from django.utils import timezone

from ..models import OTPRequest


class OTPService:
    def __init__(self, user, purpose, phone):
        self.user = user
        self.purpose = purpose
        self.phone = phone

    def generate(self, metadata=None):
        code = ''.join(random.choices('0123456789', k=6))
        expiration = timezone.now() + timedelta(minutes=5)
        otp = OTPRequest.objects.create(
            user=self.user,
            purpose=self.purpose,
            target_phone=self.phone,
            code=code,
            expires_at=expiration,
            metadata=metadata or {},
        )
        # In production integrate with SMS gateway. For now log to console.
        print(f'OTP for {self.user}: {code}')  # noqa: T201 debug output only
        return otp

