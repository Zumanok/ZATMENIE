import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

REACTION_CONFIG_FILE = "config.json"
TICKET_CONFIG_FILE = "ticket_config.json"
INFO_CONFIG_FILE = "info_config.json"


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.reactions = True
intents.message_content = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# CONFIG HELPERS
# ============================================================

def load_json(filename, default=None):
    if default is None:
        default = {}

    if not os.path.exists(filename):
        return default

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as error:
        print(f"[ERROR] Не удалось загрузить {filename}: {error}")
        return default


def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as error:
        print(f"[ERROR] Не удалось сохранить {filename}: {error}")
        return False


reaction_config = load_json(
    REACTION_CONFIG_FILE,
    {"reaction_roles": {}}
)

ticket_config = load_json(
    TICKET_CONFIG_FILE,
    {}
)

info_config = load_json(
    INFO_CONFIG_FILE,
    {}
)


def get_guild_ticket_config(guild_id: int):
    return ticket_config.get(str(guild_id))


def get_guild_info_config(guild_id: int):
    return info_config.get(str(guild_id))


# ============================================================
# TICKET TYPES
# ============================================================

TICKET_TYPES = {
    "shop": {
        "label": "Магазин",
        "emoji": "🛒",
        "description": "Проблемы с покупками и сайтом",
        "category_name": "TICKETS・МАГАЗИН",
        "role_key": "shop_role"
    },
    "tech": {
        "label": "Техническая проблема",
        "emoji": "🛠️",
        "description": "Баги, ошибки и технические проблемы",
        "category_name": "TICKETS・ТЕХ",
        "role_key": "tech_role"
    },
    "report": {
        "label": "Жалоба",
        "emoji": "⚖️",
        "description": "Жалобы на игроков и нарушения",
        "category_name": "TICKETS・ЖАЛОБЫ",
        "role_key": "moderator_role"
    },
    "donate": {
        "label": "Донат",
        "emoji": "💳",
        "description": "Вопросы по донату и платежам",
        "category_name": "TICKETS・ДОНАТ",
        "role_key": "shop_role"
    },
    "general": {
        "label": "Другое",
        "emoji": "❓",
        "description": "Другие вопросы",
        "category_name": "TICKETS・ОБЩИЕ",
        "role_key": "helper_role"
    }
}


# ============================================================
# TICKET HELPERS
# ============================================================

def is_ticket_channel(channel):
    return (
        isinstance(channel, discord.TextChannel)
        and channel.topic
        and channel.topic.startswith("ticket_owner:")
    )


def get_ticket_owner_id(channel):
    if not is_ticket_channel(channel):
        return None

    try:
        return int(
            channel.topic.split("ticket_owner:")[1].split("|")[0]
        )
    except (ValueError, IndexError):
        return None


def get_ticket_type(channel):
    if not is_ticket_channel(channel):
        return None

    try:
        return channel.topic.split("type:")[1].split("|")[0]
    except (ValueError, IndexError):
        return None


def user_can_manage_ticket(member: discord.Member, guild_config: dict):
    if member.guild_permissions.administrator:
        return True

    role_ids = {
        guild_config.get("admin_role"),
        guild_config.get("moderator_role"),
        guild_config.get("shop_role"),
        guild_config.get("tech_role"),
        guild_config.get("helper_role"),
    }

    return any(
        role_id and member.get_role(int(role_id))
        for role_id in role_ids
    )


async def build_transcript(channel: discord.TextChannel):
    lines = []

    async for message in channel.history(limit=None, oldest_first=True):
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = f"{message.author} ({message.author.id})"
        content = message.content or ""

        if message.attachments:
            attachments = " | ".join(
                attachment.url for attachment in message.attachments
            )
            content += f"\n[Вложения] {attachments}"

        lines.append(
            f"[{timestamp}] {author}: {content}"
        )

    return "\n".join(lines) or "Тикет не содержит сообщений."


# ============================================================
# INFO / NEWS HELPERS
# ============================================================

def get_info_channel(guild: discord.Guild, key: str):
    guild_info = get_guild_info_config(guild.id)

    if not guild_info:
        return None

    channel_id = guild_info.get(key)

    if not channel_id:
        return None

    return guild.get_channel(int(channel_id))


