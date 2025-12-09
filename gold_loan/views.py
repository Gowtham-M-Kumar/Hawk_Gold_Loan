from decimal import Decimal
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction, models
from django.db.models import Q, OuterRef, Exists, Count
from django.db.models.functions import Lower, Trim
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.urls import reverse
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from gold_loan.models import Notification

from datetime import timedelta
from django.utils import timezone
from gold_loan.models import Notification, Loan, LoanPayment



from .forms import (
    CustomerForm,
    LoanForm,
    GoldItemFormSet,
    DocumentFormSet,
    OTPPhoneForm,
    OTPVerificationForm,
    PaymentForm,
    ClosureDocumentFormSet,
)
from .models import (
    AppAccess,
    Customer,
    Loan,
    LoanGoldItem,
    LoanGoldItemImage,
    LoanDocument,
    LoanPayment,
    LoanClosure,
    LoanClosureDocument,
    OTPRequest,
)
from .services.otp import OTPService
from .models import quantize_money  # Use from models.py

SESSION_LOAN_CUSTOMER = "loan_wizard_customer_id"
SESSION_LOAN_ID = "loan_wizard_loan_id"
SESSION_LOAN_OTP = "loan_wizard_otp_id"
SESSION_LOAN_PHONE = "loan_wizard_phone"


def _ensure_access(user):
    if user.is_superuser:
        return True
    return AppAccess.objects.filter(user=user, app_label=AppAccess.GOLD_LOAN_APP).exists()


def _require_access(request):
    if not _ensure_access(request.user):
        raise PermissionDenied("You do not have access to the gold loan module.")


def _safe_invoke(obj, method_name, *args, **kwargs):
    try:
        attr = getattr(obj, method_name, None)
        if callable(attr):
            return attr(*args, **kwargs)
        else:
            return attr
    except Exception:
        return None


@login_required
def dashboard(request):
    _require_access(request)
    
    generate_overdue_notifications()


    loans = Loan.objects.all()

# compute pending using model logic
    pending_amount_total = sum([loan.remaining_due for loan in loans])


    # Basic stats
    total_loans = loans.count()
    active_loans = loans.filter(status=Loan.STATUS_ACTIVE).count()
    total_amount = loans.aggregate(total=Sum("total_loan_amount"))["total"] or 0
    
    

    # Customer count
    customers_count = Customer.objects.count()

    # Today's collections
    today = timezone.localdate()
    today_collections = (
        LoanPayment.objects.filter(payment_date=today)
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )

    # Avg tenure currently not supported (field removed)
    avg_tenure = None

    context = {
        "loans": loans,
        "total_loans": total_loans,
        "total_amount": total_amount,
        "customers_count": customers_count,
        "today_collections": today_collections,
        "pending_amount_total": pending_amount_total,
        "avg_tenure": avg_tenure,
    }

    return render(request, "gold_loan/dashboard.html", context)



@login_required
def search_customers(request):
    query = request.GET.get("q", "").strip()

    if not query:
        return JsonResponse({"results": []})

    customers_qs = Customer.objects.filter(
        Q(name__icontains=query) |
        Q(mobile_number__icontains=query) |
        Q(aadhaar_number__icontains=query)
    ).order_by("name")[:10]

    results = []
    for c in customers_qs:
        results.append({
            "id": c.id,
            "name": c.name,
            "mobile_number": c.mobile_number,
            # reverse the named URL so client receives the exact correct path
            "url": reverse('gold_loan:customer_loans', args=[c.id])
        })

    return JsonResponse({"results": results})



@login_required
def loan_entry_step1(request):
    _require_access(request)

    if request.method == "GET":
        customer_param = request.GET.get("customer_id")
        if customer_param:
            try:
                cid = int(customer_param)
                get_object_or_404(Customer, pk=cid)
                request.session[SESSION_LOAN_CUSTOMER] = cid
                request.session.modified = True
                return redirect("gold_loan:loan_entry_step2")
            except (ValueError, Customer.DoesNotExist):
                pass

        request.session.pop(SESSION_LOAN_ID, None)
        request.session.pop(SESSION_LOAN_CUSTOMER, None)
        request.session.pop(SESSION_LOAN_OTP, None)
        request.session.pop(SESSION_LOAN_PHONE, None)

    form = CustomerForm(request.POST or None, request.FILES or None, prefix="customer")
    if request.method == "POST" and form.is_valid():
        customer = form.save()
        request.session[SESSION_LOAN_CUSTOMER] = customer.id
        request.session.modified = True
        return redirect("gold_loan:loan_entry_step2")

    return render(request, "gold_loan/loan_entry_step1.html", {"customer_form": form})


