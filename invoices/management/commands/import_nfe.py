from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from invoices.services import import_nfe


class Command(BaseCommand):
    help = "Import NF-e XML files from files or directories (recursively)."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", type=Path)

    def handle(self, *args, paths, **options):
        files = []
        for path in paths:
            if path.is_dir():
                files += sorted(path.rglob("*.xml"))
            elif path.is_file():
                files.append(path)
            else:
                raise CommandError(f"{path} does not exist")

        summary = Counter()
        for file in files:
            result = import_nfe(file.read_bytes(), file.name)
            summary[result.status] += 1
            if result.status == "error":
                self.stderr.write(f"{file}: {result.error_code}: {result.message}")
            elif options["verbosity"] > 1:
                self.stdout.write(f"{file}: {result.status}")
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(files)} files: {summary['created']} created, "
                f"{summary['duplicate']} duplicates, {summary['error']} errors"
            )
        )
