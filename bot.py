import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import random
from keep_alive import keep_alive

load_dotenv()

# Get the token from the environment
TOKEN = os.getenv('BOT_TOKEN')

# Enable the necessary intents
intents = discord.Intents.default()
intents.message_content = True

# Create the bot with the command prefix and intents
bot = commands.Bot(command_prefix='!', intents=intents)

# Dictionary to store player stats
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

    # Send the message and include the user's profile picture
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
    embed.set_thumbnail(url="https://media.tenor.com/UQBLN9Ei6SAAAAAC/goat.gif")  # Goat gif thumbnail
    embed.set_image(url="https://media.tenor.com/9RgF7SLzJMoAAAAC/goat-king.gif")  # Big image if you want

    embed.add_field(name="✨ TFT Rank", value="Challenger", inline=True)
    embed.add_field(name="🔥 Style", value="Boombot", inline=True)
    embed.add_field(name="🏆 Rank", value="#1 GOAT", inline=False)

    embed.set_footer(text="This message was brought to you by the Weston fan club.")

    await ctx.send(embed=embed)

@bot.command(name='tft')
async def tft(ctx, summoner_name):
    url = f"https://lolchess.gg/profile/na/{summoner_name.replace(' ', '%20')}"
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        labels = soup.select('.labels')

        # Define mappings (more specific keys first to avoid substring bugs)
        mappings = [
            ("Top4 비율", "Top 4 Rate"),
            ("Top4", "Top 4s"),
            ("승률", "Win Rate"),
            ("승리", "Wins"),
            ("게임 수", "Games Played"),
            ("평균 등수", "Average Rank")
        ]

        stats = {}

        # Map each label
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

        # Store the stats in the player_stats dictionary
        player_stats[summoner_name] = {
            "Wins": stats["Wins"],
            "Win Rate": stats["Win Rate"],
            "Top 4s": stats["Top 4s"],
            "Top 4 Rate": stats["Top 4 Rate"],
            "Games Played": stats["Games Played"],
            "Average Rank": stats["Average Rank"]
        }

        result = (f"**{summoner_name}'s TFT Stats:**\n"
                  f"**Wins:** {stats['Wins']}\n"
                  f"**Win Rate:** {stats['Win Rate']}\n"
                  f"**Top 4s:** {stats['Top 4s']}\n"
                  f"**Top 4 Rate:** {stats['Top 4 Rate']}\n"
                  f"**Games Played:** {stats['Games Played']}\n"
                  f"**Average Rank:** {stats['Average Rank']}")

        await ctx.send(result)

    except Exception as e:
        await ctx.send(f"An error occurred while retrieving data for {summoner_name}: {e}")

@bot.command(name='leaderboard')
async def leaderboard(ctx, stat: str):
    valid_stats = ['wins', 'winrate', 'top4s', 'top4rate', 'games', 'avgrank']  # Use lowercase versions for case-insensitive comparison

    # Convert the stat to lowercase to handle case-insensitivity
    stat = stat.lower()

    if stat not in valid_stats:
        await ctx.send(f"Invalid stat. Choose from: {', '.join(valid_stats)}")
        return

    # Map stat to the full key in player_stats dictionary
    stat_mapping = {
        'wins': 'Wins',
        'winrate': 'Win Rate',
        'top4s': 'Top 4s',
        'top4rate': 'Top 4 Rate',
        'games': 'Games Played',
        'avgrank': 'Average Rank'
    }

    # Use the mapped stat name for sorting
    stat_key = stat_mapping[stat]

    if not player_stats:
        await ctx.send("No stats available. Use `!tft <name>` to add some.")
        return

    # Convert 'Average Rank' to float after removing the '#' symbol for sorting
    if stat_key == 'Average Rank':
        sorted_stats = sorted(player_stats.items(), key=lambda x: float(x[1][stat_key].replace('#', '').strip()), reverse=False)
    else:
        # For other stats, treat them as integers for sorting
        sorted_stats = sorted(player_stats.items(), key=lambda x: int(x[1][stat_key].replace(",", "")), reverse=True)

    leaderboard_msg = f"**Leaderboard - Sorted by {stat_key}:**\n"
    for i, (name, stats) in enumerate(sorted_stats, start=1):
        leaderboard_msg += f"{i}. {name} - {stats[stat_key]}\n"

    await ctx.send(leaderboard_msg)

@bot.command(name='clear')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount)
    await ctx.send(f"Cleared {amount} messages", delete_after=2)

keep_alive()
bot.run(TOKEN)
