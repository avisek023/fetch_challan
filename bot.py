"""Cloud-deployable Telegram bot for Parivahan eChallan lookup and PDF downloads.

Uses Python 3.11+, python-telegram-bot (v22+ async), Playwright (async), and a
lightweight aiohttp HTTP health-check server on port 8080 for Railway, Render,
and Koyeb container liveness probes.
"""

from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path
from typing import Final

from aiohttp import web
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from browser_manager import ParivahanBrowserSession, get_headless_flag

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("parivahan_bot")

# ConversationHandler states
WAITING_FOR_VEHICLE: Final[int] = 0
WAITING_FOR_CAPTCHA_LIST: Final[int] = 1
WAITING_FOR_CAPTCHA_PRINT: Final[int] = 2

# Callback query data constants
CB_REFRESH_CAPTCHA: Final[str] = "refresh_captcha"
CB_CANCEL_FLOW: Final[str] = "cancel_flow"

CONVERSATION_TIMEOUT_SECONDS: Final[int] = int(os.getenv("CONVERSATION_TIMEOUT", "180"))
VEHICLE_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{2}[0-9A-Z]{4,11}$")


def parse_allowed_user_ids(raw_ids: str | None) -> set[int]:
    """Parse comma-separated Telegram user IDs from ALLOWED_USER_IDS."""
    if not raw_ids:
        return set()
    parsed: set[int] = set()
    for token in raw_ids.split(","):
        token = token.strip()
        if token.lstrip("-").isdigit():
            parsed.add(int(token))
    return parsed


ALLOWED_USER_IDS: Final[set[int]] = parse_allowed_user_ids(os.getenv("ALLOWED_USER_IDS"))


def is_authorized(update: Update) -> bool:
    """Return True if the Telegram user is permitted to use this bot."""
    user = update.effective_user
    if user is None:
        return False
    if not ALLOWED_USER_IDS:
        logger.warning("ALLOWED_USER_IDS is empty; rejecting user %s for safety.", user.id)
        return False
    return user.id in ALLOWED_USER_IDS


def captcha_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard attached to every CAPTCHA prompt."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh CAPTCHA", callback_data=CB_REFRESH_CAPTCHA),
                InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL_FLOW),
            ]
        ]
    )


def normalize_vehicle_number(raw_text: str) -> str:
    """Strip spaces/hyphens and uppercase a vehicle registration string."""
    return re.sub(r"[\s\-]+", "", raw_text).upper()


async def cleanup_user_session(context: ContextTypes.DEFAULT_TYPE, user_id: int | None = None) -> None:
    """Strictly close any active Playwright session and purge conversation state."""
    session: ParivahanBrowserSession | None = context.user_data.pop("browser_session", None)
    active_sessions: dict[int, ParivahanBrowserSession] = context.bot_data.setdefault("active_sessions", {})

    if user_id is not None:
        tracked = active_sessions.pop(user_id, None)
        if session is None:
            session = tracked

    if session is not None:
        try:
            await session.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error closing browser session for user %s: %s", user_id, exc)

    # Clean up any leftover temp PDFs recorded in user_data
    temp_files: list[str] = context.user_data.pop("temp_files", [])
    for file_path in temp_files:
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError:
            pass

    for key in ("vehicle_number", "challan_queue", "challan_index", "challan_total"):
        context.user_data.pop(key, None)


# =============================================================================
# Stage 1 — Entry & Vehicle Lookup (WAITING_FOR_VEHICLE)
# =============================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /start and /check commands."""
    if not is_authorized(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ Unauthorized. Your Telegram user ID is not listed in ALLOWED_USER_IDS."
            )
        return ConversationHandler.END

    user_id = update.effective_user.id if update.effective_user else None
    await cleanup_user_session(context, user_id)

    # Allow optional direct invocation: /check OD02AB1234
    if context.args:
        raw_vehicle = "".join(context.args)
        return await _begin_vehicle_lookup(update, context, raw_vehicle)

    assert update.effective_message is not None
    await update.effective_message.reply_text(
        "🚗 *Parivahan eChallan Assistant*\n\n"
        "Send a vehicle registration number (for example, `OD02AB1234`) to fetch "
        "pending challans and download their PDF receipts.\n\n"
        "Use /cancel at any time to close the browser session.",
        parse_mode="Markdown",
    )
    return WAITING_FOR_VEHICLE


