import os
import json
import random
import asyncio
import uuid
import hashlib
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Bot
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress
import requests
from bs4 import BeautifulSoup
import threading
import pytz
import qrcode
from io import BytesIO
import aiohttp
from fake_useragent import UserAgent

# Configuration
TOKEN = "8129521411:AAHPu7hRsfWGjGg-BdtPT4YE42V8HQAxUZU"
ADMIN_ID = 7660038402
KEYS_FILE = "keys.json"
KEYS_HASH_FILE = "keys.hash"
DATABASE_FILES =  ["logs.txt", "logs_v1.txt", "logs_v2.txt", "logs_v3.txt", "logs_v4.txt", "logs_v5.txt", "logs_v6.txt", "logs_v7.txt", "moon.txt", "moon_v1.txt", "moon_v2.txt"]
USED_ACCOUNTS_FILE = "used_accounts.txt"
LINES_TO_SEND = 150
MAX_DAILY_GENERATIONS = 150
BACKUP_INTERVAL = 3600  # 1 hour in seconds
VERSION = "1.0.0"

# Enhanced domains with categories
DOMAINS = {
    "gaming": ["100082", "authgop", "gaslite", "mtacc", "garena", "roblox", "epicgames", "steam", "origin", "pubg"],
    "social": ["facebook", "telegram", "discord", "twitter", "instagram", "snapchat"],
    "entertainment": ["vivamax", "pornhub", "netflix", "spotify", "disneyplus", "hbo", "amazonprime"],
    "utilities": ["gameclub", "nordvpn", "expressvpn", "surfshark", "adobe", "microsoft"]
}

console = Console()
ua = UserAgent()

# Load or initialize keys data
def load_keys():
    if not os.path.exists(KEYS_FILE):
        initial_data = {
            "keys": {},
            "user_keys": {},
            "logs": {},
            "user_limits": {},
            "banned_users": [],
            "statistics": {
                "total_generations": 0,
                "active_users": 0,
                "keys_generated": 0
            },
            "settings": {
                "maintenance": False,
                "registration_open": True
            }
        }
        with open(KEYS_FILE, "w") as f:
            json.dump(initial_data, f)
        return initial_data
    
    try:
        with open(KEYS_FILE, "r") as f:
            keys = json.load(f)
        
        # Verify file integrity
        if os.path.exists(KEYS_HASH_FILE):
            with open(KEYS_HASH_FILE, "r") as hf:
                expected_hash = hf.read().strip()
                current_hash = hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()
                if expected_hash != current_hash:
                    console.print("[red]⚠️ Warning: keys.json integrity compromised! Restoring backup...[/red]")
                    restore_backup()
                    return load_keys()
        
        # Update structure if needed
        if "statistics" not in keys:
            keys["statistics"] = {
                "total_generations": 0,
                "active_users": 0,
                "keys_generated": 0
            }
        if "settings" not in keys:
            keys["settings"] = {
                "maintenance": False,
                "registration_open": True
            }
        
        return keys
    except Exception as e:
        console.print(f"[red]❌ Error loading keys file: {e}[/red]")
        console.print("[yellow]Attempting to restore from backup...[/yellow]")
        restore_backup()
        return load_keys()

def restore_backup():
    backup_files = [f for f in os.listdir() if f.startswith("keys_backup")]
    if backup_files:
        latest_backup = max(backup_files, key=lambda x: os.path.getmtime(x))
        try:
            with open(latest_backup, "r") as f:
                backup_data = json.load(f)
            with open(KEYS_FILE, "w") as f:
                json.dump(backup_data, f)
            console.print(f"[green]✅ Restored from {latest_backup}[/green]")
        except Exception as e:
            console.print(f"[red]❌ Failed to restore backup: {e}[/red]")
            initialize_new_keys_file()
    else:
        console.print("[red]❌ No backup files found[/red]")
        initialize_new_keys_file()

def initialize_new_keys_file():
    console.print("[yellow]Initializing new keys file...[/yellow]")
    initial_data = {
        "keys": {},
        "user_keys": {},
        "logs": {},
        "user_limits": {},
        "banned_users": [],
        "statistics": {
            "total_generations": 0,
            "active_users": 0,
            "keys_generated": 0
        },
        "settings": {
            "maintenance": False,
            "registration_open": True
        }
    }
    with open(KEYS_FILE, "w") as f:
        json.dump(initial_data, f)

def save_keys(keys):
    # Create backup before saving
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"keys_backup_{timestamp}.json"
    with open(backup_filename, "w") as f:
        json.dump(keys, f)
    
    # Remove old backups (keep last 5)
    backup_files = sorted([f for f in os.listdir() if f.startswith("keys_backup")], 
                         key=lambda x: os.path.getmtime(x), reverse=True)
    for old_backup in backup_files[5:]:
        try:
            os.remove(old_backup)
        except:
            pass
    
    # Save current data
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=4)
    generate_key_hash(keys)

def generate_key_hash(keys):
    file_hash = hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()
    with open(KEYS_HASH_FILE, "w") as hash_file:
        hash_file.write(file_hash)

def generate_device_id():
    return str(uuid.uuid4())

def generate_random_key(length=8):
    prefix = random.choice(["AKIRO"])
    return f"{prefix}-{''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=length))}"

def get_expiry_time(duration):
    now = datetime.now()
    duration_map = {
        "1h": 3600, "6h": 21600, "12h": 43200, "1d": 86400, 
        "3d": 259200, "7d": 604800, "14d": 1209600, "30d": 2592000
    }
    return None if duration == "lifetime" else (now + timedelta(seconds=duration_map[duration])).timestamp()

def parse_duration(duration_str):
    parts = duration_str.split()
    total_seconds = 0
    for part in parts:
        if 'd' in part:
            total_seconds += int(part.replace('d', '')) * 86400
        elif 'h' in part:
            total_seconds += int(part.replace('h', '')) * 3600
        elif 'm' in part:
            total_seconds += int(part.replace('m', '')) * 60
    return total_seconds

def format_duration(seconds):
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"

async def check_proxies():
    proxy_list = []
    try:
        # Scrape free proxies (for educational purposes only)
        url = "https://www.sslproxies.org/"
        headers = {'User-Agent': ua.random}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        table = soup.find('table', {'class': 'table table-striped table-bordered'})
        for row in table.tbody.find_all('tr'):
            columns = row.find_all('td')
            ip = columns[0].text
            port = columns[1].text
            proxy_list.append(f"{ip}:{port}")
        
        console.print(f"[green]✅ Found {len(proxy_list)} proxies[/green]")
    except Exception as e:
        console.print(f"[red]❌ Proxy scraping failed: {e}[/red]")
    
    return proxy_list

async def backup_task():
    while True:
        await asyncio.sleep(BACKUP_INTERVAL)
        save_keys(keys_data)
        console.print("[yellow]🔒 Automatic backup completed[/yellow]")

async def check_expirations():
    while True:
        await asyncio.sleep(3600)  # Check every hour
        now = time.time()
        expired_users = []
        
        for user_id, expiry in keys_data["user_keys"].items():
            if expiry and expiry < now:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del keys_data["user_keys"][user_id]
            
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Your subscription has expired. Contact admin to renew."
                )
            except:
                pass
        
        if expired_users:
            save_keys(keys_data)
            console.print(f"[yellow]🕒 Cleared {len(expired_users)} expired accounts[/yellow]")

