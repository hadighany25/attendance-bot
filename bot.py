import sqlite3
import os
from datetime import datetime
from fpdf import FPDF
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIG ---
TOKEN = '8161943789:AAHE-qdQFSJw2rMuuKt3tdY6G9EmValaFXU'
ADMIN_IDS = [5612301669]

# --- INIT DB ---
def init_db():
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    
    # ១. បង្កើត Table បុគ្គលិក (បើមិនទាន់មាន)
    c.execute('''CREATE TABLE IF NOT EXISTS employees 
                 (emp_id TEXT PRIMARY KEY, name TEXT, age INTEGER, phone TEXT, position TEXT, added_by INTEGER)''')
    
    # ២. បន្ថែម Column 'position' បើវាបាត់ពី Database ចាស់ (នេះជាកន្លែងដែលអ្នកត្រូវបន្ថែម)
    try:
        c.execute("ALTER TABLE employees ADD COLUMN position TEXT")
    except sqlite3.OperationalError:
        # បើមានរួចហើយ វានឹងចេញ error តែយើងប្រាប់វាឱ្យ ignore (រំលង)
        pass

    # ៣. បង្កើត Table សម្រាប់កត់ត្រាម៉ោងចេញចូល
    c.execute('''CREATE TABLE IF NOT EXISTS break_sessions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, emp_id TEXT, check_out_time TEXT, 
                  check_in_time TEXT, duration_minutes INTEGER, late_minutes INTEGER, status TEXT, date TEXT)''')
    
    conn.commit()
    conn.close()

# --- HELPERS ---
def generate_short_id():
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    c.execute("SELECT emp_id FROM employees ORDER BY emp_id DESC LIMIT 1")
    last = c.fetchone()
    conn.close()
    if last:
        try: return str(int(last[0]) + 1).zfill(3)
        except: return "001"
    return "001"

def get_now_time(): return datetime.now().strftime('%H:%M:%S')
def get_today(): return datetime.now().strftime('%Y-%m-%d')

# --- PROFESSIONAL PDF CLASS ---
class AttendancePDF(FPDF):
    def header(self):
        # ឡូហ្គោ ឬ ឈ្មោះប្រព័ន្ធ
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'ATTENDANCE & BREAK REPORT', 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.cell(0, 10, f'Report Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'R')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def create_pro_pdf(data, summary, title, filename):
    pdf = AttendancePDF()
    pdf.add_page()
    
    # Section 1: Summary Insights
    pdf.set_font('Arial', 'B', 12)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(0, 10, f"SUMMARY: {title}", 1, 1, 'L', True)
    
    pdf.set_font('Arial', '', 11)
    col_width = 95
    for key, value in summary.items():
        pdf.cell(col_width, 8, f"{key}: {value}", 1, 0, 'L')
        if list(summary.keys()).index(key) % 2 != 0: pdf.ln()
    pdf.ln(10)

    # Section 2: Detail Table
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(50, 50, 150) # Dark Blue Header
    pdf.set_text_color(255, 255, 255)
    
    headers = ['ID', 'Name', 'Out', 'In', 'Dur', 'Late', 'Status']
    widths = [15, 35, 25, 25, 20, 20, 50] # Total 190
    
    for i in range(len(headers)):
        pdf.cell(widths[i], 10, headers[i], 1, 0, 'C', True)
    pdf.ln()

    # Data Rows
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Arial', '', 9)
    for r in data:
        # r = (emp_id, name, out, in, dur, late, date)
        status = "Completed" if r[3] else "On Break"
        if r[5] and r[5] > 0: status += " (Late)"
            
        pdf.cell(widths[0], 8, str(r[0]), 1, 0, 'C')
        pdf.cell(widths[1], 8, str(r[1]), 1)
        pdf.cell(widths[2], 8, str(r[2]), 1, 0, 'C')
        pdf.cell(widths[3], 8, str(r[3] or '-'), 1, 0, 'C')
        pdf.cell(widths[4], 8, f"{r[4] or 0}mn", 1, 0, 'C')
        pdf.cell(widths[5], 8, f"{r[5] or 0}mn", 1, 0, 'C')
        pdf.cell(widths[6], 8, status, 1)
        pdf.ln()
        
    pdf.output(filename)

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    context.user_data.clear()
    kb = [
        ['🔍 ស្ថានភាពបុគ្គលិក', '📊 Dashboard'],
        ['➕ បន្ថែមបុគ្គលិកថ្មី', '👥 បញ្ជីបុគ្គលិក'],
        ['📝 របាយការណ៍', '🔄 Undo'],
        ['🗑️ លុបបុគ្គលិក']
    ]
    await update.message.reply_text(
        "🚀 **Attendance Management System V3.0**\nសូមជ្រើសរើសមុខងារខាងក្រោម៖", 
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), 
        parse_mode='Markdown'
    )

