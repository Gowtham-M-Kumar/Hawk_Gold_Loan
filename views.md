# gold_loan/views.py
from decimal import Decimal
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    CustomerForm,
    LoanForm,
    GoldItemFormSet,
    DocumentFormSet,
    OTPPhoneForm,
    OTPVerificationForm,
    PaymentForm,
)
from .models import (
    Customer,
    Loan,
    LoanGoldItem,
    LoanGoldItemImage,
    LoanPayment,
    LoanDocument,
    LoanClosureDocument,
    LoanAmountLog,
)

# ----------------------------------------
# SESSION CONSTANTS
# ----------------------------------------
SESSION_LOAN_ID = "loan_entry_loan_id"
SESSION_LOAN_CUSTOMER = "loan_entry_customer_id"
SESSION_LOAN_OTP = "loan_entry_otp"
SESSION_LOAN_PHONE = "loan_entry_phone"

# ----------------------------------------
# Utility helpers
# ----------------------------------------
def _get_int_safe(val, default=None):
    try:
        return int(val)
    except Exception:
        return default


def _require_access(request):
    """
    Access control check. Override this to add permission logic.
    Raise Http404 or PermissionDenied if access should be denied.
    """
    # By default, allow all authenticated users (login_required handles this).
    # Add custom logic here (e.g., staff-only, role-based checks).
    pass


def _ensure_user_can_access(request):
    """
    Wrapper to call _require_access safely (keeps call-sites small).
    """
    try:
        _require_access(request)
    except Exception:
        # If access control raises, re-raise to allow its behavior to continue.
        raise


# ----------------------------------------
# STEP 1 — CUSTOMER CREATION / SELECT
# ----------------------------------------
@login_required
def loan_entry_step1(request):
    _ensure_user_can_access(request)

    if request.method == "GET":
        customer_param = request.GET.get("customer_id")
        if customer_param:
            try:
                cid = _get_int_safe(customer_param)
                if cid:
                    get_object_or_404(Customer, pk=cid)
                    request.session[SESSION_LOAN_CUSTOMER] = cid
                    request.session.modified = True
                    return redirect("gold_loan:loan_entry_step2")
            except (ValueError, Customer.DoesNotExist):
                # ignore and continue to page
                pass

        # Reset any previous loan session data on GET landing
        for key in [SESSION_LOAN_ID, SESSION_LOAN_CUSTOMER, SESSION_LOAN_OTP, SESSION_LOAN_PHONE]:
            request.session.pop(key, None)

    form = CustomerForm(request.POST or None, request.FILES or None, prefix="customer")
    if request.method == "POST" and form.is_valid():
        customer = form.save()
        request.session[SESSION_LOAN_CUSTOMER] = customer.id
        request.session.modified = True
        return redirect("gold_loan:loan_entry_step2")

    return render(request, "gold_loan/loan_entry_step1.html", {"customer_form": form})


