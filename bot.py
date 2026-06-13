import discord
from discord import app_commands
from discord.ui import Select, View, Modal, TextInput, Button
import asyncio
from datetime import datetime
import pytz
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import audit_logger as audit
load_dotenv()

# --- CONFIG ---
BOT_TOKEN = os.environ["BOT_TOKEN"]
REMINDER_CHANNEL_ID = int(os.environ.get("REMINDER_CHANNEL_ID", "1515210070550384792"))
REMINDER_INTERVAL_MINUTES = 20
OWNER_ID = 315109913632440321
DATABASE_URL = os.environ["DATABASE_URL"]
# --------------

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


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    con = get_conn()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            user_id BIGINT PRIMARY KEY,
            timezone TEXT,
            start_time TEXT,
            end_time TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clock_status (
            user_id BIGINT PRIMARY KEY,
            clocked_in BOOLEAN DEFAULT FALSE,
            breaks_taken INTEGER DEFAULT 0,
            breaks_missed INTEGER DEFAULT 0
        )
    """)
    con.commit()
    cur.close()
    con.close()


def save_schedule(user_id, timezone, start_time, end_time):
    con = get_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO schedules (user_id, timezone, start_time, end_time)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT(user_id) DO UPDATE SET
            timezone=EXCLUDED.timezone,
            start_time=EXCLUDED.start_time,
            end_time=EXCLUDED.end_time
    """, (user_id, timezone, start_time, end_time))
    con.commit()
    cur.close()
    con.close()


def remove_schedule(user_id):
    con = get_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM schedules WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM clock_status WHERE user_id = %s", (user_id,))
    con.commit()
    cur.close()
    con.close()


def get_all_schedules():
    con = get_conn()
    cur = con.cursor()
    cur.execute("SELECT user_id, timezone, start_time, end_time FROM schedules")
    rows = cur.fetchall()
    cur.close()
    con.close()
    return rows


def set_clocked_in(user_id, value: bool):
    con = get_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO clock_status (user_id, clocked_in, breaks_taken, breaks_missed)
        VALUES (%s, %s, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET clocked_in=EXCLUDED.clocked_in
    """, (user_id, value))
    con.commit()
    cur.close()
    con.close()


def reset_breaks(user_id):
    con = get_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO clock_status (user_id, clocked_in, breaks_taken, breaks_missed)
        VALUES (%s, TRUE, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET breaks_taken=0, breaks_missed=0
    """, (user_id,))
    con.commit()
    cur.close()
    con.close()


def record_break(user_id, took: bool):
    col = "breaks_taken" if took else "breaks_missed"
    con = get_conn()
    cur = con.cursor()
    cur.execute(f"""
        INSERT INTO clock_status (user_id, clocked_in, breaks_taken, breaks_missed)
        VALUES (%s, TRUE, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET {col}=clock_status.{col}+1
    """, (user_id,))
    con.commit()
    cur.close()
    con.close()


def get_clock_status(user_id):
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "SELECT clocked_in, breaks_taken, breaks_missed FROM clock_status WHERE user_id=%s",
        (user_id,)
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    return row or (False, 0, 0)


def get_clocked_in_users():
    con = get_conn()
    cur = con.cursor()
    cur.execute("SELECT user_id FROM clock_status WHERE clocked_in=TRUE")
    rows = cur.fetchall()
    cur.close()
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
        user_last_reminded[self.user_id] = datetime.now(pytz.utc)
        self.stop()
        await audit.clock_in(self.user_id)
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
        await audit.clock_in_skipped(self.user_id)
        await interaction.response.edit_message(
            content=f"<@{self.user_id}> skipped clock-in.",
            view=None
        )