@login_required
def loan_entry_step2(request, loan_id=None):
    _require_access(request)

    customer_id = request.session.get(SESSION_LOAN_CUSTOMER)
    if not customer_id:
        messages.info(request, "Please add/select a customer first.")
        return redirect("gold_loan:loan_entry_step1")
    customer = get_object_or_404(Customer, pk=customer_id)

    loan = get_object_or_404(Loan, id=loan_id) if loan_id else None

    if request.method == "POST":
        loan_form = LoanForm(request.POST, instance=loan)
        gold_formset = GoldItemFormSet(request.POST, request.FILES, prefix='items')

        if loan_form.is_valid() and gold_formset.is_valid():
            with transaction.atomic():
                loan = loan_form.save(commit=False)
                loan.customer = customer

                if not loan.id:
                    loan.pending_interest = Decimal("0.00")
                    loan.total_interest_accrued = Decimal("0.00")
                    loan.last_interest_calculated_date = timezone.localdate()

                loan.created_by = getattr(loan, "created_by", request.user)
                loan.save()

                loan.gold_items.all().delete()
                total_grams = Decimal("0.00")

                for form in gold_formset:
                    if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                        item = form.save(commit=False)
                        item.loan = loan
                        item.save()

                        for img_field in ("image_1", "image_2", "image_3", "image_4"):
                            img = form.cleaned_data.get(img_field)
                            if img:
                                LoanGoldItemImage.objects.create(gold_item=item, image=img)

                        total_grams += item.grams or Decimal("0.00")

                loan.total_actual_grams = total_grams
                loan.save()

                request.session[SESSION_LOAN_ID] = loan.id
                request.session.modified = True
                return redirect("gold_loan:loan_entry_step3")

    else:
        loan_form = LoanForm(instance=loan)

    initial_items = []

    gold_formset = GoldItemFormSet(initial=initial_items, prefix='items')

    daily_preview = expected_interest = None

    if loan:
        try:
            daily_preview = loan.daily_interest_amount()
        except:
            daily_preview = None

        try:
            expected_interest = (
                (daily_preview * Decimal(loan.interest_period_days)).quantize(Decimal("0.01"))
                if daily_preview else Decimal("0.00")
            )
        except:
            expected_interest = Decimal("0.00")

    context = {
        "loan_form": loan_form,
        "gold_formset": gold_formset,
        "loan": loan,
        "daily_interest_preview": daily_preview,
        "expected_interest_period": expected_interest,
    }
    return render(request, "gold_loan/loan_entry_step2.html", context)


@login_required
def loan_entry_step3(request):
    _require_access(request)
    loan_id = request.session.get(SESSION_LOAN_ID)
    if not loan_id:
        messages.info(request, "Complete loan & product details first.")
        return redirect("gold_loan:loan_entry_step2")

    loan = get_object_or_404(Loan, pk=loan_id)
    document_formset = DocumentFormSet(request.POST or None, request.FILES or None, prefix="documents")

    if request.method == "POST":
        if document_formset.is_valid():
            for form in document_formset:
                if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                    doc = form.save(commit=False)
                    doc.loan = loan
                    doc.save()
            return redirect("gold_loan:loan_entry_step4")
        else:
            messages.error(request, "Please check document upload fields.")

    return render(request, "gold_loan/loan_entry_step3.html", {"document_formset": document_formset, "loan": loan})

