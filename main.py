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
#  DATA JADWAL STATIS (Dummy - sesuaikan dengan jadwal asli kamu)
#  Format: dict berisi list tugas dengan deadline dan prioritas
# ─────────────────────────────────────────────────────────────────────────
JADWAL_STATIS = {
    "mata_kuliah": [
        {
            "nama": "Mobile Programming",
            "topik": "Jetpack Compose - State & ViewModel",
            "deadline": "2026-04-28 23:59",
            "tipe": "Tugas Coding",
            "prioritas": "TINGGI",
        },
        {
            "nama": "Web Framework (Laravel)",
            "topik": "Implementasi MVC Pattern + Eloquent ORM",
            "deadline": "2026-04-27 08:00",
            "tipe": "Tugas Coding",
            "prioritas": "KRITIS",
        },
        {
            "nama": "Data Engineering",
            "topik": "BigQuery - Loading & Querying Dataset",
            "deadline": "2026-04-30 23:59",
            "tipe": "Praktikum",
            "prioritas": "SEDANG",
        },
        {
            "nama": "Basis Data Lanjut",
            "topik": "Stored Procedure & Trigger",
            "deadline": "2026-05-02 23:59",
            "tipe": "Tugas",
            "prioritas": "SEDANG",
        },
    ],
    "organisasi_hima": [
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
    ],
}

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

    def scrape_sevima_edlink(self, base_url: str = "https://edlink.id") -> list[dict]:
        """
        [PLACEHOLDER] Scraping pengumuman & tugas baru dari Sevima Edlink.
        
        TODO: Isi bagian ini dengan logika login dan parsing HTML yang sebenarnya.
        Langkah yang perlu diimplementasikan:
          1. Buat session requests
          2. POST ke endpoint login dengan credentials
          3. Ambil token/cookie dari response
          4. GET halaman dashboard/tugas
          5. Parse HTML dengan BeautifulSoup
          6. Ekstrak data tugas/pengumuman dan kembalikan sebagai list dict

        :param base_url: URL dasar portal Sevima Edlink
        :return: List dict berisi pengumuman/tugas baru
        """
        log.info("🌐 [Placeholder] Mencoba akses Sevima Edlink...")
        pengumuman = []
        try:
            # ── Contoh struktur request dasar (belum login) ──────────────
            sesi = requests.Session()
            sesi.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                )
            })

            # TODO: Ganti dengan endpoint login yang benar
            # payload_login = {"username": os.getenv("SEVIMA_USER"), "password": os.getenv("SEVIMA_PASS")}
            # resp_login = sesi.post(f"{base_url}/login", data=payload_login, timeout=20)

            # TODO: Setelah login, akses halaman tugas
            # resp_tugas = sesi.get(f"{base_url}/student/tasks", timeout=20)
            # soup = BeautifulSoup(resp_tugas.text, "html.parser")

            # TODO: Parse elemen HTML yang berisi info tugas
            # Contoh: cards = soup.select(".task-card")
            # for card in cards:
            #     pengumuman.append({
            #         "judul": card.select_one(".task-title").text.strip(),
            #         "deadline": card.select_one(".task-due").text.strip(),
            #     })

            log.info("ℹ️  Sevima scraper masih placeholder. Implementasi login diperlukan.")
        except requests.exceptions.ConnectionError:
            log.warning("⚠️ Tidak dapat terhubung ke Sevima Edlink. Lewati.")
        except Exception as e:
            log.error(f"❌ Error saat scraping Sevima: {e}")
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
        jadwal: dict,
        referensi: dict,
        waktu_sekarang: datetime,
    ) -> str:
        """
        Analisis jadwal lengkap dan buat rencana harian dengan Gemini AI.
        :param jadwal: Dict berisi semua tugas kuliah & organisasi
        :param referensi: Dict {topik: [list link]} hasil pencarian DuckDuckGo
        :param waktu_sekarang: Objek datetime dengan timezone WIB
        :return: String teks analisis dari Gemini (format HTML)
        """
        if not self.model:
            return "<b>❌ Gemini tidak tersedia. Periksa API key.</b>"

        # ── Susun konteks jadwal menjadi string yang bisa dipahami AI ────
        tanggal_str = waktu_sekarang.strftime("%A, %d %B %Y pukul %H:%M WIB")

        tugas_kuliah_str = "\n".join([
            f"  - [{t['prioritas']}] {t['nama']}: {t['topik']} | Deadline: {t['deadline']}"
            for t in jadwal.get("mata_kuliah", [])
        ])

        kegiatan_org_str = "\n".join([
            f"  - [{t['prioritas']}] {t['nama']}: {t['topik']} | Waktu: {t['waktu']}"
            for t in jadwal.get("organisasi_hima", [])
        ])

        referensi_str = ""
        if referensi:
            for topik, links in referensi.items():
                referensi_str += f"\n  Referensi untuk '{topik}':\n"
                for link in links:
                    referensi_str += f"    * {link['judul']}: {link['url']}\n"

        prompt = f"""
Sekarang adalah {tanggal_str}.

Ini adalah jadwal lengkap saya hari ini dan beberapa hari ke depan:

TUGAS KULIAH:
{tugas_kuliah_str}

KEGIATAN ORGANISASI HIMA:
{kegiatan_org_str}

REFERENSI YANG SUDAH DIKUMPULKAN HARI INI:
{referensi_str if referensi_str else "  (Tidak ada referensi yang dikumpulkan otomatis hari ini)"}

Tolong buat Morning Briefing yang komprehensif untuk saya dalam format HTML Telegram. 
Sertakan:
1. Sapaan pagi yang menyemangati
2. Ringkasan situasi hari ini (mana yang paling mendesak)
3. Rencana kerja bertahap untuk tugas KRITIS/TINGGI (pecah jadi langkah kecil yang actionable)
4. Strategi menyeimbangkan kuliah dan organisasi hari ini
5. Tips teknis singkat (💡) untuk topik yang paling sulit
6. Jika ada referensi, cantumkan sebagai link HTML <a href="url">judul</a>
7. Penutup yang memotivasi

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
        self.jadwal = JADWAL_STATIS

        log.info("🚀 PAIAOrchestrator berhasil diinisialisasi.")

    def _cek_deadline_darurat(self) -> list[dict]:
        """
        Cek apakah ada tugas dengan deadline kurang dari 6 jam dari sekarang.
        :return: List tugas yang deadline-nya darurat
        """
        sekarang = datetime.now(WIB)
        darurat = []
        for tugas in self.jadwal.get("mata_kuliah", []):
            try:
                # Parse string deadline menjadi datetime object ber-timezone
                dl = datetime.strptime(tugas["deadline"], "%Y-%m-%d %H:%M")
                dl_wib = WIB.localize(dl)
                selisih_jam = (dl_wib - sekarang).total_seconds() / 3600
                if 0 < selisih_jam <= 6:
                    darurat.append(tugas)
                    log.warning(
                        f"🔴 DEADLINE DARURAT: {tugas['nama']} "
                        f"({selisih_jam:.1f} jam lagi)"
                    )
            except ValueError as e:
                log.error(f"Format deadline tidak valid untuk '{tugas['nama']}': {e}")
        return darurat

    def jalankan_morning_briefing(self, waktu: datetime):
        """
        Alur PAGI (06:00 WIB):
        1. Cari referensi dari web untuk topik-topik trigger
        2. Analisis jadwal dengan Gemini
        3. Kirim Morning Briefing ke Telegram
        """
        log.info("☀️  Memulai alur Morning Briefing...")

        # ── Step 1: Kumpulkan referensi dari DuckDuckGo ───────────────────
        semua_tugas = self.jadwal.get("mata_kuliah", [])
        referensi = self.explorer.cari_referensi_topik(semua_tugas)

        # ── Step 2 (Opsional): Coba scrape Sevima ────────────────────────
        # pengumuman_sevima = self.explorer.scrape_sevima_edlink()

        # ── Step 3: Analisis dengan Gemini AI ────────────────────────────
        briefing_konten = self.brain.analyze_and_plan(
            jadwal=self.jadwal,
            referensi=referensi,
            waktu_sekarang=waktu,
        )

        # ── Step 4: Tambahkan header ke pesan ────────────────────────────
        tanggal_str = waktu.strftime("%d %B %Y")
        header = (
            f"🎓 <b>PAIA Morning Briefing</b>\n"
            f"📅 <b>{tanggal_str}</b>\n"
            f"{'─' * 30}\n\n"
        )
        pesan_final = header + briefing_konten

        # ── Step 5: Kirim ke Telegram ─────────────────────────────────────
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
