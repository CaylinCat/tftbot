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

@bot.event
async def on_ready():
    load_leaderboard_data()
    if not daily_leaderboard_refresh.is_running():
        daily_leaderboard_refresh.start()
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

        upsert_player_stats(summoner_name, stats, rank_text, lp_text)
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
        sorted_stats = sorted(player_stats.items(), key=lambda x: (get_rank_value(x[1][stat_key]), get_lp_value(x[1][stat_key])), reverse=False)
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

@bot.command(name='help')
async def help(ctx):
    help_message = (
        "**Available Commands:**\n"
        "✨ **!tft <name>** - Fetches TFT stats for a player.\n"
        "💖 **!leaderboard <stat>** - Shows the leaderboard sorted by a stat (wins, winrate, top4s, top4rate, games, avgrank, rank).\n"
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
    url = f"https://lolchess.gg/profile/na/{summoner_name.replace(' ', '%20')}"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    labels = soup.select('.labels')
    mappings = [
        ("Top4 비율", "Top 4 Rate"),
        ("Top4", "Top 4s"),
        ("승률", "Win Rate"),
        ("승리", "Wins"),
        ("게임 수", "Games Played"),
        ("평균 등수", "Average Rank")
    ]

    stats = {}
    for label in labels:
        text = label.get_text(strip=True)
        for key, name in mappings:
            if text.startswith(key):
                stats[name] = text.replace(key, '').strip()
                break

    required_keys = ["Wins", "Win Rate", "Top 4s", "Top 4 Rate", "Games Played", "Average Rank"]
    if not all(key in stats for key in required_keys):
        return None

    profile_icon = soup.find('img', src=lambda x: x and 'profileicon' in x)
    icon_url = profile_icon['src'] if profile_icon else None

    rank_div = soup.find('div', class_='rank')
    tier_icon_url = None
    rank_text = "Unranked"
    rank_color = "#A9A9A9"
    lp_text = "0LP"
    if rank_div:
        tier_img = rank_div.find('img', class_='tier')
        tier_icon_url = tier_img['src'] if tier_img else None
        tier_strong = rank_div.find('strong')
        if tier_strong:
            rank_text = tier_strong.get_text(strip=True)
            style = tier_strong.get('style', '')
            if ':' in style:
                rank_color = style.split(':', 1)[1].strip()
        lp_tag = rank_div.find('span')
        lp_text = lp_tag.get_text(strip=True) if lp_tag else "0LP"

    return {
        "url": url,
        "stats": stats,
        "rank_text": rank_text,
        "rank_color": rank_color,
        "lp_text": lp_text,
        "icon_url": icon_url,
        "tier_icon_url": tier_icon_url,
    }

def upsert_player_stats(summoner_name: str, stats: dict, rank_text: str, lp_text: str):
    player_stats[summoner_name] = {
        "Wins": stats["Wins"],
        "Win Rate": stats["Win Rate"],
        "Top 4s": stats["Top 4s"],
        "Top 4 Rate": stats["Top 4 Rate"],
        "Games Played": stats["Games Played"],
        "Average Rank": stats["Average Rank"],
        "Rank": f"{rank_text} {lp_text}"
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
            )
            refreshed += 1
        except Exception as e:
            print(f"Daily refresh failed for {summoner_name}: {e}")
    return refreshed

def save_leaderboard_data():
    payload = {
        "player_stats": player_stats,
        "tracked_players": list(tracked_players),
    }
    with open(LEADERBOARD_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def load_leaderboard_data():
    global player_stats, tracked_players
    if not os.path.exists(LEADERBOARD_DATA_FILE):
        return
    try:
        with open(LEADERBOARD_DATA_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        player_stats = payload.get("player_stats", {})
        tracked_players = set(payload.get("tracked_players", []))
    except Exception as e:
        print(f"Failed to load leaderboard data: {e}")

@tasks.loop(hours=24)
async def daily_leaderboard_refresh():
    refreshed = await refresh_all_tracked_players()
    if refreshed > 0:
        save_leaderboard_data()
    print(f"Daily leaderboard refresh complete. Refreshed: {refreshed}")

@daily_leaderboard_refresh.before_loop
async def before_daily_refresh():
    await bot.wait_until_ready()

keep_alive()
bot.run(TOKEN)