async def receive_vehicle_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate the vehicle number and launch Stage 1 browser lookup."""
    if not is_authorized(update):
        return ConversationHandler.END

    assert update.effective_message is not None
    raw_text = (update.effective_message.text or "").strip()
    return await _begin_vehicle_lookup(update, context, raw_text)


async def _begin_vehicle_lookup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    raw_vehicle: str,
) -> int:
    assert update.effective_message is not None
    assert update.effective_chat is not None
    user_id = update.effective_user.id if update.effective_user else 0

    vehicle_no = normalize_vehicle_number(raw_vehicle)
    if not VEHICLE_REGEX.match(vehicle_no):
        await update.effective_message.reply_text(
            "⚠️ Please enter a valid vehicle registration number (e.g. `OD02AB1234`).",
            parse_mode="Markdown",
        )
        return WAITING_FOR_VEHICLE

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    status_msg = await update.effective_message.reply_text(
        f"🌐 Opening Parivahan portal for `{vehicle_no}`...",
        parse_mode="Markdown",
    )

    session = ParivahanBrowserSession(
        headless=get_headless_flag(),
        proxy_url=os.getenv("PROXY_URL"),
    )
    context.user_data["browser_session"] = session
    context.user_data["vehicle_number"] = vehicle_no
    context.bot_data.setdefault("active_sessions", {})[user_id] = session

    try:
        captcha_png = await session.open_vehicle_lookup(vehicle_no)
        await status_msg.delete()
        await update.effective_message.reply_photo(
            photo=io.BytesIO(captcha_png),
            caption=(
                f"🔐 Vehicle: `{vehicle_no}`\n"
                "Reply with the CAPTCHA characters shown above."
            ),
            parse_mode="Markdown",
            reply_markup=captcha_keyboard(),
        )
        return WAITING_FOR_CAPTCHA_LIST
    except Exception as exc:  # noqa: BLE001
        logger.exception("Stage 1 lookup failed for %s", vehicle_no)
        await cleanup_user_session(context, user_id)
        await status_msg.edit_text(
            f"❌ Failed to load Parivahan portal for `{vehicle_no}`.\n"
            f"Reason: `{exc}`\n\nSend /start to try again.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END


# =============================================================================
# Stage 2 — Pending Challan Screenshot & Queue Extraction
# =============================================================================
async def handle_captcha_list_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Submit Stage 2 CAPTCHA, send full-page table screenshot, and kick off Stage 3."""
    if not is_authorized(update):
        return ConversationHandler.END

    assert update.effective_message is not None
    assert update.effective_chat is not None
    user_id = update.effective_user.id if update.effective_user else 0

    session: ParivahanBrowserSession | None = context.user_data.get("browser_session")
    vehicle_no: str = context.user_data.get("vehicle_number", "UNKNOWN")
    if session is None:
        await update.effective_message.reply_text(
            "⚠️ Browser session expired. Send /start to begin a new lookup."
        )
        return ConversationHandler.END

    captcha_text = (update.effective_message.text or "").strip()
    if not captcha_text:
        await update.effective_message.reply_text("Please reply with the CAPTCHA text.")
        return WAITING_FOR_CAPTCHA_LIST

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
    wait_msg = await update.effective_message.reply_text("⏳ Submitting CAPTCHA and fetching challan details...")

    try:
        result = await session.submit_vehicle_captcha(captcha_text)

        if result.status == "invalid_captcha":
            await wait_msg.delete()
            assert result.captcha_bytes is not None
            await update.effective_message.reply_photo(
                photo=io.BytesIO(result.captcha_bytes),
                caption=(
                    f"⚠️ Invalid CAPTCHA for `{vehicle_no}`. Please try again with the new image above."
                ),
                parse_mode="Markdown",
                reply_markup=captcha_keyboard(),
            )
            return WAITING_FOR_CAPTCHA_LIST

        if result.status == "no_challans":
            await wait_msg.delete()
            if result.screenshot_bytes:
                await update.effective_message.reply_photo(
                    photo=io.BytesIO(result.screenshot_bytes),
                    caption=f"✅ `{vehicle_no}`: No pending challans found.",
                    parse_mode="Markdown",
                )
            else:
                await update.effective_message.reply_text(
                    f"✅ No pending challans found for `{vehicle_no}`.",
                    parse_mode="Markdown",
                )
            await cleanup_user_session(context, user_id)
            return ConversationHandler.END

        if result.status == "error":
            await wait_msg.edit_text(
                f"❌ Portal returned an error for `{vehicle_no}`:\n`{result.message}`",
                parse_mode="Markdown",
            )
            await cleanup_user_session(context, user_id)
            return ConversationHandler.END

        # Success: Send full-page screenshot of the pending challans table
        await wait_msg.delete()
        if result.screenshot_bytes:
            await update.effective_message.reply_photo(
                photo=io.BytesIO(result.screenshot_bytes),
                caption=(
                    f"📋 Pending Challans for `{vehicle_no}`\n"
                    f"Found *{len(result.pending_challans)}* pending challan(s). "
                    "Starting sequential PDF receipt downloads..."
                ),
                parse_mode="Markdown",
            )

        # Populate queue for Stage 3
        context.user_data["challan_queue"] = list(result.pending_challans)
        context.user_data["challan_index"] = 0
        context.user_data["challan_total"] = len(result.pending_challans)

        return await _prompt_next_challan_print(update, context)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Stage 2 failed for vehicle %s", vehicle_no)
        await cleanup_user_session(context, user_id)
        try:
            await wait_msg.edit_text(f"❌ Error while fetching challans: `{exc}`", parse_mode="Markdown")
        except Exception:  # noqa: BLE001
            await update.effective_message.reply_text(f"❌ Error while fetching challans: {exc}")
        return ConversationHandler.END


