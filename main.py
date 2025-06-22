import time
import streamlit as st
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import os
import json
import sqlite3
import bcrypt
import smtplib
from email.message import EmailMessage
import google.generativeai as genai
import base64
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIGURATION & CONSTANTS ---
DB_FILE = "s_team_app_final_v13.db"

# --- 2. DATABASE & USER MANAGEMENT ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT DEFAULT 'standard',
            first_name TEXT, last_name TEXT, email TEXT UNIQUE
        )
    """)
    try:
        c.execute("PRAGMA table_info(users)")
        existing_columns = [column[1] for column in c.fetchall()]
        if 'first_name' not in existing_columns: c.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
        if 'last_name' not in existing_columns: c.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
        if 'email' not in existing_columns: c.execute("ALTER TABLE users ADD COLUMN email TEXT")
    except sqlite3.OperationalError: pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            protocol_number TEXT PRIMARY KEY, client_company TEXT, client_vat_id TEXT,
            client_address TEXT, client_tk TEXT, client_area TEXT, client_phone TEXT,
            installations INTEGER, unit_price REAL, offer_valid_until TEXT, issue_date TEXT,
            include_tech_description BOOLEAN, include_tax_solutions BOOLEAN, tax_solution_choice TEXT,
            e_invoicing_package TEXT, custom_title TEXT, custom_content TEXT,
            full_offer_data TEXT, created_by_user TEXT
        )
    """)
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        admin_username = "admin"; admin_password = "admin_password"
        c.execute("INSERT INTO users (username, password_hash, role, first_name, last_name, email) VALUES (?, ?, ?, ?, ?, ?)",
                  (admin_username, hash_password(admin_password), 'admin', 'Admin', 'User', 'admin@example.com'))
    conn.commit()
    conn.close()

def hash_password(password): return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
def check_password(password, hashed_password): return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def add_user_to_db(username, password, first_name, last_name, email, role='standard'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash, first_name, last_name, email, role) VALUES (?, ?, ?, ?, ?, ?)", (username, hash_password(password), first_name, last_name, email, role))
        conn.commit()
        return True, ""
    except sqlite3.IntegrityError: return False, "Το username ή το email υπάρχει ήδη."
    finally: conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT password_hash, role, first_name, last_name, email FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    if result and check_password(password, result[0]):
        return True, {"role": result[1], "first_name": result[2], "last_name": result[3], "email": result[4]}
    return False, None

def save_offer_to_db(offer_data, created_by_user):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    offer_data['created_by_user'] = created_by_user
    try:
        c.execute("INSERT OR REPLACE INTO offers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (offer_data.get('protocol_number'), offer_data.get('client_company'), offer_data.get('client_vat_id'),
                   offer_data.get('client_address'), offer_data.get('client_tk'), offer_data.get('client_area'),
                   offer_data.get('client_phone'), offer_data.get('installations'), offer_data.get('unit_price'),
                   offer_data.get('offer_valid_until'), offer_data.get('issue_date'),
                   offer_data.get('include_tech_description', True), offer_data.get('include_tax_solutions', True),
                   offer_data.get('tax_solution_choice'), offer_data.get('e_invoicing_package'),
                   offer_data.get('custom_title'), offer_data.get('custom_content'),
                   json.dumps(offer_data, ensure_ascii=False), created_by_user))
        conn.commit()
    finally: conn.close()

def load_offers_from_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = "SELECT full_offer_data FROM offers ORDER BY cast(substr(protocol_number, 3) as integer) DESC"
    c.execute(query)
    all_offers = [json.loads(row[0]) for row in c.fetchall() if row[0]]
    conn.close()
    return all_offers

def get_all_usernames():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username FROM users ORDER BY username")
    usernames = [row[0] for row in c.fetchall()]
    conn.close()
    return usernames

def send_email_with_attachment(recipient_email, subject, body, pdf_data=None, filename=None):
    try:
        sender_email = st.secrets["SENDER_EMAIL"]; sender_password = st.secrets["SENDER_PASSWORD"]
        msg = EmailMessage()
        msg['Subject'] = subject; msg['From'] = sender_email; msg['To'] = recipient_email
        msg.set_content(body)
        if pdf_data and filename:
            msg.add_attachment(pdf_data, maintype='application', subtype='octet-stream', filename=filename)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
        return True, "Το Email στάλθηκε με επιτυχία!"
    except Exception as e:
        return False, f"Αποτυχία αποστολής Email: {e}"

@st.cache_resource
def get_gemini_model():
    return genai.GenerativeModel('gemini-1.5-flash')

def get_user_by_email(email):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE email = ?", (email,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None
    
def update_user_details(username, first_name, last_name, email):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET first_name = ?, last_name = ?, email = ? WHERE username = ?", (first_name, last_name, email, username))
        conn.commit()
        return True, "Τα στοιχεία σας ενημερώθηκαν!"
    except sqlite3.IntegrityError:
        return False, "Το email που δώσατε χρησιμοποιείται ήδη."
    finally: conn.close()

def change_user_password(username, old_password, new_password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    if result and check_password(old_password, result[0]):
        c.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hash_password(new_password), username))
        conn.commit()
        conn.close()
        return True, "Ο κωδικός σας άλλαξε με επιτυχία."
    conn.close()
    return False, "Ο παλιός κωδικός δεν είναι σωστός."

def display_offer_details(offer_data):
    details_to_show = []
    display_order = [
        ('client_company', 'Πελάτης'), ('client_vat_id', 'ΑΦΜ'), ('client_address', 'Διεύθυνση'),
        ('client_tk', 'Τ.Κ.'), ('client_area', 'Περιοχή'), ('client_phone', 'Τηλέφωνο'),
        ('installations', 'Εγκαταστάσεις'), ('unit_price', 'Τιμή Μονάδας (€)'), 
        ('tax_solution_choice', 'Φορολογική Λύση'), ('e_invoicing_package', 'Πακέτο Παρόχου')
    ]
    for key, label in display_order:
        value = offer_data.get(key)
        if value is not None and str(value).strip() != '':
            details_to_show.append(f"- **{label}:** `{value}`")
    if details_to_show:
        st.markdown("\n".join(details_to_show))
    else:
        st.info("Δεν υπάρχουν αποθηκευμένες λεπτομέρειες για αυτήν την προσφορά.")