# ----------------------------------------
# STEP 2 — LOAN DETAILS + GOLD ITEMS
# ----------------------------------------
@login_required
def loan_entry_step2(request, loan_id: Optional[int] = None):
    _ensure_user_can_access(request)

    customer_id = request.session.get(SESSION_LOAN_CUSTOMER)
    if not customer_id:
        messages.info(request, "Please add/select a customer first.")
        return redirect("gold_loan:loan_entry_step1")

    customer = get_object_or_404(Customer, pk=customer_id)
    loan = get_object_or_404(Loan, id=loan_id) if loan_id else None

    if request.method == "POST":
        loan_form = LoanForm(request.POST, instance=loan)
        gold_formset = GoldItemFormSet(request.POST, request.FILES, prefix="items")

        if loan_form.is_valid() and gold_formset.is_valid():
            with transaction.atomic():
                loan = loan_form.save(commit=False)
                loan.customer = customer

                # initialize interest fields for new loan
                if not loan.id:
                    # keep fields safe if model has different defaults
                    loan.pending_interest = getattr(loan, "pending_interest", Decimal("0.00"))
                    loan.total_interest_accrued = getattr(loan, "total_interest_accrued", Decimal("0.00"))
                    loan.last_interest_calculated_date = timezone.localdate()

                if not getattr(loan, "created_by", None):
                    loan.created_by = request.user

                loan.save()

                # remove previous gold items (editing case)
                loan.gold_items.all().delete()

                total_grams = Decimal("0.00")
                for form in gold_formset:
                    if getattr(form, "cleaned_data", None) and not form.cleaned_data.get("DELETE"):
                        item = form.save(commit=False)
                        item.loan = loan
                        item.save()

                        # create image rows for each uploaded image field (image_1..image_4)
                        for img_field in ("image_1", "image_2", "image_3", "image_4"):
                            img = form.cleaned_data.get(img_field)
                            if img:
                                LoanGoldItemImage.objects.create(gold_item=item, image=img)

                        total_grams += item.grams or Decimal("0.00")

                loan.total_actual_grams = total_grams
                loan.save()

                # save in session and continue
                request.session[SESSION_LOAN_ID] = loan.id
                request.session.modified = True
                return redirect("gold_loan:loan_entry_step3")
        else:
            # let errors fall through to template
            pass
    else:
        loan_form = LoanForm(instance=loan)
        gold_formset = GoldItemFormSet(prefix="items")

    # initial items if editing
    initial_items = []
    if loan:
        for item in loan.gold_items.all():
            initial_items.append(
                {
                    "item_name": item.item_name,
                    "carat_value": item.carat_value,
                    "grams": item.grams,
                    "description": item.description,
                }
            )
        gold_formset = GoldItemFormSet(initial=initial_items, prefix="items")

    daily_preview = None
    expected_interest = None

    if loan:
        try:
            daily_preview = loan.daily_interest_amount()
        except Exception:
            daily_preview = None

        # For UI preview, show example 30-day expected interest (no business effect)
        try:
            if daily_preview is not None:
                EXPECTED_DAYS = Decimal("30")
                expected_interest = (daily_preview * EXPECTED_DAYS).quantize(Decimal("0.01"))
            else:
                expected_interest = Decimal("0.00")
        except Exception:
            expected_interest = Decimal("0.00")

    context = {
        "loan_form": loan_form,
        "gold_formset": gold_formset,
        "loan": loan,
        "daily_interest_preview": daily_preview,
        "expected_interest_period": expected_interest,
        "customer": customer,
    }
    return render(request, "gold_loan/loan_entry_step2.html", context)


# ----------------------------------------
# STEP 3 — DOCUMENT UPLOAD
# ----------------------------------------
@login_required
def loan_entry_step3(request):
    _ensure_user_can_access(request)

    loan_id = request.session.get(SESSION_LOAN_ID)
    if not loan_id:
        messages.info(request, "Complete loan & product details first.")
        return redirect("gold_loan:loan_entry_step2")

    loan = get_object_or_404(Loan, pk=loan_id)
    document_formset = DocumentFormSet(request.POST or None, request.FILES or None, prefix="documents")

    if request.method == "POST":
        if document_formset.is_valid():
            with transaction.atomic():
                for form in document_formset:
                    if getattr(form, "cleaned_data", None) and not form.cleaned_data.get("DELETE"):
                        doc = form.save(commit=False)
                        doc.loan = loan
                        doc.save()
            return redirect("gold_loan:loan_entry_step4")
        else:
            messages.error(request, "Please check document upload fields.")

    return render(request, "gold_loan/loan_entry_step3.html", {"document_formset": document_formset, "loan": loan})


# ----------------------------------------
# STEP 4 — PHONE & OTP (front-end JS handles OTP for UX)
# ----------------------------------------
@login_required
def loan_entry_step4(request):
    _ensure_user_can_access(request)

    loan_id = request.session.get(SESSION_LOAN_ID)
    if not loan_id:
        messages.info(request, "Start a new loan entry first.")
        return redirect("gold_loan:loan_entry_step1")

    loan = get_object_or_404(Loan, pk=loan_id)
    phone_initial = request.session.get(SESSION_LOAN_PHONE)
    phone_form = OTPPhoneForm(initial={"phone_number": phone_initial})

    return render(
        request,
        "gold_loan/loan_entry_step4.html",
        {"loan": loan, "loan_id": loan.id, "phone_form": phone_form},
    )


