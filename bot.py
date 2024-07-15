import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import datetime

API_TOKEN = '6930087476:AAGsRBj2uddidMQhsnWN7hOUt41a6xsU17g'
ADMIN_ID = '6620097375'

# Bot va Dispatcher yaratamiz
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Ma'lumotlar bazasiga ulanamiz
conn = sqlite3.connect('appointments.db')
cursor = conn.cursor()

# Mavjud jadvalidan olib tashlaymiz va to'g'ri tuzilgan yangi jadval yaratamiz
cursor.execute('DROP TABLE IF EXISTS appointments')
cursor.execute('''
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    surname TEXT NOT NULL,
    phone TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL
)
''')
conn.commit()

# Holatlar
class AppointmentForm(StatesGroup):
    name = State()
    surname = State()
    phone = State()
    appointment_date = State()
    appointment_time = State()

# /queue buyrug'i uchun klaviatura yaratamiz
queue_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
queue_keyboard.add(KeyboardButton('Qatnashish uchun ro\'yxatdan o\'tish'))

# Admin panel klaviaturasi
admin_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
admin_keyboard.add(KeyboardButton('/statistics'), KeyboardButton('/list'))

# Inline klaviatura
inline_kb_panel = InlineKeyboardMarkup(row_width=1)
inline_kb_panel.add(InlineKeyboardButton("Men keldim", callback_data="i_came"))

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    if str(message.from_user.id) == ADMIN_ID:
        await message.reply("Xush kelibsiz, admin!", reply_markup=admin_keyboard)
    else:
        await message.reply("Salom, berber do'koniga xush kelibsiz! Ro'yxatdan o'tish uchun pastdagi tugmani bosing.", reply_markup=queue_keyboard)

@dp.message_handler(lambda message: message.text == 'Qatnashish uchun ro\'yxatdan o\'tish')
async def queue_request(message: types.Message):
    await AppointmentForm.name.set()
    await message.reply("Ismingizni kiriting:", reply_markup=ReplyKeyboardRemove())

@dp.message_handler(state=AppointmentForm.name)
async def process_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['name'] = message.text
    await AppointmentForm.next()
    await message.reply("Familiyangizni kiriting:")