async def fetch_fresh_accounts(domain):
    try:
        # This is a placeholder for actual account fetching logic
        console.print(f"[yellow]🔍 Searching for fresh {domain} accounts...[/yellow]")
        await asyncio.sleep(2)  # Simulate network delay
        
        # Generate some dummy accounts (replace with real implementation)
        accounts = []
        for i in range(random.randint(5, 15)):
            username = f"{domain}_user{random.randint(1000, 9999)}"
            password = f"Pass{random.randint(10000, 99999)}!"
            accounts.append(f"{username}:{password}")
        
        console.print(f"[green]✅ Found {len(accounts)} fresh {domain} accounts[/green]")
        return accounts
    except Exception as e:
        console.print(f"[red]❌ Error fetching accounts: {e}[/red]")
        return []

async def start(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    
    if keys_data["settings"]["maintenance"] and chat_id != str(ADMIN_ID):
        return await update.message.reply_text("🔧 Inaayos pa ng pogi mag antay ka kupal!")
    
    if chat_id in keys_data.get("banned_users", []):
        return await update.message.reply_text("🚨 Your account has been banned!")
    
    keyboard = [
        [InlineKeyboardButton("🔐 Login/Register", callback_data="login_menu")],
        [InlineKeyboardButton("🛠 Generate Accounts", callback_data="generate")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats_menu"),
         InlineKeyboardButton("ℹ️ Help", callback_data="help_menu")]
    ]
    
    if update.message.chat_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    
    welcome_text = f"""
✨ *Welcome to KIRO Premium Generator v{VERSION}!* ✨

🔹 *Features:*
✅ Fresh Accounts (Updated Hourly)
⚡ Fast Generation
🔐 Secure Access
📂 Multiple Domains Available

🔹 Use the buttons below to navigate
"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def generate_menu(update: Update, context: CallbackContext):
    # Support both command and button callbacks
    if update.message:
        message = update.message
    elif update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        return

    chat_id = str(update.effective_chat.id)

    if str(chat_id) in keys_data.get("banned_users", []):
        return await message.reply_text("🚨 Your account has been banned!")

    # Check if user needs to login
    if chat_id not in keys_data["user_keys"]:
        keyboard = [
            [InlineKeyboardButton("🔐 Login/Register", callback_data="login_menu")],
            [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
        ]
        return await message.reply_text(
            "🔒 Please login or register first to generate accounts",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Check if user has reached daily limit
    user_logs = keys_data["logs"].get(chat_id, {})
    today = datetime.now().strftime("%Y-%m-%d")
    if user_logs.get("last_generation_date") != today:
        user_logs["generations_today"] = 0
        user_logs["last_generation_date"] = today
    
    if user_logs.get("generations_today", 0) >= MAX_DAILY_GENERATIONS:
        remaining_time = 86400 - (time.time() % 86400)
        remaining_str = format_duration(remaining_time)
        return await update.message.reply_text(
            f"⚠️ You've reached your daily generation limit ({MAX_DAILY_GENERATIONS}).\n"
            f"Next reset in: {remaining_str}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
            ])
        )
    
        # Show domain categories
    keyboard = []
    for category, domains in DOMAINS.items():
        keyboard.append([InlineKeyboardButton(
            f"🎮 {category.capitalize()} ({len(domains)})", 
            callback_data=f"category_{category}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔍 Search All Domains", callback_data="search_all_domains")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    
    await update.message.reply_text(
        "🛠 *Pili kana kupal:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def search_all_domains(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    
    if str(chat_id) in keys_data.get("banned_users", []):
        return await query.message.reply_text("🚨Banned! kana kupal ka kasi!")
    
    # Update user logs
    user_logs = keys_data["logs"].get(chat_id, {})
    today = datetime.now().strftime("%Y-%m-%d")
    if user_logs.get("last_generation_date") != today:
        user_logs["generations_today"] = 0
        user_logs["last_generation_date"] = today
    
    if user_logs.get("generations_today", 0) >= MAX_DAILY_GENERATIONS:
        remaining_time = 86400 - (time.time() % 86400)
        remaining_str = format_duration(remaining_time)
        return await query.message.reply_text(
            f"⚠️ Bawal na mag generate ubos na daily mo uhaw ka kasi eh! ({MAX_DAILY_GENERATIONS}).\n"
            f"Next reset in: {remaining_str}"
        )
    
    # Start generation process
    processing_msg = await query.message.reply_text(
        "⚡ Eto na mag antay ka kumag! ...\n"
        "🔄 Mag antay ka muna..."
    )
    
    try:
        # Check for used accounts
        with open(USED_ACCOUNTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            used_accounts = set(f.read().splitlines())
    except:
        used_accounts = set()
    
    matched_lines = []
    
    # Check database files
    for db_file in DATABASE_FILES:
        if len(matched_lines) >= LINES_TO_SEND:
            break
        try:
            with open(db_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    stripped_line = line.strip()
                    if stripped_line and stripped_line not in used_accounts:
                        matched_lines.append(stripped_line)
                        if len(matched_lines) >= LINES_TO_SEND:
                            break
        except Exception as e:
            console.print(f"[red]❌ Error reading {db_file}: {e}[/red]")
            continue
    
    if not matched_lines:
        await processing_msg.edit_text(
            "❌ No accounts available!\n"
            "Puta bat mo kasi inubos!.",
            parse_mode="Markdown"
        )
        return
    
    # Update used accounts
    with open(USED_ACCOUNTS_FILE, "a", encoding="utf-8", errors="ignore") as f:
        f.writelines("\n".join(matched_lines) + "\n")
    
    # Prepare the file
    filename = f"𝙿𝚁𝙴𝙼𝙸𝚄𝙼_ALL_DOMAINS_𝙰𝙲𝙲𝙾𝚄𝙽𝚃𝚂 𝙽𝙸 𝙺𝙸𝚁𝙾{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8", errors="ignore") as f:
        f.write(f"🔥 Generated By KIROS Generator\n")
        f.write(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"🔍 Domains: All\n")
        f.write(f"👤 User ID: {chat_id}\n\n")
        f.writelines("\n".join(matched_lines))
    
    # Update statistics
    keys_data["statistics"]["total_generations"] += 1
    user_logs["generations_today"] = user_logs.get("generations_today", 0) + 1
    keys_data["logs"][chat_id] = user_logs
    save_keys(keys_data)
    
    await asyncio.sleep(1)  # Simulate processing delay
    
    try:
        with open(filename, "rb") as f:
            await processing_msg.delete()
            await query.message.reply_document(
                document=InputFile(f, filename=filename),
                caption=f"✅ **Accounts Generated!**\n"
                       f"📊 Today's generations: {user_logs['generations_today']}/{MAX_DAILY_GENERATIONS}",
                parse_mode="Markdown"
            )
    except Exception as e:
        console.print(f"[red]❌ Error sending file: {e}[/red]")
        await query.message.reply_text(
            f"❌ Error generating accounts: {str(e)}\n"
            "Try mo mamaya bro."
        )
    finally:
        if os.path.exists(filename):
            os.remove(filename)

async def show_category_domains(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("category_", "")
    
    domains = DOMAINS.get(category, [])
    if not domains:
        return await query.message.reply_text("❌ Walang ganyan kupal kaba!")
    
    keyboard = [
        [InlineKeyboardButton(domain, callback_data=f"generate_{domain}") for domain in domains[i:i+2]] 
        for i in range(0, len(domains), 2)
    ]
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="generate_menu")])
    
    await query.message.edit_text(
        f"🎮 *{category.capitalize()} Domains*\nPili kana nga baka kaltukan kita:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def generate_filtered_accounts(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    selected_domain = query.data.replace("generate_", "")
    
    if str(chat_id) in keys_data.get("banned_users", []):
        return await query.message.reply_text("🚨 Banned! kana kupal ka kasi!")
    
    # Update user logs
    user_logs = keys_data["logs"].get(chat_id, {})
    today = datetime.now().strftime("%Y-%m-%d")
    if user_logs.get("last_generation_date") != today:
        user_logs["generations_today"] = 0
        user_logs["last_generation_date"] = today
    
    if user_logs.get("generations_today", 0) >= MAX_DAILY_GENERATIONS:
        remaining_time = 86400 - (time.time() % 86400)
        remaining_str = format_duration(remaining_time)
        return await query.message.reply_text(
            f"⚠️ Bawal na mag generate ubos na daily mo uhaw ka kasi eh! ({MAX_DAILY_GENERATIONS}).\n"
            f"Next reset in: {remaining_str}"
        )
    
    # Start generation process
    processing_msg = await query.message.reply_text(
        f"⚡ Malapit na yung {selected_domain.upper()} accounts mo...\n"
        "🔄 Mag antay ka muna jan..."
    )
    
    try:
        # Check for used accounts
        with open(USED_ACCOUNTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            used_accounts = set(f.read().splitlines())
    except:
        used_accounts = set()
    
    # Try to find fresh accounts first
    fresh_accounts = await fetch_fresh_accounts(selected_domain)
    matched_lines = [acc for acc in fresh_accounts if acc not in used_accounts]
    
    # If not enough fresh accounts, check database files
    if len(matched_lines) < LINES_TO_SEND:
        for db_file in DATABASE_FILES:
            if len(matched_lines) >= LINES_TO_SEND:
                break
            try:
                with open(db_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        stripped_line = line.strip()
                        if selected_domain.lower() in stripped_line.lower() and stripped_line not in used_accounts:
                            matched_lines.append(stripped_line)
                            if len(matched_lines) >= LINES_TO_SEND:
                                break
            except Exception as e:
                console.print(f"[red]❌ Error reading {db_file}: {e}[/red]")
                continue
    
    if not matched_lines:
        await processing_msg.edit_text(
            f"❌ Bat mo inubos kupal ka! {selected_domain.upper()}!\n"
            "Try another domain or check back later.",
            parse_mode="Markdown"
        )
        return
    
    # Update used accounts
    with open(USED_ACCOUNTS_FILE, "a", encoding="utf-8", errors="ignore") as f:
        f.writelines("\n".join(matched_lines) + "\n")
    
    # Prepare the file
    filename = f"𝙿𝚁𝙴𝙼𝚄𝙸𝙼_{selected_domain.upper()}_𝙰𝙲𝙲𝙾𝚄𝙽𝚃𝚂 𝙽𝙸 𝙰𝙺𝙸𝚁𝙾_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8", errors="ignore") as f:
        f.write(f"🔥 Generated By KIROS Generator\n")
        f.write(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"🔍 Domain: {selected_domain.upper()}\n")
        f.write(f"👤 User ID: {chat_id}\n\n")
        f.writelines("\n".join(matched_lines))
    
    # Update statistics
    keys_data["statistics"]["total_generations"] += 1
    user_logs["generations_today"] = user_logs.get("generations_today", 0) + 1
    keys_data["logs"][chat_id] = user_logs
    save_keys(keys_data)
    
    await asyncio.sleep(1)  # Simulate processing delay
    
    try:
        with open(filename, "rb") as f:
            await processing_msg.delete()
            await query.message.reply_document(
                document=InputFile(f, filename=filename),
                caption=f"✅ **{selected_domain.upper()} Accounts Generated!**\n"
                       f"📊 Today's generations: {user_logs['generations_today']}/{MAX_DAILY_GENERATIONS}",
                parse_mode="Markdown"
            )
    except Exception as e:
        console.print(f"[red]❌ Error sending file: {e}[/red]")
        await query.message.reply_text(
            f"❌ Error generating accounts: {str(e)}\n"
            "Please try again later."
        )
    finally:
        if os.path.exists(filename):
            os.remove(filename)

async def generate_key(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) < 1 or context.args[0] not in ["1h", "6h", "12h", "1d", "3d", "7d", "14d", "30d", "lifetime"]:
        return await update.message.reply_text(
            "⚠ Usage: `/genkey <duration>`\n"
            "Available durations: 1h, 6h, 12h, 1d, 3d, 7d, 14d, 30d, lifetime\n"
            "Example: `/genkey 7d`",
            parse_mode="Markdown"
        )
    
    duration = context.args[0]
    quantity = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
    quantity = min(quantity, 50)  # Limit to 50 keys at once
    
    generated_keys = []
    for _ in range(quantity):
        new_key = generate_random_key()
        expiry = get_expiry_time(duration)
        
        keys_data["keys"][new_key] = expiry
        generated_keys.append(new_key)
    
    keys_data["statistics"]["keys_generated"] += quantity
    save_keys(keys_data)
    
    if quantity == 1:
        await update.message.reply_text(
            f"✅ **Key Generated!**\n"
            f"🔑 `{generated_keys[0]}`\n"
            f"⏳ Expires: `{duration}`",
            parse_mode="Markdown"
        )
    else:
        keys_text = "\n".join(f"🔑 `{key}`" for key in generated_keys)
        await update.message.reply_text(
            f"✅ **{quantity} Keys Generated!**\n"
            f"⏳ Expires: `{duration}`\n\n"
            f"{keys_text}",
            parse_mode="Markdown"
        )

async def login_user(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    
    if keys_data["settings"]["maintenance"] and chat_id != str(ADMIN_ID):
        return await update.message.reply_text("🔧 Inaayos pa nang pogi mag antay kanga wag atat!")
    
    if str(chat_id) in keys_data.get("banned_users", []):
        return await update.message.reply_text("🚨 Your account has been banned!")
    
    if len(context.args) < 2:
        return await update.message.reply_text(
            "⚠ Usage: `/login <username> <key>`\n"
            "Example: `/login john_doe MRMODDER-ABCD1234`",
            parse_mode="Markdown"
        )
    
    username, entered_key = context.args[0], context.args[1]
    
    if entered_key not in keys_data["keys"]:
        return await update.message.reply_text("❌ Taena key ko ba talaga yan?!")
    
    expiry = keys_data["keys"][entered_key]
    if expiry is not None and datetime.now().timestamp() > expiry:
        del keys_data["keys"][entered_key]
        save_keys(keys_data)
        return await update.message.reply_text("❌ Expired nayan kumag!")
    
    # Register user
    keys_data["user_keys"][chat_id] = expiry
    del keys_data["keys"][entered_key]
    
    # Initialize user logs if not exists
    if chat_id not in keys_data["logs"]:
        keys_data["logs"][chat_id] = {
            "username": username,
            "first_login": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "generations_today": 0,
            "total_generations": 0
        }
    
    keys_data["statistics"]["active_users"] = len(keys_data["user_keys"])
    save_keys(keys_data)
    
    expiry_text = "Lifetime" if expiry is None else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M:%S')
    await update.message.reply_text(
        f"✅ **Login Successful!**\n"
        f"👤 Username: `{username}`\n"
        f"🆔 User ID: `{chat_id}`\n"
        f"⏳ Expires: `{expiry_text}`\n\n"
        f"Now you can use /generate to get accounts!",
        parse_mode="Markdown"
    )

async def view_logs(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin kaba? kupall!")
    
    if not keys_data["user_keys"]:
        return await update.message.reply_text("📂 No active users.")
    
    # Calculate some statistics
    active_users = len(keys_data["user_keys"])
    total_generations = keys_data["statistics"]["total_generations"]
    keys_generated = keys_data["statistics"]["keys_generated"]
    
    log_text = (
        f"📋 **System Statistics**\n"
        f"👥 Active Users: `{active_users}`\n"
        f"🔄 Total Generations: `{total_generations}`\n"
        f"🔑 Keys Generated: `{keys_generated}`\n\n"
        f"📜 **Recent Activity (Last 5 Users):**\n"
    )
    
    # Get last 5 active users
    users = sorted(
        [(user, data) for user, data in keys_data["logs"].items() if user in keys_data["user_keys"]],
        key=lambda x: x[1].get("last_activity", ""),
        reverse=True
    )[:5]
    
    for user, data in users:
        username = data.get("username", "Unknown")
        last_active = data.get("last_activity", "Never")
        generations = data.get("total_generations", 0)
        
        expiry = keys_data["user_keys"][user]
        expiry_text = "Lifetime" if expiry is None else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d')
        
        log_text += (
            f"👤 `{username}` (ID: `{user}`)\n"
            f"⏳ Expiry: `{expiry_text}` | 🔄 Generations: `{generations}`\n"
            f"🕒 Last Active: `{last_active}`\n\n"
        )
    
    await update.message.reply_text(log_text, parse_mode="Markdown")

async def status_check(update: Update, context: CallbackContext):
    if len(context.args) < 1:
        return await update.message.reply_text("⚠ Usage: `/status <username|user_id> [full]`")
    
    target = context.args[0]
    show_full = len(context.args) > 1 and context.args[1].lower() == "full"
    
    # Find user by username or ID
    user_id = None
    username = None
    
    # Check if target is a user ID
    if target in keys_data["user_keys"]:
        user_id = target
        for uid, data in keys_data["logs"].items():
            if uid == target:
                username = data.get("username", "Unknown")
                break
    else:
        # Search by username
        for uid, data in keys_data["logs"].items():
            if data.get("username", "").lower() == target.lower():
                user_id = uid
                username = data.get("username", "Unknown")
                break
    
    if not user_id:
        return await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode="Markdown")
    
    expiry = keys_data["user_keys"][user_id]
    expiry_text = "Lifetime" if expiry is None else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M:%S')
    
    response = f"🔍 **Status for {username}**\n"
    response += f"🆔 User ID: `{user_id}`\n"
    response += f"⏳ Expiry: `{expiry_text}`\n"
    
    if show_full or update.message.chat_id == ADMIN_ID:
        is_banned = user_id in keys_data.get("banned_users", [])
        limit = keys_data["user_limits"].get(user_id, "Unlimited")
        last_active = keys_data["logs"][user_id].get("last_activity", "Never")
        generations = keys_data["logs"][user_id].get("total_generations", 0)
        
        response += f"🚫 Banned: `{'Yes' if is_banned else 'No'}`\n"
        response += f"📊 Limit: `{limit}`\n"
        response += f"🔄 Total Generations: `{generations}`\n"
        response += f"🕒 Last Active: `{last_active}`\n"
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def account_expiry(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) < 2:
        return await update.message.reply_text(
            "⚠ Usage: `/setexpiry <username|user_id> <duration|YYYY-MM-DD>`\n"
            "Example: `/setexpiry user123 7d` or `/setexpiry user123 2023-12-31`"
        )
    
    target = context.args[0]
    expiry_arg = " ".join(context.args[1:])
    
    # Find user by username or ID
    user_id = None
    
    # Check if target is a user ID
    if target in keys_data["user_keys"]:
        user_id = target
    else:
        # Search by username
        for uid, data in keys_data["logs"].items():
            if data.get("username", "").lower() == target.lower():
                user_id = uid
                break
    
    if not user_id:
        return await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode="Markdown")
    
    # Parse expiry time
    try:
        if 'd' in expiry_arg or 'h' in expiry_arg or 'm' in expiry_arg:
            # Duration format (e.g., 7d, 12h)
            duration_seconds = parse_duration(expiry_arg)
            expiry_timestamp = time.time() + duration_seconds
        else:
            # Date format (e.g., 2023-12-31)
            expiry_timestamp = datetime.strptime(expiry_arg, "%Y-%m-%d").timestamp()
    except:
        return await update.message.reply_text(
            "❌ Invalid expiry format. Use either:\n"
            "- Duration (e.g., 7d, 12h 30m)\n"
            "- Date (YYYY-MM-DD)"
        )
    
    keys_data["user_keys"][user_id] = expiry_timestamp
    save_keys(keys_data)
    
    expiry_date = datetime.fromtimestamp(expiry_timestamp).strftime('%Y-%m-%d %H:%M:%S')
    await update.message.reply_text(
        f"✅ Expiry for user `{user_id}` set to `{expiry_date}`",
        parse_mode="Markdown"
    )

async def account_details(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) != 1:
        return await update.message.reply_text("⚠ Usage: `/details <username|user_id>`")
    
    target = context.args[0]
    
    # Find user by username or ID
    user_id = None
    username = None
    
    if target in keys_data["user_keys"]:
        user_id = target
        for uid, data in keys_data["logs"].items():
            if uid == target:
                username = data.get("username", "Unknown")
                break
    else:
        for uid, data in keys_data["logs"].items():
            if data.get("username", "").lower() == target.lower():
                user_id = uid
                username = data.get("username", "Unknown")
                break
    
    if not user_id:
        return await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode="Markdown")
    
    expiry = keys_data["user_keys"][user_id]
    expiry_text = "Lifetime" if expiry is None else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M:%S')
    is_banned = user_id in keys_data.get("banned_users", [])
    limit = keys_data["user_limits"].get(user_id, "Unlimited")
    last_active = keys_data["logs"][user_id].get("last_activity", "Never")
    generations = keys_data["logs"][user_id].get("total_generations", 0)
    first_login = keys_data["logs"][user_id].get("first_login", "Unknown")
    
    response = f"📋 **Detailed Info for {username}**\n"
    response += f"🆔 User ID: `{user_id}`\n"
    response += f"⏳ Expiry: `{expiry_text}`\n"
    response += f"🚫 Banned: `{'Yes' if is_banned else 'No'}`\n"
    response += f"📊 Limit: `{limit}`\n"
    response += f"🔄 Total Generations: `{generations}`\n"
    response += f"📅 First Login: `{first_login}`\n"
    response += f"🕒 Last Active: `{last_active}`\n"
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def gen_account(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) < 3 or context.args[1] != "+":
        return await update.message.reply_text(
            "⚠ Usage: `/extend <username|user_id> + <duration>`\n"
            "Example: `/extend user123 + 3h 45m`"
        )
    
    target = context.args[0]
    duration_str = " ".join(context.args[2:])
    
    # Find user by username or ID
    user_id = None
    
    if target in keys_data["user_keys"]:
        user_id = target
    else:
        for uid, data in keys_data["logs"].items():
            if data.get("username", "").lower() == target.lower():
                user_id = uid
                break
    
    if not user_id:
        return await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode="Markdown")
    
    try:
        duration_seconds = parse_duration(duration_str)
    except:
        return await update.message.reply_text(
            "❌ Invalid duration format. Use like '+ 3h 45m'"
        )
    
    current_expiry = keys_data["user_keys"].get(user_id, time.time())
    if current_expiry is None:  # Lifetime account
        return await update.message.reply_text(
            "⚠️ This account has lifetime access. No need to extend."
        )
    
    new_expiry = (current_expiry if current_expiry > time.time() else time.time()) + duration_seconds
    keys_data["user_keys"][user_id] = new_expiry
    save_keys(keys_data)
    
    expiry_date = datetime.fromtimestamp(new_expiry).strftime('%Y-%m-%d %H:%M:%S')
    await update.message.reply_text(
        f"✅ Account `{target}` extended until `{expiry_date}`",
        parse_mode="Markdown"
    )

async def admin_reset(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) < 2:
        return await update.message.reply_text(
            "⚠ Usage: `/reset <username|user_id> <all|expiry|limit|ban>`"
        )
    
    target = context.args[0]
    reset_type = context.args[1].lower()
    
    # Find user by username or ID
    user_id = None
    username = None
    
    if target in keys_data["user_keys"]:
        user_id = target
        for uid, data in keys_data["logs"].items():
            if uid == target:
                username = data.get("username", "Unknown")
                break
    else:
        for uid, data in keys_data["logs"].items():
            if data.get("username", "").lower() == target.lower():
                user_id = uid
                username = data.get("username", "Unknown")
                break
    
    if not user_id:
        return await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode="Markdown")
    
    if reset_type == "all":
        del keys_data["user_keys"][user_id]
        keys_data["user_limits"].pop(user_id, None)
        if "banned_users" in keys_data and user_id in keys_data["banned_users"]:
            keys_data["banned_users"].remove(user_id)
        response = f"✅ Fully reset account `{username or user_id}`"
    elif reset_type == "expiry":
        del keys_data["user_keys"][user_id]
        response = f"✅ Reset expiry for account `{username or user_id}`"
    elif reset_type == "limit":
        keys_data["user_limits"].pop(user_id, None)
        response = f"✅ Reset limit for account `{username or user_id}`"
    elif reset_type == "ban":
        if "banned_users" not in keys_data:
            keys_data["banned_users"] = []
        if user_id in keys_data["banned_users"]:
            keys_data["banned_users"].remove(user_id)
            response = f"✅ Unbanned account `{username or user_id}`"
        else:
            keys_data["banned_users"].append(user_id)
            response = f"✅ Banned account `{username or user_id}`"
    else:
        return await update.message.reply_text("❌ Invalid reset type. Use all/expiry/limit/ban")
    
    save_keys(keys_data)
    await update.message.reply_text(response, parse_mode="Markdown")

async def force_expiry_delay(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) < 2:
        return await update.message.reply_text(
            "⚠ Usage: `/delay <username|user_id> +<duration>`\n"
            "Example: `/delay user123 +10d 5h`"
        )
    
    target = context.args[0]
    duration_str = " ".join(context.args[1:])
    
    # Find user by username or ID
    user_id = None
    
    if target in keys_data["user_keys"]:
        user_id = target
    else:
        for uid, data in keys_data["logs"].items():
            if data.get("username", "").lower() == target.lower():
                user_id = uid
                break
    
    if not user_id:
        return await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode="Markdown")
    
    try:
        duration_seconds = parse_duration(duration_str.replace("+", "").strip())
    except:
        return await update.message.reply_text("❌ Invalid duration format. Use like '+10d 5h'")
    
    current_expiry = keys_data["user_keys"].get(user_id, time.time())
    if current_expiry is None:
        new_expiry = time.time() + duration_seconds
    else:
        new_expiry = current_expiry + duration_seconds
    
    keys_data["user_keys"][user_id] = new_expiry
    save_keys(keys_data)
    
    expiry_date = datetime.fromtimestamp(new_expiry).strftime('%Y-%m-%d %H:%M:%S')
    await update.message.reply_text(
        f"✅ New expiry for `{target}`: `{expiry_date}`",
        parse_mode="Markdown"
    )

async def set_expiry_date(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) != 2:
        return await update.message.reply_text(
            "⚠ Usage: `/setexpiry <username|user_id> <YYYY-MM-DD>`\n"
            "Example: `/setexpiry user123 2023-12-31`"
        )
    
    target = context.args[0]
    expiry_date = context.args[1]
    
    # Find user by username or ID
    user_id = None
    
    if target in keys_data["user_keys"]:
        user_id = target
    else:
        for uid, data in keys_data["logs"].items():
            if data.get("username", "").lower() == target.lower():
                user_id = uid
                break
    
    if not user_id:
        return await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode="Markdown")
    
    try:
        expiry_timestamp = datetime.strptime(expiry_date, "%Y-%m-%d").timestamp()
    except:
        return await update.message.reply_text("❌ Invalid date format. Use YYYY-MM-DD")
    
    keys_data["user_keys"][user_id] = expiry_timestamp
    save_keys(keys_data)
    
    expiry_date_str = datetime.fromtimestamp(expiry_timestamp).strftime('%Y-%m-%d %H:%M:%S')
    await update.message.reply_text(
        f"✅ Expiry for `{target}` set to `{expiry_date_str}`",
        parse_mode="Markdown"
    )

async def set_limit(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) < 2:
        return await update.message.reply_text(
            "⚠ Usage: `/limit <username|user_id> <max|unlimited> [value]`\n"
            "Example: `/limit user123 max 50` or `/limit user123 unlimited`"
        )
    
    target = context.args[0]
    limit_type = context.args[1].lower()
    
    # Find user by username or ID
    user_id = None
    
    if target in keys_data["user_keys"]:
        user_id = target
    else:
        for uid, data in keys_data["logs"].items():
            if data.get("username", "").lower() == target.lower():
                user_id = uid
                break
    
    if not user_id:
        return await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode="Markdown")
    
    if limit_type == "max":
        if len(context.args) < 3:
            return await update.message.reply_text("❌ Please specify a limit value")
        
        try:
            limit = int(context.args[2])
            keys_data["user_limits"][user_id] = limit
            response = f"✅ Set max daily limit for `{target}` to `{limit}`"
        except:
            return await update.message.reply_text("❌ Invalid limit value. Must be a number")
    elif limit_type == "unlimited":
        keys_data["user_limits"].pop(user_id, None)
        response = f"✅ Removed limits for `{target}`"
    else:
        return await update.message.reply_text("❌ Invalid limit type. Use max/unlimited")
    
    save_keys(keys_data)
    await update.message.reply_text(response, parse_mode="Markdown")

async def ban_account(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) < 2:
        return await update.message.reply_text(
            "⚠ Usage: `/ban <username|user_id> <permanent|temporary> [duration]`\n"
            "Example: `/ban user123 permanent` or `/ban user123 temporary 7d`"
        )
    
    target = context.args[0]
    ban_type = context.args[1].lower()
    
    # Find user by username or ID
    user_id = None
    username = None
    
    if target in keys_data["user_keys"]:
        user_id = target
        for uid, data in keys_data["logs"].items():
            if uid == target:
                username = data.get("username", "Unknown")
                break
    else:
        for uid, data in keys_data["logs"].items():
            if data.get("username", "").lower() == target.lower():
                user_id = uid
                username = data.get("username", "Unknown")
                break
    
    if not user_id:
        return await update.message.reply_text(f"❌ User `{target}` not found!", parse_mode="Markdown")
    
    if "banned_users" not in keys_data:
        keys_data["banned_users"] = []
    
    if ban_type == "permanent":
        if user_id not in keys_data["banned_users"]:
            keys_data["banned_users"].append(user_id)
            response = f"✅ Permanently banned `{username or user_id}`"
        else:
            response = f"ℹ️ `{username or user_id}` is already banned"
    elif ban_type == "temporary":
        if len(context.args) < 3:
            return await update.message.reply_text("⚠ Please specify a duration")
        
        duration_str = " ".join(context.args[2:])
        try:
            duration_seconds = parse_duration(duration_str)
            ban_until = time.time() + duration_seconds
            keys_data["user_keys"][user_id] = ban_until
            if user_id not in keys_data["banned_users"]:
                keys_data["banned_users"].append(user_id)
            expiry_date = datetime.fromtimestamp(ban_until).strftime('%Y-%m-%d %H:%M:%S')
            response = f"✅ Temporarily banned `{username or user_id}` until `{expiry_date}`"
        except:
            return await update.message.reply_text("❌ Invalid duration format. Use like '10d 5h'")
    else:
        return await update.message.reply_text("❌ Invalid ban type. Use permanent/temporary")
    
    save_keys(keys_data)
    await update.message.reply_text(response, parse_mode="Markdown")

async def help_command(update: Update, context: CallbackContext):
    is_admin = update.message.chat_id == ADMIN_ID
    
    keyboard = [
        [InlineKeyboardButton("📋 User Commands", callback_data="user_help")],
        [InlineKeyboardButton("🔐 Admin Commands", callback_data="admin_help")] if is_admin else None,
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    keyboard = [btn for btn in keyboard if btn is not None]
    
    await update.message.reply_text(
        "📚 **Help Center**\nSelect a category:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def main_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    
    keyboard = [
        [InlineKeyboardButton("🔐 Login/Register", callback_data="login_menu")],
        [InlineKeyboardButton("🛠 Generate Accounts", callback_data= "generate_menu")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats_menu"),
         InlineKeyboardButton("ℹ️ Help", callback_data="help_menu")]
    ]
    
    if query.message.chat_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    
    await query.message.edit_text(
        "🏠 *Main Menu*\nSelect an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def help_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    is_admin = query.message.chat_id == ADMIN_ID
    
    if query.data == "user_help":
        help_text = """
🔹 *User Commands:*
/start - Start the bot
/status <username> - Check account status
/login <username> <key> - Login with your key
/generate - Generate accounts
/help - Show this help menu
"""
        keyboard = [
            [InlineKeyboardButton("🔐 Admin Commands", callback_data="admin_help")] if is_admin else None,
            [InlineKeyboardButton("🔙 Back", callback_data="help_menu")],
            [InlineKeyboardButton("🏠 Main", callback_data="main_menu")]
        ]
        keyboard = [btn for btn in keyboard if btn is not None]
        
        await query.message.edit_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    elif query.data == "admin_help" and is_admin:
        help_text = """
🔹 *Admin Commands:*
/genkey <duration> [quantity] - Generate keys
/reset <user> <type> - Reset account
/delay <user> +<duration> - Extend expiry
/setexpiry <user> <date> - Set expiry date
/limit <user> <type> <value> - Set limits
/ban <user> <type> [duration] - Ban user
/logs - View system logs
/maintenance <on/off> - Toggle maintenance
"""
        keyboard = [
            [InlineKeyboardButton("📋 User Commands", callback_data="user_help")],
            [InlineKeyboardButton("🔙 Back", callback_data="help_menu")],
            [InlineKeyboardButton("🏠 Main", callback_data="main_menu")]
        ]
        await query.message.edit_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    elif query.data == "help_menu":
        keyboard = [
            [InlineKeyboardButton("📋 User Commands", callback_data="user_help")],
            [InlineKeyboardButton("🔐 Admin Commands", callback_data="admin_help")] if is_admin else None,
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        keyboard = [btn for btn in keyboard if btn is not None]
        
        await query.message.edit_text(
            "📚 **Help Center**\nSelect a category:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def login_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔑 I have a key", callback_data="has_key")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    
    await query.message.edit_text(
        "🔐 *Account Access*\n\n"
        "To use the generator, you need an activation key from admin\n\n"
        "Select an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def has_key_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🔑 To login with a key, send:\n`/login <username> <your_key>`\n\n"
        "Example: `/login john_doe AKIRO-ABCD1234`",
        parse_mode="Markdown"
    )

async def admin_panel_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.message.chat_id != ADMIN_ID:
        return await query.message.reply_text("❌ Admin only!")
    
    maintenance_status = "ON 🔴" if keys_data["settings"]["maintenance"] else "OFF 🟢"
    
    keyboard = [
        [InlineKeyboardButton("🔑 Generate Keys", callback_data="gen_key_admin")],
        [InlineKeyboardButton("📋 View Logs", callback_data="view_logs_admin")],
        [InlineKeyboardButton("👥 Manage Users", callback_data="manage_accounts")],
        [InlineKeyboardButton("⚙️ Maintenance Mode", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("📊 Statistics", callback_data="view_stats_admin")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    
    await query.message.edit_text(
        f"⚙️ **Admin Panel**\n"
        f"🔧 Maintenance: `{maintenance_status}`\n\n"
        "Select an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def toggle_maintenance(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keys_data["settings"]["maintenance"] = not keys_data["settings"]["maintenance"]
    save_keys(keys_data)
    
    status = "ON 🔴" if keys_data["settings"]["maintenance"] else "OFF 🟢"
    await query.message.reply_text(
        f"✅ Maintenance mode is now `{status}`",
        parse_mode="Markdown"
    )
    await admin_panel_button(update, context)

async def gen_key_admin(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🔑 To generate keys:\n`/genkey <duration> [quantity]`\n\n"
        "Available durations: 1h, 6h, 12h, 1d, 3d, 7d, 14d, 30d, lifetime\n"
        "Example: `/genkey 7d 5` (generates 5 keys valid for 7 days)",
        parse_mode="Markdown"
    )

async def view_logs_admin(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await view_logs(Update(message=query.message, active_user=query.from_user), context)

async def view_stats_admin(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    stats = keys_data["statistics"]
    active_users = len(keys_data["user_keys"])
    banned_users = len(keys_data.get("banned_users", []))
    
    text = f"""
📊 *System Statistics*

👥 Users:
- Active: `{active_users}`
- Banned: `{banned_users}`

📈 Activity:
- Total Generations: `{stats['total_generations']}`
- Keys Generated: `{stats['keys_generated']}`

🛠 Last Backup: `{datetime.fromtimestamp(os.path.getmtime(KEYS_FILE)).strftime('%Y-%m-%d %H:%M:%S')}`
"""
    
    await query.message.reply_text(
        text,
        parse_mode="Markdown"
    )

async def manage_accounts(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔄 Reset Account", callback_data="reset_account")],
        [InlineKeyboardButton("⏳ Set Expiry", callback_data="set_expiry")],
        [InlineKeyboardButton("📊 Set Limit", callback_data="set_limit_btn")],
        [InlineKeyboardButton("🚫 Ban Account", callback_data="ban_account_btn")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]
    ]
    
    await query.message.edit_text(
        "👥 **User Management**\nSelect an action:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def reset_account_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🔄 To reset an account:\n`/reset <username|user_id> <all|expiry|limit|ban>`\n\n"
        "Example: `/reset user123 all` (full reset)",
        parse_mode="Markdown"
    )

async def set_expiry_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "⏳ To set expiry:\n`/setexpiry <username|user_id> <duration|YYYY-MM-DD>`\n\n"
        "Example: `/setexpiry user123 7d` (7 days from now)\n"
        "`/setexpiry user123 2023-12-31` (specific date)",
        parse_mode="Markdown"
    )

async def set_limit_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📊 To set limits:\n`/limit <username|user_id> <max|unlimited> [value]`\n\n"
        "Example: `/limit user123 max 50` (max 50 generations/day)\n"
        "`/limit user123 unlimited` (remove limits)",
        parse_mode="Markdown"
    )

async def ban_account_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🚫 To ban an account:\n`/ban <username|user_id> <permanent|temporary> [duration]`\n\n"
        "Example: `/ban user123 permanent`\n"
        "`/ban user123 temporary 7d` (7 day ban)",
        parse_mode="Markdown"
    )

async def stats_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    
    user_logs = keys_data["logs"].get(chat_id, {})
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_logs.get("last_generation_date") != today:
        user_logs["generations_today"] = 0
        user_logs["last_generation_date"] = today
    
    expiry = keys_data["user_keys"].get(chat_id, 0)
    expiry_text = "Lifetime" if expiry is None else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M:%S')
    
    text = f"""
📊 *Your Statistics*

⏳ Expiry Date: `{expiry_text}`
🔄 Generations Today: `{user_logs.get("generations_today", 0)}`/{MAX_DAILY_GENERATIONS}
📅 First Login: `{user_logs.get("first_login", "Unknown")}`
🕒 Last Active: `{user_logs.get("last_activity", "Never")}`
"""
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def maintenance_command(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if len(context.args) != 1 or context.args[0] not in ["on", "off"]:
        return await update.message.reply_text("⚠ Usage: `/maintenance <on|off>`")
    
    keys_data["settings"]["maintenance"] = (context.args[0] == "on")
    save_keys(keys_data)
    
    status = "ON 🔴" if keys_data["settings"]["maintenance"] else "OFF 🟢"
    await update.message.reply_text(
        f"✅ Maintenance mode is now `{status}`",
        parse_mode="Markdown"
    )

async def broadcast_message(update: Update, context: CallbackContext):
    if update.message.chat_id != ADMIN_ID:
        return await update.message.reply_text("❌ Admin only command!")
    
    if not context.args:
        return await update.message.reply_text("⚠ Usage: `/broadcast <message>`")
    
    message = " ".join(context.args)
    users = list(keys_data["user_keys"].keys())
    success = 0
    failed = 0
    
    progress_msg = await update.message.reply_text(
        f"📢 Broadcasting to {len(users)} users...\n"
        "0% completed (0/{len(users)})"
    )
    
    for i, user_id in enumerate(users):
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 *Announcement from Admin*\n\n{message}",
                parse_mode="Markdown"
            )
            success += 1
        except Exception as e:
            console.print(f"[red]❌ Failed to send to {user_id}: {e}[/red]")
            failed += 1
        
        # Update progress every 10% or every 10 users
        if i % 10 == 0 or i == len(users) - 1:
            percent = int((i + 1) / len(users) * 100)
            await progress_msg.edit_text(
                f"📢 Broadcasting to {len(users)} users...\n"
                f"{percent}% completed ({i + 1}/{len(users)})\n"
                f"✅ Success: {success} | ❌ Failed: {failed}"
            )
    
    await update.message.reply_text(
        f"📢 Broadcast completed!\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}"
    )

async def unknown_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "❌ Unknown command. Use /help to see available commands."
    )

def display_features():
    table = Table("✨ Feature", "📝 Description", title="🌟 Features")
    table.add_row("🔑 Key Generation", "Create access keys with expiration")
    table.add_row("👤 User Management", "Add/remove/modify user accounts")
    table.add_row("⏳ Expiration Tracking", "Monitor account validity periods")
    table.add_row("📊 Statistics", "Track system usage and activity")
    table.add_row("🔒 Security", "Data encryption and integrity checks")
    console.print(table)

def admin_panel_cli():
    if not os.path.exists(KEYS_HASH_FILE):
        generate_key_hash(keys_data)
    
    display_features()
    while True:
        console.print("\n[bold magenta]╔══════════════╗[/bold magenta]")
        console.print("[bold magenta]║  ADMIN PANEL ║[/bold magenta]")
        console.print("[bold magenta]╚══════════════╝[/bold magenta]")
        console.print("[bold green]1.[/bold green] ✨ Register User")
        console.print("[bold green]2.[/bold green] 🔐 Authentication")
        console.print("[bold green]3.[/bold green] ⏳ Expiration Report")
        console.print("[bold green]4.[/bold green] 📊 View Statistics")
        console.print("[bold green]5.[/bold green] 🛠 Maintenance Tools")
        console.print("[bold green]6.[/bold green] 🚪 Exit to Bot")
        choice = Prompt.ask("[bold blue]❯ Select option:[/bold blue]")

        if choice == "1":
            register_user()
        elif choice == "2":
            authenticate_user()
        elif choice == "3":
            show_expiration_report()
        elif choice == "4":
            show_statistics()
        elif choice == "5":
            maintenance_tools()
        elif choice == "6":
            break
        else:
            console.print("[bold red]❌ Invalid choice![/bold red]")

def register_user():
    console.print(Panel("[bold blue]✨ User Registration[/bold blue]", expand=False))
    username = Prompt.ask("[bold blue]👤 Username:[/bold blue]")
    if username in [data.get("username") for data in keys_data["logs"].values()]:
        console.print(Panel(f"[bold red]❌ Error: Username '{username}' exists![/bold red]", expand=False))
        return

    device_id = generate_device_id()
    key = generate_random_key()

    while True:
        try:
            duration = Prompt.ask(
                "[bold blue]⏳ Duration (e.g., 7d, 1h, 30m or 'lifetime'):[/bold blue]",
                default="7d"
            )
            
            if duration.lower() == "lifetime":
                expiry = None
                break
            
            duration_seconds = parse_duration(duration)
            if duration_seconds <= 0:
                raise ValueError("Duration must be positive")
            
            expiry = time.time() + duration_seconds
            break
        except ValueError as e:
            console.print(f"[red]❌ Error: {e}[/red]")

    keys_data["keys"][key] = expiry
    keys_data["logs"][device_id] = {
        "username": username,
        "first_login": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "last_activity": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "generations_today": 0,
        "total_generations": 0
    }
    save_keys(keys_data)

    expiry_text = "Lifetime" if expiry is None else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M:%S')
    console.print(Panel(
        f"[bold green]✅ User '{username}' registered!\n"
        f"🔑 Key: {key}\n"
        f"⏳ Expires: {expiry_text}\n"
        f"🆔 Device ID: {device_id}[/bold green]",
        expand=False
    ))

def authenticate_user():
    console.print(Panel("[bold blue]🔐 Authentication[/bold blue]", expand=False))
    username = Prompt.ask("[bold blue]👤 Username:[/bold blue]")
    key = Prompt.ask("[bold blue]🔑 Key:[/bold blue]")

    user_found = None
    for device_id, data in keys_data["logs"].items():
        if data.get("username") == username:
            user_found = device_id
            break
    
    if not user_found:
        console.print(Panel("[bold red]❌ User Not Found![/bold red]", expand=False))
        return False
    
    if key not in keys_data["keys"]:
        console.print(Panel("[bold red]❌ Invalid Key![/bold red]", expand=False))
        return False
    
    expiry = keys_data["keys"][key]
    if expiry is not None and datetime.now().timestamp() > expiry:
        del keys_data["keys"][key]
        save_keys(keys_data)
        console.print(Panel("[bold red]❌ This key has expired![/bold red]", expand=False))
        return False
    
    keys_data["user_keys"][user_found] = expiry
    del keys_data["keys"][key]
    save_keys(keys_data)
    
    expiry_text = "Lifetime" if expiry is None else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M:%S')
    console.print(Panel(
        f"[bold green]✅ Authentication Successful!\n"
        f"👤 Username: {username}\n"
        f"⏳ Expires: {expiry_text}[/bold green]",
        expand=False
    ))
    return True

def show_expiration_report():
    console.print(Panel("[bold yellow]⏳ Expiration Report[/bold yellow]", expand=False))
    if not keys_data["user_keys"]:
        console.print("[yellow]📭 No registered users[/yellow]")
        return

    table = Table("👤 Username", "🆔 Device ID", "⏳ Expiry Time", "🔄 Generations", title="📋 Active Users")
    for device_id, expiry in keys_data["user_keys"].items():
        user_data = keys_data["logs"].get(device_id, {})
        username = user_data.get("username", "Unknown")
        generations = user_data.get("total_generations", 0)
        
        expiry_text = "Lifetime" if expiry is None else datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M:%S')
        table.add_row(username, device_id[:8] + "...", expiry_text, str(generations))
    
    console.print(table)

def show_statistics():
    stats = keys_data["statistics"]
    active_users = len(keys_data["user_keys"])
    banned_users = len(keys_data.get("banned_users", []))
    
    table = Table("📊 Metric", "📝 Value", title="📈 System Statistics")
    table.add_row("👥 Active Users", str(active_users))
    table.add_row("🚫 Banned Users", str(banned_users))
    table.add_row("🔄 Total Generations", str(stats["total_generations"]))
    table.add_row("🔑 Keys Generated", str(stats["keys_generated"]))
    table.add_row("💾 Last Backup", datetime.fromtimestamp(os.path.getmtime(KEYS_FILE)).strftime('%Y-%m-%d %H:%M:%S'))
    
    console.print(table)

def maintenance_tools():
    console.print(Panel("[bold red]🛠 Maintenance Tools[/bold red]", expand=False))
    console.print("[bold green]1.[/bold green] 🔧 Toggle Maintenance Mode")
    console.print("[bold green]2.[/bold green] 🔄 Create Backup")
    console.print("[bold green]3.[/bold green] ⏰ Check Expired Accounts")
    console.print("[bold green]4.[/bold green] 🔙 Back")
    
    choice = Prompt.ask("[bold blue]❯ Select option:[/bold blue]")
    
    if choice == "1":
        keys_data["settings"]["maintenance"] = not keys_data["settings"]["maintenance"]
        save_keys(keys_data)
        status = "ON" if keys_data["settings"]["maintenance"] else "OFF"
        console.print(f"[green]✅ Maintenance mode is now {status}[/green]")
    elif choice == "2":
        save_keys(keys_data)
        console.print("[green]✅ Backup created successfully[/green]")
    elif choice == "3":
        now = time.time()
        expired = [uid for uid, expiry in keys_data["user_keys"].items() if expiry and expiry < now]
        console.print(f"[yellow]🕒 Found {len(expired)} expired accounts[/yellow]")
        if expired and Confirm.ask("[bold]Remove expired accounts?[/bold]"):
            for uid in expired:
                del keys_data["user_keys"][uid]
            save_keys(keys_data)
            console.print(f"[green]✅ Removed {len(expired)} expired accounts[/green]")
    elif choice == "4":
        return
    else:
        console.print("[red]❌ Invalid choice![/red]")

if __name__ == "__main__":
    # Initialize files if they don't exist
    if not os.path.exists(USED_ACCOUNTS_FILE):
        open(USED_ACCOUNTS_FILE, "w").close()
    
    for db_file in DATABASE_FILES:
        if not os.path.exists(db_file):
            open(db_file, "w").close()
    
    keys_data = load_keys()
    
    # Start background tasks
    loop = asyncio.get_event_loop()
    loop.create_task(backup_task())
    loop.create_task(check_expirations())
    
    # Start admin panel in a separate thread
    panel_thread = threading.Thread(target=admin_panel_cli)
    panel_thread.daemon = True
    panel_thread.start()
    
    # Create and configure bot
    app = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("generate", generate_menu))
    app.add_handler(CommandHandler("genkey", generate_key))
    app.add_handler(CommandHandler("login", login_user))
    app.add_handler(CommandHandler("logs", view_logs))
    app.add_handler(CommandHandler("status", status_check))
    app.add_handler(CommandHandler("setexpiry", account_expiry))
    app.add_handler(CommandHandler("details", account_details))
    app.add_handler(CommandHandler("extend", gen_account))
    app.add_handler(CommandHandler("reset", admin_reset))
    app.add_handler(CommandHandler("delay", force_expiry_delay))
    app.add_handler(CommandHandler("setexpiry", set_expiry_date))
    app.add_handler(CommandHandler("limit", set_limit))
    app.add_handler(CommandHandler("ban", ban_account))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_menu))
    app.add_handler(CommandHandler("maintenance", maintenance_command))
    app.add_handler(CommandHandler("broadcast", broadcast_message))
    
    # Add callback handlers
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(help_menu, pattern="^help_menu$"))
    app.add_handler(CallbackQueryHandler(help_menu, pattern="^user_help$"))
    app.add_handler(CallbackQueryHandler(help_menu, pattern="^admin_help$"))
    app.add_handler(CallbackQueryHandler(login_menu, pattern="^login_menu$"))
    app.add_handler(CallbackQueryHandler(has_key_menu, pattern="^has_key$"))
    app.add_handler(CallbackQueryHandler(generate_menu, pattern="^generate_menu$"))
    app.add_handler(CallbackQueryHandler(show_category_domains, pattern="^category_"))
    app.add_handler(CallbackQueryHandler(generate_filtered_accounts, pattern="^generate_"))
    app.add_handler(CallbackQueryHandler(search_all_domains, pattern="^search_all_domains$"))
    app.add_handler(CallbackQueryHandler(admin_panel_button, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(toggle_maintenance, pattern="^toggle_maintenance$"))
    app.add_handler(CallbackQueryHandler(gen_key_admin, pattern="^gen_key_admin$"))
    app.add_handler(CallbackQueryHandler(view_logs_admin, pattern="^view_logs_admin$"))
    app.add_handler(CallbackQueryHandler(view_stats_admin, pattern="^view_stats_admin$"))
    app.add_handler(CallbackQueryHandler(manage_accounts, pattern="^manage_accounts$"))
    app.add_handler(CallbackQueryHandler(reset_account_button, pattern="^reset_account$"))
    app.add_handler(CallbackQueryHandler(set_expiry_button, pattern="^set_expiry$"))
    app.add_handler(CallbackQueryHandler(set_limit_button, pattern="^set_limit_btn$"))
    app.add_handler(CallbackQueryHandler(ban_account_button, pattern="^ban_account_btn$"))
    app.add_handler(CallbackQueryHandler(stats_menu, pattern="^stats_menu$"))
    
    # Add handler for unknown commands
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    console.print(f"[green]🤖  KIROS Premium Generator v{VERSION} is running...[/green]")
    console.print(f"[yellow]🛠 Admin panel available in separate thread[/yellow]")
    
    try:
        app.run_polling()
    except Exception as e:
        console.print(f"[red]❌ Bot crashed: {e}[/red]")
    finally:
        # Ensure data is saved before exiting
        save_keys(keys_data)
        console.print("[yellow]🔒 All data saved. Exiting...[/yellow]")