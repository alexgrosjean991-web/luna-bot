import asyncio
import logging
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler as TGMessageHandler, filters

from config.settings import config
from src.database.models import db
from src.handlers.message_handler import MessageHandler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global message handler instance
msg_handler = None


async def start_command(update: Update, context) -> None:
    """Handle /start command"""
    user = update.effective_user
    
    # Get or create user
    db_user = await db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        language_code=user.language_code or "en"
    )
    
    is_french = db_user.get('language_code', 'en').startswith('fr')
    
    if is_french:
        welcome = f"""hey 👋

t'es qui toi? 

je suis luna btw"""
    else:
        welcome = f"""hey 👋

who r u?

im luna btw"""
    
    await update.message.reply_text(welcome)


async def profile_command(update: Update, context) -> None:
    """Handle /profile command"""
    user = update.effective_user
    
    db_user = await db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    user_id = db_user['id']
    luna_state = await db.get_luna_state(user_id)
    
    from src.services.memory_service import ConversionManager
    day = await ConversionManager.get_user_day(db, user_id)
    is_converted = await ConversionManager.is_converted(db, user_id)
    
    affection = luna_state.get('affection_level', 10)
    
    # Affection bar
    filled = int(affection / 10)
    bar = "❤️" * filled + "🤍" * (10 - filled)
    
    status = "chouchou 💕" if is_converted else "getting to know each other"
    
    is_french = db_user.get('language_code', 'en').startswith('fr')
    
    if is_french:
        profile_text = f"""💕 Moi & {db_user.get('first_name', 'toi')}

📅 On se parle depuis: {day} jours
💝 Ce que je ressens: {bar} {int(affection)}%
✨ Status: {status}

{'tu comptes beaucoup pour moi 🥺' if affection > 50 else 'on apprend à se connaître 💫'}"""
    else:
        profile_text = f"""💕 Me & {db_user.get('first_name', 'you')}

📅 Days talking: {day}
💝 How I feel: {bar} {int(affection)}%
✨ Status: {status}

{'you mean a lot to me 🥺' if affection > 50 else 'still getting to know each other 💫'}"""
    
    await update.message.reply_text(profile_text)


async def help_command(update: Update, context) -> None:
    """Handle /help command"""
    user = update.effective_user
    db_user = await db.get_or_create_user(telegram_id=user.id)
    
    is_french = db_user.get('language_code', 'en').startswith('fr')
    
    if is_french:
        help_text = """hey c'est quoi ces commandes mdr

/start - on recommence
/profile - nous voir
/help - t'es dessus là

sinon tu peux juste me parler normal 😊"""
    else:
        help_text = """lol ok here's what u can do

/start - start over
/profile - see us
/help - ur looking at it

or just talk to me like a normal person 😊"""
    
    await update.message.reply_text(help_text)


async def handle_message(update: Update, context) -> None:
    """Route messages to handler"""
    global msg_handler
    if msg_handler:
        await msg_handler.handle_message(update, context)


async def post_init(application: Application) -> None:
    """Setup after bot starts"""
    global msg_handler
    
    # Connect to database
    await db.connect()
    
    # Initialize message handler
    msg_handler = MessageHandler(db)
    
    # Set bot commands
    commands = [
        BotCommand("start", "Start chatting"),
        BotCommand("profile", "See our relationship"),
        BotCommand("help", "Get help"),
    ]
    await application.bot.set_my_commands(commands)
    
    logger.info("Luna is online! 💕")


async def shutdown(application: Application) -> None:
    """Cleanup on shutdown"""
    await db.close()
    logger.info("Luna going offline... 😴")


def main():
    """Start the bot"""
    
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    # Build application
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(shutdown)
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(TGMessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Run
    logger.info("Starting Luna...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
