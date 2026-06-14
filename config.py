import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
REMINDER_CHANNEL_ID: int = int(os.environ.get("REMINDER_CHANNEL_ID", "1515210070550384792"))
REMINDER_INTERVAL_MINUTES: int = 20
OWNER_ID: int = 315109913632440321
GUILD_ID: int = 1515210069480833125
ADMIN_ROLE_ID: int | None = int(os.environ["ADMIN_ROLE_ID"]) if os.environ.get("ADMIN_ROLE_ID") else None

TIMEZONES: list[tuple[str, str]] = [
    ("Malaysia (GMT+8)", "Asia/Kuala_Lumpur"),
    ("Singapore (GMT+8)", "Asia/Singapore"),
    ("Indonesia WIB (GMT+7)", "Asia/Jakarta"),
    ("Philippines (GMT+8)", "Asia/Manila"),
    ("Japan (GMT+9)", "Asia/Tokyo"),
    ("India (GMT+5:30)", "Asia/Kolkata"),
    ("UAE (GMT+4)", "Asia/Dubai"),
    ("UK (GMT+0/+1)", "Europe/London"),
    ("Germany (GMT+1/+2)", "Europe/Berlin"),
    ("US Eastern (GMT-5/-4)", "America/New_York"),
    ("US Central (GMT-6/-5)", "America/Chicago"),
    ("US Pacific (GMT-8/-7)", "America/Los_Angeles"),
    ("Australia Sydney (GMT+10/+11)", "Australia/Sydney"),
]
