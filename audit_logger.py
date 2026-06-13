import logging
import discord
from datetime import datetime, timezone

log = logging.getLogger("audit")
log.setLevel(logging.INFO)
log.propagate = False
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s [AUDIT] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
log.addHandler(_handler)

AUDIT_CHANNEL_ID = 1515254837917257781
_client = None


def init(client: discord.Client):
    global _client
    _client = client


def _ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


async def _send(color: discord.Color, action: str, fields: dict):
    if _client is None:
        return
    channel = _client.get_channel(AUDIT_CHANNEL_ID)
    if channel is None:
        return
    embed = discord.Embed(
        title=action,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    for k, v in fields.items():
        embed.add_field(name=k, value=str(v), inline=True)
    embed.set_footer(text=_ts())
    await channel.send(embed=embed)


async def schedule_set(user_id, user, tz, start, end):
    log.info(f"SCHEDULE_SET user={user_id} ({user}) tz={tz} start={start} end={end}")
    await _send(discord.Color.blue(), "Schedule Set", {
        "User": f"<@{user_id}>",
        "Timezone": tz,
        "Start": start,
        "End": end,
    })


async def schedule_removed(user_id, user):
    log.info(f"SCHEDULE_REMOVED user={user_id} ({user})")
    await _send(discord.Color.greyple(), "Schedule Removed", {
        "User": f"<@{user_id}>",
    })


async def clock_in(user_id):
    log.info(f"CLOCK_IN user={user_id}")
    await _send(discord.Color.green(), "Clock In", {
        "User": f"<@{user_id}>",
    })


async def clock_in_skipped(user_id):
    log.info(f"CLOCK_IN_SKIPPED user={user_id}")
    await _send(discord.Color.yellow(), "Clock In Skipped", {
        "User": f"<@{user_id}>",
    })


async def clock_in_prompt_sent(user_id, start_time):
    log.info(f"CLOCK_IN_PROMPT_SENT user={user_id} start_time={start_time}")
    await _send(discord.Color.blurple(), "Clock In Prompt Sent", {
        "User": f"<@{user_id}>",
        "Start Time": start_time,
    })


async def clock_out(user_id, reason="auto"):
    log.info(f"CLOCK_OUT user={user_id} reason={reason}")
    await _send(discord.Color.orange(), "Clock Out", {
        "User": f"<@{user_id}>",
        "Reason": reason,
    })


async def break_reminder_sent(user_ids):
    log.info(f"BREAK_REMINDER_SENT users={user_ids}")
    await _send(discord.Color.teal(), "Break Reminder Sent", {
        "Users": " ".join(f"<@{uid}>" for uid in user_ids),
        "Count": len(user_ids),
    })


async def break_taken(user_id):
    log.info(f"BREAK_TAKEN user={user_id}")
    await _send(discord.Color.green(), "Break Taken", {
        "User": f"<@{user_id}>",
    })


async def break_missed(user_id, reason="no"):
    log.info(f"BREAK_MISSED user={user_id} reason={reason}")
    await _send(discord.Color.red(), "Break Missed", {
        "User": f"<@{user_id}>",
        "Reason": reason,
    })


async def admin_clock_in(admin_id, target_id):
    log.info(f"ADMIN_CLOCK_IN admin={admin_id} target={target_id}")
    await _send(discord.Color.green(), "Admin: Clock In", {
        "Admin": f"<@{admin_id}>",
        "Target": f"<@{target_id}>",
    })


async def admin_clock_out(admin_id, target_id):
    log.info(f"ADMIN_CLOCK_OUT admin={admin_id} target={target_id}")
    await _send(discord.Color.orange(), "Admin: Clock Out", {
        "Admin": f"<@{admin_id}>",
        "Target": f"<@{target_id}>",
    })


async def admin_test(admin_id, user_ids):
    log.info(f"ADMIN_TEST admin={admin_id} users={user_ids}")
    await _send(discord.Color.purple(), "Admin: Test Reminder", {
        "Admin": f"<@{admin_id}>",
        "Users": " ".join(f"<@{uid}>" for uid in user_ids),
    })


async def status_checked(user_id):
    log.info(f"STATUS_CHECKED user={user_id}")
    await _send(discord.Color.blurple(), "Status Checked", {
        "User": f"<@{user_id}>",
    })