# ----------------------------------------
# OTP: Send and Verify (simple/session-backed)
# Integrate with your SMS/OTP provider where indicated
# ----------------------------------------
@login_required
def send_otp(request):
    _ensure_user_can_access(request)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    phone = request.POST.get("phone_number")
    if not phone:
        return JsonResponse({"error": "phone_number required"}, status=400)

    # Generate a simple numeric OTP for demo. Replace with real provider integration.
    import random
    otp = f"{random.randint(100000, 999999)}"
    request.session[SESSION_LOAN_OTP] = otp
    request.session[SESSION_LOAN_PHONE] = phone
    request.session.modified = True

    # TODO: integrate actual SMS provider here to send `otp` to `phone`.
    # For now we return success and the OTP for local testing (remove in production).
    return JsonResponse({"ok": True, "otp_for_testing": otp})


@login_required
def verify_otp(request):
    _ensure_user_can_access(request)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    form = OTPVerificationForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": "Invalid code"}, status=400)

    code = form.cleaned_data["code"]
    stored = request.session.get(SESSION_LOAN_OTP)
    if not stored:
        return JsonResponse({"error": "OTP expired or not sent"}, status=400)

    if code != stored:
        return JsonResponse({"error": "Invalid OTP"}, status=400)

    # OTP valid -> mark verified and clear OTP
    request.session.pop(SESSION_LOAN_OTP, None)
    request.session.modified = True
    return JsonResponse({"ok": True})


# ----------------------------------------
# LOAN LIST / SEARCH
# ----------------------------------------
@login_required
def loan_list(request):
    _ensure_user_can_access(request)

    q = request.GET.get("q", "").strip()
    loans = Loan.objects.all().select_related("customer", "created_by")

    if q:
        loans = loans.filter(
            Q(loan_number__icontains=q)
            | Q(customer__name__icontains=q)
            | Q(lot_no__icontains=q)
        )

    loans = loans.order_by("-created_at")[:200]
    return render(request, "gold_loan/loan_list.html", {"loans": loans, "query": q})


# ----------------------------------------
# LOAN DETAIL
# ----------------------------------------
@login_required
def loan_detail(request, loan_id):
    _ensure_user_can_access(request)
    loan = get_object_or_404(Loan, pk=loan_id)

    # ensure interest is accrued up to today for display (but don't force save if you prefer)
    try:
        loan.accrue_interest_up_to(timezone.localdate())
    except Exception:
        # ignore but continue so UI shows current stored values
        pass

    # compute interest preview and payments
    daily = None
    total_interest = None
    try:
        daily = loan.daily_interest_amount()
        total_interest = loan.total_interest_accrued
    except Exception:
        daily = None
        total_interest = loan.total_interest_accrued if hasattr(loan, "total_interest_accrued") else Decimal("0.00")

    payments = getattr(loan, "payments", loan.loanpayment_set).all()[:50]  # guard for related_name variations

    return render(
        request,
        "gold_loan/loan_detail.html",
        {
            "loan": loan,
            "daily_interest": daily,
            "total_interest_accrued": total_interest,
            "payments": payments,
        },
    )


