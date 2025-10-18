# -*- coding: utf-8 -*-

import sqlite3
from contextlib import closing

DB_NAME = "run_coach.db"

def init_db():
    """Инициализирует базу данных и создает таблицы, если они не существуют."""
    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    current_week INTEGER NOT NULL DEFAULT 1,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Таблица для записи тренировок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workouts (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    week INTEGER NOT NULL,
                    distance REAL NOT NULL,
                    duration INTEGER NOT NULL, -- в минутах
                    avg_hr INTEGER NOT NULL,
                    log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
        conn.commit()

def add_user(user_id: int):
    """Добавляет нового пользователя в БД, если его там нет."""
    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

def get_user_current_week(user_id: int) -> int:
    """Возвращает номер текущей недели для пользователя."""
    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT current_week FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 1

def update_user_week(user_id: int, new_week: int):
    """Обновляет номер текущей недели для пользователя."""
    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("UPDATE users SET current_week = ? WHERE user_id = ?", (new_week, user_id))
        conn.commit()


def log_workout(data: dict):
    """Записывает данные о тренировке в БД."""
    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("""
                INSERT INTO workouts (user_id, week, distance, duration, avg_hr)
                VALUES (?, ?, ?, ?, ?)
            """, (data['user_id'], data['week'], data['distance'], data['duration'], data['avg_hr']))
        conn.commit()

def get_all_user_workouts(user_id: int) -> list:
    """Возвращает все записанные тренировки пользователя."""
    with closing(sqlite3.connect(DB_NAME)) as conn:
        conn.row_factory = sqlite3.Row # Возвращает результаты в виде словаря
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT * FROM workouts WHERE user_id = ? ORDER BY log_date ASC", (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

def get_workouts_for_week(user_id: int, week: int) -> list:
    """Возвращает тренировки пользователя за определенную неделю."""
    with closing(sqlite3.connect(DB_NAME)) as conn:
        conn.row_factory = sqlite3.Row
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT * FROM workouts WHERE user_id = ? AND week = ?", (user_id, week))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
