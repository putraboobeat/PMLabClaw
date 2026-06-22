# ⚡ PmlabClaw

> **Personal AI Task Runner & Autonomous VPS Agent**  
> Zero-dependency · Token-efficient · Modular · Extensible

PmlabClaw adalah framework AI agent pribadi yang berjalan di VPS Anda dan dapat dikendalikan sepenuhnya melalui Telegram. Didesain dari awal agar **super ringan** (hanya 10.9MB RAM), **hemat token**, dan memiliki **arsitektur plugin-based** yang siap untuk dikembangkan tanpa batas.

---

## 🚀 Fitur Utama

- **Zero External Dependencies** — Hanya menggunakan Python standard library (urllib, subprocess, json, dll). Tidak ada `pip install`.
- **Plugin Architecture** — Tambahkan kemampuan baru (tools/skills) hanya dengan membuat 1 file Python di folder `plugins/`. Tidak perlu menyentuh core engine.
- **Token Optimizer** — System prompt dipadatkan, riwayat chat secara otomatis dipangkas agar konsumsi token di API selalu minimal.
- **Long-Polling Efficient** — Menggunakan Telegram long-polling 50 detik untuk menghemat CPU & bandwidth secara drastis.
- **Multi-Tool Calling** — Model AI dapat memanggil beberapa tool sekaligus dalam satu respons.
- **Secure by Default** — Hanya menerima perintah dari `ALLOWED_CHAT_ID` yang terdaftar.
- **Systemd-Ready** — Berjalan sebagai layanan OS yang otomatis restart jika crash.
- **Contextual Memory** — Mempertahankan konteks obrolan dengan window yang dioptimalkan.

---

## 📂 Struktur Proyek

```
pmlabclaw/
├── main.py                  # Entry point utama
├── pmlabclaw.service        # Systemd service definition
├── .env.example             # Template konfigurasi
├── .gitignore
├── README.md
│
├── core/                    # Engine inti (tidak perlu diubah untuk tambah fitur)
│   ├── __init__.py
│   ├── config.py            # Loader konfigurasi dari .env
│   ├── telegram.py          # Telegram Bot API client
│   ├── llm.py               # AgentRouter/OpenAI-compatible LLM client
│   ├── dispatcher.py        # Tool registry & executor dispatcher
│   └── agent.py             # Loop agent: polling → LLM → tool → reply
│
├── plugins/                 # Tambahkan fitur baru di sini
│   ├── __init__.py
│   ├── base.py              # Abstract base class untuk semua plugin
│   ├── shell.py             # [BUILT-IN] Eksekusi perintah shell
│   ├── system.py            # [BUILT-IN] Monitor CPU, RAM, disk
│   ├── scheduler.py         # [BUILT-IN] Jadwalkan task berulang
│   └── web.py               # [BUILT-IN] HTTP request ke URL eksternal
│
├── tasks/                   # Tempat menyimpan task terjadwal (cron-like)
│   ├── __init__.py
│   └── example_task.py      # Contoh task terjadwal
│
├── data/                    # Penyimpanan data persisten (db sederhana)
│   └── .gitkeep
│
└── logs/                    # Log output (tidak di-commit ke git)
    └── .gitkeep
```

---

## ⚙️ Cara Deploy

### 1. Konfigurasi
```bash
cp .env.example .env
nano .env  # isi dengan credential Anda
```

### 2. Deploy ke Server
```bash
# Salin ke server
scp -r . root@your-server:/usr/local/lib/pmlabclaw/

# Atau gunakan git
ssh root@your-server
git clone https://github.com/username/pmlabclaw.git /usr/local/lib/pmlabclaw
```

### 3. Aktifkan Systemd Service
```bash
cp pmlabclaw.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pmlabclaw.service
```

### 4. Cek Status
```bash
systemctl status pmlabclaw.service
journalctl -u pmlabclaw.service -f
```

---

## 🔌 Membuat Plugin Baru

Setiap plugin adalah sebuah class Python yang mewarisi `PluginBase`. Tidak ada boilerplate rumit.

```python
# plugins/my_feature.py
from plugins.base import PluginBase

class MyFeaturePlugin(PluginBase):
    
    @property
    def tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "my_tool",
                    "description": "Penjelasan singkat apa yang dilakukan tool ini.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "param1": {"type": "string", "description": "..."}
                        },
                        "required": ["param1"]
                    }
                }
            }
        ]
    
    def execute(self, tool_name, args):
        if tool_name == "my_tool":
            return f"Hasil: {args.get('param1')}"
        return None
```

Setelah file dibuat, daftarkan di `main.py` — selesai. Plugin Anda langsung aktif.

---

## 🛡️ Keamanan

- `.env` sudah masuk ke `.gitignore` — credential tidak pernah ter-commit ke git.
- Semua perintah dieksekusi sebagai `root` — pastikan `ALLOWED_CHAT_ID` dikonfigurasi benar.
- Timeout 30 detik untuk setiap eksekusi perintah shell — mencegah proses zombie.

---

## 📡 Perintah Telegram

| Perintah | Fungsi |
|---|---|
| `/start` | Sapa bot, lihat status aktif |
| `/clear` | Hapus riwayat percakapan (reset konteks) |
| `/status` | Lihat ringkasan resource server (CPU, RAM, Disk) |
| `/help` | Tampilkan daftar plugin yang aktif |
| Pesan biasa | Chat bebas, AI akan memutuskan tool mana yang dipakai |

---

## 🗺️ Roadmap Pengembangan

- [ ] Plugin: Database (SQLite) — simpan & query data sederhana via chat
- [ ] Plugin: Notifikasi Terjadwal — kirim alert CPU/RAM jika melampaui threshold
- [ ] Plugin: Deploy Manager — pull git repo & restart service via perintah chat
- [ ] Plugin: File Manager — baca, tulis, cari file di server via chat
- [ ] Multi-user Support — izinkan beberapa Chat ID dengan level akses berbeda
- [ ] Plugin: Webhook Receiver — terima notifikasi dari GitHub, Grafana, dll

---

## 📄 Lisensi

Private Project — PutraVPS Personal Use Only.