# --- TEXT MESSAGE HANDLER ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, text = update.effective_user.id, update.message.text
    if user_id not in ADMIN_IDS: return

    # បញ្ជីឈ្មោះប៊ូតុង Menu ទាំងអស់
    menus = ['🔍 ស្ថានភាពបុគ្គលិក', '📊 Dashboard', '➕ បន្ថែមបុគ្គលិកថ្មី', '👥 បញ្ជីបុគ្គលិក', '📝 របាយការណ៍', '🔄 Undo', '🗑️ លុបបុគ្គលិក']
    
    # លុប State ចាស់ចោលពេលចុច Menu ណាមួយ
    if text in menus: context.user_data.clear()

    # 1. ប៊ូតុង បន្ថែមបុគ្គលិកថ្មី
    if text == '➕ បន្ថែមបុគ្គលិកថ្មី':
        context.user_data['action'] = 'add'
        await update.message.reply_text("📝 សូមផ្ញើតាមទម្រង់៖ `ឈ្មោះ អាយុ លេខទូរស័ព្ទ តួនាទី` \n\nឧទាហរណ៍៖ `Dara 22 08536665 Staff`", parse_mode='Markdown')
        return

    # 2. ប៊ូតុង ស្ថានភាពបុគ្គលិក
    elif text == '🔍 ស្ថានភាពបុគ្គលិក':
        await update.message.reply_text("🔎 **សូមវាយបញ្ចូល ID ឬ ឈ្មោះបុគ្គលិក ដើម្បីស្វែងរក៖**", parse_mode='Markdown')
        return

    # 3. ប៊ូតុង របាយការណ៍
    elif text == '📝 របាយការណ៍':
        kb = [
            [InlineKeyboardButton("📄 ថ្ងៃនេះ", callback_data="rep_today"), InlineKeyboardButton("📄 ខែនេះ", callback_data="rep_month")],
            [InlineKeyboardButton("📅 កំណត់ចន្លោះថ្ងៃ", callback_data="rep_custom")]
        ]
        await update.message.reply_text("📊 **ជ្រើសរើសប្រភេទរបាយការណ៍ដែលចង់បាន៖**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return

    # 4. ប៊ូតុង បញ្ជីបុគ្គលិក
    elif text == '👥 បញ្ជីបុគ្គលិក':
        conn = sqlite3.connect('attendance_system.db')
        c = conn.cursor()
        c.execute("SELECT emp_id, name, phone FROM employees")
        data = c.fetchall()
        conn.close()
        if not data:
            await update.message.reply_text("❌ មិនទាន់មានបុគ្គលិកទេ!")
            return
        msg = "👥 **បញ្ជីបុគ្គលិកទាំងអស់៖**\n`ID  | NAME | PHONE NUMBER`\n"
        msg += "\n".join([f"• {e[0]} - {e[1]} - {e[2]}" for e in data])
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    # 5. ប៊ូតុង Dashboard
    elif text == '📊 Dashboard':
        conn = sqlite3.connect('attendance_system.db')
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute("SELECT COUNT(*) FROM break_sessions WHERE date=? AND status='on_break'", (today,))
        on_break = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM break_sessions WHERE date=? AND late_minutes > 0", (today,))
        late = c.fetchone()[0]
        conn.close()
        await update.message.reply_text(f"📊 **ស្ថានភាពថ្ងៃនេះ ({today})**\n━━━━━━━━━━━━━━\n🏃 កំពុងសម្រាក់៖ `{on_break}` នាក់\n⏰ យឺតថ្ងៃនេះ៖ `{late}` នាក់", parse_mode='Markdown')
        return

    # 6. ប៊ូតុង Undo (ដំណោះស្រាយបញ្ហាដែលអ្នកជួប)
    elif text == '🔄 Undo':
        conn = sqlite3.connect('attendance_system.db')
        c = conn.cursor()
        # រកមើល Record ចុងក្រោយបង្អស់ក្នុងតារាងសម្រាក់
        c.execute("SELECT id, emp_id, status, date FROM break_sessions ORDER BY id DESC LIMIT 1")
        last_record = c.fetchone()
        
        if last_record:
            rec_id, emp_id, status, date = last_record
            c.execute("DELETE FROM break_sessions WHERE id = ?", (rec_id,))
            conn.commit()
            status_text = "ចេញសម្រាក់" if status == 'on_break' else "ចូលវិញ"
            await update.message.reply_text(f"🔄 **Undo ជោគជ័យ!**\nលុបទិន្នន័យចុងក្រោយរបស់ ID: `{emp_id}` ({status_text}) កាលពី `{date}`", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ មិនមានទិន្នន័យអ្វីត្រូវ Undo ទេ។")
        conn.close()
        return
    elif text == '🗑️ លុបបុគ្គលិក':
        context.user_data['action'] = 'delete_request'
        await update.message.reply_text("🗑️ **សូមវាយ ID ឬ ឈ្មោះបុគ្គលិកដែលអ្នកចង់លុប៖**", parse_mode='Markdown')
        return

    # --- បន្ថែម Logic លុបបុគ្គលិក (ដាក់ក្នុងផ្នែក ACTIONS LOGIC) ---
    action = context.user_data.get('action')
    if action == 'delete_request':
        conn = sqlite3.connect('attendance_system.db')
        c = conn.cursor()
        # ស្វែងរកមើលសិនថាមានបុគ្គលិកហ្នឹងអត់
        c.execute("SELECT emp_id, name FROM employees WHERE emp_id=? OR name LIKE ?", (text, f"%{text}%"))
        emp = c.fetchone()
        
        if emp:
            # បើរកឃើញ ឱ្យគាត់បញ្ជាក់សិន (Confirm) ដើម្បីការពារការលុបច្រឡំ
            keyboard = [
                [InlineKeyboardButton("✅ បាទ/ចាស លុបចោល", callback_data=f"confirm_del_{emp[0]}"),
                 InlineKeyboardButton("❌ អត់ទេ កុំលុប", callback_data="cancel_del")]
            ]
            await update.message.reply_text(
                f"⚠️ **តើអ្នកប្រាកដថាចង់លុបបុគ្គលិកនេះមែនទេ?**\n🆔 ID: `{emp[0]}`\n👤 ឈ្មោះ: `{emp[1]}`\n\n*ការលុបនេះនឹងបាត់ទាំងប្រវត្តិសម្រាក់ទាំងអស់របស់គេ!*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ រកមិនឃើញបុគ្គលិក `{text}` ដើម្បីលុបឡើយ!")
        
        conn.close()
        context.user_data.clear() # លុប State ចោលវិញ
        return
    
    # --- ACTIONS LOGIC (សម្រាប់ការបញ្ចូលទិន្នន័យ) ---
    action = context.user_data.get('action')
    if action == 'add':
        parts = text.split()
        if len(parts) >= 4:
            name, age, phone, pos = parts[0], parts[1], parts[2], " ".join(parts[3:])
            new_id = generate_short_id()
            conn = sqlite3.connect('attendance_system.db')
            c = conn.cursor()
            c.execute("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?)", (new_id, name, int(age), phone, pos, user_id))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ **បន្ថែមបុគ្គលិកជោគជ័យ!**\n🆔 ID: `{new_id}`\n👤 ឈ្មោះ: `{name}`\n🎂 អាយុ: `{age}`\n💼 តួនាទី: `{pos}`\n📞 លេខ: `{phone}`", parse_mode='Markdown')
        else:
            await update.message.reply_text("⚠️ ទម្រង់ខុស! សូមផ្ញើ៖ `ឈ្មោះ អាយុ លេខ តួនាទី`")
        return

    elif action == 'custom_date':
        dates = text.split()
        if len(dates) == 2:
            await generate_and_send_report(update, dates[0], dates[1], f"Report from {dates[0]} to {dates[1]}")
            context.user_data.clear()
        return

    # --- SEARCH FOR ID/NAME (ផ្នែកនេះនឹងរត់តែពេលដែល Text មិនមែនជាប៊ូតុង Menu ខាងលើប៉ុណ្ណោះ) ---
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    c.execute("SELECT emp_id, name FROM employees WHERE emp_id=? OR name LIKE ?", (text, f"%{text}%"))
    emp = c.fetchone()
    
    if emp:
        c.execute("SELECT status FROM break_sessions WHERE emp_id=? AND date=? ORDER BY id DESC LIMIT 1", (emp[0], datetime.now().strftime('%Y-%m-%d')))
        last = c.fetchone()
        btn_text = "📥 Check-in (ចូលវិញ)" if last and last[0] == 'on_break' else "✅ Check-out (ចេញសម្រាក់)"
        call_data = f"in_{emp[0]}" if "in" in btn_text.lower() else f"out_{emp[0]}"
        
        await update.message.reply_text(
            f"👤 **{emp[1]}** (`{emp[0]}`)\nតើអ្នកចង់ធ្វើអ្វី?", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data=call_data)]]), 
            parse_mode='Markdown'
        )
    else:
        # បង្ហាញសារនេះ តែពេល User វាយអក្សរស្វែងរកអ្វីផ្សេងដែលមិនមានក្នុង Database ប៉ុណ្ណោះ
        await update.message.reply_text(f"🔍 រកមិនឃើញបុគ្គលិកឈ្មោះ ឬ ID: `{text}` ទេ! សូមពិនិត្យម្ដងទៀត។", parse_mode='Markdown')
    
    conn.close()

