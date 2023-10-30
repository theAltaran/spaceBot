import discord
import requests
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import asyncio
import json

# Load environment variables from .env file
load_dotenv()

# Retrieve the Discord token from the environment variable
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID_1 = os.getenv('DISCORD_CHANNEL_ID_1')
DISCORD_CHANNEL_ID_2 = os.getenv('DISCORD_CHANNEL_ID_2')
MAX_CHANNEL_IDS = 5  # Maximum number of channel IDs to handle

# Create an instance of the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables to store upcoming launches and live streams
upcoming_launches = []
live_streams = []
last_response = None
user_message_ids = {}

# Function to load stored message IDs from the JSON file
def load_message_ids():
    try:
        with open('/app/jsonFiles/message_ids.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# Function to save message IDs to the JSON file
def save_message_ids(message_ids):
    with open('/app/jsonFiles/message_ids.json', 'w') as file:
        json.dump(message_ids, file)

# Load stored message IDs from the JSON file
message_ids = load_message_ids()

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
    global upcoming_launches  # Move the global declaration here
    response = requests.get('https://spacebotapi.altaran.duckdns.org/upcoming_launches')
    #response = requests.get('http://64.176.195.225:5050/upcoming_launches')


    if response.status_code == 200:
        data = response.json()
        upcoming_launches = data

        # Filter out launches that have already occurred
        upcoming_launches = [launch for launch in upcoming_launches if datetime.now(timezone.utc) < datetime.fromisoformat(launch['net'].replace("Z", "+00:00"))]
    else:
        # In case of an API error, you might want to handle it accordingly
        print("Failed to retrieve upcoming launches data.")
        upcoming_launches = []

async def sync_live_streams():
    url = "https://spacebotapi.altaran.duckdns.org/live_streams"
    #url = "http://64.176.195.225:5050/live_streams"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        global live_streams
        live_streams = data
    else:
        print("Failed to retrieve live streams data.")
        live_streams = []


# Define the `next` command
@bot.command(name='next')
async def next_launch(ctx):
    await sync_upcoming_launches()
    if upcoming_launches:
        # Get the next two launches
        next_launches = upcoming_launches[:2]
        message = ""

        for launch in next_launches:
            provider = launch['launch_service_provider']['name']
            name = launch['name']
            window_start = launch['window_start']

            # Convert the time to EST
            utc_time = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
            eastern_time = utc_time - timedelta(hours=0)  # Adjust for EST (UTC-4)

            # Format the time in the desired format and add timezone indication
            formatted_time = eastern_time.strftime("%m-%d-%Y %I:%M %p").lstrip('0') + " EST"

            # Calculate the time difference in hours and minutes
            current_time = datetime.now(timezone.utc)
            time_until_launch = eastern_time - current_time
            hours, remainder = divmod(time_until_launch.seconds, 3600)
            minutes = remainder // 60

            # If the time until launch is more than 24 hours, adjust the hours to include days
            if time_until_launch.days > 0:
                days = time_until_launch.days
                hours += days * 24

            # Create a string with the estimated time to launch
            estimated_time = f"{hours} hours and {minutes} minutes"

            # Extract date and time components
            date = eastern_time.strftime("%m-%d")
            time = eastern_time.strftime("%I:%M %p").lstrip('0')  # Remove leading zero from hour

            # Add launch information to the message, including estimated time to launch
            message += f"Launch Provider: {provider}\nName: {name}\nWindow Start: {date} - {time} EST\n"
            message += f"TTL: {estimated_time}\n\n"


        response = await ctx.send(message)
        await response.add_reaction('🚀')
        global last_response
        last_response = response
        await ctx.message.add_reaction('🚀')

        # Store the ID of the user's message and the bot's response in the dictionary
        user_message_ids[ctx.message.id] = response.id

        # Store the ID of the posted message in the JSON file
        message_ids = load_message_ids()
        message_ids[str(response.id)] = True  # Use True as a value, it can be anything as we just need the keys
        save_message_ids(message_ids)

        def check(reaction, user):
            return str(reaction.emoji) == '🚀' and user != bot.user

        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=600.0, check=check)
            if reaction.message.id == response.id:
                await response.delete()
                # Remove the ID from the JSON file when the message is deleted
                message_ids = load_message_ids()
                del message_ids[str(response.id)]
                save_message_ids(message_ids)
        except asyncio.TimeoutError:
            pass
    else:
        await ctx.send("No upcoming launches found.")
        
