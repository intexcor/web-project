import asyncio
import base64
from os import getenv

import aiohttp
import sqlalchemy as db
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import BufferedInputFile, Message, KeyboardButton, ReplyKeyboardMarkup
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, Session
from sqlitestorage import SQLiteStorage

from kandinsky import Kandinsky

load_dotenv()
# Bot token can be obtained via https://t.me/BotFather
TOKEN = getenv("BOT_TOKEN")
API_KEY = getenv("API_KEY")
SECRET_KEY = getenv("SECRET_KEY")
# All handlers should be attached to the Router (or Dispatcher)
kandinsky = Kandinsky(API_KEY, SECRET_KEY)

storage = SQLiteStorage("myDatabase.db")

router = Router()
dp = Dispatcher(storage=storage)
dp.include_routers(router)

sched = BackgroundScheduler()
bot = Bot(TOKEN, default=DefaultBotProperties())
engine = db.create_engine('sqlite:///myDatabase.db')
conn = engine.connect()
metadata = db.MetaData()


class FormStates(StatesGroup):
    FIRST_BUTTON = State()
    FIRST_TEXT = State()
    SECOND_BUTTON = State()
    SECOND_TEXT = State()
    THIRD_BUTTON = State()

    FIRST_IMAGE = State()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True, nullable=False)
    count_generations: Mapped[int] = mapped_column(unique=True, nullable=False)
    is_premium: Mapped[bool] = mapped_column(nullable=False, default=False)

    def __repr__(self) -> str:
        return (f"User(id={self.id!r}, telegram_id={self.telegram_id!r}, count_generations={self.count_generations!r}, "
                f"i)")


Base.metadata.create_all(engine)


