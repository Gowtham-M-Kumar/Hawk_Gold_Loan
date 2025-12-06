# gold_loan/models.py
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, getcontext

from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

User = get_user_model()
getcontext().prec = 28



def quantize_money(d: Decimal) -> Decimal:
    if d is None:
        d = Decimal('0.00')
    return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AppAccess(TimeStampedModel):
    GOLD_LOAN_APP = 'gold_loan'
    APP_CHOICES = [
        (GOLD_LOAN_APP, 'Gold Loan'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='app_accesses')
    app_label = models.CharField(max_length=100, choices=APP_CHOICES)

    class Meta:
        unique_together = ('user', 'app_label')
        verbose_name = 'App Access'
        verbose_name_plural = 'App Access'

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} -> {self.get_app_label_display()}'


class Customer(TimeStampedModel):
    name = models.CharField(max_length=255)
    alternate_name = models.CharField(max_length=255, blank=True)
    mobile_number = models.CharField(max_length=15)
    alternate_number = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField()
    aadhaar_number = models.CharField(max_length=16)
    company = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to='customers/photos/', blank=True, null=True)

    def __str__(self):
        return f'{self.name} ({self.mobile_number})'


class CustomerDocument(TimeStampedModel):
    DOCUMENT_TYPES = [
        ('aadhaar', 'Aadhaar'),
        ('pan', 'PAN'),
        ('passport', 'Passport'),
        ('other', 'Other'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    file = models.FileField(upload_to='customers/documents/')

    def __str__(self):
        return f'{self.customer.name} - {self.get_document_type_display()}'


class OTPRequest(TimeStampedModel):
    PURPOSE_LOAN_CREATE = 'loan_create'
    PURPOSE_LOAN_CLOSE = 'loan_close'
    PURPOSE_CHOICES = [
        (PURPOSE_LOAN_CREATE, 'Loan Creation'),
        (PURPOSE_LOAN_CLOSE, 'Loan Closure'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_requests')
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=50, choices=PURPOSE_CHOICES)
    target_phone = models.CharField(max_length=20)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ('-created_at',)

    @property
    def is_valid(self):
        if self.verified_at:
            return False
        return timezone.now() <= self.expires_at

    def verify(self, code: str) -> bool:
        if not self.is_valid:
            return False
        if self.code != code:
            return False
        self.verified_at = timezone.now()
        self.save(update_fields=['verified_at'])
        return True


INTEREST_YEAR_DAYS = Decimal("365")


class Loan(TimeStampedModel):
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_CLOSED, 'Closed'),
    ]

    lot_no = models.CharField(max_length=50)
    loan_number = models.CharField(max_length=50, unique=True, editable=False)

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='loans')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_loans')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    total_actual_grams = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    approved_net_grams = models.DecimalField(max_digits=10, decimal_places=2)
    price_per_gram = models.DecimalField(max_digits=10, decimal_places=2)

    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)  # annual interest %

    # --- ADD BACK: interest_period_days (safe default to satisfy existing DB schema) ---
    interest_period_days = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Number of days used for preview/period interest (kept for backward compatibility)."
    )
    # --- end added field ---

    # PRINCIPAL
    total_loan_amount = models.DecimalField(max_digits=12, decimal_places=2)

    # INTEREST FIELDS
    pending_interest = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_interest_accrued = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    last_interest_calculated_date = models.DateField(blank=True, null=True)

    notes = models.TextField(blank=True)
    previous_loan = models.ForeignKey(
        'self', on_delete=models.SET_NULL, related_name='renewals', blank=True, null=True
    )

    pledge_bank_name = models.CharField(max_length=255, blank=True)
    pledge_bank_address = models.TextField(blank=True)
    pledge_receipt_no = models.CharField(max_length=100, blank=True)

    # --- REMOVED (NOT NEEDED SINCE WE FIXED TO 365 DAYS) ---
    # interest_period_days = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'Loan {self.loan_number}'

    # ================================================================
    # SAVE
    # ================================================================
    def save(self, *args, **kwargs):
        if not self.loan_number:
            self.loan_number = self._generate_loan_number()

        # principal auto-calculated
        self.total_loan_amount = self._calculate_total_amount()

        # initialize interest start date
        if not self.last_interest_calculated_date:
            self.last_interest_calculated_date = timezone.localdate()

        super().save(*args, **kwargs)

    def _generate_loan_number(self):
        today_part = timezone.now().strftime('%Y%m%d')
        short_uuid = uuid.uuid4().hex[:8].upper()
        return f'GL-{today_part}-{short_uuid}'

    def _calculate_total_amount(self):
        price = self.price_per_gram or Decimal('0')
        grams = self.approved_net_grams or Decimal('0')
        return quantize_money(price * grams)

    # ================================================================
    # DAILY INTEREST (FIXED 365 DAY FINANCIAL YEAR)
    # ================================================================
    def daily_interest_amount(self) -> Decimal:
        """
        Formula: (Principal * Annual Rate) / (365 * 100)
        Always uses 365 days as fixed period.
        """
        principal = Decimal(self.total_loan_amount)
        rate = Decimal(self.interest_rate)

        if principal <= 0 or rate <= 0:
            return Decimal("0.00")

        daily = (principal * rate) / (INTEREST_YEAR_DAYS * Decimal("100"))
        return quantize_money(daily)

    # ================================================================
    # INTEREST BETWEEN TWO DATES
    # ================================================================
    def interest_between_dates(self, from_date: date, to_date: date) -> Decimal:
        if from_date is None:
            from_date = self.created_at.date()

        if to_date is None:
            to_date = timezone.localdate()

        days = max((to_date - from_date).days, 0)

        if days <= 0:
            return Decimal("0.00")

        daily = self.daily_interest_amount()
        return quantize_money(daily * Decimal(days))

    # ================================================================
    # ACCRUE INTEREST UP TO A DATE
    # ================================================================
    def accrue_interest_up_to(self, up_to_date: date | None = None) -> Decimal:
        if up_to_date is None:
            up_to_date = timezone.localdate()

        start_date = self.last_interest_calculated_date or self.created_at.date()

        if start_date >= up_to_date:
            return Decimal("0.00")

        new_interest = self.interest_between_dates(start_date, up_to_date)

        if new_interest > 0:
            self.pending_interest = quantize_money(self.pending_interest + new_interest)
            self.total_interest_accrued = quantize_money(self.total_interest_accrued + new_interest)
            self.last_interest_calculated_date = up_to_date

            self.save(update_fields=[
                "pending_interest",
                "total_interest_accrued",
                "last_interest_calculated_date",
                "updated_at"
            ])

        return quantize_money(new_interest)

    # ================================================================
    # PAYMENT HELPERS
    # ================================================================
    def total_interest_paid(self) -> Decimal:
        total = self.payments.aggregate(total=Sum("interest_component"))["total"]
        return quantize_money(total or Decimal("0.00"))

    def total_principal_paid(self) -> Decimal:
        total = self.payments.aggregate(total=Sum("principal_component"))["total"]
        return quantize_money(total or Decimal("0.00"))

    def principal_remaining(self) -> Decimal:
        remaining = self.total_loan_amount - self.total_principal_paid()
        return max(quantize_money(remaining), Decimal("0.00"))

    @property
    def remaining_due(self):
        return quantize_money(self.principal_remaining() + self.pending_interest)

    # ================================================================
    # APPLY PAYMENT
    # ================================================================
    def apply_payment(self, amount: Decimal, payment_date: date | None = None) -> dict:
        if payment_date is None:
            payment_date = timezone.localdate()

        amount = quantize_money(amount)

        if amount <= 0:
            return {
                "interest_deducted": Decimal("0.00"),
                "principal_deducted": Decimal("0.00"),
                "remaining_principal": self.principal_remaining(),
                "remaining_interest": self.pending_interest,
            }

        # 1) First accrue interest
        self.accrue_interest_up_to(payment_date)

        # 2) Apply amount to interest
        interest_deducted = min(self.pending_interest, amount)
        amount -= interest_deducted

        # 3) Apply remaining to principal
        principal_deducted = Decimal("0.00")
        if amount > 0:
            principal_deducted = min(self.principal_remaining(), amount)

        # Update interest
        self.pending_interest = quantize_money(self.pending_interest - interest_deducted)

        # Update principal
        if principal_deducted > 0:
            new_principal = Decimal(self.total_loan_amount) - principal_deducted
            self.total_loan_amount = quantize_money(max(new_principal, Decimal("0.00")))

        self.save(update_fields=["pending_interest", "total_loan_amount", "updated_at"])

        return {
            "interest_deducted": quantize_money(interest_deducted),
            "principal_deducted": quantize_money(principal_deducted),
            "remaining_principal": self.principal_remaining(),
            "remaining_interest": quantize_money(self.pending_interest),
        }



