"""
=============================================================================
  PAIA - Personal Academic Intelligence Agent
  Dibuat untuk Mahasiswa TRPL - Politeknik Negeri Madiun
=============================================================================
  Arsitektur : OOP (TelegramNotifier, ExplorerAgent, GeminiBrain, Orchestrator)
  Runtime    : GitHub Actions (Ubuntu) - Cron setiap jam
  AI Engine  : Google Gemini 1.5 Pro
  Notifikasi : Telegram Bot API
  Pencarian  : DuckDuckGo Search + BeautifulSoup (Sevima Placeholder)
=============================================================================
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta

import pytz
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from notion_client import Client
import google.generativeai as genai

# ── Muat environment variables dari file .env (untuk development lokal) ──
load_dotenv()

# ── Konfigurasi logging agar output GitHub Actions mudah dibaca ──────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("PAIA")

# ── Timezone Asia/Jakarta (WIB, UTC+7) ───────────────────────────────────
WIB = pytz.timezone("Asia/Jakarta")

# ─────────────────────────────────────────────────────────────────────────
#  FALLBACK JADWAL ORGANISASI (Statis - isi sesuai jadwal HIMA kamu)
#  Jadwal kuliah diambil otomatis dari Edlink API (fetch_edlink_jadwal).
#  Hanya organisasi yang statis karena tidak ada di Edlink.
# ─────────────────────────────────────────────────────────────────────────
JADWAL_ORGANISASI_HIMA = [
    {
        "nama": "Rapat PSDM",
        "topik": "Evaluasi Program Kerja Semester",
        "waktu": "2026-04-26 19:00",
        "tipe": "Rapat Wajib",
        "prioritas": "TINGGI",
    },
    {
        "nama": "Follow-up Rekrutmen",
        "topik": "Rekapitulasi data calon anggota baru",
        "waktu": "2026-04-27 15:00",
        "tipe": "Tugas Organisasi",
        "prioritas": "SEDANG",
    },
]

# Fallback jadwal kuliah — dipakai HANYA jika Edlink API tidak bisa diakses
JADWAL_KULIAH_FALLBACK = [
    {"nama": "Komputasi Statistika", "hari": "Senin", "jam_mulai": "08:40", "jam_selesai": "10:35", "ruangan": "315"},
    {"nama": "Pengujian Perangkat Lunak", "hari": "Senin", "jam_mulai": "13:35", "jam_selesai": "14:05", "ruangan": "Lab Multimedia"},
    {"nama": "Wawasan Transportasi Berkelanjutan", "hari": "Selasa", "jam_mulai": "08:40", "jam_selesai": "10:35", "ruangan": "313"},
    {"nama": "Pemrograman Mobile II", "hari": "Selasa", "jam_mulai": "12:45", "jam_selesai": "13:35", "ruangan": "-"},
    {"nama": "Praktik Pemrograman Mobile II", "hari": "Selasa", "jam_mulai": "13:35", "jam_selesai": "14:05", "ruangan": "-"},
    {"nama": "Kecerdasan Buatan", "hari": "Rabu", "jam_mulai": "08:00", "jam_selesai": "10:15", "ruangan": "-"},
    {"nama": "Bahasa Inggris", "hari": "Rabu", "jam_mulai": "12:45", "jam_selesai": "14:25", "ruangan": "301"},
    {"nama": "Manajemen Risiko Perangkat Lunak", "hari": "Kamis", "jam_mulai": "10:35", "jam_selesai": "12:15", "ruangan": "313"},
    {"nama": "Arsitektur Perangkat Lunak", "hari": "Kamis", "jam_mulai": "12:45", "jam_selesai": "14:25", "ruangan": "313"},
    {"nama": "Data Engineering", "hari": "Jumat", "jam_mulai": "07:00", "jam_selesai": "11:15", "ruangan": "-"},
]

# Kata kunci topik yang akan dipicu pencarian otomatis referensi
# Kata kunci topik yang akan dipicu pencarian otomatis referensi
TOPIK_TRIGGER_SEARCH = [
    # Mobile Programming II
    "Retrofit", "Firebase Auth", "SQLite Android", "Jetpack Compose", "MVVM Pattern",
    # Pengujian Perangkat Lunak
    "Whitebox Testing", "Blackbox Testing", "Cyclomatic Complexity", "Selenium", "JUnit",
    # Kecerdasan Buatan (AI)
    "Fuzzy Logic", "Neural Network", "Naive Bayes", "Machine Learning Python",
    # Arsitektur & Manajemen Risiko
    "Microservices", "REST API", "Risk Mitigation", "ISO 27001", "Agile Scrum",
    # Data Engineering
    "ETL Pipeline", "Data Warehouse", "SQL Optimization", "NoSQL MongoDB"
]


# =============================================================================
#  KELAS 1: TelegramManager
#  Bertanggung jawab mengirim pesan dan membaca input dari Telegram
# =============================================================================
class TelegramManager:
    """Mengelola notifikasi dan input pesan ke/dari Telegram menggunakan Bot API."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.offset_file = "last_update_id.txt"
        log.info("TelegramManager siap.")

    def kirim_pesan(self, teks: str, mode: str = "HTML") -> bool:
        """Kirim pesan ke Telegram."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": teks,
            "parse_mode": mode,
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            log.info("✅ Pesan Telegram berhasil dikirim.")
            return True
        except Exception as e:
            log.error(f"❌ Error kirim Telegram: {e}")
            return False

    def get_unread_updates(self) -> list:
        """Ambil data JSON mentah dari getUpdates tanpa offset (Manual-ACK)."""
        url = f"{self.base_url}/getUpdates"
        try:
            resp = requests.get(url, params={"timeout": 10}, timeout=20)
            resp.raise_for_status()
            return resp.json().get("result", [])
        except Exception as e:
            log.error(f"❌ Error get_unread_updates: {e}")
            return []

    def mark_as_read(self, last_update_id: int):
        """Kirim offset untuk membersihkan antrean yang sukses diproses."""
        url = f"{self.base_url}/getUpdates"
        try:
            requests.get(url, params={"offset": last_update_id + 1}, timeout=10)
            log.info(f"🗑️ Antrean Telegram dibersihkan hingga ID: {last_update_id}")
        except Exception as e:
            log.error(f"❌ Gagal mark_as_read: {e}")

    def kirim_morning_briefing(self, konten: str):
        self.kirim_pesan(konten, mode="HTML")

    def kirim_panic_reminder(self, tugas: dict):
        pesan = (
            f"🔴 <b>PANIC REMINDER!</b>\n\n"
            f"⚠️ Kelas akan segera dimulai!\n\n"
            f"📌 <b>Mata Kuliah:</b> {tugas['nama']}\n"
            f"⏰ <b>Mulai:</b> {tugas['jam_mulai']}\n\n"
            f"💪 <i>Segera bersiap!</i>"
        )
        self.kirim_pesan(pesan, mode="HTML")

    def kirim_task_reminder(self, tugas: dict):
        pesan = (
            f"🔔 <b>REMINDER TUGAS!</b>\n\n"
            f"⚠️ Jangan lupa ada tugas yang mendekati deadline!\n\n"
            f"📌 <b>Tugas:</b> {tugas['nama']}\n"
            f"⏰ <b>Deadline:</b> {tugas['deadline']}\n\n"
            f"💻 <i>Segera diselesaikan ya!</i>"
        )
        self.kirim_pesan(pesan, mode="HTML")


# =============================================================================
#  KELAS 2: ExplorerAgent
#  Sistem pencari proaktif - DuckDuckGo + placeholder Sevima Edlink
# =============================================================================
class ExplorerAgent:
    """Agen pencarian referensi dan scraping portal akademik."""

    def __init__(self):
        log.info("ExplorerAgent siap.")

    def web_search(self, query: str, max_hasil: int = 3) -> list[dict]:
        """
        Cari referensi/tutorial menggunakan DuckDuckGo Search.
        :param query: Kata kunci pencarian
        :param max_hasil: Jumlah hasil maksimal yang dikembalikan
        :return: List dict berisi title, url, snippet
        """
        log.info(f"🔍 Mencari referensi: '{query}'")
        hasil = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_hasil):
                    hasil.append({
                        "judul": r.get("title", "Tanpa Judul"),
                        "url": r.get("href", "#"),
                        "snippet": r.get("body", "")[:150],
                    })
            log.info(f"✅ Ditemukan {len(hasil)} referensi untuk '{query}'.")
        except Exception as e:
            log.error(f"❌ DuckDuckGo search gagal untuk '{query}': {e}")
        return hasil

    def cari_referensi_topik(self, daftar_tugas: list) -> dict:
        """
        Iterasi semua tugas dan cari referensi jika topik cocok dengan trigger.
        :param daftar_tugas: List dict berisi info tugas
        :return: Dict {topik: [list referensi]}
        """
        referensi_map = {}
        for tugas in daftar_tugas:
            topik = tugas.get("topik", "")
            for trigger in TOPIK_TRIGGER_SEARCH:
                if trigger.lower() in topik.lower():
                    query = f"tutorial {trigger} untuk pemula bahasa Indonesia"
                    hasil = self.web_search(query)
                    if hasil:
                        referensi_map[trigger] = hasil
                    break  # Satu trigger per tugas cukup
        return referensi_map

    def get_jadwal_kuliah(self) -> list[dict]:
        """
        Mengambil jadwal kuliah. 
        Karena Edlink sering expired, kita gunakan sistem Fallback Statis (TRPL 4B) yang akurat.
        """
        log.info("📅 Menggunakan jadwal kuliah Fallback (TRPL 4B)...")
        # Tandai mana yang hari ini
        hari_ini = datetime.now(WIB).strftime("%A")
        # Buat copy agar tidak merusak data original
        jadwal = [dict(x) for x in JADWAL_KULIAH_FALLBACK]
        for item in jadwal:
            item["adalah_hari_ini"] = item["hari"].lower() == hari_ini.lower()
        return jadwal



# =============================================================================
#  KELAS 3: GeminiBrain
#  Engine kecerdasan - menganalisis jadwal dan menyusun prioritas harian
# =============================================================================
class GeminiBrain:
    """Otak AI berbasis Google Gemini 1.5 Pro untuk analisis dan perencanaan."""

    # System prompt yang mendefinisikan kepribadian dan konteks AI
    SYSTEM_PROMPT = """