@login_required
def loan_entry_step4(request):
    _require_access(request)

    # Get loan ID from session
    loan_id = request.session.get(SESSION_LOAN_ID)
    if not loan_id:
        messages.info(request, "Start a new loan entry first.")
        return redirect("gold_loan:loan_entry_step1")

    loan = get_object_or_404(Loan, pk=loan_id)

    # -------------------------------
    # POST — OTP Verified → Finalize
    # -------------------------------
    if request.method == "POST":

        # (OTP is already verified by JavaScript)
        # Finalize loan & cleanup session

        if SESSION_LOAN_ID in request.session:
            del request.session[SESSION_LOAN_ID]

        if SESSION_LOAN_PHONE in request.session:
            del request.session[SESSION_LOAN_PHONE]

        messages.success(request, "Loan created successfully.")
        
       

        Notification.objects.create(
        customer=loan.customer,
        loan=loan,
        type=Notification.TYPE_NEW_LOAN,
        message=f"New loan added for {loan.customer.name}. Loan No: {loan.loan_number}"
    )


        # Redirect to loan detail page
        return redirect("gold_loan:loan_detail", loan_id=loan.id)

    # -------------------------------
    # GET — Show Page
    # -------------------------------
    phone_initial = request.session.get(SESSION_LOAN_PHONE)
    phone_form = OTPPhoneForm(initial={"phone_number": phone_initial})

    return render(
        request,
        "gold_loan/loan_entry_step4.html",
        {
            "loan": loan,
            "loan_id": loan.id,
            "phone_form": phone_form,
        }
    )


@login_required
def loan_detail(request, loan_id):
    _require_access(request)
    loan = get_object_or_404(Loan, pk=loan_id)
    payments = loan.payments.all()

    interest_due = _safe_invoke(loan, "interest_due", timezone.localdate())
    if interest_due is None:
        interest_due = _safe_invoke(loan, "interest_due") or Decimal("0.00")

    interest_paid = _safe_invoke(loan, "total_interest_paid", timezone.localdate())
    if interest_paid is None:
        interest_paid = _safe_invoke(loan, "total_interest_paid") or Decimal("0.00")

    interest_pending = _safe_invoke(loan, "interest_pending", timezone.localdate())
    if interest_pending is None:
        interest_pending = _safe_invoke(loan, "interest_pending") or Decimal("0.00")

    principal_remaining = _safe_invoke(loan, "principal_remaining", timezone.localdate())
    if principal_remaining is None:
        principal_remaining = _safe_invoke(loan, "principal_remaining") or None

    # 🔥 ADD THIS LINE — FETCH DOCUMENTS
    documents = loan.documents.all()   # OR loan.loandocument_set.all()

    return render(request, "gold_loan/loan_detail.html", {
        "loan": loan,
        "payments": payments,
        "documents": documents,    # 🔥 SEND DOCUMENTS TO TEMPLATE
        "interest_due": interest_due,
        "interest_paid": interest_paid,
        "interest_pending": interest_pending,
        "principal_remaining": principal_remaining,
        "remaining_due": loan.remaining_due,
    })

############
#############
from django.db.models import Sum
from decimal import Decimal