class LoanDocument(TimeStampedModel):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=100)
    file = models.FileField(upload_to='loan/documents/')

    def __str__(self):
        return f'{self.loan.loan_number} - {self.document_type}'


class LoanGoldItem(TimeStampedModel):
    CARAT_CHOICES = [
        ('18', '18K'),
        ('20', '20K'),
        ('22', '22K'),
        ('24', '24K'),
    ]

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='gold_items')
    item_name = models.CharField(max_length=255)
    carat_value = models.CharField(max_length=3, choices=CARAT_CHOICES)
    grams = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    description = models.TextField(blank=True)

    def __str__(self):
        return f'{self.item_name} ({self.carat_value}K)'


class LoanGoldItemImage(TimeStampedModel):
    gold_item = models.ForeignKey(LoanGoldItem, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='loan/items/')

    def __str__(self):
        return f'Image for {self.gold_item.item_name}'


class LoanPayment(TimeStampedModel):
    MEDIUM_CASH = 'cash'
    MEDIUM_UPI = 'upi'
    MEDIUM_BANK = 'bank'

    MEDIUM_CHOICES = [
        (MEDIUM_CASH, 'Cash'),
        (MEDIUM_UPI, 'UPI'),
        (MEDIUM_BANK, 'Bank Transfer'),
    ]

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='payments')
    payment_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    medium = models.CharField(max_length=20, choices=MEDIUM_CHOICES, blank=True)
    notes = models.TextField(blank=True)
    interest_component = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    principal_component = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    receipt_number = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ('-payment_date', '-created_at')

    def save(self, *args, **kwargs):
        """
        We allow views to compute and set interest_component/principal_component before save.
        For backward compatibility, if both components are zero, compute allocation using loan.interest_pending().
        """
        # ensure quantization
        self.amount = quantize_money(self.amount)
        self.interest_component = quantize_money(self.interest_component)
        self.principal_component = quantize_money(self.principal_component)

        if not self.receipt_number:
            self.receipt_number = self._generate_receipt()

        # If nothing set, fallback to computing allocation (safe fallback)
        if self.interest_component == Decimal('0.00') and self.principal_component == Decimal('0.00'):
            # compute interest pending up to payment_date but DO NOT persist accrual here
            interest_pending = self.loan.interest_pending(self.payment_date)
            interest_component = min(self.amount, interest_pending)
            principal_component = quantize_money(self.amount - interest_component)
            self.interest_component = quantize_money(interest_component)
            self.principal_component = quantize_money(principal_component)

        super().save(*args, **kwargs)

    def _generate_receipt(self) -> str:
        return f'PAY-{uuid.uuid4().hex[:10].upper()}'

    def __str__(self):
        return f'Payment {self.receipt_number} - {self.loan.loan_number}'


class LoanAmountLog(TimeStampedModel):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='amount_logs')
    log_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    medium = models.CharField(max_length=20, choices=LoanPayment.MEDIUM_CHOICES)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'{self.loan.loan_number} log on {self.log_date}'


class LoanClosure(TimeStampedModel):
    loan = models.OneToOneField(Loan, on_delete=models.CASCADE, related_name='closure')
    closed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='closed_loans')
    closure_notes = models.TextField(blank=True)
    otp_request = models.ForeignKey(OTPRequest, on_delete=models.PROTECT, related_name='closures')
    confirmed = models.BooleanField(default=False)

    def __str__(self):
        return f'Closure for {self.loan.loan_number}'


class LoanClosureDocument(TimeStampedModel):
    closure = models.ForeignKey(LoanClosure, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=100)
    file = models.FileField(upload_to='loan/closure/')

    def __str__(self):
        return f'{self.closure.loan.loan_number} closure doc'



# gold_loan/models.py
from django.db import models

class GoldRate(models.Model):
    carat = models.IntegerField()
    rate_per_gram = models.FloatField()

    def __str__(self):
        return f"{self.carat}K - ₹{self.rate_per_gram}"