def build_news_embed(title: str, text: str):
    embed = discord.Embed(
        title="📢 НОВОСТИ",
        description=f"**{title}**\n\n{text}",
        color=discord.Color.dark_red(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_footer(
        text="ZATMENIE • DAYZ"
    )

    return embed


def build_update_embed(title: str, text: str):
    embed = discord.Embed(
        title="📝 ОБНОВЛЕНИЕ СЕРВЕРА",
        description=f"**{title}**\n\n{text}",
        color=discord.Color.dark_red(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_footer(
        text="ZATMENIE • DAYZ"
    )

    return embed


# ============================================================
# INFORMATION MODAL
# ============================================================

class InformationModal(
    discord.ui.Modal,
    title="Создание информационного сообщения"
):
    information_title = discord.ui.TextInput(
        label="Заголовок",
        placeholder="Например: О сервере ZATMENIE",
        max_length=256,
        required=True
    )

    information_text = discord.ui.TextInput(
        label="Информация",
        placeholder="Введите основную информацию...",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = get_info_channel(
            interaction.guild,
            "information_channel"
        )

        if channel is None:
            await interaction.response.send_message(
                "❌ Канал информации не настроен. "
                "Сначала используйте `/info_setup`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📌 ИНФОРМАЦИЯ",
            description=(
                f"**{self.information_title}**\n\n"
                f"{self.information_text}"
            ),
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.set_footer(text="ZATMENIE • DAYZ")

        try:
            await channel.send(embed=embed)
            await interaction.response.send_message(
                f"✅ Информация опубликована в {channel.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ У бота нет прав отправлять сообщения в этот канал.",
                ephemeral=True
            )


# ============================================================
# RULES MODAL
# ============================================================

class RulesModal(
    discord.ui.Modal,
    title="Создание правил"
):
    rules_title = discord.ui.TextInput(
        label="Заголовок",
        placeholder="Например: Правила сервера",
        max_length=256,
        required=True
    )

    rules_text = discord.ui.TextInput(
        label="Правила",
        placeholder="Введите правила...\nНапример:\n1. ...\n2. ...\n3. ...",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = get_info_channel(
            interaction.guild,
            "rules_channel"
        )

        if channel is None:
            await interaction.response.send_message(
                "❌ Канал правил не настроен. "
                "Сначала используйте `/info_setup`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📜 ПРАВИЛА СЕРВЕРА",
            description=(
                f"**{self.rules_title}**\n\n"
                f"{self.rules_text}"
            ),
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.set_footer(text="ZATMENIE • DAYZ")

        try:
            await channel.send(embed=embed)
            await interaction.response.send_message(
                f"✅ Правила опубликованы в {channel.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ У бота нет прав отправлять сообщения в этот канал.",
                ephemeral=True
            )


# ============================================================
# NEWS MODAL
# ============================================================

class NewsModal(discord.ui.Modal, title="Создание новости"):
    news_title = discord.ui.TextInput(
        label="Заголовок",
        placeholder="Например: Открытие сервера",
        max_length=256,
        required=True
    )

    news_text = discord.ui.TextInput(
        label="Текст новости",
        placeholder="Введите текст новости...",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = get_info_channel(
            interaction.guild,
            "news_channel"
        )

        if channel is None:
            await interaction.response.send_message(
                "❌ Канал новостей не настроен. "
                "Сначала используйте `/info_setup`.",
                ephemeral=True
            )
            return

        embed = build_news_embed(
            str(self.news_title),
            str(self.news_text)
        )

        try:
            await channel.send(embed=embed)

            await interaction.response.send_message(
                f"✅ Новость опубликована в {channel.mention}.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ У бота нет прав отправлять сообщения в канал новостей.",
                ephemeral=True
            )


# ============================================================
# UPDATE MODAL
# ============================================================

class UpdateModal(discord.ui.Modal, title="Создание обновления"):
    update_title = discord.ui.TextInput(
        label="Что изменилось",
        placeholder="Например: Обновление сервера",
        max_length=256,
        required=True
    )

    update_text = discord.ui.TextInput(
        label="Описание изменений",
        placeholder="Опишите изменения...\nМожно использовать • для списка.",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = get_info_channel(
            interaction.guild,
            "update_channel"
        )

        if channel is None:
            await interaction.response.send_message(
                "❌ Канал изменений не настроен. "
                "Сначала используйте `/info_setup`.",
                ephemeral=True
            )
            return

        embed = build_update_embed(
            str(self.update_title),
            str(self.update_text)
        )

        try:
            await channel.send(embed=embed)

            await interaction.response.send_message(
                f"✅ Обновление опубликовано в {channel.mention}.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ У бота нет прав отправлять сообщения в канал изменений.",
                ephemeral=True
            )


# ============================================================
# INFO COMMANDS
# ============================================================

@bot.tree.command(
    name="info_setup",
    description="Настроить каналы информации, правил, новостей и изменений"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    information_channel="Канал с общей информацией",
    rules_channel="Канал с правилами",
    news_channel="Канал новостей",
    update_channel="Канал изменений"
)
async def info_setup(
    interaction: discord.Interaction,
    information_channel: discord.TextChannel,
    rules_channel: discord.TextChannel,
    news_channel: discord.TextChannel,
    update_channel: discord.TextChannel
):
    info_config[str(interaction.guild.id)] = {
        "information_channel": information_channel.id,
        "rules_channel": rules_channel.id,
        "news_channel": news_channel.id,
        "update_channel": update_channel.id
    }

    if not save_json(INFO_CONFIG_FILE, info_config):
        await interaction.response.send_message(
            "❌ Не удалось сохранить info_config.json.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "✅ Информационные каналы настроены.\n\n"
        f"📌 Информация: {information_channel.mention}\n"
        f"📜 Правила: {rules_channel.mention}\n"
        f"📢 Новости: {news_channel.mention}\n"
        f"📝 Изменения: {update_channel.mention}",
        ephemeral=True
    )


@bot.tree.command(
    name="information",
    description="Опубликовать общую информацию через форму"
)
@app_commands.checks.has_permissions(administrator=True)
async def information(interaction: discord.Interaction):
    await interaction.response.send_modal(InformationModal())


@bot.tree.command(
    name="rules",
    description="Опубликовать правила через форму"
)
@app_commands.checks.has_permissions(administrator=True)
async def rules(interaction: discord.Interaction):
    await interaction.response.send_modal(RulesModal())


@bot.tree.command(
    name="news",
    description="Создать новость через форму"
)
@app_commands.checks.has_permissions(administrator=True)
async def news(interaction: discord.Interaction):
    await interaction.response.send_modal(NewsModal())


@bot.tree.command(
    name="update",
    description="Создать публикацию об обновлении через форму"
)
@app_commands.checks.has_permissions(administrator=True)
async def update(interaction: discord.Interaction):
    await interaction.response.send_modal(UpdateModal())


@bot.tree.command(
    name="announce",
    description="Создать важное объявление в канале новостей"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    everyone="Упомянуть @everyone"
)
async def announce(
    interaction: discord.Interaction,
    everyone: bool = False
):
    await interaction.response.send_modal(
        AnnouncementModal(everyone=everyone)
    )


class AnnouncementModal(
    discord.ui.Modal,
    title="Создание объявления"
):
    announce_title = discord.ui.TextInput(
        label="Заголовок",
        placeholder="Например: Важное объявление",
        max_length=256,
        required=True
    )

    announce_text = discord.ui.TextInput(
        label="Текст объявления",
        placeholder="Введите текст...",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True
    )

    def __init__(self, everyone=False):
        super().__init__()
        self.everyone = everyone

    async def on_submit(self, interaction: discord.Interaction):
        channel = get_info_channel(
            interaction.guild,
            "news_channel"
        )

        if channel is None:
            await interaction.response.send_message(
                "❌ Канал новостей не настроен. "
                "Сначала используйте `/info_setup`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🚨 {self.announce_title}",
            description=str(self.announce_text),
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.set_footer(
            text="ZATMENIE • DAYZ"
        )

        content = "@everyone" if self.everyone else None

        try:
            await channel.send(
                content=content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    everyone=self.everyone
                )
            )

            await interaction.response.send_message(
                f"✅ Объявление опубликовано в {channel.mention}.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ У бота нет прав публиковать сообщения в этом канале.",
                ephemeral=True
            )


# ============================================================
# REACTION ROLES
# ============================================================

@bot.event
async def on_raw_reaction_add(payload):
    print(
        f"[REACTION] Emoji: {payload.emoji} | "
        f"User ID: {payload.user_id} | "
        f"Message ID: {payload.message_id}"
    )

    if bot.user and payload.user_id == bot.user.id:
        return

    if payload.guild_id is None:
        return

    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    reaction_roles = reaction_config.get(
        "reaction_roles",
        {}
    )

    if message_id not in reaction_roles:
        return

    if emoji not in reaction_roles[message_id]:
        return

    role_id = reaction_roles[message_id][emoji]

    guild = bot.get_guild(payload.guild_id)

    if guild is None:
        return

    member = guild.get_member(payload.user_id)

    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except (discord.NotFound, discord.HTTPException):
            return

    role = guild.get_role(role_id)

    if role is None:
        return

    bot_member = guild.me

    if bot_member is None:
        return

    if role >= bot_member.top_role:
        print(
            f"[ERROR] Бот не может выдать роль {role.name}. "
            "Роль бота должна быть выше."
        )
        return

    if role in member.roles:
        return

    try:
        await member.add_roles(
            role,
            reason="Reaction Role"
        )
        print(f"[ROLE +] {member} -> {role.name}")

    except discord.Forbidden:
        print("[ERROR] У бота недостаточно прав для выдачи роли.")

    except discord.HTTPException as error:
        print(f"[ERROR] Discord API: {error}")


@bot.event
async def on_raw_reaction_remove(payload):
    if bot.user and payload.user_id == bot.user.id:
        return

    if payload.guild_id is None:
        return

    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    reaction_roles = reaction_config.get(
        "reaction_roles",
        {}
    )

    if message_id not in reaction_roles:
        return

    if emoji not in reaction_roles[message_id]:
        return

    role_id = reaction_roles[message_id][emoji]

    guild = bot.get_guild(payload.guild_id)

    if guild is None:
        return

    member = guild.get_member(payload.user_id)

    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except (discord.NotFound, discord.HTTPException):
            return

    role = guild.get_role(role_id)

    if role is None or role not in member.roles:
        return

    try:
        await member.remove_roles(
            role,
            reason="Reaction Role removed"
        )
        print(f"[ROLE -] {member} -> {role.name}")

    except discord.Forbidden:
        print(f"[ERROR] Недостаточно прав для снятия роли {role.name}.")

    except discord.HTTPException as error:
        print(f"[ERROR] Discord API: {error}")


@bot.tree.command(
    name="reactionrole",
    description="Создать сообщение с реакциями для получения ролей"
)
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(
    channel="Канал, куда отправить сообщение",
    title="Заголовок сообщения",
    description="Текст сообщения"
)
async def reactionrole(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    description: str
):
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.dark_red()
    )

    embed.set_footer(
        text="Выберите реакцию, чтобы получить роль."
    )

    try:
        message = await channel.send(embed=embed)

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ У бота нет права отправлять сообщения в этот канал.",
            ephemeral=True
        )
        return

    except discord.HTTPException as error:
        await interaction.response.send_message(
            f"❌ Ошибка Discord: {error}",
            ephemeral=True
        )
        return

    reaction_config.setdefault("reaction_roles", {})
    reaction_config["reaction_roles"][str(message.id)] = {}

    save_json(
        REACTION_CONFIG_FILE,
        reaction_config
    )

    await interaction.response.send_message(
        f"✅ Сообщение создано:\n"
        f"{message.jump_url}\n\n"
        f"Теперь используй `/addrole` для привязки реакций к ролям.",
        ephemeral=True
    )


@bot.tree.command(
    name="addrole",
    description="Привязать реакцию к роли"
)
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(
    message_id="ID сообщения с реакциями",
    emoji="Эмодзи, например 👍",
    role="Роль, которую нужно выдавать"
)
async def addrole(
    interaction: discord.Interaction,
    message_id: str,
    emoji: str,
    role: discord.Role
):
    try:
        message_id_int = int(message_id)
    except ValueError:
        await interaction.response.send_message(
            "❌ Неверный ID сообщения.",
            ephemeral=True
        )
        return

    if interaction.guild is None:
        await interaction.response.send_message(
            "❌ Команду нельзя использовать в личных сообщениях.",
            ephemeral=True
        )
        return

    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "❌ Команду нужно использовать в текстовом канале.",
            ephemeral=True
        )
        return

    try:
        message = await channel.fetch_message(message_id_int)

    except discord.NotFound:
        await interaction.response.send_message(
            "❌ Сообщение не найдено в этом канале.",
            ephemeral=True
        )
        return

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ У бота нет права читать сообщения в этом канале.",
            ephemeral=True
        )
        return

    bot_member = interaction.guild.me

    if bot_member is None:
        await interaction.response.send_message(
            "❌ Не удалось определить роль бота.",
            ephemeral=True
        )
        return

    if role >= bot_member.top_role:
        await interaction.response.send_message(
            "❌ Я не могу выдавать эту роль.\n\n"
            "Моя роль должна находиться выше этой роли.",
            ephemeral=True
        )
        return

    if not bot_member.guild_permissions.manage_roles:
        await interaction.response.send_message(
            "❌ У бота нет права Управление ролями.",
            ephemeral=True
        )
        return

    try:
        await message.add_reaction(emoji)

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Бот не может добавить реакцию.\n"
            "Проверь права Добавлять реакции и Просматривать историю сообщений.",
            ephemeral=True
        )
        return

    except discord.HTTPException as error:
        await interaction.response.send_message(
            f"❌ Не удалось добавить такую реакцию.\nОшибка: {error}",
            ephemeral=True
        )
        return

    reaction_config.setdefault("reaction_roles", {})
    reaction_config["reaction_roles"].setdefault(
        message_id,
        {}
    )

    reaction_config["reaction_roles"][message_id][emoji] = role.id

    if not save_json(
        REACTION_CONFIG_FILE,
        reaction_config
    ):
        await interaction.response.send_message(
            "❌ Не удалось сохранить config.json.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"✅ Reaction Role настроен!\n\n"
        f"{emoji} → {role.mention}\n"
        f"Сообщение: `{message_id}`",
        ephemeral=True
    )


@bot.tree.command(
    name="removerole",
    description="Удалить привязку реакции к роли"
)
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.describe(
    message_id="ID сообщения",
    emoji="Эмодзи"
)
async def removerole(
    interaction: discord.Interaction,
    message_id: str,
    emoji: str
):
    reaction_roles = reaction_config.get(
        "reaction_roles",
        {}
    )

    if message_id not in reaction_roles:
        await interaction.response.send_message(
            "❌ Такое сообщение не зарегистрировано.",
            ephemeral=True
        )
        return

    if emoji not in reaction_roles[message_id]:
        await interaction.response.send_message(
            "❌ Такая реакция не привязана к роли.",
            ephemeral=True
        )
        return

    del reaction_roles[message_id][emoji]

    save_json(
        REACTION_CONFIG_FILE,
        reaction_config
    )

    await interaction.response.send_message(
        f"✅ Привязка {emoji} удалена.",
        ephemeral=True
    )


@bot.tree.command(
    name="roles",
    description="Показать все reaction roles"
)
@app_commands.checks.has_permissions(manage_roles=True)
async def roles(interaction: discord.Interaction):
    reaction_roles = reaction_config.get(
        "reaction_roles",
        {}
    )

    if not reaction_roles:
        await interaction.response.send_message(
            "📭 Reaction Roles пока не настроены.",
            ephemeral=True
        )
        return

    text = "## Reaction Roles\n\n"

    for message_id, roles_data in reaction_roles.items():
        text += f"**Сообщение:** `{message_id}`\n"

        for emoji, role_id in roles_data.items():
            role = interaction.guild.get_role(role_id)

            if role:
                text += f"{emoji} → {role.mention}\n"
            else:
                text += f"{emoji} → `роль удалена`\n"

        text += "\n"

    await interaction.response.send_message(
        text,
        ephemeral=True
    )


# ============================================================
# TICKET PANEL
# ============================================================

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = []

        for key, data in TICKET_TYPES.items():
            options.append(
                discord.SelectOption(
                    label=data["label"],
                    value=key,
                    emoji=data["emoji"],
                    description=data["description"]
                )
            )

        super().__init__(
            placeholder="Выберите тип тикета | Select ticket type",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_type_select"
        )

    async def callback(self, interaction: discord.Interaction):
        ticket_type = self.values[0]
        await create_ticket(interaction, ticket_type)


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ============================================================
# TICKET BUTTONS
# ============================================================

class CloseConfirmView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=60)
        self.channel = channel

    @discord.ui.button(
        label="Закрыть тикет",
        style=discord.ButtonStyle.danger,
        emoji="🔒"
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await close_ticket(
            interaction,
            self.channel
        )

    @discord.ui.button(
        label="Отмена",
        style=discord.ButtonStyle.secondary
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="Закрытие тикета отменено.",
            view=None
        )


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Закрыть",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket_close"
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        channel = interaction.channel

        if not is_ticket_channel(channel):
            await interaction.response.send_message(
                "❌ Эта кнопка работает только внутри тикета.",
                ephemeral=True
            )
            return

        guild_config = get_guild_ticket_config(
            interaction.guild.id
        )

        if not guild_config or not user_can_manage_ticket(
            interaction.user,
            guild_config
        ):
            owner_id = get_ticket_owner_id(channel)

            if interaction.user.id != owner_id:
                await interaction.response.send_message(
                    "❌ У вас нет прав для закрытия этого тикета.",
                    ephemeral=True
                )
                return

        await interaction.response.send_message(
            "Вы уверены, что хотите закрыть тикет?",
            view=CloseConfirmView(channel),
            ephemeral=True
        )

    @discord.ui.button(
        label="Взять тикет",
        style=discord.ButtonStyle.primary,
        emoji="👤",
        custom_id="ticket_claim"
    )
    async def claim(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        channel = interaction.channel

        if not is_ticket_channel(channel):
            await interaction.response.send_message(
                "❌ Эта кнопка работает только внутри тикета.",
                ephemeral=True
            )
            return

        guild_config = get_guild_ticket_config(
            interaction.guild.id
        )

        if not guild_config or not user_can_manage_ticket(
            interaction.user,
            guild_config
        ):
            await interaction.response.send_message(
                "❌ У вас нет прав для работы с этим тикетом.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Тикет взят в работу",
            description=f"Ответственный: {interaction.user.mention}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        await channel.send(embed=embed)

        await interaction.response.send_message(
            "✅ Тикет закреплён за вами.",
            ephemeral=True
        )

    @discord.ui.button(
        label="Добавить",
        style=discord.ButtonStyle.secondary,
        emoji="➕",
        custom_id="ticket_add"
    )
    async def add_user(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        channel = interaction.channel
        guild_config = get_guild_ticket_config(
            interaction.guild.id
        )

        if not is_ticket_channel(channel):
            return

        if not guild_config or not user_can_manage_ticket(
            interaction.user,
            guild_config
        ):
            await interaction.response.send_message(
                "❌ Недостаточно прав.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Используйте `/ticket_add @пользователь`.",
            ephemeral=True
        )


# ============================================================
# CREATE TICKET
# ============================================================

async def create_ticket(
    interaction: discord.Interaction,
    ticket_type: str
):
    guild = interaction.guild

    if guild is None:
        return

    guild_config = get_guild_ticket_config(guild.id)

    if not guild_config:
        await interaction.response.send_message(
            "❌ Система тикетов ещё не настроена.",
            ephemeral=True
        )
        return

    data = TICKET_TYPES[ticket_type]
    category_id = guild_config["categories"].get(ticket_type)

    category = guild.get_channel(int(category_id))

    if category is None:
        await interaction.response.send_message(
            "❌ Категория тикетов не найдена.",
            ephemeral=True
        )
        return

    for channel in category.text_channels:
        if get_ticket_owner_id(channel) == interaction.user.id:
            await interaction.response.send_message(
                f"❌ У вас уже есть открытый тикет: {channel.mention}",
                ephemeral=True
            )
            return

    support_role_id = guild_config.get(
        data["role_key"]
    )

    support_role = (
        guild.get_role(int(support_role_id))
        if support_role_id
        else None
    )

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )
    }

    admin_role_id = guild_config.get("admin_role")

    if admin_role_id:
        admin_role = guild.get_role(
            int(admin_role_id)
        )

        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                attach_files=True,
                embed_links=True
            )

    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )

    channel_name = (
        f"{data['emoji']}-{ticket_type}-{interaction.user.name}"
    )

    channel_name = (
        channel_name.lower()
        .replace(" ", "-")[:90]
    )

    topic = (
        f"ticket_owner:{interaction.user.id}"
        f"|type:{ticket_type}"
        f"|created:{datetime.now(timezone.utc).isoformat()}"
    )

    await interaction.response.defer(
        ephemeral=True
    )

    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        topic=topic,
        reason=f"Создание тикета: {data['label']}"
    )

    embed = discord.Embed(
        title=f"Тикет — {data['label']}",
        description=(
            f"Здравствуйте, {interaction.user.mention}.\n\n"
            f"Опишите вашу проблему максимально подробно.\n"
            f"При необходимости приложите скриншоты или другие материалы.\n\n"
            f"**Тип обращения:** {data['label']}\n"
            f"**Статус:** Открыт"
        ),
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_footer(
        text="Система поддержки"
    )

    mention_text = interaction.user.mention

    if support_role:
        mention_text += f" {support_role.mention}"

    await channel.send(
        content=mention_text,
        embed=embed,
        view=TicketControlView()
    )

    await interaction.followup.send(
        f"✅ Тикет создан: {channel.mention}",
        ephemeral=True
    )


# ============================================================
# CLOSE TICKET
# ============================================================

async def close_ticket(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    guild_config = get_guild_ticket_config(
        interaction.guild.id
    )

    transcript = await build_transcript(channel)

    filename = f"{channel.name}-transcript.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(transcript)

    log_channel_id = (
        guild_config.get("log_channel")
        if guild_config
        else None
    )

    log_channel = (
        interaction.guild.get_channel(
            int(log_channel_id)
        )
        if log_channel_id
        else None
    )

    if log_channel:
        embed = discord.Embed(
            title="Тикет закрыт",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Тикет",
            value=channel.name,
            inline=False
        )

        owner_id = get_ticket_owner_id(channel)

        if owner_id:
            embed.add_field(
                name="Автор",
                value=f"<@{owner_id}>",
                inline=True
            )

        embed.add_field(
            name="Закрыл",
            value=interaction.user.mention,
            inline=True
        )

        await log_channel.send(
            embed=embed,
            file=discord.File(filename)
        )

    await interaction.response.edit_message(
        content="🔒 Тикет закрывается...",
        view=None
    )

    await channel.set_permissions(
        interaction.guild.default_role,
        view_channel=False
    )

    owner_id = get_ticket_owner_id(channel)

    if owner_id:
        owner = interaction.guild.get_member(owner_id)

        if owner:
            await channel.set_permissions(
                owner,
                view_channel=False,
                send_messages=False
            )

    await channel.edit(
        name=f"closed-{channel.name}"[:100],
        topic=f"{channel.topic}|closed_by:{interaction.user.id}"
    )

    await channel.send(
        f"🔒 Тикет закрыт пользователем {interaction.user.mention}."
    )

    try:
        os.remove(filename)
    except OSError:
        pass


# ============================================================
# TICKET SETUP
# ============================================================

@bot.tree.command(
    name="ticket_setup",
    description="Настроить систему тикетов"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    admin_role="Роль, которая видит все тикеты",
    shop_role="Команда магазина / доната",
    tech_role="Команда технической поддержки",
    moderator_role="Модераторы, работающие с жалобами",
    helper_role="Хелперы для общих обращений",
    log_channel="Канал для логов закрытых тикетов"
)
async def ticket_setup(
    interaction: discord.Interaction,
    admin_role: discord.Role,
    shop_role: discord.Role,
    tech_role: discord.Role,
    moderator_role: discord.Role,
    helper_role: discord.Role,
    log_channel: discord.TextChannel
):
    guild = interaction.guild

    await interaction.response.defer(
        ephemeral=True
    )

    categories = {}

    for key, data in TICKET_TYPES.items():
        existing = discord.utils.get(
            guild.categories,
            name=data["category_name"]
        )

        if existing:
            category = existing
        else:
            category = await guild.create_category(
                data["category_name"],
                reason="Настройка системы тикетов"
            )

        categories[key] = category.id

    ticket_config[str(guild.id)] = {
        "admin_role": admin_role.id,
        "shop_role": shop_role.id,
        "tech_role": tech_role.id,
        "moderator_role": moderator_role.id,
        "helper_role": helper_role.id,
        "log_channel": log_channel.id,
        "categories": categories
    }

    save_json(
        TICKET_CONFIG_FILE,
        ticket_config
    )

    await interaction.followup.send(
        "✅ Система тикетов настроена.\n\n"
        "Созданы/найдены категории:\n"
        "🛒 Магазин\n"
        "🛠️ Технические проблемы\n"
        "⚖️ Жалобы\n"
        "💳 Донат\n"
        "❓ Общие\n\n"
        "Теперь используйте `/ticket_panel`.",
        ephemeral=True
    )


# ============================================================
# TICKET PANEL COMMAND
# ============================================================

@bot.tree.command(
    name="ticket_panel",
    description="Отправить панель создания тикетов"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    channel="Канал, куда отправить панель"
)
async def ticket_panel(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    if not get_guild_ticket_config(interaction.guild.id):
        await interaction.response.send_message(
            "❌ Сначала выполните `/ticket_setup`.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Поддержка | Support",
        description=(
            "Если у вас возникли проблемы или вопросы, "
            "вы можете создать тикет для связи с администрацией сервера.\n\n"
            "• Ознакомьтесь с правилами сервера\n"
            "• Не создавайте дублирующие тикеты\n"
            "• Подробно опишите проблему\n"
            "• Ответ может занять некоторое время\n"
            "• Указывайте всю необходимую информацию\n\n"
            "**Выберите тип обращения ниже.**"
        ),
        color=discord.Color.red()
    )

    embed.set_footer(
        text="Система поддержки"
    )

    await channel.send(
        embed=embed,
        view=TicketPanelView()
    )

    await interaction.response.send_message(
        f"✅ Панель отправлена в {channel.mention}.",
        ephemeral=True
    )


# ============================================================
# TICKET ADD
# ============================================================

@bot.tree.command(
    name="ticket_add",
    description="Добавить пользователя в текущий тикет"
)
@app_commands.describe(
    user="Пользователь"
)
async def ticket_add(
    interaction: discord.Interaction,
    user: discord.Member
):
    channel = interaction.channel
    guild_config = get_guild_ticket_config(
        interaction.guild.id
    )

    if not is_ticket_channel(channel):
        await interaction.response.send_message(
            "❌ Команду можно использовать только внутри тикета.",
            ephemeral=True
        )
        return

    if not guild_config or not user_can_manage_ticket(
        interaction.user,
        guild_config
    ):
        await interaction.response.send_message(
            "❌ Недостаточно прав.",
            ephemeral=True
        )
        return

    await channel.set_permissions(
        user,
        view_channel=True,
        send_messages=True,
        read_message_history=True,
        attach_files=True,
        embed_links=True
    )

    await interaction.response.send_message(
        f"✅ {user.mention} добавлен в тикет."
    )


# ============================================================
# TICKET REMOVE
# ============================================================

@bot.tree.command(
    name="ticket_remove",
    description="Удалить пользователя из текущего тикета"
)
@app_commands.describe(
    user="Пользователь"
)
async def ticket_remove(
    interaction: discord.Interaction,
    user: discord.Member
):
    channel = interaction.channel
    guild_config = get_guild_ticket_config(
        interaction.guild.id
    )

    if not is_ticket_channel(channel):
        await interaction.response.send_message(
            "❌ Команду можно использовать только внутри тикета.",
            ephemeral=True
        )
        return

    if not guild_config or not user_can_manage_ticket(
        interaction.user,
        guild_config
    ):
        await interaction.response.send_message(
            "❌ Недостаточно прав.",
            ephemeral=True
        )
        return

    await channel.set_permissions(
        user,
        overwrite=None
    )

    await interaction.response.send_message(
        f"✅ {user.mention} удалён из тикета."
    )


# ============================================================
# TICKET CLOSE COMMAND
# ============================================================

@bot.tree.command(
    name="ticket_close",
    description="Закрыть текущий тикет"
)
async def ticket_close_command(
    interaction: discord.Interaction
):
    channel = interaction.channel

    if not is_ticket_channel(channel):
        await interaction.response.send_message(
            "❌ Вы не находитесь в тикете.",
            ephemeral=True
        )
        return

    guild_config = get_guild_ticket_config(
        interaction.guild.id
    )

    if not guild_config:
        return

    if not user_can_manage_ticket(
        interaction.user,
        guild_config
    ):
        owner_id = get_ticket_owner_id(channel)

        if interaction.user.id != owner_id:
            await interaction.response.send_message(
                "❌ Недостаточно прав.",
                ephemeral=True
            )
            return

    await interaction.response.send_message(
        "Вы уверены, что хотите закрыть тикет?",
        view=CloseConfirmView(channel),
        ephemeral=True
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

async def permission_error_handler(
    interaction: discord.Interaction,
    error,
    message="❌ Недостаточно прав."
):
    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                message,
                ephemeral=True
            )


@ticket_setup.error
async def ticket_setup_error(
    interaction: discord.Interaction,
    error
):
    await permission_error_handler(
        interaction,
        error,
        "❌ Нужны права администратора."
    )


@ticket_panel.error
async def ticket_panel_error(
    interaction: discord.Interaction,
    error
):
    await permission_error_handler(
        interaction,
        error,
        "❌ Нужны права администратора."
    )


@info_setup.error
async def info_setup_error(
    interaction: discord.Interaction,
    error
):
    await permission_error_handler(
        interaction,
        error,
        "❌ Нужны права администратора."
    )


@information.error
async def information_error(
    interaction: discord.Interaction,
    error
):
    await permission_error_handler(
        interaction,
        error,
        "❌ Нужны права администратора."
    )


@rules.error
async def rules_error(
    interaction: discord.Interaction,
    error
):
    await permission_error_handler(
        interaction,
        error,
        "❌ Нужны права администратора."
    )


@news.error
async def news_error(
    interaction: discord.Interaction,
    error
):
    await permission_error_handler(
        interaction,
        error,
        "❌ Нужны права администратора."
    )


@update.error
async def update_error(
    interaction: discord.Interaction,
    error
):
    await permission_error_handler(
        interaction,
        error,
        "❌ Нужны права администратора."
    )


@announce.error
async def announce_error(
    interaction: discord.Interaction,
    error
):
    await permission_error_handler(
        interaction,
        error,
        "❌ Нужны права администратора."
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"Бот запущен: {bot.user}")
    print(f"ID: {bot.user.id}")
    print(f"Серверов: {len(bot.guilds)}")
    print("=" * 60)

    # Persistent views.
    # add_view вызывается только один раз за процесс.
    if not getattr(bot, "_persistent_views_added", False):
        bot.add_view(TicketPanelView())
        bot.add_view(TicketControlView())
        bot._persistent_views_added = True

    try:
        synced = await bot.tree.sync()
        print(f"Slash-команд синхронизировано: {len(synced)}")
    except Exception as error:
        print(f"[ERROR] Ошибка синхронизации команд: {error}")


# ============================================================
# START
# ============================================================

if not TOKEN:
    print(
        "❌ ОШИБКА: переменная DISCORD_TOKEN не найдена в .env"
    )
else:
    print("✅ DISCORD_TOKEN найден.")

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print(
            "❌ Discord отклонил токен. "
            "Проверь DISCORD_TOKEN."
        )
    except Exception as error:
        print(
            f"❌ Критическая ошибка запуска: {error}"
        )
