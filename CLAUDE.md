# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Running the bot

```
cd "eyes break discord"
python main.py
```

**Required `.env`:**
```
BOT_TOKEN=...
DB_HOST=...
DB_USER=...
DB_PASSWORD=...
DB_NAME=postgres        # optional, defaults to postgres
DB_PORT=5432            # optional
REMINDER_CHANNEL_ID=... # optional, has hardcoded fallback in config.py
ADMIN_ROLE_ID=...       # optional, Discord role ID that grants admin-level access
```

Install deps: `pip install -r requirements.txt`

---

## Architecture

Strict layered architecture. Data flows in one direction only:

```
cogs (Discord commands/events)
  └── views (discord.ui components — UI only)
  └── services (business logic)
        └── db (repository layer — one module per table)
              └── PostgreSQL (via psycopg2, no ORM)
models (plain dataclasses, shared across all layers)
state.py (in-memory runtime state, non-persistent)
config.py (env vars + constants)
audit_logger.py (side-effect logging, called from cogs/views/tasks)
tasks/reminder.py (background polling loop, not a cog)
```

### Layer rules — NEVER violate these

- **Cogs** call services and audit_logger only. Never call `db.*` directly from a cog.
- **Views** call services and audit_logger only. Never call `db.*` directly from a view.
- **Services** call db repos only. Never import discord or interact with the bot client.
- **DB modules** call `get_conn()` only. Every function opens and closes its own connection — no shared connections, no connection pooling (psycopg2-binary, not async).
- **Models** are pure dataclasses — no methods, no imports from other project modules.
- **`state.py`** is imported directly by cogs, views, and tasks. It is intentionally not abstracted behind a service — keep it that way.
- **`audit_logger.py`** is a side-effect layer. It must never influence control flow. Always call audit functions after the primary action succeeds.
- Adding a new table requires: a model in `models/`, a db module in `db/`, `init_db()` updated in `db/connection.py`, and a service in `services/`. Register the service in `services/__init__.py`.

---

## Strict rules

### 1. Audit every user-facing action

Every command and every view button interaction that mutates state MUST call the corresponding `audit_logger` function. No exceptions.

**Coverage matrix — all of these must be audited:**

| Action | Audit function |
|---|---|
| Schedule set | `audit.schedule_set(user_id, user, tz, start, end)` |
| Schedule removed | `audit.schedule_removed(user_id, user)` |
| Clock in (user) | `audit.clock_in(user_id)` |
| Clock in (skipped) | `audit.clock_in_skipped(user_id)` |
| Clock in prompt sent | `audit.clock_in_prompt_sent(user_id, start_time)` |
| Clock out | `audit.clock_out(user_id, reason=...)` |
| Break reminder sent | `audit.break_reminder_sent(user_ids)` |
| Break taken | `audit.break_taken(user_id)` |
| Break missed | `audit.break_missed(user_id, reason=...)` |
| Admin clock in | `audit.admin_clock_in(admin_id, target_id)` |
| Admin clock out | `audit.admin_clock_out(admin_id, target_id)` |
| Admin test reminder | `audit.admin_test(admin_id, user_ids)` |
| Status checked (user) | `audit.status_checked(user_id)` |
| Status checked (admin) | `audit.admin_status_checked(admin_id)` |

When adding a new auditable action, add both a function to `audit_logger.py` AND call it at every code path that triggers the action. The audit call must be `await`ed. Never fire-and-forget it.

Adding a new action type to `audit_logger.py`: add an `async def` that calls `_send()` with a unique color and action name string, then log via `log.info(...)`.

### 2. Type safety — always

- All function signatures must have full type annotations: parameters and return types.
- All dataclass fields must be typed.
- Use `| None` (not `Optional`) for nullable types.
- Use `list[T]`, `dict[K, V]`, `set[T]` (not `List`, `Dict`, `Set` from `typing`).
- DB repo functions that return a single row return `Model | None`, never a bare tuple or untyped value.
- Never use `Any`. If a type is genuinely unknown, use a bounded type or narrow it with `isinstance`.
- `discord.Interaction`, `discord.Member`, `discord.Message`, `discord.TextChannel` — always type these, never leave them untyped.
- Service return types must match what the calling cog/view expects without casting.

### 3. Fallbacks — always

**Discord channel lookups:**
- `bot.get_channel(id)` returns `None` if the channel is not cached. Always guard:
  ```python
  channel = self.bot.get_channel(REMINDER_CHANNEL_ID)
  if channel is None:
      return  # or log + return
  ```
- Never call `channel.send(...)` without first asserting `channel is not None`.

