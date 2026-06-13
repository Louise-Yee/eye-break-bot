import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import pytz
import state
import audit_logger as audit
from services import clock_service
from views.break_view import BreakView
from config import OWNER_ID, REMINDER_CHANNEL_ID


def owner_only(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_ID


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="admin_clockin", description="[Owner] Manually clock in a user")
    @app_commands.check(owner_only)
    async def admin_clockin(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)
        clock_service.clock_in(user.id)
        state.user_last_reminded[user.id] = datetime.now(pytz.utc)
        await audit.admin_clock_in(interaction.user.id, user.id)
        channel = self.bot.get_channel(REMINDER_CHANNEL_ID)
        if channel:
            await channel.send(f"<@{user.id}> manually clocked in by admin.")
        await interaction.followup.send(f"{user.display_name} clocked in.", ephemeral=True)

    @app_commands.command(name="admin_clockout", description="[Owner] Manually clock out a user")
    @app_commands.check(owner_only)
    async def admin_clockout(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)
        clock_service.clock_out(user.id)
        state.user_last_reminded.pop(user.id, None)
        await audit.admin_clock_out(interaction.user.id, user.id)
        channel = self.bot.get_channel(REMINDER_CHANNEL_ID)
        if channel:
            await channel.send(f"<@{user.id}> manually clocked out by admin.")
        await interaction.followup.send(f"{user.display_name} clocked out.", ephemeral=True)

    @app_commands.command(name="admin_test", description="[Owner] Fire a break reminder immediately")
    @app_commands.check(owner_only)
    async def admin_test(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        channel = self.bot.get_channel(REMINDER_CHANNEL_ID)
        clocked_in_users = clock_service.get_clocked_in_users()
        if not clocked_in_users:
            await interaction.followup.send("No users clocked in.", ephemeral=True)
            return
        mentions = " ".join(f"<@{uid}>" for uid in clocked_in_users)
        view = BreakView(set(clocked_in_users))
        await audit.admin_test(interaction.user.id, clocked_in_users)
        msg = await channel.send(
            f"{mentions} Eye break! Look 20 feet away for 20 seconds. Did you take your break?",
            view=view,
        )
        view.message = msg
        await interaction.followup.send("Test reminder sent.", ephemeral=True)

    @admin_clockin.error
    @admin_clockout.error
    @admin_test.error
    async def admin_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("Owner only.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