@dp.message_handler(state=AppointmentForm.surname)
async def process_surname(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['surname'] = message.text
    await AppointmentForm.next()
    await message.reply("Telefon raqamingizni kiriting:")

@dp.message_handler(state=AppointmentForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['phone'] = message.text
    await AppointmentForm.next()
    await message.reply("Tashrif sanangizni kiriting (kiritish formati: kunOyl, masalan, 24Iyul):")

@dp.message_handler(state=AppointmentForm.appointment_date)
async def process_appointment_date(message: types.Message, state: FSMContext):
    appointment_date = message.text
    try:
        appointment_date = datetime.datetime.strptime(appointment_date, '%d%b').date()
    except ValueError:
        await message.reply("Noto'g'ri san'at formati. Iltimos, qayta urinib ko'ring.")
        return

    async with state.proxy() as data:
        data['appointment_date'] = appointment_date

    await AppointmentForm.next()
    await message.reply("Tashrif vaqtingizni kiriting (vaqtni formati: Soat:Daqiqa, masalan, 22:00):")

@dp.message_handler(state=AppointmentForm.appointment_time)
async def process_appointment_time(message: types.Message, state: FSMContext):
    appointment_time = message.text
    try:
        appointment_time = datetime.datetime.strptime(appointment_time, '%H:%M').time()
    except ValueError:
        await message.reply("Noto'g'ri vaqtni formati. Iltimos, qayta urinib ko'ring.")
        return

    async with state.proxy() as data:
        data['appointment_time'] = appointment_time

        appointment_datetime = datetime.datetime.combine(data['appointment_date'], appointment_time)

        cursor.execute('SELECT * FROM appointments WHERE appointment_date = ? AND appointment_time = ?', 
                       (data['appointment_date'].strftime('%Y-%m-%d'), appointment_time.strftime('%H:%M')))
        if cursor.fetchone():
            await message.reply("Bu vaqt uchun ro'yxat mavjud. Iltimos, boshqa vaqtni tanlang.")
        else:
            cursor.execute('INSERT INTO appointments (name, surname, phone, appointment_date, appointment_time) VALUES (?, ?, ?, ?, ?)',
                           (data['name'], data['surname'], data['phone'], data['appointment_date'].strftime('%Y-%m-%d'), appointment_time.strftime('%H:%M')))
            conn.commit()

            # Foydalanuvchi tasdiqlanadi
            await message.reply(f"Ro'yxat qabul qilindi: {data['name']} {data['surname']}, {data['phone']}, {data['appointment_date'].strftime('%d%b')}, {appointment_time.strftime('%H:%M')}")

            # Yangi ro'yxatni admin ga yuborish
            await send_appointments_to_admin()

    await state.finish()

async def send_appointments_to_admin():
    cursor.execute('SELECT id, name, surname, phone, appointment_date, appointment_time FROM appointments ORDER BY appointment_date, appointment_time')
    rows = cursor.fetchall()
    response = "Barcha ro'yxatlar ro'yxati:\n"
    for row in rows:
        appointment_id = row[0]
        response += f"{row[4]} {row[5]}: {row[1]} {row[2]} ({row[3]})\n"
        delete_button = InlineKeyboardButton(text="O'chirish", callback_data=f"delete_{appointment_id}")
        delete_markup = InlineKeyboardMarkup().add(delete_button)
        await bot.send_message(ADMIN_ID, response, reply_markup=delete_markup)
        response = ""

@dp.callback_query_handler(lambda c: c.data and c.data == 'i_came')
async def callback_i_came(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    cursor.execute('SELECT name, surname, phone FROM appointments WHERE id = ?', (user_id,))
    appointment_data = cursor.fetchone()
    if appointment_data:
        name, surname, phone = appointment_data
        message_text = f"{name} {surname} tashrif buyurdi. Telefon raqami: {phone}"
        await bot.send_message(ADMIN_ID, message_text)
    else:
        await bot.send_message(ADMIN_ID, "Bunday foydalanuvchi topilmadi.")
    await bot.answer_callback_query(callback_query.id)

@dp.message_handler(commands=['statistics'], state='*')
async def send_statistics(message: types.Message):
    if str(message.from_user.id) == ADMIN_ID:
        cursor.execute('SELECT COUNT(*) FROM appointments')
        total_appointments = cursor.fetchone()[0]
        await message.reply(f"Umumiy ro'yxatlar soni: {total_appointments}")
    else:
        await message.reply("Siz admin emassiz.")

@dp.message_handler(commands=['list'], state='*')
async def list_appointments(message: types.Message):
    if str(message.from_user.id) == ADMIN_ID:
        cursor.execute('SELECT id, name, surname, phone, appointment_date, appointment_time FROM appointments ORDER BY appointment_date, appointment_time')
        rows = cursor.fetchall()
        if not rows:
            await message.reply("Hozircha hech qanday ro'yxat yo'q.")
        else:
            response = "Ro'yxatlar:\n"
            for row in rows:
                appointment_id = row[0]
                response += f"{row[4]} {row[5]}: {row[1]} {row[2]} ({row[3]})\n"
                delete_button = InlineKeyboardButton(text="O'chirish", callback_data=f"delete_{appointment_id}")
                delete_markup = InlineKeyboardMarkup().add(delete_button)
                await bot.send_message(message.chat.id, response, reply_markup=delete_markup)
                response = ""
    else:
        await message.reply("Siz admin emassiz.")

@dp.message_handler(commands=['panel'])
async def panel(message: types.Message):
    if str(message.from_user.id) == ADMIN_ID:
        await message.reply("Admin panel:", reply_markup=inline_kb_panel)
    else:
        await message.reply("Siz admin emassiz.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
