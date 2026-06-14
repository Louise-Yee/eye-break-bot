import discord
from discord import app_commands
from discord.ext import commands
from dataclasses import dataclass
from datetime import datetime
import pytz
import audit_logger as audit
from services import schedule_service, clock_service
from config import TIMEZONES, OWNER_ID, ADMIN_ROLE_ID

PAGE_SIZE = 10


@dataclass
class StatusEntry:
    user_id: int
    display_name: str
    clocked_in: bool
    breaks_taken: int
    breaks_missed: int
    start_time: str
    end_time: str
    tz_label: str
    current_time: str


def _is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.id == OWNER_ID:
        return True
    if ADMIN_ROLE_ID is not None and isinstance(interaction.user, discord.Member):
        return any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles)
    return False


def _tz_label(timezone: str) -> str:
    return next((label for label, tz in TIMEZONES if tz == timezone), timezone)


def _build_admin_embed(
    entries: list[StatusEntry],
    filter_mode: str,
    page: int,
    total_pages: int,
) -> discord.Embed:
    filter_label = {"all": "All", "clocked_in": "Clocked In", "clocked_out": "Clocked Out"}[filter_mode]
    embed = discord.Embed(
        title=f"Work Status — {filter_label}",
        color=discord.Color.blue(),
        description=f"Page {page + 1}/{total_pages} · {len(entries)} user(s)",
    )
    for entry in entries[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]:
        icon = "🟢" if entry.clocked_in else "⚪"
        embed.add_field(
            name=f"{icon} {entry.display_name}",
            value=(
                f"Hours: {entry.start_time}–{entry.end_time} ({entry.tz_label})\n"
                f"Current: {entry.current_time}\n"
                f"Breaks taken: {entry.breaks_taken} | Missed: {entry.breaks_missed}"
            ),
            inline=False,
        )
    return embed


class FilterSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="All", value="all", default=True),
            discord.SelectOption(label="Clocked In", value="clocked_in"),
            discord.SelectOption(label="Clocked Out", value="clocked_out"),
        ]
        super().__init__(placeholder="Filter...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: AdminStatusView = self.view  # type: ignore[assignment]
        view.filter_mode = self.values[0]
        view.page = 0
        for opt in self.options:
            opt.default = opt.value == self.values[0]
        await view.refresh(interaction)


class AdminStatusView(discord.ui.View):
    def __init__(self, all_entries: list[StatusEntry]) -> None:
        super().__init__(timeout=120)
        self.all_entries = all_entries
        self.filter_mode: str = "all"
        self.page: int = 0
        self.add_item(FilterSelect())

    def _filtered(self) -> list[StatusEntry]:
        if self.filter_mode == "clocked_in":
            return [e for e in self.all_entries if e.clocked_in]
        if self.filter_mode == "clocked_out":
            return [e for e in self.all_entries if not e.clocked_in]
        return self.all_entries

    def _total_pages(self, entries: list[StatusEntry]) -> int:
        return max(1, (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _sync_buttons(self, total_pages: int) -> None:
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= total_pages - 1

    async def refresh(self, interaction: discord.Interaction) -> None:
        entries = self._filtered()
        total_pages = self._total_pages(entries)
        self.page = min(self.page, max(0, total_pages - 1))
        self._sync_buttons(total_pages)
        embed = _build_admin_embed(entries, self.filter_mode, self.page, total_pages)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page -= 1
        await self.refresh(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page += 1
        await self.refresh(interaction)


class StatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="status", description="View work status")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if _is_admin(interaction):
            await self._admin_status(interaction)
        else:
            await self._user_status(interaction)

    async def _admin_status(self, interaction: discord.Interaction) -> None:
        schedules = schedule_service.get_all_schedules()
        if not schedules:
            await interaction.followup.send("No users registered.", ephemeral=True)
            return

        entries: list[StatusEntry] = []
        for schedule in schedules:
            clock = clock_service.get_status(schedule.user_id)
            tz = pytz.timezone(schedule.timezone)
            try:
                member = await interaction.guild.fetch_member(schedule.user_id)
                display_name = member.display_name
            except Exception:
                display_name = f"<@{schedule.user_id}>"
            entries.append(StatusEntry(
                user_id=schedule.user_id,
                display_name=display_name,
                clocked_in=clock.clocked_in,
                breaks_taken=clock.breaks_taken,
                breaks_missed=clock.breaks_missed,
                start_time=schedule.start_time,
                end_time=schedule.end_time,
                tz_label=_tz_label(schedule.timezone),
                current_time=datetime.now(tz).strftime("%H:%M"),
            ))

        view = AdminStatusView(entries)
        total_pages = view._total_pages(entries)
        view._sync_buttons(total_pages)
        embed = _build_admin_embed(entries, "all", 0, total_pages)
        await audit.admin_status_checked(interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _user_status(self, interaction: discord.Interaction) -> None:
        schedule = schedule_service.get_schedule(interaction.user.id)
        if not schedule:
            await interaction.followup.send("No schedule set. Use /timeon first.", ephemeral=True)
            return

        clock = clock_service.get_status(interaction.user.id)
        tz = pytz.timezone(schedule.timezone)
        icon = "🟢" if clock.clocked_in else "⚪"
        embed = discord.Embed(title="Your Work Status", color=discord.Color.blue())
        embed.add_field(
            name=f"{icon} {interaction.user.display_name}",
            value=(
                f"Hours: {schedule.start_time}–{schedule.end_time} ({_tz_label(schedule.timezone)})\n"
                f"Current: {datetime.now(tz).strftime('%H:%M')}\n"
                f"Breaks taken: {clock.breaks_taken} | Missed: {clock.breaks_missed}"
            ),
            inline=False,
        )
        await audit.status_checked(interaction.user.id)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatusCog(bot))
