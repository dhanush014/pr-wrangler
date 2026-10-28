"""Re-plan the whole review queue every weekday morning, before the team starts reviewing."""

from managed_deepagents import define_schedule

schedule = define_schedule(
    cron="0 9 * * 1-5",
    timezone="America/New_York",
    prompt="Wrangle the queue.",
)
