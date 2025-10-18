# -*- coding: utf-8 -*-

import logging
import os
from datetime import time, date, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import database as db
from training_plan import PLAN, DAY_NAMES_RU

# Настройка логирования для отладки
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Этапы диалога для записи тренировки
WEEK, DISTANCE, DURATION, AVG_HR = range(4)

# --- Функции-обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start. Приветствует пользователя и настраивает напоминания."""
    user = update.effective_user
    user_id = user.id
    db.add_user(user_id) # Добавляем пользователя в БД, если его там нет

    await update.message.reply_html(
        f"Привет, {user.mention_html()}! Я твой бот-тренер по бегу. 🏃‍♂️💨\n\n"
        "Я помогу тебе следовать 24-недельному плану подготовки к полумарафону.\n\n"
        "<b>Основные команды:</b>\n"
        "/plan - Показать план тренировки на сегодня\n"
        "/log - Записать данные о прошедшей тренировке\n"
        "/progress - Показать твой общий прогресс\n"
        "/help - Помощь по командам\n\n"
        "Каждый день в 8:00 я буду присылать тебе план на сегодня. Удачи!",
    )
    
    # Настройка ежедневного напоминания для этого пользователя
    context.job_queue.run_daily(
        send_daily_reminder,
        time=time(hour=8, minute=0), # 8:00 по времени сервера
        chat_id=user_id,
        name=f"reminder_{user_id}"
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет справочное сообщение."""
    await update.message.reply_text(
        "<b>Список доступных команд:</b>\n\n"
        "/start - Перезапустить бота и увидеть приветствие.\n"
        "/plan - Узнать, какая тренировка запланирована на сегодня.\n"
        "/log - Начать процесс записи результатов последней тренировки.\n"
        "/progress - Показать сводку по вашему прогрессу: общая дистанция и сравнение с планом.\n"
        "/help - Показать это сообщение.",
        parse_mode='HTML'
    )

async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Функция, отправляющая ежедневное напоминание о тренировке."""
    job = context.job
    user_id = job.chat_id
    
    current_week = db.get_user_current_week(user_id)
    if current_week > 24:
        await context.bot.send_message(job.chat_id, text="Поздравляю! План тренировок полностью завершен! 🏆")
        return

    today_weekday_index = date.today().weekday() # Понедельник = 0, Вторник = 1, ...
    
    # Находим тренировку на сегодня
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
        await context.bot.send_message(job.chat_id, text="На сегодня тренировок не запланировано. Время отдохнуть!")


async def get_plan_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет пользователю план на текущий день."""
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


# --- Логика диалога для записи тренировки (/log) ---

async def log_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог для записи тренировки."""
    await update.message.reply_text(
        "Отлично! Давай запишем твою тренировку.\n"
        "За какую неделю ты хочешь отчитаться? Введи число (например, 1)."
    )
    return WEEK

async def get_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает номер недели и запрашивает дистанцию."""
    try:
        week_number = int(update.message.text)
        if not 1 <= week_number <= 24:
            raise ValueError
        context.user_data['log_week'] = week_number
        await update.message.reply_text("Понял. Теперь введи дистанцию в километрах (например, 5.5).")
        return DISTANCE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректный номер недели от 1 до 24.")
        return WEEK

async def get_distance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает дистанцию и запрашивает время."""
    try:
        distance = float(update.message.text.replace(',', '.'))
        context.user_data['log_distance'] = distance
        await update.message.reply_text("Отлично! Сколько времени заняла тренировка в минутах? (например, 35).")
        return DURATION
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи дистанцию в виде числа (например, 10.2).")
        return DISTANCE

async def get_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает время и запрашивает средний ЧСС."""
    try:
        duration = int(update.message.text)
        context.user_data['log_duration'] = duration
        await update.message.reply_text("Супер. И последнее: какой был средний пульс (ЧСС)? (уд/мин).")
        return AVG_HR
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи время тренировки в минутах (целое число).")
        return DURATION

async def get_avg_hr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает ЧСС, сохраняет тренировку в БД и завершает диалог."""
    try:
        avg_hr = int(update.message.text)
        
        # Собираем все данные
        user_id = update.effective_user.id
        log_data = {
            'user_id': user_id,
            'week': context.user_data['log_week'],
            'distance': context.user_data['log_distance'],
            'duration': context.user_data['log_duration'],
            'avg_hr': avg_hr,
        }

        # Сохраняем в базу данных
        db.log_workout(log_data)
        
        # Обновляем текущую неделю пользователя, если он закрыл предыдущую
        logged_workouts_for_week = db.get_workouts_for_week(user_id, log_data['week'])
        if len(logged_workouts_for_week) >= 4: # 4 беговых тренировки в неделю по плану
             db.update_user_week(user_id, log_data['week'] + 1)


        await update.message.reply_text(
            f"✅ Тренировка за {log_data['week']} неделю успешно сохранена!\n"
            "Так держать! Чтобы посмотреть общий прогресс, используй команду /progress."
        )
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи средний пульс в виде целого числа.")
        return AVG_HR

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий диалог записи тренировки."""
    await update.message.reply_text(
        "Запись тренировки отменена.", reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END


# --- Логика отображения прогресса (/progress) ---

async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает статистику и прогресс пользователя."""
    user_id = update.effective_user.id
    all_workouts = db.get_all_user_workouts(user_id)
    current_week = db.get_user_current_week(user_id)

    if not all_workouts:
        await update.message.reply_text("Ты еще не записал ни одной тренировки. Начни с команды /log.")
        return

    total_distance = sum(w['distance'] for w in all_workouts)
    total_duration = sum(w['duration'] for w in all_workouts)
    
    # Прогресс по плану
    weeks_completed = current_week - 1
    progress_percentage = (weeks_completed / 24) * 100
    progress_bar_length = 20
    filled_length = int(progress_bar_length * weeks_completed // 24)
    bar = '▓' * filled_length + '░' * (progress_bar_length - filled_length)

    message = (
        f"<b>Твой Прогресс на Пути к Полумарафону:</b>\n\n"
        f"🎯 <b>Цель:</b> 21.1 км\n"
        f"🗓️ <b>Текущая неделя:</b> {current_week}/24\n\n"
        f"<b>Движение по плану:</b>\n"
        f"[{bar}] {progress_percentage:.1f}%\n\n"
        f"<b>Общая статистика:</b>\n"
        f"🏃‍♂️ Всего пробежал: {total_distance:.2f} км\n"
        f"⏱️ Общее время в движении: {total_duration // 60} ч {total_duration % 60} мин\n\n"
        "Отличная работа! Продолжай в том же духе!"
    )
    
    await update.message.reply_text(message, parse_mode='HTML')


def main() -> None:
    """Основная функция для запуска бота."""
    # Получаем токен из переменных окружения
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TELEGRAM_TOKEN:
        raise ValueError("Необходимо установить переменную окружения TELEGRAM_TOKEN")
        
    # Инициализация базы данных
    db.init_db()

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Настройка планировщика для напоминаний
    scheduler = AsyncIOScheduler()
    scheduler.start()
    
    # Настройка ConversationHandler для команды /log
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

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("plan", get_plan_today))
    application.add_handler(CommandHandler("progress", show_progress))
    application.add_handler(conv_handler)
    
    # Передаем job_queue в контекст команд, чтобы иметь к нему доступ
    application.job_queue.start()

    logger.info("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()
