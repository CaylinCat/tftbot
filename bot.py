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
import re

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

player_stats = {}

@bot.event
async def on_ready():
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
    "난동꾼": "Bruiser",
    "신성기업": "Divinicorp",
    "선봉대": "Vanguard",
    "기술광": "Techie",
    "범죄 조직": "Syndicate",
    "책략가": "Strategist",
    "거리의 악마": "Street Demon",
    "사이버보스": "Cyberboss",
    "속사 포": "Rapidfire",
    "영혼 살해자": "Soul Killer",
    "다이나모": "Dynamo",
    "황금 황소": "Golden Ox",
    "요새": "Bastion",
    "엑소테크": "Exotech",
    "동물특공대": "Anima Squad",
    "사격수": "Marksman",
    "군주": "Overlord",
    "학살자": "Slayer",
    "처형자": "Executioner",
    "네트워크의 신": "God of the Net",
    "폭발 봇": "BoomBot",
    "증.폭.": "A.M.P.",
    "바이러스": "Virus",
    "사이퍼": "Cipher"
} 

async def fetch_traits(summoner_name):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        url = f"https://lolchess.gg/profile/na/{summoner_name}/set14/statistics?staticType=traits"
        await page.goto(url, timeout=60000)
        await page.wait_for_selector('table.css-meomra')  # Wait for table to load

        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', class_='css-meomra')
    if not table:
        print("No table found")
        return []

    rows = table.find('tbody').find_all('tr')
    trait_data = []

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 6:
            continue

        raw_trait = cols[0].text.strip()
        trait_clean = re.sub(r'\d+$', '', raw_trait)

        for kor, eng in Trait_Map.items():
            if kor in trait_clean:
                trait_clean = trait_clean.replace(kor, eng)
                break

        trait_data.append({
            "trait": trait_clean,
            "plays": int(cols[1].text.strip().replace(",", "")),
            "win_rate": float(cols[2].text.strip().replace("%", "")),
            "top4_rate": float(cols[3].text.strip().replace("%", "")),
            "avg_rank": float(cols[4].text.strip().replace("#", ""))
        })

    print("Fetched traits:", trait_data)
    return trait_data

def build_embed(data, sort_by):
    embed = discord.Embed(title=f"🧠 Trait Stats (Sorted by {sort_by})", color=0xFFD700)
    for entry in data[:10]:  # Top 10
        embed.add_field(
            name=entry["trait"],
            value=f"Plays: {entry['plays']}\n🏆 Win Rate: {entry['win_rate']}%\n🎯 Top 4 Rate: {entry['top4_rate']}%\n📊 Avg Rank: {entry['avg_rank']}",
            inline=False
        )
    return embed

class TraitSortView(View):
    def __init__(self, data):
        super().__init__(timeout=60)
        self.data = data

    @discord.ui.button(label="Plays", style=discord.ButtonStyle.primary)
    async def sort_plays(self, interaction: discord.Interaction, button: Button):
        sorted_data = sorted(self.data, key=lambda x: x['plays'], reverse=True)
        embed = build_embed(sorted_data, "Plays")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Win Rate", style=discord.ButtonStyle.success)
    async def sort_winrate(self, interaction: discord.Interaction, button: Button):
        sorted_data = sorted(self.data, key=lambda x: x['win_rate'], reverse=True)
        embed = build_embed(sorted_data, "Win Rate")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Avg Rank", style=discord.ButtonStyle.danger)
    async def sort_avgrank(self, interaction: discord.Interaction, button: Button):
        sorted_data = sorted(self.data, key=lambda x: x['avg_rank'])
        embed = build_embed(sorted_data, "Avg Rank")
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command()
async def traits(ctx, *, summoner_name):
    data = await fetch_traits(summoner_name.replace(' ', '%20'))
    sorted_data = sorted(data, key=lambda x: x['plays'], reverse=True)
    embed = build_embed(sorted_data, "Plays")
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
