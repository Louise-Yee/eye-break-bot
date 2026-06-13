import discord
from discord.ext import commands
from dotenv import load_dotenv
load_dotenv()

import audit_logger as audit
from config import BOT_TOKEN, GUILD_ID
from db.connection import init_db
from tasks.reminder import reminder_task

MY_GUILD = discord.Object(id=GUILD_ID)


class EyeBreakBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.schedule")
        await self.load_extension("cogs.admin")
        await self.load_extension("cogs.status")
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)
        await self.tree.sync()

    async def on_ready(self) -> None:
        audit.init(self)
        print(f"Logged in as {self.user}")
        self.loop.create_task(reminder_task(self))


init_db()
bot = EyeBreakBot()
bot.run(BOT_TOKEN)