# --- CALLBACK HANDLING ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()

    if data.startswith('out_'):
        emp_id = data.split('_')[1]
        now = get_now_time()
        c.execute("INSERT INTO break_sessions (emp_id, check_out_time, status, date) VALUES (?, ?, 'on_break', ?)", (emp_id, now, get_today()))
        await query.edit_message_text(f"✅ `{emp_id}` **បានចេញសម្រាក់!**\n⏰ ម៉ោងចេញ៖ `{now}`", parse_mode='Markdown')

    elif data.startswith('in_'):
        emp_id = data.split('_')[1]
        now = get_now_time()
        c.execute("SELECT id, check_out_time FROM break_sessions WHERE emp_id=? AND date=? AND status='on_break' ORDER BY id DESC LIMIT 1", (emp_id, get_today()))
        row = c.fetchone()
        if row:
            t_out = datetime.strptime(row[1], '%H:%M:%S')
            t_in = datetime.strptime(now, '%H:%M:%S')
            dur = int((t_in - t_out).seconds / 60)
            late = max(0, dur - 60) # យឺតបើលើសពី 60 នាទី
            c.execute("UPDATE break_sessions SET check_in_time=?, duration_minutes=?, late_minutes=?, status='completed' WHERE id=?", (now, dur, late, row[0]))
            await query.edit_message_text(f"📥 `{emp_id}` **បានចូលមកវិញ!**\n⏰ ចេញ៖ `{row[1]}` | ចូល៖ `{now}`\n⏱ រយៈពេល៖ `{dur}mn` | ⚠️ យឺត៖ `{late}mn`", parse_mode='Markdown')
