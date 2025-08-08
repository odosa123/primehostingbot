import telebot, os, subprocess, threading, time, sqlite3
from telebot import types
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("8299348274:AAF_8StvDGF1vlFOyOwhpPk9yhEnKGQ2exQ")  # ✅ Fixed: Load from correct env variable name
OWNER_ID = 8138742825
MAX_FREE_UPLOADS = 2
FREE_USER_LIMIT = 2
VIP_USER_LIMIT = 10
OWNER_LIMIT = 99999999
LOCKED = False

bot = telebot.TeleBot(BOT_TOKEN)
conn = sqlite3.connect("vipdata.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS vip (user_id INTEGER PRIMARY KEY, expires_at INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS usage (user_id INTEGER, date TEXT, count INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
conn.commit()

running_processes = {}
last_logs = {}

def is_vip(user_id):
    if user_id == OWNER_ID:
        return True
    cursor.execute("SELECT expires_at FROM vip WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row and int(time.time()) < row[0]:
        return True
    return False

def get_limit(user_id):
    if user_id == OWNER_ID:
        return OWNER_LIMIT
    elif is_vip(user_id):
        return VIP_USER_LIMIT
    else:
        return FREE_USER_LIMIT

def can_upload(user_id):
    if user_id == OWNER_ID or is_vip(user_id):
        return True
    user_dir = f"files/{user_id}"
    if not os.path.exists(user_dir):
        return True
    return len(os.listdir(user_dir)) < MAX_FREE_UPLOADS

def ensure_user_dir(user_id):
    user_dir = f"files/{user_id}"
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def track_usage(user_id):
    date = datetime.utcnow().strftime("%Y-%m-%d")
    cursor.execute("SELECT count FROM usage WHERE user_id=? AND date=?", (user_id, date))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE usage SET count=? WHERE user_id=? AND date=?", (row[0]+1, user_id, date))
    else:
        cursor.execute("INSERT INTO usage (user_id, date, count) VALUES (?, ?, 1)", (user_id, date))
    conn.commit()

def usage_remaining(user_id):
    limit = get_limit(user_id)
    if limit == OWNER_LIMIT:
        return "∞"
    date = datetime.utcnow().strftime("%Y-%m-%d")
    cursor.execute("SELECT count FROM usage WHERE user_id=? AND date=?", (user_id, date))
    row = cursor.fetchone()
    return limit - row[0] if row else limit

def clean_old_files():
    now = time.time()
    for root, dirs, files in os.walk("files"):
        for f in files:
            path = os.path.join(root, f)
            if os.path.isfile(path) and now - os.path.getmtime(path) > 3600:
                os.remove(path)

def run_bot(user_id, filepath):
    ext = filepath.split(".")[-1]
    cmd = ["python3", filepath] if ext == "py" else ["node", filepath]
    def runner():
        while True:
            if user_id not in running_processes:
                break
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                running_processes[user_id] = proc
                output = ""
                for line in proc.stdout:
                    output += line.decode()
                    last_logs[user_id] = output[-4000:]
                proc.wait()
                if user_id in running_processes:
                    time.sleep(60)
            except:
                break
    threading.Thread(target=runner, daemon=True).start()

@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "👋 Welcome to the Hosting Bot! Use /upload to upload your Python or JS bot.")
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (msg.from_user.id,))
    conn.commit()

@bot.message_handler(commands=['vip'])
def vip_status(msg):
    vip = is_vip(msg.from_user.id)
    left = usage_remaining(msg.from_user.id)
    bot.reply_to(msg, f"VIP: {'✅ Yes' if vip else '❌ No'}\nUsage left today: {left}")

@bot.message_handler(commands=['buyvip'])
def buyvip(msg):
    btn = types.InlineKeyboardMarkup()
    btn.add(types.InlineKeyboardButton("💎 Contact Owner", url="https://t.me/ItzjustPRIME"))
    bot.reply_to(msg, "🚀 Get VIP for more uploads & unlimited runs!", reply_markup=btn)

@bot.message_handler(commands=['channel'])
def channel(msg):
    bot.reply_to(msg, "📢 Stay updated: https://t.me/RN_PRIME")

