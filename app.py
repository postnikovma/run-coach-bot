# -*- coding: utf-8 -*-

import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
import database as db
from training_plan import PLAN
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

# Настройка
logging.basicConfig(level=logging.INFO)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL") # Ссылка на наш Frontend

bot = Bot(token=TELEGRAM_TOKEN)
app = Flask(__name__)
CORS(app) # Разрешаем запросы с других доменов (нашего Mini App)

# --- Логика для старого бота (только запуск Mini App) ---
# Эта часть нужна, чтобы настроить вебхук и отвечать на команду /start

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Обрабатывает входящие обновления от Telegram."""
    update_data = request.get_json()
    message = update_data.get('message')

    if message and message.get('text') == '/start':
        chat_id = message['chat']['id']
        
        # Создаем кнопку, которая открывает наше веб-приложение
        keyboard = [
            [InlineKeyboardButton("🚀 Открыть приложение-тренер", web_app={'url': WEB_APP_URL})]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bot.send_message(
            chat_id=chat_id, 
            text="Привет! Нажми кнопку ниже, чтобы открыть твой персональный план тренировок.", 
            reply_markup=reply_markup
        )
    return 'ok', 200


# --- API для взаимодействия с Frontend ---

@app.route('/api/user_data')
def get_user_data():
    """Отдает все данные пользователя: прогресс, текущую неделю."""
    # TODO: Здесь нужна верификация tg.initData для безопасности
    user_id = request.args.get('user_id') # Временно для простоты
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
        
    db.add_user(user_id) # Добавляем, если новый
    
    user_data = {
        "current_week": db.get_user_current_week(user_id),
        "workouts": db.get_all_user_workouts(user_id)
    }
    return jsonify(user_data)

@app.route('/api/log_workout', methods=['POST'])
def log_workout():
    """Принимает и сохраняет данные о новой тренировке."""
    # TODO: Верификация tg.initData
    data = request.get_json()
    user_id = data.get('user_id') # Временно
    
    # Сохраняем тренировку
    db.log_workout({
        'user_id': user_id,
        'week': int(data['week']),
        'distance': float(data['distance']),
        'duration': int(data['duration']),
        'avg_hr': int(data['avg_hr']),
    })
    
    # Проверяем, не пора ли переходить на след. неделю
    logged_workouts_for_week = db.get_workouts_for_week(user_id, int(data['week']))
    if len(logged_workouts_for_week) >= 4:
         db.update_user_week(user_id, int(data['week']) + 1)
            
    return jsonify({"status": "success"})


if __name__ == "__main__":
    # Эта часть для локального теста, Render будет использовать Gunicorn
    app.run(debug=True, port=5001)