@login_required
def loan_payment(request, loan_id):
    loan = get_object_or_404(Loan.objects.select_related('customer'), id=loan_id)
    today = timezone.localdate()
    
    # ---------------------------
    # FIX: Ensure interest starts for new loans
    # ---------------------------
    if loan.last_interest_calculated_date is None:
        loan.last_interest_calculated_date = loan.created_at.date()
        loan.save(update_fields=["last_interest_calculated_date"])

    # 1) Accrue interest
    loan.accrue_interest_up_to(today)
    loan.refresh_from_db()

    # 2) Aggregate existing payments
    payments_agg = LoanPayment.objects.filter(loan=loan).aggregate(
        principal_sum=Sum('principal_component'),
        interest_sum=Sum('interest_component'),
        total_sum=Sum('amount')
    )
    principal_paid = payments_agg.get('principal_sum') or Decimal("0.00")
    interest_paid = payments_agg.get('interest_sum') or Decimal("0.00")
    total_paid = payments_agg.get('total_sum') or Decimal("0.00")

    # 3) Loan values
    original_principal = loan.total_loan_amount or Decimal("0.00")
    try:
        principal_remaining = loan.principal_remaining() or Decimal("0.00")
    except:
        principal_remaining = max(Decimal("0.00"), original_principal - principal_paid)

    total_interest_accrued = loan.total_interest_accrued or Decimal("0.00")
    pending_interest = max(total_interest_accrued - interest_paid, Decimal("0.00"))

    try:
        daily_interest = quantize_money(loan.daily_interest_amount())
    except:
        daily_interest = Decimal("0.00")

    closing_amount = quantize_money(principal_remaining + pending_interest)
    pending_amount = quantize_money(max(closing_amount - total_paid, Decimal("0.00")))

    # -------------------------------------------------
    # POST — Process Payment
    # -------------------------------------------------
    if request.method == "POST":

        payment_amount_raw = request.POST.get("payment_amount")
        medium = request.POST.get("medium", LoanPayment.MEDIUM_CASH)
        notes = request.POST.get("notes", "")

        try:
            payment_amount = quantize_money(Decimal(payment_amount_raw or "0"))
        except:
            messages.error(request, "Invalid payment amount.")
            return redirect("gold_loan:loan_payment", loan_id=loan.id)

        if payment_amount <= 0:
            messages.error(request, "Payment must be positive.")
            return redirect("gold_loan:loan_payment", loan_id=loan.id)

        with transaction.atomic():

            breakdown = loan.apply_payment(payment_amount, payment_date=today)

            LoanPayment.objects.create(
                loan=loan,
                payment_date=today,
                amount=payment_amount,
                medium=medium,
                notes=notes,
                interest_component=breakdown.get('interest_deducted', Decimal("0")),
                principal_component=breakdown.get('principal_deducted', Decimal("0")),
            )

            loan.refresh_from_db()

            Notification.objects.create(
                customer=loan.customer,
                loan=loan,
                type=Notification.TYPE_PAYMENT,
                message=f"PAYMENT_SUCCESS::Payment of ₹{payment_amount} received from {loan.customer.name}."
            )

            messages.success(request, f"PAYMENT_SUCCESS::Payment ₹{payment_amount} recorded successfully.")

        return redirect("gold_loan:loan_detail", loan_id=loan.id)

    # -------------------------------------------------
    # GET — Render page
    # -------------------------------------------------
    context = {
        "loan": loan,
        "original_principal": quantize_money(original_principal),
        "remaining_principal": quantize_money(principal_remaining),
        "pending_interest": quantize_money(pending_interest),
        "daily_interest": daily_interest,
        "closing_amount": closing_amount,
        "total_paid": quantize_money(total_paid),
        "pending_amount": pending_amount,
        "total_interest_accrued": quantize_money(total_interest_accrued),
        "total_interest_paid": quantize_money(interest_paid),
        "total_principal_paid": quantize_money(principal_paid),
        "interest_rate": loan.interest_rate,
    }

    return render(request, "gold_loan/loan_payment.html", context)




