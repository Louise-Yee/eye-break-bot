import discord
from discord import app_commands
from discord.ui import Select, View, Modal, TextInput, Button
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
OWNER_ID = 315109913632440321
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
    con.execute("""
        CREATE TABLE IF NOT EXISTS clock_status (
            user_id INTEGER PRIMARY KEY,
            clocked_in INTEGER DEFAULT 0,
            breaks_taken INTEGER DEFAULT 0,
            breaks_missed INTEGER DEFAULT 0
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
    con.execute("DELETE FROM clock_status WHERE user_id = ?", (user_id,))
    con.commit()
    con.close()


def get_all_schedules():
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT user_id, timezone, start_time, end_time FROM schedules").fetchall()
    con.close()
    return rows


def set_clocked_in(user_id, value: bool):
    con = sqlite3.connect(DB)
    con.execute("""
        INSERT INTO clock_status (user_id, clocked_in, breaks_taken, breaks_missed)
        VALUES (?, ?, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET clocked_in=excluded.clocked_in
    """, (user_id, 1 if value else 0))
    con.commit()
    con.close()


def reset_breaks(user_id):
    con = sqlite3.connect(DB)
    con.execute("""
        INSERT INTO clock_status (user_id, clocked_in, breaks_taken, breaks_missed)
        VALUES (?, 1, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET breaks_taken=0, breaks_missed=0
    """, (user_id,))
    con.commit()
    con.close()


def record_break(user_id, took: bool):
    col = "breaks_taken" if took else "breaks_missed"
    con = sqlite3.connect(DB)
    con.execute(f"""
        INSERT INTO clock_status (user_id, clocked_in, breaks_taken, breaks_missed)
        VALUES (?, 1, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET {col}={col}+1
    """, (user_id,))
    con.commit()
    con.close()


def get_clock_status(user_id):
    con = sqlite3.connect(DB)
    row = con.execute(
        "SELECT clocked_in, breaks_taken, breaks_missed FROM clock_status WHERE user_id=?",
        (user_id,)
    ).fetchone()
    con.close()
    return row or (0, 0, 0)


def get_clocked_in_users():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT user_id FROM clock_status WHERE clocked_in=1"
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def is_within_work_hours(timezone, start_time, end_time):
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    current = now.strftime("%H:%M")
    return start_time <= current <= end_time


def get_current_time_str(timezone):
    tz = pytz.timezone(timezone)
    return datetime.now(tz).strftime("%H:%M")


# --- Views ---

class ClockInView(View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Yes, clock in", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return
        set_clocked_in(self.user_id, True)
        reset_breaks(self.user_id)
        self.stop()
        await interaction.response.edit_message(
            content=f"<@{self.user_id}> clocked in. Break reminders started.",
            view=None
        )

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(
            content=f"<@{self.user_id}> skipped clock-in.",
            view=None
        )


class BreakView(View):
    def __init__(self, user_ids):
        super().__init__(timeout=300)
        self.user_ids = set(user_ids)
        self.responded = set()

    async def on_timeout(self):
        for user_id in self.user_ids:
            if user_id not in self.responded:
                record_break(user_id, took=False)

    @discord.ui.button(label="Yes, took break", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in self.user_ids:
            await interaction.response.send_message("You are not in the current break group.", ephemeral=True)
            return
        if interaction.user.id in self.responded:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.responded.add(interaction.user.id)
        record_break(interaction.user.id, took=True)
        await interaction.response.send_message("Great! Keep it up.", ephemeral=True)

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in self.user_ids:
            await interaction.response.send_message("You are not in the current break group.", ephemeral=True)
            return
        if interaction.user.id in self.responded:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.responded.add(interaction.user.id)
        record_break(interaction.user.id, took=False)
        await interaction.response.send_message("Try to take the next one!", ephemeral=True)


# --- Modals / Selects ---

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
            f"Saved. Clock-in prompt at {start}, reminders every {REMINDER_INTERVAL_MINUTES} min until {end} ({self.tz_label}).",
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


# --- Bot ---

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Track which users got a clock-in prompt this minute (avoid duplicates)
clock_in_prompted = set()


@tree.command(name="timeon", description="Set your work hours for eye break reminders")
async def timeon(interaction: discord.Interaction):
    view = TimezoneView()
    await interaction.response.send_message(
        "Step 1: Select your timezone.", view=view, ephemeral=True
    )


@tree.command(name="timeoff", description="Stop receiving eye break reminders")
async def timeoff(interaction: discord.Interaction):
    set_clocked_in(interaction.user.id, False)
    remove_schedule(interaction.user.id)
    await interaction.response.send_message(
        "Removed. You won't receive reminders anymore.", ephemeral=True
    )


@tree.command(name="status", description="See who is clocked in and their break stats")
async def status(interaction: discord.Interaction):
    schedules = get_all_schedules()
    if not schedules:
        await interaction.response.send_message("No users registered.", ephemeral=True)
        return

    embed = discord.Embed(title="Work Status", color=discord.Color.blue())
    for user_id, timezone, start_time, end_time in schedules:
        clocked_in, breaks_taken, breaks_missed = get_clock_status(user_id)
        current_time = get_current_time_str(timezone)
        tz_label = next((l for l, t in TIMEZONES if t == timezone), timezone)
        status_icon = "🟢" if clocked_in else "⚪"
        embed.add_field(
            name=f"{status_icon} <@{user_id}>",
            value=(
                f"Hours: {start_time}–{end_time} ({tz_label})\n"
                f"Current time: {current_time}\n"
                f"Breaks taken: {breaks_taken} | Missed: {breaks_missed}"
            ),
            inline=False,
        )
    await interaction.response.send_message(embed=embed)


def owner_only(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_ID


@tree.command(name="admin_clockin", description="[Owner] Manually clock in a user")
@app_commands.check(owner_only)
async def admin_clockin(interaction: discord.Interaction, user: discord.Member):
    set_clocked_in(user.id, True)
    reset_breaks(user.id)
    channel = client.get_channel(REMINDER_CHANNEL_ID)
    if channel:
        view = ClockInView(user.id)
        await channel.send(f"<@{user.id}> manually clocked in by admin.", view=None)
    await interaction.response.send_message(f"{user.display_name} clocked in.", ephemeral=True)


@tree.command(name="admin_clockout", description="[Owner] Manually clock out a user")
@app_commands.check(owner_only)
async def admin_clockout(interaction: discord.Interaction, user: discord.Member):
    set_clocked_in(user.id, False)
    channel = client.get_channel(REMINDER_CHANNEL_ID)
    if channel:
        await channel.send(f"<@{user.id}> manually clocked out by admin.")
    await interaction.response.send_message(f"{user.display_name} clocked out.", ephemeral=True)


@tree.command(name="admin_test", description="[Owner] Fire a break reminder immediately")
@app_commands.check(owner_only)
async def admin_test(interaction: discord.Interaction):
    channel = client.get_channel(REMINDER_CHANNEL_ID)
    clocked_in_users = get_clocked_in_users()
    if not clocked_in_users:
        await interaction.response.send_message("No users clocked in.", ephemeral=True)
        return
    mentions = " ".join(f"<@{uid}>" for uid in clocked_in_users)
    view = BreakView(set(clocked_in_users))
    await channel.send(
        f"{mentions} Eye break! Look 20 feet away for 20 seconds. Did you take your break?",
        view=view
    )
    await interaction.response.send_message("Test reminder sent.", ephemeral=True)


@admin_clockin.error
@admin_clockout.error
@admin_test.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("Owner only.", ephemeral=True)


async def background_loop():
    await client.wait_until_ready()
    channel = client.get_channel(REMINDER_CHANNEL_ID)
    last_break_minute = -1

    while not client.is_closed():
        await asyncio.sleep(30)

        if channel is None:
            channel = client.get_channel(REMINDER_CHANNEL_ID)
            continue

        schedules = get_all_schedules()
        now_utc = datetime.utcnow()

        for user_id, timezone, start_time, end_time in schedules:
            tz = pytz.timezone(timezone)
            now_local = datetime.now(tz)
            current = now_local.strftime("%H:%M")

            # Clock-in prompt at start time
            if current == start_time and user_id not in clock_in_prompted:
                clock_in_prompted.add(user_id)
                set_clocked_in(user_id, False)
                view = ClockInView(user_id)
                await channel.send(
                    f"<@{user_id}> It's {start_time} — time to start work. Clock in?",
                    view=view
                )

            # Auto clock-out at end time
            if current == end_time:
                clocked_in, _, _ = get_clock_status(user_id)
                if clocked_in:
                    set_clocked_in(user_id, False)
                    await channel.send(f"<@{user_id}> Work hours ended. Clocked out. Good work today!")
                clock_in_prompted.discard(user_id)

            # Reset prompt tracker at midnight
            if current == "00:00":
                clock_in_prompted.discard(user_id)

        # Break reminder every 20 min (on the minute mark)
        current_minute = now_utc.hour * 60 + now_utc.minute
        if current_minute % REMINDER_INTERVAL_MINUTES == 0 and current_minute != last_break_minute:
            last_break_minute = current_minute
            clocked_in_users = get_clocked_in_users()
            if clocked_in_users:
                mentions = " ".join(f"<@{uid}>" for uid in clocked_in_users)
                view = BreakView(set(clocked_in_users))
                await channel.send(
                    f"{mentions} Eye break! Look 20 feet away for 20 seconds. Did you take your break?",
                    view=view
                )


MY_GUILD = discord.Object(id=1515210069480833125)

@client.event
async def on_ready():
    tree.copy_global_to(guild=MY_GUILD)
    await tree.sync(guild=MY_GUILD)
    print(f"Logged in as {client.user}")
    client.loop.create_task(background_loop())


init_db()
client.run(BOT_TOKEN)
