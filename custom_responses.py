import asyncio
import json
import os
import re
import secrets
import time

import discord
from discord.ext import commands

DATA_FILE = "custom_responses.json"
COOLDOWN_SECONDS = 5 * 60
TRIGGER_LIMIT = 80
RESPONSE_LIMIT = 500
WIZARD_TIMEOUT = 120
MAX_TRIGGERS = 10
SELECT_CUSTOM_ID = "cr:select"
EDIT_CUSTOM_ID = "cr:edit"
DELETE_CUSTOM_ID = "cr:delete"
REFRESH_CUSTOM_ID = "cr:refresh"

data = {"guilds": {}}
wizard_users = set()
cooldowns = {}
selected_response = {}


def load_custom_responses():
    global data
    if not os.path.exists(DATA_FILE):
        data = {"guilds": {}}
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError("custom responses file is not an object")
        loaded.setdefault("guilds", {})
        data = loaded
    except Exception as exc:
        print(f"Failed to load custom responses: {exc}")
        data = {"guilds": {}}


def save_custom_responses():
    with open(DATA_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def guild_record(guild_id, create=False):
    key = str(guild_id)
    guilds = data.setdefault("guilds", {})
    record = guilds.get(key)
    if record is None:
        if not create:
            return None
        record = {"timeout_role_id": None, "responses": []}
        guilds[key] = record
    record.setdefault("timeout_role_id", None)
    record.setdefault("responses", [])
    return record


def list_responses(guild_id):
    record = guild_record(guild_id)
    if record is None:
        return []
    return list(record["responses"])


def find_entry(guild_id, entry_id):
    for entry in list_responses(guild_id):
        if entry["id"] == entry_id:
            return entry
    return None


def _new_id(record):
    existing = {entry["id"] for entry in record["responses"]}
    while True:
        candidate = secrets.token_hex(4)
        if candidate not in existing:
            return candidate


def save_response(guild_id, trigger, response, created_by, match_mode="contains"):
    record = guild_record(guild_id, create=True)
    trigger_key = trigger.casefold()
    for entry in record["responses"]:
        if entry["trigger"].casefold() == trigger_key:
            entry["trigger"] = trigger
            entry["response"] = response
            entry["created_by"] = created_by
            entry["match_mode"] = match_mode
            save_custom_responses()
            return entry, True
    entry = {
        "id": _new_id(record),
        "trigger": trigger,
        "response": response,
        "created_by": created_by,
        "match_mode": match_mode,
    }
    record["responses"].append(entry)
    save_custom_responses()
    return entry, False


def update_response(guild_id, entry_id, trigger, response):
    record = guild_record(guild_id)
    if record is None:
        return None
    target = next((entry for entry in record["responses"] if entry["id"] == entry_id), None)
    if target is None:
        return None
    trigger_key = trigger.casefold()
    record["responses"] = [
        entry
        for entry in record["responses"]
        if entry["id"] == entry_id or entry["trigger"].casefold() != trigger_key
    ]
    target["trigger"] = trigger
    target["response"] = response
    save_custom_responses()
    return target


def delete_response(guild_id, entry_id):
    record = guild_record(guild_id)
    if record is None:
        return False
    kept = [entry for entry in record["responses"] if entry["id"] != entry_id]
    if len(kept) == len(record["responses"]):
        return False
    record["responses"] = kept
    save_custom_responses()
    return True


def set_timeout_role(guild_id, role_id):
    record = guild_record(guild_id, create=True)
    record["timeout_role_id"] = role_id
    save_custom_responses()


def resolve_timeout_role(guild, record):
    if record is None:
        return None
    role_id = record.get("timeout_role_id")
    if role_id:
        role = guild.get_role(int(role_id))
        if role is not None:
            return role
    for role in guild.roles:
        if role.name.casefold() == "timeout":
            return role
    return None


def _trigger_match_index(content, trigger, match_mode):
    if match_mode == "word":
        match = re.search(rf"(?<!\w){re.escape(trigger)}(?!\w)", content)
        return None if match is None else match.start()
    index = content.find(trigger)
    return None if index == -1 else index


def find_earliest_response(content, responses):
    lowered = content.casefold()
    best = None
    for entry in responses:
        trigger = entry.get("trigger", "").casefold()
        if not trigger:
            continue
        index = _trigger_match_index(lowered, trigger, entry.get("match_mode", "contains"))
        if index is None:
            continue
        # Same starting point: the longer trigger is the one they actually wrote.
        rank = (index, -len(trigger))
        if best is None or rank < best[0]:
            best = (rank, entry)
    return None if best is None else best[1]


def reply_text_for_message(content, responses, on_cooldown):
    if on_cooldown or not content or content.startswith("!"):
        return None
    entry = find_earliest_response(content, responses)
    if entry is None:
        return None
    return entry["response"]


def cooldown_remaining(guild_id, user_id, now=None):
    now = time.monotonic() if now is None else now
    last = cooldowns.get((guild_id, user_id))
    if last is None:
        return 0
    remaining = COOLDOWN_SECONDS - (now - last)
    return remaining if remaining > 0 else 0


def mark_cooldown(guild_id, user_id, now=None):
    cooldowns[(guild_id, user_id)] = time.monotonic() if now is None else now


def is_wizard_user(user_id):
    return user_id in wizard_users


def can_modify(member, entry):
    permissions = getattr(member, "guild_permissions", None)
    if permissions is not None and permissions.manage_messages:
        return True
    try:
        return int(entry.get("created_by", 0)) == member.id
    except (TypeError, ValueError):
        return False


def _option_text(value, limit):
    text = " ".join(str(value).split())
    return text[:limit]


def _validate_pair(trigger, response):
    trigger = trigger.strip()
    response = response.strip()
    if not trigger or not response:
        return None, None, "Trigger and response both need text."
    if trigger.startswith("!"):
        return None, None, "The trigger can't start with ! or it will never fire. Pick a normal word."
    if len(trigger) > TRIGGER_LIMIT:
        return None, None, f"Trigger needs to be {TRIGGER_LIMIT} characters or less."
    if len(response) > RESPONSE_LIMIT:
        return None, None, f"Response needs to be {RESPONSE_LIMIT} characters or less."
    return trigger, response, None


def build_responses_embed(guild):
    record = guild_record(guild.id)
    responses = [] if record is None else record["responses"]
    role = resolve_timeout_role(guild, record)
    embed = discord.Embed(title="Custom responses")
    if not responses:
        embed.description = "No custom responses yet. Use `!create response`."
    else:
        lines = [
            f"**{_option_text(entry['trigger'], 80)}** ({_match_label(entry)}) — {entry['response']}"
            for entry in responses
        ]
        description = "\n".join(lines)
        if len(description) > 4000:
            description = description[:4000] + "\n…"
        embed.description = description
    if role is None:
        footer = "No timeout role set. Use !responses role @Role. Saved responses will not fire yet."
    else:
        footer = f"Fires when the {role.name} role says a trigger. 5 minute cooldown per user."
    if len(responses) > 25:
        footer += " Menu shows the first 25."
    embed.set_footer(text=footer[:2048])
    return embed


def _selection_key(interaction):
    if interaction.guild_id is None or interaction.message is None:
        return None
    return (interaction.guild_id, interaction.message.id, interaction.user.id)


def _clear_message_selection(message_id):
    for key in list(selected_response):
        if key[1] == message_id:
            selected_response.pop(key, None)


class ResponseSelect(discord.ui.Select):
    def __init__(self, responses):
        options = []
        for entry in responses[:25]:
            label = _option_text(entry["trigger"], 100) or "trigger"
            description = _option_text(entry["response"], 100)
            kwargs = {"label": label, "value": str(entry["id"])}
            if description:
                kwargs["description"] = description
            options.append(discord.SelectOption(**kwargs))
        super().__init__(
            custom_id=SELECT_CUSTOM_ID,
            placeholder="Pick a response",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction):
        key = _selection_key(interaction)
        if key is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        selected_response[key] = self.values[0]
        await interaction.response.defer()


class EditButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Edit",
            style=discord.ButtonStyle.primary,
            custom_id=EDIT_CUSTOM_ID,
            row=1,
        )

    async def callback(self, interaction):
        await handle_edit(interaction)


class DeleteButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Delete",
            style=discord.ButtonStyle.danger,
            custom_id=DELETE_CUSTOM_ID,
            row=1,
        )

    async def callback(self, interaction):
        await handle_delete(interaction)


class RefreshButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            custom_id=REFRESH_CUSTOM_ID,
            row=1,
        )

    async def callback(self, interaction):
        await handle_refresh(interaction)


class ResponsesView(discord.ui.View):
    def __init__(self, responses=None):
        super().__init__(timeout=None)
        shown = list(responses or [])
        if shown:
            self.add_item(ResponseSelect(shown))
        self.add_item(EditButton())
        self.add_item(DeleteButton())
        self.add_item(RefreshButton())


class EditResponseModal(discord.ui.Modal, title="Edit response"):
    def __init__(self, entry):
        super().__init__()
        self.entry_id = entry["id"]
        self.trigger_input = discord.ui.TextInput(
            label="Trigger",
            default=entry["trigger"][:TRIGGER_LIMIT],
            max_length=TRIGGER_LIMIT,
            required=True,
        )
        self.response_input = discord.ui.TextInput(
            label="Response",
            default=entry["response"][:RESPONSE_LIMIT],
            style=discord.TextStyle.paragraph,
            max_length=RESPONSE_LIMIT,
            required=True,
        )
        self.add_item(self.trigger_input)
        self.add_item(self.response_input)

    async def on_submit(self, interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        trigger, response, error = _validate_pair(self.trigger_input.value, self.response_input.value)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        entry = find_entry(interaction.guild.id, self.entry_id)
        if entry is None:
            await interaction.response.send_message("That response is gone. Hit Refresh.", ephemeral=True)
            return
        if not can_modify(interaction.user, entry):
            await interaction.response.send_message("you can't edit this", ephemeral=True)
            return
        update_response(interaction.guild.id, self.entry_id, trigger, response)
        embed = build_responses_embed(interaction.guild)
        view = ResponsesView(list_responses(interaction.guild.id))
        await interaction.response.edit_message(embed=embed, view=view)


def restore_view():
    return ResponsesView(
        [{"id": "__placeholder__", "trigger": "placeholder", "response": "placeholder"}]
    )


def _selected_entry(interaction):
    if interaction.guild is None:
        return None, "Use this in a server."
    responses = list_responses(interaction.guild.id)
    if not responses:
        return None, "Nothing saved yet. Use `!create response`."
    key = _selection_key(interaction)
    entry_id = None if key is None else selected_response.get(key)
    if not entry_id:
        return None, "Pick a response from the menu first."
    entry = find_entry(interaction.guild.id, entry_id)
    if entry is None:
        return None, "That response is gone. Hit Refresh."
    return entry, None


async def handle_edit(interaction):
    entry, error = _selected_entry(interaction)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return
    if not can_modify(interaction.user, entry):
        await interaction.response.send_message("you can't edit this", ephemeral=True)
        return
    await interaction.response.send_modal(EditResponseModal(entry))


async def handle_delete(interaction):
    entry, error = _selected_entry(interaction)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return
    if not can_modify(interaction.user, entry):
        await interaction.response.send_message("you can't delete this", ephemeral=True)
        return
    delete_response(interaction.guild.id, entry["id"])
    if interaction.message is not None:
        _clear_message_selection(interaction.message.id)
    embed = build_responses_embed(interaction.guild)
    view = ResponsesView(list_responses(interaction.guild.id))
    await interaction.response.edit_message(embed=embed, view=view)


async def handle_refresh(interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    embed = build_responses_embed(interaction.guild)
    view = ResponsesView(list_responses(interaction.guild.id))
    await interaction.response.edit_message(embed=embed, view=view)


async def send_responses_panel(ctx):
    if ctx.guild is None:
        await ctx.send("Use this in a server.")
        return
    embed = build_responses_embed(ctx.guild)
    view = ResponsesView(list_responses(ctx.guild.id))
    await ctx.send(embed=embed, view=view)


def _wizard_check(ctx):
    def check(message):
        return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id

    return check


async def _ask(ctx, prompt):
    # Listen before sending. on_message drops this user's messages during the wizard,
    # so a reply that arrives before wait_for is registered would be lost.
    waiter = asyncio.create_task(
        ctx.bot.wait_for("message", check=_wizard_check(ctx), timeout=WIZARD_TIMEOUT)
    )
    await asyncio.sleep(0)
    try:
        await ctx.send(prompt)
        return await waiter
    except Exception:
        if not waiter.done():
            waiter.cancel()
            try:
                await waiter
            except (asyncio.CancelledError, Exception):
                pass
        raise


def _ordinal(number):
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _join_words(words, conjunction="and"):
    if len(words) == 1:
        return words[0]
    if len(words) == 2:
        return f"{words[0]} {conjunction} {words[1]}"
    return ", ".join(words[:-1]) + f", {conjunction} {words[-1]}"


def _match_label(entry):
    if entry.get("match_mode") == "word":
        return "whole word"
    return "inside words"


def _inside_example(trigger):
    return f"b{trigger}"


def _parse_yes_no(text):
    answer = text.strip().casefold().rstrip("!.")
    if answer in {"yes", "y", "yeah", "yep"}:
        return "contains"
    if answer in {"no", "n", "nope", "nah"}:
        return "word"
    return None


def _trigger_problem(raw):
    text = raw.strip()
    if text.startswith("!"):
        return "That trigger starts with ! so it would never fire. Pick a normal word."
    if len(text) > TRIGGER_LIMIT:
        return f"Trigger needs to be {TRIGGER_LIMIT} characters or less."
    return "Trigger needs to be 1 to 80 characters."


async def run_create_wizard(ctx, count=1):
    if ctx.guild is None:
        await ctx.send("Use this in a server.")
        return
    if ctx.author.id in wizard_users:
        await ctx.send("Finish the response you're already creating first.")
        return

    wizard_users.add(ctx.author.id)
    try:
        triggers = []
        for index in range(1, count + 1):
            if count == 1:
                prompt = f"hi {ctx.author.mention} what trigger word do you want?"
            elif index == 1:
                prompt = f"hi {ctx.author.mention} whats the 1st trigger word?"
            else:
                prompt = f"whats the {_ordinal(index)} trigger word?"
            try:
                trigger_message = await _ask(ctx, prompt)
            except asyncio.TimeoutError:
                await ctx.send("Timed out. Run `!create response` again if you still want to add one.")
                return

            trigger, _, error = _validate_pair(trigger_message.content, "ok")
            if error and trigger is None:
                await ctx.send(_trigger_problem(trigger_message.content) + " Run `!create response` again.")
                return
            if any(existing.casefold() == trigger.casefold() for existing in triggers):
                await ctx.send(f"You already used {trigger}. Run `!create response` again and pick different words.")
                return
            triggers.append(trigger)

        if count == 1:
            response_prompt = f"the trigger word you chose is {triggers[0]} what response do you want?"
        else:
            response_prompt = (
                f"the trigger words you chose are {_join_words(triggers)} what response do you want?"
            )
        try:
            response_message = await _ask(ctx, response_prompt)
        except asyncio.TimeoutError:
            await ctx.send("Timed out. Run `!create response` again if you still want to add one.")
            return

        _, response, error = _validate_pair(triggers[0], response_message.content)
        if error:
            if len(response_message.content.strip()) > RESPONSE_LIMIT:
                await ctx.send(
                    f"Response needs to be {RESPONSE_LIMIT} characters or less. Run `!create response` again."
                )
            else:
                await ctx.send("Response needs to be 1 to 500 characters. Run `!create response` again.")
            return

        example = _inside_example(triggers[0])
        if count == 1:
            match_prompt = (
                f"if the trigger word is {triggers[0]}, should {example} count? reply yes or no"
            )
        else:
            match_prompt = (
                f"if the trigger word is {triggers[0]}, should {example} count? "
                "this applies to every trigger you just added. reply yes or no"
            )
        try:
            match_message = await _ask(ctx, match_prompt)
        except asyncio.TimeoutError:
            await ctx.send("Timed out. Run `!create response` again if you still want to add one.")
            return
        match_mode = _parse_yes_no(match_message.content)
        if match_mode is None:
            await ctx.send("Reply yes or no. Run `!create response` again.")
            return

        saved = []
        updated = []
        for trigger in triggers:
            _, overwritten = save_response(
                ctx.guild.id, trigger, response, ctx.author.id, match_mode
            )
            (updated if overwritten else saved).append(trigger)

        if saved and updated:
            lead = f"Saved {_join_words(saved)}. Updated {_join_words(updated)}."
        elif updated:
            lead = "Updated that trigger." if count == 1 else "Updated those triggers."
        else:
            lead = "Saved."
        listed = triggers[0] if count == 1 else _join_words(triggers, "or")
        rule = f"{example} counts." if match_mode == "contains" else f"{example} does not count."
        record = guild_record(ctx.guild.id)
        role = resolve_timeout_role(ctx.guild, record)
        if role is None:
            await ctx.send(
                f"{lead} When the timeout role says {listed}, I'll reply: {response} {rule}\n"
                "This will not fire until a timeout role is set with `!responses role @Timeout`."
            )
            return
        await ctx.send(
            f"{lead} When someone with {role.mention} says {listed}, I'll reply: {response} {rule}"
        )
    finally:
        wizard_users.discard(ctx.author.id)


async def maybe_reply_to_trigger(message):
    if message.guild is None or not isinstance(message.author, discord.Member):
        return
    if message.author.bot:
        return
    record = guild_record(message.guild.id)
    if record is None or not record["responses"]:
        return
    role = resolve_timeout_role(message.guild, record)
    if role is None or role not in message.author.roles:
        return
    on_cooldown = cooldown_remaining(message.guild.id, message.author.id) > 0
    reply = reply_text_for_message(message.content or "", record["responses"], on_cooldown)
    if reply is None:
        return
    await message.channel.send(reply)
    mark_cooldown(message.guild.id, message.author.id)


def add_persistent_view(bot):
    bot.add_view(restore_view())


def register(bot):
    load_custom_responses()

    @bot.command(name="create")
    async def create(ctx, kind: str = None, count: str = "1"):
        if (kind or "").casefold() != "response":
            await ctx.send("Use `!create response` or `!create response 2`.")
            return
        try:
            trigger_count = int(count)
        except (TypeError, ValueError):
            await ctx.send("Use `!create response` or `!create response 2`. The number has to be from 1 to 10.")
            return
        if trigger_count < 1 or trigger_count > MAX_TRIGGERS:
            await ctx.send("Pick a number from 1 to 10. `!create response` is the same as 1.")
            return
        await run_create_wizard(ctx, trigger_count)

    @bot.group(name="responses", invoke_without_command=True)
    async def responses(ctx):
        await send_responses_panel(ctx)

    @responses.command(name="role")
    @commands.has_permissions(manage_guild=True)
    async def responses_role(ctx, role: discord.Role):
        if ctx.guild is None:
            await ctx.send("Use this in a server.")
            return
        set_timeout_role(ctx.guild.id, role.id)
        await ctx.send(
            f"Timeout role set to {role.mention}. Custom responses only fire for members with that role."
        )

    @responses_role.error
    async def responses_role_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need Manage Server to set the timeout role.")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Use `!responses role @Timeout`.")
            return
        if isinstance(error, commands.RoleNotFound):
            await ctx.send("I couldn't find that role. Mention it, like `!responses role @Timeout`.")
            return
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send("Use this in a server.")
            return
        raise error
