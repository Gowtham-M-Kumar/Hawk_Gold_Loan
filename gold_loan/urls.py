from django.urls import path
from . import views

app_name = 'gold_loan'

urlpatterns = [

    # HOME + DASHBOARD
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),

    # CUSTOMER SEARCH
    path("search/customers/", views.search_customers, name="search_customers"),

    # CUSTOMER PAGES
    path("customers/", views.customers, name="customers"),
    path("customers/<int:customer_id>/loans/", views.customer_loans, name="customer_loans"),

    # LOAN ENTRY WIZARD (4-Steps)
    path('loan/new/personal/', views.loan_entry_step1, name='loan_entry_step1'),
    path('loan/new/product/', views.loan_entry_step2, name='loan_entry_step2'),
    path('loan/new/documents/', views.loan_entry_step3, name='loan_entry_step3'),
    path('loan/new/otp/', views.loan_entry_step4, name='loan_entry_step4'),

    # LOAN DETAIL & ACTIONS
    path('loan/<int:loan_id>/', views.loan_detail, name='loan_detail'),
    path('loan/<int:loan_id>/payments/', views.loan_payment, name='loan_payment'),
    path('loan/<int:loan_id>/edit/', views.loan_edit, name='loan_edit'),
    path('loan/<int:loan_id>/close/', views.loan_close, name='loan_close'),
    
    # ADD LOAN FOR EXISTING CUSTOMER
    path("loan/existing/<int:customer_id>/step2/", views.add_loan_step2, name="add_loan_step2"),
    path("loan/existing/<int:customer_id>/step3/", views.add_loan_step3, name="add_loan_step3"),
    path("loan/existing/<int:customer_id>/step4/", views.add_loan_step4, name="add_loan_step4"),

]