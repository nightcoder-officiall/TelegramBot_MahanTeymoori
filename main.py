# main.py
# این فایل شامل هسته اصلی ربات تلگرام است

import telebot
from telebot import types
import json
from telebot.apihelper import ApiTelegramException
import logging
from datetime import datetime, timedelta
import os
import openpyxl




try:
    from config import TOKEN, DEVELOPER_ID, MIN_SCORE_FOR_VIP, DATA_FILE, QUESTIONS_FILE, LOG_FILE, END_PIC_PATH
except ImportError:
    print("Warning: config.py not found. Using default values.")
    TOKEN = '6175047131:AAHpZXJSjKiJ_GfuT1Np0mNxD1-EUYTMnmM'
    DEVELOPER_ID = 5721909122
    MIN_SCORE_FOR_VIP = 8
    DATA_FILE = 'users_data.json'
    QUESTIONS_FILE = 'questions.json'
    LOG_FILE = 'bot.log'
    END_PIC_PATH = 'end_pic.jpg'

bot = telebot.TeleBot(TOKEN)

# --- LOG SYSTEM ---
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
last_error_notification = datetime.min

# --- RAM STORAGE ---
user_states = {}
questions = []

def load_data():
    """داده‌های کاربران و سوالات را از فایل‌ها بارگذاری می‌کند."""
    global questions
    try:
        # IMPORT USER DATA
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            # اگر فایل داده وجود نداشت، یک ساختار اولیه ایجاد می‌کند
            data = {"users": [], "admins": [DEVELOPER_ID]}

        # IMPORT QUESTIONS FILE
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            questions = json.load(f)

        return data

    except Exception as e:
        logging.error(f"خطا در بارگذاری داده‌ها: {e}")
        send_developer_error_notification(f"Error loading initial data: {e}")
        return {"users": [], "admins": [DEVELOPER_ID]}

def save_data(data):
    """داده‌های کاربران را در فایل JSON ذخیره می‌کند."""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"خطا در ذخیره داده‌ها: {e}")
        send_developer_error_notification(f"Error saving user data: {e}")

def get_question_by_key(key):
    """یک سوال را بر اساس کلید یکتا (key) پیدا می‌کند."""
    for q in questions:
        if q['key'] == key:
            return q
    return None

def find_user_by_id_or_phone(user_id, phone_number=None):
    """بررسی می‌کند که آیا کاربر قبلاً با آیدی یا شماره تلفن ثبت شده است."""
    data = load_data()
    for user in data['users']:
        if user['id'] == user_id:
            return True, "id"
        if phone_number and user.get('answers', {}).get('phone') == phone_number:
            return True, "phone"
    return False, None

def get_next_question(current_question_key):
    """سوال بعدی در توالی را برمی‌گرداند."""
    if not current_question_key:
        return questions[0]
    
    current_index = -1
    for i, q in enumerate(questions):
        if q['key'] == current_question_key:
            current_index = i
            break
    
    if current_index + 1 < len(questions):
        return questions[current_index + 1]
    return None

def get_prev_question(current_question_key):
    """سوال قبلی در توالی را برمی‌گرداند."""
    current_index = -1
    for i, q in enumerate(questions):
        if q['key'] == current_question_key:
            current_index = i
            break
    
    if current_index > 0:
        return questions[current_index - 1]
    return None