# --- បន្ថែមផ្នែកលុបបុគ្គលិកនៅត្រង់នេះ ---
    elif data.startswith('confirm_del_'):
        emp_id = data.split('_')[2]
        # ១. លុបឈ្មោះបុគ្គលិកចេញពីតារាង employees
        c.execute("DELETE FROM employees WHERE emp_id = ?", (emp_id,))
        # ២. លុបប្រវត្តិសម្រាក់ទាំងអស់របស់បុគ្គលិកនោះចេញពីតារាង break_sessions
        c.execute("DELETE FROM break_sessions WHERE emp_id = ?", (emp_id,))
        
        conn.commit()
        await query.edit_message_text(f"✅ **បានលុបបុគ្គលិក ID: `{emp_id}` និងទិន្នន័យពាក់ព័ន្ធទាំងអស់ រួចរាល់!**", parse_mode='Markdown')

    elif data == 'cancel_del':
        await query.edit_message_text("❌ **ការលុបត្រូវបានបោះបង់។**", parse_mode='Markdown')
    elif data == "rep_today":
        await generate_and_send_report(query, get_today(), get_today(), "Daily Report")
    elif data == "rep_month":
        start_month = datetime.now().strftime('%Y-%m-01')
        await generate_and_send_report(query, start_month, get_today(), "Monthly Report")
    elif data == "rep_custom":
        await query.message.reply_text("📅 សូមផ្ញើថ្ងៃចាប់ផ្ដើម និងថ្ងៃបញ្ចប់ (ឧទាហរណ៍៖ `2026-04-01 2026-04-06`)៖")
        context.user_data['action'] = 'custom_date'

    conn.commit()
    conn.close()
    await query.answer()