@login_required
def loan_edit(request, loan_id):
    _require_access(request)
    loan = get_object_or_404(Loan, pk=loan_id)

    loan_form = LoanForm(request.POST or None, instance=loan)

    submitted_keys = set(request.POST.keys())
    formset_submitted = any(k.endswith('-TOTAL_FORMS') for k in submitted_keys)

    gold_item_formset = None
    if request.method == "POST" and formset_submitted:
        gold_item_formset = GoldItemFormSet(request.POST, request.FILES)
    else:
        initial_items = [
            {
                "item_name": it.item_name,
                "carat_value": it.carat_value,
                "grams": it.grams,
                "description": it.description,
            }
            for it in loan.gold_items.all()
        ]
        gold_item_formset = GoldItemFormSet(initial=initial_items)

    if request.method == "POST":
        if loan_form.is_valid():
            with transaction.atomic():
                loan = loan_form.save(commit=False)
                loan.save()

                if formset_submitted:
                    if gold_item_formset.is_valid():
                        loan.gold_items.all().delete()
                        total_grams = Decimal("0.00")
                        for f in gold_item_formset:
                            if getattr(f, "cleaned_data", None) and not f.cleaned_data.get("DELETE", False):
                                item = LoanGoldItem.objects.create(
                                    loan=loan,
                                    item_name=f.cleaned_data["item_name"],
                                    carat_value=f.cleaned_data["carat_value"],
                                    grams=f.cleaned_data["grams"],
                                    description=f.cleaned_data.get("description", ""),
                                )
                                for img_field in ("image_1", "image_2", "image_3", "image_4"):
                                    img = f.cleaned_data.get(img_field)
                                    if img:
                                        LoanGoldItemImage.objects.create(gold_item=item, image=img)
                                total_grams += item.grams or Decimal("0.00")
                        loan.total_actual_grams = total_grams
                        loan.save()
                    else:
                        messages.error(request, "Please fix the errors in items below.")
                        for i, f in enumerate(gold_item_formset.forms):
                            if f.errors:
                                messages.error(request, f"Item #{i+1} errors: {f.errors}")
                        return render(
                            request,
                            "gold_loan/loan_edit.html",
                            {"form": loan_form, "loan": loan, "gold_item_formset": gold_item_formset},
                        )

                messages.success(request, f"Payment ₹{payment_amount} recorded successfully.")
                return redirect("gold_loan:loan_detail", loan_id=loan.id)

        else:
            messages.error(request, "Please fix the errors in the loan form.")
            return render(
                request,
                "gold_loan/loan_edit.html",
                {"form": loan_form, "loan": loan, "gold_item_formset": gold_item_formset},
            )

    return render(
        request,
        "gold_loan/loan_edit.html",
        {"form": loan_form, "loan": loan, "gold_item_formset": gold_item_formset},
    )


@login_required
def loan_close(request, loan_id):
    _require_access(request)

    loan = get_object_or_404(Loan, id=loan_id)
    if request.method == 'POST':
        if hasattr(loan, 'accrue_interest_up_to'):
            try:
                loan.accrue_interest_up_to(timezone.localdate())
            except Exception:
                pass

        pending_interest = None
        if hasattr(loan, 'pending_interest'):
            pending_interest = loan.pending_interest
        elif hasattr(loan, 'interest_pending'):
            try:
                pending_interest = loan.interest_pending(timezone.localdate())
            except TypeError:
                try:
                    pending_interest = loan.interest_pending()
                except Exception:
                    pending_interest = None
            except Exception:
                pending_interest = None

        if pending_interest is None:
            pending_interest = Decimal('0.00')

        try:
            total_due = (loan.total_loan_amount + pending_interest).quantize(Decimal('0.01'))
        except Exception:
            try:
                total_due = (Decimal(loan.total_loan_amount) + Decimal(pending_interest)).quantize(Decimal('0.01'))
            except Exception:
                total_due = Decimal('1.00')

        if total_due <= Decimal('0.00'):
            loan.status = Loan.STATUS_CLOSED
            loan.save(update_fields=['status', 'updated_at'])
            return redirect('gold_loan:loan_detail', loan_id=loan.id)
        else:
            return redirect('gold_loan:loan_payment', loan_id=loan.id)

    context = {
        'loan': loan,
        'principal_remaining': loan.principal_remaining() if hasattr(loan, 'principal_remaining') else None,
        'pending_interest': getattr(loan, 'pending_interest', None),
    }
    return render(request, 'gold_loan/loan_close.html', context)


@login_required
def customer_loans(request, customer_id):
    _require_access(request)

    customer = get_object_or_404(Customer, pk=customer_id)
    loans = Loan.objects.filter(customer=customer).order_by('-created_at')

    return render(request, "gold_loan/customer_loans.html", {
        "customer": customer,
        "customer_id": customer_id,   
        "loans": loans,
    })
    
    


def home(request):
    loans = Loan.objects.all()

    pending_amount_total = sum([loan.remaining_due for loan in loans])

    context = {
        "total_loans": loans.count(),
        "customers_count": Customer.objects.count(),
        "today_collections": LoanPayment.objects.filter(
            payment_date=timezone.localdate()
        ).aggregate(total=Sum("amount"))["total"] or 0,
        "recent_loans": Loan.objects.order_by("-created_at")[:7],
        "pending_amount_total": pending_amount_total,
        "active_loans": loans.filter(status=Loan.STATUS_ACTIVE).count(),
    }
    return render(request, "gold_loan/home.html", context)


