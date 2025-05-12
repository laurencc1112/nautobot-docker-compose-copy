from nautobot.apps.jobs import Job, register_jobs, ChoiceVar
from nautobot.extras.models import ObjectChange
from django.utils.timezone import now
from collections import defaultdict
from datetime import datetime, timedelta


class UserChangeLogAudit(Job):
    """Report on users who made changes this calendar week or day."""

    class Meta:
        name = "User Change Log Report"
        description = "Report on users who made changes today or this week."
        hidden = True

    # Add a choice variable to select run type
    run_type = ChoiceVar(
        choices=[("daily", "Daily"), ("weekly", "Weekly")],
        label="Report Type",
        description="Choose whether to report on changes today (8AM–now) or this week (Mon–now)",
        default="weekly"
    )

    def run(self, run_type):
        now_ts = now()
        today = now_ts.date()

        # Set time bounds depending on mode
        if run_type == "weekly":
            start = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time()).astimezone()
            end = now_ts
            self.logger.info(f" Weekly mode selected — reviewing changes from {start} to {end}")
        else:  # daily
            start = datetime.combine(today, datetime.min.time()).replace(hour=8).astimezone()
            end = now_ts
            self.logger.info(f" Daily mode selected — reviewing changes from {start} to {end}")

        # Query changes
        changes = ObjectChange.objects.filter(
            time__gte=start,
            time__lt=end,
        )

        excluded_users = {"DworaczykBlakeD", "bdd4329"}
        user_changes = defaultdict(int)

        for change in changes:
            user = change.user_name or "System/Script"
            if user in excluded_users:
                continue
            user_changes[user] += 1

        if not user_changes:
            self.logger.success("No changes were recorded.")
            return "No user changes to report."

        self.logger.info("#################### Change Log Summary ####################")
        for user, count in user_changes.items():
            self.logger.info(f"👤 {user} — {count} change(s)")

        return f" Change log complete. {len(user_changes)} user(s) made changes."


register_jobs(UserChangeLogAudit)
