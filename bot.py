import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import random
from keep_alive import keep_alive
from tabulate import tabulate
import aiohttp
import re
from collections import defaultdict
from urllib.parse import quote
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from datetime import time as dt_time
import csv
import io

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

player_stats = {}
browser = None
CURRENT_TFT_SET = "set17"
TRAITS_DATA_URL = "https://tft.dakgg.io/api/v1/data/traits?hl=en&season={season}"
LEADERBOARD_DATA_FILE = "leaderboard_data.json"
tracked_players = set()
DAILY_LEADERBOARD_CONFIG = {}
PST_TIMEZONE = ZoneInfo("America/Los_Angeles")
COMPS_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1QREhel46OklYQ3qeWbjZ62fBpXiYK7Jq-xVjPTrnDnY/export?format=csv&gid=1524437377"
comps_cache = []

@bot.event
async def on_ready():
    load_leaderboard_data()
    refresh_comps_cache()
    if not daily_leaderboard_refresh.is_running():
        daily_leaderboard_refresh.start()
    if not daily_leaderboard_poster.is_running():
        daily_leaderboard_poster.start()
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if bot.user.mentioned_in(message):
        await message.channel.send("hi")
    await bot.process_commands(message)

@bot.command(name='loser')
async def loser(ctx, member: discord.Member):
    messages = [
        "HAHA HARDSTUCK",
        "Did you try playing FLEXIBLE??",
        "Reroll comps OP",
        "Demoted",
        "Get Mortdogged"
    ]
    
    selected_message = random.choice(messages)
    message = f"{selected_message} {member.mention}"

    embed = discord.Embed(description=message)
    embed.set_thumbnail(url=member.avatar.url)
    
    await ctx.send(embed=embed)

@bot.command()
async def weston(ctx):
    embed = discord.Embed(
        title="🐐 WESTON MY GOAT 🐐",
        description="No one does it like Weston. Absolute **legend**, unmatched comps, and the unmatched goat of tft.",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url="https://media.tenor.com/UQBLN9Ei6SAAAAAC/goat.gif") 
    embed.set_image(url="https://media.tenor.com/9RgF7SLzJMoAAAAC/goat-king.gif")  

    embed.add_field(name="✨ TFT Rank", value="Challenger", inline=True)
    embed.add_field(name="🔥 Style", value="Boombot", inline=True)
    embed.add_field(name="🏆 Rank", value="#1 GOAT", inline=False)

    embed.set_footer(text="This message was brought to you by the Weston fan club.")

    await ctx.send(embed=embed)

@bot.command(name='tft')
async def tft(ctx, *, summoner_name):
    try:
        profile_data = scrape_tft_profile(summoner_name)
        if not profile_data:
            await ctx.send(f"Could not retrieve valid data for {summoner_name}. Please check the summoner name or region.")
            return
        url = profile_data["url"]
        stats = profile_data["stats"]
        rank_text = profile_data["rank_text"]
        rank_color = profile_data["rank_color"]
        lp_text = profile_data["lp_text"]
        icon_url = profile_data["icon_url"]
        tier_icon_url = profile_data["tier_icon_url"]

        # Create an embed
        embed = discord.Embed(
            title=f"{summoner_name}'s TFT Stats",
            url=url,
            color=discord.Color.blue()
        )

        embed.add_field(name="Rank", value=f"{rank_text} {lp_text}", inline=False)
        embed.add_field(name="Wins", value=stats['Wins'], inline=True)
        embed.add_field(name="Win Rate", value=stats['Win Rate'], inline=True)
        embed.add_field(name="Top 4s", value=stats['Top 4s'], inline=True)
        embed.add_field(name="Top 4 Rate", value=stats['Top 4 Rate'], inline=True)
        embed.add_field(name="Games Played", value=stats['Games Played'], inline=True)
        embed.add_field(name="Average Rank", value=stats['Average Rank'], inline=True)

        if icon_url:
            embed.set_thumbnail(url=icon_url)
        if tier_icon_url:
            embed.set_image(url=tier_icon_url)

        embed.color = discord.Color.from_str(rank_color)

        await ctx.send(embed=embed)

        upsert_player_stats(summoner_name, stats, rank_text, lp_text, tier_icon_url)
        save_leaderboard_data()

    except Exception as e:
        await ctx.send(f"An error occurred while retrieving data for {summoner_name}: {e}")


