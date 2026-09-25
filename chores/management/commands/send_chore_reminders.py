from django.core.management.base import BaseCommand

from chores.services.notifications import generate_due_reminders


class Command(BaseCommand):
    help = 'Create in-app reminders for active chores due today.'

    def handle(self, *args, **options):
        count = generate_due_reminders()
        self.stdout.write(self.style.SUCCESS(f'Created {count} due reminder(s).'))
