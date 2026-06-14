import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import pytz
import state
import audit_logger as audit
from services import schedule_service, clock_service
from views.schedule_views import TimezoneView


class ScheduleCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="timeon", description="Set your work hours for eye break reminders")
    async def timeon(self, interaction: discord.Interaction) -> None:
        view = TimezoneView()
        await interaction.response.send_message("Step 1: Select your timezone.", view=view, ephemeral=True)

    @app_commands.command(name="clockin", description="Clock in to start receiving eye break reminders")
    async def clockin(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        schedule = schedule_service.get_schedule(interaction.user.id)
        if not schedule:
            await interaction.followup.send("No schedule set. Use /timeon first.", ephemeral=True)
            return
        status = clock_service.get_status(interaction.user.id)
        if status.clocked_in:
            await interaction.followup.send("Already clocked in.", ephemeral=True)
            return
        clock_service.clock_in(interaction.user.id)
        state.user_last_reminded[interaction.user.id] = datetime.now(pytz.utc)
        state.clock_in_prompted.add(interaction.user.id)
        await audit.clock_in(interaction.user.id)
        await interaction.followup.send("Clocked in. Break reminders started.", ephemeral=True)

    @app_commands.command(name="timeoff", description="Stop receiving eye break reminders")
    async def timeoff(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        clock_service.clock_out(interaction.user.id)
        schedule_service.remove_schedule(interaction.user.id)
        state.user_last_reminded.pop(interaction.user.id, None)
        state.clock_in_prompted.discard(interaction.user.id)
        await audit.schedule_removed(interaction.user.id, interaction.user)
        await interaction.followup.send("Removed. You won't receive reminders anymore.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ScheduleCog(bot))
