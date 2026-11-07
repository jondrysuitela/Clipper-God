# ClipperGod

Clipper video offline untuk Windows: potong video panjang jadi klip vertikal siap-posting,
dengan caption karaoke bergaya CapCut, face tracking per speaker, dan batas potongan yang
tidak pernah jatuh di tengah kalimat.

**Status:** mesin pemrosesan video, proyek, transkripsi, dan **studio offline**:
antarmuka (`ui/ClipperGod-Prototipe-Interaktif.html`) tersambung ke mesin untuk memilih
video, membuat klip, memutar hasil, mengatur status, dan melihat skor.

Jalankan `python tools/cg.py ui studio` untuk membuka Studio tersambung ke mesin lokal.

---

## Yang sudah jalan

| Modul | Isi | Butuh GPU? |
|---|---|---|
| `core/boundaries.py` | Semantic Boundary Engine: snap potongan ke jeda aman, tolak potong tengah klausa, punchline guard | tidak |
| `core/captions.py` | ASS karaoke per kata + face-aware placement + laporan kepatuhan | tidak |
| `core/scoring.py` | Viral Potential Score 0–100, terurai 6 komponen, hard gate, alasan tekstual | tidak |
| `project/schema.py` | Skema `.cgproj`: media, transkrip, klip, speaker, setelan, versi skema | tidak |
| `project/store.py` | Simpan atomik, autosave hemat disk, pemulihan setelah crash, relink media | tidak |
| `project/history.py` | Undo/redo dengan penggabungan geseran + aksi massal sebagai satu langkah | tidak |
| `pipeline/candidates.py` | Kandidat klip dari kalimat utuh, target durasi reach/watch/story | tidak |
| `pipeline/faces.py` | Deteksi wajah YuNet (232 KB) + pelacak IoU + peta waktu→kotak | tidak |
| `pipeline/reframe.py` | Jalur crop: deadband → EMA → Kalman (dua arah) → clamp → polinomial | tidak |
| `pipeline/render.py` | Render 2 pass FFmpeg: crop dinamis + scale 1080×1920, lalu bakar ASS + loudnorm | tidak |
| `pipeline/asr.py` | Antarmuka transkripsi + backend faster-whisper (dimuat malas) | ya, untuk model besar |

### Alur satu perintah (`python -m clippergod run`)

```powershell
python -m clippergod transcribe video.mp4 --out transkrip.json --model small
python -m clippergod run video.mp4 --transcript transkrip.json --out hasil --target reach --limit 3
python -m clippergod run video.mp4 --transcript transkrip.json --out hasil-horizontal --format landscape
python -m clippergod probe video.mp4
```

Format ekspor yang tersedia: `portrait` (9:16, 1080×1920), `square` (1:1, 1080×1080),
dan `landscape` (16:9, 1920×1080). Studio menyediakan pilihan yang sama saat membuat klip.

Satu putaran menulis artefak tiap tahap, bukan cuma hasil akhir:

```
hasil/
  transcript.json          kata + waktu absolut (sumber kebenaran)
  candidates.json          kandidat + skor + alasan
  run.json                 probe, config, daftar klip, folder basi
  clips/01_judul-klip/
    clip.json              batas + skor, jalur crop (koefisien & ekspresi), laporan caption
    caption.ass
    clip.mp4
```

Sifatnya idempoten: `clip.json` yang sudah ada dilewati (pakai `--force` untuk render ulang),
dan folder klip dari putaran lama dilaporkan di `run.json` → `stale_dirs`, tidak dihapus.

### Speaker timeline (awal F3)

Kalau transkrip punya label `speaker`, klip memakai `pipeline/speakers.py`:

- **binding label → track wajah**, dengan tiga tingkat kepercayaan: `speaker_map` eksplisit
  (dipercaya), satu pembicara–satu wajah (dipercaya), dan jumlah pembicara = jumlah wajah
  (dipetakan kiri-ke-kanan, **selalu** ditandai `review` — tanpa active-speaker detection
  ini tebakan posisi, bukan bukti).
- **warna highlight caption per pembicara** (`\2c`, teks tetap putih).
- **framing memotong** ke pembicara aktif, bukan meluncur 500 px di antara dua wajah.