# ----------------------------------------
# LOAN PAYMENT (create)
# ----------------------------------------
@login_required
def loan_payment(request, loan_id):
    _ensure_user_can_access(request)
    loan = get_object_or_404(Loan, pk=loan_id)

    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            # amount and date
            payment_date = form.cleaned_data.get("payment_date") or timezone.localdate()
            amount = form.cleaned_data.get("amount")
            medium = form.cleaned_data.get("medium", "")
            notes = form.cleaned_data.get("notes", "")

            # Use loan.apply_payment() if available to compute breakdown and mutate loan
            breakdown = {}
            try:
                breakdown = loan.apply_payment(amount=Decimal(amount), payment_date=payment_date)
            except Exception:
                # fallback: if apply_payment isn't present or failed, just accrue interest and deduct interest/principal manually
                try:
                    loan.accrue_interest_up_to(payment_date)
                except Exception:
                    pass

                # pay interest first
                interest_deducted = min(loan.pending_interest, Decimal(amount))
                remainder = Decimal(amount) - interest_deducted
                principal_deducted = Decimal("0.00")
                if remainder > 0:
                    principal_deducted = min(loan.total_loan_amount, remainder)
                    loan.total_loan_amount = loan.total_loan_amount - principal_deducted

                loan.pending_interest = loan.pending_interest - interest_deducted
                loan.save(update_fields=["pending_interest", "total_loan_amount", "updated_at"])

                breakdown = {
                    "interest_deducted": quantize_if_possible(interest_deducted),
                    "principal_deducted": quantize_if_possible(principal_deducted),
                    "remaining_principal": quantize_if_possible(getattr(loan, "total_loan_amount", Decimal("0.00"))),
                    "remaining_interest": quantize_if_possible(getattr(loan, "pending_interest", Decimal("0.00"))),
                }

            # Create LoanPayment record (fields may vary between projects; be defensive)
            payment_kwargs = {
                "loan": loan,
                "amount": Decimal(amount),
                "payment_date": payment_date,
                "medium": medium,
                "notes": notes,
            }
            # try to set principal_component / interest_component if model has those
            try:
                # prefer numeric keys from breakdown
                payment_kwargs["interest_component"] = breakdown.get("interest_deducted", Decimal("0.00"))
                payment_kwargs["principal_component"] = breakdown.get("principal_deducted", Decimal("0.00"))
            except Exception:
                pass

            # create payment record
            try:
                LoanPayment.objects.create(**payment_kwargs)
            except Exception:
                # Payment model might use different field names; try minimal create
                LoanPayment.objects.create(loan=loan, amount=Decimal(amount), payment_date=payment_date)

            messages.success(request, "Payment recorded successfully.")
            return redirect("gold_loan:loan_detail", loan_id=loan.id)
        else:
            messages.error(request, "Please check the payment form.")
    else:
        form = PaymentForm(initial={"payment_date": timezone.localdate()})

    # show current interest/pending for UI
    try:
        loan.accrue_interest_up_to(timezone.localdate())
    except Exception:
        pass

    return render(request, "gold_loan/loan_payment.html", {"loan": loan, "form": form})


# ----------------------------------------
# LOAN RENEWAL (create a new loan with previous link)
# ----------------------------------------
@login_required
def loan_renew(request, loan_id):
    _ensure_user_can_access(request)
    old_loan = get_object_or_404(Loan, pk=loan_id)

    if request.method == "POST":
        form = LoanForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                new_loan = form.save(commit=False)
                new_loan.customer = old_loan.customer
                new_loan.previous_loan = old_loan
                if not getattr(new_loan, "created_by", None):
                    new_loan.created_by = request.user
                # initialize interest fields
                new_loan.pending_interest = Decimal("0.00")
                new_loan.total_interest_accrued = Decimal("0.00")
                new_loan.last_interest_calculated_date = timezone.localdate()
                new_loan.save()
            messages.success(request, "Loan renewed successfully.")
            return redirect("gold_loan:loan_detail", loan_id=new_loan.id)
    else:
        # prefill fields from existing loan where appropriate
        initial = {
            "approved_net_grams": old_loan.approved_net_grams,
            "price_per_gram": old_loan.price_per_gram,
            "interest_rate": old_loan.interest_rate,
        }
        form = LoanForm(initial=initial)

    return render(request, "gold_loan/loan_renew.html", {"form": form, "old_loan": old_loan})


