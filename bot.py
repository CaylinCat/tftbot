import discord
from discord.ext import commands
from discord.ui import View, Button
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import random
from keep_alive import keep_alive
from playwright.async_api import async_playwright
from tabulate import tabulate
import aiohttp
import re
from collections import defaultdict

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

player_stats = {}
playwright = None
browser = None

@bot.event
async def on_ready():
    global playwright, browser
    if playwright is None:
        playwright = await async_playwright().start()
    if browser is None:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
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
    url = f"https://lolchess.gg/profile/na/{summoner_name.replace(' ', '%20')}"
    
    try:
        response = requests.get(url)
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
            await ctx.send(f"Could not retrieve valid data for {summoner_name}. Please check the summoner name or region.")
            return

        # Scrape pfp
        profile_icon = soup.find('img', src=lambda x: x and 'profileicon' in x)
        icon_url = profile_icon['src'] if profile_icon else None

        # Scrape rank, LP, and color
        rank_div = soup.find('div', class_='rank')
        if rank_div:
            tier_img = rank_div.find('img', class_='tier')
            tier_icon_url = tier_img['src'] if tier_img else None
            tier_strong = rank_div.find('strong')
            if tier_strong:
                rank_text = tier_strong.get_text(strip=True)
                rank_color = tier_strong['style'].split(':')[1].strip()
            else:
                rank_text = "Unranked"
                rank_color = "#A9A9A9" 

            lp_tag = rank_div.find('span')
            lp_text = lp_tag.get_text(strip=True) if lp_tag else "0LP"
        else:
            tier_icon_url = None
            rank_text = "Unranked"
            rank_color = "#A9A9A9"
            lp_text = "0LP"

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

        player_stats[summoner_name] = {
            "Wins": stats["Wins"],
            "Win Rate": stats["Win Rate"],
            "Top 4s": stats["Top 4s"],
            "Top 4 Rate": stats["Top 4 Rate"],
            "Games Played": stats["Games Played"],
            "Average Rank": stats["Average Rank"],
            "Rank": f"{rank_text} {lp_text}"
        }

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

Trait_Map = {
    "TFT14_Bruiser": "Bruiser",
    "TFT14_Divinicorp": "Divinicorp",
    "TFT14_Vanguard": "Vanguard",
    "TFT14_Techie": "Techie",
    "TFT14_Mob": "Syndicate",
    "TFT14_Controller": "Strategist",
    "TFT14_StreetDemon": "Street Demon",
    "TFT14_Cyberboss": "Cyberboss",
    "TFT14_Swift": "Rapidfire",
    "TFT14_ViegoUniqueTrait": "Soul Killer",
    "TFT14_Thirsty": "Dynamo",
    "TFT14_Immortal": "Golden Ox",
    "TFT14_Armorclad": "Bastion",
    "TFT14_EdgeRunner": "Exotech",
    "TFT14_AnimaSquad": "Anima Squad",
    "TFT14_Marksman": "Marksman",
    "TFT14_Strong": "Slayer",
    "TFT14_Cutter": "Executioner",
    "TFT14_Netgod": "God of the Net",
    "TFT14_BallisTek": "BoomBot",
    "TFT14_Supercharge": "A.M.P.",
    "TFT14_Virus": "Virus",
    "TFT14_Suits": "Cipher",
    "TFT14_Overlord": "Overlord",
} 

async def fetch_traits(summoner_name: str):
    url = f"https://tft.dakgg.io/api/v1/summoners/na1/{summoner_name}/overviews?season=set14"
    
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

    print("Raw trait stats:", trait_stats)

    from collections import defaultdict
    grouped_traits = defaultdict(lambda: {"plays": 0, "wins": 0, "tops": 0, "placements": 0})

    for entry in trait_stats:
        try:
            raw_trait = entry["key"][0]
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

        trait_clean = Trait_Map.get(raw_trait, raw_trait)
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

    print("Fetched traits:", trait_data)
    return trait_data

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

    # @discord.ui.button(label="Top 4 Rate", style=discord.ButtonStyle.secondary)
    # async def sort_top4(self, interaction: discord.Interaction, button: Button):
    #     sorted_data = sorted(self.data, key=lambda x: x["top4_rate"], reverse=True)
    #     embed = build_embed(sorted_data, "Top 4 Rate")
    #     await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Avg Rank", style=discord.ButtonStyle.danger)
    async def sort_avgrank(self, interaction: discord.Interaction, button: Button):
        sorted_data = sorted(self.data, key=lambda x: x["avg_rank"], reverse=False)
        embed = build_embed(sorted_data, "Avg Rank")
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command()
async def traits(ctx, *, summoner_name):
    data = await fetch_traits(summoner_name.replace(' ', '%20'))
    if not data:
        await ctx.send("❌ Couldn't fetch data. Make sure the summoner name is correct.")
        return

    sorted_data = sorted(data, key=lambda x: x["plays"], reverse=True)
    embed = build_embed(sorted_data, sort_by="Plays")
    view = TraitSortView(data)
    await ctx.send(embed=embed, view=view)
    
@bot.command(name='delete')
async def delete(ctx, *, player_name: str):
    if player_name in player_stats:
        del player_stats[player_name]
        await ctx.send(f"✅ Successfully deleted **{player_name}** from your mom!")
    else:
        await ctx.send(f"❌ Player **{player_name}** not found in da leaderboard :( womp womp)")

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

keep_alive()
bot.run(TOKEN)