### Brand kit (`--brand`)

Satu profil berisi gaya caption + logo, dipakai berulang tanpa menyalin setelan ke setiap job:

```json
{
  "name": "Kanal Rio",
  "caption": {"font": "Inter Black", "size": 72, "highlight": "#FF7A45", "position": "top"},
  "logo": {"path": "logo.png", "position": "tr", "width_ratio": 0.16, "margin": 24, "opacity": 0.9}
}
```

```powershell
python tools/cg.py run video.mp4 --transcript t.json --out hasil --brand brand.json
```

Logo ditempel di pass 2 **setelah** caption dibakar, supaya tidak tertimpa subtitle.
`--caption` eksplisit tetap menang atas `caption` di dalam brand.

### Caption yang bisa diatur (`--caption`)

Gaya caption sekarang berasal dari file JSON, bukan hard-code:

```json
{
  "font": "Inter Black", "size": 72, "color": "#FFFFFF", "highlight": "#FF7A45",
  "position": "top", "uppercase": true, "karaoke": false, "box": false,
  "max_words": 3, "max_chars": 24, "max_cps": 18
}
```

```powershell
python tools/cg.py run video.mp4 --transcript t.json --out hasil --caption caption.json
python tools/inspect_caption.py hasil     # ringkasan ASS tanpa membuka gambar
```

Yang divalidasi: `size` di bawah 48 px ditolak kecuali `"allow_small_font": true`;
`max_lines` 1-3, `max_words` 1-8, `max_chars` 12-48, `max_cps` 8-30, safe area harus
muat di kanvas. Kunci asing ditolak supaya typo tidak diam-diam diabaikan.

Catatan jujur: `max_cps` hanya bisa dipenuhi kalau ada jeda untuk memperpanjang cue.
Kata tunggal panjang yang langsung diikuti kata lain dapat tetap di atas cap; kondisi itu
dilaporkan sebagai `over_cap` + `notes`.

### Layout split (dua panel)

Kalau dua pembicara sama-sama layak dilihat, framing tidak perlu memotong — panel
ditumpuk dan caption dapat strip sendiri:

```powershell
python tools/cg.py run video.mp4 --transcript t.json --out hasil --layout split --limit 1
python tools/verify_layout.py hasil
```

Pada mode split, panel di-zoom agar tiap pembicara cukup besar; padding menjaga output
tetap 1080×1920 dan menempatkan caption di strip bawah.

### Batch queue (banyak video)

```powershell
python tools/cg.py batch manifest.json --out antrean --attempts 2
```

```json
{"jobs": [
  {"id": "ep01", "video": "a.mp4", "transcript": "a.json", "target": "reach", "limit": 3},
  {"id": "ep02", "video": "b.mp4", "transcript": "b.json", "layout": "split"}
]}
```

Status tiap job ditulis ke `queue.json` **sebelum** job berikutnya dimulai, jadi proses
mati di tengah antrean tidak menghilangkan pekerjaan yang sudah selesai. Job `failed`
dicoba ulang selama `attempts < --attempts`; `--stop-on-error` menghentikan antrean.

### Transkripsi dan diarisasi

```powershell
python tools/cg.py transcribe video.mp4 --out transkrip.json --model base --language en --diarize
python tools/cg.py run video.mp4 --transcript transkrip.json --out hasil --target reach --limit 1
```

Transkripsi memakai backend faster-whisper yang dimuat saat diperlukan. Opsi
`--diarize` menambahkan label speaker berbasis pitch; hasilnya bergantung pada
karakteristik suara dan perlu ditinjau untuk pembicara dengan pitch serupa.

> Catatan lingkungan: di runtime ini Python dijalankan *isolated* (`-I`), sehingga
> `python -m clippergod` tidak menemukan paket lokal. Pakai `python tools/cg.py ...`;
> di instalasi Python normal, `python -m clippergod ...` bekerja seperti biasa.

## Studio offline

```powershell
python tools/cg.py ui studio
```

