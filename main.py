import sqlite3
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from plyer import notification
import threading
import time


# === Работа с базой данных ===
class NoteDatabase:
    def __init__(self, db_name="notes_app.db"):
        self.connection = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self.create_tables()
        self.add_default_categories()
        self.add_category_column_if_not_exists()  # Добавление столбца category_id при необходимости

    def create_tables(self):
        # Создание таблицы пользователей
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'admin'))
        )
        """)
        # Создание таблицы категорий (если еще не существует)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """)
        # Создание таблицы заметок
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            reminder_time TEXT NOT NULL,
            notified INTEGER DEFAULT 0,
            user_id INTEGER NOT NULL,
            category_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
        """)
        self.connection.commit()

    def add_category_column_if_not_exists(self):
        # Проверим, есть ли уже столбец category_id в таблице notes
        self.cursor.execute("PRAGMA table_info(notes);")
        columns = self.cursor.fetchall()
        column_names = [column[1] for column in columns]
        if "category_id" not in column_names:
            self.cursor.execute("ALTER TABLE notes ADD COLUMN category_id INTEGER;")
            self.connection.commit()

    def add_default_categories(self):
        # Добавляем категории по умолчанию
        categories = ["Работа", "Личное", "Учеба"]
        for category in categories:
            try:
                self.cursor.execute("INSERT INTO categories (name) VALUES (?)", (category,))
                self.connection.commit()
            except sqlite3.IntegrityError:
                pass  # Игнорируем, если категория уже существует

    def add_user(self, username, password, role="user"):
        try:
            self.cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                                (username, password, role))
            self.connection.commit()
        except sqlite3.IntegrityError:
            raise ValueError("Пользователь с таким именем уже существует.")

    def get_user(self, username, password):
        self.cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        return self.cursor.fetchone()

    def get_all_users(self):
        self.cursor.execute("SELECT id, username, password, role FROM users")
        return self.cursor.fetchall()

    def add_note(self, user_id, title, content, reminder_time, category_id):
        self.cursor.execute("INSERT INTO notes (title, content, reminder_time, user_id, category_id) VALUES (?, ?, ?, ?, ?)",
                            (title, content, reminder_time, user_id, category_id))
        self.connection.commit()

    def get_notes(self, user_id=None):
        self.cursor.execute("SELECT notes.id, notes.title, notes.content, notes.reminder_time, categories.name FROM notes LEFT JOIN categories ON notes.category_id = categories.id WHERE user_id = ?", (user_id,))
        return self.cursor.fetchall()

    def update_note(self, note_id, title, content, reminder_time, category_id):
        self.cursor.execute("""
        UPDATE notes
        SET title = ?, content = ?, reminder_time = ?, category_id = ?
        WHERE id = ?
        """, (title, content, reminder_time, category_id, note_id))
        self.connection.commit()

    def delete_note_by_id(self, note_id):
        self.cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self.connection.commit()

    def mark_as_notified(self, note_id):
        self.cursor.execute("UPDATE notes SET notified = 1 WHERE id = ?", (note_id,))
        self.connection.commit()


# === Напоминания ===
def reminder_worker(database, stop_event):
    while not stop_event.is_set():
        current_time = datetime.now()
        notes = database.cursor.execute("SELECT * FROM notes WHERE notified = 0").fetchall()
        for note in notes:
            note_id, title, content, reminder_time, notified, _, _ = note
            try:
                reminder_dt = datetime.strptime(reminder_time, "%Y-%m-%d %H:%M")
                if reminder_dt <= current_time and not notified:
                    notification.notify(title=f"Напоминание: {title}", message=content, timeout=10)
                    database.mark_as_notified(note_id)
            except ValueError:
                continue
        time.sleep(60)


# === Интерфейс приложения ===
class NoteApp:
    def __init__(self, main_window):
        self.main_window = main_window
        self.database = NoteDatabase()

        # Создание администратора, если не существует
        try:
            self.database.add_user("admin", "admin", "admin")
        except ValueError:
            pass

        self.logged_in_user = None
        self.stop_event = threading.Event()
        self.reminder_thread = threading.Thread(target=reminder_worker, args=(self.database, self.stop_event), daemon=True)
        self.reminder_thread.start()

        self.show_login()

    def show_login(self):
        self.clear_window()

        tk.Label(self.main_window, text="Логин").pack()
        username_entry = tk.Entry(self.main_window)
        username_entry.pack()

        tk.Label(self.main_window, text="Пароль").pack()
        password_entry = tk.Entry(self.main_window, show="*")
        password_entry.pack()

        def login():
            username = username_entry.get()
            password = password_entry.get()
            user = self.database.get_user(username, password)
            if user:
                self.logged_in_user = user
                self.show_main_screen()
            else:
                messagebox.showerror("Ошибка", "Неверные логин или пароль!")

        tk.Button(self.main_window, text="Войти", command=login).pack()

        # Кнопка для перехода на экран регистрации
        tk.Button(self.main_window, text="Зарегистрироваться", command=self.register_user).pack()

    def register_user(self):
        self.clear_window()

        tk.Label(self.main_window, text="Регистрация").pack()
        username_entry = tk.Entry(self.main_window)
        username_entry.pack()
        tk.Label(self.main_window, text="Пароль").pack()
        password_entry = tk.Entry(self.main_window, show="*")
        password_entry.pack()

        def save_registration():
            username = username_entry.get()
            password = password_entry.get()
            if username and password:
                try:
                    self.database.add_user(username, password)
                    messagebox.showinfo("Успех", "Регистрация прошла успешно!")
                    self.show_login()  # Переход к экрану входа
                except ValueError:
                    messagebox.showerror("Ошибка", "Пользователь с таким именем уже существует.")
            else:
                messagebox.showerror("Ошибка", "Все поля должны быть заполнены.")

        tk.Button(self.main_window, text="Зарегистрироваться", command=save_registration).pack()
        tk.Button(self.main_window, text="Назад", command=self.show_login).pack()

    def show_main_screen(self):
        self.clear_window()

        tk.Label(self.main_window, text=f"Добро пожаловать, {self.logged_in_user[1]}!").pack()

        tk.Button(self.main_window, text="Создать заметку", command=self.add_note).pack()
        tk.Button(self.main_window, text="Посмотреть заметки", command=self.view_notes).pack()
        tk.Button(self.main_window, text="Редактировать заметку", command=self.edit_notes).pack()
        tk.Button(self.main_window, text="Удалить заметку", command=self.delete_notes).pack()

        if self.logged_in_user[3] == "admin":
            tk.Button(self.main_window, text="Посмотреть пользователей", command=self.view_users).pack()

        # Кнопка выхода
        tk.Button(self.main_window, text="Выход", command=self.main_window.quit).pack()

    def add_note(self):
        self.clear_window()

        tk.Label(self.main_window, text="Создать заметку").pack()
        title_label = tk.Label(self.main_window, text="Заголовок:")
        title_label.pack()
        title_entry = tk.Entry(self.main_window)
        title_entry.pack()

        content_label = tk.Label(self.main_window, text="Текст заметки:")
        content_label.pack()
        content_entry = tk.Entry(self.main_window)
        content_entry.pack()

        reminder_label = tk.Label(self.main_window, text="Время напоминания (формат: ГОД-МЕСЯЦ-ДЕНЬ ЧАСЫ:МИНУТЫ):")
        reminder_label.pack()
        reminder_entry = tk.Entry(self.main_window)
        reminder_entry.pack()

        category_label = tk.Label(self.main_window, text="Категория")
        category_label.pack()

        # Список категорий
        categories = self.database.cursor.execute("SELECT id, name FROM categories").fetchall()
        category_combobox = tk.StringVar(self.main_window)
        category_combobox.set(categories[0][1])  # Устанавливаем категорию по умолчанию
        category_menu = tk.OptionMenu(self.main_window, category_combobox, *[cat[1] for cat in categories])
        category_menu.pack()

        def save_note():
            title = title_entry.get()
            content = content_entry.get()
            reminder_time = reminder_entry.get()
            category_name = category_combobox.get()
            category_id = next(cat[0] for cat in categories if cat[1] == category_name)

            try:
                datetime.strptime(reminder_time, "%Y-%m-%d %H:%M")
                self.database.add_note(self.logged_in_user[0], title, content, reminder_time, category_id)
                messagebox.showinfo("Успех", "Заметка добавлена!")
                self.show_main_screen()
            except ValueError:
                messagebox.showerror("Ошибка", "Неверный формат даты и времени!")

        tk.Button(self.main_window, text="Сохранить", command=save_note).pack()

        # Кнопка назад
        tk.Button(self.main_window, text="Назад", command=self.show_main_screen).pack()

    def view_notes(self):
        self.clear_window()
        notes = self.database.get_notes(self.logged_in_user[0])
        tk.Label(self.main_window, text="Ваши заметки").pack()
        for note in notes:
            tk.Label(self.main_window, text=f"Заголовок: {note[1]}\nТекст: {note[2]}\nВремя: {note[3]}\nКатегория: {note[4]}").pack()
            tk.Label(self.main_window, text="-----------------------------").pack()

        # Кнопка назад
        tk.Button(self.main_window, text="Назад", command=self.show_main_screen).pack()

    def edit_notes(self):
        self.clear_window()
        notes = self.database.get_notes(self.logged_in_user[0])
        if notes:
            tk.Label(self.main_window, text="Редактировать заметки").pack()
            for note in notes:
                tk.Button(self.main_window, text=f"Редактировать {note[1]}",
                          command=lambda n=note: self.edit_note_window(n)).pack()
        else:
            tk.Label(self.main_window, text="Нет заметок для редактирования").pack()

        # Кнопка назад
        tk.Button(self.main_window, text="Назад", command=self.show_main_screen).pack()

    def edit_note_window(self, note):
        self.clear_window()

        tk.Label(self.main_window, text=f"Редактировать: {note[1]}").pack()
        title_entry = tk.Entry(self.main_window)
        title_entry.insert(0, note[1])
        title_entry.pack()

        content_entry = tk.Entry(self.main_window)
        content_entry.insert(0, note[2])
        content_entry.pack()

        reminder_entry = tk.Entry(self.main_window)
        reminder_entry.insert(0, note[3])
        reminder_entry.pack()

        category_label = tk.Label(self.main_window, text="Категория")
        category_label.pack()

        categories = self.database.cursor.execute("SELECT id, name FROM categories").fetchall()
        category_combobox = tk.StringVar(self.main_window)
        category_combobox.set(note[4])  # Устанавливаем текущую категорию
        category_menu = tk.OptionMenu(self.main_window, category_combobox, *[cat[1] for cat in categories])
        category_menu.pack()

        def save_edit():
            title = title_entry.get()
            content = content_entry.get()
            reminder_time = reminder_entry.get()
            category_name = category_combobox.get()
            category_id = next(cat[0] for cat in categories if cat[1] == category_name)

            try:
                datetime.strptime(reminder_time, "%Y-%m-%d %H:%M")
                self.database.update_note(note[0], title, content, reminder_time, category_id)
                messagebox.showinfo("Успех", "Заметка обновлена!")
                self.show_main_screen()
            except ValueError:
                messagebox.showerror("Ошибка", "Неверный формат даты и времени!")

        tk.Button(self.main_window, text="Сохранить изменения", command=save_edit).pack()

        # Кнопка назад
        tk.Button(self.main_window, text="Назад", command=self.show_main_screen).pack()

    def delete_notes(self):
        self.clear_window()
        notes = self.database.get_notes(self.logged_in_user[0])
        if notes:
            tk.Label(self.main_window, text="Удалить заметку").pack()
            for note in notes:
                tk.Button(self.main_window, text=f"Удалить {note[1]}",
                          command=lambda n=note: self.delete_note(n[0])).pack()
        else:
            tk.Label(self.main_window, text="Нет заметок для удаления").pack()

        # Кнопка назад
        tk.Button(self.main_window, text="Назад", command=self.show_main_screen).pack()

    def delete_note(self, note_id):
        self.database.delete_note_by_id(note_id)
        messagebox.showinfo("Успех", "Заметка удалена!")
        self.show_main_screen()

    def view_users(self):
        self.clear_window()
        users = self.database.get_all_users()
        tk.Label(self.main_window, text="Пользователи").pack()
        for user in users:
            tk.Label(self.main_window, text=f"Username: {user[1]}, Password: {user[2]}, Role: {user[3]}").pack()

        # Кнопка назад
        tk.Button(self.main_window, text="Назад", command=self.show_main_screen).pack()

    def clear_window(self):
        for widget in self.main_window.winfo_children():
            widget.destroy()


# === Запуск приложения ===
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Приложение для заметок")
    app = NoteApp(root)
    root.mainloop()