def generate_markup(question_data, user_id):
    """Markup دکمه‌های اینلاین برای سوالات را ایجاد می‌کند."""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    if question_data['type'] == 'options':
        user_answers = user_states[user_id].get('answers', {})
        selected_option = user_answers.get(question_data['key'])
        
        for i, option in enumerate(question_data['options']):
            text_to_show = option['text']
            # اگر گزینه قبلاً انتخاب شده، یک ایموجی ستاره اضافه می‌کند
            if selected_option and selected_option['text'] == option['text']:
                text_to_show = f"🌟 {text_to_show}"
            
            # استفاده از ایندکس برای جلوگیری از طولانی شدن callback_data
            callback_data = f"ans_{question_data['key']}_{i}"
            markup.add(types.InlineKeyboardButton(text_to_show, callback_data=callback_data))

    elif question_data['type'] == 'multi_options':
        user_answers = user_states[user_id].get('answers', {})
        selected_options = user_answers.get(question_data['key'], [])
        
        for i, option in enumerate(question_data['options']):
            text_to_show = option['text']
            if option['text'] in [o['text'] for o in selected_options]:
                text_to_show = f"✅ {text_to_show}"
            
            callback_data = f"multians_{question_data['key']}_{i}"
            markup.add(types.InlineKeyboardButton(text_to_show, callback_data=callback_data))
        
        # دکمه‌های بعدی و بازگشت در یک ردیف جدا
        row_buttons = []
        
        if question_data['key'] != questions[0]['key']:
            row_buttons.append(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"back_{question_data['key']}"))
        
        row_buttons.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"next_{question_data['key']}"))
        markup.row(*row_buttons)

    # دکمه بازگشت به سوال قبل فقط بعد از سوالات اولیه نمایش داده می‌شود
    initial_questions_keys = ['name', 'phone', 'business_field']
    if question_data['key'] not in initial_questions_keys and question_data['type'] not in ['multi_options', 'text']:
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به سوال قبل", callback_data=f"back_{question_data['key']}"))
    
    return markup

def create_survey_message(user_id):
    """متن و دکمه‌های سوال نظرسنجی را ایجاد می‌کند."""
    user_state = user_states[user_id]
    current_q_key = user_state['current_question_key']
    current_q_data = get_question_by_key(current_q_key)
    
    if not current_q_data:
        return "خطا در بارگذاری سوالات. لطفا مجددا /start را بزنید.", None
    
    text = current_q_data['text']
    
    if current_q_data['type'] == 'phone':
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton('ارسال شماره تلفن', request_contact=True))
        return text, markup
    else:
        markup = generate_markup(current_q_data, user_id)
        return text, markup

def finish_survey(user_id, chat_id, message_id):
    """امتیاز نهایی را محاسبه و داده‌های کاربر را ذخیره می‌کند."""
    user_data_to_save = user_states[user_id]
    total_score = 0
    
    for q_key, answer in user_data_to_save['answers'].items():
        if isinstance(answer, dict) and 'score' in answer:
            total_score += answer['score']
        elif isinstance(answer, list):
            for ans in answer:
                if isinstance(ans, dict) and 'score' in ans:
                    total_score += ans['score']


    user_data_to_save['final_score'] = total_score
    
    data = load_data()
    data['users'].append(user_data_to_save)
    save_data(data)
    
    # حذف وضعیت کاربر از حافظه موقت
    if user_id in user_states:
        del user_states[user_id]
    
    # پیام نهایی با نمایش نمره و پیام تبریک
    final_message = f"""تبریک می‌گوییم!
    
نمره شما در این نظرسنجی: {total_score}

این تست نشان می‌دهد شما جزو مدیرانی هستید که ظرفیت نامبر وان شدن را دارید 👑

کارشناسان مااز واحد منتورینگ مجموعه ظرف 48 ساعت آینده با شما تماس میگیرند
"""
    
    # ابتدا پیام آخر را حذف می‌کند و سپس عکس را می‌فرستد
    try:
        bot.delete_message(chat_id, message_id)
    except ApiTelegramException as e:
        logging.warning(f"Failed to delete last message for user {user_id}: {e}")
        send_developer_error_notification(f"Error deleting last message: {e}")

    try:
        with open(END_PIC_PATH, 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=final_message)
    except FileNotFoundError:
        bot.send_message(chat_id, f"{final_message}")
    except Exception as e:
        logging.error(f"خطا در ارسال عکس پایانی: {e}")
        bot.send_message(chat_id, f"{final_message}")
        send_developer_error_notification(f"Error sending end picture to user {user_id}: {e}")