def customers(request):
    sort_option = request.GET.get("sort")
    if sort_option:
        request.session["customer_sort"] = sort_option
        return redirect("gold_loan:customers")

    sort_by = request.session.get("customer_sort", "name")

    qs = Customer.objects.annotate(
        total_loans=Count("loans"),
        has_pending=Exists(
            Loan.objects.filter(customer=OuterRef("pk"), status="Pending")
        )
    )

    # sorting
    if sort_by == "name":
        qs = qs.order_by(Lower(Trim("name")))
    elif sort_by == "date":
        qs = qs.order_by("-id")
    elif sort_by == "pending":
        qs = qs.order_by("-has_pending", Lower(Trim("name")))

    # Convert queryset → list with index for true horizontal ordering
    customers = list(qs)

    for idx, c in enumerate(customers):
        c.order_index = idx  # dynamic attribute

    return render(request, "gold_loan/customers.html", {
        "customers": customers,
        "active_sort": sort_by,
    })

    
    
    
    
# ADD LOAN FOR EXISTING CUSTOMER - STEPs
# ================================
# EXISTING CUSTOMER LOAN — STEP 1
# Product Details (Gold Items + Loan Form)
# ================================
@login_required
def add_loan_step2(request, customer_id):
    _require_access(request)
    
    if request.method == "GET":
        if "EXISTING_CUSTOMER_LOAN_ID" in request.session:
            del request.session["EXISTING_CUSTOMER_LOAN_ID"]


    customer = get_object_or_404(Customer, id=customer_id)

    loan_id = request.session.get("EXISTING_CUSTOMER_LOAN_ID")
    loan = Loan.objects.filter(id=loan_id).first() if loan_id else None

    # ---------- POST ----------
    if request.method == "POST":
        loan_form = LoanForm(request.POST, instance=loan)
        gold_formset = GoldItemFormSet(request.POST, request.FILES, prefix="items")

        if loan_form.is_valid() and gold_formset.is_valid():
            with transaction.atomic():
                loan = loan_form.save(commit=False)
                loan.customer = customer
                loan.created_by = request.user
                loan.save()

                # Remove old items
                loan.gold_items.all().delete()
                total_grams = Decimal("0.00")

                # Save new items
                for form in gold_formset:
                    if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                        item = form.save(commit=False)
                        item.loan = loan
                        item.save()

                        # Save images
                        for img_field in ("image_1", "image_2", "image_3", "image_4"):
                            img = form.cleaned_data.get(img_field)
                            if img:
                                LoanGoldItemImage.objects.create(
                                    gold_item=item, image=img
                                )

                        total_grams += item.grams or Decimal("0.00")

                loan.total_actual_grams = total_grams
                loan.save()

                request.session["EXISTING_CUSTOMER_LOAN_ID"] = loan.id

                # Go to documents upload (NEW STEP 2)
                return redirect("gold_loan:add_loan_step2", customer_id=customer.id)

        # INVALID → return back to template
        return render(
            request,
            "existing_customer_loan/add_loan_step1.html",
            {
                "customer": customer,
                "loan_form": loan_form,
                "gold_formset": gold_formset,
                "loan": loan,
                "is_existing_customer": True,
            }
        )

    # ---------- GET ----------
    loan_form = LoanForm(instance=loan)

    if loan:
        initial_items = [
        {
            "item_name": item.item_name,
            "carat_value": item.carat_value,
            "grams": item.grams,
            "description": item.description,
        }
        for item in loan.gold_items.all()
    ]
    else:
        initial_items = []

    gold_formset = GoldItemFormSet(initial=initial_items, prefix="items")

    return render(
        request,
        "existing_customer_loan/add_loan_step1.html",
        {
            "customer": customer,
            "loan_form": loan_form,
            "gold_formset": gold_formset,
            "loan": loan,
            "is_existing_customer": True,
        }
    )