@router.message(CommandStart())
async def start(message: types.Message, state: FSMContext) -> None:
    with Session(engine) as session:
        if session.query(User).filter(User.telegram_id == message.from_user.id).count() == 0:
            user = User(telegram_id=message.from_user.id, is_premium=False, count_generations=20)
            session.add_all([user])
            session.commit()

    await state.clear()

    kb = [
        [types.KeyboardButton(text="Сгенерировать изображение")],
        [types.KeyboardButton(text="Удалить фон")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
    )

    await message.answer(
        "Привет! Я нейробот. Вот что я могу:", reply_markup=keyboard)


@router.message(StateFilter(None), F.text.lower() == "удалить фон")
async def del_fon(message: types.Message, state: FSMContext) -> None:
    kb = [
        [types.KeyboardButton(text="🔙Назад")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
    )

    await message.answer(
        "Отправить изображение", reply_markup=keyboard)

    await state.set_state(FormStates.FIRST_IMAGE)


async def ask_acetone(img_bytes):
    async with aiohttp.ClientSession() as session:
        async with session.post(
                url='https://api.acetone.ai/api/v1/remove/background?format=png',
                data={'image': img_bytes},
                headers={'Token': 'ea774a17-1105-4f7d-bfd1-d94d7cf27f10'}
        ) as response:
            return await response.read()


@router.message(FormStates.FIRST_IMAGE)
async def set_image(message: types.Message, state: FSMContext) -> None:
    if message.photo:
        mes = await message.reply("Фон удаляется")

        photo = await bot.download(message.photo[-1])
        img = await ask_acetone(photo)
        await bot.delete_message(chat_id=mes.chat.id, message_id=mes.message_id)
        await message.reply_photo(BufferedInputFile(img, filename="del_img.png"))
        await state.clear()

        kb = [
            [types.KeyboardButton(text="Сгенерировать изображение")],
            [types.KeyboardButton(text="Удалить фон")]
        ]
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
        )

        await message.answer(
            "Фон успешно удален", reply_markup=keyboard)
    else:
        await message.answer("Отправьте пожалуйста фото")


@router.message(FormStates.FIRST_IMAGE, F.text.lower() == "🔙назад")
async def naz(message: types.Message, state: FSMContext) -> None:
    await state.clear()

    kb = [
        [types.KeyboardButton(text="Сгенерировать изображение")],
        [types.KeyboardButton(text="Удалить фон")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
    )

    await message.answer(
        "Главное меню", reply_markup=keyboard)


@router.message(StateFilter(None), F.text.lower() == "сгенерировать изображение")
async def set_model(message: Message, state: FSMContext):
    kb = [
        [types.KeyboardButton(text="Kandinsky")],
        [types.KeyboardButton(text="🔙Назад")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
    )

    await message.answer(
        "Выберите модель", reply_markup=keyboard)

    await state.set_state(FormStates.FIRST_BUTTON)


@router.message(FormStates.FIRST_BUTTON)
async def enter_prompt(message: Message, state: FSMContext):
    if message.text.lower() == "🔙назад":
        kb = [
            [types.KeyboardButton(text="Сгенерировать изображение")],
            [types.KeyboardButton(text="Удалить фон")]
        ]
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
        )
        await message.answer("Главное меню", reply_markup=keyboard)
        await state.clear()
        return

    kb = [
        [types.KeyboardButton(text="🔙Назад")],
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
    )
    await message.answer(
        "Введите промпт", reply_markup=keyboard)
    await state.set_state(FormStates.FIRST_TEXT)


@router.message(FormStates.FIRST_TEXT, F.text)
async def save_prompt(message: Message, state: FSMContext):
    if message.text.lower() == "🔙назад":
        kb = [
            [types.KeyboardButton(text="Kandinsky")],
            [types.KeyboardButton(text="Назад")]
        ]
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
        )

        await message.answer(
            "Выберите модель", reply_markup=keyboard)

        await state.set_state(FormStates.FIRST_BUTTON)
        return
    await state.update_data(prompt=message.text.lower())
    kb = [
        [types.KeyboardButton(text="Пропустить")],
        [types.KeyboardButton(text="🔙Назад")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
    )
    await message.answer(
        "Введите негативный промпт или нажмите пропустить", reply_markup=keyboard)
    await state.set_state(FormStates.SECOND_TEXT)


async def get_buttons(  # message: Message, state: FSMContext
):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://cdn.fusionbrain.ai/static/styles/api") as response:
            data = await response.json()
            return data


@router.message(FormStates.SECOND_TEXT)
async def save_negative_prompt(message: Message, state: FSMContext):
    if message.text.lower() == "🔙назад":
        kb = [
            [types.KeyboardButton(text="🔙Назад")],
        ]
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
        )
        await message.answer(
            "Введите промпт", reply_markup=keyboard)
        await state.set_state(FormStates.FIRST_TEXT)
        return
    n_prompt = message.text.lower()
    await state.update_data(negative_prompt=n_prompt if n_prompt != "пропустить" else None)
    buttons = await get_buttons()
    row = [KeyboardButton(text=item["name"]) for item in buttons]
    keyboard = ReplyKeyboardMarkup(keyboard=[row, [types.KeyboardButton(text="🔙Назад")]], resize_keyboard=True)
    await message.answer(
        "Выберите стиль", reply_markup=keyboard)
    await state.set_state(FormStates.THIRD_BUTTON)


@router.message(FormStates.THIRD_BUTTON, F.text)
async def gem_img(message: Message, state: FSMContext):
    if message.text.lower() == "🔙назад":
        kb = [
            [types.KeyboardButton(text="Пропустить")],
            [types.KeyboardButton(text="🔙Назад")]
        ]
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
        )
        await message.answer(
            "Введите негативный промпт или нажмите пропустить", reply_markup=keyboard)
        await state.set_state(FormStates.SECOND_TEXT)
        return
    await state.update_data(style=message.text)

    with Session(engine) as session:
        user = session.scalars(select(User).where(User.telegram_id == message.from_user.id)).one()
        if user.count_generations <= 0 and not user.is_premium:
            await message.reply("Ваши генерации закончились. Попробуйте завтра")
            await state.clear()
            return
        user.count_generations -= 1
        session.commit()

    mes = await message.reply("Изображение генерируется")
    data = await state.get_data()
    img = await kandinsky.generate_img(data["prompt"], negativeprompt=data["negative_prompt"], style=data["style"])
    await bot.delete_message(chat_id=mes.chat.id, message_id=mes.message_id)
    await message.reply_photo(BufferedInputFile(base64.b64decode(img), filename="gen_img.png"))
    await state.clear()

    kb = [
        [types.KeyboardButton(text="Сгенерировать изображение")],
        [types.KeyboardButton(text="Удалить фон")]
    ]

    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
    )

    await message.answer(text="Изображение сгенерировано", reply_markup=keyboard)


def job():
    with Session(engine) as session:
        for user in session.scalars(select(User)):
            user.count_generations = 20
        session.commit()


async def main() -> None:
    # Initialize Bot instance with a default parse mode which will be passed to all API calls

    # And the run events dispatching
    sched.add_job(job, 'cron', hour=23, minute=7)
    sched.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
