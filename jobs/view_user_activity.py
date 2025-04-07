from nautobot.apps.jobs import Job, register_jobs
from nautobot.extras.models import ObjectChange
from django.utils.timezone import now
from collections import defaultdict
from datetime import timedelta


class WeeklyChangeLogAudit(Job):
    """Report on users who made changes this calendar week."""

    class Meta:
        name = "Weekly Change Log Report"
        description = "Report on users who made changes this calendar week."
        #read_only = True
        hidden = True

    def run(self):
        today = now().date()
        start_of_week = today - timedelta(days=today.weekday()) 
        end_of_week = start_of_week + timedelta(days=7)

        changes = ObjectChange.objects.filter(
            time__date__gte=start_of_week,
            time__date__lt=end_of_week,
        )
        excluded_users = {"DworaczykBlakeD", "bdd4329"}
        user_changes = defaultdict(int)
 
        for change in changes:
            user = change.user_name or "System/Script"
            if user in excluded_users:
                continue            
            user_changes[user] += 1

        if not user_changes:
            self.logger.success("No changes were recorded this week.")
            return "No user changes to report."

        self.logger.info("### Weekly Change Log Summary ####")
        for user, count in user_changes.items():
            self.logger.info(f"👤 {user} — {count} change(s)")

        return f"Weekly change log review complete. {len(user_changes)} user(s) made changes."


register_jobs(WeeklyChangeLogAudit)