@bot.command(name='leaderboard')
async def leaderboard(ctx, stat: str):
    valid_stats = ['wins', 'winrate', 'top4s', 'top4rate', 'games', 'avgrank', 'rank']  # Added 'rank' to valid stats

    stat = stat.lower()

    if stat not in valid_stats:
        await ctx.send(f"Invalid stat. Choose from: {', '.join(valid_stats)}")
        return

    # Map stat to key in player_stats
    stat_mapping = {
        'wins': 'Wins',
        'winrate': 'Win Rate',
        'top4s': 'Top 4s',
        'top4rate': 'Top 4 Rate',
        'games': 'Games Played',
        'avgrank': 'Average Rank',
        'rank': 'Rank'
    }

    stat_key = stat_mapping[stat]

    if not player_stats:
        await ctx.send("No stats available. Use `!tft <name>` to add some.")
        return

    # Sort based on stat
    if stat_key == 'Rank':
        sorted_stats = sorted(player_stats.items(), key=lambda x: (get_rank_value(x[1][stat_key]), get_lp_value(x[1][stat_key])), reverse=True)
    elif stat_key == 'Average Rank':
        sorted_stats = sorted(player_stats.items(), key=lambda x: float(x[1][stat_key].replace('#', '').strip()), reverse=False)
    elif stat_key in ['Win Rate', 'Top 4 Rate']:
        sorted_stats = sorted(player_stats.items(), key=lambda x: float(x[1][stat_key].replace('%', '').strip()), reverse=True)
    else:
        sorted_stats = sorted(player_stats.items(), key=lambda x: int(x[1][stat_key].replace(",", "")), reverse=True)

    # old
    # embed = discord.Embed(
    #     title=f"**Leaderboard - Sorted by {stat_key.capitalize()}**",
    #     color=discord.Color.blue()  # You can change the color here if you'd like
    # )

    # for i, (name, stats) in enumerate(sorted_stats, start=1):
    #     if stat_key == 'Rank':
    #         rank_info = f"{stats[stat_key]}".strip()
    #         embed.add_field(name=f"{i}. **{name}**", value=rank_info, inline=False)
    #     else:
    #         embed.add_field(name=f"{i}. **{name}**", value=stats[stat_key], inline=False)

    # await ctx.send(embed=embed)

    cuteness = [
        "✨💖✨",
        "💕🌸💕",
        "🌟💗🌟",
        "🌈💝🌈",
        "🪄💓🪄"
    ]
    cutey = random.choice(cuteness)

    leaderboard_msg = f"**Leaderboard - Sorted by {stat_key.capitalize()}** {cutey}\n"
    for i, (name, stats) in enumerate(sorted_stats, start=1):
        if stat_key == 'Rank':
            rank_info = f"{stats[stat_key]}".strip()
            leaderboard_msg += f"{i}. {name} - {rank_info}\n"
        else:
            leaderboard_msg += f"{i}. {name} - {stats[stat_key]}\n"

    await ctx.send(leaderboard_msg)

def get_rank_value(rank_str):
    rank_order = {
        'Iron': 1,
        'Bronze': 2,
        'Silver': 3,
        'Gold': 4,
        'Platinum': 5,
        'Diamond': 6,
        'Master': 7,
        'Grandmaster': 8,
        'Challenger': 9
    }
    
    rank_name = rank_str.split()[0]
    return rank_order.get(rank_name, 0)

def get_lp_value(rank_str):
    try:
        lp_value = rank_str.split()[-1].replace('LP', '').strip()
        return int(lp_value) if lp_value else 0
    except ValueError:
        return 0