Kamu adalah PAIA (Personal Academic Intelligence Agent), asisten mahasiswa cerdas 
untuk program studi Teknologi Rekayasa Perangkat Lunak (TRPL) di Politeknik Negeri Madiun.

Identitas & Kepribadian:
- Kamu mengenal pengguna sebagai mahasiswa aktif yang juga menjabat sebagai pengurus 
  organisasi PSDM Hima, sehingga kamu paham tekanan antara tugas akademik dan kewajiban organisasi.
- Kamu berbicara dalam Bahasa Indonesia yang santai tapi tetap profesional, seperti senior 
  yang benar-benar peduli pada perkembangan juniornya.
- Kamu TIDAK pernah meremehkan atau menghakimi. Kamu selalu memberi semangat.

Keahlian Teknis:
- Mobile Programming: Kotlin, Android Jetpack Compose, ViewModel, Coroutines, Retrofit
- Web Backend: PHP Laravel (MVC, Eloquent ORM, Middleware, Blade, REST API)
- Data Engineering: BigQuery, ETL Pipeline, Python Pandas, Apache Kafka
- Database: MySQL, PostgreSQL, Stored Procedure, Trigger, Indexing

Cara Memprioritaskan Tugas:
1. KRITIS (deadline < 12 jam) → Fokus 100%, pecah jadi langkah kecil, kerjakan sekarang
2. TINGGI (deadline < 3 hari) → Buat rencana kerja bertahap hari ini
3. SEDANG (deadline < 7 hari) → Sisihkan 1-2 jam per hari, jangan ditunda
4. Jika ada rapat organisasi → Anggarkan 1-2 jam sebelumnya untuk persiapan

