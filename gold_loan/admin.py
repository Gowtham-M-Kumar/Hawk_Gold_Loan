from django.contrib import admin

from .models import (
    AppAccess,
    Customer,
    CustomerDocument,
    Loan,
    LoanAmountLog,
    LoanClosure,
    LoanClosureDocument,
    LoanDocument,
    LoanGoldItem,
    LoanGoldItemImage,
    LoanPayment,
    OTPRequest,
)


# ================================
# INLINE MODELS
# ================================
class CustomerDocumentInline(admin.TabularInline):
    model = CustomerDocument
    extra = 0
    readonly_fields = ("created_at",)


class LoanDocumentInline(admin.TabularInline):
    model = LoanDocument
    extra = 0
    readonly_fields = ("created_at",)


class LoanGoldItemImageInline(admin.TabularInline):
    model = LoanGoldItemImage
    extra = 0
    readonly_fields = ("created_at",)


class LoanGoldItemInline(admin.TabularInline):
    model = LoanGoldItem
    extra = 0


class LoanPaymentInline(admin.TabularInline):
    model = LoanPayment
    extra = 0
    readonly_fields = ("receipt_number", "created_at")


class LoanClosureDocumentInline(admin.TabularInline):
    model = LoanClosureDocument
    extra = 0
    readonly_fields = ("created_at",)


# ================================
# CUSTOMER ADMIN
# ================================
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "mobile_number", "aadhaar_number", "created_at")
    search_fields = ("name", "mobile_number", "aadhaar_number")
    list_filter = ("created_at",)
    inlines = [CustomerDocumentInline]


# ================================
# LOAN ADMIN
# ================================
@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "loan_number",
        "customer",
        "total_loan_amount",
        "pending_interest",
        "status",
        "created_at",
    )
    search_fields = ("loan_number", "customer__name", "customer__mobile_number")
    list_filter = ("status", "created_at")
    ordering = ("-created_at",)

    readonly_fields = (
        "loan_number",
        "total_interest_accrued",
        "last_interest_calculated_date",
        "created_at",
        "updated_at",
    )

    # FIX: Removed LoanClosureDocumentInline (invalid for Loan)
    inlines = [
        LoanDocumentInline,
        LoanGoldItemInline,
        LoanPaymentInline,
    ]


# ================================
# LOAN PAYMENT ADMIN
# ================================
@admin.register(LoanPayment)
class LoanPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "loan",
        "payment_date",
        "amount",
        "interest_component",
        "principal_component",
        "medium",
        "receipt_number",
    )
    list_filter = ("medium", "payment_date")
    search_fields = ("loan__loan_number", "receipt_number")
    readonly_fields = ("receipt_number", "created_at")


# ================================
# LOAN DOCUMENT ADMIN
# ================================
@admin.register(LoanDocument)
class LoanDocumentAdmin(admin.ModelAdmin):
    list_display = ("loan", "document_type", "created_at")
    list_filter = ("document_type",)
    search_fields = ("loan__loan_number",)


# ================================
# GOLD ITEM + IMAGES ADMIN
# ================================
@admin.register(LoanGoldItem)
class LoanGoldItemAdmin(admin.ModelAdmin):
    list_display = ("loan", "item_name", "carat_value", "grams")
    search_fields = ("item_name", "loan__loan_number")
    list_filter = ("carat_value",)
    inlines = [LoanGoldItemImageInline]


@admin.register(LoanGoldItemImage)
class LoanGoldItemImageAdmin(admin.ModelAdmin):
    list_display = ("gold_item", "image", "created_at")
    search_fields = ("gold_item__item_name",)


# ================================
# LOAN AMOUNT LOG ADMIN
# ================================
@admin.register(LoanAmountLog)
class LoanAmountLogAdmin(admin.ModelAdmin):
    list_display = ("loan", "log_date", "amount", "medium")
    list_filter = ("medium", "log_date")
    search_fields = ("loan__loan_number",)


# ================================
# LOAN CLOSURE ADMIN
# ================================
@admin.register(LoanClosure)
class LoanClosureAdmin(admin.ModelAdmin):
    list_display = ("loan", "closed_by", "confirmed", "created_at")
    list_filter = ("confirmed", "created_at")
    search_fields = ("loan__loan_number",)
    inlines = [LoanClosureDocumentInline]  # ✔ correct inline here


# ================================
# LOAN CLOSURE DOCUMENT ADMIN
# ================================
@admin.register(LoanClosureDocument)
class LoanClosureDocumentAdmin(admin.ModelAdmin):
    list_display = ("closure", "document_type", "created_at")
    search_fields = ("closure__loan__loan_number",)


# ================================
# APP ACCESS ADMIN
# ================================
@admin.register(AppAccess)
class AppAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "app_label")
    list_filter = ("app_label",)
    search_fields = ("user__username", "app_label")


# ================================
# OTP REQUEST ADMIN
# ================================
@admin.register(OTPRequest)
class OTPRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "target_phone", "created_at", "verified_at")
    list_filter = ("purpose", "verified_at")
    search_fields = ("user__username", "target_phone")