DEFAULT_TRAIT_MAP = {
    "TFT17_MeleeTrait": "Melee",
    "TFT17_SummonTrait": "Summoner",
    "TFT17_ShieldTank": "Shield Tank",
    "TFT17_SpaceGroove": "Space Groove",
    "TFT17_ManaTrait": "Mana",
    "TFT17_RangedTrait": "Ranged",
    "TFT17_MorganaUniqueTrait": "Morgana",
    "TFT17_Fateweaver": "Fateweaver",
    "TFT17_JhinUniqueTrait": "Jhin",
    "TFT17_ShenUniqueTrait": "Shen",
    "TFT17_DarkStar": "Dark Star",
    "TFT17_FlexTrait": "Flex",
    "TFT17_ResistTank": "Resist Tank",
    "TFT17_AssassinTrait": "Assassin",
    "TFT17_BlitzcrankUniqueTrait": "Blitzcrank",
    "TFT17_SonaUniqueTrait": "Sona",
    "TFT17_RhaastUniqueTrait": "Rhaast",
    "TFT17_DRX": "DRX",
    "TFT17_APTrait": "AP",
    "TFT17_PsyOps": "PsyOps",
    "TFT17_Timebreaker": "Timebreaker",
    "TFT17_VexUniqueTrait": "Vex",
    "TFT17_Astronaut": "Astronaut",
    "TFT17_FioraUniqueTrait": "Fiora",
}
Trait_Map = DEFAULT_TRAIT_MAP.copy()

def normalize_trait_name(raw_trait: str) -> str:
    if raw_trait in Trait_Map:
        return Trait_Map[raw_trait]

    cleaned = raw_trait
    cleaned = re.sub(r"^TFT\d+_", "", cleaned)
    cleaned = cleaned.replace("UniqueTrait", "")
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)
    cleaned = cleaned.replace("_", " ").strip()
    return cleaned or raw_trait

async def fetch_traits(summoner_name: str):
    await refresh_trait_map()
    encoded_name = quote(summoner_name)
    url = f"https://tft.dakgg.io/api/v1/summoners/na1/{encoded_name}/overviews?season={CURRENT_TFT_SET}"
    
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=30) as resp:
                if resp.status != 200:
                    print(f"Failed to fetch data for {summoner_name}, status: {resp.status}")
                    return []
                data = await resp.json()
        except Exception as e:
            print(f"Error during API fetch: {e}")
            return []

    trait_stats = []
    try:
        overviews = data.get("summonerSeasonOverviews", [])
        for overview in overviews:
            match_stats = overview.get("matchStats", [])
            for match in match_stats:
                if match.get("key") == "last20" and match.get("plays") == 20:
                    trait_stats = match.get("traitStats", [])
                    break
            if trait_stats:
                break
    except Exception as e:
        print(f"Error parsing nested traitStats: {e}")
        return []

    if not trait_stats:
        print("No traitStats found in valid last20 match stats")
        return []

    # print("Raw trait stats:", trait_stats)

    grouped_traits = defaultdict(lambda: {"plays": 0, "wins": 0, "tops": 0, "placements": 0})

    for entry in trait_stats:
        try:
            key_value = entry.get("key")
            if isinstance(key_value, list) and key_value:
                raw_trait = key_value[0]
            elif isinstance(key_value, str):
                raw_trait = key_value
            else:
                raise KeyError("Missing trait key")
            grouped_traits[raw_trait]["plays"] += entry.get("plays", 0)
            grouped_traits[raw_trait]["wins"] += entry.get("wins", 0)
            grouped_traits[raw_trait]["tops"] += entry.get("tops", 0)
            grouped_traits[raw_trait]["placements"] += entry.get("placements", 0)
        except (KeyError, TypeError) as e:
            print(f"Skipping malformed entry: {e}")
            continue

    trait_data = []
    for raw_trait, stats in grouped_traits.items():
        plays = stats["plays"]
        wins = stats["wins"]
        tops = stats["tops"]
        placements = stats["placements"]

        trait_clean = normalize_trait_name(raw_trait)
        win_rate = (wins / plays) * 100 if plays else 0
        top4_rate = (tops / plays) * 100 if plays else 0
        avg_rank = placements / plays if plays else 0

        trait_data.append({
            "trait": trait_clean,
            "plays": plays,
            "win_rate": round(win_rate, 2),
            "top4_rate": round(top4_rate, 2),
            "avg_rank": round(avg_rank, 2)
        })

    # print("Fetched traits:", trait_data)
    return trait_data

