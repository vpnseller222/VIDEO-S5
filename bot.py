import asyncio
import logging
import time
import os
import uuid
import firebase_admin
from firebase_admin import credentials, db as firebase_db
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, 
    InlineKeyboardButton, WebAppInfo, MenuButtonWebApp, Message, CallbackQuery, FSInputFile
)

# --- ১. Firebase কানেকশন সেটআপ ---
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://bachelor-point-season-5-default-rtdb.firebaseio.com/' 
})

# --- ২. ট্রাফিক পুলিশ (Rate Limiter) ---
class TrafficPoliceMiddleware(BaseMiddleware):
    def __init__(self, limit: int = 25):
        self.limit = limit
        self.request_times = []
        super().__init__()

    async def __call__(self, handler, event, data):
        current_time = time.time()
        self.request_times = [t for t in self.request_times if current_time - t < 1.0]
        if len(self.request_times) >= self.limit:
            await asyncio.sleep(0.1)
            return await self.__call__(handler, event, data)
        self.request_times.append(current_time)
        return await handler(event, data)

# --- ৩. কনফিগারেশন ---
TOKEN = "8546964452:AAE41mqRnnq2G9Ih54Rh9mPIaUAW2_9Uzwo" 
ADMIN_LIST = [6856009995, 8724211967] 
WEB_APP_URL = "https://videotube.pages.dev/" 
START_IMAGE_URL = "https://i.ibb.co.com/G4ZdCYtP/1779163887792-01.jpg"

bot = Bot(token=TOKEN)
dp = Dispatcher()
traffic_police = TrafficPoliceMiddleware(limit=25)
dp.message.outer_middleware(traffic_police)

# --- ৪. States ---
class VideoUpload(StatesGroup):
    name = State()
    photo = State()
    category = State()
    video_source = State()

class VideoDelete(StatesGroup):
    waiting_for_search = State()
    confirm_selection = State()

class BotNotice(StatesGroup):
    waiting_for_payload = State()

class AdminSettings(StatesGroup):
    waiting_for_update_text = State()

# --- ৫. কিবোর্ড ফাংশনসমূহ ---
def get_admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Add Video"), KeyboardButton(text="🔕 Delete Video")],
        [KeyboardButton(text="📢 BOT NOTICE"), KeyboardButton(text="📊 Total Users")], # এখানে বাটন যুক্ত করা হয়েছে
        [KeyboardButton(text="⚙️ SET VIDEO UPDATE"), KeyboardButton(text="🔙 Back to Menu")]
    ], resize_keyboard=True)

def get_back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Back to Menu")]], resize_keyboard=True)

def get_category_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="BP S5")],
        [KeyboardButton(text="🔙 Back to Menu")]
    ], resize_keyboard=True)

# --- ৬. সাপ্তাহিক অটোমেটিক ব্যাকআপ ফাংশন ---
async def send_weekly_backup():
    while True:
        await asyncio.sleep(604800) 
        for admin_id in ADMIN_LIST:
            try:
                data = firebase_db.reference('/').get()
                backup_filename = "firebase_backup.json"
                with open(backup_filename, "w", encoding="utf-8") as f:
                    import json
                    json.dump(data, f, indent=4)
                
                db_file = FSInputFile(backup_filename)
                await bot.send_document(
                    chat_id=admin_id, 
                    document=db_file, 
                    caption=f"📅 <b>সাপ্তাহিক ক্লাউড ব্যাকআপ রিপোর্ট</b>\n\n✅ আপনার ফায়ারবেস ডাটাবেজটি ক্লাউড থেকে সরাসরি পাঠানো হয়েছে।"
                )
            except Exception as e:
                logging.error(f"Backup failed for {admin_id}: {e}")