# ================================
# EXISTING CUSTOMER LOAN — STEP 2
# Document Upload
# ================================
@login_required
def add_loan_step3(request, customer_id):
    _require_access(request)

    loan_id = request.session.get("EXISTING_CUSTOMER_LOAN_ID")
    if not loan_id:
        messages.error(request, "Start adding loan from Step 1.")
        return redirect("gold_loan:add_loan_step2", customer_id=customer_id)

    loan = get_object_or_404(Loan, id=loan_id)

    document_formset = DocumentFormSet(
        request.POST or None,
        request.FILES or None,
        prefix="documents"
    )

    if request.method == "POST":
        if document_formset.is_valid():
            for form in document_formset:
                if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                    doc = form.save(commit=False)
                    doc.loan = loan
                    doc.save()

            # Go to OTP (NEW STEP 3)
            return redirect("gold_loan:add_loan_step3", customer_id=customer_id)
        else:
            messages.error(request, "Please correct the document errors.")

    return render(
        request,
        "existing_customer_loan/add_loan_step2.html",
        {
            "document_formset": document_formset,
            "loan": loan,
            "customer": loan.customer,
            "is_existing_customer": True,
        }
    )


# ================================
# EXISTING CUSTOMER LOAN — STEP 3
# OTP Verification
# ================================
@login_required
def add_loan_step4(request, customer_id):
    _require_access(request)

    loan_id = request.session.get("EXISTING_CUSTOMER_LOAN_ID")
    if not loan_id:
        messages.error(request, "Complete previous steps first.")
        return redirect("gold_loan:add_loan_step2", customer_id=customer_id)

    loan = get_object_or_404(Loan, id=loan_id)

    # Pre-fill phone number
    phone_form = OTPPhoneForm(initial={"phone_number": loan.customer.mobile_number})

    if request.method == "POST":
        # Once OTP is verified (JS), finalize loan
        loan.is_submitted = True
        loan.save()
        
        
        Notification.objects.create(
        customer=loan.customer,
        loan=loan,
        type=Notification.TYPE_NEW_LOAN,
        message=f"New loan added for {loan.customer.name}. Loan No: {loan.loan_number}"
        )


        # Clear session
        if "EXISTING_CUSTOMER_LOAN_ID" in request.session:
            del request.session["EXISTING_CUSTOMER_LOAN_ID"]

        messages.success(request, "Loan successfully created.")
        return redirect("gold_loan:customer_loans", customer_id=customer_id)

    return render(
        request,
        "existing_customer_loan/add_loan_step3.html",
        {
            "loan": loan,
            "loan_id": loan.id,
            "phone_form": phone_form,
            "customer": loan.customer,
            "is_existing_customer": True,
        }
    )


# -----------------------------



from django.shortcuts import render
from django.http import JsonResponse
from .models import GoldRate

def gold_calculator_home(request):
    carat_rates = GoldRate.objects.all().order_by('carat')
    return render(request, "gold_loan/gold_calculator.html", {"carat_rates": carat_rates})


def calculate_gold_value(request):
    """AJAX API to calculate eligible amount"""
    grams = float(request.GET.get("grams", 0))
    carat = int(request.GET.get("carat", 22))

    try:
        rate = GoldRate.objects.get(carat=carat).rate_per_gram
    except GoldRate.DoesNotExist:
        return JsonResponse({"amount": 0})

    eligible_amount = grams * rate  

    return JsonResponse({"amount": eligible_amount})



#NOTIFICATION 

@login_required
def notifications(request):
    notes = Notification.objects.order_by("-created_at")
    return render(request, "gold_loan/notifications.html", {"notifications": notes})


@login_required
def notifications_list(request):
    notifications = Notification.objects.select_related("customer", "loan")\
                        .order_by("-created_at")

    return render(request, "gold_loan/notifications.html", {
        "notifications": notifications
    })


def generate_overdue_notifications():
    today = timezone.localdate()
    loans = Loan.objects.filter(status=Loan.STATUS_ACTIVE)

    for loan in loans:
        last_payment = loan.payments.order_by('-payment_date').first()

        if not last_payment:
            continue  # skip loans with no payments at all

        days_since = (today - last_payment.payment_date).days

        if days_since >= 28:
            Notification.objects.get_or_create(
                customer=loan.customer,
                loan=loan,
                type=Notification.TYPE_OVERDUE,
                message=f"{loan.customer.name} has not made a payment in {days_since} days."
            )
