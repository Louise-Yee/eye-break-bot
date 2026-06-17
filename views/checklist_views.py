import asyncio
import discord
import audit_logger as audit
from models.checklist import Checklist, ChecklistItem
from services import checklist_service


class AddItemModal(discord.ui.Modal, title="Add Item"):
    item_text = discord.ui.TextInput(
        label="Item",
        placeholder="Enter item text...",
        max_length=200,
    )

    def __init__(self, checklist: Checklist, parent_message: discord.Message | None) -> None:
        super().__init__()
        self.checklist = checklist
        self.parent_message = parent_message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = self.item_text.value.strip()
        if not text:
            await interaction.response.send_message("Item text cannot be empty.", ephemeral=True)
            return
        await asyncio.to_thread(checklist_service.add_item, self.checklist.id, text)
        items = await asyncio.to_thread(checklist_service.get_items, self.checklist.id)
        new_view = ChecklistView(self.checklist, items)
        new_view.message = self.parent_message
        await interaction.response.defer()
        if self.parent_message is not None:
            await self.parent_message.edit(embed=new_view.build_embed(), view=new_view)
        await audit.checklist_item_added(interaction.user.id, self.checklist.name, text)


class ItemToggleSelect(discord.ui.Select):
    def __init__(self, items: list[ChecklistItem]) -> None:
        self._item_map: dict[str, ChecklistItem] = {str(i.id): i for i in items}
        options = [
            discord.SelectOption(
                label=item.text[:100],
                value=str(item.id),
                description="[x] Done" if item.checked else "[ ] Not done",
            )
            for item in items[:25]
        ]
        super().__init__(placeholder="Toggle item...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        item_id = int(self.values[0])
        item = self._item_map[str(item_id)]
        new_checked = not item.checked
        await asyncio.to_thread(checklist_service.toggle_item, item_id, new_checked)
        view: ChecklistView = self.view  # type: ignore
        updated_items = await asyncio.to_thread(checklist_service.get_items, view.checklist.id)
        new_view = ChecklistView(view.checklist, updated_items)
        new_view.message = view.message
        await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)
        await audit.checklist_item_toggled(interaction.user.id, view.checklist.name, item.text, new_checked)


class ChecklistView(discord.ui.View):
    def __init__(self, checklist: Checklist, items: list[ChecklistItem]) -> None:
        super().__init__(timeout=600)
        self.checklist = checklist
        self.items = items
        self.message: discord.Message | None = None
        if items:
            self.add_item(ItemToggleSelect(items))

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title=self.checklist.name)
        if not self.items:
            embed.description = "No items yet. Use 'Add Item' to get started."
        else:
            lines = [
                f"[x] {item.text}" if item.checked else f"[ ] {item.text}"
                for item in self.items
            ]
            embed.description = "\n".join(lines)
        done = sum(1 for i in self.items if i.checked)
        embed.set_footer(text=f"{done}/{len(self.items)} done")
        return embed

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass

    @discord.ui.button(label="Add Item", style=discord.ButtonStyle.primary, row=1)
    async def add_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = AddItemModal(self.checklist, self.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Reset All", style=discord.ButtonStyle.secondary, row=1)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await asyncio.to_thread(checklist_service.reset_items, self.checklist.id)
        items = await asyncio.to_thread(checklist_service.get_items, self.checklist.id)
        new_view = ChecklistView(self.checklist, items)
        new_view.message = self.message
        await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)
        await audit.checklist_reset(interaction.user.id, self.checklist.name)

    @discord.ui.button(label="Delete Checklist", style=discord.ButtonStyle.danger, row=1)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await asyncio.to_thread(checklist_service.delete_checklist, self.checklist.id)
        await interaction.response.edit_message(
            content=f"Checklist '{self.checklist.name}' deleted.",
            embed=None,
            view=None,
        )
        await audit.checklist_deleted(interaction.user.id, self.checklist.name)