**DB queries:**
- Single-row queries (`fetchone`) return `None` if the row does not exist. Always handle the `None` case before accessing fields.
- `get()` in `db/clock_status.py` returns a zero-state `ClockStatus` when the user has no row — this is the established fallback pattern. Follow it for any new single-row lookups that represent "user has no record yet".
- DB functions must not let exceptions propagate silently. If a db call fails and it is called from an async context, the exception will surface naturally — do not swallow it.

**View interactions:**
- Every `discord.ui` button/select callback must check that `interaction.user.id` is authorized before mutating state.
- Views with `timeout` must implement `on_timeout()` to handle users who never respond (record missed state, edit or disable the message).
- Every `View` that edits its original message on timeout must store `self.message: discord.Message | None = None` and set it after `channel.send(...)`.

**Discord API calls:**
- `fetch_member` and similar network calls must be wrapped in `try/except Exception` with a fallback value (see `status.py:31-34` pattern).
- Any `await channel.send(...)` or `await interaction.followup.send(...)` inside a background task must be wrapped to avoid killing the polling loop on a Discord API error.

**State lookups:**
- `state.user_last_reminded.get(user_id)` — always use `.get()`, never `state.user_last_reminded[user_id]` (KeyError risk).
- `state.clock_in_prompted.discard(user_id)` — always use `.discard()`, never `.remove()` (KeyError risk).

**Config / env:**
- `BOT_TOKEN`, `DB_HOST`, `DB_USER`, `DB_PASSWORD` are required — `os.environ["KEY"]` is correct (fail fast at startup).
- Optional env vars use `os.environ.get("KEY", default)` — never add a required env var as `.get()` with a None default.

**`reminder_task` loop:**
- The `while not bot.is_closed()` loop must never crash silently. Wrap the body in `try/except Exception as e` and log the error; the loop must continue.

### 4. Slash command conventions

- All slash commands use `app_commands.command`. No prefix commands.
- All mutating commands (`clockin`, `timeoff`, schedule saves) must `defer(ephemeral=True)` immediately, then use `followup.send`.
- All read-only commands that do async work must also defer.
- Cog error handlers use the `@command.error` decorator pattern (see `admin.py:64-69`). Every cog with restricted commands must have an error handler for `CheckFailure`.
- All cogs expose `async def setup(bot: commands.Bot) -> None` and are loaded via `main.py:setup_hook`.

### 5. In-memory state (`state.py`)

- `state.py` holds only two collections: `user_last_reminded: dict[int, datetime]` and `clock_in_prompted: set[int]`. Do not add persistent data here.
- State is reset on bot restart. Any feature that requires persistence across restarts must use the DB.
- State mutations in views/cogs and in `reminder_task` can race. Keep mutations atomic (single dict/set operation); do not read-modify-write across `await` boundaries on state.

### 6. Adding new features — checklist

- [ ] New slash command → add to a cog → call service → call audit
- [ ] New DB table → model dataclass → db module with typed functions → `init_db()` entry → service wrapper
- [ ] New view → type all `__init__` params → guard user authorization → implement `on_timeout` → set `self.message` after send if timeout edits are needed
- [ ] New audit event → add `async def` to `audit_logger.py` → call `log.info` + `_send()` → call it at every trigger site
- [ ] New config value → add to `config.py` → use `os.environ["KEY"]` if required, `.get("KEY", default)` if optional

---

## Key runtime behaviors

- `reminder_task` polls every 30s. It fires clock-in prompts at `schedule.start_time`, auto-clocks-out at `schedule.end_time`, and sends break reminders every `REMINDER_INTERVAL_MINUTES` (20) minutes to all clocked-in users.
- `clock_in_prompted` prevents duplicate clock-in prompts within the same day; cleared at `00:00` and on clock-out.
- `BreakView` timeout is 300s. Users who do not respond are marked missed in `on_timeout()`.
- Slash commands sync globally and to `GUILD_ID` on every startup (`setup_hook`).
- Bot restart clears `state.py`. Users persisted as clocked-in in the DB will not receive reminders until they clock in again via command (which sets `user_last_reminded`).
- `AUDIT_CHANNEL_ID` is hardcoded in `audit_logger.py` (not in `.env`). `OWNER_ID` and `GUILD_ID` are hardcoded in `config.py`. These are intentional constants, not secrets.
- Admin access is granted to `OWNER_ID` (hardcoded) **or** any member holding the `ADMIN_ROLE_ID` Discord role (optional env var). The check lives in `_is_admin()` in `cogs/status.py` and must be reused for any future admin-gated commands, not duplicated.
- `/status` is role-aware: normal users see only their own stats; admins see all users with filter (All / Clocked In / Clocked Out) and pagination (10 per page via `AdminStatusView`). The `StatusEntry` dataclass is a display-only aggregate defined in `cogs/status.py` — it is not a DB model and does not belong in `models/`.
