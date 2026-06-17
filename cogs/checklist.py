import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import audit_logger as audit
from services import checklist_service
from views.checklist_views import ChecklistView


class ChecklistCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    checklist = app_commands.Group(name="checklist", description="Manage personal checklists")

    @checklist.command(name="create", description="Create a new checklist")
    @app_commands.describe(name="Name for the checklist")
    async def create(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        existing = await asyncio.to_thread(checklist_service.get_checklist, interaction.user.id, name)
        if existing is not None:
            await interaction.followup.send(f"A checklist named '{name}' already exists. Use /checklist view.", ephemeral=True)
            return
        checklist = await asyncio.to_thread(checklist_service.create_checklist, interaction.user.id, name)
        items = await asyncio.to_thread(checklist_service.get_items, checklist.id)
        view = ChecklistView(checklist, items)
        msg = await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)
        view.message = msg
        await audit.checklist_created(interaction.user.id, name)

    @checklist.command(name="view", description="View and manage a checklist")
    @app_commands.describe(name="Name of the checklist to view")
    async def view(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        checklist = await asyncio.to_thread(checklist_service.get_checklist, interaction.user.id, name)
        if checklist is None:
            await interaction.followup.send(f"No checklist named '{name}'. Use /checklist create.", ephemeral=True)
            return
        items = await asyncio.to_thread(checklist_service.get_items, checklist.id)
        cv = ChecklistView(checklist, items)
        msg = await interaction.followup.send(embed=cv.build_embed(), view=cv, ephemeral=True)
        cv.message = msg
        await audit.checklist_viewed(interaction.user.id, name)

    @checklist.command(name="list", description="List all your checklists")
    async def list_checklists(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        checklists = await asyncio.to_thread(checklist_service.get_all_checklists, interaction.user.id)
        if not checklists:
            await interaction.followup.send("You have no checklists. Use /checklist create.", ephemeral=True)
            return
        lines = [f"- {c.name}" for c in checklists]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @checklist.command(name="delete", description="Delete a checklist")
    @app_commands.describe(name="Name of the checklist to delete")
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        checklist = await asyncio.to_thread(checklist_service.get_checklist, interaction.user.id, name)
        if checklist is None:
            await interaction.followup.send(f"No checklist named '{name}'.", ephemeral=True)
            return
        await asyncio.to_thread(checklist_service.delete_checklist, checklist.id)
        await interaction.followup.send(f"Checklist '{name}' deleted.", ephemeral=True)
        await audit.checklist_deleted(interaction.user.id, name)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChecklistCog(bot))