# --- ৭. মেইন স্টার্ট হ্যান্ডলার ---
@dp.message(CommandStart())
@dp.message(F.text == "🔙 Back to Menu")
async def start_handler(message: Message, command: CommandObject = None, state: FSMContext = None):
    if state: await state.clear()
    user_id = str(message.from_user.id)
    user_name = message.from_user.first_name # ইউজারের নাম সংগ্রহ
    
    # ইউজার ডাটা সেভ
    user_ref = firebase_db.reference(f'users/{user_id}')
    if not user_ref.get():
        user_ref.set({'joined_at': time.time(), 'name': user_name})

    # ওয়েব অ্যাপ বাটন সেটআপ
    await bot.set_chat_menu_button(
        chat_id=int(user_id), 
        menu_button=MenuButtonWebApp(text="Watch Now 🎬", web_app=WebAppInfo(url=WEB_APP_URL))
    )

    # যদি ডাইরেক্ট ভিডিও লিংকে ক্লিক করে আসে
    if command and command.args:
        video_id = command.args
        v_data = firebase_db.reference(f'videos/{video_id}').get()
        if v_data:
            await bot.send_video(
                chat_id=int(user_id), 
                video=v_data['video'], 
                caption=f"🎬 <b>{v_data['name']}</b>\n\nউপভোগ করুন!", 
                parse_mode="HTML",
                protect_content=True
            )
            return

    # ইউজার কিবোর্ড
    user_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 WATCH NOW", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton(text="🔔 VIDEO UPDATE", callback_data="view_video_update")]
    ])

    # নামসহ স্বাগতম মেসেজ
    welcome_text = (
        f"<b>আসসালামুয়ালাইকুম {user_name}</b> 🥰\n\n"
        "আমাদের বট ২৪ ঘন্টা সচল। ভিডিও ডাউনলোড করতে নিচের <b>WATCH NOW</b> বাটনে ক্লিক করুন 🥰"
    )

    # ছবি সহ মেসেজ পাঠানো
    await message.answer_photo(
        photo=START_IMAGE_URL,
        caption=welcome_text,
        reply_markup=user_kb,
        parse_mode="HTML"
    )
    
    if int(user_id) in ADMIN_LIST:
        await message.answer("🛠 এডমিন প্যানেল সচল করা হয়েছে:", reply_markup=get_admin_kb())

# --- ৮. ভিডিও আপডেট দেখার লজিক ---
@dp.callback_query(F.data == "view_video_update")
async def view_update_callback(callback: CallbackQuery):
    update_data = firebase_db.reference('settings/video_update_text').get()
    if not update_data:
        update_data = "বর্তমানে কোনো নতুন আপডেট নেই। আমাদের সাথেই থাকুন!"
    
    await callback.answer()
    await callback.message.answer(f"📢 <b>ভিডিও আপডেট:</b>\n\n{update_data}", parse_mode="HTML")

