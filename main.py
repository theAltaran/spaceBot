import os
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify
import json
import pytz
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
import asyncio

# Load environment variables from .env file
load_dotenv()

# Flask app initialization
app = Flask(__name__)

# Initialize the scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Global variables for Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables to store upcoming launches
upcoming_launches = []
last_response = None
user_message_ids = {}

# Global variable for last update time
last_launches_update_time = None

# Retrieve the Discord token from the environment variable
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID_1 = os.getenv('DISCORD_CHANNEL_ID_1')
DISCORD_CHANNEL_ID_2 = os.getenv('DISCORD_CHANNEL_ID_2')

# Function to load stored message IDs from the JSON file
def load_message_ids():
    try:
        with open('/data/dockerData/spaceBot/message_ids.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# Function to save message IDs to the JSON file
def save_message_ids(message_ids):
    with open('/data/dockerData/spaceBot/message_ids.json', 'w') as file:
        json.dump(message_ids, file)

# ======================
# FLASK API FUNCTIONS
# ======================

def get_upcoming_launches(force_refresh=False):
    """Get upcoming launches, using cache if available and fresh enough"""
    file_path = '/data/dockerData/spaceBot/upcoming_launches.json'
    
    # Check if we have cached data that's less than 1 hour old
    if not force_refresh:
        try:
            if os.path.exists(file_path):
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if datetime.now() - file_mtime < timedelta(hours=1):
                    with open(file_path, 'r') as json_file:
                        return json.load(json_file)
        except:
            pass
    
    # Fetch fresh data from the API
    response = requests.get('https://ll.thespacedevs.com/2.2.0/launch/upcoming/')
    if response.status_code == 200:
        data = response.json()
        upcoming_launches = data['results']
        upcoming_launches = [launch for launch in upcoming_launches if datetime.now(pytz.utc) < datetime.fromisoformat(launch['window_start'].replace("Z", "+00:00"))]

        # Convert datetime to EST timezone
        est = pytz.timezone('America/New_York')
        for launch in upcoming_launches:
            window_start_utc = datetime.fromisoformat(launch['window_start'].replace("Z", "+00:00")).replace(tzinfo=pytz.utc)
            launch['window_start'] = window_start_utc.astimezone(est).isoformat()

        # Save to cache
        save_upcoming_launches_to_json(upcoming_launches)
        print("Upcoming launches data fetched from the API.")
        return upcoming_launches
    return []

def save_upcoming_launches_to_json(data):
    with open('/data/dockerData/spaceBot/upcoming_launches.json', 'w') as json_file:
        json.dump(data, json_file, indent=4)
    print("Upcoming launches data has been updated.")

# ======================
# INITIALIZATION
# ======================

def initialize_data():
    global last_launches_update_time

    current_time = datetime.now(pytz.utc)
    if last_launches_update_time is not None and (current_time - last_launches_update_time <= timedelta(minutes=5)):
        with open('/data/dockerData/spaceBot/upcoming_launches.json', 'r') as json_file:
            upcoming_launches_data = json.load(json_file)
    else:
        upcoming_launches_data = get_upcoming_launches()
        save_upcoming_launches_to_json(upcoming_launches_data)
        print("Upcoming launches data has been updated.")
        last_launches_update_time = current_time

    return upcoming_launches_data

# Schedule data initialization at application launch
initialize_data()

# Schedule the get_upcoming_launches function to run every 30 minutes
scheduler.add_job(get_upcoming_launches, 'interval', minutes=30)

# ======================
# FLASK ROUTES
# ======================

@app.route('/upcoming_launches', methods=['GET'])
def upcoming_launches_endpoint():
    return jsonify(get_upcoming_launches())

@app.route('/apod', methods=['GET'])
def apod_endpoint():
    """Internal APOD endpoint - fetches directly from NASA's APOD website with caching"""
    from bs4 import BeautifulSoup
    import re
    
    apod_file = '/data/dockerData/spaceBot/apod_cache.json'
    
    # Check cache first (APOD only changes once per day, so cache for 1 hour minimum)
    try:
        if os.path.exists(apod_file):
            file_mtime = datetime.fromtimestamp(os.path.getmtime(apod_file))
            # Only use cache if it's from today OR less than 1 hour old
            if datetime.now().date() == file_mtime.date() or datetime.now() - file_mtime < timedelta(hours=1):
                with open(apod_file, 'r') as f:
                    return jsonify(json.load(f))
    except:
        pass
    
    try:
        # Fetch the APOD page directly
        response = requests.get('https://apod.nasa.gov/apod/astropix.html')
        if response.status_code != 200:
            return jsonify({'error': 'Failed to fetch APOD'}), 500
        
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Get the image URL
        img_tag = soup.find('img')
        if img_tag:
            image_url = 'https://apod.nasa.gov/apod/' + img_tag.get('src', '')
        else:
            image_url = None
        
        # Get title (from <b> tag inside center)
        title = ""
        b_tags = soup.find_all('b')
        for b in b_tags:
            text = b.get_text().strip()
            if text and 'Explanation' not in text and 'Copyright' not in text and 'Image Credit' not in text and 'Text:' not in text:
                title = text
                break
        
        # Get explanation using regex - find everything between "Explanation:" and "Tomorrow's picture"
        explanation_match = re.search(r'Explanation:.*?</b>(.*?)Tomorrow', html, re.DOTALL)
        if explanation_match:
            explanation = explanation_match.group(1)
            # Clean up HTML tags
            explanation = re.sub(r'<[^>]+>', '', explanation)
            explanation = ' '.join(explanation.split())
        else:
            explanation = ""
        
        # Get copyright
        copyright = ""
        for b in b_tags:
            text = b.get_text().strip()
            if 'Copyright' in text or 'Image Credit' in text:
                # Get next sibling text
                for sib in b.next_siblings:
                    if sib.name == 'br':
                        continue
                    if hasattr(sib, 'get_text'):
                        txt = sib.get_text().strip()
                        if txt:
                            copyright = txt
                            break
                break
        
        result = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'title': title or 'Astronomy Picture of the Day',
            'url': image_url or '',
            'explanation': explanation,
            'copyright': copyright,
            'media_type': 'image'
        }
        
        # Save to cache
        with open(apod_file, 'w') as f:
            json.dump(result, f)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ======================