def send_developer_error_notification(error_message):
    """ارسال نوتیفیکیشن خطا به توسعه‌دهنده با محدودیت زمانی."""
    global last_error_notification
    if datetime.now() - last_error_notification > timedelta(minutes=15):
        try:
            bot.send_message(DEVELOPER_ID, f"🚨 **خطا در ربات** 🚨\n\n```\n{error_message}\n```", parse_mode='Markdown')
            last_error_notification = datetime.now()
        except Exception as e:
            logging.error(f"Failed to send error notification to developer: {e}")

def create_excel_output(vip_only=False):
    """یک فایل اکسل از داده‌های کاربران ایجاد می‌کند."""
    try:
        data = load_data()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "User Data"
        
        headers = ["ID", "Name", "Final Score"] + [q['text'] for q in questions]
        ws.append(headers)

        users_to_export = data['users']
        if vip_only:
            users_to_export = [u for u in data['users'] if u.get('final_score', 0) >= MIN_SCORE_FOR_VIP]
            
        for user in users_to_export:
            row = [user['id'], user.get('name', 'N/A'), user.get('final_score', 0)]
            
            for q in questions:
                answer = user.get('answers', {}).get(q['key'])
                if isinstance(answer, dict):
                    row.append(answer.get('text'))
                elif isinstance(answer, list):
                    # برای سوالات چند گزینه‌ای، پاسخ‌ها را با کاما جدا می‌کند
                    row.append(", ".join([ans.get('text') for ans in answer]))
                else:
                    row.append(answer)
            ws.append(row)

        file_name = "vip_users_data.xlsx" if vip_only else "all_users_data.xlsx"
        wb.save(file_name)
        return file_name

    except Exception as e:
        logging.error(f"خطا در ساخت فایل اکسل: {e}")
        send_developer_error_notification(f"Error creating Excel file: {e}")
        return None

# --- هندلرهای تلگرام ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    """هندلر دستور /start برای شروع نظرسنجی."""
    try:
        user_id = message.from_user.id
        user_exists, found_by = find_user_by_id_or_phone(user_id)
        
        if user_exists:
            bot.send_message(message.chat.id, "شما قبلا در این نظرسنجی شرکت کرده‌اید.")
            return

        # ارسال پیام خوش‌آمدگویی جداگانه
        welcome_message = """برند شدن یه سفره … 🐦‍🔥✨
مقصد، جاده رو تعیین می‌کنه … 🎯
برای اولین بار تو ایران می‌خوام صادقانه بهت بگم کجای جاده‌ی برند شدن هستی و چقدر دیگه راه داری تا برسی 🚀
به کجا؟!
به شماره یک شدن 🥇
به قدرت و شهرت و ثروتی که بهت کمک می‌کنه خدمت کنی 💪
من ماهانِ تیموری، به عنوان کسی که سال‌هاست منتور شماره‌ی یک‌های ایرانه، ازت می‌خوام  نیم ساعت وقت بذاری و با دقت به سؤالای این تست جواب بدی ✅"""
        
        bot.send_message(message.chat.id, welcome_message)

        # شروع نظرسنجی با اولین سوال
        user_states[user_id] = {
            'id': user_id,
            'current_question_key': questions[0]['key'],
            'answers': {},
            'message_id': None,
            'name': message.from_user.first_name + ' ' + (message.from_user.last_name or '')
        }
        
        text, markup = create_survey_message(user_id)
        sent_message = bot.send_message(message.chat.id, text, reply_markup=markup)
        user_states[user_id]['message_id'] = sent_message.message_id

    except Exception as e:
        logging.error(f"خطا در هندلر /start برای کاربر {message.from_user.id}: {e}")
        bot.send_message(message.chat.id, "متاسفانه مشکلی پیش آمده. لطفا بعداً مجدداً تلاش کنید.")
        send_developer_error_notification(f"Error in /start for user {message.from_user.id}: {e}")

