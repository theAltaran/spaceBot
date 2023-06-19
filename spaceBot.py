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
MAX_CHANNEL_IDS = 5  # Maximum number of channel IDs to handle

# Create an instance of the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Event triggered when the bot is ready and connected to Discord
@bot.event
async def on_ready():
    print('Bot is ready and connected to Discord!')
    bot.loop.create_task(schedule_next_launch())

# Define the `next` command
@bot.command(name='next')
async def next_launch(ctx):
    # Make a request to the API
    response = requests.get('https://ll.thespacedevs.com/2.2.0/launch/upcoming/')

    if response.status_code == 200:
        data = response.json()
        upcoming_launches = data['results']

        # Filter out launches with past dates
        upcoming_launches = [launch for launch in upcoming_launches if datetime.now(timezone.utc) < datetime.fromisoformat(launch['window_start'].replace("Z", "+00:00"))]

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

        await ctx.send(message)

    else:
        await ctx.send("Failed to fetch upcoming launches")

async def schedule_next_launch():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now(timezone.utc)
        next_launch_time = get_next_launch_time()

        if next_launch_time is not None and next_launch_time - now <= timedelta(minutes=5):
            await announce_next_launch()

        await asyncio.sleep(60)  # Check every minute

def get_next_launch_time():
    response = requests.get('https://ll.thespacedevs.com/2.2.0/launch/upcoming/')

    if response.status_code == 200:
        data = response.json()
        upcoming_launches = data['results']

        # Filter out launches with past dates
        upcoming_launches = [launch for launch in upcoming_launches if datetime.now(timezone.utc) < datetime.fromisoformat(launch['window_start'].replace("Z", "+00:00"))]

        if upcoming_launches:
            next_launch = upcoming_launches[0]
            window_start = next_launch['window_start']
            next_launch_time = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
            return next_launch_time

    return None

async def announce_next_launch():
    for i in range(1, MAX_CHANNEL_IDS + 1):
        channel_id = os.getenv(f'CHANNEL_ID_{i}')
        if channel_id:
            channel = bot.get_channel(int(channel_id))
            if channel:
                await channel.send("Next launch will start in 5 minutes!\nLaunch Provider: SpaceX\nLocation: Cape Canaveral, Florida")

# Run the bot
bot.run(DISCORD_TOKEN)
