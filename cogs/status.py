import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import pytz
import audit_logger as audit
from services import schedule_service, clock_service
from config import TIMEZONES


class StatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="status", description="See who is clocked in and their break stats")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        schedules = schedule_service.get_all_schedules()
        if not schedules:
            await interaction.followup.send("No users registered.", ephemeral=True)
            return

        embed = discord.Embed(title="Work Status", color=discord.Color.blue())
        for schedule in schedules:
            clock = clock_service.get_status(schedule.user_id)
            tz = pytz.timezone(schedule.timezone)
            current_time = datetime.now(tz).strftime("%H:%M")
            tz_label = next((l for l, t in TIMEZONES if t == schedule.timezone), schedule.timezone)
            icon = "🟢" if clock.clocked_in else "⚪"
            try:
                member = await interaction.guild.fetch_member(schedule.user_id)
                display_name = member.display_name
            except Exception:
                display_name = f"<@{schedule.user_id}>"
            embed.add_field(
                name=f"{icon} {display_name}",
                value=(
                    f"Hours: {schedule.start_time}–{schedule.end_time} ({tz_label})\n"
                    f"Current time: {current_time}\n"
                    f"Breaks taken: {clock.breaks_taken} | Missed: {clock.breaks_missed}"
                ),
                inline=False,
            )
        await audit.status_checked(interaction.user.id)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatusCog(bot))