# DISCORD BOT COMMANDS
# ======================

@bot.event
async def on_ready():
    print('Bot is ready and connected to Discord!')
    await sync_upcoming_launches()

async def sync_upcoming_launches():
    global upcoming_launches
    response = requests.get('https://ll.thespacedevs.com/2.2.0/launch/upcoming/')
    if response.status_code == 200:
        data = response.json()
        upcoming_launches = data['results']
        upcoming_launches = [launch for launch in upcoming_launches if datetime.now(timezone.utc) < datetime.fromisoformat(launch['net'].replace("Z", "+00:00"))]
    else:
        print("Failed to retrieve upcoming launches data.")
        upcoming_launches = []

@bot.command(name='next')
async def next_launch(ctx, count: int = None):
    await sync_upcoming_launches()
    if upcoming_launches:
        # Determine how many launches to show
        if count is None:
            count = 2
        else:
            count = min(max(1, count), 10)  # Clamp between 1-10
        
        next_launches = upcoming_launches[:count]
        message = ""

        for i, launch in enumerate(next_launches):
            provider = launch['launch_service_provider']['name']
            name = launch['name']
            window_start = launch['window_start']

            # Convert the time to EST
            utc_time = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
            eastern_time = utc_time  # Already converted

            # Calculate time until launch
            current_time = datetime.now(timezone.utc)
            time_until_launch = eastern_time - current_time
            hours, remainder = divmod(time_until_launch.seconds, 3600)
            minutes = remainder // 60

            if time_until_launch.days > 0:
                days = time_until_launch.days
                hours += days * 24

            estimated_time = f"{hours}h {minutes}m"

            # Format date and time now since both branches use them
            date = eastern_time.strftime("%m-%d")
            time = eastern_time.strftime("%I:%M %p").lstrip('0')

            if count <= 2:
                # Full format for 1-2 launches
                formatted_time = eastern_time.strftime("%m-%d-%Y %I:%M %p").lstrip('0') + " EST"
                message += f"Launch Provider: {provider}\nName: {name}\nWindow Start: {date} - {time} EST\n"
                message += f"TTL: {estimated_time}\n\n"
            else:
                # Compact format for 3+ launches
                message += f"[{i+1}] {provider} | {name} | T-{estimated_time}\n"

        response = await ctx.send(message)
        await response.add_reaction('🚀')
        global last_response
        last_response = response
        await ctx.message.add_reaction('🚀')

        # Store the ID of the user's message and the bot's response in the dictionary
        user_message_ids[ctx.message.id] = response.id

        # Store the ID of the posted message in the JSON file
        message_ids = load_message_ids()
        message_ids[str(response.id)] = True
        save_message_ids(message_ids)

        def check(reaction, user):
            return str(reaction.emoji) == '🚀' and user != bot.user

        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=600.0, check=check)
            if reaction.message.id == response.id:
                await response.delete()
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
        return

    if reaction.emoji == '🚀':
        channel = reaction.message.channel

        if reaction.message.id in user_message_ids.values():
            user_message_id = next((key for key, value in user_message_ids.items() if value == reaction.message.id), None)

            if user_message_id is not None:
                try:
                    await channel.delete_messages([await channel.fetch_message(user_message_id)])
                    await channel.delete_messages([reaction.message])
                    user_message_ids.pop(reaction.message.id, None)
                    user_message_ids.pop(user_message_id, None)
                except discord.errors.NotFound:
                    pass