Cara Memecah Tugas Coding (contoh MVC Laravel):
  Langkah 1: Setup Route & Controller skeleton (15 menit)
  Langkah 2: Buat Migration & Model Eloquent (20 menit)
  Langkah 3: Implementasi logika di Controller (45 menit)
  Langkah 4: Buat View Blade dengan form (30 menit)
  Langkah 5: Testing & debugging (20 menit)

Format output kamu SELALU dalam format HTML Telegram yang bersih dan mudah dibaca.
Gunakan <b>bold</b> untuk judul penting, <i>italic</i> untuk tips, dan emoji yang relevan.
"""

    def __init__(self, api_key: str):
        try:
            genai.configure(api_key=api_key)
            
            # Cek daftar model yang tersedia untuk API Key ini
            log.info("🔍 Mencari model Gemini yang tersedia untuk akun Anda...")
            available_models = [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
            log.info(f"📋 Model tersedia: {available_models}")

            # Urutan prioritas model yang akan dicoba (disesuaikan dengan akun Anda)
            priority_models = [
                "models/gemini-2.5-flash",
                "models/gemini-1.5-flash",
                "models/gemini-1.5-pro",
                "models/gemini-pro"
            ]

            selected_model = None
            for model_path in priority_models:
                if model_path in available_models:
                    selected_model = model_path
                    break
            
            if not selected_model and available_models:
                selected_model = available_models[0]
                log.warning(f"⚠️ Model prioritas tidak ditemukan, menggunakan: {selected_model}")

            if selected_model:
                self.model = genai.GenerativeModel(model_name=selected_model)
                log.info(f"✅ GeminiBrain siap menggunakan model: {selected_model}")
            else:
                log.error("❌ Tidak ada model generatif yang ditemukan untuk API Key ini.")
                self.model = None

        except Exception as e:
            log.error(f"❌ Gagal inisialisasi Gemini: {e}")
            self.model = None

    def analyze_and_plan(
        self,
        jadwal_kuliah: list,
        jadwal_org: list,
        referensi: dict,
        waktu_sekarang: datetime,
        tugas_notion: list = None,
    ) -> str:
        """
        Analisis jadwal harian dan buat rencana kerja dengan Gemini AI.

        :param jadwal_kuliah: List dict jadwal kuliah dari Edlink API (sudah dinormalisasi)
        :param jadwal_org: List dict kegiatan organisasi HIMA (statis)
        :param referensi: Dict {topik: [list link]} hasil pencarian DuckDuckGo
        :param waktu_sekarang: Objek datetime dengan timezone WIB
        :param tugas_notion: List dict tugas dari database Notion
        :return: String teks analisis dari Gemini (format HTML)
        """
        if not self.model:
            return "<b>❌ Gemini tidak tersedia. Periksa API key.</b>"

        tanggal_str = waktu_sekarang.strftime("%A, %d %B %Y pukul %H:%M WIB")
        hari_ini_str = waktu_sekarang.strftime("%A")

        # ── Format jadwal kuliah dari Edlink ──────────────────────────────
        # Pisahkan jadwal hari ini vs minggu ini untuk konteks yang lebih fokus
        jadwal_hari_ini = [j for j in jadwal_kuliah if j.get("adalah_hari_ini")]
        jadwal_minggu_ini = [j for j in jadwal_kuliah if not j.get("adalah_hari_ini")]

        def fmt_kuliah(j: dict) -> str:
            dosen = j.get('dosen', '-')
            return (
                f"  • {j['nama']} | {j['hari']} {j['jam_mulai']}-{j['jam_selesai']} "
                f"| Ruang: {j['ruangan']} | Dosen: {dosen}"
            )

        kuliah_hari_ini_str = (
            "\n".join(fmt_kuliah(j) for j in jadwal_hari_ini)
            if jadwal_hari_ini else "  (Tidak ada kelas hari ini)"
        )
        kuliah_minggu_str = (
            "\n".join(fmt_kuliah(j) for j in jadwal_minggu_ini)
            if jadwal_minggu_ini else "  (Tidak ada jadwal lain minggu ini)"
        )

        # ── Format kegiatan organisasi ────────────────────────────────────
        kegiatan_org_str = "\n".join([
            f"  • [{t['prioritas']}] {t['nama']}: {t['topik']} | Waktu: {t['waktu']}"
            for t in jadwal_org
        ]) if jadwal_org else "  (Tidak ada kegiatan organisasi terjadwal)"

        # ── Format referensi DuckDuckGo ───────────────────────────────────
        referensi_str = ""
        if referensi:
            for topik, links in referensi.items():
                referensi_str += f"\n  Referensi '{topik}':\n"
                for link in links:
                    referensi_str += f"    * {link['judul']}: {link['url']}\n"
                    
        # ── Format Tugas Notion ───────────────────────────────────────────
        tugas_str = ""
        if tugas_notion:
            tugas_str = "\n".join([f"  • {t['nama']} (Deadline: {t['deadline']})" for t in tugas_notion])
        else:
            tugas_str = "  (Tidak ada tugas aktif di Notion yang mendekati deadline)"

        prompt = f"""