# =============================================================================
# Stage 3 — Sequential PDF Download Loop (WAITING_FOR_CAPTCHA_PRINT)
# =============================================================================
async def _prompt_next_challan_print(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Open /index/challan-print for the next queued challan and send its CAPTCHA."""
    assert update.effective_message is not None
    assert update.effective_chat is not None
    user_id = update.effective_user.id if update.effective_user else 0

    session: ParivahanBrowserSession | None = context.user_data.get("browser_session")
    queue: list[str] = context.user_data.get("challan_queue", [])
    index: int = context.user_data.get("challan_index", 0)
    total: int = context.user_data.get("challan_total", len(queue))

    if session is None:
        await update.effective_message.reply_text("⚠️ Browser session expired. Send /start to begin again.")
        return ConversationHandler.END

    if index >= len(queue):
        vehicle_no = context.user_data.get("vehicle_number", "")
        await update.effective_message.reply_text(
            f"✅ Completed! All {total} pending challan PDF(s) for `{vehicle_no}` have been sent.",
            parse_mode="Markdown",
        )
        await cleanup_user_session(context, user_id)
        return ConversationHandler.END

    challan_no = queue[index]
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)

    try:
        captcha_png = await session.open_challan_print(challan_no)
        await update.effective_message.reply_photo(
            photo=io.BytesIO(captcha_png),
            caption=f"Challan [{index + 1}/{total}]: {challan_no} — Reply with CAPTCHA to download PDF",
            reply_markup=captcha_keyboard(),
        )
        return WAITING_FOR_CAPTCHA_PRINT
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load print page for challan %s", challan_no)
        await update.effective_message.reply_text(
            f"⚠️ Could not load print page for Challan [{index + 1}/{total}] `{challan_no}`: `{exc}`\n"
            "Moving to the next challan...",
            parse_mode="Markdown",
        )
        context.user_data["challan_index"] = index + 1
        return await _prompt_next_challan_print(update, context)


async def handle_captcha_print_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Submit Stage 3 CAPTCHA, upload /tmp/<CHALLAN_NO>.pdf, delete temp file, advance queue."""
    if not is_authorized(update):
        return ConversationHandler.END

    assert update.effective_message is not None
    assert update.effective_chat is not None
    user_id = update.effective_user.id if update.effective_user else 0

    session: ParivahanBrowserSession | None = context.user_data.get("browser_session")
    queue: list[str] = context.user_data.get("challan_queue", [])
    index: int = context.user_data.get("challan_index", 0)
    total: int = context.user_data.get("challan_total", len(queue))

    if session is None or index >= len(queue):
        await cleanup_user_session(context, user_id)
        await update.effective_message.reply_text("⚠️ Session state reset. Send /start to begin a new lookup.")
        return ConversationHandler.END

    challan_no = queue[index]
    captcha_text = (update.effective_message.text or "").strip()
    if not captcha_text:
        await update.effective_message.reply_text("Please reply with the CAPTCHA characters.")
        return WAITING_FOR_CAPTCHA_PRINT

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)
    progress_msg = await update.effective_message.reply_text(
        f"⏳ Generating PDF for Challan [{index + 1}/{total}]: `{challan_no}`...",
        parse_mode="Markdown",
    )

    pdf_path: Path | None = None
    try:
        result = await session.submit_print_captcha_and_download(challan_no, captcha_text)

        if result.status == "invalid_captcha":
            await progress_msg.delete()
            assert result.captcha_bytes is not None
            await update.effective_message.reply_photo(
                photo=io.BytesIO(result.captcha_bytes),
                caption=(
                    f"⚠️ Invalid CAPTCHA.\n"
                    f"Challan [{index + 1}/{total}]: {challan_no} — Reply with CAPTCHA to download PDF"
                ),
                reply_markup=captcha_keyboard(),
            )
            return WAITING_FOR_CAPTCHA_PRINT

        if result.status == "ok" and result.pdf_path is not None:
            pdf_path = result.pdf_path
            context.user_data.setdefault("temp_files", []).append(str(pdf_path))
            await progress_msg.delete()
            with pdf_path.open("rb") as pdf_file:
                await update.effective_message.reply_document(
                    document=pdf_file,
                    filename=f"{challan_no}.pdf",
                    caption=f"📄 Challan [{index + 1}/{total}]: {challan_no}",
                )
        else:
            await progress_msg.edit_text(
                f"⚠️ Skipped Challan [{index + 1}/{total}] `{challan_no}`: `{result.message}`",
                parse_mode="Markdown",
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("PDF capture failed for challan %s", challan_no)
        try:
            await progress_msg.edit_text(
                f"⚠️ Failed to download PDF for `{challan_no}`: `{exc}`",
                parse_mode="Markdown",
            )
        except Exception:  # noqa: BLE001
            pass
    finally:
        # Always remove temporary PDF file immediately after Telegram upload
        if pdf_path is not None:
            try:
                pdf_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to delete temp PDF %s: %s", pdf_path, exc)

    context.user_data["challan_index"] = index + 1
    return await _prompt_next_challan_print(update, context)


# =============================================================================
# Inline Button Handlers (Refresh CAPTCHA & Cancel) + Timeout Cleanup
# =============================================================================
async def handle_refresh_captcha_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Refresh CAPTCHA during Stage 1/2 without resetting the Vehicle Number form."""
    query = update.callback_query
    assert query is not None
    await query.answer("Refreshing CAPTCHA...")

    if not is_authorized(update):
        return ConversationHandler.END

    session: ParivahanBrowserSession | None = context.user_data.get("browser_session")
    vehicle_no: str = context.user_data.get("vehicle_number", "")
    user_id = update.effective_user.id if update.effective_user else 0

    if session is None:
        await query.message.reply_text("⚠️ Session expired. Send /start to begin again.")  # type: ignore[union-attr]
        return ConversationHandler.END

    try:
        fresh_png = await session.refresh_captcha(stage="list")
        await query.message.reply_photo(  # type: ignore[union-attr]
            photo=io.BytesIO(fresh_png),
            caption=f"🔄 Refreshed CAPTCHA for `{vehicle_no}`. Reply with the new characters.",
            parse_mode="Markdown",
            reply_markup=captcha_keyboard(),
        )
        return WAITING_FOR_CAPTCHA_LIST
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to refresh Stage 1 CAPTCHA")
        await cleanup_user_session(context, user_id)
        await query.message.reply_text(f"❌ Could not refresh CAPTCHA: {exc}. Send /start to retry.")  # type: ignore[union-attr]
        return ConversationHandler.END


async def handle_refresh_captcha_print(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Refresh CAPTCHA during Stage 3 without resetting the current Challan Number."""
    query = update.callback_query
    assert query is not None
    await query.answer("Refreshing CAPTCHA...")

    if not is_authorized(update):
        return ConversationHandler.END

    session: ParivahanBrowserSession | None = context.user_data.get("browser_session")
    queue: list[str] = context.user_data.get("challan_queue", [])
    index: int = context.user_data.get("challan_index", 0)
    total: int = context.user_data.get("challan_total", len(queue))
    user_id = update.effective_user.id if update.effective_user else 0

    if session is None or index >= len(queue):
        await cleanup_user_session(context, user_id)
        await query.message.reply_text("⚠️ Session expired. Send /start to begin again.")  # type: ignore[union-attr]
        return ConversationHandler.END

    challan_no = queue[index]
    try:
        fresh_png = await session.refresh_captcha(stage="print")
        await query.message.reply_photo(  # type: ignore[union-attr]
            photo=io.BytesIO(fresh_png),
            caption=f"Challan [{index + 1}/{total}]: {challan_no} — Reply with CAPTCHA to download PDF",
            reply_markup=captcha_keyboard(),
        )
        return WAITING_FOR_CAPTCHA_PRINT
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to refresh Stage 3 CAPTCHA")
        await cleanup_user_session(context, user_id)
        await query.message.reply_text(f"❌ Could not refresh CAPTCHA: {exc}. Send /start to retry.")  # type: ignore[union-attr]
        return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel command and strictly close the Playwright session."""
    user_id = update.effective_user.id if update.effective_user else None
    await cleanup_user_session(context, user_id)
    if update.effective_message:
        await update.effective_message.reply_text("❌ Operation cancelled and browser session closed.")
    return ConversationHandler.END


async def cancel_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle [❌ Cancel] inline button click and close the Playwright session."""
    query = update.callback_query
    assert query is not None
    await query.answer("Cancelling session...")
    user_id = update.effective_user.id if update.effective_user else None
    await cleanup_user_session(context, user_id)
    if query.message:
        await query.message.reply_text("❌ Operation cancelled and browser session closed.")
    return ConversationHandler.END


async def conversation_timeout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Automatically close browser resources after 180 seconds of inactivity."""
    user_id = update.effective_user.id if update.effective_user else None
    await cleanup_user_session(context, user_id)
    if update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    f"⏱️ Session timed out after {CONVERSATION_TIMEOUT_SECONDS} seconds of inactivity. "
                    "Browser session closed. Send /start to begin a new lookup."
                ),
            )
        except Exception:  # noqa: BLE001
            pass
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global exception logger ensuring sessions do not leak on unexpected errors."""
    logger.exception("Unhandled exception while processing update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_user:
        await cleanup_user_session(context, update.effective_user.id)


# =============================================================================
# Lightweight HTTP Health-Check Server (Port 8080 via aiohttp)
# =============================================================================
async def health_endpoint(_request: web.Request) -> web.Response:
    """Respond 200 OK to cloud platform liveness/readiness probes."""
    return web.json_response(
        {
            "status": "ok",
            "service": "parivahan-echallan-bot",
        }
    )


async def post_init(application: Application) -> None:
    """Start the background aiohttp health-check server inside PTB's event loop."""
    port = int(os.getenv("PORT", "8080"))
    web_app = web.Application()
    web_app.router.add_get("/", health_endpoint)
    web_app.router.add_get("/health", health_endpoint)
    web_app.router.add_get("/healthz", health_endpoint)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    application.bot_data["health_runner"] = runner
    application.bot_data["active_sessions"] = {}
    logger.info("Health-check HTTP server listening on http://0.0.0.0:%d/health", port)


async def post_shutdown(application: Application) -> None:
    """Gracefully close all active Chromium browsers and stop the health server."""
    active_sessions: dict[int, ParivahanBrowserSession] = application.bot_data.get("active_sessions", {})
    for user_id, session in list(active_sessions.items()):
        try:
            await session.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed closing session for user %s on shutdown: %s", user_id, exc)
    active_sessions.clear()

    runner: web.AppRunner | None = application.bot_data.get("health_runner")
    if runner is not None:
        await runner.cleanup()
        logger.info("Health-check HTTP server stopped.")


def build_application() -> Application:
    """Assemble the python-telegram-bot v22+ async Application."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required.")

    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CommandHandler("check", start_command),
        ],
        states={
            WAITING_FOR_VEHICLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_vehicle_number),
            ],
            WAITING_FOR_CAPTCHA_LIST: [
                CallbackQueryHandler(handle_refresh_captcha_list, pattern=f"^{CB_REFRESH_CAPTCHA}$"),
                CallbackQueryHandler(cancel_button_callback, pattern=f"^{CB_CANCEL_FLOW}$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_captcha_list_reply),
            ],
            WAITING_FOR_CAPTCHA_PRINT: [
                CallbackQueryHandler(handle_refresh_captcha_print, pattern=f"^{CB_REFRESH_CAPTCHA}$"),
                CallbackQueryHandler(cancel_button_callback, pattern=f"^{CB_CANCEL_FLOW}$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_captcha_print_reply),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, conversation_timeout_handler),
                CallbackQueryHandler(conversation_timeout_handler),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_button_callback, pattern=f"^{CB_CANCEL_FLOW}$"),
        ],
        conversation_timeout=CONVERSATION_TIMEOUT_SECONDS,
        allow_reentry=True,
    )

    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    """Start the Telegram bot with long polling and the background health server."""
    application = build_application()
    logger.info("Starting Parivahan eChallan Telegram bot (timeout=%ds)...", CONVERSATION_TIMEOUT_SECONDS)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
