import os
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USER_IDS = set(int(x) for x in os.environ["ALLOWED_TELEGRAM_USER_IDS"].split(","))
STATE_FILE       = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"log_num": 1}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def today_str():
    return datetime.now().strftime("%d/%m/%Y")

def user_tag(update: Update):
    user = update.effective_user
    return f"user={user.id} username=@{user.username or 'none'}"

def format_caption(log_num, thought, hashtags):
    tags = hashtags.strip()
    if tags and "#journalling" not in tags:
        tags = "#journalling " + tags
    elif not tags:
        tags = "#journalling"
    return f"Log entry : {log_num}\n({today_str()})\n\n-- {thought}\n\n{tags}"

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ALLOWED_USER_IDS:
        logger.warning(f"Unauthorized /start attempt — {user_tag(update)}")
        return
    logger.info(f"/start — {user_tag(update)}")
    state = load_state()
    ctx.user_data.clear()
    await update.message.reply_text(
        f"Caption bot ready.\n\n"
        f"Current log entry: {state['log_num']}\n\n"
        f"Just send your thought and I'll ask for hashtags.\n\n"
        f"Commands:\n"
        f"/setlog 102 — set entry number\n"
        f"/current — see current entry number\n"
        f"/cancel — start over"
    )

async def current(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ALLOWED_USER_IDS:
        logger.warning(f"Unauthorized /current attempt — {user_tag(update)}")
        return
    state = load_state()
    logger.info(f"/current — {user_tag(update)} — log_num={state['log_num']}")
    await update.message.reply_text(f"Current log entry: {state['log_num']}")

async def set_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ALLOWED_USER_IDS:
        logger.warning(f"Unauthorized /setlog attempt — {user_tag(update)}")
        return
    try:
        num = int(ctx.args[0])
        state = load_state()
        old_num = state["log_num"]
        state["log_num"] = num
        save_state(state)
        logger.info(f"/setlog — {user_tag(update)} — changed {old_num} → {num}")
        await update.message.reply_text(f"Log entry number set to {num}.")
    except (IndexError, ValueError):
        logger.warning(f"/setlog failed — {user_tag(update)} — invalid args: {ctx.args}")
        await update.message.reply_text("Usage: /setlog 102")

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ALLOWED_USER_IDS:
        logger.warning(f"Unauthorized /cancel attempt — {user_tag(update)}")
        return
    step = ctx.user_data.get("step", "thought")
    logger.info(f"/cancel — {user_tag(update)} — was at step={step}")
    ctx.user_data.clear()
    await update.message.reply_text("Cancelled. Send your thought to start again.")

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ALLOWED_USER_IDS:
        logger.warning(f"Unauthorized message — {user_tag(update)} — text='{update.message.text[:50]}'")
        return

    text = update.message.text.strip()
    step = ctx.user_data.get("step", "thought")

    if step == "thought":
        logger.info(f"Thought received — {user_tag(update)} — thought='{text[:80]}'")
        ctx.user_data["thought"] = text
        ctx.user_data["step"] = "hashtags"
        await update.message.reply_text("Now send your hashtags.")

    elif step == "hashtags":
        thought = ctx.user_data.get("thought", "")
        hashtags = text

        try:
            state = load_state()
            caption = format_caption(state["log_num"], thought, hashtags)
            log_num_used = state["log_num"]
            state["log_num"] += 1
            save_state(state)
            ctx.user_data.clear()

            logger.info(f"Caption generated — {user_tag(update)} — entry={log_num_used} hashtags='{hashtags}' next_entry={state['log_num']}")
            logger.info(f"Caption content:\n{caption}")

            await update.message.reply_text(caption)

        except Exception as e:
            logger.error(f"Error generating caption — {user_tag(update)} — {e}", exc_info=True)
            await update.message.reply_text("Something went wrong. Try again or use /cancel.")

def main():
    logger.info("Starting caption bot...")
    logger.info(f"Allowed user IDs: {ALLOWED_USER_IDS}")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    async def post_init(application):
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook cleared. Polling started.")

    app.post_init = post_init

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("current", current))
    app.add_handler(CommandHandler("setlog", set_log))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
