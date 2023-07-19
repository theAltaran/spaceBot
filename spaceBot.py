import discord
import requests
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import asyncio

# Load environment variables from .env file
load_dotenv()

# Retrieve the Discord token from the environment variable
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY')
DISCORD_CHANNEL_ID_1 = os.getenv('DISCORD_CHANNEL_ID_1')
DISCORD_CHANNEL_ID_2 = os.getenv('DISCORD_CHANNEL_ID_2')
YOUTUBE_CHANNEL_ID = os.getenv('YOUTUBE_CHANNEL_ID')
MAX_CHANNEL_IDS = 5  # Maximum number of channel IDs to handle

# Create an instance of the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables to store upcoming launches and live streams
upcoming_launches = []
live_streams = []
last_response = None

# Event triggered when the bot is ready and connected to Discord
@bot.event
async def on_ready():
    print('Bot is ready and connected to Discord!')
    await sync_data()
    bot.loop.create_task(schedule_next_launch())

async def sync_data():
    await sync_upcoming_launches()
    await sync_live_streams()

async def sync_upcoming_launches():
    response = requests.get('https://ll.thespacedevs.com/2.2.0/launch/upcoming/')
    if response.status_code == 200:
        data = response.json()
        global upcoming_launches
        upcoming_launches = data['results']
        upcoming_launches = [launch for launch in upcoming_launches if datetime.now(timezone.utc) < datetime.fromisoformat(launch['window_start'].replace("Z", "+00:00"))]

async def sync_live_streams():
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&eventType=live&type=video&key={API_KEY}&channelId={YOUTUBE_CHANNEL_ID}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        global live_streams
        live_streams = data.get('items', [])

# Define the `next` command
@bot.command(name='next')
async def next_launch(ctx):
    await sync_upcoming_launches()
    if upcoming_launches:
        # Get the next two launches
        next_launches = upcoming_launches[:2]
        message = "Next 2 launches:\n"

        for launch in next_launches:
            provider = launch['launch_service_provider']['name']
            name = launch['name']
            window_start = launch['window_start']

            # Convert the time to EST
            utc_time = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
            eastern_time = utc_time - timedelta(hours=4)  # Adjust for EST (UTC-4)

            # Format the time in 12-hour format and add timezone indication
            formatted_time = eastern_time.strftime("%m-%d-%Y %I:%M:%S %p") + " EST"

            # Add launch information to the message
            message += f"Launch Provider: {provider}\nName: {name}\nWindow Start: {formatted_time}\n\n"

        response = await ctx.send(message)
        await response.add_reaction('🚀')  # Add rocket emoji reaction to the response message
        global last_response
        last_response = response
        await ctx.message.add_reaction('🚀')  # Add rocket emoji reaction to the command message

        def check(reaction, user):
            return str(reaction.emoji) == '🚀' and user != bot.user

        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=600.0, check=check)
            if reaction.message.id == response.id:
                await response.delete()  # Delete the response message if reacted with the rocket emoji
            if reaction.message.id == ctx.message.id:
                await ctx.message.delete()  # Delete the command message if reacted with the rocket emoji
        except asyncio.TimeoutError:
            pass

    else:
        await ctx.send("No upcoming launches found.")

# Define the `cancel` command
@bot.command(name='cancel')
async def cancel_next_launch(ctx):
    global last_response
    if last_response:
        await last_response.delete()
        last_response = None
        await ctx.send("Last launch announcement cancelled.")
    else:
        await ctx.send("No active launch announcement to cancel.")

# Define the `live` command
@bot.command(name='live')
async def live_streams_command(ctx):
    await sync_live_streams()
    if live_streams:
        message = "Live streams:\n"

        for stream in live_streams:
            title = stream['snippet']['title']
            video_id = stream['id']['videoId']
            url = f"https://www.youtube.com/watch?v={video_id}"
            message += f"{title}\nURL: {url}\n\n"

        await ctx.send(message)
    else:
        await ctx.send("No live streams found.")

# Define the `apod` command
@bot.command(name='apod')
async def apod_command(ctx):
    url = "https://apod.altaran.duckdns.org/v1/apod/"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        image_url = data.get('url')
        explanation = data.get('explanation')

        if image_url:
            await ctx.send("Astronomy Picture of the Day")
            await ctx.send(image_url)

            explanation_message = await ctx.send(explanation)
            await explanation_message.add_reaction('🚀')  # Add rocket emoji reaction to the explanation message

            def check(reaction, user):
                return str(reaction.emoji) == '🚀' and user != bot.user

            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=600.0, check=check)
                if explanation_message.id == reaction.message.id and str(reaction.emoji) == '🚀':
                    await explanation_message.delete()  # Delete the explanation message if reacted with a rocket emoji
                    await ctx.message.delete()  # Delete the command message
            except asyncio.TimeoutError:
                pass
        else:
            await ctx.send("No image URL found.")
    else:
        await ctx.send("Failed to retrieve APOD data.")

# Define the `bot_help` command
@bot.command(name='space_help')
async def bot_help_command(ctx):
    command_prefix = bot.command_prefix
    help_message = f"**Command List**\n\n"
    help_message += f"`{command_prefix}next` - Get information about the next two upcoming launches.\n"
    # help_message += f"`{command_prefix}cancel` - Cancel the last launch announcement.\n"
    help_message += f"`{command_prefix}live` - Get information about current live streams.\n"
    help_message += f"`{command_prefix}apod` - Get the Astronomy Picture of the Day.\n"
    help_message += f"`{command_prefix}space_help` - Show this help menu.\n"

    await ctx.send(help_message)



async def schedule_next_launch():
    while True:
        await sync_upcoming_launches()
        if upcoming_launches:
            launch = upcoming_launches[0]
            launch_time = datetime.fromisoformat(launch['window_start'].replace("Z", "+00:00"))
            current_time = datetime.now(timezone.utc)
            time_until_launch = (launch_time - current_time).total_seconds()

            if time_until_launch > 0:
                await asyncio.sleep(time_until_launch)
                channel = bot.get_channel(int(DISCORD_CHANNEL_ID_1))
                await channel.send("Next launch is about to happen!")
        await asyncio.sleep(60)  # Check for upcoming launches every minute

# Start the bot
bot.run(DISCORD_TOKEN)