async def refresh_trait_map():
    global Trait_Map

    url = TRAITS_DATA_URL.format(season=CURRENT_TFT_SET)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as resp:
                if resp.status != 200:
                    print(f"Trait map request failed with status: {resp.status}")
                    return

                payload = await resp.json()
                api_traits = payload.get("traits", [])
                if not api_traits:
                    print("Trait map response had no traits")
                    return

                dynamic_map = {}
                for trait in api_traits:
                    ingame_key = trait.get("ingameKey")
                    trait_name = trait.get("name")
                    if ingame_key and trait_name:
                        dynamic_map[ingame_key] = trait_name

                if dynamic_map:
                    Trait_Map = {**DEFAULT_TRAIT_MAP, **dynamic_map}
    except Exception as e:
        print(f"Trait map refresh error: {e}")

# def build_embed(data, sort_by):
#     embed = discord.Embed(title=f"🧠 Trait Stats (Sorted by {sort_by})", color=0xFFD700)
#     for entry in data[:10]:  # Top 10
#         embed.add_field(
#             name=entry["trait"],
#             value=f"Plays: {entry['plays']}\n🏆 Win Rate: {entry['win_rate']}%\n🎯 Top 4 Rate: {entry['top4_rate']}%\n📊 Avg Rank: {entry['avg_rank']}",
#             inline=False
#         )
#     return embed

def build_embed(data, sort_by):
    embed = discord.Embed(
        title=f"🧠 Trait Stats - Last 20 Games (Sorted by {sort_by})",
        color=0xFFD700
    )

    table_lines = ["`{:<16} {:>7} {:>10} {:>13} {:>11}`".format(
        "Trait", "Plays", "Win Rate🏆", "Top 4 Rate🎯", "Avg Rank✨"
    )]

    for entry in data[:10]:
        table_lines.append("`{:<16} {:>5} {:>10} {:>13} {:>13}`".format(
            entry["trait"][:16],  # truncate long trait names
            entry["plays"],
            f"{entry['win_rate']}%",
            f"{entry['top4_rate']}%",
            f"{entry['avg_rank']:.2f}"
        ))

    embed.description = "\n".join(table_lines)
    return embed


class TraitSortView(View):
    def __init__(self, data):
        super().__init__(timeout=60)
        self.data = data

    @discord.ui.button(label="Plays", style=discord.ButtonStyle.primary)
    async def sort_plays(self, interaction: discord.Interaction, button: Button):
        sorted_data = sorted(self.data, key=lambda x: x["plays"], reverse=True)
        embed = build_embed(sorted_data, "Plays")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Win Rate", style=discord.ButtonStyle.success)
    async def sort_winrate(self, interaction: discord.Interaction, button: Button):
        sorted_data = sorted(self.data, key=lambda x: x["win_rate"], reverse=True)
        embed = build_embed(sorted_data, "Win Rate")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Top 4 Rate", style=discord.ButtonStyle.danger)
    async def sort_top4(self, interaction: discord.Interaction, button: Button):
        sorted_data = sorted(self.data, key=lambda x: x["top4_rate"], reverse=True)
        embed = build_embed(sorted_data, "Top 4 Rate")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Avg Rank", style=discord.ButtonStyle.success)
    async def sort_avgrank(self, interaction: discord.Interaction, button: Button):
        sorted_data = sorted(self.data, key=lambda x: x["avg_rank"], reverse=False)
        embed = build_embed(sorted_data, "Avg Rank")
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command()
async def traits(ctx, *, summoner_name):
    data = await fetch_traits(summoner_name)
    if not data:
        await ctx.send("❌ Couldn't fetch data. Make sure the summoner name is correct.")
        return

    sorted_data = sorted(data, key=lambda x: x["plays"], reverse=True)
    embed = build_embed(sorted_data, sort_by="Plays")
    view = TraitSortView(data)
    await ctx.send(embed=embed, view=view)

