import os
import discord
from discord.ext import commands
from openai import OpenAI
import google.generativeai as genai
from flask import Flask
import threading
import json
from collections import defaultdict

# ১. Flask সার্ভার সেটআপ (Render-এর জন্য)
app = Flask('')

@app.route('/')
def home():
    return "Tarzan AI Bot is alive and running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ২. DeepSeek এবং Gemini Client সেটআপ
deepseek_client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=(
        "You are Tarzan AI, a smart, friendly, and helpful Discord AI assistant. "
        "You reply clearly and concisely. Always respond in Bangla."
    )
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CONFIG_FILE = "allowed_channels.json"
chat_history = defaultdict(list)
gemini_chats = {}
MAX_HISTORY_LENGTH = 30

BOT_PERSONALITY = (
    "You are Tarzan AI, a smart, friendly, and helpful Discord AI assistant. "
    "You reply clearly and concisely. Always respond in Bangla."
)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # বোটের স্ট্যাটাস সেট করা (Playing Lightning Speeeed Ai)
    activity = discord.Activity(type=discord.ActivityType.playing, name="Lightning Speeeed Ai")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    
    print("Tarzan AI is ready and online with new status!")

# --- ৩. চ্যানেল ও মেমোরি কন্ট্রোল কমান্ডসমূহ ---

@bot.command(name="setchannel")
@commands.has_permissions(administrator=True)
async def setchannel(ctx, channel: discord.TextChannel = None):
    if not channel:
        channel = ctx.channel
    config = load_config()
    config[str(ctx.guild.id)] = channel.id
    save_config(config)
    await ctx.send(f"সফলভাবে সেট করা হয়েছে! এখন থেকে Tarzan AI শুধুমাত্র {channel.mention} চ্যানেলে কাজ করবে।")

@bot.command(name="removechannel")
@commands.has_permissions(administrator=True)
async def removechannel(ctx):
    config = load_config()
    if str(ctx.guild.id) in config:
        del config[str(ctx.guild.id)]
        save_config(config)
        await ctx.send("চ্যানেল রেস্ট্রিকশন মুছে ফেলা হয়েছে! যেকোনো চ্যানেলে Tarzan AI কাজ করবে।")
    else:
        await ctx.send("কোনো নির্দিষ্ট চ্যানেল সেট করা নেই।")

@bot.command(name="clearmemory")
async def clearmemory(ctx):
    channel_id = ctx.channel.id
    if channel_id in chat_history:
        chat_history[channel_id].clear()
    if channel_id in gemini_chats:
        gemini_chats[channel_id] = gemini_model.start_chat(history=[])
    await ctx.send("চ্যাট মেমোরি পরিষ্কার করা হয়েছে! Tarzan AI নতুন করে চ্যাট শুরু করবে।")

@setchannel.error
async def setchannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("দুঃখিত, এই কমান্ডটি ব্যবহার করার জন্য আপনার **Administrator** পারমিশন থাকতে হবে!")

# --- ৪. মেসেজ হ্যান্ডলার (স্বয়ংক্রিয় এআই উত্তর) ---

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    # চ্যানেল ম্যানেজমেন্ট কমান্ডগুলো প্রসেস করা
    await bot.process_commands(message)

    # '!' দিয়ে শুরু হওয়া মেসেজগুলো (কমান্ড) এআই দ্বারা উত্তর হবে না
    if message.content.startswith("!"):
        return

    # চ্যানেল রেস্ট্রিকশন চেক
    config = load_config()
    guild_id = str(message.guild.id)
    if guild_id in config:
        if message.channel.id != config[guild_id]:
            return

    prompt = message.content.strip()
    if not prompt:
        return

    async with message.channel.typing():
        try:
            channel_id = message.channel.id
            answer = ""

            # প্রশ্ন দীর্ঘ বা কোডিং/জটিল হলে Gemini, সাধারণ কথার জন্য DeepSeek
            is_complex = len(prompt) > 80 or any(kw in prompt.lower() for kw in ["code", "python", "javascript", "explain", "why", "how", "কোড", "ব্যাখ্যা", "কেন", "কীভাবে"])

            if is_complex:
                if channel_id not in gemini_chats:
                    gemini_chats[channel_id] = gemini_model.start_chat(history=[])
                
                chat_session = gemini_chats[channel_id]
                response = chat_session.send_message(prompt)
                answer = response.text
            else:
                messages_payload = [{"role": "system", "content": BOT_PERSONALITY}]
                messages_payload.extend(chat_history[channel_id])
                messages_payload.append({"role": "user", "content": prompt})

                response = deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages_payload
                )
                answer = response.choices[0].message.content

                chat_history[channel_id].append({"role": "user", "content": prompt})
                chat_history[channel_id].append({"role": "assistant", "content": answer})

                if len(chat_history[channel_id]) > MAX_HISTORY_LENGTH:
                    chat_history[channel_id] = chat_history[channel_id][-MAX_HISTORY_LENGTH:]

            # ডিসকর্ডের ২০০০ অক্ষরের লিমিট হ্যান্ডেল করা
            if len(answer) > 2000:
                for i in range(0, len(answer), 2000):
                    await message.channel.send(answer[i:i+2000])
            else:
                await message.channel.send(answer)

        except Exception as e:
            # ব্যাকআপ সিস্টেম
            try:
                messages_payload = [{"role": "system", "content": BOT_PERSONALITY}, {"role": "user", "content": prompt}]
                response = deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages_payload
                )
                await message.channel.send(response.choices[0].message.content)
            except Exception as backup_err:
                await message.channel.send(f"দুঃখিত, উত্তর দিতে সমস্যা হয়েছে: {backup_err}")

# ৫. বোট চালানো
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()
    
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_TOKEN environment variable not set.")
