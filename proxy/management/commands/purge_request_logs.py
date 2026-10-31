from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from proxy.models import RequestLog


class Command(BaseCommand):
    help = "Delete request logs older than the configured retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=settings.REQUEST_LOG_RETENTION_DAYS,
            help="Keep logs from this many recent days (default: configured retention).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the number of logs that would be deleted without deleting them.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be at least 1")

        cutoff = timezone.now() - timedelta(days=days)
        old_logs = RequestLog.objects.filter(started_at__lt=cutoff)
        count = old_logs.count()
        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} request log(s) older than {days} days.")
            return

        deleted, _ = old_logs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} record(s) older than {days} days."))