@bot.command(name='traitstest')
async def traitstest(ctx, *, summoner_name: str = "Satella018-LOOT"):
    data = await fetch_traits(summoner_name)
    if not data:
        await ctx.send(f"❌ No trait data returned for **{summoner_name}**.")
        return

    sorted_data = sorted(data, key=lambda x: x["plays"], reverse=True)
    embed = build_embed(sorted_data, sort_by="Plays")
    preview_lines = [
        f"✅ Loaded **{len(data)}** traits for **{summoner_name}**.",
        "Top 3 parsed rows:",
    ]
    for entry in sorted_data[:3]:
        preview_lines.append(
            f"- {entry['trait']}: plays={entry['plays']}, win={entry['win_rate']}%, top4={entry['top4_rate']}%, avg={entry['avg_rank']}"
        )

    await ctx.send("\n".join(preview_lines))
    await ctx.send(embed=embed)
    
@bot.command(name='delete')
async def delete(ctx, *, player_name: str):
    if player_name in player_stats:
        del player_stats[player_name]
        tracked_players.discard(player_name)
        save_leaderboard_data()
        await ctx.send(f"✅ Successfully deleted **{player_name}** from your mom!")
    else:
        await ctx.send(f"❌ Player **{player_name}** not found in da leaderboard :( womp womp)")

@bot.command(name='refreshnow')
@commands.has_permissions(manage_guild=True)
async def refreshnow(ctx):
    refreshed = await refresh_all_tracked_players()
    save_leaderboard_data()
    await ctx.send(f"Refreshed **{refreshed}** tracked players.")

@bot.command(name='tftbot')
async def tftbot(ctx, *, user_text: str = ""):
    text = user_text.strip().lower()
    if not text:
        await ctx.send("say something to me bestie ✨ try `!tftbot hi`")
        return

    triggers = [
        ("welcome back", [
            "welcome back, cutie. mortdog patched the game but not my obsession with your LP climb 💋",
            "you are back? okay then i'm locked in like k3soju on a reroll line 😘",
            "wb bestie. the lobby got hotter the second you queued up 🔥",
        ]),
        ("hi", [
            "hi gorgeous, are we playing clean tempo or boxbox-style chaos today? 👀",
            "hey you 💖 i can be your pocket coach if you promise to hold hands on 2-1",
            "hiii, i brought imaqtpie vibes and a dangerously confident level 8 roll down 😏",
        ]),
        ("how are you", [
            "i'm feeling spicy, slightly contested, and still ready to carry you to top 4 😌",
            "honestly? like a highroll soju opener: cute, dangerous, and up 30 hp 😘",
            "better now that you're here. call it a two-star mood with perfect items 💫",
        ]),
        ("when weston", [
            "right after mortdog blesses your shop and stops griefing your augments 🕯️",
            "weston going up when the lobby is weak and your board is looking disrespectfully cute 😮‍💨",
            "soon. like a boxbox pivot, he'll appear exactly when you least deserve it 😤",
        ]),
    ]

    for trigger, replies in triggers:
        if text.startswith(trigger):
            await ctx.send(random.choice(replies))
            return

    comp_row = get_random_comp_row()
    if comp_row:
        await ctx.send(format_comp_reply(comp_row))
    else:
        default_replies = [
            "laaaaaaaaaaameeeeeeeeeeeeee",
            "A weston crashout would get my bot banned so just image it 😔",
            "you're just 8th.",
        ]
        await ctx.send(random.choice(default_replies))