class BreakView(View):
    def __init__(self, user_ids):
        super().__init__(timeout=300)
        self.user_ids = set(user_ids)
        self.taken = set()
        self.missed = set()
        self.message = None  # set after sending

    def _build_content(self):
        lines = ["Eye break! Look 20 feet away for 20 seconds. Did you take your break?"]
        for uid in self.user_ids:
            if uid in self.taken:
                lines.append(f"<@{uid}> took their break")
            elif uid in self.missed:
                lines.append(f"<@{uid}> skipped their break")
        return "\n".join(lines)

    async def _update(self, interaction: discord.Interaction):
        all_responded = (self.taken | self.missed) >= self.user_ids
        await interaction.response.edit_message(
            content=self._build_content(),
            view=None if all_responded else self,
        )

    async def on_timeout(self):
        for user_id in self.user_ids:
            if user_id not in self.taken and user_id not in self.missed:
                record_break(user_id, took=False)
                await audit.break_missed(user_id, reason="timeout")
        if self.message:
            await self.message.edit(content=self._build_content(), view=None)

    @discord.ui.button(label="Yes, took break", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in self.user_ids:
            await interaction.response.send_message("You are not in the current break group.", ephemeral=True)
            return
        if interaction.user.id in self.taken or interaction.user.id in self.missed:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.taken.add(interaction.user.id)
        record_break(interaction.user.id, took=True)
        await audit.break_taken(interaction.user.id)
        await self._update(interaction)

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in self.user_ids:
            await interaction.response.send_message("You are not in the current break group.", ephemeral=True)
            return
        if interaction.user.id in self.taken or interaction.user.id in self.missed:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.missed.add(interaction.user.id)
        record_break(interaction.user.id, took=False)
        await audit.break_missed(interaction.user.id, reason="no")
        await self._update(interaction)


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
        await audit.schedule_set(interaction.user.id, interaction.user, self.tz_name, start, end)
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

MY_GUILD = discord.Object(id=1515210069480833125)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Track which users got a clock-in prompt this minute (avoid duplicates)
clock_in_prompted = set()


@tree.command(guild=MY_GUILD,name="timeon", description="Set your work hours for eye break reminders")
async def timeon(interaction: discord.Interaction):
    view = TimezoneView()
    await interaction.response.send_message(
        "Step 1: Select your timezone.", view=view, ephemeral=True
    )


@tree.command(guild=MY_GUILD,name="timeoff", description="Stop receiving eye break reminders")
async def timeoff(interaction: discord.Interaction):
    set_clocked_in(interaction.user.id, False)
    remove_schedule(interaction.user.id)
    await audit.schedule_removed(interaction.user.id, interaction.user)
    await interaction.response.send_message(
        "Removed. You won't receive reminders anymore.", ephemeral=True
    )


@tree.command(guild=MY_GUILD,name="status", description="See who is clocked in and their break stats")
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
    await audit.status_checked(interaction.user.id)
    await interaction.response.send_message(embed=embed)


def owner_only(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_ID


@tree.command(guild=MY_GUILD,name="admin_clockin", description="[Owner] Manually clock in a user")
@app_commands.check(owner_only)
async def admin_clockin(interaction: discord.Interaction, user: discord.Member):
    set_clocked_in(user.id, True)
    reset_breaks(user.id)
    user_last_reminded[user.id] = datetime.now(pytz.utc)
    await audit.admin_clock_in(interaction.user.id, user.id)
    channel = client.get_channel(REMINDER_CHANNEL_ID)
    if channel:
        await channel.send(f"<@{user.id}> manually clocked in by admin.")
    await interaction.response.send_message(f"{user.display_name} clocked in.", ephemeral=True)


@tree.command(guild=MY_GUILD,name="admin_clockout", description="[Owner] Manually clock out a user")
@app_commands.check(owner_only)
async def admin_clockout(interaction: discord.Interaction, user: discord.Member):
    set_clocked_in(user.id, False)
    await audit.admin_clock_out(interaction.user.id, user.id)
    channel = client.get_channel(REMINDER_CHANNEL_ID)
    if channel:
        await channel.send(f"<@{user.id}> manually clocked out by admin.")
    await interaction.response.send_message(f"{user.display_name} clocked out.", ephemeral=True)


@tree.command(guild=MY_GUILD,name="admin_test", description="[Owner] Fire a break reminder immediately")
@app_commands.check(owner_only)
async def admin_test(interaction: discord.Interaction):
    channel = client.get_channel(REMINDER_CHANNEL_ID)
    clocked_in_users = get_clocked_in_users()
    if not clocked_in_users:
        await interaction.response.send_message("No users clocked in.", ephemeral=True)
        return
    mentions = " ".join(f"<@{uid}>" for uid in clocked_in_users)
    view = BreakView(set(clocked_in_users))
    await audit.admin_test(interaction.user.id, clocked_in_users)
    msg = await channel.send(
        f"{mentions} Eye break! Look 20 feet away for 20 seconds. Did you take your break?",
        view=view
    )
    view.message = msg
    await interaction.response.send_message("Test reminder sent.", ephemeral=True)


@admin_clockin.error
@admin_clockout.error
@admin_test.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("Owner only.", ephemeral=True)


# Per-user last reminder timestamp (UTC)
user_last_reminded: dict[int, datetime] = {}


async def background_loop():
    await client.wait_until_ready()
    channel = client.get_channel(REMINDER_CHANNEL_ID)

    while not client.is_closed():
        await asyncio.sleep(30)

        if channel is None:
            channel = client.get_channel(REMINDER_CHANNEL_ID)
            continue

        schedules = get_all_schedules()
        now_utc = datetime.now(pytz.utc)

        for user_id, timezone, start_time, end_time in schedules:
            tz = pytz.timezone(timezone)
            now_local = datetime.now(tz)
            current = now_local.strftime("%H:%M")

            # Clock-in prompt at start time
            if current == start_time and user_id not in clock_in_prompted:
                clock_in_prompted.add(user_id)
                set_clocked_in(user_id, False)
                await audit.clock_in_prompt_sent(user_id, start_time)
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
                    user_last_reminded.pop(user_id, None)
                    await audit.clock_out(user_id, reason="auto")
                    await channel.send(f"<@{user_id}> Work hours ended. Clocked out. Good work today!")
                clock_in_prompted.discard(user_id)

            # Reset prompt tracker at midnight
            if current == "00:00":
                clock_in_prompted.discard(user_id)

        # Per-user break reminders — 20 min after clock-in or last reminder
        clocked_in_users = get_clocked_in_users()
        due = []
        for user_id in clocked_in_users:
            last = user_last_reminded.get(user_id)
            elapsed = (now_utc - last).total_seconds() if last else float("inf")
            if elapsed >= REMINDER_INTERVAL_MINUTES * 60:
                due.append(user_id)
                user_last_reminded[user_id] = now_utc

        if due:
            mentions = " ".join(f"<@{uid}>" for uid in due)
            view = BreakView(set(due))
            await audit.break_reminder_sent(due)
            msg = await channel.send(
                f"{mentions} Eye break! Look 20 feet away for 20 seconds. Did you take your break?",
                view=view
            )
            view.message = msg


@client.event
async def on_ready():
    audit.init(client)
    await tree.sync(guild=MY_GUILD)
    await tree.sync()  # clears any previously registered global commands
    print(f"Logged in as {client.user}")
    client.loop.create_task(background_loop())


init_db()
client.run(BOT_TOKEN)