# --- REPORT GENERATION & SEND ---
async def generate_and_send_report(target, start, end, title):
    conn = sqlite3.connect('attendance_system.db')
    c = conn.cursor()
    
    # ឆែកមើលថា តើនេះជារបាយការណ៍ប្រចាំថ្ងៃ ឬប្រចាំខែ (តាមរយៈចំណងជើង)
    is_monthly = "Monthly" in title or (start != end)

    if is_monthly:
        # --- LOGIC សម្រាប់របាយការណ៍ប្រចាំខែ (សរុបម្នាក់ៗ) ---
        query = """
            SELECT b.emp_id, e.name, 
                   COUNT(b.id) as total_breaks, 
                   SUM(CASE WHEN b.late_minutes > 0 THEN 1 ELSE 0 END) as total_late_count,
                   AVG(b.duration_minutes) as avg_dur,
                   SUM(b.late_minutes) as total_late_mins
            FROM break_sessions b 
            JOIN employees e ON b.emp_id = e.emp_id 
            WHERE b.date BETWEEN ? AND ?
            GROUP BY b.emp_id
        """
        headers = ['ID', 'Name', 'Total Breaks', 'Total Late', 'Avg Dur', 'Late Mins']
        widths = [20, 50, 30, 30, 30, 30]
    else:
        # --- LOGIC សម្រាប់របាយការណ៍ប្រចាំថ្ងៃ (លម្អិត) ---
        query = """
            SELECT b.emp_id, e.name, b.check_out_time, b.check_in_time, 
                   b.duration_minutes, b.late_minutes, b.status 
            FROM break_sessions b 
            JOIN employees e ON b.emp_id = e.emp_id 
            WHERE b.date BETWEEN ? AND ?
        """
        headers = ['ID', 'Name', 'Out', 'In', 'Dur', 'Late', 'Status']
        widths = [15, 35, 25, 25, 20, 20, 50]

    c.execute(query, (start, end))
    rows = c.fetchall()
    
    if not rows:
        msg = "❌ គ្មានទិន្នន័យសម្រាប់កាលបរិច្ឆេទនេះទេ!"
        if hasattr(target, 'message'): await target.message.reply_text(msg)
        else: await target.reply_text(msg)
        return

    # បង្កើត PDF ថ្មី
    filename = f"Report_{start}_to_{end}.pdf"
    pdf = AttendancePDF()
    pdf.add_page()
    
    # គ្រោងក្បាលតារាង
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(50, 50, 150)
    pdf.set_text_color(255, 255, 255)
    for i in range(len(headers)):
        pdf.cell(widths[i], 10, headers[i], 1, 0, 'C', True)
    pdf.ln()

    # បញ្ចូលទិន្នន័យ
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Arial', '', 9)
    for r in rows:
        for i in range(len(r)):
            val = str(r[i]) if r[i] is not None else "-"
            # កែសម្រួលការបង្ហាញលេខឱ្យស្អាត (បើជាមធ្យមភាគ)
            if isinstance(r[i], float): val = f"{r[i]:.1f}"
            pdf.cell(widths[i], 8, val, 1, 0, 'C')
        pdf.ln()
        
    pdf.output(filename)
    
    # ផ្ញើទៅ Telegram
    caption = f"📄 {title} ({start} ដល់ {end})"
    if hasattr(target, 'message'):
        with open(filename, 'rb') as f: await target.message.reply_document(f, caption=caption)
    else:
        with open(filename, 'rb') as f: await target.reply_document(f, caption=caption)
    
    os.remove(filename)
    conn.close()

# --- MAIN ---
if __name__ == '__main__':
    init_db()
    print("🚀 Bot is starting...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.run_polling()