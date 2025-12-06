# gold_loan/forms.py
from django import forms
from django.forms import BaseFormSet, formset_factory
from decimal import Decimal

from .models import (
    Customer,
    Loan,
    LoanAmountLog,
    LoanClosureDocument,
    LoanDocument,
    LoanGoldItem,
    LoanGoldItemImage,
    LoanPayment,
)


class RequiredFormSet(BaseFormSet):
    """
    Ensures at least ONE form is filled inside formsets like
    Gold Items and Loan Documents.
    """
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        valid_forms = [
            f for f in self.forms
            if getattr(f, "cleaned_data", None) and not f.cleaned_data.get("DELETE")
        ]

        if not valid_forms:
            raise forms.ValidationError("Please add at least one entry.")


# -----------------------------
# Customer Form
# -----------------------------
class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "name",
            "alternate_name",
            "mobile_number",
            "alternate_number",
            "email",
            "address",
            "aadhaar_number",
            "company",
            "photo",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }


# -----------------------------
# Loan Form (Step 2)
# -----------------------------
class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = [
            "lot_no",
            "approved_net_grams",
            "price_per_gram",
            "interest_rate",
            "notes",
            "pledge_bank_name",
            "pledge_bank_address",
            "pledge_receipt_no",
        ]
        widgets = {
            "lot_no": forms.TextInput(attrs={"class": "form-control"}),
            "approved_net_grams": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "price_per_gram": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "interest_rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "pledge_bank_name": forms.TextInput(attrs={"class": "form-control"}),
            "pledge_bank_address": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "pledge_receipt_no": forms.TextInput(attrs={"class": "form-control"}),
        }



    def clean_interest_rate(self):
        r = self.cleaned_data.get('interest_rate') or Decimal('0.00')
        if r < 0:
            raise forms.ValidationError("Interest rate cannot be negative")
        return r

    def clean_price_per_gram(self):
        p = self.cleaned_data.get('price_per_gram') or Decimal('0.00')
        if p < 0:
            raise forms.ValidationError("Price per gram cannot be negative")
        return p


# -----------------------------
# Loan Document Form (Step 3)
# with "Other" option support
# -----------------------------
class LoanDocumentForm(forms.ModelForm):
    OTHER_OPTION = "__other__"

    document_type = forms.ChoiceField(
        choices=[
            ("aadhaar", "Aadhaar"),
            ("pan", "PAN"),
            ("driving", "Driving Licence"),
            ("voter", "Voter ID"),
            (OTHER_OPTION, "Other"),
        ],
        widget=forms.Select(attrs={"class": "doc-type-select"}),
    )

    other_document_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Enter document name"}),
    )

    class Meta:
        model = LoanDocument
        fields = ["document_type", "other_document_name", "file"]

    def clean(self):
        cleaned = super().clean()
        doc_type = cleaned.get("document_type")
        other_doc = cleaned.get("other_document_name")

        # If "Other", require user to type document name
        if doc_type == self.OTHER_OPTION:
            if not other_doc:
                self.add_error("other_document_name", "Please enter document name.")
            cleaned["document_type"] = other_doc  # store custom name into field

        return cleaned


# -----------------------------
# Gold Item Form (Step 2)
# (Option C: form accepts 4 upload inputs; view will create LoanGoldItemImage rows)
# -----------------------------
class LoanGoldItemForm(forms.ModelForm):
    image_1 = forms.ImageField(required=False)
    image_2 = forms.ImageField(required=False)
    image_3 = forms.ImageField(required=False)
    image_4 = forms.ImageField(required=False)

    class Meta:
        model = LoanGoldItem
        fields = ["item_name", "carat_value", "grams", "description"]

    def clean(self):
        cleaned = super().clean()

        images = [
            cleaned.get("image_1"),
            cleaned.get("image_2"),
            cleaned.get("image_3"),
            cleaned.get("image_4"),
        ]

        uploaded_count = sum(1 for img in images if img)

        if uploaded_count < 2:
            raise forms.ValidationError(
                "Please upload at least 2 images for this gold item."
            )

        return cleaned


# -----------------------------
# Payment Form
# -----------------------------
class PaymentForm(forms.ModelForm):
    class Meta:
        model = LoanPayment
        fields = ["payment_date", "amount", "medium", "notes"]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "medium": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }

    def clean_amount(self):
        amt = self.cleaned_data.get('amount')
        if amt is None or amt <= 0:
            raise forms.ValidationError("Enter a payment amount greater than zero.")
        return amt



# -----------------------------
# Company Log Form
# -----------------------------
class CompanyAmountLogForm(forms.ModelForm):
    class Meta:
        model = LoanAmountLog
        fields = ["log_date", "amount", "medium", "notes"]
        widgets = {
            "log_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


# -----------------------------
# Closure Document Form
# -----------------------------
class ClosureDocumentForm(forms.ModelForm):
    class Meta:
        model = LoanClosureDocument
        fields = ["document_type", "file"]


# -----------------------------
# OTP Forms
# -----------------------------
class OTPPhoneForm(forms.Form):
    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={"placeholder": "Enter phone number"}),
    )


class OTPVerificationForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={"placeholder": "Enter OTP", "autocomplete": "one-time-code"}),
    )


# -----------------------------
# FORMSET FACTORIES
# (must always stay at bottom)
# -----------------------------
DocumentFormSet = formset_factory(
    LoanDocumentForm,
    formset=RequiredFormSet,
    extra=1
)

GoldItemFormSet = formset_factory(
    LoanGoldItemForm,
    formset=RequiredFormSet,
    extra=1
)

PaymentFormSet = formset_factory(PaymentForm, extra=1)

CompanyLogFormSet = formset_factory(CompanyAmountLogForm, extra=1)

ClosureDocumentFormSet = formset_factory(
    ClosureDocumentForm,
    formset=RequiredFormSet,
    extra=1
)