Sekarang adalah {tanggal_str}.

JADWAL KULIAH HARI INI ({hari_ini_str}) — Data dari Edlink:
{kuliah_hari_ini_str}

JADWAL KULIAH SISA MINGGU INI — Data dari Edlink:
{kuliah_minggu_str}

KEGIATAN ORGANISASI HIMA:
{kegiatan_org_str}

TUGAS AKTIF DARI NOTION:
{tugas_str}

REFERENSI YANG SUDAH DIKUMPULKAN HARI INI:
{referensi_str if referensi_str else "  (Tidak ada referensi yang dikumpulkan otomatis hari ini)"}

Tolong buat Morning Briefing yang komprehensif untuk saya dalam format HTML Telegram.
Sertakan:
1. Sapaan pagi yang menyemangati (sebutkan hari dan tanggal)
2. Ringkasan kelas yang harus dihadiri hari ini beserta ruangannya
3. DAFTAR TUGAS NOTION: Sebutkan tugas-tugas yang ada, DAN berikan 1-2 kalimat PENJELASAN (maksud/tujuan) dari setiap tugas tersebut agar saya paham apa yang harus dikerjakan.
4. Tips persiapan untuk setiap mata kuliah hari ini (materi apa yang perlu dibaca)
5. Strategi menyeimbangkan kelas + kegiatan organisasi hari ini
6. Preview jadwal besok agar bisa persiapan dari sekarang
7. Jika ada referensi, cantumkan sebagai link HTML <a href="url">judul</a>
8. Penutup yang memotivasi