# ----------------------------------------
# LOAN CLOSURE
# ----------------------------------------
@login_required
def loan_close(request, loan_id):
    _ensure_user_can_access(request)
    loan = get_object_or_404(Loan, pk=loan_id)

    if request.method == "POST":
        # Optionally accept closure documents and final payment
        closure_docs = request.FILES.getlist("closure_documents")
        final_payment_amount = request.POST.get("final_payment_amount")

        with transaction.atomic():
            try:
                # record final payment if provided
                if final_payment_amount:
                    amt = Decimal(final_payment_amount)
                    # reuse loan.apply_payment where available
                    try:
                        loan.apply_payment(amount=amt, payment_date=timezone.localdate())
                    except Exception:
                        loan.accrue_interest_up_to(timezone.localdate())
                        # apply naive payment to principal
                        loan.total_loan_amount = max(Decimal("0.00"), loan.total_loan_amount - amt)
                        loan.save(update_fields=["total_loan_amount", "updated_at"])

                    # create payment record
                    try:
                        LoanPayment.objects.create(loan=loan, amount=amt, payment_date=timezone.localdate())
                    except Exception:
                        pass

                # create closure documents records if model exists
                for f in closure_docs:
                    try:
                        LoanClosureDocument.objects.create(loan=loan, document_type="closure", file=f)
                    except Exception:
                        pass

                loan.status = Loan.STATUS_CLOSED
                loan.save(update_fields=["status", "updated_at"])
                messages.success(request, "Loan closed successfully.")
                return redirect("gold_loan:loan_detail", loan_id=loan.id)
            except Exception as exc:
                messages.error(request, f"Error closing loan: {exc}")
    return render(request, "gold_loan/loan_close.html", {"loan": loan})


# ----------------------------------------
# COMPANY AMOUNT LOGS (list and add)
# ----------------------------------------
@login_required
def company_amount_logs(request, loan_id):
    _ensure_user_can_access(request)
    loan = get_object_or_404(Loan, pk=loan_id)
    # list logs related to loan (if your model tracks company-level logs globally, adjust)
    logs = LoanAmountLog.objects.filter(loan=loan).order_by("-log_date") if hasattr(LoanAmountLog, "objects") else []
    return render(request, "gold_loan/company_logs.html", {"loan": loan, "logs": logs})


# ----------------------------------------
# SEARCH (ajax)
# ----------------------------------------
@login_required
def ajax_search_loans(request):
    _ensure_user_can_access(request)
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"results": []})

    qs = Loan.objects.filter(Q(loan_number__icontains=q) | Q(customer__name__icontains=q))[:20]
    results = [
        {"id": l.id, "loan_number": l.loan_number, "customer": l.customer.name, "status": l.status}
        for l in qs
    ]
    return JsonResponse({"results": results})


# ----------------------------------------
# EXPORT / PRINT (basic HTML render, integrate a PDF generator if needed)
# ----------------------------------------
@login_required
def loan_export_print(request, loan_id):
    _ensure_user_can_access(request)
    loan = get_object_or_404(Loan, pk=loan_id)
    # ensure up-to-date interest
    try:
        loan.accrue_interest_up_to(timezone.localdate())
    except Exception:
        pass
    return render(request, "gold_loan/loan_export_print.html", {"loan": loan})


# ----------------------------------------
# Small helper for quantize when quantize helper is not available in views
# (the model uses quantize_money; views can use this fallback)
# ----------------------------------------
def quantize_if_possible(value: Decimal) -> Decimal:
    try:
        return value.quantize(Decimal("0.01"))
    except Exception:
        return Decimal(value)



@login_required
def home(request):
    _ensure_user_can_access(request)

    # You can change what data to show on home page
    loans = Loan.objects.order_by('-created_at')[:10]  # latest 10 loans

    return render(request, "gold_loan/home.html", {
        "loans": loans,
    })

@login_required
def dashboard(request):
    _ensure_user_can_access(request)

    # Latest loans
    latest_loans = Loan.objects.select_related("customer").order_by("-created_at")[:10]

    # Totals (safe aggregation)
    total_active = Loan.objects.filter(status=Loan.STATUS_ACTIVE).count()
    total_closed = Loan.objects.filter(status=Loan.STATUS_CLOSED).count()
    total_draft = Loan.objects.filter(status=Loan.STATUS_DRAFT).count()

    # Total outstanding principal
    outstanding = sum([loan.principal_remaining() for loan in Loan.objects.filter(status=Loan.STATUS_ACTIVE)])

    # Today's collections
    today = timezone.localdate()
    today_payments = LoanPayment.objects.filter(payment_date=today)
    today_collection = sum([p.amount for p in today_payments])

    context = {
        "latest_loans": latest_loans,
        "total_active": total_active,
        "total_closed": total_closed,
        "total_draft": total_draft,
        "outstanding": outstanding,
        "today_collection": today_collection,
        "today_payments": today_payments,
    }

    return render(request, "gold_loan/dashboard.html", context)



