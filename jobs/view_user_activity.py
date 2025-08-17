from nautobot.apps.jobs import Job, register_jobs, ChoiceVar, StringVar
from nautobot.extras.models import ObjectChange
from django.utils.timezone import now
from collections import defaultdict
from datetime import datetime, timedelta


class UserChangeLogAudit(Job):
    """Report on users who made changes during a selected period."""

    class Meta:
        name = "User Change Log Report"
        description = "Report on users who made changes today, this week, or over a custom date range."
        hidden = True

    run_type = ChoiceVar(
        choices=[
            ("daily", "Daily (8AM–now)"),
            ("weekly", "Weekly (Mon–now)"),
            ("custom", "Custom Date Range")
        ],
        label="Report Type",
        description="Choose daily, weekly, or a custom date range.",
        default="weekly",
    )

    start_date = StringVar(
        label="Start Date",
        description="Start date in YYYY-MM-DD format (only used for custom mode)",
        required=False,
    )

    end_date = StringVar(
        label="End Date",
        description="End date in YYYY-MM-DD format (only used for custom mode)",
        required=False,
    )

    def run(self, run_type, start_date, end_date):
        now_ts = now()
        today = now_ts.date()

        if run_type == "weekly":
            start = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time()).astimezone()
            end = now_ts
            self.logger.info(f"Weekly mode — checking from {start} to {end}")

        elif run_type == "daily":
            start = datetime.combine(today, datetime.min.time()).replace(hour=8).astimezone()
            end = now_ts
            self.logger.info(f"Daily mode — checking from {start} to {end}")

        elif run_type == "custom":
            if not start_date or not end_date:
                self.logger.error("Custom mode selected but start or end date not provided.")
                return "Please provide both start and end dates for custom mode."

            try:
                start = datetime.strptime(start_date, "%Y-%m-%d").astimezone()
                end = datetime.strptime(end_date, "%Y-%m-%d").astimezone() + timedelta(days=1)
            except ValueError:
                self.logger.error("Date format invalid. Use YYYY-MM-DD.")
                return "Invalid date format. Please use YYYY-MM-DD."

            self.logger.info(f"Custom mode — checking from {start} to {end}")

        else:
            return "Invalid report type."

        # Query changes
        changes = ObjectChange.objects.filter(time__gte=start, time__lt=end)
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

        return f"Change log complete. {len(user_changes)} user(s) made changes."


register_jobs(UserChangeLogAudit)
