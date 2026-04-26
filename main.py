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
import logging
from datetime import datetime

import pytz
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
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
    {
        "nama": "Mobile Programming",
        "dosen": "-",
        "ruangan": "-",
        "hari": "Senin",
        "jam_mulai": "08:00",
        "jam_selesai": "09:40",
        "adalah_hari_ini": False,
    },
    {
        "nama": "Web Framework (Laravel)",
        "dosen": "-",
        "ruangan": "-",
        "hari": "Selasa",
        "jam_mulai": "10:00",
        "jam_selesai": "11:40",
        "adalah_hari_ini": False,
    },
    {
        "nama": "Data Engineering",
        "dosen": "-",
        "ruangan": "-",
        "hari": "Rabu",
        "jam_mulai": "13:00",
        "jam_selesai": "14:40",
        "adalah_hari_ini": False,
    },
]

# Kata kunci topik yang akan dipicu pencarian otomatis referensi
TOPIK_TRIGGER_SEARCH = [
    "Jetpack Compose", "BigQuery", "Eloquent ORM",
    "Kotlin Coroutines", "Laravel Livewire", "Apache Kafka",
    "Stored Procedure", "ViewModel", "Data Pipeline",
]


# =============================================================================
#  KELAS 1: TelegramNotifier
#  Bertanggung jawab mengirim semua notifikasi ke Telegram
# =============================================================================
class TelegramNotifier:
    """Mengirim pesan ke Telegram menggunakan Bot API."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        log.info("TelegramNotifier siap.")

    def kirim_pesan(self, teks: str, mode: str = "HTML") -> bool:
        """
        Kirim pesan ke Telegram.
        :param teks: Isi pesan (mendukung HTML atau MarkdownV2)
        :param mode: 'HTML' atau 'MarkdownV2'
        :return: True jika berhasil, False jika gagal
        """
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
        except requests.exceptions.Timeout:
            log.error("❌ Timeout saat mengirim ke Telegram.")
        except requests.exceptions.HTTPError as e:
            log.error(f"❌ HTTP Error Telegram: {e} | Response: {resp.text}")
        except Exception as e:
            log.error(f"❌ Error tak terduga saat kirim Telegram: {e}")
        return False

    def kirim_morning_briefing(self, konten: str):
        """Kirim pesan Morning Briefing yang panjang dan terformat."""
        self.kirim_pesan(konten, mode="HTML")

    def kirim_panic_reminder(self, tugas: dict):
        """Kirim pesan singkat Panic Reminder untuk deadline darurat."""
        pesan = (
            f"🔴 <b>PANIC REMINDER!</b>\n\n"
            f"⚠️ Deadline kurang dari 6 jam!\n\n"
            f"📌 <b>Mata Kuliah:</b> {tugas['nama']}\n"
            f"📝 <b>Topik:</b> {tugas['topik']}\n"
            f"⏰ <b>Deadline:</b> {tugas['deadline']}\n"
            f"🔥 <b>Prioritas:</b> {tugas['prioritas']}\n\n"
            f"💪 <i>Segera kerjakan! Jangan sampai terlambat!</i>"
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

    def scrape_sevima_edlink(self) -> list[dict]:
        """
        Login ke Sevima Edlink via SSO dan ambil pengumuman/tugas baru.

        Token Edlink (EDLINK_TOKEN) bersifat ganda:
          - Dipakai sebagai parameter ?token=... di URL SSO login
          - Dipakai sebagai Bearer token untuk hit endpoint API
        Keduanya menggunakan token yang SAMA dari Local Storage browser.

        Credentials yang dibutuhkan di GitHub Secrets:
          - EDLINK_TOKEN   : token dari Local Storage browser (key: 'token')
          - EDLINK_EMAIL   : email akun Edlink
          - EDLINK_PASSWORD: password akun Edlink

        :return: List dict berisi pengumuman/tugas baru, atau [] jika gagal
        """
        # ── Ambil credentials dari environment variables (GitHub Secrets) ─
        token = os.getenv("EDLINK_TOKEN", "")   # token yang sama untuk SSO & Bearer
        email = os.getenv("EDLINK_EMAIL", "")
        password = os.getenv("EDLINK_PASSWORD", "")

        if not all([token, email, password]):
            missing = [k for k, v in {
                "EDLINK_TOKEN": token,
                "EDLINK_EMAIL": email,
                "EDLINK_PASSWORD": password,
            }.items() if not v]
            log.warning(f"⚠️  Scraper Edlink dilewati. Secrets belum diset: {missing}")
            return []

        log.info("🌐 Mencoba login ke Sevima Edlink via SSO...")
        pengumuman = []
        try:
            sesi = requests.Session()
            sesi.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                ),
                "Accept": "application/json, text/html",
            })

            # ── Step 1: POST login ke SSO Edlink ──────────────────────────
            # EDLINK_TOKEN dipakai sebagai ?token= di URL SSO (token sama!)
            sso_url = (
                f"https://api.edlink.id/sso/auth"
                f"?token={token}"
                f"&redirect=https%3A%2F%2Fedlink.id%2Fpanel"
            )
            payload_login = {
                "email": email,       # string key — bukan variable!
                "password": password,
            }
            resp_login = sesi.post(sso_url, data=payload_login, timeout=20)
            resp_login.raise_for_status()
            log.info(f"✅ Login Edlink: status {resp_login.status_code}")

            # ── Step 2: Fetch jadwal/tugas via API yang sudah punya token ─
            # Setelah login berhasil, sesi sudah menyimpan cookie otomatis.
            # Gunakan endpoint weekly-schedules yang sudah kita ketahui:
            resp_tugas = sesi.get(
                "https://api.edlink.id/api/v1.4/account/weekly-schedules",
                timeout=20,
            )
            resp_tugas.raise_for_status()

            # ── Step 3: Parse response ────────────────────────────────────
            try:
                data = resp_tugas.json()
                # Jika response adalah JSON langsung
                items = data if isinstance(data, list) else data.get("data", [])
                for item in items:
                    pengumuman.append({
                        "judul": item.get("course_name") or item.get("name", "-"),
                        "hari": item.get("day", "-"),
                        "jam": f"{item.get('start_time','-')}-{item.get('end_time','-')}",
                    })
                log.info(f"✅ Berhasil ambil {len(pengumuman)} data dari Edlink.")
            except ValueError:
                # Jika response HTML, gunakan BeautifulSoup
                log.info("📄 Response bukan JSON, mencoba parse HTML...")
                soup = BeautifulSoup(resp_tugas.text, "html.parser")
                # TODO: sesuaikan selector dengan struktur HTML Edlink
                cards = soup.select(".task-card, .schedule-item")
                for card in cards:
                    judul_el = card.select_one(".task-title, .course-name")
                    pengumuman.append({
                        "judul": judul_el.text.strip() if judul_el else "?",
                    })

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            if status == 401:
                log.error("❌ Login Edlink gagal: credentials salah atau token expired (401).")
            else:
                log.error(f"❌ HTTP Error Edlink SSO: {status}")
        except requests.exceptions.ConnectionError:
            log.error("❌ Tidak dapat terhubung ke Edlink. Cek koneksi.")
        except requests.exceptions.Timeout:
            log.error("❌ Timeout saat request ke Edlink.")
        except Exception as e:
            log.error(f"❌ Error tak terduga scraper Edlink: {e}", exc_info=True)

        return pengumuman


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
            self.model = genai.GenerativeModel(
                model_name="gemini-1.5-pro",
                system_instruction=self.SYSTEM_PROMPT,
            )
            log.info("GeminiBrain siap dengan model gemini-1.5-pro.")
        except Exception as e:
            log.error(f"❌ Gagal inisialisasi Gemini: {e}")
            self.model = None

    def analyze_and_plan(
        self,
        jadwal_kuliah: list,
        jadwal_org: list,
        referensi: dict,
        waktu_sekarang: datetime,
    ) -> str:
        """
        Analisis jadwal harian dan buat rencana kerja dengan Gemini AI.

        :param jadwal_kuliah: List dict jadwal kuliah dari Edlink API (sudah dinormalisasi)
        :param jadwal_org: List dict kegiatan organisasi HIMA (statis)
        :param referensi: Dict {topik: [list link]} hasil pencarian DuckDuckGo
        :param waktu_sekarang: Objek datetime dengan timezone WIB
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
            return (
                f"  • {j['nama']} | {j['hari']} {j['jam_mulai']}-{j['jam_selesai']} "
                f"| Ruang: {j['ruangan']} | Dosen: {j['dosen']}"
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

        prompt = f"""
Sekarang adalah {tanggal_str}.

JADWAL KULIAH HARI INI ({hari_ini_str}) — Data dari Edlink:
{kuliah_hari_ini_str}

JADWAL KULIAH SISA MINGGU INI — Data dari Edlink:
{kuliah_minggu_str}

KEGIATAN ORGANISASI HIMA:
{kegiatan_org_str}

REFERENSI YANG SUDAH DIKUMPULKAN HARI INI:
{referensi_str if referensi_str else "  (Tidak ada referensi yang dikumpulkan otomatis hari ini)"}

Tolong buat Morning Briefing yang komprehensif untuk saya dalam format HTML Telegram.
Sertakan:
1. Sapaan pagi yang menyemangati (sebutkan hari dan tanggal)
2. Ringkasan kelas yang harus dihadiri hari ini beserta ruangannya
3. Tips persiapan untuk setiap mata kuliah hari ini (materi apa yang perlu dibaca)
4. Strategi menyeimbangkan kelas + kegiatan organisasi hari ini
5. Preview jadwal besok agar bisa persiapan dari sekarang
6. Tips teknis singkat (💡) untuk mata kuliah yang topiknya paling kompleks
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


# =============================================================================
#  KELAS 4: PAIAOrchestrator
#  Koordinator utama - mengatur alur logika pagi vs jam lain
# =============================================================================
class PAIAOrchestrator:
    """Orkestrator PAIA - mengkoordinasikan semua komponen sesuai jadwal."""

    def __init__(self):
        # Ambil semua credentials dari environment variables
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        tg_token = os.getenv("TELEGRAM_TOKEN", "")
        tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        # Validasi credentials wajib ada
        if not all([gemini_key, tg_token, tg_chat_id]):
            missing = [
                k for k, v in {
                    "GEMINI_API_KEY": gemini_key,
                    "TELEGRAM_TOKEN": tg_token,
                    "TELEGRAM_CHAT_ID": tg_chat_id,
                }.items() if not v
            ]
            log.critical(f"❌ Env vars wajib tidak ditemukan: {missing}")
            raise EnvironmentError(f"Missing required env vars: {missing}")

        # Inisialisasi semua komponen
        self.notifier = TelegramNotifier(tg_token, tg_chat_id)
        self.explorer = ExplorerAgent()
        self.brain = GeminiBrain(gemini_key)

        # ── Ambil jadwal kuliah dari Edlink API ───────────────────────────
        # Jika EDLINK_TOKEN ada → fetch dari API (data real)
        # Jika tidak ada / gagal → pakai JADWAL_KULIAH_FALLBACK (data statis)
        log.info("📅 Mengambil jadwal kuliah dari Edlink...")
        jadwal_dari_edlink = self.explorer.fetch_edlink_jadwal()

        if jadwal_dari_edlink:
            self.jadwal_kuliah = jadwal_dari_edlink
            log.info(f"✅ Jadwal kuliah dari Edlink: {len(jadwal_dari_edlink)} entri.")
        else:
            self.jadwal_kuliah = JADWAL_KULIAH_FALLBACK
            log.warning("⚠️  Menggunakan JADWAL_KULIAH_FALLBACK (Edlink tidak tersedia).")

        # Jadwal organisasi selalu statis (tidak ada di Edlink)
        self.jadwal_org = JADWAL_ORGANISASI_HIMA

        log.info("🚀 PAIAOrchestrator berhasil diinisialisasi.")

    def _cek_deadline_darurat(self) -> list[dict]:
        """
        Cek apakah ada kelas yang dimulai dalam 6 jam ke depan hari ini.
        Edlink hanya memberi jadwal (jam mulai), bukan deadline tugas.
        Untuk deadline tugas, integrasikan endpoint Edlink assignments terpisah.
        :return: List jadwal kelas yang akan segera dimulai
        """
        sekarang = datetime.now(WIB)
        akan_segera = []
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
                    akan_segera.append(kelas)
                    log.warning(
                        f"🔔 KELAS SEGERA: {kelas['nama']} mulai "
                        f"{jam_mulai_str} ({selisih_jam * 60:.0f} menit lagi)"
                    )
            except ValueError as e:
                log.error(f"Format jam tidak valid untuk '{kelas['nama']}': {e}")
        return akan_segera

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

        # ── Step 2: Analisis dengan Gemini AI ────────────────────────────
        briefing_konten = self.brain.analyze_and_plan(
            jadwal_kuliah=self.jadwal_kuliah,
            jadwal_org=self.jadwal_org,
            referensi=referensi,
            waktu_sekarang=waktu,
        )

        # ── Step 3: Tambahkan header ke pesan ────────────────────────────
        tanggal_str = waktu.strftime("%A, %d %B %Y")
        sumber = "Edlink API" if len(self.jadwal_kuliah) != len(JADWAL_KULIAH_FALLBACK) else "Fallback"
        header = (
            f"🎓 <b>PAIA Morning Briefing</b>\n"
            f"📅 <b>{tanggal_str}</b>\n"
            f"📡 <i>Sumber jadwal: {sumber}</i>\n"
            f"{'─' * 30}\n\n"
        )
        pesan_final = header + briefing_konten

        # ── Step 4: Kirim ke Telegram ─────────────────────────────────────
        self.notifier.kirim_morning_briefing(pesan_final)
        log.info("✅ Morning Briefing berhasil dikirim.")

    def jalankan_pengecekan_jam(self):
        """
        Alur JAM LAIN (Hourly):
        - Cek apakah ada deadline darurat (< 6 jam)
        - Jika ya: kirim Panic Reminder
        - Jika tidak: diam (hemat API quota)
        """
        log.info("🕐 Memulai pengecekan deadline jam ini...")
        tugas_darurat = self._cek_deadline_darurat()

        if tugas_darurat:
            for tugas in tugas_darurat:
                self.notifier.kirim_panic_reminder(tugas)
            log.info(f"🔴 {len(tugas_darurat)} Panic Reminder terkirim.")
        else:
            log.info("✅ Tidak ada deadline darurat. Bot diam (hemat API). ✓")

    def jalankan(self):
        """
        Entry point utama - menentukan alur berdasarkan jam saat ini (WIB).
        """
        sekarang = datetime.now(WIB)
        jam_sekarang = sekarang.hour
        log.info(f"⏰ Waktu sekarang: {sekarang.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if jam_sekarang == 6:
            # ── Mode Pagi: Morning Briefing lengkap ───────────────────────
            log.info("🌅 Jam 06:00 WIB terdeteksi → Mode Morning Briefing")
            self.jalankan_morning_briefing(sekarang)
        else:
            # ── Mode Jam Lain: Pengecekan deadline darurat saja ───────────
            log.info(f"🕐 Jam {jam_sekarang:02d}:00 WIB → Mode Pengecekan Hourly")
            self.jalankan_pengecekan_jam()


# =============================================================================
#  ENTRY POINT UTAMA
# =============================================================================
def main():
    """Fungsi utama yang dipanggil oleh GitHub Actions."""
    log.info("=" * 60)
    log.info("  PAIA - Personal Academic Intelligence Agent")
    log.info("  Mahasiswa TRPL - Politeknik Negeri Madiun")
    log.info("=" * 60)

    try:
        agen = PAIAOrchestrator()
        agen.jalankan()
    except EnvironmentError as e:
        # Error konfigurasi - workflow harus gagal agar terdeteksi
        log.critical(f"❌ Konfigurasi tidak lengkap: {e}")
        raise
    except Exception as e:
        # Error tak terduga - log tapi jangan crash workflow sepenuhnya
        log.error(f"❌ Error tak terduga di main: {e}", exc_info=True)

    log.info("=" * 60)
    log.info("  PAIA selesai dijalankan.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