@bot.command(name='apod')
async def apod_command(ctx):
    url = "http://127.0.0.1:2000/apod"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        image_url = data.get('url')
        explanation = data.get('explanation')
        title = data.get('title', 'Astronomy Picture of the Day')

        if image_url:
            await ctx.send(title)
            message = await ctx.send(image_url)

            await message.add_reaction('🚀')
            await message.add_reaction('🛰️')

            def check(reaction, user):
                return (str(reaction.emoji) == '🚀' or str(reaction.emoji) == '🛰️') and user != bot.user and reaction.message.id == message.id

            explanation_message = None

            while True:
                try:
                    reaction, user = await bot.wait_for('reaction_add', timeout=7200.0, check=check)
                    if reaction.message.id == message.id:
                        if str(reaction.emoji) == '🚀':
                            if user != bot.user:
                                await message.delete()
                                if explanation_message:
                                    await explanation_message.delete()
                            await ctx.message.delete()
                        elif str(reaction.emoji) == '🛰️':
                            if explanation_message:
                                await explanation_message.delete()
                                explanation_message = None
                            else:
                                explanation_message = await ctx.send(explanation)
                except asyncio.TimeoutError:
                    if explanation_message:
                        await explanation_message.delete()
                    break
        else:
            await ctx.send("No image URL found.")
    else:
        await ctx.send("Failed to retrieve APOD data.")

@bot.command(name='space_help')
async def bot_help_command(ctx):
    command_prefix = bot.command_prefix
    help_message = f"**Command List**\n\n"
    help_message += f"`{command_prefix}next` - Get information about the next two upcoming launches.\n"
    help_message += f"`{command_prefix}apod` - Get the Astronomy Picture of the Day.\n"
    help_message += f"`{command_prefix}space_help` - Show this help menu.\n"

    await ctx.send(help_message)

# ======================
# MAIN
# ======================

def run_flask():
    app.run(debug=False, host='0.0.0.0', port=2000)

def run_discord():
    bot.run(DISCORD_TOKEN)

if __name__ == '__main__':
    # Run Flask in a separate thread
    from threading import Thread
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Run Discord bot in the main thread
    run_discord()