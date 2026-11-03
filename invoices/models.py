from django.db import models


class Company(models.Model):
    """An issuer or recipient, identified by CNPJ (14 chars) or CPF (11 digits)."""

    class Kind(models.TextChoices):
        CNPJ = "cnpj", "CNPJ"
        CPF = "cpf", "CPF"

    document = models.CharField(max_length=14, unique=True)
    kind = models.CharField(max_length=4, choices=Kind.choices)
    name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    state_registration = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return f"{self.name} ({self.document})"


class Invoice(models.Model):
    class Direction(models.IntegerChoices):
        INBOUND = 0, "Entrada"
        OUTBOUND = 1, "Saída"

    access_key = models.CharField(max_length=44, unique=True)
    model = models.CharField(max_length=2)  # 55 = NF-e, 65 = NFC-e
    series = models.PositiveIntegerField()
    number = models.PositiveIntegerField()
    issued_at = models.DateTimeField()
    # Fiscal date as written by the issuer (dhEmi in its own UTC offset). Monthly reports
    # group on this field, so they don't depend on the database's time zone tables.
    issue_date = models.DateField(db_index=True)
    operation_nature = models.CharField(max_length=60)
    direction = models.PositiveSmallIntegerField(choices=Direction.choices)
    issuer = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="issued_invoices")
    recipient = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="received_invoices", null=True, blank=True
    )
    products_total = models.DecimalField(max_digits=15, decimal_places=2)
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    freight_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    invoice_total = models.DecimalField(max_digits=15, decimal_places=2)
    authorization_protocol = models.CharField(max_length=20, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)  # cStat, 100 = authorized
    xml_sha256 = models.CharField(max_length=64, unique=True)
    xml = models.TextField(help_text="Original XML, kept for audit (the legal record).")
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issue_date", "-number"]
        indexes = [models.Index(fields=["issuer", "issue_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["issuer", "model", "series", "number"], name="unique_invoice_number"
            )
        ]

    def __str__(self) -> str:
        return f"NF-e {self.number}/{self.series} {self.issuer.name}"


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    item_number = models.PositiveSmallIntegerField()
    product_code = models.CharField(max_length=60)
    description = models.CharField(max_length=120)
    ncm = models.CharField(max_length=8, db_index=True)
    cfop = models.CharField(max_length=4)
    unit = models.CharField(max_length=6)
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit_price = models.DecimalField(max_digits=21, decimal_places=10)
    total = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        ordering = ["item_number"]
        constraints = [
            models.UniqueConstraint(fields=["invoice", "item_number"], name="unique_item_number")
        ]

    def __str__(self) -> str:
        return f"{self.item_number}: {self.description}"


class ImportLog(models.Model):
    class Status(models.TextChoices):
        CREATED = "created"
        DUPLICATE = "duplicate"
        ERROR = "error"

    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices)
    error_code = models.CharField(max_length=40, blank=True)
    message = models.TextField(blank=True)
    access_key = models.CharField(max_length=44, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.filename}: {self.status}"
