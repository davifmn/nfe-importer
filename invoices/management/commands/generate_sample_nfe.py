from pathlib import Path

from django.core.management.base import BaseCommand

from invoices.nfe.samples import generate_batch


class Command(BaseCommand):
    help = "Write synthetic (fictitious) NF-e XML files for demos and load tests."

    def add_arguments(self, parser):
        parser.add_argument("directory", type=Path)
        parser.add_argument("--count", type=int, default=50)
        parser.add_argument("--seed", type=int, default=2026)

    def handle(self, *args, directory, count, seed, **options):
        directory.mkdir(parents=True, exist_ok=True)
        for name, xml in generate_batch(count, seed=seed):
            (directory / name).write_bytes(xml)
        self.stdout.write(self.style.SUCCESS(f"wrote {count} NF-e files to {directory}"))