Buka URL yang dicetak. UI-nya adalah `ui/ClipperGod-Prototipe-Interaktif.html` — desain yang
sama, tapi datanya nyata: kandidat dari transkrip, video hasil render diputar di panggung,
transkrip menyorot kata sesuai waktu video, panel Skor menampilkan komponen H/R/C/A/L/P
beserta alasannya, dan status klip tersimpan di `studio/project.cgproj`. Gunakan pemilih
proyek di topbar untuk berpindah proyek atau **+ Proyek** untuk membuat proyek baru.
Setiap proyek memiliki folder dan antrean job sendiri; job yang sedang berjalan tetap
memproses proyek asalnya saat Anda berpindah atau membuat proyek lain. Proyek baru disimpan
di `studio/projects/`, sementara proyek `studio` yang sudah ada tetap menjadi proyek awal.
Pilihan font caption diambil dari keluarga font umum yang terpasang di Windows, tanpa
mengunduh atau membundel font. Seret caption pada preview untuk mengatur posisinya
(panah keyboard juga dapat dipakai setelah caption difokuskan); posisi berlaku untuk
render berikutnya dan klip yang sudah dibakar perlu dirender ulang.

Klik **Buat klip**, tempel URL YouTube atau pilih file, lalu tentukan target. Tahap
pertama hanya membaca metadata, mengunduh audio URL saja bila perlu, lalu memakai ASR
`tiny` untuk pemindaian hook awal di seluruh audio. Ollama menilai cuplikan teks kandidat;
workspace hanya menyimpan kata pada rentang kandidat, bukan transkrip seluruh sumber.
Video penuh belum diunduh atau dirender pada tahap ini. Pilih kandidat untuk
**Analisis visual** (unduh video URL hanya pada tahap ini); pemindaian wajah dan ASR
model pilihan dibatasi ke rentang kandidat terpilih. Transkrip akurat disimpan agar
tombol **Render final** tidak mengulang ASR. File lokal memakai preview sumber dengan
caption overlay yang bisa diubah langsung. Setelah render, tombol **Preview sumber**
kembali ke overlay caption yang bisa diedit. Preview sumber bukan simulasi crop/framing;
preview YouTube memakai iframe dan tidak dapat menampilkan framing lokal atau sinkronisasi
caption yang akurat. Render final menggunakan renderer yang sama dengan pipeline.
Gunakan **Batalkan job** pada toolbar atau tombol batal di dialog untuk menghentikan proses.
Job berjalan di worker terpisah agar worker dapat dihentikan paksa tanpa menutup Studio.
Membatalkan job membuang proyek yang sedang diproses beserta data sebelumnya di dalamnya.
Pada proyek default, data default dibersihkan tetapi registry dan proyek lain tetap aman;
proyek terpisah dihapus dari daftar proyek.

Pemindaian hook awal Studio memakai faster-whisper `tiny`; model yang dipilih di dialog
dipakai untuk transkripsi akurat klip. Pilih `small` untuk model lebih ringan, `medium`
atau `large-v3-turbo` untuk model lebih teliti (model besar mungkin perlu diunduh saat
pertama dipakai). Untuk file lokal, tombol **Pilih…** membuka pemilih file browser lalu
menyalin video ke `studio/source/`. Pemrosesan media dan transkripsi lokal; URL YouTube
diakses untuk metadata/audio, sementara video penuh baru diunduh setelah kandidat dipilih.
Progress menunjukkan pemindaian awal atau ASR klip terpilih, cakupan audio, perangkat,
compute type, dan perkiraan waktu tersisa. Worker terisolasi dapat memuat ulang model untuk
job berikutnya.

### Skor hook Ollama lokal (opsional)

Pasang Ollama secara terpisah, jalankan, lalu pasang model yang ingin dipakai. Contoh:

```powershell
ollama pull llama3.2
```

Di dialog **Buat klip**, aktifkan penilaian Ollama dan isi nama model. Saat analisis,
aplikasi mengirim transkrip kandidat yang batas waktunya sudah dibuat dari kalimat utuh
ke server Ollama loopback lokal (`127.0.0.1:11434`). Ollama merangking kandidat dan
menandai pilihan teratas sesuai jumlah klip; pilihan itu tetap dapat ditinjau sebelum
analisis visual atau render. Skor AI disimpan terpisah dari skor heuristik. AI memilih
di antara rentang kandidat yang valid—tidak mengarang timestamp. Jika Ollama/model tidak
tersedia, analisis tetap lanjut dengan ranking heuristik dan peringatan yang jelas.
Model Ollama tidak dibundel bersama EXE; penilaian hook sepenuhnya lokal.

