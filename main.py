import time
import streamlit as st
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import os
import google.generativeai as genai
import re 
import json 

# Configure Google Generative AI with API key from Streamlit secrets
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("Το Gemini API Key δεν βρέθηκε. Δημιουργήστε ένα αρχείο '.streamlit/secrets.toml' με 'GEMINI_API_KEY=\"ΤΟ_ΚΛΕΙΔΙ_ΣΟΥ\"'.")
    st.stop()
except Exception as e:
    st.error(f"Σφάλμα κατά την αρχικοποίηση του Gemini API: {e}")
    st.stop()

# ############################################################################
# ΔΥΝΑΜΙΚΗ ΕΠΙΛΟΓΗ GEMINI ΜΟΝΤΕΛΟΥ
# ############################################################################
@st.cache_resource
def get_gemini_model():
    """Επιλέγει το κατάλληλο Gemini μοντέλο που υποστηρίζει generateContent."""
    try:
        available_models = genai.list_models()
        
        preferred_models = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
        
        for preferred_name in preferred_models:
            for m in available_models:
                if preferred_name in m.name and 'generateContent' in m.supported_generation_methods:
                    if "vision" not in m.name.lower() or "1.5" in m.name:
                        st.info(f"Βρέθηκε και χρησιμοποιείται το μοντέλο Gemini: **{m.name}**")
                        return genai.GenerativeModel(m.name)
        
        st.error("Δεν βρέθηκε κανένα κατάλληλο μοντέλο Gemini που να υποστηρίζει 'generateContent' και να μην είναι deprecated.")
        st.info("Βεβαιωθείτε ότι το Gemini API είναι ενεργοποιημένο για τον λογαριασμό σας και ότι έχετε πρόσβαση σε μοντέλα όπως 'gemini-1.5-flash' ή 'gemini-1.5-pro'.")
        st.stop()
    except Exception as e:
        st.error(f"Σφάλμα κατά την ανάκτηση των διαθέσιμων μοντέλων Gemini: {e}")
        st.info("Ελέγξτε τη συνδεσιμότητα στο Internet και το Gemini API Key.")
        st.stop()

model = get_gemini_model()

