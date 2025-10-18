# -*- coding: utf-8 -*-

import logging
import os
from datetime import time, date
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
import database as db
from training_plan import PLAN, DAY_NAMES_RU

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Этапы диалога
WEEK, DISTANCE, DURATION, AVG_HR = range(4)

# --- Вспомогательная функция для напоминаний ---

async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет ежедневное напоминание о тренировке."""
    job = context.job
    user_id = job.chat_id
    
    current_week = db.get_user_current_week(user_id)
    if current_week > 24:
        await context.bot.send_message(job.chat_id, text="Поздравляю! План тренировок полностью завершен! 🏆")
        job.schedule_removal()
        return

    today_weekday_index = date.today().weekday()
    
    try:
        training_day_info = PLAN[current_week - 1]['schedule'][today_weekday_index]
        day_name = DAY_NAMES_RU[today_weekday_index]
        
        message = (
            f"<b>Доброе утро! План на сегодня ({day_name}):</b>\n\n"
            f"📍 Неделя: {current_week}\n"
            f"🏋️‍♂️ Задание: {training_day_info}\n\n"
            "Не забудь записать результаты после тренировки с помощью команды /log. Хорошего дня!"
        )
        await context.bot.send_message(job.chat_id, text=message, parse_mode='HTML')
    except (IndexError, KeyError):
        logger.info(f"Для пользователя {user_id} на сегодня нет тренировки.")

# --- Функции-обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start."""
    user = update.effective_user
    user_id = user.id
    db.add_user(user_id)

    current_jobs = context.job_queue.get_jobs_by_name(f"reminder_{user_id}")
    for job in current_jobs:
        job.schedule_removal()

    context.job_queue.run_daily(
        send_daily_reminder,
        time=time(hour=8, minute=0),
        chat_id=user_id,
        name=f"reminder_{user_id}"
    )
    
    await update.message.reply_html(
        f"Привет, {user.mention_html()}! Я твой бот-тренер по бегу. 🏃‍♂️💨\n\n"
        "Я помогу тебе следовать 24-недельному плану подготовки к полумарафону.\n\n"
        "<b>Основные команды:</b>\n"
        "/plan - Показать план на сегодня\n"
        "/log - Записать тренировку\n"
        "/progress - Показать прогресс\n"
        "/help - Помощь\n\n"
        "Ежедневные напоминания в 8:00 утра настроены!"
    )
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Список команд:</b>\n\n"
        "/start - Перезапуск бота и приветствие.\n"
        "/plan - План на сегодня.\n"
        "/log - Запись результатов тренировки.\n"
        "/progress - Сводка по прогрессу.\n"
        "/help - Это сообщение.",
        parse_mode='HTML'
    )

async def get_plan_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current_week = db.get_user_current_week(user_id)
    
    if current_week > 24:
        await update.message.reply_text("Поздравляю! План тренировок полностью завершен! 🏆")
        return

    today_weekday_index = date.today().weekday()
    
    try:
        training_day_info = PLAN[current_week - 1]['schedule'][today_weekday_index]
        day_name = DAY_NAMES_RU[today_weekday_index]
        message = (
            f"<b>План на сегодня ({day_name}):</b>\n\n"
            f"📍 Неделя: {current_week}\n"
            f"🏋️‍♂️ Задание: {training_day_info}"
        )
        await update.message.reply_text(message, parse_mode='HTML')
    except (IndexError, KeyError):
        await update.message.reply_text("На сегодня тренировок не запланировано. Время отдохнуть!")

async def log_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("За какую неделю ты хочешь отчитаться? Введи число (например, 1).")
    return WEEK

async def get_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        week_number = int(update.message.text)
        if not 1 <= week_number <= 24: raise ValueError
        context.user_data['log_week'] = week_number
        await update.message.reply_text("Теперь введи дистанцию в километрах (например, 5.5).")
        return DISTANCE
    except ValueError:
        await update.message.reply_text("Введи корректный номер недели от 1 до 24.")
        return WEEK

async def get_distance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        distance = float(update.message.text.replace(',', '.'))
        context.user_data['log_distance'] = distance
        await update.message.reply_text("Сколько времени заняла тренировка в минутах? (например, 35).")
        return DURATION
    except ValueError:
        await update.message.reply_text("Введи дистанцию в виде числа (например, 10.2).")
        return DISTANCE

async def get_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        duration = int(update.message.text)
        context.user_data['log_duration'] = duration
        await update.message.reply_text("Какой был средний пульс (ЧСС)? (уд/мин).")
        return AVG_HR
    except ValueError:
        await update.message.reply_text("Введи время в минутах (целое число).")
        return DURATION

async def get_avg_hr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        avg_hr = int(update.message.text)
        user_id = update.effective_user.id
        log_data = {
            'user_id': user_id,
            'week': context.user_data['log_week'],
            'distance': context.user_data['log_distance'],
            'duration': context.user_data['log_duration'],
            'avg_hr': avg_hr,
        }
        db.log_workout(log_data)
        
        logged_workouts_for_week = db.get_workouts_for_week(user_id, log_data['week'])
        if len(logged_workouts_for_week) >= 4:
             db.update_user_week(user_id, log_data['week'] + 1)

        await update.message.reply_text(
            f"✅ Тренировка за {log_data['week']} неделю сохранена! Так держать!"
        )
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Введи средний пульс в виде целого числа.")
        return AVG_HR

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Запись тренировки отменена.")
    context.user_data.clear()
    return ConversationHandler.END

async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    all_workouts = db.get_all_user_workouts(user_id)
    current_week = db.get_user_current_week(user_id)

    if not all_workouts:
        await update.message.reply_text("Ты еще не записал ни одной тренировки. Начни с /log.")
        return

    total_distance = sum(w['distance'] for w in all_workouts)
    total_duration = sum(w['duration'] for w in all_workouts)
    
    weeks_completed = current_week - 1
    progress_percentage = (weeks_completed / 24) * 100
    progress_bar_length = 20
    filled_length = int(progress_bar_length * weeks_completed // 24)
    bar = '▓' * filled_length + '░' * (progress_bar_length - filled_length)

    message = (
        f"<b>Твой Прогресс:</b>\n\n"
        f"🎯 <b>Цель:</b> 21.1 км\n"
        f"🗓️ <b>Текущая неделя:</b> {current_week}/24\n\n"
        f"<b>Движение по плану:</b>\n"
        f"[{bar}] {progress_percentage:.1f}%\n\n"
        f"<b>Общая статистика:</b>\n"
        f"🏃‍♂️ Всего пробежал: {total_distance:.2f} км\n"
        f"⏱️ Общее время: {total_duration // 60} ч {total_duration % 60} мин\n\n"
        "Отличная работа! Продолжай в том же духе!"
    )
    await update.message.reply_text(message, parse_mode='HTML')

def main() -> None: # <-- Убрали async отсюда
    """Основная функция для запуска бота."""
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TELEGRAM_TOKEN:
        raise ValueError("Необходимо установить переменную окружения TELEGRAM_TOKEN")
        
    db.init_db()

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("log", log_start)],
        states={
            WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_week)],
            DISTANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_distance)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_duration)],
            AVG_HR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_avg_hr)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("plan", get_plan_today))
    application.add_handler(CommandHandler("progress", show_progress))
    application.add_handler(conv_handler)
    
    logger.info("Бот запущен...")
    application.run_polling() # <-- Убрали await отсюда

if __name__ == "__main__":
    main() # <-- Запускаем main() напрямую, без asyncio.run()