@bot.event
async def on_reaction_add(reaction, user):
    if user == bot.user:
        return  # Ignore reactions made by the bot itself

    if reaction.emoji == '🚀':
        channel = reaction.message.channel

        # Check if the reacted message ID is in the dictionary
        if reaction.message.id in user_message_ids.values():
            # Find the user's message ID corresponding to the bot's response
            user_message_id = next((key for key, value in user_message_ids.items() if value == reaction.message.id), None)

            if user_message_id is not None:
                try:
                    # Delete both the user's message and the bot's response
                    await channel.delete_messages([await channel.fetch_message(user_message_id)])
                    await channel.delete_messages([reaction.message])
                    # Remove the IDs from the dictionary
                    user_message_ids.pop(reaction.message.id, None)
                    user_message_ids.pop(user_message_id, None)
                except discord.errors.NotFound:
                    # Handle the case where the messages have already been deleted or are inaccessible
                    pass


# Define the `live` command
@bot.command(name='live')
async def live_streams_command(ctx):
    await sync_live_streams()
    if live_streams:
        messages = []

        for stream in live_streams:
            author = stream['author']
            title = stream['title']
            message = f"{author}\n{title}"

            # Send each live stream as a separate message
            response = await ctx.send(message)
            await response.add_reaction('✅')
            messages.append(response)

        def check(reaction, user):
            return str(reaction.emoji) == '✅' and user != bot.user

        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=600.0, check=check)

            # Find the message with the checkmark reaction
            reacted_message = next(message for message in messages if message.id == reaction.message.id)

            # Delete all other messages in the group and the original message with the checkmark
            for message in messages:
                if message != reacted_message:
                    await message.delete()

            # Get the corresponding stream data
            stream = live_streams[messages.index(reacted_message)]
            author = stream['author']
            title = stream['title']
            video_id = stream['videoId']
            url = f"https://www.youtube.com/watch?v={video_id}"

            # Post the link in a new message and add a rocket ship emoji reaction
            link_message = await ctx.send(url)
            await link_message.add_reaction('🚀')
            await reacted_message.delete()

        except asyncio.TimeoutError:
            # If no reactions were received within the timeout, remove all reactions from the messages
            for message in messages:
                await message.clear_reactions()

    else:
        await ctx.send("No live streams found.")

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
            message = await ctx.send(image_url)

            # Add rocket emoji and "🛰️" emoji reactions to the message
            await message.add_reaction('🚀')
            await message.add_reaction('🛰️')

            def check(reaction, user):
                return (str(reaction.emoji) == '🚀' or str(reaction.emoji) == '🛰️') and user != bot.user and reaction.message.id == message.id

            explanation_message = None  # Store the explanation message

            while True:
                try:
                    reaction, user = await bot.wait_for('reaction_add', timeout=7200.0, check=check)
                    if reaction.message.id == message.id:
                        if str(reaction.emoji) == '🚀':
                            # If rocket emoji is clicked by someone other than the bot, delete the message
                            if user != bot.user:
                                await message.delete()
                                if explanation_message:
                                    await explanation_message.delete()  # Delete the explanation message, if any
                            await ctx.message.delete()
                        elif str(reaction.emoji) == '🛰️':
                            if explanation_message:
                                await explanation_message.delete()  # Delete the explanation message, if any
                                explanation_message = None
                            else:
                                explanation_message = await ctx.send(explanation)  # Post the explanation
                except asyncio.TimeoutError:
                    if explanation_message:
                        await explanation_message.delete()  # Delete the explanation message if the timeout is reached
                    break
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
                provider = launch['launch_service_provider']['name']
                message = f"Next {provider} launch is about to happen!"
                channel = bot.get_channel(int(DISCORD_CHANNEL_ID_1))
                await channel.send(message)
        await asyncio.sleep(60)  # Check for upcoming launches every minute

# Start the bot
bot.run(DISCORD_TOKEN)