# ############################################################################
# ΚΛΑΣΗ ΓΙΑ ΤΗ ΔΗΜΙΟΥΡΓΙΑ ΤΟΥ PDF (ΤΕΛΙΚΗ ΕΚΔΟΣΗ 3.0)
# ############################################################################
class OfferPDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            if not os.path.exists('DejaVuSans.ttf'):
                st.error("ΣΦΑΛΜΑ: Το αρχείο γραμματοσειράς 'DejaVuSans.ttf' δεν βρέθηκε.")
                st.stop() 
            if not os.path.exists('DejaVuSans-Bold.ttf'):
                st.error("ΣΦΑΛΜΑ: Το αρχείο γραμματοσειράς 'DejaVuSans-Bold.ttf' δεν βρέθηκε.")
                st.stop() 

            self.add_font('DejaVu', '', 'DejaVuSans.ttf')
            self.add_font('DejaVu', 'B', 'DejaVuSans-Bold.ttf')
        except RuntimeError as e:
            st.error(f"Σφάλμα κατά την αρχικοποίηση της γραμματοσειράς: {e}")
            st.warning("Βεβαιωθείτε ότι τα DejaVuSans.ttf και DejaVuSans-Bold.ttf υπάρχουν στον φάκελο του project.")
            st.stop()

    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVu', '', 8)
        self.cell(0, 10, f'{self.page_no()}', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

# ############################################################################
# ΣΥΝΑΡΤΗΣΕΙΣ ΔΗΜΙΟΥΡΓΙΑΣ ΣΕΛΙΔΩΝ
# ############################################################################

def create_page_1_intro(pdf, data, toc_entries): # Χρησιμοποιούμε την παράμετρο toc_entries
    pdf.add_page()
    if os.path.exists('logo.png'):
        pdf.image('logo.png', x=150, y=10, w=50)
    else:
        st.warning("Το αρχείο 'logo.png' δεν βρέθηκε. Συνεχίζω χωρίς λογότυπο.")
    
    # Ρύθμιση χρώματος γραμμών (borders) για την ενότητα αυτή
    pdf.set_draw_color(100, 100, 100) # Σκούρο γκρι για borders

    pdf.set_font('DejaVu', 'B', 12)
    pdf.set_xy(15, 40)
    pdf.cell(0, 10, 'ΣΤΟΙΧΕΙΑ ΠΕΛΑΤΗ')
    pdf.set_font('DejaVu', '', 11)
    pdf.set_xy(15, 50)
    client_info_text = (
        f"Επωνυμία: {data['client_company']}\n"
        f"Οδός: {data['client_address']}\n"
        f"ΤΚ: {data['client_tk']}\n"
        f"Περιοχή: {data['client_area']}"
    )
    if 'client_phone' in data and data['client_phone']:
        client_info_text += f"\nΤηλέφωνο: {data['client_phone']}"
    pdf.multi_cell(90, 7, client_info_text, border=1)

    pdf.set_font('DejaVu', '', 11)
    pdf.set_xy(120, 50)
    pdf.multi_cell(75, 7, f"Αριθμός Πρωτοκόλλου: {data['protocol_number']}\n"
                           f"Ημερομηνία Έκδοσης: {data['issue_date']}", border=1)
    pdf.set_xy(15, 90)
    pdf.set_font('DejaVu', 'B', 14)
    pdf.cell(0, 10, "Πρόταση Λογισμικού Εμπορικής Διαχείρισης", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    intro_text = (
        "Αξιότιμε συνεργάτη,\n"
        "σε συνέχεια της επικοινωνίας μας, σας αποστέλλουμε την πρόταση της εταιρίας μας σχετικά με το "
        "λογισμικό εμπορικής διαχείρισης. Η S-Team έχει πάντοτε ως γνώμονα την καλύτερη και την αρτιότερη κάλυψη των "
        "αναγκών της επιχείρησής σας. Διαθέτει πολυετή εμπειρία, βαθιά τεχνογνωσία και υψηλή εξειδίκευση σε προϊόντα "
        "και λύσεις μηχανογράφησης επιχειρήσεων. Η αποδεδειγμένη ικανοποίηση των πελατών της εταιρίας είναι "
        "στοιχεία που χαρακτηρίζουν την S-Team. Συνημμένα θα βρείτε τους όρους και τις προϋποθέσεις της προσφοράς "
        "μας. Παραμένουμε στη διάθεση σας για οποιαδήποτε συμπληρωματική πληροφορία.\n\n"
        "Με εκτίμηση,\nΤμήμα Υποστήριξης Πελατών."
    )
    pdf.set_xy(15, 105)
    pdf.set_font('DejaVu', '', 10)
    pdf.multi_cell(0, 5, intro_text)
    pdf.set_xy(15, 170)
    pdf.set_font('DejaVu', 'B', 12)
    pdf.cell(0, 10, "Περιεχόμενα", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', '', 10)
    
    # Χρησιμοποιούμε τη δυναμική λίστα TOC που δημιουργήθηκε στην generate_pdf_and_display
    for item_text, page_num in toc_entries:
        pdf.cell(80, 6, item_text) # item_text θα περιέχει ήδη τον αριθμό κεφαλαίου
        pdf.cell(0, 6, str(page_num), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')

def create_page_2_tech_desc(pdf):
    pdf.add_page()
    # Εικόνα UpSales (αν υπάρχει)
    if os.path.exists('upsales_logo.png'): # Υποθέτουμε ότι υπάρχει αρχείο upsales_logo.png
        # Προσαρμογή θέσης και μεγέθους για να μοιάζει με το παράδειγμα
        pdf.image('upsales_logo.png', x=100, y=10, w=90) # Προσαρμόστε x, y, w αν χρειάζεται
    
    pdf.set_draw_color(100, 100, 100) # Σκούρο γκρι για borders

    pdf.set_font('DejaVu', 'B', 14); pdf.cell(0, 10, "2. ΤΕΧΝΙΚΗ ΠΕΡΙΓΡΑΦΗ", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)
    pdf.set_font('DejaVu', '', 10)
    tech_points_1 = [
        "UpSales. Το εμπορικό πρόγραμμα διαχείρισης κάθε επιχείρησης που συνδυάζει άψογα ποιότητα - τιμή - ευκολία χρήσης.",
        "Μία εμπορική εφαρμογή προσιτή σε κάθε επιχείρηση, λόγω χαμηλού κόστους απόκτησης και ετήσιας συντήρησης.",
        "Εφαρμογή φιλική σε κάθε χρήστη ανεξαρτήτως επιπέδου γνώσεων Η/Υ.",
        "Σχεδιασμένο έτσι ώστε ο χρήστης με ελάχιστες κινήσεις να επεξεργάζεται όλες τις λειτουργίες του προγράμματος στο λιγότερο δυνατό χρόνο.",
        "Τεχνολογία αιχμής. Η ανάπτυξή του έγινε με τα πλέον σύγχρονα εργαλεία προγραμματισμού, προσφέροντας ευελιξία και εφαρμογή στις ανάγκες κάθε επιχείρησης ξεχωριστά.",
        "Το πλήρως στελεχωμένο τμήμα ανάπτυξης λογισμικού της S-Team εγγυάται την άψογη υποστήριξη της επιχείρησης σε σύγχρονες και μελλοντικές προκλήσεις."
    ]
    for point in tech_points_1:
        pdf.multi_cell(0, 5, f"•  {point}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(2)
    pdf.set_font('DejaVu', 'B', 11)
    pdf.cell(0, 10, "Η Βασική έκδοση περιλαμβάνει:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', '', 10)
    tech_points_2 = [
        "Διαχείριση πελατών-προμηθευτών, ειδών-υπηρεσιών, αποθήκης, πωλήσεων (λιανικής & χονδρικής) - αγορών, εισπράξεων-πληρωμών-αξιογράφων.",
        "Μεταφορά εγγραφών πωλήσεων-αγορών- χρηματοοικονομικών σε πλήθος λογιστικών εφαρμογών μειώνοντας τον χρόνο επεξεργασίας των λογιστών και ελαχτοποιώντας την πιθανότητα ανθρώπινου σφάλματος στην καταχώρηση των στοιχείων.",
        "Εξαγωγή αρχείων Μηνιαίων Καταστάσεων Πελατών Προμηθευτών και Συναλλαγών έτοιμα για αποστολή στην Γενική Γραμματεία Πληροφοριακών Συστημάτων.",
        "Δυνατότητα απευθείας σύνδεσης με πλήθος φορολογικών μηχανισμών για την έκδοση λιανικών αποδείξεων.",
        "Πληθώρα εκτυπώσεων για είδη, πελάτες-προμηθευτές, πωλήσεων, αγορών, χρηματοοικονομικών, καθώς επίσης ένας νέος επαναστατικός τρόπος εκτύπωσης με φίλτρα ώστε να βγάζετε ό,τι αποτελέσματα θέλετε σύμφωνα με τις ανάγκες σας."
    ]
    for point in tech_points_2:
        pdf.multi_cell(0, 5, f"•  {point}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(2)

def create_page_3_financials(pdf, data):
    pdf.add_page()
    pdf.set_draw_color(100, 100, 100) # Σκούρο γκρι για borders

    pdf.set_font('DejaVu', 'B', 14); pdf.cell(0, 10, "3. ΟΙΚΟΝΟΜΙΚΗ ΠΡΟΤΑΣΗ", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)
    pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 8, "Βασική έκδοση UpSales", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', '', 10); pdf.multi_cell(0, 5, "Σας αποστέλλουμε οικονομική προσφορά για την μηχανογράφηση / μηχανοργάνωση της εταιρείας σας.", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)
    
    pdf.set_text_color(50, 50, 50) 
    pdf.set_fill_color(255, 255, 255) # Λευκό background για header cells
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(100, 8, "ΠΕΡΙΓΡΑΦΗ", border=1, fill=True); pdf.cell(30, 8, "ΕΓΚΑΤΑΣΤΑΣΗ", border=1, align='C', fill=True); pdf.cell(60, 8, "ΤΙΜΗ ΜΟΝΑΔΟΣ (€)", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
    pdf.set_text_color(0, 0, 0) # Επαναφορά χρώματος κειμένου σε μαύρο για το περιεχόμενο
    
    pdf.set_font('DejaVu', '', 10)
    items_desc = "Εμπορικό UpSales, περιλαμβάνει:\n• Άδεια Χρήσης Λογισμικού για ένα έτος\n• Εγκατάσταση & Παραμετροποίηση προγράμματος\n• Εκπαίδευση"
    y_before = pdf.get_y(); pdf.multi_cell(100, 5, items_desc, border=1, new_x=XPos.LEFT, new_y=YPos.NEXT); height = pdf.get_y() - y_before
    pdf.set_xy(110, y_before); pdf.cell(30, height, str(data['installations']), border=1, align='C'); pdf.cell(60, height, f"{data['unit_price']:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(0, 6, "Στις παραπάνω τιμές ΔΕΝ συμπεριλαμβάνεται Φ.Π.A.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R'); pdf.ln(10)
    
    pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 8, "Άδεια Χρήσης Λογισμικού", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_text_color(50, 50, 50) 
    pdf.set_fill_color(255, 255, 255)
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(130, 8, "ΠΕΡΙΓΡΑΦΗ", border=1, fill=True); pdf.cell(60, 8, "ΤΙΜΗ", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
    pdf.set_text_color(0, 0, 0) 
    
    pdf.set_font('DejaVu', '', 10); pdf.multi_cell(130, 5, "Ετήσια Άδεια Χρήσης Λογισμικού που περιλαμβάνει νέες εκδόσεις (Μετά το 1ο έτος)", border=1, new_x=XPos.LEFT, new_y=YPos.NEXT)
    y_before = pdf.get_y() - 10; pdf.set_xy(140, y_before); pdf.cell(60, 10, "120€ / Εγκατάσταση", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(0, 6, "Στις παραπάνω τιμές ΔΕΝ συμπεριλαμβάνεται Φ.Π.A.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R'); pdf.ln(10)
    
    pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 8, "Υπηρεσίες", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', '', 10); pdf.multi_cell(0, 5, "Λόγω των διαφορετικών αναγκών και απαιτήσεων κάθε επιχείρησης, προτείνεται η Προαγορά Ωρών Υποστήριξης, καθώς παρέχεται Παραμετροποίηση και Τεχνική Υποστήριξη.", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)

    support_header = ["ΠΕΡΙΓΡΑΦΗ ΣΥΜΒΟΛΑΙΟΥ ΥΠΟΣΤΗΡΙΞΗΣ", "ΩΡΕΣ", "ΑΞΙΑ (€)"]
    pdf.set_text_color(50, 50, 50) 
    pdf.set_fill_color(255, 255, 255)
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(110, 8, support_header[0], border=1, align='C', fill=True); pdf.cell(30, 8, support_header[1], border=1, align='C', fill=True); pdf.cell(50, 8, support_header[2], border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
    pdf.set_text_color(0, 0, 0) 
    
    pdf.set_font('DejaVu', '', 10)
    support_data = [
        ["Συμβόλαιο Τηλεφωνικής & Απομακρομισμένης Υποστήριξης", "2 ώρες", 150.00],
        ["", "5 ώρες", 270.00],
        ["", "10 ώρες", 520.00],
        ["", "20 ώρες", 940.00],
        ["", "30 ώρες", 1450.00],
        ["", "50 ώρες", 2250.00]
    ]
    for row in support_data:
        pdf.cell(110, 6, row[0], border=1); pdf.cell(30, 6, row[1], border=1, align='C'); pdf.cell(50, 6, f"{row[2]:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(0, 6, "Στις παραπάνω τιμές ΔΕΝ συμπεριλαμβάνεται Φ.Π.A.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R'); pdf.ln(5)
    
    pdf.set_font('DejaVu', 'B', 11); pdf.cell(0, 8, "Πλεονεκτήματα:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    advantages = ["ΔΕΝ έχουν ημερολογιακό περιορισμό", "Έχουν χαμηλό κόστος ώρας", "Υποστήριξη όταν τη χρειάζεστε", "Λήγουν μόνο όταν εξαντληθούν οι ώρες προαγοράς", "Καλύπτει Παραμετροποίηση, Εκπαίδευση, Επίσκεψη Τεχνικού, Remote Υποστήριξη", "Ελάχιστη χρέωση 10λεπτά ανά τηλεφωνική κλήση.", "Χρέωση πραγματικού χρόνου υποστήριξης."]
    pdf.set_font('DejaVu', '', 10)
    for advantage in advantages: 
        pdf.multi_cell(0, 5, f"•  {advantage}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

def create_page_4_tax_solutions(pdf): 
    pdf.add_page()
    pdf.set_draw_color(100, 100, 100) # Σκούρο γκρι για borders

    pdf.set_font('DejaVu', 'B', 14); pdf.cell(0, 10, "4. ΛΥΣΕΙΣ ΦΟΡΟΛΟΓΙΚΗΣ ΣΗΜΑΝΣΗΣ", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(5)
    
    pdf.set_text_color(50, 50, 50) 
    pdf.set_fill_color(255, 255, 255)
    # CORRECTED: fill=True for standalone cells
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(140, 8, "ΦΟΡΟΛΟΓΙΚΗ ΣΗΜΑΝΣΗ", border=1, align='C', fill=True); pdf.cell(50, 8, "ΤΙΜΗ", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
    pdf.set_text_color(0, 0, 0) 

    pdf.set_font('DejaVu', '', 10); 
    pdf.cell(140, 8, "ΦΟΡΟΛΟΓΙΚΟΣ ΜΗΧΑΝΙΣΜΟΣ SAMTEC NEXT AI", border=1); pdf.cell(50, 8, "480.00 € + ΦΠΑ", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R'); pdf.ln(10)

    pdf.set_font('DejaVu', 'B', 10); pdf.cell(190, 8, "ΠΑΡΟΧΟΣ Impact e-invoicing", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    e_invoice_header_defs = [
        ("Πάκετο EINVOICING\n(ετήσια συνδρομή)", 35), ("Αξία Πελάτη", 20),
        ("Μέγιστος Αριθμός\nΑποδείξεων Λιανικής", 25), ("Μέγιστος Αριθμός\nΠαραστατικών Χονδρικής", 25),
        ("Μέγιστος Αριθμός\nΠαραστατικών B2G", 25), ("Τιμή ανά\nΠαραστατικό Λιανικής", 20),
        ("Τιμή ανά\nΠαραστατικό Χονδρικής", 20), ("Τιμή ανά\nΠαραστατικό B2G", 20),
        ("-50% ΠΡΟΣΦΟΡΑ\nΕΩΣ 20/03/25", 25)
    ]
    e_invoice_data = [
        ["Service Pack Fuel 25K", "250 €", "25,000", "5,000", "1,000", "0.0100 €", "0.0500 €", "0.25 €", "125 €"],
        ["Service Pack Fuel 50K", "450 €", "50,000", "10,000", "2,000", "0.0090 €", "0.0450 €", "0.23 €", "225 €"],
        ["Service Pack Fuel 75K", "600 €", "75,000", "15,000", "3,000", "0.0080 €", "0.0400 €", "0.20 €", "300 €"],
        ["Service Pack Fuel 100K", "700 €", "100,000", "20,000", "4,000", "0.0070 €", "0.0350 €", "0.18 €", "350 €"],
        ["Service Pack Fuel 150K", "900 €", "150,000", "30,000", "6,000", "0.0060 €", "0.0300 €", "0.15 €", "450 €"],
        ["Service Pack Fuel 250K", "1,000 €", "250,000", "50,000", "10,000", "0.0040 €", "0.0200 €", "0.10 €", "500 €"],
        ["Service Pack Fuel 500K", "1,250 €", "500,000", "50,000", "10,000", "0.0025 €", "0.0125 €", "0.06 €", "625 €"],
        ["Service Pack Fuel 1M", "2,000 €", "1,000,000", "200,000", "40,000", "0.0020 €", "0.0100 €", "0.05 €", "1,000 €"]
    ]
    
    with pdf.table(col_widths=[w for _, w in e_invoice_header_defs], text_align="C", line_height=4) as table:
        # Header row
        header_row = table.row()
        pdf.set_font('DejaVu', 'B', 6)
        pdf.set_fill_color(*DEFAULT_TABLE_HEADER_COLOR) # Εδώ χρησιμοποιούμε το default πράσινο
        pdf.set_text_color(50, 50, 50) # Σκούρο γκρι για κείμενο header
        # CORRECTED: Cells within pdf.table are implicitly filled if pdf.set_fill_color is set.
        # No 'fill=True' or 'cell_kwargs' is needed here.
        for text, _ in e_invoice_header_defs:
            header_row.cell(text, border=1) 
        pdf.set_text_color(0, 0, 0) # Επαναφορά χρώματος κειμένου σε μαύρο

        # Data Rows
        pdf.set_font('DejaVu', '', 8)
        for row_data in e_invoice_data:
            current_row = table.row()
            for i, cell_text in enumerate(row_data):
                if i == len(row_data) - 1: # Last column for offer
                    pdf.set_fill_color(255, 192, 0) # Orange for offer column
                    current_row.cell(cell_text, border=1) # Implicitly uses current fill color
                else:
                    pdf.set_fill_color(255, 255, 255) # White for other cells
                    current_row.cell(cell_text, border=1) # Implicitly uses current fill color

def create_page_5_terms(pdf, data):
    pdf.add_page()
    pdf.set_draw_color(100, 100, 100) # Σκούρο γκρι για borders

    def add_section(title, points, is_bulleted=True):
        pdf.set_font('DejaVu', 'B', 12); pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        pdf.set_font('DejaVu', '', 9)
        for point in points:
            prefix = "•  " if is_bulleted else ""
            pdf.multi_cell(0, 5, f"{prefix}{point}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); pdf.ln(1)
    
    add_section("5. ΟΡΟΙ ΚΑΙ ΠΡΟΥΠΟΘΕΣΕΙΣ", [])
    add_section("Τι καλύπτουν τα Συμβόλαια Προαγοράς Ωρών", ["1. Τηλεφωνική & Remote Υποστήριξη Δευτ-Παρ 09:00-17:00.", "2. Άμεση υποστήριξη ή σας καλούμε εμείς το αργότερο σε 30λεπτά από την κλήση.", "3. Επίσκεψη στο χώρο του πελάτη κατόπιν ραντεβού.", "4. Θέματα που σχετίζονται με τις εφαρμογές και την σωστή λειτουργία των Η/Υ ή Servers – Hardware, Printer-Δίκτυο και μπορούν να επιλυθούν μέσω Remote Support."], is_bulleted=False)
    add_section("Σημειώσεις", ["1. Για υποστήριξη έκτος ωρών εργασίας, ισχύουν οι επιπλέον επιβαρύνσεις: α) 50% από 17:00 ως και 21:00 β) 100% από 21:00 ως και 24:00, για Σάββατο & Κυριακή καθώς και επίσημες αργίες γ) Δευτέρα-Κυριακή δεν λειτουργεί το Support από 00:01 – 09:00", "2. H τιμολόγηση των ωρών προαγοράς γίνεται με την παραγγελία. Για να ισχύσουν τα παραπάνω πακέτα προαγοράς ωρών, θα πρέπει να έχει προηγηθεί πλήρης εξόφληση του τιμολογιου.", "3. Στα παραπάνω δεν περιλαμβάνεται περαιτέρω ανάπτυξη της εφαρμογής. Τα κόστη προκύπτουν κατόπιν ανάλυσης των απαιτήσεων του πελάτη.", "4. Οι εκτός έδρας εργασίες επιβαρύνονται με επιπλέον κόστος 0,60€/χλμ + διόλια + έξοδα διαμονής."], is_bulleted=False)
    add_section("Ειδικοί Όροι", ["Όλες οι εργασίες θα γίνουν μέσω απομακρομισμένης πρόσβασης", "Η εκπαίδευση γίνεται σε ένα και μόνο άτομο."])
    add_section("Τιμές", ["Οι τιμές του παρόντος εγγράφου δίνονται σε ευρώ (€) και δεν περιλαμβάνουν Φ.Π.A.", "Οι τιμές περιλαμβάνουν μεταφορικά έξοδα για παράδοση σε χώρο που θα μας υποδείξετε, εντός των ορίων του νομού Αττικής. Για αποστολές εκτός νομού Αττικής το κόστος των μεταφορικών επιβαρύνει τον πελάτη."])
    add_section("Τρόποι πληρωμής", ["Προκαταβολή του 50% με κατάθεση σε τραπεζικό λογαριασμό της εταιρείας και το υπόλοιπο 50% με την ολοκλήρωση των εργασιών."])
    
    # CORRECTED: data_rows definition moved here
    data_rows = [
        ["Πειραιώς", "GR45 0172 1830 00 51 8307 0951 644", "S-Team OE"], 
        ["Eurobank", "GR60 0260 3530 00 08 6020 0518 561", "S-Team OE"]
    ]
    with pdf.table(col_widths=(40, 75, 75), text_align="L") as table:
        # Header row
        header = table.row()
        pdf.set_font('DejaVu', 'B') # Set font for header
        pdf.set_text_color(50, 50, 50) 
        pdf.set_fill_color(255, 255, 255)
        # CORRECTED: No fill=True for cells within pdf.table. They inherit fill color.
        header.cell("Τράπεζα")
        header.cell("ΙΒΑΝ")
        header.cell("Δικαιούχος")
        pdf.set_text_color(0, 0, 0) # Επαναφορά χρώματος κειμένου σε μαύρο
        
        # Data Rows
        pdf.set_font('DejaVu', '') # Reset font for data rows
        for data_row in data_rows: table.row(data_row)
    pdf.ln(5)

    add_section("Χρόνος Παράδοσης", ["Εντός 10 - 15 ημερών από την έγγραφη ανάθεση της παραγγελίας σας.", "Ο χρόνος παράδοσης του εξοπλισμού μπορεί να διαφοροποιείται, ανάλογα με τη διαθεσιμότητα των προϊόντων από τον κατασκευαστή."])
    add_section("Ισχύς Προσφοράς", [f"Η πρόταση ισχύει έως {data['offer_valid_until']}"])

def create_page_6_acceptance(pdf, data):
    pdf.add_page()
    pdf.set_draw_color(100, 100, 100) # Σκούρο γκρι για borders

    pdf.set_font('DejaVu', 'B', 14); pdf.cell(0, 10, "6. ΣΥΜΠΛΗΡΩΣΗ ΣΤΟΙΧΕΙΩΝ", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); pdf.ln(10)
    pdf.set_font('DejaVu', '', 10)
    pdf.multi_cell(0, 5, "Για την αποδοχή της παραπάνω προσφοράς, παρακαλείσθε να επιστρέψετε υπογεγραμμένη και σφραγισμένη την παρούσα σελίδα.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(20)

    col1_x = pdf.get_x(); col2_x = col1_x + 100; y_start = pdf.get_y()
    
    pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Από:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT) 
    pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Υπεύθυνος:"); pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT) 
    pdf.set_font('DejaVu', 'B'); pdf.cell(25, 7, "Τηλέφωνο:"); 
    pdf.set_font('DejaVu', ''); pdf.cell(65, 7, "", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT) # Always empty as requested

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
    pdf.set_y(pdf.get_y() + 25)
    pdf.set_font('DejaVu', 'B'); pdf.cell(0, 10, "Υπογραφή - Σφραγίδα Επιχείρησης", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_y(pdf.get_y() + 20)
    pdf.set_font('DejaVu', 'B', 10); pdf.cell(40, 10, "ΑΡ. ΠΡΩΤ.:", align='R'); pdf.set_font('DejaVu', ''); pdf.cell(50, 10, data['protocol_number'])

# ############################################################################
# ΚΥΡΙΩΣ ΠΡΟΓΡΑΜΜΑ ΓΙΑ STREAMLIT
# ############################################################################

# Υποχρεωτικά πεδία για την προσφορά και οι "φιλικές" ονομασίες τους
REQUIRED_FIELDS = {
    "client_company": "επωνυμία εταιρείας", 
    "client_address": "οδός", 
    "client_tk": "ταχυδρομικός κώδικας (Τ.Κ.)", 
    "client_area": "περιοχή", 
    "installations": "αριθμός εγκαταστάσεων", 
    "unit_price": "τιμή μονάδας", 
    "offer_valid_until": "ημερομηνία λήξης προσφοράς"
}

# Έχουμε μόνο ένα προεπιλεγμένο χρώμα για τον πίνακα φορολογικής σήμανσης
DEFAULT_TABLE_HEADER_COLOR = (146, 208, 80) # Πράσινο

def get_missing_fields_names(missing_field_keys):
    """Μεταφράζει τα keys των ελλειπόντων πεδίων σε φιλικές ονομασίες."""
    return [REQUIRED_FIELDS.get(key, key) for key in missing_field_keys]

# Function to parse natural language input using Gemini API
def parse_natural_language_input(prompt_text):
    base_prompt = f"""
    Είσαι ένας φιλικός βοηθός της S-Team που δημιουργεί προσφορές.
    Αρχικά, προσπάθησε να καταλάβεις αν ο χρήστης ζητάει μια προσφορά ή κάνει μια γενική ερώτηση/χαιρετισμό.

    Αν ο χρήστης ζητάει μια προσφορά, εξάγαγε όλες τις ακόλουθες πληροφορίες από το παρακάτω κείμενο αιτήματος σε μορφή JSON.
    Χρησιμοποίησε μόνο λατινικούς χαρακτήρες για τα keys του JSON.
    Εάν κάποια πληροφορία δεν αναφέρεται σαφώς στο κείμενο, άφησε την αντίστοιχη τιμή κενή (null).

    Απαραίτητα πεδία για προσφορά (με ακριβώς αυτά τα ονόματα):
    - client_company (string): Επωνυμία της εταιρείας του πελάτη.
    - client_address (string): Οδός και αριθμός.
    - client_tk (string): Ταχυδρομικός κώδικας.
    - client_area (string): Περιοχή.
    - client_phone (string): Τηλέφωνο επικοινωνίας (προαιρετικό).
    - installations (integer): Αριθμός εγκαταστάσεων.
    - unit_price (float): Τιμή μονάδας.
    - offer_valid_until (string): Ημερομηνία λήξης προσφοράς σε μορφή DD/MM/YYYY.
    - include_tech_description (boolean): True αν θέλει την ενότητα "Τεχνική Περιγραφή", False αν δεν την θέλει (π.χ., "μη συμπεριλάβεις τεχνική περιγραφή"). Προεπιλεγμένη τιμή: True.
    - include_tax_solutions (boolean): True αν θέλει την ενότητα "Λύσεις Φορολογικής Σήμανσης", False αν δεν την θέλει (π.χ., "χωρίς φορολογική σήμανση"). Προεπιλεγμένη τιμή: True.

    Αν ο χρήστης κάνει μια γενική ερώτηση ή χαιρετισμό και ΔΕΝ ζητάει προσφορά, τότε απάντησε με ένα φιλικό, ανθρώπινο μήνυμα, χωρίς JSON.
    Για παράδειγμα, αν ο χρήστης πει "γεια", απάντησε "Γεια σας! Πώς μπορώ να σας εξυπηρετήσω σήμερα; Αν χρειάζεστε μια προσφορά, πείτε μου τα στοιχεία της εταιρείας σας."

    ΣΗΜΑΝΤΙΚΟ:
    1. Αν πρόκειται για αίτημα προσφοράς, Επίστρεψε ΜΟΝΟ το JSON αντικείμενο, χωρίς επιπλέον κείμενο ή σχόλια.
    2. Αν δεν πρόκειται για αίτημα προσφοράς (π.χ. χαιρετισμός, γενική ερώτηση), Επίστρεψε ΜΟΝΟ το φιλικό κείμενο.
    3. Εάν δεν μπορείς να εξάγεις μια τιμή για πεδίο JSON, χρησιμοποίησε `null` για strings/dates/numbers (αν δεν αναφέρονται).
    4. Μην συμπεριλαμβάνεις "ΦΠΑ" στην τιμή, μόνο την καθαρή αριθμητική τιμή.
    5. Να είσαι ευέλικτος στην αναγνώριση των ελληνικών χαρακτήρων και συντομογραφιών.

    Κείμενο αιτήματος: "{prompt_text}"
    """
    
    try:
        response = model.generate_content(base_prompt)
        raw_response_text = response.text.strip()
        
        # Πρώτα προσπαθούμε να αναλύσουμε ως JSON
        json_string = raw_response_text
        if json_string.startswith("```json") and json_string.endswith("```"):
            json_string = json_string[7:-3].strip()
        
        try:
            parsed_data = json.loads(json_string)
            # Αν η ανάλυση ως JSON πετύχει, είναι αίτημα προσφοράς
            is_offer_request = True
        except json.JSONDecodeError:
            # Αν αποτύχει, είναι πιθανόν γενική απάντηση
            is_offer_request = False
            parsed_data = {} # Θέτουμε κενό dict για να αποφύγουμε λάθη

        if is_offer_request:
            # CORRECTED: Handle NoneType explicitly for installations and unit_price
            installations_val = parsed_data.get('installations')
            if installations_val is None:
                parsed_data['installations'] = 1
            else:
                parsed_data['installations'] = int(installations_val)

            unit_price_val = parsed_data.get('unit_price')
            if unit_price_val is None:
                parsed_data['unit_price'] = 120.00
            else:
                parsed_data['unit_price'] = float(unit_price_val)

            parsed_data['offer_valid_until'] = parsed_data.get('offer_valid_until', "31/12/2025")
            
            parsed_data['include_tech_description'] = str(parsed_data.get('include_tech_description', True)).lower() == 'true'
            parsed_data['include_tax_solutions'] = str(parsed_data.get('include_tax_solutions', True)).lower() == 'true'
            
            return {
                "type": "offer_data",
                "data": {
                    "client_company": parsed_data.get('client_company'),
                    "client_address": parsed_data.get('client_address'),
                    "client_tk": parsed_data.get('client_tk'),
                    "client_area": parsed_data.get('client_area'),
                    "client_phone": parsed_data.get('client_phone'),
                    "installations": parsed_data['installations'], 
                    "unit_price": parsed_data['unit_price'],     
                    "offer_valid_until": parsed_data['offer_valid_until'],
                    "include_tech_description": parsed_data['include_tech_description'],
                    "include_tax_solutions": parsed_data['include_tax_solutions']
                }
            }
        else:
            # Αν δεν είναι JSON, είναι απάντηση σε γενική ερώτηση
            return {"type": "general_response", "content": raw_response_text}

    except Exception as e:
        st.error(f"Σφάλμα κατά την επικοινωνία με το Gemini API ή ανάλυση: {e}")
        st.info("Βεβαιωθείτε ότι το API key είναι σωστό και ότι έχετε συνδεσιμότητα στο Internet.")
        st.exception(e) 
        return {"type": "error", "content": "Προέκυψε ένα σφάλμα κατά την επικοινωνία με τον βοηθό."}

# Fallback RegEx parser - Ενημερώθηκε για αφαίρεση χρώματος και για boolean defaults
def parse_with_regex_fallback(text):
    data = {
        "client_company": None, "client_address": None, "client_tk": None,
        "client_area": None, "client_phone": None, 
        "installations": 1, "unit_price": 120.00, "offer_valid_until": "31/12/2025",
        "include_tech_description": True, "include_tax_solutions": True
    }

    company_match = re.search(r'(?:εταιρεία|επιχείρηση|για την)\s+[\'"]?([^"\']+)[\'"]?', text, re.IGNORECASE | re.UNICODE)
    if company_match:
        data['client_company'] = company_match.group(1).strip().replace('.', '').replace(',', '')

    address_match = re.search(r'(?:οδ[οό])\s+([^,]+?)\s+(\d+)', text, re.IGNORECASE | re.UNICODE)
    if address_match:
        data['client_address'] = f"{address_match.group(1).strip()} {address_match.group(2).strip()}"

    tk_match = re.search(r'(?:τ[.]?κ[.]?|Τ[.]?Κ[.]?)\s*(\d{5}|\d{3}\s*\d{2})', text, re.IGNORECASE | re.UNICODE)
    if tk_match:
        data['client_tk'] = tk_match.group(1).replace(' ', '')

    area_match = re.search(r'(?:περιοχή|στην)\s+([Α-Ωα-ω\s]+?)(?:,|$|\.|\b)', text, re.IGNORECASE | re.UNICODE)
    if area_match:
        potential_area = area_match.group(1).strip()
        if len(potential_area) > 2 and not potential_area.lower().startswith('οδό'):
            data['client_area'] = potential_area

    phone_match = re.search(r'(?:τηλ[.]?|τηλέφωνο|τηλεφωνο)\s*(\+?\d{9,14})', text, re.IGNORECASE | re.UNICODE)
    if phone_match:
        data['client_phone'] = phone_match.group(1)

    installations_match = re.search(r'(\d+)\s+(?:εγκαταστάσεις|installations|inst)', text, re.IGNORECASE | re.UNICODE)
    if installations_match:
        data['installations'] = int(installations_match.group(1))

    price_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:€|ευρώ|ευρω)', text, re.IGNORECASE | re.UNICODE)
    if price_match:
        price_str = price_match.group(1).replace(',', '.')
        data['unit_price'] = float(price_str)

    date_match = re.search(r'(?:μέχρι|εώς)\s+(?:της?\s+)?(\d{1,2}/\d{1,2}/(?:\d{2}|\d{4}))', text, re.IGNORECASE | re.UNICODE)
    if date_match:
        date_str = date_match.group(1)
        parts = date_str.split('/')
        if len(parts) == 3 and len(parts[2]) == 2:
            current_year_prefix = str(time.localtime().tm_year)[:2]
            date_str = f"{parts[0]}/{parts[1]}/{current_year_prefix}{parts[2]}"
        data['offer_valid_until'] = date_str

    # RegEx for include/exclude sections (basic)
    if re.search(r'(?:μη συμπεριλάβετε|χωρίς|βγάλτε)\s+(?:την\s+)?τεχνική περιγραφή', text, re.IGNORECASE | re.UNICODE):
        data['include_tech_description'] = False
    if re.search(r'(?:μη συμπεριλάβετε|χωρίς|βγάλτε)\s+(?:την\s+)?φορολογική σήμανση', text, re.IGNORECASE | re.UNICODE):
        data['include_tax_solutions'] = False
    
    return data


def main():
    st.set_page_config(layout="wide")
    st.title("Δημιουργία Προσφοράς Λογισμικού S-Team")

    st.sidebar.header("Επιλογές Εισαγωγής")
    input_mode = st.sidebar.radio(
        "Πώς θέλετε να εισάγετε τα στοιχεία;",
        ("Συμπλήρωση Πεδίων", "Συνομιλία")
    )

    # Αρχικοποίηση session_state για τα στοιχεία της προσφοράς, αν δεν υπάρχουν
    if 'offer_details' not in st.session_state:
        st.session_state.offer_details = {
            "client_company": None, "client_address": None, "client_tk": None,
            "client_area": None, "client_phone": None, "installations": 1,
            "unit_price": 120.00, "offer_valid_until": "31/12/2025"
        }
        st.session_state.parsed_offer_data = { # Για το chat_mode
            "client_company": None, "client_address": None, "client_tk": None,
            "client_area": None, "client_phone": None, "installations": 1,
            "unit_price": 120.00, "offer_valid_until": "31/12/2025",
            "include_tech_description": True, # Default to include
            "include_tax_solutions": True # Default to include
        }
        st.session_state.chat_messages = [] 
        st.session_state.all_fields_complete = False 
    
    if input_mode == "Συμπλήρωση Πεδίων":
        st.header("Συμπλήρωση Στοιχείων Πελάτη")
        col1, col2 = st.columns(2)

        with col1:
            st.session_state.offer_details['client_company'] = st.text_input("Επωνυμία Πελάτη:", st.session_state.offer_details['client_company'] or "Δοκιμαστική Εταιρεία Α.Ε.")
            st.session_state.offer_details['client_address'] = st.text_input("Οδός Πελάτη:", st.session_state.offer_details['client_address'] or "Λεωφ. Δοκιμών 123")
            st.session_state.offer_details['client_tk'] = st.text_input("Τ.Κ. Πελάτη:", st.session_state.offer_details['client_tk'] or "123 45")
            st.session_state.offer_details['client_area'] = st.text_input("Περιοχή Πελάτη:", st.session_state.offer_details['client_area'] or "Αθήνα")
            st.session_state.offer_details['client_phone'] = st.text_input("Τηλέφωνο Πελάτη:", st.session_state.offer_details['client_phone'] or "")
        
        with col2:
            st.text_input("Αριθμός Πρωτοκόλλου (δημιουργείται στο PDF):", "Αυτόματος", disabled=True)
            st.text_input("Ημερομηνία Έκδοσης (δημιουργείται στο PDF):", "Αυτόματη", disabled=True)
            st.session_state.offer_details['offer_valid_until'] = st.text_input("Προσφορά Ισχύει έως (DD/MM/YYYY):", st.session_state.offer_details['offer_valid_until'] or "31/12/2025")
            
            st.markdown("---")
            st.subheader("Στοιχεία Λογισμικού")
            st.session_state.offer_details['installations'] = st.number_input("Αριθμός Εγκαταστάσεων:", min_value=1, value=st.session_state.offer_details['installations'])
            st.session_state.offer_details['unit_price'] = st.number_input("Τιμή Μονάδας (€):", min_value=0.0, value=st.session_state.offer_details['unit_price'], format="%.2f")

            st.markdown("---")
            st.subheader("Προσαρμογή PDF")
            st.session_state.parsed_offer_data['include_tech_description'] = st.checkbox(
                "Συμπερίληψη 'Τεχνικής Περιγραφής';", 
                value=st.session_state.parsed_offer_data['include_tech_description'],
                key="form_include_tech_desc"
            )
            st.session_state.parsed_offer_data['include_tax_solutions'] = st.checkbox(
                "Συμπερίληψη 'Λύσεων Φορολογικής Σήμανσης';", 
                value=st.session_state.parsed_offer_data['include_tax_solutions'],
                key="form_include_tax_sol"
            )

        offer_data_for_validation = {**st.session_state.offer_details, 
                                     "include_tech_description": st.session_state.parsed_offer_data['include_tech_description'],
                                     "include_tax_solutions": st.session_state.parsed_offer_data['include_tax_solutions']}

        if st.button("Δημιουργία PDF Προσφοράς"):
            missing_fields = [f for f in REQUIRED_FIELDS if offer_data_for_validation.get(f) is None or str(offer_data_for_validation.get(f)).strip() == "" or (isinstance(offer_data_for_validation.get(f), (int, float)) and offer_data_for_validation.get(f) == 0)]
            if missing_fields:
                st.warning(f"Παρακαλώ συμπληρώστε τα ακόλουθα υποχρεωτικά πεδία: {', '.join(get_missing_fields_names(missing_fields))}")
            else:
                current_protocol_number = f"PR{int(time.time())}"
                current_issue_date = time.strftime("%d/%m/%Y")
                
                final_offer_data = {
                    **offer_data_for_validation,
                    "protocol_number": current_protocol_number,
                    "issue_date": current_issue_date
                }
                generate_pdf_and_display(final_offer_data)

    elif input_mode == "Συνομιλία":
        st.header("Εισαγωγή Στοιχείων μέσω Συνομιλίας")
        
        for message in st.session_state.chat_messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        chat_input = st.chat_input(
            "Γράψε την εντολή σου εδώ:", 
            key="chat_input_text_area"
        )
        
        if chat_input:
            st.session_state.chat_messages.append({"role": "user", "content": chat_input})
            with st.chat_message("user"):
                st.markdown(chat_input)

            with st.spinner("Αναλύω το κείμενο... Παρακαλώ περιμένετε."):
                parsed_gemini_response = parse_natural_language_input(chat_input)
            
            if parsed_gemini_response["type"] == "offer_data":
                newly_parsed_data = parsed_gemini_response["data"]
                
                for key, value in newly_parsed_data.items():
                    if value is not None and \
                       (isinstance(value, str) and value.strip() != "" or not isinstance(value, str)) and \
                       (key not in ['installations', 'unit_price', 'offer_valid_until', 'include_tech_description', 'include_tax_solutions'] or \
                        (key == 'installations' and value != 1) or \
                        (key == 'unit_price' and value != 120.00) or \
                        (key == 'offer_valid_until' and value != "31/12/2025") or \
                        (key == 'include_tech_description' and value != True) or \
                        (key == 'include_tax_solutions' and value != True)):
                        
                        st.session_state.parsed_offer_data[key] = value

                st.session_state.parsed_offer_data['installations'] = int(st.session_state.parsed_offer_data.get('installations', 1))
                st.session_state.parsed_offer_data['unit_price'] = float(st.session_state.parsed_offer_data.get('unit_price', 120.00))
                st.session_state.parsed_offer_data['offer_valid_until'] = st.session_state.parsed_offer_data.get('offer_valid_until', "31/12/2025")
                st.session_state.parsed_offer_data['include_tech_description'] = bool(st.session_state.parsed_offer_data.get('include_tech_description', True))
                st.session_state.parsed_offer_data['include_tax_solutions'] = bool(st.session_state.parsed_offer_data.get('include_tax_solutions', True))

                missing_fields_keys = [f for f in REQUIRED_FIELDS if st.session_state.parsed_offer_data.get(f) is None or str(st.session_state.parsed_offer_data.get(f)).strip() == "" or (isinstance(st.session_state.parsed_offer_data.get(f), (int, float)) and st.session_state.parsed_offer_data.get(f) == 0)]
                
                with st.chat_message("assistant"):
                    if missing_fields_keys:
                        missing_names = get_missing_fields_names(missing_fields_keys)
                        response_message = f"Χρειάζομαι ακόμα κάποιες πληροφορίες για να δημιουργίσω την προσφορά. Μπορείτε να μου πείτε την/τον/το/τα **{', '.join(missing_names)}**;"
                        st.markdown(response_message)
                        st.session_state.chat_messages.append({"role": "assistant", "content": response_message})
                        st.session_state.all_fields_complete = False 
                    else:
                        response_message = "Έχω όλα τα απαραίτητα στοιχεία! Είμαι έτοιμος να δημιουργίσω την προσφορά."
                        st.markdown(response_message)
                        st.session_state.chat_messages.append({"role": "assistant", "content": response_message})
                        st.session_state.all_fields_complete = True 
            elif parsed_gemini_response["type"] == "general_response":
                with st.chat_message("assistant"):
                    st.markdown(parsed_gemini_response["content"])
                    st.session_state.chat_messages.append({"role": "assistant", "content": parsed_gemini_response["content"]})
                st.session_state.all_fields_complete = False # Επειδή ήταν γενική απάντηση, δεν είναι πλήρη τα πεδία για προσφορά
            else: # type == "error"
                with st.chat_message("assistant"):
                    st.markdown(parsed_gemini_response["content"])
                    st.session_state.chat_messages.append({"role": "assistant", "content": parsed_gemini_response["content"]})
                st.session_state.all_fields_complete = False 

        # Κουμπί "Δημιουργία PDF Προσφοράς"
        if st.session_state.all_fields_complete:
            current_protocol_number = f"PR{int(time.time())}"
            current_issue_date = time.strftime("%d/%m/%Y")

            final_offer_data_for_pdf = {
                **st.session_state.parsed_offer_data, # Στοιχεία από το chat
                "protocol_number": current_protocol_number, # Νέος αριθμός
                "issue_date": current_issue_date # Νέα ημερομηνία
            }
            if st.button("Δημιουργία PDF Προσφοράς"):
                generate_pdf_and_display(final_offer_data_for_pdf)
        else:
            st.info("Συμπληρώστε όλα τα απαραίτητα στοιχεία στη συνομιλία για να ενεργοποιηθεί η δημιουργία PDF.")
        
        # Προσθήκη ενός κουμπιού "Επαναφορά Συνομιλίας"
        if st.button("Επαναφορά Συνομιλίας & Καθαρισμός Στοιχείων", key="reset_chat_button"):
            st.session_state.parsed_offer_data = {
                "client_company": None, "client_address": None, "client_tk": None,
                "client_area": None, "client_phone": None, "installations": 1,
                "unit_price": 120.00, "offer_valid_until": "31/12/2025",
                "include_tech_description": True, # Επαναφορά default
                "include_tax_solutions": True # Επαναφορά default
            } 
            st.session_state.chat_messages = [] 
            st.session_state.all_fields_complete = False 
            st.rerun() 

def generate_pdf_and_display(data):
    pdf = OfferPDF('P', 'mm', 'A4')
    
    st.write("Δημιουργία σελίδων PDF...")

    # Λογική για τη δυναμική δημιουργία TOC και αρίθμησης σελίδων
    calculated_toc_entries = []
    chapter_num = 1 # Μετρητής για τους αριθμούς των κεφαλαίων στο TOC
    current_page_num = 1 # Μετρητής για τους αριθμούς των σελίδων στο PDF

    # Δομή των ενοτήτων με τους αρχικούς τους τίτλους
    sections_config = [
        {"id": "intro", "title": "ΕΙΣΑΓΩΓΗ", "create_func": create_page_1_intro, "always_include": True},
        {"id": "tech_desc", "title": "ΤΕΧΝΙΚΗ ΠΕΡΙΓΡΑΦΗ", "create_func": create_page_2_tech_desc, "include_key": "include_tech_description"},
        {"id": "financials", "title": "ΟΙΚΟΝΟΜΙΚΗ ΠΡΟΤΑΣΗ", "create_func": create_page_3_financials, "always_include": True},
        {"id": "tax_solutions", "title": "ΛΥΣΕΙΣ ΦΟΡΟΛΟΓΙΚΗΣ ΣΗΜΑΝΣΗΣ", "create_func": create_page_4_tax_solutions, "include_key": "include_tax_solutions"},
        {"id": "terms", "title": "ΟΡΟΙ ΚΑΙ ΠΡΟΥΠΟΘΕΣΕΙΣ", "create_func": create_page_5_terms, "always_include": True},
        {"id": "acceptance", "title": "ΣΥΜΠΛΗΡΩΣΗ ΣΤΟΙΧΕΙΩΝ", "create_func": create_page_6_acceptance, "always_include": True},
    ]

    # Πρώτο πέρασμα: Υπολογισμός TOC και αρίθμησης κεφαλαίων/σελίδων
    for section in sections_config:
        should_include = False
        if section.get("always_include"):
            should_include = True
        elif section.get("include_key") and data.get(section["include_key"], True):
            should_include = True
        
        if should_include:
            section_title_with_num = f"{chapter_num}. {section['title']}"
            calculated_toc_entries.append((section_title_with_num, current_page_num))
            
            chapter_num += 1
            current_page_num += 1

    # Τώρα που έχουμε το TOC με σωστούς αριθμούς κεφαλαίων και σελίδων, μπορούμε να δημιουργήσουμε το PDF.
    try:
        # Κλήση της create_page_1_intro με το υπολογισμένο TOC
        create_page_1_intro(pdf, data, calculated_toc_entries) 
        
        # Δεύτερο πέρασμα: Πραγματική δημιουργία σελίδων στο PDF
        # Ξεκινάμε από την 2η ενότητα (index 1), καθώς η 1η (intro) έχει ήδη δημιουργηθεί
        for section in sections_config[1:]: 
            should_include = False
            if section.get("always_include"):
                should_include = True
            elif section.get("include_key") and data.get(section["include_key"], True):
                should_include = True
            
            if should_include:
                # Καλούμε τη συνάρτηση δημιουργίας σελίδας με τα κατάλληλα arguments
                if section["id"] in ["financials", "terms", "acceptance"]: # Όσες χρειάζονται το data dict
                    section["create_func"](pdf, data)
                else: # Για τις υπόλοιπες συναρτήσεις που δεν χρειάζονται extra params (π.χ. create_page_2_tech_desc, create_page_4_tax_solutions)
                    section["create_func"](pdf)
        
        filename = f"Offer_{data['client_company'].replace(' ', '_').replace('.', '').replace(',', '')}.pdf"
        
        pdf_output = bytes(pdf.output(dest='S')) 
        
        st.success(f"Το PDF δημιουργήθηκε με επιτυχία: '{filename}'")
        st.download_button(
            label="Λήψη PDF Προσφοράς",
            data=pdf_output,
            file_name=filename,
            mime="application/pdf"
        )
    except Exception as e:
        st.error(f"Σφάλμα κατά τη δημιουργία του PDF: {e}")
        st.exception(e)

if __name__ == "__main__":
    main()