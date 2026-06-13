import discord
from discord.ui import View, Button
import audit_logger as audit
from services import break_service


class BreakView(View):
    def __init__(self, user_ids: set[int]) -> None:
        super().__init__(timeout=300)
        self.user_ids = set(user_ids)
        self.taken: set[int] = set()
        self.missed: set[int] = set()
        self.message: discord.Message | None = None

    def _build_content(self) -> str:
        lines = ["Eye break! Look 20 feet away for 20 seconds. Did you take your break?"]
        for uid in self.user_ids:
            if uid in self.taken:
                lines.append(f"<@{uid}> took their break")
            elif uid in self.missed:
                lines.append(f"<@{uid}> skipped their break")
        return "\n".join(lines)

    async def _update(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        all_responded = (self.taken | self.missed) >= self.user_ids
        await interaction.edit_original_response(
            content=self._build_content(),
            view=None if all_responded else self,
        )

    async def on_timeout(self) -> None:
        for user_id in self.user_ids:
            if user_id not in self.taken and user_id not in self.missed:
                break_service.record_break(user_id, took=False)
                await audit.break_missed(user_id, reason="timeout")
        if self.message:
            await self.message.edit(content=self._build_content(), view=None)

    @discord.ui.button(label="Yes, took break", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: Button) -> None:
        if interaction.user.id not in self.user_ids:
            await interaction.response.send_message("You are not in the current break group.", ephemeral=True)
            return
        if interaction.user.id in self.taken or interaction.user.id in self.missed:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.taken.add(interaction.user.id)
        break_service.record_break(interaction.user.id, took=True)
        await audit.break_taken(interaction.user.id)
        await self._update(interaction)

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: Button) -> None:
        if interaction.user.id not in self.user_ids:
            await interaction.response.send_message("You are not in the current break group.", ephemeral=True)
            return
        if interaction.user.id in self.taken or interaction.user.id in self.missed:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.missed.add(interaction.user.id)
        break_service.record_break(interaction.user.id, took=False)
        await audit.break_missed(interaction.user.id, reason="no")
        await self._update(interaction)