@bot.message_handler(commands=['contact'])
def contact(msg):
    bot.reply_to(msg, "👤 Contact the owner: https://t.me/ItzjustPRIME")

@bot.message_handler(commands=['speed'])
def speed(msg):
    start = time.time()
    reply = bot.reply_to(msg, "⏱ Testing...")
    latency = time.time() - start
    bot.edit_message_text(f"⚡ Response time: {latency:.3f} sec", msg.chat.id, reply.message_id)

@bot.message_handler(commands=['stat'])
def stats(msg):
    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM vip WHERE expires_at > ?", (int(time.time()),))
    vips = cursor.fetchone()[0]
    bot.reply_to(msg, f"📊 Users: {users}\n💎 VIPs: {vips}")

@bot.message_handler(commands=['lock'])
def lock(msg):
    global LOCKED
    if msg.from_user.id == OWNER_ID:
        LOCKED = True
        bot.reply_to(msg, "🔒 Bot is now locked. No one can use it.")

@bot.message_handler(commands=['unlock'])
def unlock(msg):
    global LOCKED
    if msg.from_user.id == OWNER_ID:
        LOCKED = False
        bot.reply_to(msg, "🔓 Bot is now unlocked.")

@bot.message_handler(commands=['upload'])
def upload(msg):
    if LOCKED and msg.from_user.id != OWNER_ID:
        return bot.reply_to(msg, "🔒 Bot is currently locked.")
    bot.reply_to(msg, "📤 Send your .py or .js file now.")

@bot.message_handler(content_types=['document'])
def handle_file(msg):
    if LOCKED and msg.from_user.id != OWNER_ID:
        return bot.reply_to(msg, "🔒 Bot is currently locked.")

    user_id = msg.from_user.id
    if not can_upload(user_id):
        return bot.reply_to(msg, "❌ Upload limit reached. Buy VIP to increase limit.")

    file_info = bot.get_file(msg.document.file_id)
    filename = msg.document.file_name
    if not filename.endswith(".py") and not filename.endswith(".js"):
        return bot.reply_to(msg, "❌ Only .py and .js files are supported.")

    user_dir = ensure_user_dir(user_id)
    filepath = os.path.join(user_dir, filename)
    downloaded_file = bot.download_file(file_info.file_path)
    with open(filepath, "wb") as f:
        f.write(downloaded_file)

    bot.reply_to(msg, f"✅ Uploaded `{filename}`.", parse_mode="Markdown")

@bot.message_handler(commands=['run'])
def run_script(msg):
    user_id = msg.from_user.id
    user_dir = ensure_user_dir(user_id)
    files = os.listdir(user_dir)
    if not files:
        return bot.reply_to(msg, "❌ No uploaded file found.")
    filename = files[0]
    filepath = os.path.join(user_dir, filename)
    run_bot(user_id, filepath)
    track_usage(user_id)
    bot.reply_to(msg, f"🚀 Running `{filename}`.", parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_script(msg):
    user_id = msg.from_user.id
    proc = running_processes.pop(user_id, None)
    if proc:
        proc.kill()
        bot.reply_to(msg, "🛑 Script stopped.")
    else:
        bot.reply_to(msg, "⚠️ No script running.")

@bot.message_handler(commands=['delete'])
def delete_script(msg):
    user_dir = ensure_user_dir(msg.from_user.id)
    for f in os.listdir(user_dir):
        os.remove(os.path.join(user_dir, f))
    if msg.from_user.id in running_processes:
        running_processes[msg.from_user.id].kill()
        del running_processes[msg.from_user.id]
    bot.reply_to(msg, "🗑️ File(s) and process deleted.")

@bot.message_handler(commands=['logs'])
def get_logs(msg):
    log = last_logs.get(msg.from_user.id)
    if not log:
        return bot.reply_to(msg, "⚠️ No logs found.")
    bot.reply_to(msg, f"📄 Last logs:\n```\n{log}```", parse_mode="Markdown")

threading.Thread(target=clean_old_files, daemon=True).start()
bot.polling(non_stop=True)
