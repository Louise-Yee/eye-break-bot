import discord
from discord.ui import Select, View, Modal, TextInput
from datetime import datetime
import audit_logger as audit
from services import schedule_service
from config import TIMEZONES, REMINDER_INTERVAL_MINUTES


class WorkHoursModal(Modal, title="Set Work Hours"):
    start = TextInput(label="Start time (HH:MM, 24h)", placeholder="09:00")
    end = TextInput(label="End time (HH:MM, 24h)", placeholder="18:00")

    def __init__(self, tz_name: str, tz_label: str) -> None:
        super().__init__()
        self.tz_name = tz_name
        self.tz_label = tz_label

    async def on_submit(self, interaction: discord.Interaction) -> None:
        start = self.start.value.strip()
        end = self.end.value.strip()
        try:
            datetime.strptime(start, "%H:%M")
            datetime.strptime(end, "%H:%M")
        except ValueError:
            await interaction.response.send_message(
                "Invalid time format. Use HH:MM (e.g. 09:00).", ephemeral=True
            )
            return
        schedule_service.save_schedule(interaction.user.id, self.tz_name, start, end)
        await audit.schedule_set(interaction.user.id, interaction.user, self.tz_name, start, end)
        await interaction.response.send_message(
            f"Saved. Clock-in prompt at {start}, reminders every {REMINDER_INTERVAL_MINUTES} min until {end} ({self.tz_label}).",
            ephemeral=True,
        )


class TimezoneSelect(Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=label, value=tz)
            for label, tz in TIMEZONES
        ]
        super().__init__(placeholder="Select your timezone", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        tz_value = self.values[0]
        tz_label = next(label for label, tz in TIMEZONES if tz == tz_value)
        modal = WorkHoursModal(tz_name=tz_value, tz_label=tz_label)
        await interaction.response.send_modal(modal)


class TimezoneView(View):
    def __init__(self) -> None:
        super().__init__(timeout=60)
        self.add_item(TimezoneSelect())