# --- ৯. এডমিন: ভিডিও আপডেট সেট করার লজিক ---
@dp.message(F.text == "⚙️ SET VIDEO UPDATE")
async def set_update_init(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(AdminSettings.waiting_for_update_text)
        await message.answer("📝 নতুন আপডেট টেক্সটটি লিখুন যা ইউজাররা দেখতে পাবে:", reply_markup=get_back_kb())

@dp.message(AdminSettings.waiting_for_update_text)
async def set_update_save(message: Message, state: FSMContext):
    new_text = message.text
    firebase_db.reference('settings/video_update_text').set(new_text)
    await message.answer(f"✅ ভিডিও আপডেট টেক্সট সফলভাবে সেভ হয়েছে!", reply_markup=get_admin_kb())
    await state.clear()

# --- ১০. ভিডিও অ্যাড করার লজিক ---
@dp.message(F.text == "➕ Add Video")
async def add_v_start(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(VideoUpload.name)
        await message.answer("📝 ভিডিওর টাইটেল লিখুন (উদাঃ Episode 01):", reply_markup=get_back_kb())

@dp.message(VideoUpload.name)
async def add_v_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(VideoUpload.photo)
    await message.answer("🖼 থাম্বনেইল পাঠান (সরাসরি ফটো অথবা ইউআরএল):", reply_markup=get_back_kb())

@dp.message(VideoUpload.photo)
async def add_v_photo(message: Message, state: FSMContext):
    if message.photo:
        file = await bot.get_file(message.photo[-1].file_id)
        photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
        await state.update_data(photo=photo_url)
    else:
        await state.update_data(photo=message.text)
    
    await state.set_state(VideoUpload.category)
    await message.answer("📂 ক্যাটাগরি সিলেক্ট করুন:", reply_markup=get_category_kb())

@dp.message(VideoUpload.category)
async def add_v_cat(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(VideoUpload.video_source)
    await message.answer("🎬 এখন ভিডিও ফাইলটি (Telegram Video) পাঠান:", reply_markup=get_back_kb())

@dp.message(VideoUpload.video_source, F.video)
async def add_v_final(message: Message, state: FSMContext):
    data = await state.get_data()
    v_id = str(uuid.uuid4())[:8]
    
    firebase_db.reference(f'videos/{v_id}').set({
        'id': v_id,
        'name': data['name'],
        'photo': data['photo'],
        'ad_count': 0,
        'video': message.video.file_id,
        'category': data['category']
    })
    
    await message.answer(f"✅ ভিডিও সফলভাবে যুক্ত হয়েছে!\nআইডি: `{v_id}`", parse_mode="Markdown", reply_markup=get_admin_kb())
    await state.clear()

# --- ১১. ভিডিও ডিলিট করার লজিক ---
@dp.message(F.text == "🔕 Delete Video")
async def delete_v_init(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(VideoDelete.waiting_for_search)
        await message.answer("🔍 ডিলিট করতে চাওয়া ভিডিওর নাম লিখুন:", reply_markup=get_back_kb())

@dp.message(VideoDelete.waiting_for_search)
async def delete_v_search_results(message: Message, state: FSMContext):
    query = message.text.lower()
    videos_ref = firebase_db.reference('videos').get()
    if not videos_ref:
        await message.answer("❌ কোনো ভিডিও পাওয়া যায়নি।")
        return
    matches = [v for v in videos_ref.values() if query in v['name'].lower()]
    if not matches:
        await message.answer("❌ কোনো ভিডিও পাওয়া যায়নি।")
        return
    buttons = [[InlineKeyboardButton(text=f"🗑 {v['name']}", callback_data=f"ask_del:{v['id']}")] for v in matches]
    buttons.append([InlineKeyboardButton(text="❌ বাতিল", callback_data="cancel_del")])
    await message.answer(f"🔎 {len(matches)}টি ভিডিও পাওয়া গেছে। কোনটি মুছবেন?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(VideoDelete.confirm_selection)

@dp.callback_query(F.data.startswith("ask_del:"), VideoDelete.confirm_selection)
async def delete_v_confirm(callback: CallbackQuery):
    vid_id = callback.data.split(":")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ হ্যা, ডিলিট করুন", callback_data=f"do_del:{vid_id}")],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="cancel_del")]
    ])
    await callback.message.edit_text("⚠️ আপনি কি নিশ্চিতভাবে এই ভিডিওটি মুছতে চান?", reply_markup=kb)

@dp.callback_query(F.data.startswith("do_del:"), VideoDelete.confirm_selection)
async def delete_v_execute(callback: CallbackQuery, state: FSMContext):
    vid_id = callback.data.split(":")[1]
    firebase_db.reference(f'videos/{vid_id}').delete()
    await callback.message.edit_text("✅ ভিডিওটি সফলভাবে মুছে ফেলা হয়েছে।")
    await state.clear()

@dp.callback_query(F.data == "cancel_del")
async def delete_v_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚫 অপারেশন বাতিল করা হয়েছে।")
    await state.clear()

# --- ১২. ব্রডকাস্ট নোটিশ (লাইভ কাউন্টার ও লিমিট সহ) ---
@dp.message(F.text == "📢 BOT NOTICE")
async def notice_init(message: Message, state: FSMContext):
    if message.from_user.id in ADMIN_LIST:
        await state.set_state(BotNotice.waiting_for_payload)
        await message.answer("📢 নোটিশ মেসেজটি দিন (টেক্সট/ছবি/ভিডিও):", reply_markup=get_back_kb())

@dp.message(BotNotice.waiting_for_payload)
async def notice_broadcast(message: Message, state: FSMContext):
    users_ref = firebase_db.reference('users').get()
    if not users_ref:
        await message.answer("❌ কোনো ইউজার পাওয়া যায়নি।")
        await state.clear()
        return

    total_users = len(users_ref)
    success_count = 0
    fail_count = 0
    status_msg = await message.answer(f"⚡ লাইভ ব্রডকাস্টিং শুরু হচ্ছে...", parse_mode="HTML")

    start_time = time.time()
    batch_size = 15 
    user_ids = list(users_ref.keys())

    for i in range(0, total_users, batch_size):
        batch = user_ids[i:i + batch_size]
        for uid in batch:
            try:
                await message.copy_to(chat_id=int(uid))
                success_count += 1
            except:
                fail_count += 1
        
        progress = int(((success_count + fail_count) / total_users) * 100)
        try:
            await status_msg.edit_text(
                f"⚡ <b>লাইভ ব্রডকাস্টিং...</b>\n\n👥 মোট ইউজার: {total_users}\n✅ সফল: {success_count}\n❌ ব্যর্থ: {fail_count}\n📊 অগ্রগতি: {progress}%", 
                parse_mode="HTML"
            )
        except: pass
        await asyncio.sleep(1.0)

    end_time = round(time.time() - start_time, 2)
    await status_msg.delete()
    await message.answer(f"📢 <b>ব্রডকাস্ট সম্পন্ন!</b>\n\n✅ সফল: {success_count}\n❌ ব্যর্থ: {fail_count}\n⏱ সময়: {end_time} সে.", parse_mode="HTML", reply_markup=get_admin_kb())
    await state.clear()

# --- ১৩. মেইন রানার ---
@dp.message(F.text == "📊 Total Users")
async def show_total_users(message: Message):
    if message.from_user.id in ADMIN_LIST:
        users_ref = firebase_db.reference('users').get()
        
        if users_ref:
            count = len(users_ref)
            await message.answer(
                f"📊 <b>বট ইউজার স্ট্যাটিসটিকস</b>\n\n"
                f"👥 মোট ইউজার সংখ্যা: <b>{count}</b> জন।\n"
                f"📡 ডাটা সোর্স: Firebase Realtime DB",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ ডাটাবেজে এখনো কোনো ইউজার ডাটা নেই।")

async def main():
    print("🤖 Bot is Starting with Cloud Database...")
    asyncio.create_task(send_weekly_backup())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
                