@bot.command(name='dailyleaderboard')
@commands.has_permissions(manage_guild=True)
async def dailyleaderboard(ctx, mode: str):
    mode = mode.lower().strip()
    guild_key = str(ctx.guild.id) if ctx.guild else "dm"

    if mode == "on":
        DAILY_LEADERBOARD_CONFIG[guild_key] = {
            "enabled": True,
            "channel_id": ctx.channel.id,
            "last_post_date": DAILY_LEADERBOARD_CONFIG.get(guild_key, {}).get("last_post_date"),
        }
        save_leaderboard_data()
        await ctx.send("✅ Daily leaderboard is now ON. I'll post top 3 at **12:00 AM PST** in this channel.")
        return

    if mode == "off":
        DAILY_LEADERBOARD_CONFIG[guild_key] = {
            "enabled": False,
            "channel_id": DAILY_LEADERBOARD_CONFIG.get(guild_key, {}).get("channel_id"),
            "last_post_date": DAILY_LEADERBOARD_CONFIG.get(guild_key, {}).get("last_post_date"),
        }
        save_leaderboard_data()
        await ctx.send("🛑 Daily leaderboard is now OFF.")
        return

    await ctx.send("Use `!dailyleaderboard on` or `!dailyleaderboard off`.")

@bot.command(name='help')
async def help(ctx):
    help_message = (
        "**Available Commands:**\n"
        "✨ **!tft <name>** - Fetches TFT stats for a player.\n"
        "💖 **!leaderboard <stat>** - Shows the leaderboard sorted by a stat (wins, winrate, top4s, top4rate, games, avgrank, rank).\n"
        "🤖 **!tftbot <text>** - Chat trigger bot (try: hi, welcome back, how are you, when weston).\n"
        "🌟 **!loser** - Call someone a loser.\n"
        "🌸 **!weston** - Cause he DID get me to emerald but also called me vanessa so HMMM.\n"
        "🌈 **!delete <name>** - Deletes a player from the leaderboard.\n"
    )
    await ctx.send(help_message)

@bot.command(name='clear')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount)
    await ctx.send(f"Cleared {amount} messages", delete_after=2)

def scrape_tft_profile(summoner_name: str):
    encoded_name = quote(summoner_name)
    profile_url = f"https://tft.dakgg.io/profile/na1/{encoded_name}"
    overviews_url = f"https://tft.dakgg.io/api/v1/summoners/na1/{encoded_name}/overviews?season={CURRENT_TFT_SET}"
    leagues_url = f"https://tft.dakgg.io/api/v1/summoners/na1/{encoded_name}/leagues"
    summoner_url = f"https://tft.dakgg.io/api/v1/summoners/na1/{encoded_name}"

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    overviews_resp = requests.get(overviews_url, headers=headers, timeout=20)
    leagues_resp = requests.get(leagues_url, headers=headers, timeout=20)
    summoner_resp = requests.get(summoner_url, headers=headers, timeout=20)
    overviews_resp.raise_for_status()
    leagues_resp.raise_for_status()
    summoner_resp.raise_for_status()

    overviews_data = overviews_resp.json()
    leagues_data = leagues_resp.json()
    summoner_data = summoner_resp.json()

    # Pull aggregate stats from season overview.
    season_overviews = overviews_data.get("summonerSeasonOverviews", [])
    if not season_overviews:
        return None
    season_overview = season_overviews[0]
    games_played = int(season_overview.get("plays", 0))
    wins = int(season_overview.get("wins", 0))
    tops = int(season_overview.get("tops", 0))
    avg_rank_value = 0.0
    if games_played > 0:
        placements = season_overview.get("placements", [])
        if isinstance(placements, list) and len(placements) == 8:
            weighted_sum = sum((idx + 1) * int(count) for idx, count in enumerate(placements))
            avg_rank_value = weighted_sum / games_played

    # Pull rank info from leagues.
    rank_text = "Unranked"
    lp_text = "0LP"
    tier_icon_url = None
    rank_color = "#A9A9A9"
    leagues = leagues_data.get("summonerLeagues", [])
    ranked_entry = next((x for x in leagues if x.get("queue") == "RANKED_TFT"), leagues[0] if leagues else None)
    if ranked_entry:
        tier_raw = (ranked_entry.get("tier") or "UNRANKED").title()
        division = ranked_entry.get("rank") or ""
        rank_text = f"{tier_raw} {division}".strip()
        league_points = ranked_entry.get("leaguePoints", 0)
        lp_text = f"{league_points}LP"
        color_map = {
            "Iron": "#6B6B6B", "Bronze": "#8C5A3C", "Silver": "#A7B1B8", "Gold": "#C9A14A",
            "Platinum": "#4BA89C", "Diamond": "#5A77E0", "Master": "#A45CE7",
            "Grandmaster": "#D94C4C", "Challenger": "#F2C94C", "Unranked": "#A9A9A9"
        }
        rank_color = color_map.get(tier_raw, "#A9A9A9")

    summoner_obj = summoner_data.get("summoner", {})
    icon_url = summoner_obj.get("profileIconUrl")

    win_rate = (wins / games_played * 100) if games_played else 0
    top4_rate = (tops / games_played * 100) if games_played else 0
    stats = {
        "Wins": f"{wins:,}",
        "Win Rate": f"{win_rate:.2f}%",
        "Top 4s": f"{tops:,}",
        "Top 4 Rate": f"{top4_rate:.2f}%",
        "Games Played": f"{games_played:,}",
        "Average Rank": f"{avg_rank_value:.2f}",
    }

    return {
        "url": profile_url,
        "stats": stats,
        "rank_text": rank_text,
        "rank_color": rank_color,
        "lp_text": lp_text,
        "icon_url": icon_url,
        "tier_icon_url": tier_icon_url,
    }

