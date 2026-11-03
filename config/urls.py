from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from invoices import views

router = DefaultRouter()
router.register("invoices", views.InvoiceViewSet, basename="invoice")
router.register("companies", views.CompanyViewSet, basename="company")
router.register("import-logs", views.ImportLogViewSet, basename="import-log")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health, name="health"),
    path("api/auth/token/", obtain_auth_token, name="api-token"),
    path("api/imports/", views.ImportView.as_view(), name="imports"),
    path("api/reports/top-products/", views.top_products, name="report-top-products"),
    path("api/reports/monthly/", views.monthly_totals, name="report-monthly"),
    path("api/reports/by-state/", views.sales_by_state, name="report-by-state"),
    path("api/", include(router.urls)),
]