Pastikan format HTML rapi dan mudah dibaca di Telegram.
"""

        log.info("🧠 Mengirim prompt ke Gemini AI untuk analisis jadwal...")
        try:
            response = self.model.generate_content(prompt)
            log.info("✅ Gemini berhasil menganalisis jadwal.")
            return response.text
        except Exception as e:
            log.error(f"❌ Gemini generate_content gagal: {e}")
            return f"<b>❌ Analisis Gemini gagal:</b> <i>{e}</i>"

    def extract_task_from_text(self, text: str) -> dict:
        """Ekstrak input teks manual menjadi struktur data tugas."""
        if not self.model: return {}
        
        instruksi = f"""
{self.SYSTEM_PROMPT}

TUGAS KHUSUS:
Analisis teks berikut: "{text}"
Waktu sekarang: {datetime.now(WIB).strftime('%Y-%m-%d')}

Tentukan apakah pengguna ingin MENAMBAHKAN tugas baru, atau MENYELESAIKAN/MENGHAPUS tugas yang sudah ada.

Format output WAJIB HANYA JSON (tanpa blok kode lain):
{{
    "intent": "create" atau "complete",
    "task_name": "Nama tugas",
    "deadline": "YYYY-MM-DD" (jika create, kosongkan jika complete),
    "priority": "Tinggi/Sedang/Rendah" (jika create),
    "subtasks": ["step 1", "step 2"] (jika create),
    "explanation": "Penjelasan inti tugas (jika create), atau pujian/motivasi karena sudah selesai (jika complete)"
}}
"""
        try:
            res = self.model.generate_content(instruksi)
            clean_json = res.text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_json)
        except Exception as e:
            log.error(f"❌ Gagal ekstrak tugas: {e}")
            return {}

# =============================================================================
#  KELAS 5: NotionDashboard
#  Sinkronisasi data ke Notion
# =============================================================================
class NotionDashboard:
    def __init__(self, api_key: str, database_id: str):
        self.db_id = database_id
        try:
            self.client = Client(auth=api_key)
            log.info("NotionDashboard siap.")
        except Exception as e:
            log.error(f"❌ Notion init error: {e}")
            self.client = None

    def create_task_card(self, task_name, deadline, priority, subtasks, source):
        if not self.client: return False
        try:
            children = []
            if subtasks:
                children.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"text": {"content": "Subtasks"}}]}})
                for st in subtasks:
                    children.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": st}}]}})

            self.client.pages.create(
                parent={"database_id": self.db_id},
                properties={
                    "Name": {"title": [{"text": {"content": task_name}}]},
                    "Deadline": {"date": {"start": deadline}} if deadline else {"date": None},
                    "Priority": {"select": {"name": priority}},
                    "Source": {"select": {"name": source}}
                },
                children=children
            )
            return True
        except Exception as e:
            log.error(f"❌ Gagal buat Notion card: {e}")
            return False

    def mark_task_completed(self, task_name: str) -> bool:
        if not self.client: return False
        try:
            # Cari task berdasarkan nama
            response = self.client.databases.query(
                database_id=self.db_id,
                filter={
                    "property": "Name",
                    "title": {
                        "contains": task_name
                    }
                }
            )
            results = response.get("results", [])
            if not results:
                log.warning(f"⚠️ Tugas '{task_name}' tidak ditemukan di Notion.")
                return False
                
            # Archive (hapus) task pertama yang ditemukan
            page_id = results[0]["id"]
            self.client.pages.update(page_id, archived=True)
            log.info(f"🗑️ Tugas '{task_name}' berhasil dihapus/diselesaikan.")
            return True
        except Exception as e:
            log.error(f"❌ Gagal menghapus Notion card: {e}")
            return False

    def get_upcoming_tasks(self) -> list[dict]:
        if not self.client: return []
        try:
            # Ambil tugas yang belum selesai dan deadline hari ini/besok (atau abaikan filter untuk simplicity)
            # Kita ambil semua tugas yang belum 'Done' (asumsi belum ada filter status kompleks, kita ambil 10 terbaru saja)
            response = self.client.databases.query(
                database_id=self.db_id,
                page_size=10
            )
            tasks = []
            for page in response.get("results", []):
                props = page.get("properties", {})
                
                # Ekstrak nama
                name_prop = props.get("Name", {}).get("title", [])
                task_name = name_prop[0].get("plain_text", "Tanpa Judul") if name_prop else "Tanpa Judul"
                
                # Ekstrak deadline
                deadline_prop = props.get("Deadline", {}).get("date", {})
                deadline = deadline_prop.get("start", "-") if deadline_prop else "-"
                
                tasks.append({"nama": task_name, "deadline": deadline})
            return tasks
        except Exception as e:
            log.error(f"❌ Gagal fetch Notion tasks: {e}")
            return []


# =============================================================================
#  KELAS 4: PAIAOrchestrator
#  Koordinator utama - mengatur alur logika pagi vs jam lain
# =============================================================================
class PAIAOrchestrator:
    """Orkestrator PAIA - mengkoordinasikan semua komponen sesuai jadwal."""

    def __init__(self):
        # Ambil credentials
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        tg_token = os.getenv("TELEGRAM_TOKEN", "")
        tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        notion_key = os.getenv("NOTION_API_KEY", "")
        notion_db = os.getenv("NOTION_DATABASE_ID", "")

        # Validasi
        if not all([gemini_key, tg_token, tg_chat_id]):
            raise EnvironmentError("Missing core env vars")

        # Inisialisasi
        self.notifier = TelegramManager(tg_token, tg_chat_id)
        self.explorer = ExplorerAgent()
        self.brain = GeminiBrain(gemini_key)
        self.notion = NotionDashboard(notion_key, notion_db) if notion_key and notion_db else None

        # Ambil jadwal kuliah (Mandiri)
        self.jadwal_kuliah = self.explorer.get_jadwal_kuliah()
        self.jadwal_org = JADWAL_ORGANISASI_HIMA

        log.info("🚀 PAIAOrchestrator berhasil diinisialisasi.")

    def _cek_deadline_darurat(self) -> tuple[list[dict], list[dict]]:
        """
        Cek apakah ada kelas yang dimulai dalam 1 jam ke depan hari ini.
        Juga cek apakah ada tugas Notion yang deadlinenya hari ini atau besok.
        :return: Tuple (kelas_segera, tugas_segera)
        """
        sekarang = datetime.now(WIB)
        kelas_segera = []
        
        # 1. Cek Kelas Kuliah
        for kelas in self.jadwal_kuliah:
            if not kelas.get("adalah_hari_ini"):
                continue
            jam_mulai_str = kelas.get("jam_mulai", "")
            if not jam_mulai_str or jam_mulai_str == "-":
                continue
            try:
                # Gabungkan tanggal hari ini + jam mulai kelas
                tanggal_hari_ini = sekarang.strftime("%Y-%m-%d")
                waktu_kelas = datetime.strptime(
                    f"{tanggal_hari_ini} {jam_mulai_str}", "%Y-%m-%d %H:%M"
                )
                waktu_kelas_wib = WIB.localize(waktu_kelas)
                selisih_jam = (waktu_kelas_wib - sekarang).total_seconds() / 3600

                # Ingatkan jika kelas mulai dalam 1 jam ke depan
                if 0 < selisih_jam <= 1:
                    kelas_segera.append(kelas)
                    log.warning(
                        f"🔔 KELAS SEGERA: {kelas['nama']} mulai "
                        f"{jam_mulai_str} ({selisih_jam * 60:.0f} menit lagi)"
                    )
            except ValueError as e:
                log.error(f"Format jam tidak valid untuk '{kelas['nama']}': {e}")
                
        # 2. Cek Tugas Notion
        tugas_segera = []
        if self.notion:
            tugas_notion = self.notion.get_upcoming_tasks()
            hari_ini_str = sekarang.strftime("%Y-%m-%d")
            besok_str = (sekarang + timedelta(days=1)).strftime("%Y-%m-%d")
            
            for t in tugas_notion:
                dl = t.get("deadline", "")
                if dl == hari_ini_str or dl == besok_str:
                    tugas_segera.append(t)
                    log.warning(f"🔔 TUGAS SEGERA: {t['nama']} deadline {dl}")

        return kelas_segera, tugas_segera

    def jalankan_morning_briefing(self, waktu: datetime):
        """
        Alur PAGI (06:00 WIB):
        1. Jadwal kuliah sudah di-fetch dari Edlink saat __init__
        2. Cari referensi DuckDuckGo berdasarkan nama mata kuliah hari ini
        3. Analisis dengan Gemini → kirim Morning Briefing ke Telegram
        """
        log.info("☀️  Memulai alur Morning Briefing...")

        # ── Step 1: Cari referensi untuk kelas-kelas hari ini ─────────────
        # Konversi jadwal Edlink ke format yang dimengerti cari_referensi_topik()
        kelas_hari_ini = [
            {"topik": j["nama"]}  # Gunakan nama matkul sebagai query pencarian
            for j in self.jadwal_kuliah
            if j.get("adalah_hari_ini")
        ]
        referensi = self.explorer.cari_referensi_topik(kelas_hari_ini)

        # ── Step 2: Ambil tugas dari Notion (Deadline Reminder) ──────────
        tugas_notion = self.notion.get_upcoming_tasks() if self.notion else []

        # ── Step 3: Analisis dengan Gemini AI ────────────────────────────
        briefing_konten = self.brain.analyze_and_plan(
            jadwal_kuliah=self.jadwal_kuliah,
            jadwal_org=self.jadwal_org,
            referensi=referensi,
            waktu_sekarang=waktu,
            tugas_notion=tugas_notion
        )

        # ── Step 3: Tambahkan header ke pesan ────────────────────────────
        tanggal_str = waktu.strftime("%A, %d %B %Y")
        header = (
            f"🎓 <b>PAIA Morning Briefing</b>\n"
            f"📅 <b>{tanggal_str}</b>\n"
            f"📡 <i>Sumber jadwal: Sistem Mandiri</i>\n"
            f"{'─' * 30}\n\n"
        )
        pesan_final = header + briefing_konten

        # ── Step 4: Kirim ke Telegram ─────────────────────────────────────
        self.notifier.kirim_morning_briefing(pesan_final)
        log.info("✅ Morning Briefing berhasil dikirim.")

    def jalankan_pengecekan_jam(self):
        """
        Alur JAM LAIN (Hourly):
        - Cek apakah ada kelas darurat (< 1 jam)
        - Cek apakah ada tugas Notion (Deadline hari ini/besok)
        - Jika ya: kirim Reminder
        """
        log.info("🕐 Memulai pengecekan kelas/tugas jam ini...")
        kelas_darurat, tugas_darurat = self._cek_deadline_darurat()

        if kelas_darurat:
            for k in kelas_darurat:
                self.notifier.kirim_panic_reminder(k)
            log.info(f"🔴 {len(kelas_darurat)} Panic Reminder (Kelas) terkirim.")
            
        if tugas_darurat:
            for t in tugas_darurat:
                self.notifier.kirim_task_reminder(t)
            log.info(f"🔴 {len(tugas_darurat)} Task Reminder (Tugas) terkirim.")

        if not kelas_darurat and not tugas_darurat:
            log.info("✅ Tidak ada kelas/tugas darurat. Bot diam (hemat API). ✓")

    def jalankan(self, run_hourly=True):
        """Entry point utama."""
        sekarang = datetime.now(WIB)
        jam_sekarang = sekarang.hour
        
        if run_hourly:
            log.info(f"⏰ Waktu sekarang: {sekarang.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # FITUR 2: Cek pesan masuk Telegram (Alur Manual-ACK)
        updates = self.notifier.get_unread_updates()
        last_successful_update_id = None

        for update in updates:
            try:
                msg = update.get("message", {})
                if str(msg.get("chat", {}).get("id")) != str(self.notifier.chat_id):
                    continue
                
                teks = msg.get("text", "")
                if not teks:
                    continue

                log.info(f"💡 Memproses input manual: {teks}")
                task = self.brain.extract_task_from_text(teks)
                
                # PROTEKSI: Jika ekstraksi gagal, berhenti dan jangan tandai sebagai sukses
                if not task:
                    log.error("❌ Gagal mengekstrak tugas. Menghentikan antrean.")
                    break

                if self.notion:
                    intent = task.get("intent", "create")
                    
                    if intent == "complete":
                        success = self.notion.mark_task_completed(task["task_name"])
                        if success:
                            pesan_balasan = f"🎉 Yeay! Tugas <b>{task['task_name']}</b> sudah saya coret dari Notion.\n\n💡 <i>{task.get('explanation', 'Kerja bagus!')}</i>"
                            self.notifier.kirim_pesan(pesan_balasan, mode="HTML")
                        else:
                            self.notifier.kirim_pesan(f"⚠️ Maaf, saya tidak bisa menemukan tugas bernama <b>{task['task_name']}</b> di Notion Anda.", mode="HTML")
                    else:
                        success = self.notion.create_task_card(
                            task["task_name"], task.get("deadline"), task.get("priority", "Sedang"), 
                            task.get("subtasks", []), "Telegram Input"
                        )
                        if success:
                            penjelasan = task.get('explanation', '')
                            pesan_balasan = f"✅ Siap! Tugas <b>{task['task_name']}</b> sudah saya masukkan ke Notion.\n\n💡 <i>{penjelasan}</i>"
                            self.notifier.kirim_pesan(pesan_balasan, mode="HTML")
                        else:
                            raise Exception("Gagal buat kartu Notion")
                
                # Jika sampai sini tanpa error, tandai sebagai sukses
                last_successful_update_id = update["update_id"]

            except Exception as e:
                log.error(f"⚠️ Berhenti memproses antrean karena error: {e}")
                break # Berhenti agar pesan yang gagal tidak hilang dari antrean

        # Bersihkan antrean hanya jika ada yang sukses
        if last_successful_update_id is not None:
            self.notifier.mark_as_read(last_successful_update_id)

        if run_hourly:
            if jam_sekarang == 6:
                log.info("🌅 Jam 06:00 WIB terdeteksi → Mode Morning Briefing")
                self.jalankan_morning_briefing(sekarang)
            else:
                log.info(f"🕐 Jam {jam_sekarang:02d}:00 WIB → Mode Pengecekan Hourly")
                self.jalankan_pengecekan_jam()


# =============================================================================
#  ENTRY POINT UTAMA
# =============================================================================
def main():
    """Fungsi utama yang dipanggil oleh GitHub Actions atau Terminal Lokal."""
    log.info("=" * 60)
    log.info("  PAIA - Personal Academic Intelligence Agent")
    log.info("  Mahasiswa TRPL - Politeknik Negeri Madiun")
    log.info("=" * 60)

    try:
        agen = PAIAOrchestrator()
        
        # Mode Paksa Kirim Briefing: python main.py --briefing
        if "--briefing" in sys.argv:
            log.info("🚀 Memaksa pengiriman Morning Briefing sekarang juga...")
            agen.jalankan_morning_briefing(datetime.now(WIB))
            
        # Mode Polling (Lokal): python main.py --poll
        elif "--poll" in sys.argv:
            log.info("🔄 Berjalan dalam mode POLLING (Lokal). Tekan Ctrl+C untuk berhenti.")
            last_hour = -1
            while True:
                # Modifikasi agar jalankan() tidak spam Morning Briefing tiap loop
                sekarang = datetime.now(WIB)
                jam_sekarang = sekarang.hour
                
                if jam_sekarang != last_hour:
                    agen.jalankan(run_hourly=True)
                    last_hour = jam_sekarang
                else:
                    agen.jalankan(run_hourly=False)
                
                time.sleep(5)
        else:
            # Mode Cron (GitHub Actions)
            agen.jalankan()
            
    except EnvironmentError as e:
        log.critical(f"❌ Konfigurasi tidak lengkap: {e}")
        raise
    except KeyboardInterrupt:
        log.info("🛑 Bot dihentikan secara manual oleh pengguna.")
    except Exception as e:
        log.error(f"❌ Error tak terduga di main: {e}", exc_info=True)

    log.info("=" * 60)
    log.info("  PAIA selesai dijalankan.")
    log.info("=" * 60)

if __name__ == "__main__":
    main()
