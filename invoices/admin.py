from django.contrib import admin

from .models import Company, ImportLog, Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in InvoiceItem._meta.fields]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["number", "series", "issue_date", "issuer", "recipient", "invoice_total"]
    list_filter = ["issue_date", "status_code", "issuer__state"]
    search_fields = ["access_key", "issuer__name", "issuer__document", "recipient__name"]
    list_select_related = ["issuer", "recipient"]
    date_hierarchy = "issue_date"
    inlines = [InvoiceItemInline]
    exclude = ["xml"]
    readonly_fields = [f.name for f in Invoice._meta.fields if f.name != "xml"]


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "document", "kind", "city", "state"]
    list_filter = ["kind", "state"]
    search_fields = ["name", "trade_name", "document"]


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "filename", "status", "error_code"]
    list_filter = ["status", "error_code"]
    search_fields = ["filename", "access_key"]
