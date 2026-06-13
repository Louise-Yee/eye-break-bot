import discord
from discord import app_commands
from discord.ui import Select, View, Modal, TextInput
import sqlite3
import asyncio
from datetime import datetime
import pytz
import os
from dotenv import load_dotenv
load_dotenv()

# --- CONFIG ---
BOT_TOKEN = os.environ["BOT_TOKEN"]
REMINDER_CHANNEL_ID = int(os.environ.get("REMINDER_CHANNEL_ID", "1515210070550384792"))
REMINDER_INTERVAL_MINUTES = 20
# --------------

DB = "schedules.db"

TIMEZONES = [
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


def init_db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            user_id INTEGER PRIMARY KEY,
            timezone TEXT,
            start_time TEXT,
            end_time TEXT
        )
    """)
    con.commit()
    con.close()


def save_schedule(user_id, timezone, start_time, end_time):
    con = sqlite3.connect(DB)
    con.execute("""
        INSERT INTO schedules (user_id, timezone, start_time, end_time)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            timezone=excluded.timezone,
            start_time=excluded.start_time,
            end_time=excluded.end_time
    """, (user_id, timezone, start_time, end_time))
    con.commit()
    con.close()


def remove_schedule(user_id):
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM schedules WHERE user_id = ?", (user_id,))
    con.commit()
    con.close()


def get_all_schedules():
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT user_id, timezone, start_time, end_time FROM schedules").fetchall()
    con.close()
    return rows


def is_within_work_hours(timezone, start_time, end_time):
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    current = now.strftime("%H:%M")
    return start_time <= current <= end_time


class WorkHoursModal(Modal, title="Set Work Hours"):
    start = TextInput(label="Start time (HH:MM, 24h)", placeholder="09:00")
    end = TextInput(label="End time (HH:MM, 24h)", placeholder="18:00")

    def __init__(self, tz_name, tz_label):
        super().__init__()
        self.tz_name = tz_name
        self.tz_label = tz_label

    async def on_submit(self, interaction: discord.Interaction):
        start = self.start.value.strip()
        end = self.end.value.strip()
        try:
            datetime.strptime(start, "%H:%M")
            datetime.strptime(end, "%H:%M")
        except ValueError:
            await interaction.response.send_message(
                "Invalid time format. Use HH:MM (e.g. 09:00).", ephemeral=True
            )
            return
        save_schedule(interaction.user.id, self.tz_name, start, end)
        await interaction.response.send_message(
            f"Saved. You'll be reminded every {REMINDER_INTERVAL_MINUTES} min "
            f"between {start} and {end} ({self.tz_label}).",
            ephemeral=True,
        )


class TimezoneSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=label, value=tz)
            for label, tz in TIMEZONES
        ]
        super().__init__(placeholder="Select your timezone", options=options)

    async def callback(self, interaction: discord.Interaction):
        tz_value = self.values[0]
        tz_label = next(label for label, tz in TIMEZONES if tz == tz_value)
        modal = WorkHoursModal(tz_name=tz_value, tz_label=tz_label)
        await interaction.response.send_modal(modal)


class TimezoneView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(TimezoneSelect())


intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tree.command(name="timeon", description="Set your work hours for eye break reminders")
async def timeon(interaction: discord.Interaction):
    view = TimezoneView()
    await interaction.response.send_message(
        "Step 1: Select your timezone.", view=view, ephemeral=True
    )


@tree.command(name="timeoff", description="Stop receiving eye break reminders")
async def timeoff(interaction: discord.Interaction):
    remove_schedule(interaction.user.id)
    await interaction.response.send_message(
        "Removed. You won't receive reminders anymore.", ephemeral=True
    )


async def reminder_loop():
    await client.wait_until_ready()
    channel = client.get_channel(REMINDER_CHANNEL_ID)
    while not client.is_closed():
        await asyncio.sleep(REMINDER_INTERVAL_MINUTES * 60)
        if channel is None:
            continue
        schedules = get_all_schedules()
        mentions = []
        for user_id, timezone, start_time, end_time in schedules:
            if is_within_work_hours(timezone, start_time, end_time):
                mentions.append(f"<@{user_id}>")
        if mentions:
            await channel.send(
                " ".join(mentions) +
                " Eye break! Look 20 feet away for 20 seconds. (20-20-20 rule)"
            )


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")
    client.loop.create_task(reminder_loop())


init_db()
client.run(BOT_TOKEN)
