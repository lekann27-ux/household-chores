from django.core.management.base import BaseCommand

from chores.services.assignments import mark_overdue_assignments


class Command(BaseCommand):
    help = 'Mark pending chore assignments overdue when their due date has passed.'

    def handle(self, *args, **options):
        count = mark_overdue_assignments()
        self.stdout.write(self.style.SUCCESS(f'Marked {count} assignment(s) overdue.'))