def upsert_player_stats(summoner_name: str, stats: dict, rank_text: str, lp_text: str, tier_icon_url: str = None):
    player_stats[summoner_name] = {
        "Wins": stats["Wins"],
        "Win Rate": stats["Win Rate"],
        "Top 4s": stats["Top 4s"],
        "Top 4 Rate": stats["Top 4 Rate"],
        "Games Played": stats["Games Played"],
        "Average Rank": stats["Average Rank"],
        "Rank": f"{rank_text} {lp_text}",
        "Tier Icon URL": tier_icon_url,
    }
    tracked_players.add(summoner_name)

async def refresh_all_tracked_players():
    refreshed = 0
    for summoner_name in list(tracked_players):
        try:
            profile_data = scrape_tft_profile(summoner_name)
            if not profile_data:
                continue
            upsert_player_stats(
                summoner_name,
                profile_data["stats"],
                profile_data["rank_text"],
                profile_data["lp_text"],
                profile_data["tier_icon_url"],
            )
            refreshed += 1
        except Exception as e:
            print(f"Daily refresh failed for {summoner_name}: {e}")
    return refreshed

def save_leaderboard_data():
    payload = {
        "player_stats": player_stats,
        "tracked_players": list(tracked_players),
        "daily_leaderboard_config": DAILY_LEADERBOARD_CONFIG,
    }
    with open(LEADERBOARD_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def load_leaderboard_data():
    global player_stats, tracked_players, DAILY_LEADERBOARD_CONFIG
    if not os.path.exists(LEADERBOARD_DATA_FILE):
        return
    try:
        with open(LEADERBOARD_DATA_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        player_stats = payload.get("player_stats", {})
        tracked_players = set(payload.get("tracked_players", []))
        DAILY_LEADERBOARD_CONFIG = payload.get("daily_leaderboard_config", {})
    except Exception as e:
        print(f"Failed to load leaderboard data: {e}")

def refresh_comps_cache():
    global comps_cache
    try:
        response = requests.get(COMPS_SHEET_CSV_URL, timeout=20)
        response.raise_for_status()
        text = response.text
        reader = csv.DictReader(io.StringIO(text))

        parsed_rows = []
        for row in reader:
            tier = (row.get("TIER") or "").strip()
            type_value = (row.get("TYPE") or "").strip()
            name = (row.get("NAME") or "").strip()
            if not (tier and type_value and name):
                continue

            parsed_rows.append({
                "tier": tier,
                "type": type_value,
                "name": name,
                "conditions": (row.get("CONDITIONS") or "").strip(),
                "board": (row.get("BOARD") or "").strip(),
                "notes": (row.get("NOTES") or "").strip(),
                "items": (row.get("ITEMS") or "").strip(),
                "component_pref": (row.get("Component Pref") or "").strip(),
            })

        if parsed_rows:
            comps_cache = parsed_rows
    except Exception as e:
        print(f"Failed to refresh comps cache: {e}")

def get_random_comp_row():
    if not comps_cache:
        refresh_comps_cache()
    if not comps_cache:
        return None
    return random.choice(comps_cache)

def format_comp_reply(comp):
    conditions = comp["conditions"] if comp["conditions"] else "No special condition listed"
    items = comp["items"] if comp["items"] else "No item line listed"
    component_pref = comp["component_pref"] if comp["component_pref"] else "N/A"
    notes = comp["notes"] if comp["notes"] else "No notes listed"

    return (
        f"🎯 **{comp['tier']} Tier • {comp['type']} • {comp['name']}**\n"
        f"**Conditions:** {conditions}\n"
        f"**Items:** {items}\n"
        f"**Component Pref:** {component_pref}\n"
        f"**Notes:** {notes[:220]}"
    )

def get_top_ranked_players(limit=3):
    return sorted(
        player_stats.items(),
        key=lambda x: (get_rank_value(x[1]["Rank"]), get_lp_value(x[1]["Rank"])),
        reverse=True
    )[:limit]

def build_daily_leaderboard_embed(top_players):
    sparkle = random.choice(["✨", "💖", "🌸", "🌟", "🌈"])
    embed = discord.Embed(
        title=f"{sparkle} Daily TFT Top 3 Leaderboard {sparkle}",
        description="```text\n      🥇\n   🥈     🥉\n  2nd     3rd\n      1st\n```",
        color=discord.Color.magenta()
    )

    medals = ["🥇", "🥈", "🥉"]
    labels = ["1st Place", "2nd Place", "3rd Place"]
    for i, (name, stats) in enumerate(top_players):
        badge_url = stats.get("Tier Icon URL")
        badge_text = f"({badge_url})" if badge_url else "🛡️"
        embed.add_field(
            name=f"{medals[i]} {labels[i]} — {name}",
            value=f"{badge_text}\n**{stats['Rank']}**",
            inline=False
        )

    first_badge_url = top_players[0][1].get("Tier Icon URL")
    if first_badge_url:
        embed.set_thumbnail(url=first_badge_url)

    embed.set_footer(text="Don't get mortdogged losers :P")
    return embed

@tasks.loop(hours=24)
async def daily_leaderboard_refresh():
    refreshed = await refresh_all_tracked_players()
    if refreshed > 0:
        save_leaderboard_data()
    print(f"Daily leaderboard refresh complete. Refreshed: {refreshed}")

@daily_leaderboard_refresh.before_loop
async def before_daily_refresh():
    await bot.wait_until_ready()

@tasks.loop(time=dt_time(hour=0, minute=0, tzinfo=PST_TIMEZONE))
async def daily_leaderboard_poster():
    now_pst = datetime.now(PST_TIMEZONE)
    today = now_pst.strftime("%Y-%m-%d")
    top_players = get_top_ranked_players(limit=3)
    if len(top_players) == 0:
        return

    for guild_key, config in DAILY_LEADERBOARD_CONFIG.items():
        if not config.get("enabled"):
            continue
        if config.get("last_post_date") == today:
            continue

        channel_id = config.get("channel_id")
        if not channel_id:
            continue

        channel = bot.get_channel(channel_id)
        if channel is None:
            continue

        try:
            await channel.send(embed=build_daily_leaderboard_embed(top_players))
            config["last_post_date"] = today
        except Exception as e:
            print(f"Failed posting daily leaderboard to guild {guild_key}: {e}")

    save_leaderboard_data()

@daily_leaderboard_poster.before_loop
async def before_daily_leaderboard_poster():
    await bot.wait_until_ready()

keep_alive()
bot.run(TOKEN)
