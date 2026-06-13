import discord
from discord.ui import View, Button
from datetime import datetime
import pytz
import state
import audit_logger as audit
from services import clock_service


class ClockInView(View):
    def __init__(self, user_id: int) -> None:
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Yes, clock in", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return
        clock_service.clock_in(self.user_id)
        state.user_last_reminded[self.user_id] = datetime.now(pytz.utc)
        self.stop()
        await audit.clock_in(self.user_id)
        await interaction.response.edit_message(
            content=f"<@{self.user_id}> clocked in. Break reminders started.",
            view=None,
        )

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return
        self.stop()
        await audit.clock_in_skipped(self.user_id)
        await interaction.response.edit_message(
            content=f"<@{self.user_id}> skipped clock-in.",
            view=None,
        )