@bot.message_handler(commands=['admin'])
def handle_admin_panel(message):
    """هندلر دستور /admin برای دسترسی به پنل مدیریت."""
    user_id = message.from_user.id
    data = load_data()
    
    if user_id not in data['admins']:
        bot.send_message(message.chat.id, "شما دسترسی به پنل مدیریت ندارید.")
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📊 تعداد تکمیل کنندگان", callback_data="admin_stats"))
    markup.add(types.InlineKeyboardButton("📄 خروجی اکسل کامل", callback_data="admin_excel_all"))
    markup.add(types.InlineKeyboardButton("💎 خروجی اکسل VIP", callback_data="admin_excel_vip"))

    bot.send_message(message.chat.id, "به پنل مدیریت خوش آمدید:", reply_markup=markup)

@bot.message_handler(commands=['dev'])
def handle_dev_panel(message):
    """هندلر دستور /dev برای دسترسی به پنل دولوپر."""
    if message.from_user.id != DEVELOPER_ID:
        bot.send_message(message.chat.id, "شما دسترسی به پنل دولوپر ندارید.")
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👤 مدیریت ادمین‌ها", callback_data="dev_manage_admins"))
    markup.add(types.InlineKeyboardButton("🗒️ دریافت لاگ", callback_data="dev_get_logs"))
    bot.send_message(message.chat.id, "به پنل دولوپر خوش آمدید:", reply_markup=markup)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    """هندلر دریافت شماره تلفن از کاربر."""
    user_id = message.from_user.id
    if user_id not in user_states:
        return
        
    try:
        phone_number = message.contact.phone_number
        user_exists, found_by = find_user_by_id_or_phone(user_id, phone_number)

        if user_exists and found_by == 'phone':
            bot.send_message(message.chat.id, "این شماره تلفن قبلاً در نظرسنجی شرکت کرده است.")
            if user_id in user_states:
                del user_states[user_id]
            return

        user_states[user_id]['answers']['phone'] = phone_number
        
        next_q = get_next_question(user_states[user_id]['current_question_key'])
        if next_q:
            user_states[user_id]['current_question_key'] = next_q['key']
            text, markup = create_survey_message(user_id)
            try:
                # حذف کیبورد "ارسال شماره تلفن"
                bot.send_message(message.chat.id, "شماره تلفن شما با موفقیت ثبت شد.", reply_markup=types.ReplyKeyboardRemove())
                # ارسال پیام جدید برای سوال بعدی
                new_msg = bot.send_message(message.chat.id, text, reply_markup=markup)
                user_states[user_id]['message_id'] = new_msg.message_id
            except ApiTelegramException as e:
                logging.warning(f"Failed to send next message for user {user_id}: {e}")
                bot.send_message(message.chat.id, text, reply_markup=markup)
            
    except Exception as e:
        logging.error(f"خطا در هندلر دریافت شماره تلفن برای کاربر {user_id}: {e}")
        bot.send_message(message.chat.id, "مشکلی در دریافت شماره تلفن شما پیش آمده. لطفا دوباره تلاش کنید.")
        send_developer_error_notification(f"Error in contact handler: {e}")