# --- 3. PDF GENERATION LOGIC ---
class OfferPDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            if not os.path.exists('DejaVuSans.ttf') or not os.path.exists('DejaVuSans-Bold.ttf'): st.warning("Δεν βρέθηκαν οι γραμματοσειρές 'DejaVuSans'.")
            self.add_font('DejaVu', '', 'DejaVuSans.ttf')
            self.add_font('DejaVu', 'B', 'DejaVuSans-Bold.ttf')
        except Exception as e:
            st.error(f"Σφάλμα στις γραμματοσειρές: {e}"); st.stop()
    def footer(self):
        self.set_y(-15); self.set_font('DejaVu', '', 8); self.cell(0, 10, f'{self.page_no()}', align='C')

def create_page_1_intro(pdf, data, toc_entries):
    pdf.add_page()
    if os.path.exists('logo.png'): pdf.image('logo.png', x=150, y=10, w=50)
    if os.path.exists('upsales_logo.png'): pdf.image('upsales_logo.png', x=105, y=10, w=40)
    pdf.set_draw_color(100, 100, 100)
    pdf.set_font('DejaVu', 'B', 12); pdf.set_xy(15, 40); pdf.cell(0, 10, 'ΣΤΟΙΧΕΙΑ ΠΕΛΑΤΗ')
    pdf.set_font('DejaVu', '', 10); pdf.set_xy(15, 50)
    info_lines = []
    if data.get("client_company"): info_lines.append(f"Επωνυμία: {data['client_company']}")
    if data.get("client_vat_id"): info_lines.append(f"ΑΦΜ: {data['client_vat_id']}")
    if data.get("client_address"): info_lines.append(f"Οδός: {data['client_address']}")
    if data.get("client_tk") and data.get("client_area"): info_lines.append(f"ΤΚ: {data['client_tk']} - Περιοχή: {data['client_area']}")
    if data.get("client_phone"): info_lines.append(f"Τηλέφωνο: {data['client_phone']}")
    client_info_text = "\n".join(info_lines)
    pdf.multi_cell(90, 6, client_info_text, border=1)
    pdf.set_xy(120, 50); pdf.multi_cell(75, 7, f"Αριθμός Πρωτοκόλλου: {data.get('protocol_number', 'N/A')}\nΗμερομηνία Έκδοσης: {data.get('issue_date', 'N/A')}", border=1)
    pdf.set_xy(15, 90); pdf.set_font('DejaVu', 'B', 14)
    offer_title = data.get('custom_title') or "Πρόταση Λογισμικού Εμπορικής Διαχείρισης"
    pdf.cell(0, 10, offer_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    intro_text = data.get('custom_content') or (
        "Αξιότιμε συνεργάτη,\n"
        "σε συνέχεια της επικοινωνίας μας, σας αποστέλλουμε την πρόταση της εταιρίας μας σχετικά με το "
        "λογισμικό εμπορικής διαχείρισης. Η S-Team έχει πάντοτε ως γνώμονα την καλύτερη και την αρτιότερη κάλυψη των "
        "αναγκών της επιχείρησής σας. Διαθέτει πολυετή εμπειρία, βαθιά τεχνογνωσία και υψηλή εξειδίκευση σε προϊόντα "
        "και λύσεις μηχανογράφησης επιχειρήσεων. Η αποδεδειγμένη ικανοποίηση των πελατών της εταιρίας είναι "
        "στοιχεία που χαρακτηρίζουν την S-Team. Συνημμένα θα βρείτε τους όρους και τις προϋποθέσεις της προσφοράς "
        "μας. Παραμένουμε στη διάθεση σας για οποιαδήποτε συμπληρωματική πληροφορία.\n\nΜε εκτίμηση,\nΤμήμα Υποστήψης Πελατών.")
    pdf.set_xy(15, 105); pdf.set_font('DejaVu', '', 10); pdf.multi_cell(0, 5, intro_text)
    pdf.set_xy(15, pdf.get_y() + 10); pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 10, "Περιεχόμενα", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', '', 10)
    for item_text, page_num in toc_entries:
        pdf.cell(80, 6, item_text); pdf.cell(0, 6, str(page_num), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')

def create_page_2_tech_desc(pdf):
    pdf.add_page(); pdf.set_font('DejaVu', 'B', 14); pdf.cell(0, 10, "2. ΤΕΧΝΙΚΗ ΠΕΡΙΓΡΑΦΗ", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)
    pdf.set_font('DejaVu', '', 10)
    tech_points_1 = [
        "UpSales. Το εμπορικό πρόγραμμα διαχείρισης κάθε επιχείρησης που συνδυάζει άψογα ποιότητα - τιμή - ευκολία χρήσης.",
        "Μία εμπορική εφαρμογή προσιτή σε κάθε επιχείρηση, λόγω χαμηλού κόστους απόκτησης και ετήσιας συντήρησης.",
        "Εφαρμογή φιλική σε κάθε χρήστη ανεξαρτήτως επιπέδου γνώσεων Η/Υ.",
        "Σχεδιασμένο έτσι ώστε ο χρήστης με ελάχιστες κινήσεις να επεξεργάζεται όλες τις λειτουργίες του προγράμματος στο λιγότερο δυνατό χρόνο.",
        "Τεχνολογία αιχμής. Η ανάπτυξή του έγινε με τα πλέον σύγχρονα εργαλεία προγραμματισμού, προσφέροντας ευελιξία και εφαρμογή στις ανάγκες κάθε επιχείρησης ξεχωριστά.",
        "Το πλήρως στελεχωμένο τμήμα ανάπτυξης λογισμικού της S-Team εγγυάται την άψογη υποστήριξη της επιχείρησης σε σύγχρονες και μελλοντικές προκλήσεις."
    ]
    for point in tech_points_1: pdf.multi_cell(0, 5, f"•  {point}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(2)
    pdf.set_font('DejaVu', 'B', 11); pdf.cell(0, 10, "Η Βασική έκδοση περιλαμβάνει:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', '', 10)
    tech_points_2 = [
        "Διαχείριση πελατών-προμηθευτών, ειδών-υπηρεσιών, αποθήκης, πωλήσεων (λιανικής & χονδρικής) - αγορών, εισπράξεων-πληρωμών-αξιογράφων.",
        "Μεταφορά εγγραφών πωλήσεων-αγορών- χρηματοοικονομικών σε πλήθος λογιστικών εφαρμογών μειώνοντας τον χρόνο επεξεργασίας των λογιστών και ελαχτοποιώντας την πιθανότητα ανθρώπινου σφάλματος στην καταχώρηση των στοιχείων.",
        "Εξαγωγή αρχείων Μηνιαίων Καταστάσεων Πελατών Προμηθευτών και Συναλλαγών έτοιμα για αποστολή στην Γενική Γραμματεία Πληροφοριακών Συστημάτων.",
        "Δυνατότητα απευθείας σύνδεσης με πλήθος φορολογικών μηχανισμών για την έκδοση λιανικών αποδείξεων.",
        "Πληθώρα εκτυπώσεων για είδη, πελάτες-προμηθευτές, πωλήσεων, αγορών, χρηματοοικονομικών, καθώς επίσης ένας νέος επαναστατικός τρόπος εκτύπωσης με φίλτρα ώστε να βγάζετε ό,τι αποτελέσματα θέλετε σύμφωνα με τις ανάγκες σας."
    ]
    for point in tech_points_2: pdf.multi_cell(0, 5, f"•  {point}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(2)

def create_page_3_financials(pdf, data):
    pdf.add_page(); pdf.set_font('DejaVu', 'B', 14); pdf.cell(0, 10, "3. ΟΙΚΟΝΟΜΙΚΗ ΠΡΟΤΑΣΗ", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)
    pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 8, "Βασική έκδοση UpSales", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', '', 10); pdf.multi_cell(0, 5, "Σας αποστέλλουμε οικονομική προσφορά για την μηχανογράφηση / μηχανοργάνωση της εταιρείας σας.", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)
    pdf.set_fill_color(240, 240, 240); pdf.set_font('DejaVu', 'B', 10)
    pdf.cell(100, 8, "ΠΕΡΙΓΡΑΦΗ", 1, 0, 'L', 1); pdf.cell(30, 8, "ΕΓΚΑΤΑΣΤΑΣΗ", 1, 0, 'C', 1); pdf.cell(60, 8, "ΤΙΜΗ ΜΟΝΑΔΟΣ (€)", 1, 1, 'C', 1)
    pdf.set_font('DejaVu', '', 10)
    items_desc = "Εμπορικό UpSales, περιλαμβάνει:\n• Άδεια Χρήσης Λογισμικού για ένα έτος\n• Εγκατάσταση & Παραμετροποίηση προγράμματος\n• Εκπαίδευση"
    y1 = pdf.get_y(); pdf.multi_cell(100, 5, items_desc, 1, 'L'); h = pdf.get_y() - y1
    pdf.set_xy(110, y1); pdf.cell(30, h, '1', 1, 0, 'C'); pdf.cell(60, h, f"{data.get('unit_price', 0.0):.2f}", 1, 1, 'R')
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(0, 6, "Στις παραπάνω τιμές ΔΕΝ συμπεριλαμβάνεται Φ.Π.A.", 0, 1, 'R'); pdf.ln(10)
    pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 8, "Άδεια Χρήσης Λογισμικού", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_fill_color(240, 240, 240); pdf.set_font('DejaVu', 'B', 10)
    pdf.cell(130, 8, "ΠΕΡΙΓΡΑΦΗ", 1, 0, 'L', 1); pdf.cell(60, 8, "ΤΙΜΗ", 1, 1, 'C', 1)
    pdf.set_font('DejaVu', '', 10);
    pdf.multi_cell(130, 5, "Ετήσια Άδεια Χρήσης Λογισμικού που περιλαμβάνει νέες εκδόσεις (Μετά το 1ο έτος)", 1, 'L');
    y1 = pdf.get_y() - 10; pdf.set_xy(140, y1); pdf.cell(60, 10, "120€ / Εγκατάσταση", 1, 1, 'C');
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(0, 6, "Στις παραπάνω τιμές ΔΕΝ συμπεριλαμβάνεται Φ.Π.A.", 0, 1, 'R'); pdf.ln(10)
    pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 8, "Υπηρεσίες", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', '', 10); pdf.multi_cell(0, 5, "Λόγω των διαφορετικών αναγκών και απαιτήσεων κάθε επιχείρησης, προτείνεται η Προαγορά Ωρών Υποστήριξης, καθώς παρέχεται Παραμετροποίηση και Τεχνική Υποστήριξη.", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)
    pdf.set_fill_color(240, 240, 240); pdf.set_font('DejaVu', 'B', 10);
    pdf.cell(110, 8, "ΠΕΡΙΓΡΑΦΗ ΣΥΜΒΟΛΑΙΟΥ ΥΠΟΣΤΗΡΙΞΗΣ", 1, 0, 'C', 1); pdf.cell(30, 8, "ΩΡΕΣ", 1, 0, 'C', 1); pdf.cell(50, 8, "ΑΞΙΑ (€)", 1, 1, 'C', 1)
    support_data = [["Συμβόλαιο Τηλεφωνικής & Απομακρομισμένης Υποστήριξης", "2 ώρες", 150.00], ["", "5 ώρες", 270.00], ["", "10 ώρες", 520.00], ["", "20 ώρες", 940.00], ["", "30 ώρες", 1450.00], ["", "50 ώρες", 2250.00]]
    pdf.set_font('DejaVu', '', 10)
    for row in support_data: pdf.cell(110, 6, row[0], 1); pdf.cell(30, 6, row[1], 1, 0, 'C'); pdf.cell(50, 6, f"{row[2]:.2f}", 1, 1, 'R')
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(0, 6, "Στις παραπάνω τιμές ΔΕΝ συμπεριλαμβάνεται Φ.Π.A.", 0, 1, 'R'); pdf.ln(5)
    pdf.set_font('DejaVu', 'B', 11); pdf.cell(0, 8, "Πλεονεκτήματα:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    advantages = ["ΔΕΝ έχουν ημερολογιακό περιορισμό", "Έχουν χαμηλό κόστος ώρας", "Υποστήριξη όταν τη χρειάζεστε", "Λήγουν μόνο όταν εξαντληθούν οι ώρες προαγοράς", "Καλύπτει Παραμετροποίηση, Εκπαίδευση, Επίσκεψη Τεχνικού, Remote Υποστήριξη", "Ελάχιστη χρέωση 10λεπτά ανά τηλεφωνική κλήση.", "Χρέωση πραγματικού χρόνου υποστήριξης."]
    pdf.set_font('DejaVu', '', 10)
    for advantage in advantages: pdf.multi_cell(0, 5, f"•  {advantage}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

def create_page_4_tax_solutions(pdf, data):
    pdf.add_page(); pdf.set_font('DejaVu', 'B', 14); pdf.cell(0, 10, "4. ΛΥΣΕΙΣ ΦΟΡΟΛΟΓΙΚΗΣ ΣΗΜΑΝΣΗΣ", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)
    pdf.set_fill_color(240, 240, 240); pdf.set_font('DejaVu', 'B', 10)
    pdf.cell(140, 8, "ΦΟΡΟΛΟΓΙΚΗ ΣΗΜΑΝΣΗ", 1, 0, 'C', 1); pdf.cell(50, 8, "ΤΙΜΗ", 1, 1, 'C', 1)
    pdf.set_font('DejaVu', '', 10)
    pdf.cell(140, 8, "ΦΟΡΟΛΟΓΙΚΟΣ ΜΗΧΑΝΙΣΜΟΣ SAMTEC NEXT AI", 1, 0); pdf.cell(50, 8, "480.00 € + ΦΠΑ", 1, 1, 'R'); pdf.ln(5)
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(190, 8, "ΠΑΡΟΧΟΣ Impact e-invoicing", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    e_invoice_header_defs = [("Πάκετο EINVOICING\n(ετήσια συνδρομή)", 35), ("Αξία Πελάτη", 20),("Μέγιστος Αριθμός\nΑποδείξεων Λιανικής", 25), ("Μέγιστος Αριθμός\nΠαραστατικών Χονδρικής", 25), ("Μέγιστος Αριθμός\nΠαραστατικών B2G", 25), ("Τιμή ανά\nΠαραστατικό Λιανικής", 20), ("Τιμή ανά\nΠαραστατικό Χονδρικής", 20), ("Τιμή ανά\nΠαραστατικό B2G", 20), ("-50% ΠΡΟΣΦΟΡΑ\nΕΩΣ 20/03/25", 25)]
    e_invoice_data = [
        ["Service Pack Fuel 25K", "250 €", "25,000", "5,000", "1,000", "0.0100 €", "0.0500 €", "0.25 €", "125 €"], ["Service Pack Fuel 50K", "450 €", "50,000", "10,000", "2,000", "0.0090 €", "0.0450 €", "0.23 €", "225 €"],
        ["Service Pack Fuel 75K", "600 €", "75,000", "15,000", "3,000", "0.0080 €", "0.0400 €", "0.20 €", "300 €"], ["Service Pack Fuel 100K", "700 €", "100,000", "20,000", "4,000", "0.0070 €", "0.0350 €", "0.18 €", "350 €"],
        ["Service Pack Fuel 150K", "900 €", "150,000", "30,000", "6,000", "0.0060 €", "0.0300 €", "0.15 €", "450 €"], ["Service Pack Fuel 250K", "1,000 €", "250,000", "50,000", "10,000", "0.0040 €", "0.0200 €", "0.10 €", "500 €"],
        ["Service Pack Fuel 500K", "1,250 €", "500,000", "50,000", "10,000", "0.0025 €", "0.0125 €", "0.06 €", "625 €"], ["Service Pack Fuel 1M", "2,000 €", "1,000,000", "200,000", "40,000", "0.0020 €", "0.0100 €", "0.05 €", "1,000 €"]
    ]
    with pdf.table(col_widths=[w for _, w in e_invoice_header_defs], text_align="C", line_height=4) as table:
        header_row = table.row(); pdf.set_font('DejaVu', 'B', 6); pdf.set_fill_color(146, 208, 80)
        for text, _ in e_invoice_header_defs: header_row.cell(text, border=1)
        pdf.set_font('DejaVu', '', 8)
        for row_data in e_invoice_data:
            current_row = table.row()
            for i, cell_text in enumerate(row_data):
                pdf.set_fill_color(255, 192, 0) if i == len(row_data) - 1 else pdf.set_fill_color(255, 255, 255)
                current_row.cell(cell_text, border=1)
    pdf.ln(10)
    pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 8, "Επιλογές Πελάτη & Συνολικό Κόστος", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(2)
    pdf.set_fill_color(240, 240, 240); pdf.set_font('DejaVu', 'B', 10)
    pdf.cell(140, 8, "ΠΕΡΙΓΡΑΦΗ", 1, 0, 'L', 1); pdf.cell(50, 8, "ΠΟΣΟ (€)", 1, 1, 'R', 1)
    pdf.set_font('DejaVu', '', 10)
    total_cost = 0.0
    upsales_cost = data.get('installations', 1) * data.get('unit_price', 0.0)
    pdf.cell(140, 7, f"{data.get('installations', 1)} Εγκαταστάσεις UpSales @ {data.get('unit_price', 0.0):.2f}€", 1, 0); pdf.cell(50, 7, f"{upsales_cost:.2f}", 1, 1, 'R')
    total_cost += upsales_cost
    e_invoicing_prices = {"Service Pack Fuel 25K": 250, "Service Pack Fuel 50K": 450, "Service Pack Fuel 75K": 600, "Service Pack Fuel 100K": 700, "Service Pack Fuel 150K": 900, "Service Pack Fuel 250K": 1000, "Service Pack Fuel 500K": 1250, "Service Pack Fuel 1M": 2000}
    if data.get('tax_solution_choice') == "Φορολογικός Μηχανισμός":
        pdf.cell(140, 7, "Φορολογικός Μηχανισμός SAMTEC NEXT AI", 1, 0); pdf.cell(50, 7, "480.00", 1, 1, 'R')
        total_cost += 480.0
    elif data.get('tax_solution_choice') == "Πάροχος" and data.get('e_invoicing_package'):
        package_name = data['e_invoicing_package']
        package_price = e_invoicing_prices.get(package_name, 0.0)
        pdf.cell(140, 7, f"Πάροχος Impact e-invoicing ({package_name})", 1, 0); pdf.cell(50, 7, f"{package_price:.2f}", 1, 1, 'R')
        total_cost += package_price
    pdf.set_font('DejaVu', 'B', 12)
    pdf.cell(140, 10, "ΣΥΝΟΛΙΚΟ ΚΟΣΤΟΣ ΠΡΟ ΦΠΑ:", 1, 0, 'R'); pdf.cell(50, 10, f"{total_cost:.2f} €", 1, 1, 'R')

def create_page_5_terms(pdf, data):
    pdf.add_page(); pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 10, "5. ΟΡΟΙ ΚΑΙ ΠΡΟΥΠΟΘΕΣΕΙΣ", new_x=XPos.LMARGIN, new_y=YPos.NEXT);
    def add_section(title, points, is_bulleted=True):
        pdf.set_font('DejaVu', 'B', 11); pdf.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(1)
        pdf.set_font('DejaVu', '', 9)
        for point in points:
            prefix = "•  " if is_bulleted else ""
            pdf.multi_cell(0, 5, f"{prefix}{point}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(1)
    add_section("Τι καλύπτουν τα Συμβόλαια Προαγοράς Ωρών", ["1. Τηλεφωνική & Remote Υποστήριξη Δευτ-Παρ 09:00-17:00.", "2. Άμεση υποστήριξη ή σας καλούμε εμείς το αργότερο σε 30λεπτά από την κλήση.", "3. Επίσκεψη στο χώρο του πελάτη κατόπιν ραντεβού.", "4. Θέματα που σχετίζονται με τις εφαρμογές και την σωστή λειτουργία των Η/Υ ή Servers – Hardware, Printer-Δίκτυο και μπορούν να επιλυθούν μέσω Remote Support."], is_bulleted=False)
    add_section("Σημειώσεις", ["1. Για υποστήριξη έκτος ωρών εργασίας, ισχύουν οι επιπλέον επιβαρύνσεις: α) 50% από 17:00 ως και 21:00 β) 100% από 21:00 ως και 24:00, για Σάββατο & Κυριακή καθώς και επίσημες αργίες γ) Δευτέρα-Κυριακή δεν λειτουργεί το Support από 00:01 – 09:00", "2. H τιμολόγηση των ωρών προαγοράς γίνεται με την παραγγελία. Για να ισχύουν τα παραπάνω πακέτα προαγοράς ωρών, θα πρέπει να έχει προηγηθεί πλήρης εξόφληση του τιμολογιου.", "3. Στα παραπάνω δεν περιλαμβάνεται περαιτέρω ανάπτυξη της εφαρμογής. Τα κόστη προκύπτουν κατόπιν ανάλυσης των απαιτήσεων του πελάτη.", "4. Οι εκτός έδρας εργασίες επιβαρύνονται με επιπλέον κόστος 0,60€/χλμ + διόλια + έξοδα διαμονής."], is_bulleted=False)
    add_section("Ειδικοί Όροι", ["Όλες οι εργασίες θα γίνουν μέσω απομακρομισμένης πρόσβασης", "Η εκπαίδευση γίνεται σε ένα και μόνο άτομο."])
    add_section("Τιμές", ["Οι τιμές του παρόντος εγγράφου δίνονται σε ευρώ (€) και δεν περιλαμβάνουν Φ.Π.A.", "Οι τιμές περιλαμβάνουν μεταφορικά έξοδα για παράδοση σε χώρο που θα μας υποδείξετε, εντός των ορίων του νομού Αττικής. Για αποστολές εκτός νομού Αττικής το κόστος των μεταφορικών επιβαρύνει τον πελάτη."])
    add_section("Τρόποι πληρωμής", ["Προκαταβολή του 50% με κατάθεση σε τραπεζικό λογαριασμό της εταιρείας και το υπόλοιπο 50% με την ολοκλήρωση των εργασιών."])
    pdf.ln(2)
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(40, 7, "Τράπεζα", 1); pdf.cell(75, 7, "ΙΒΑΝ", 1); pdf.cell(75, 7, "Δικαιούχος", 1, 1)
    pdf.set_font('DejaVu', '', 10)
    pdf.cell(40, 7, "Πειραιώς", 1); pdf.cell(75, 7, "GR45 0172 1830 00 51 8307 0951 644", 1); pdf.cell(75, 7, "S-Team OE", 1, 1)
    pdf.cell(40, 7, "Eurobank", 1); pdf.cell(75, 7, "GR60 0260 3530 00 08 6020 0518 561", 1); pdf.cell(75, 7, "S-Team OE", 1, 1)
    pdf.ln(5)
    add_section("Χρόνος Παράδοσης", ["Εντός 10 - 15 ημερών από την έγγραφη ανάθεση της παραγγελίας σας.", "Ο χρόνος παράδοσης του εξοπλισμού μπορεί να διαφοροποιείται, ανάλογα με τη διαθεσιμότητα των προϊόντων από τον κατασκευαστή."])
    add_section("Ισχύς Προσφοράς", [f"Η πρόταση ισχύει έως {data.get('offer_valid_until', 'N/A')}"])

def create_page_6_acceptance(pdf, data):
    pdf.add_page(); pdf.set_font('DejaVu', 'B', 14); pdf.cell(0, 10, "6. ΣΥΜΠΛΗΡΩΣΗ ΣΤΟΙΧΕΙΩΝ", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); pdf.ln(10)
    pdf.set_font('DejaVu', '', 10)
    pdf.multi_cell(0, 5, "Για την αποδοχή της παραπάνω προσφοράς, παρακαλείσθε να επιστρέψετε υπογεγραμμένη και σφραγισμένη την παρούσα σελίδα.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); pdf.ln(20)
    col1_x = pdf.get_x(); col2_x = col1_x + 100; y_start = pdf.get_y()
    pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Από:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Υπεύθυνος:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Τηλέφωνο:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Fax:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Ημερομηνία:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    y_end = pdf.get_y()
    pdf.set_xy(col2_x, y_start)
    pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Προς:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "S TEAM", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(col2_x, pdf.get_y()); pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Τηλέφωνο:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "2108040424", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(col2_x, pdf.get_y()); pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "E-MAIL:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "acc@s-team.gr", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(col2_x, pdf.get_y()); pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Υπόψη:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "Τμήμα Πωλήσεων", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(y_end + 10)
    pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 10, "ΠΑΡΑΤΗΡΗΣΕΙΣ", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.multi_cell(0, 20, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(pdf.get_y() + 25); pdf.set_font('DejaVu', 'B'); pdf.cell(0, 10, "Υπογραφή - Σφραγίδα Επιχείρησης", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_y(pdf.get_y() + 20)
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(40, 10, "ΑΡ. ΠΡΩΤ.:", align='R'); pdf.set_font('DejaVu', ''); pdf.cell(50, 10, data.get('protocol_number', ''))

def generate_pdf_data(data):
    pdf = OfferPDF('P', 'mm', 'A4')
    sections = [
        {"id": "intro", "title": "ΕΙΣΑΓΩΓΗ", "func": create_page_1_intro, "data": True, "always": True},
        {"id": "tech", "title": "ΤΕΧΝΙΚΗ ΠΕΡΙΓΡΑΦΗ", "func": create_page_2_tech_desc, "data": False, "key": "include_tech_description"},
        {"id": "financials", "title": "ΟΙΚΟΝΟΜΙΚΗ ΠΡΟΤΑΣΗ", "func": create_page_3_financials, "data": True, "always": True},
        {"id": "tax", "title": "ΛΥΣΕΙΣ ΦΟΡΟΛΟΓΙΚΗΣ ΣΗΜΑΝΣΗΣ", "func": create_page_4_tax_solutions, "data": True, "key": "include_tax_solutions"},
        {"id": "terms", "title": "ΟΡΟΙ ΚΑΙ ΠΡΟΥΠΟΘΕΣΕΙΣ", "func": create_page_5_terms, "data": True, "always": True},
        {"id": "acceptance", "title": "ΣΥΜΠΛΗΡΩΣΗ ΣΤΟΙΧΕΙΩΝ", "func": create_page_6_acceptance, "data": True, "always": True},
    ]
    active_sections = [s for s in sections if s.get("always") or data.get(s.get("key"), True)]
    toc = [(f"{i+1}. {s['title']}", i + 1) for i, s in enumerate(active_sections)]
    try:
        create_page_1_intro(pdf, data, toc) 
        active_sections.pop(0) 
        for section in active_sections:
             section['func'](pdf, data) if section.get('data') else section['func'](pdf)
        return bytes(pdf.output())
    except Exception as e:
        st.error(f"Σφάλμα κατά τη δημιουργία των δεδομένων του PDF: {e}"); st.exception(e)
        return None

def logout():
    keys_to_clear = ['logged_in', 'username', 'user_role', 'first_name', 'last_name', 'email', 'offers_history', 'pdf_output', 'pdf_filename', 'ai_messages']
    for key in keys_to_clear:
        if key in st.session_state:
            st.session_state[key] = False if key == 'logged_in' else [] if key in ['offers_history', 'ai_messages'] else None

def display_settings_tab():
    st.header("⚙️ Ρυθμίσεις Λογαριασμού")
    with st.container(border=True):
        st.subheader("Επεξεργασία Στοιχείων")
        with st.form("update_profile_form"):
            c1, c2 = st.columns(2)
            fname = c1.text_input("Όνομα", value=st.session_state.first_name)
            lname = c2.text_input("Επώνυμο", value=st.session_state.last_name)
            email = st.text_input("Email", value=st.session_state.email)
            if st.form_submit_button("Ενημέρωση Στοιχείων", use_container_width=True):
                success, message = update_user_details(st.session_state.username, fname, lname, email)
                if success:
                    st.session_state.first_name, st.session_state.last_name, st.session_state.email = fname, lname, email
                    st.success(message); time.sleep(1); st.rerun()
                else:
                    st.error(message)

    with st.container(border=True):
        st.subheader("Αλλαγή Κωδικού Πρόσβασης")
        with st.form("change_password_form"):
            old_pass = st.text_input("Τρέχων Κωδικός", type="password")
            new_pass = st.text_input("Νέος Κωδικός", type="password")
            confirm_pass = st.text_input("Επιβεβαίωση Νέου Κωδικού", type="password")
            if st.form_submit_button("Αλλαγή Κωδικού", use_container_width=True, type="primary"):
                if new_pass and new_pass == confirm_pass:
                    success, message = change_user_password(st.session_state.username, old_pass, new_pass)
                    if success: st.success(message)
                    else: st.error(message)
                else:
                    st.error("Οι νέοι κωδικοί δεν ταιριάζουν ή είναι κενοί.")

def display_analytics_tab(username, role):
    st.header("📈 Ανάλυση Προσφορών")
    all_offers = load_offers_from_db()
    
    if role == 'admin':
        user_list = ["Όλοι οι Χρήστες"] + get_all_usernames()
        selected_user = st.selectbox("Φιλτράρισμα Ανάλυσης ανά Χρήστη:", user_list)
        if selected_user != "Όλοι οι Χρήστες":
            offers_for_analysis = [offer for offer in all_offers if offer.get('created_by_user') == selected_user]
        else:
            offers_for_analysis = all_offers
    else:
        offers_for_analysis = [offer for offer in all_offers if offer.get('created_by_user') == username]
            
    if not offers_for_analysis:
        st.warning("Δεν υπάρχουν δεδομένα προσφορών για την τρέχουσα επιλογή."); return

    try:
        df = pd.DataFrame(offers_for_analysis)
        if 'issue_date' not in df.columns: df['issue_date'] = None
        df['issue_date'] = pd.to_datetime(df['issue_date'], format='%d/%m/%Y', errors='coerce')
        df['total_value'] = df['installations'].fillna(0) * df['unit_price'].fillna(0)
        df.dropna(subset=['issue_date'], inplace=True)
        col1, col2 = st.columns(2)
        today = datetime.now().date()
        start_date = col1.date_input("Από ημερομηνία", today - timedelta(days=30)); end_date = col2.date_input("Έως ημερομηνία", today)
        start_datetime = datetime.combine(start_date, datetime.min.time()); end_datetime = datetime.combine(end_date, datetime.max.time())
        filtered_df = df[(df['issue_date'] >= start_datetime) & (df['issue_date'] <= end_datetime)]
        if filtered_df.empty:
            st.info("Δεν βρέθηκαν προσφορές στο επιλεγμένο εύρος ημερομηνιών."); return
        st.divider(); c1, c2 = st.columns(2)
        c1.metric("Σύνολο Προσφορών", f"{len(filtered_df)}"); c2.metric("Συνολική Αξία (€)", f"{filtered_df['total_value'].sum():,.2f} €")
        st.divider(); st.subheader("Προσφορές ανά Μήνα")
        offers_per_month = filtered_df.set_index('issue_date').resample('M').size(); offers_per_month.index = offers_per_month.index.strftime('%Y-%m')
        st.bar_chart(offers_per_month)
        if role == 'admin':
            st.divider(); st.subheader("Ανάλυση ανά Χρήστη (στο επιλεγμένο διάστημα)")
            if 'created_by_user' in filtered_df.columns:
                offers_by_user = filtered_df['created_by_user'].dropna().value_counts()
                if not offers_by_user.empty:
                    c1, c2 = st.columns(2)
                    with c1: st.write("Προσφορές ανά Χρήστη:"); st.dataframe(offers_by_user)
                    with c2: st.write("Γράφημα:"); st.bar_chart(offers_by_user)
                else: st.info("Δεν υπάρχουν δεδομένα χρηστών για το επιλεγμένο εύρος ημερομηνιών.")
            else: st.warning("Η ανάλυση ανά χρήστη δεν είναι διαθέσιμη (παλαιότερες εγγραφές).")
    except Exception as e:
        st.error(f"Παρουσιάστηκε ένα σφάλμα κατά την επεξεργασία των δεδομένων: {e}")
def display_settings_popover():
    with st.popover("⚙️", help="Ρυθμίσεις Λογαριασμού"):
        st.header("Ρυθμίσεις Λογαριασμού")
        
        with st.form("update_profile_form_popover"):
            st.subheader("Επεξεργασία Στοιχείων")
            c1, c2 = st.columns(2)
            fname = c1.text_input("Όνομα", value=st.session_state.first_name)
            lname = c2.text_input("Επώνυμο", value=st.session_state.last_name)
            email = st.text_input("Email", value=st.session_state.email)
            if st.form_submit_button("Ενημέρωση Στοιχείων", use_container_width=True):
                success, message = update_user_details(st.session_state.username, fname, lname, email)
                if success:
                    st.session_state.first_name = fname
                    st.session_state.last_name = lname
                    st.session_state.email = email
                    st.success(message)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(message)

        st.divider()

        with st.form("change_password_form_popover"):
            st.subheader("Αλλαγή Κωδικού Πρόσβασης")
            old_pass = st.text_input("Τρέχων Κωδικός", type="password")
            new_pass = st.text_input("Νέος Κωδικός", type="password")
            confirm_pass = st.text_input("Επιβεβαίωση Νέου Κωδικού", type="password")
            if st.form_submit_button("Αλλαγή Κωδικού", use_container_width=True, type="primary"):
                if new_pass and new_pass == confirm_pass:
                    success, message = change_user_password(st.session_state.username, old_pass, new_pass)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                else:
                    st.error("Οι νέοι κωδικοί δεν ταιριάζουν ή είναι κενοί.")
# --- 5. MAIN APPLICATION ---
def main():
    st.set_page_config(layout="wide", page_title="S-Team Dashboard")

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.user_role = None
        st.session_state.first_name = None
        st.session_state.last_name = None
        st.session_state.email = None
        st.session_state.offers_history = []
        st.session_state.ai_messages = []
        st.session_state.pdf_output = None
        st.session_state.pdf_filename = None

    if not st.session_state.logged_in:
        st.title("S-Team Dashboard");
        _ , col2, _ = st.columns([1, 1.5, 1])
        with col2:
            st.header("Είσοδος στο Σύστημα")
            auth_choice = st.radio("Επιλογή", ["Σύνδεση", "Εγγραφή", "Ανάκτηση Λογαριασμού"], horizontal=True, label_visibility="collapsed")
            if auth_choice == "Σύνδεση":
                with st.form("login_form"):
                    username = st.text_input("Username"); password = st.text_input("Password", type="password")
                    if st.form_submit_button("Σύνδεση", use_container_width=True, type="primary"):
                        success, user_data = authenticate_user(username, password)
                        if success:
                            st.session_state.logged_in = True; st.session_state.username = username
                            for key, value in user_data.items(): st.session_state[key] = value
                            st.rerun()
                        else: st.error("Λάθος στοιχεία σύνδεσης.")
            elif auth_choice == "Εγγραφή":
                with st.form("register_form"):
                    st.markdown("Δημιουργία νέου λογαριασμού")
                    c1, c2 = st.columns(2)
                    first_name = c1.text_input("Όνομα*"); last_name = c2.text_input("Επώνυμο*")
                    email = st.text_input("Email*")
                    username = c1.text_input("Username*"); password = c2.text_input("Password*", type="password")
                    if st.form_submit_button("Εγγραφή", use_container_width=True):
                        if all([first_name, last_name, email, username, password]):
                            success, msg = add_user_to_db(username, password, first_name, last_name, email)
                            if success: st.success("Επιτυχής εγγραφή! Μπορείτε τώρα να συνδεθείτε.")
                            else: st.error(msg)
                        else: st.error("Όλα τα πεδία είναι υποχρεωτικά.")
            elif auth_choice == "Ανάκτηση Λογαριασμού":
                display_recovery_ui()
        st.stop()

    col1, col_user, col_settings, col_logout = st.columns([4, 2, 1, 1])
    with col1:
        st.title("S-Team Dashboard"); st.markdown("##### Διαχείριση προσφορών και πελατών")
    with col_user:
        st.markdown(f"###### Καλωσήρθες, {st.session_state.first_name}!");
    with col_settings:
        display_settings_popover()
    with col_logout:
        if st.button("🚪", help="Αποσύνδεση", use_container_width=True):
            logout(); st.rerun()
    st.divider()

    # --- ΔΙΟΡΘΩΣΗ ΕΔΩ: Προστέθηκε η καρτέλα "Ρυθμίσεις" ---
    tabs = ["➕ Νέα Προσφορά", "📂 Ιστορικό", "📈 Ανάλυση", "🤖 AI Assistant", "⚙️ Ρυθμίσεις"]
    tab_new, tab_history, tab_analytics, tab_ai, tab_settings = st.tabs(tabs)

    with tab_new:
        st.header("Δημιουργία Νέας Προσφοράς")
        col_form, col_actions = st.columns([3, 2])
        with col_form:
            with st.container(border=True):
                st.markdown("###### Επιλογές Ενοτήτων & Λύσεων")
                c1, c2 = st.columns(2)
                include_tech = c1.checkbox("Τεχνική Περιγραφή", value=True)
                include_tax = c2.checkbox("Λύσεις Φορολ. Σήμανσης", value=True)
                tax_choice = "Δεν εφαρμόζεται"; e_invoicing_package = None
                if include_tax:
                    tax_choice = st.selectbox("Επιλογή Φορολογικής Λύσης", ["Δεν γνωρίζω", "Φορολογικός Μηχανισμός", "Πάροχος"])
                    if tax_choice == "Πάροχος":
                        package_options = ["Service Pack Fuel 25K", "Service Pack Fuel 50K", "Service Pack Fuel 75K", "Service Pack Fuel 100K", "Service Pack Fuel 150K", "Service Pack Fuel 250K", "Service Pack Fuel 500K", "Service Pack Fuel 1M"]
                        e_invoicing_package = st.selectbox("Επιλογή Πακέτου Παρόχου", options=package_options)
            with st.form("offer_form"):
                st.markdown("###### Στοιχεία Πελάτη & Οικονομικά")
                c1, c2, c3 = st.columns(3)
                client_company = c1.text_input("Επωνυμία*"); client_address = c1.text_input("Οδός & Αριθμός*"); installations = c1.number_input("Εγκαταστάσεις*", min_value=1, value=1)
                client_vat_id = c2.text_input("ΑΦΜ"); client_tk = c2.text_input("Τ.Κ.*"); unit_price = c2.number_input("Τιμή Μονάδας (€)*", min_value=0.0, value=120.0, format="%.2f")
                client_phone = c3.text_input("Τηλέφωνο"); client_area = c3.text_input("Περιοχή*"); offer_valid_until = c3.text_input("Ισχύς έως*", value=time.strftime("%d/%m/%Y", time.localtime(time.time() + 30*24*60*60)))
                st.markdown("###### Εξατομίκευση Προσφοράς")
                custom_title = st.text_input("Προσαρμοσμένος Τίτλος", placeholder="π.χ. Πρόταση για το κατάστημα Χ")
                custom_content = st.text_area("Προσαρμοσμένο Κείμενο Εισαγωγής", height=100, placeholder="Αντικαθιστά το προεπιλεγμένο κείμενο της εισαγωγής.")
                submitted = st.form_submit_button("💾 Δημιουργία & Αποθήκευση", use_container_width=True, type="primary")
        if submitted:
            if all([client_company, client_address, client_tk, client_area]):
                offer_data = { "client_company": client_company, "client_vat_id": client_vat_id, "client_address": client_address, "client_tk": client_tk, "client_area": client_area, "client_phone": client_phone, "custom_title": custom_title, "custom_content": custom_content, "installations": installations, "unit_price": unit_price, "offer_valid_until": offer_valid_until, "include_tech_description": include_tech, "include_tax_solutions": include_tax, "tax_solution_choice": tax_choice, "e_invoicing_package": e_invoicing_package, "protocol_number": f"PR{int(time.time())}", "issue_date": time.strftime("%d/%m/%Y") }
                pdf_bytes = generate_pdf_data(offer_data)
                if pdf_bytes:
                    st.session_state.pdf_output = pdf_bytes; st.session_state.pdf_filename = f"Offer_{offer_data.get('client_company', 'NO_NAME').replace(' ', '_')}.pdf"
                    save_offer_to_db(offer_data, st.session_state.username)
                    st.success("Η προσφορά δημιουργήθηκε και αποθηκεύτηκε!")
            else: st.error("Παρακαλώ συμπληρώστε όλα τα πεδία με αστερίσκο (*).")
        
        if st.session_state.get("pdf_output"):
            with col_actions:
                st.subheader("Ενέργειες Προσφοράς")
                base64_pdf = base64.b64encode(st.session_state.pdf_output).decode('utf-8'); pdf_data_uri = f"data:application/pdf;base64,{base64_pdf}"
                st.link_button("👁️ Προεπισκόπηση σε Νέα Καρτέλα", url=pdf_data_uri, use_container_width=True)
                st.download_button("📥 Λήψη του PDF", st.session_state.pdf_output, st.session_state.pdf_filename, "application/pdf", use_container_width=True)
                with st.expander("📧 Αποστολή με Email"):
                    recipient = st.text_input("Email παραλήπτη:", key="recipient_email")
                    if st.button("Αποστολή Email"):
                        if recipient:
                            with st.spinner("Αποστολή..."):
                                success, msg = send_email_with_attachment(recipient, f"Προσφορά: {st.session_state.pdf_filename}", "Συνημμένα θα βρείτε την προσφορά μας.", st.session_state.pdf_output, st.session_state.pdf_filename)
                                if success: st.success(msg)
                                else: st.error(msg)
                        else: st.warning("Παρακαλώ εισάγετε email παραλήπτη.")

    with tab_history:
        st.header("Ιστορικό Προσφορών")
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.session_state.user_role == 'admin':
                user_list = ["Όλοι οι Χρήστες"] + get_all_usernames()
                selected_user = st.selectbox("Φιλτράρισμα Ιστορικού ανά Χρήστη:", user_list)
        with col2:
            st.write(""); st.write("")
            if st.button("Ανανέωση Λίστας", use_container_width=True):
                st.session_state.offers_history = []
                st.rerun()
        if not st.session_state.get('offers_history'):
            st.session_state.offers_history = load_offers_from_db()
        
        offers_to_display = st.session_state.offers_history
        if 'selected_user' in locals() and st.session_state.user_role == 'admin' and selected_user != "Όλοι οι Χρήστες":
            offers_to_display = [offer for offer in offers_to_display if offer.get('created_by_user') == selected_user]
        elif st.session_state.user_role != 'admin':
             offers_to_display = [offer for offer in offers_to_display if offer.get('created_by_user') == st.session_state.username]

        for i, offer in enumerate(offers_to_display):
            with st.expander(f"**{offer.get('protocol_number')}** - {offer.get('client_company')} ({offer.get('issue_date')})"):
                display_offer_details(offer)
                st.divider()
                pdf_bytes_hist = generate_pdf_data(offer)
                if pdf_bytes_hist:
                    base64_pdf_hist = base64.b64encode(pdf_bytes_hist).decode('utf-8')
                    pdf_data_uri_hist = f"data:application/pdf;base64,{base64_pdf_hist}"
                    c1, c2, c3 = st.columns([2, 2, 3])
                    c1.link_button("👁️ Προεπισκόπηση", url=pdf_data_uri_hist, use_container_width=True)
                    c2.download_button(label=f"📥 Λήψη", data=pdf_bytes_hist, file_name=f"Offer_{offer.get('protocol_number')}.pdf", mime="application/pdf", key=f"down_hist_{i}", use_container_width=True)
                    with c3:
                        with st.expander("📧"):
                            hist_recipient = st.text_input("Email", key=f"send_email_hist_{i}")
                            if st.button("Αποστολή", key=f"send_btn_hist_{i}"):
                                if hist_recipient:
                                    success, msg = send_email_with_attachment(hist_recipient, f"Προσφορά: {offer.get('protocol_number')}", "Συνημμένα θα βρείτε την προσφορά μας.", pdf_bytes_hist, f"Offer_{offer.get('protocol_number')}.pdf")
                                    if success: st.success(msg)
                                    else: st.error(msg)

    with tab_analytics:
        display_analytics_tab(st.session_state.username, st.session_state.user_role)
        
    with tab_ai:
        st.header("🤖 AI Assistant")
        st.info("Συνομιλήστε ελεύθερα με τον βοηθό AI για οποιαδήποτε ερώτηση.")
        if 'ai_messages' not in st.session_state: st.session_state.ai_messages = []
        for message in st.session_state.ai_messages:
            with st.chat_message(message["role"]): st.markdown(message["content"])
        if prompt := st.chat_input("Κάντε μια ερώτηση..."):
            st.session_state.ai_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                try:
                    with st.spinner("Ο βοηθός σκέφτεται..."):
                        model = get_gemini_model(); response = model.generate_content(prompt); response_text = response.text
                        st.markdown(response_text)
                    st.session_state.ai_messages.append({"role": "assistant", "content": response_text})
                except Exception as e:
                    error_message = f"Παρουσιάστηκε σφάλμα: {e}"; st.error(error_message)
                    st.session_state.ai_messages.append({"role": "assistant", "content": error_message})

    with tab_settings:
        display_settings_tab()

# --- 5. SCRIPT EXECUTION ---
if __name__ == "__main__":
    init_db()
    try: genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    except Exception: st.warning("Δεν ήταν δυνατή η αρχικοποίηση του Gemini AI.", icon="⚠️")
    main()
