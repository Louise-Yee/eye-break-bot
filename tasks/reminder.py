import asyncio
import logging
from datetime import datetime
import discord
import pytz
import state
import audit_logger as audit
from services import schedule_service, clock_service
from views.clock_in_view import ClockInView
from views.break_view import BreakView
from config import REMINDER_CHANNEL_ID, REMINDER_INTERVAL_MINUTES

log = logging.getLogger(__name__)


async def reminder_task(bot: discord.Client) -> None:
    await bot.wait_until_ready()
    channel = bot.get_channel(REMINDER_CHANNEL_ID)

    while not bot.is_closed():
        await asyncio.sleep(30)
        try:
            if channel is None:
                channel = bot.get_channel(REMINDER_CHANNEL_ID)
                continue

            schedules = await asyncio.to_thread(schedule_service.get_all_schedules)
            now_utc = datetime.now(pytz.utc)

            for schedule in schedules:
                tz = pytz.timezone(schedule.timezone)
                current = datetime.now(tz).strftime("%H:%M")

                if current == schedule.start_time and schedule.user_id not in state.clock_in_prompted:
                    state.clock_in_prompted.add(schedule.user_id)
                    await asyncio.to_thread(clock_service.clock_out, schedule.user_id)
                    await audit.clock_in_prompt_sent(schedule.user_id, schedule.start_time)
                    view = ClockInView(schedule.user_id)
                    await channel.send(
                        f"<@{schedule.user_id}> It's {schedule.start_time} — time to start work. Clock in?",
                        view=view,
                    )

                if current == schedule.end_time:
                    status = await asyncio.to_thread(clock_service.get_status, schedule.user_id)
                    if status.clocked_in:
                        await asyncio.to_thread(clock_service.clock_out, schedule.user_id)
                        state.user_last_reminded.pop(schedule.user_id, None)
                        await audit.clock_out(schedule.user_id, reason="auto")
                        await channel.send(f"<@{schedule.user_id}> Work hours ended. Clocked out. Good work today!")
                    state.clock_in_prompted.discard(schedule.user_id)

                if current == "00:00":
                    state.clock_in_prompted.discard(schedule.user_id)

            clocked_in_users = await asyncio.to_thread(clock_service.get_clocked_in_users)
            due: list[int] = []
            for user_id in clocked_in_users:
                last = state.user_last_reminded.get(user_id)
                elapsed = (now_utc - last).total_seconds() if last else float("inf")
                if elapsed >= REMINDER_INTERVAL_MINUTES * 60:
                    due.append(user_id)
                    state.user_last_reminded[user_id] = now_utc

            if due:
                mentions = " ".join(f"<@{uid}>" for uid in due)
                view = BreakView(set(due))
                await audit.break_reminder_sent(due)
                msg = await channel.send(
                    f"{mentions} Eye break! Look 20 feet away for 20 seconds. Did you take your break?",
                    view=view,
                )
                view.message = msg
        except Exception as e:
            log.error(f"reminder_task error: {e}")