Pada panel **Skor → Pemeriksa transkrip**, pilih **Periksa ulang** untuk menjalankan
ASR kedua pada audio sumber lalu meminta Ollama menandai jendela waktu yang berbeda.
Model ASR pemeriksa default `large-v3-turbo` dapat diunduh (sekitar 1,6 GB) saat pertama
kali dipakai; pilih `small` atau `medium` jika ingin model lebih ringan. Untuk URL,
audio dapat diunduh ulang saat pemeriksaan diminta. Hasil hanya berupa perbandingan dan
catatan Ollama; transkrip proyek serta timestamp tidak pernah ditimpa otomatis.
Ollama tidak mendengar audio dan tidak dapat memastikan versi mana yang benar, jadi
dengarkan bagian yang ditandai sebelum mengubah caption. Jika kedua ASR melewatkan kata
yang sama, pemeriksaan ini juga tidak dapat menemukannya.

### Build Windows EXE

Build satu-folder membutuhkan Python 3.11+ dan dependensi pada `requirements-build.txt`:

```powershell
python -m pip install -r requirements-build.txt
.\build-windows.ps1
```

Hasilnya `dist/ClipperGod/ClipperGod.exe`; jalankan EXE tanpa argumen untuk membuka
Studio, atau berikan subcommand CLI seperti biasa. Ini distribusi aplikasi, bukan satu file
mandiri: folder hasil build harus ikut disalin. Ollama/model AI, bobot faster-whisper,
dan koneksi untuk unduh audio/video URL tetap disediakan atau diunduh terpisah pada
komputer pengguna.

## Jalankan

```powershell
python tools/fetch_face_model.py                # sekali: unduh model YuNet + verifikasi SHA-256
python -m unittest discover -s tests -t . -v
```

## Struktur

```
clippergod/core/   mesin inti (murni Python, tanpa dependensi)
clippergod/project/ skema proyek, penyimpanan, undo/redo
clippergod/pipeline/ transkrip, kandidat, wajah, reframe, speaker, diarisasi, caption, brand, layout, batch, render, orkestrator
clippergod/cli.py  antarmuka `python -m clippergod` / `python tools/cg.py`
ui/                prototipe UI interaktif (HTML mandiri) + aset
docs/              SPEC-CLIPPERGOD.md — spec produk & teknis
research/          bukti riset (teardown 11 tool, stack offline, sains hook)
tests/             unit test (175)
tools/             CLI, utilitas model, dan alat inspeksi/evaluasi
models/            model YuNet — tidak ikut repo, diunduh lewat tools/fetch_face_model.py
```

## Catatan lingkungan

Dua API yang dihapus di versi baru dan sudah ditangani kode:

- **OpenCV 5** menghapus `cv2.CascadeClassifier`. `faces.py` memakai YuNet
  (`cv2.FaceDetectorYN`) dan masih menyediakan jalur Haar untuk OpenCV 4.x.
- **FFmpeg 8+** menghapus opsi `crop.eval` (posisi selalu dievaluasi per frame),
  sedangkan FFmpeg ≤7 butuh `eval=frame` atau crop membeku di frame pertama.
  `render.py` memprobe kemampuan build-nya sekali, lalu memilih bentuk filter yang benar.

## Prinsip yang tidak boleh dilanggar

1. Batas potongan lebih penting daripada skor.
2. Caption = transkrip = timeline: satu struktur data.
3. Setiap tahap menghasilkan artefak JSON di disk.
4. Skor adalah potensi, bukan probabilitas — selalu sertakan alasan.
5. Caption preview dan export memakai transkrip/timeline yang sama; hasil render final
   adalah acuan untuk framing dan tampilan libass.

Lihat `docs/SPEC-CLIPPERGOD.md` untuk peta fitur, arsitektur, parameter, dan roadmap.