@bot.message_handler(func=lambda message: True)
def handle_text_answer(message):
    """هندلر دریافت پاسخ‌های متنی از کاربر."""
    user_id = message.from_user.id
    if user_id not in user_states:
        return

    current_q_key = user_states[user_id]['current_question_key']
    current_q_data = get_question_by_key(current_q_key)

    if not current_q_data or current_q_data['type'] != 'text':
        return

    try:
        answer_text = message.text.strip()
        
        # اعتبارسنجی برای سوال 'name'
        if current_q_key == 'name' and len(answer_text) > 30:
            bot.send_message(message.chat.id, "نام و نام خانوادگی نمی‌تواند بیشتر از ۳۰ کاراکتر باشد. لطفا دوباره وارد کنید.")
            return

        user_states[user_id]['answers'][current_q_key] = answer_text

        next_q = get_next_question(current_q_key)
        if next_q:
            user_states[user_id]['current_question_key'] = next_q['key']
            text, markup = create_survey_message(user_id)
            # ارسال پیام جدید برای پاسخ‌های متنی
            sent_message = bot.send_message(message.chat.id, text, reply_markup=markup)
            user_states[user_id]['message_id'] = sent_message.message_id
        else:
            finish_survey(user_id, message.chat.id, user_states[user_id]['message_id'])

    except Exception as e:
        logging.error(f"خطا در هندلر پاسخ متنی برای کاربر {user_id}: {e}")
        bot.send_message(message.chat.id, "مشکلی در ذخیره پاسخ شما پیش آمده. لطفا دوباره تلاش کنید.")
        send_developer_error_notification(f"Error in text handler: {e}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """هندلر کلیک روی دکمه‌های اینلاین."""
    user_id = call.from_user.id
    message_id = call.message.message_id
    
    bot.answer_callback_query(call.id)

    if call.data.startswith("ans_"):
        if user_id not in user_states or user_states[user_id].get('message_id') != message_id:
            bot.answer_callback_query(call.id, "این نظرسنجی منقضی شده است.")
            return
        
        try:
            # Parse callback data more robustly for keys with underscores
            parts = call.data.split('_')
            q_key = "_".join(parts[1:-1])
            option_index = int(parts[-1])
            
            current_q_data = get_question_by_key(q_key)
            selected_option = current_q_data['options'][option_index]

            user_states[user_id]['answers'][q_key] = selected_option
            
            next_q = get_next_question(q_key)
            if next_q:
                user_states[user_id]['current_question_key'] = next_q['key']
                text, markup = create_survey_message(user_id)
                try:
                    bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=message_id, reply_markup=markup)
                except ApiTelegramException as e:
                    logging.warning(f"Failed to edit message for user {user_id}: {e}")
                    new_msg = bot.send_message(call.message.chat.id, text, reply_markup=markup)
                    user_states[user_id]['message_id'] = new_msg.message_id
            else:
                finish_survey(user_id, call.message.chat.id, message_id)

        except Exception as e:
            logging.error(f"خطا در هندلر کلیک (ans) برای کاربر {user_id}: {e}")
            bot.answer_callback_query(call.id, "خطایی رخ داد. لطفا مجددا تلاش کنید.")
            send_developer_error_notification(f"Error in callback_query (ans): {e}")

    elif call.data.startswith("multians_"):
        if user_id not in user_states or user_states[user_id].get('message_id') != message_id:
            bot.answer_callback_query(call.id, "این نظرسنجی منقضی شده است.")
            return
        
        try:
            parts = call.data.split('_')
            q_key = "_".join(parts[1:-1])
            option_index = int(parts[-1])
            
            current_q_data = get_question_by_key(q_key)
            selected_option_data = current_q_data['options'][option_index]
            
            user_answers = user_states[user_id]['answers'].get(q_key, [])
            
            if selected_option_data in user_answers:
                user_answers.remove(selected_option_data)
            else:
                user_answers.append(selected_option_data)
            
            user_states[user_id]['answers'][q_key] = user_answers
            
            text, markup = create_survey_message(user_id)
            try:
                bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=message_id, reply_markup=markup)
            except ApiTelegramException as e:
                logging.warning(f"Failed to edit message for user {user_id}: {e}")
                new_msg = bot.send_message(call.message.chat.id, text, reply_markup=markup)
                user_states[user_id]['message_id'] = new_msg.message_id

        except Exception as e:
            logging.error(f"خطا در هندلر کلیک چند گزینه‌ای برای کاربر {user_id}: {e}")
            bot.answer_callback_query(call.id, "خطایی رخ داد. لطفا مجددا تلاش کنید.")
            send_developer_error_notification(f"Error in multi-select callback: {e}")

    elif call.data.startswith("next_"):
        if user_id not in user_states:
            return
        
        try:
            q_key = "_".join(call.data.split('_')[1:]) # اصلاح شده برای گرفتن کل کلید
            next_q = get_next_question(q_key)
            
            if next_q:
                user_states[user_id]['current_question_key'] = next_q['key']
                text, markup = create_survey_message(user_id)
                try:
                    bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=message_id, reply_markup=markup)
                except ApiTelegramException as e:
                    logging.warning(f"Failed to edit message for user {user_id}: {e}")
                    new_msg = bot.send_message(call.message.chat.id, text, reply_markup=markup)
                    user_states[user_id]['message_id'] = new_msg.message_id
            else:
                finish_survey(user_id, call.message.chat.id, message_id)
        
        except Exception as e:
            logging.error(f"خطا در هندلر کلیک (next) برای کاربر {user_id}: {e}")
            bot.answer_callback_query(call.id, "خطایی رخ داد. لطفا مجددا تلاش کنید.")
            send_developer_error_notification(f"Error in next callback: {e}")

    elif call.data.startswith("back_"):
        if user_id not in user_states:
            return

        try:
            # Parse callback data more robustly for keys with underscores
            parts = call.data.split('_')
            q_key = "_".join(parts[1:])
            prev_q = get_prev_question(q_key)
            
            if prev_q:
                user_states[user_id]['current_question_key'] = prev_q['key']
                text, markup = create_survey_message(user_id)
                
                # بررسی نوع سوال قبلی
                if prev_q['type'] == 'text':
                    # اگر سوال قبلی متنی بود، پیام فعلی را پاک و پیام جدید ارسال می‌کند
                    try:
                        bot.delete_message(chat_id=call.message.chat.id, message_id=message_id)
                    except ApiTelegramException as e:
                        logging.warning(f"Failed to delete message for user {user_id}: {e}")
                    
                    new_msg = bot.send_message(call.message.chat.id, text, reply_markup=markup)
                    user_states[user_id]['message_id'] = new_msg.message_id
                
                else:
                    # اگر سوال قبلی گزینه‌ای بود، پیام فعلی را ویرایش می‌کند
                    try:
                        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=message_id, reply_markup=markup)
                    except ApiTelegramException as e:
                        logging.warning(f"Failed to edit message for user {user_id}: {e}")
                        new_msg = bot.send_message(call.message.chat.id, text, reply_markup=markup)
                        user_states[user_id]['message_id'] = new_msg.message_id
            else:
                bot.answer_callback_query(call.id, "شما در اولین سوال هستید.")

        except Exception as e:
            logging.error(f"خطا در هندلر کلیک (back) برای کاربر {user_id}: {e}")
            bot.answer_callback_query(call.id, "خطایی رخ داد. لطفا مجددا تلاش کنید.")
            send_developer_error_notification(f"Error in callback_query (back): {e}")

    elif call.data.startswith("admin_"):
        data = load_data()
        if user_id not in data['admins']:
            bot.answer_callback_query(call.id, "شما دسترسی ندارید.")
            return

        try:
            action = call.data.split('_')[1]
            if action == 'stats':
                bot.answer_callback_query(call.id)
                count = len(data['users'])
                bot.send_message(call.message.chat.id, f"تعداد کل شرکت کنندگان: {count}")
            elif action == 'excel_all':
                bot.answer_callback_query(call.id)
                file_path = create_excel_output(vip_only=False)
                if file_path:
                    bot.send_document(call.message.chat.id, open(file_path, 'rb'))
                else:
                    bot.send_message(call.message.chat.id, "خطا در ساخت فایل اکسل کامل. لطفا لاگ را بررسی کنید.")
            elif action == 'excel_vip':
                bot.answer_callback_query(call.id)
                file_path = create_excel_output(vip_only=True)
                if file_path:
                    bot.send_document(call.message.chat.id, open(file_path, 'rb'))
                else:
                    bot.send_message(call.message.chat.id, "خطا در ساخت فایل اکسل VIP. لطفا لاگ را بررسی کنید.")
        except Exception as e:
            logging.error(f"خطا در پنل ادمین برای کاربر {user_id}: {e}")
            bot.answer_callback_query(call.id, "خطایی رخ داد.")
            send_developer_error_notification(f"Error in admin panel: {e}")

    elif call.data.startswith("dev_"):
        if user_id != DEVELOPER_ID:
            bot.answer_callback_query(call.id, "شما دسترسی به پنل دولوپر ندارید.")
            return

        try:
            action = call.data.split('_')[1]
            if action == 'panel':
                bot.answer_callback_query(call.id)
                handle_dev_panel(call.message)
            elif action == 'manage_admins':
                bot.answer_callback_query(call.id)
                data = load_data()
                admin_list = "\n".join([str(uid) for uid in data['admins']])
                bot.send_message(call.message.chat.id, f"لیست ادمین‌ها:\n{admin_list}\n\nبرای اضافه کردن ادمین، پیامش را به من فوروارد کنید.\nبرای حذف، آیدی عددی را ارسال کنید.")
            elif action == 'get_logs':
                bot.answer_callback_query(call.id)
                if os.path.exists(LOG_FILE):
                    with open(LOG_FILE, 'rb') as f:
                        bot.send_document(call.message.chat.id, f)
                else:
                    bot.send_message(call.message.chat.id, "فایل لاگ پیدا نشد.")
        except Exception as e:
            logging.error(f"خطا در پنل دولوپر برای کاربر {user_id}: {e}")
            bot.answer_callback_query(call.id, "خطایی رخ داد.")
            send_developer_error_notification(f"Error in dev panel: {e}")

# --- MANAGE ADMINS ---
@bot.message_handler(func=lambda message: message.from_user.id == DEVELOPER_ID and message.text and message.text.isdigit())
def handle_admin_management_by_text(message):


    try:
        admin_id_to_manage = int(message.text)
        data = load_data()

        if admin_id_to_manage in data['admins']:
            data['admins'].remove(admin_id_to_manage)
            save_data(data)
            bot.send_message(message.chat.id, f"کاربر با آیدی {admin_id_to_manage} از لیست ادمین‌ها حذف شد.")
        else:
            data['admins'].append(admin_id_to_manage)
            save_data(data)
            bot.send_message(message.chat.id, f"کاربر با آیدی {admin_id_to_manage} به لیست ادمین‌ها اضافه شد.")
    except Exception as e:
        logging.error(f"خطا در مدیریت ادمین با متن: {e}")
        bot.send_message(message.chat.id, "خطا در مدیریت ادمین.")
        send_developer_error_notification(f"Error managing admin by text: {e}")

@bot.message_handler(content_types=['forwarded'])
def handle_admin_management_by_forward(message):


    if message.from_user.id != DEVELOPER_ID or not message.forward_from:
        return

    try:
        new_admin_id = message.forward_from.id
        data = load_data()

        if new_admin_id not in data['admins']:
            data['admins'].append(new_admin_id)
            save_data(data)
            bot.send_message(message.chat.id, f"کاربر {message.forward_from.first_name} با آیدی {new_admin_id} به عنوان ادمین اضافه شد.")
        else:
            bot.send_message(message.chat.id, "این کاربر قبلا ادمین بوده است.")
    except Exception as e:
        logging.error(f"خطا در مدیریت ادمین با فوروارد: {e}")
        bot.send_message(message.chat.id, "خطا در مدیریت ادمین.")
        send_developer_error_notification(f"Error managing admin by forward: {e}")

# RUN
if __name__ == "__main__":

    load_data()
    bot.polling(none_stop=True)