from django.http import JsonResponse

@login_required
def search_customers(request):
    _ensure_user_can_access(request)

    query = request.GET.get("q", "").strip()

    if not query:
        return JsonResponse({"results": []})

    customers = Customer.objects.filter(
        Q(name__icontains=query)
        | Q(alternate_name__icontains=query)
        | Q(mobile_number__icontains=query)
        | Q(alternate_number__icontains=query)
        | Q(aadhaar_number__icontains=query)
    ).order_by("name")[:20]

    results = []
    for c in customers:
        results.append({
            "id": c.id,
            "name": c.name,
            "mobile": c.mobile_number,
            "alternate": c.alternate_number,
            "aadhaar": c.aadhaar_number,
            "address": c.address,
        })

    return JsonResponse({"results": results})



@login_required
def customers(request):
    _ensure_user_can_access(request)

    q = request.GET.get("q", "").strip()

    queryset = Customer.objects.all().order_by("-created_at")

    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(mobile_number__icontains=q)
            | Q(aadhaar_number__icontains=q)
            | Q(alternate_name__icontains=q)
        )

    context = {
        "customers": queryset[:200],  # limit to prevent huge lists
        "query": q,
    }
    return render(request, "gold_loan/customers.html", context)


@login_required
def customer_loans(request, customer_id):
    _ensure_user_can_access(request)

    customer = get_object_or_404(Customer, pk=customer_id)

    loans = Loan.objects.filter(customer=customer).order_by("-created_at")

    # Accrue interest for accurate display
    for loan in loans:
        try:
            loan.accrue_interest_up_to(timezone.localdate())
        except Exception:
            pass

    return render(
        request,
        "gold_loan/customer_loans.html",
        {
            "customer": customer,
            "loans": loans,
        }
    )


@login_required
def loan_edit(request, loan_id):
    _ensure_user_can_access(request)

    loan = get_object_or_404(Loan, pk=loan_id)
    customer = loan.customer  # already linked

    if request.method == "POST":
        loan_form = LoanForm(request.POST, instance=loan)
        gold_formset = GoldItemFormSet(request.POST, request.FILES, prefix="items")

        if loan_form.is_valid() and gold_formset.is_valid():
            with transaction.atomic():
                # Update loan fields
                loan = loan_form.save(commit=False)
                loan.customer = customer
                loan.save()

                # Remove previous gold items and re-add
                loan.gold_items.all().delete()

                total_grams = Decimal("0.00")

                for form in gold_formset:
                    if getattr(form, "cleaned_data", None) and not form.cleaned_data.get("DELETE"):
                        item = form.save(commit=False)
                        item.loan = loan
                        item.save()

                        # Save images (image_1..image_4)
                        for img_field in ("image_1", "image_2", "image_3", "image_4"):
                            img = form.cleaned_data.get(img_field)
                            if img:
                                LoanGoldItemImage.objects.create(gold_item=item, image=img)

                        total_grams += item.grams or Decimal("0.00")

                loan.total_actual_grams = total_grams
                loan.save()

                messages.success(request, "Loan updated successfully.")
                return redirect("gold_loan:loan_detail", loan_id=loan.id)

        else:
            messages.error(request, "Please correct the errors below.")

    else:
        # Pre-fill gold items
        initial_items = [
            {
                "item_name": item.item_name,
                "carat_value": item.carat_value,
                "grams": item.grams,
                "description": item.description,
            }
            for item in loan.gold_items.all()
        ]

        loan_form = LoanForm(instance=loan)
        gold_formset = GoldItemFormSet(initial=initial_items, prefix="items")

    # Interest preview
    try:
        daily_interest = loan.daily_interest_amount()
    except:
        daily_interest = None

    context = {
        "loan": loan,
        "customer": customer,
        "loan_form": loan_form,
        "gold_formset": gold_formset,
        "daily_interest_preview": daily_interest,
    }

    return render(request, "gold_loan/loan_edit.html", context)


