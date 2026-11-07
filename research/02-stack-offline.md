# ClipperGod — Riset Stack Teknis Offline (Windows, GPU Konsumer 8–12 GB)

**Status:** riset tahap 1 — fact-finding, bukan keputusan final
**Tanggal akses sumber:** 6 November 2026
**Ruang lingkup:** aplikasi desktop Windows, 100% offline (tanpa cloud), GPU NVIDIA 8–12 GB VRAM, wajib ada fallback CPU
**Di luar ruang lingkup:** desain UI/UX, model bisnis, distribusi/updater, lisensi Qt/Electron

---

## 1. Ringkasan eksekutif

Semua kebutuhan inti bisa dipenuhi 100% offline dengan komponen berlisensi permissive (MIT/BSD/Apache/ISC/Unlicense). Tidak ada satu pun kebutuhan yang **harus** memakai komponen GPL/AGPL, **asalkan** tiga jebakan dihindari: (a) build FFmpeg `--enable-gpl`/libx264, (b) Ultralytics YOLO (AGPL), (c) model InsightFace (non-komersial).

Rekomendasi tulang punggung:

| Tahap | Pilihan utama | Alasan singkat |
|---|---|---|
| ASR + timestamp | **faster-whisper** (CTranslate2) + `large-v3-turbo` | tercepat di GPU 8 GB, word timestamp tersedia, MIT |
| Penajaman timestamp per kata | **WhisperX align** + `cahya/wav2vec2-large-xlsr-indonesian` | forced alignment phoneme-level; **Indonesia didukung** (ada di daftar default) |
| Diarisasi | **pyannote.audio community-1** | satu-satunya yang praktis di Windows; NeMo tidak mendukung Windows |
| Wajah (preview) | **MediaPipe BlazeFace** | 2,94 ms/frame di CPU, Apache-2.0 |
| Wajah (export) | MediaPipe full-range / ByteTrack | hindari SCRFD/InsightFace karena lisensi model |
| Active speaker | **Light-ASD** | mAP 94,06 % AVA-ActiveSpeaker, MIT |
| Scene/silence | **PySceneDetect** + `ffmpeg silencedetect`/auto-editor | BSD-3 / Unlicense |
| LLM skoring | **llama.cpp** + Qwen3-8B Q4_K_M | 4,68 GB, Apache-2.0, JSON schema terjamin |
| Render | **FFmpeg LGPL + NVENC + libass (ASS `\k`)** | 2 pass sederhana: crop/scale → burn ASS, karaoke tanpa ratusan filter |

**Temuan paling menentukan:** diarisasi adalah mata rantai terlemah untuk konten Indonesia. Satu-satunya studi yang ditemukan melaporkan DER **53,47 %** untuk pipeline pyannote zero-shot pada audio percakapan Indonesia (turun ke 29,24 % setelah domain adaptation). Angka ini belum tentu representatif untuk podcast 2 orang, tapi cukup untuk menyimpulkan: **kualitas diarisasi Indonesia wajib diukur sendiri sebelum arsitektur dikunci.**

---

## 2. Metode & tingkat bukti

Setiap klaim diberi label:

- **[KODE]** — dibaca langsung dari source/README/API repo (bukti terkuat untuk "apa yang benar-benar ada").
- **[DOK]** — dokumentasi resmi atau model card (menyatakan niat/kontrak).
- **[PAPER]** — preprint/jurnal (bukti terukur, tapi cakupan terbatas).
- **[EST]** — estimasi/penalaran engineer, **bukan** hasil ukur. Tidak boleh dipakai sebagai angka kontrak.

Catatan penting: dokumentasi menggambarkan niat, kode menggambarkan kondisi. Bila keduanya berbeda, saya tulis perbedaannya.

---

## 3. Tabel komponen (deliverable utama)

VRAM di bawah ini adalah **puncak per tahap**, bukan penjumlahan — pipeline dirancang sekuensial (lihat §11).

| # | Fungsi | Pilihan utama | Alternatif | VRAM (puncak) | Lisensi | Catatan |
|---|---|---|---|---|---|---|
| 1 | ASR + timestamp | faster-whisper + `large-v3-turbo` (int8_float16) | whisper.cpp; WhisperX penuh | ~1,6–2,8 GB [EST] | MIT (kode) / MIT (bobot turbo) | 12,4–48,8× realtime di RTX 3070 Ti 8 GB (large-v2) |
| 2 | ASR fallback CPU | faster-whisper `small` int8 | whisper.cpp `small` | RAM ~1,5 GB | MIT | CPU 8 thread: 1m42s per 13 menit audio (~7,6× realtime) |
| 3 | Word alignment | WhisperX `align()` + `cahya/wav2vec2-large-xlsr-indonesian` | timestamp bawaan faster-whisper (DTW) | ~0,6–1 GB [EST] | BSD-2 (WhisperX) / Apache-2.0 (model) | Model align Indonesia **ada** di default WhisperX |
| 4 | VAD / potong sunyi | Silero VAD (built-in faster-whisper) | `ffmpeg silencedetect` | CPU | MIT | Aktifkan `vad_filter=True` untuk cegah halusinasi |
| 5 | Diarisasi speaker | pyannote.audio `speaker-diarization-community-1` | pyannote 3.1 (legacy); NeMo Sortformer (**tidak bisa di Windows**) | ~1,0–1,5 GB [EST] | MIT (kode) / **CC-BY-4.0** (bobot) | Gated di HF; wajib bundle bobot + atribusi |
| 6 | Deteksi wajah realtime | MediaPipe BlazeFace (short/full range) | MediaPipe Face Landmarker | ~0 (CPU/GPU ringan) | Apache-2.0 | 2,94 ms/frame CPU (Pixel 6) |
| 7 | Deteksi wajah export | MediaPipe full-range | YuNet (OpenCV Zoo, verifikasi lisensi) | <0,5 GB [EST] | Apache-2.0 | **Jangan** pakai InsightFace/SCRFD weights |
| 8 | Face tracking | ByteTrack (`lap`) | IoU tracker sederhana | CPU | MIT | ByteTrack dipakai auto-vertical-reframe |
| 9 | Active speaker detection | Light-ASD | TalkNet-ASD (lebih berat) | <1 GB [EST] | MIT | mAP 94,06 % AVA-ActiveSpeaker |
| 10 | Auto-reframe + smoothing | in-house (Kalman + EMA + deadband) | salin algoritma auto-vertical-reframe | 0 | — | Library siap pakai bergantung YOLO (AGPL) |
| 11 | Scene cut | PySceneDetect 0.7.2 | `ffmpeg scdet` | CPU | BSD-3-Clause | `ContentDetector`/`AdaptiveDetector` |
| 12 | Cut silence/dead-air | auto-editor / `ffmpeg silencedetect` | — | CPU | Unlicense / LGPL | auto-editor default `--edit audio:threshold=0.04`; filler word butuh logika sendiri (§8.3) |
| 13 | LLM skoring hook | llama.cpp + Qwen3-8B-Instruct Q4_K_M | Qwen2.5-7B-Instruct Q4_K_M (4,36 GB) | 4,68 GB + KV [KODE] | MIT / Apache-2.0 | JSON schema via `response_format`/GBNF |
| 14 | Skoring embedding | sentence-transformers + `paraphrase-multilingual-MiniLM-L12-v2` | BGE-M3 (MIT) | ~0,5 GB [EST] | Apache-2.0 | 117 M param, jalan di CPU |
| 15 | Render/encode | FFmpeg LGPL + `h264_nvenc`/`hevc_nvenc` | OpenH264 (BSD-2) untuk CPU | ~0,5–1 GB [EST] | LGPL-2.1+ | **Tanpa** `--enable-gpl`, **tanpa** libx264 |
| 16 | Caption karaoke | ASS + libass via filter `subtitles` | drawtext (tidak disarankan) | CPU | ISC | libass punya `EF_KARAOKE`, `EF_KARAOKE_KF`, `EF_KARAOKE_KO` |
| 17 | Prototyping | MoviePy 2.x | — | — | MIT | Jangan untuk render produksi (per-frame Python) |

---

## 4. Pertanyaan 1 — Transkripsi word-level timestamp

### 4.1 Angka benchmark yang bisa dipertanggungjawabkan

README faster-whisper memuat benchmark 13 menit audio, **RTX 3070 Ti 8 GB, CUDA 12.4**, diukur oleh maintainer (bukan klaim pihak ketiga):

| Implementasi | Presisi | Beam | Waktu | VRAM |
|---|---|---|---|---|
| openai/whisper | fp16 | 5 | 2m23s | 4.708 MB |
| whisper.cpp (Flash Attention) | fp16 | 5 | 1m05s | 4.127 MB |
| transformers (SDPA) | fp16 | 5 | 1m52s | 4.960 MB |
| **faster-whisper** | fp16 | 5 | **1m03s** | 4.525 MB |
| **faster-whisper** `batch_size=8` | fp16 | 5 | **17s** | 6.090 MB |
| **faster-whisper** | int8 | 5 | **59s** | **2.926 MB** |
| **faster-whisper** `batch_size=8` | int8 | 5 | **16s** | 4.500 MB |

Sumber: <https://github.com/SYSTRAN/faster-whisper> (bagian *Benchmark*). Turunan: 780 s / 16 s ≈ **48,8× realtime**; 780/63 ≈ **12,4×**.

whisper.cpp dan faster-whisper **seri** di GPU (65 s vs 63 s), jadi pemilihan bukan soal kecepatan mentah, tapi soal ekosistem:

| Kriteria | faster-whisper | whisper.cpp | WhisperX |
|---|---|---|---|
| Bahasa host | Python + CTranslate2 | C/C++ murni, DLL/exe | Python + PyTorch |
| Word timestamp | `word_timestamps=True` (DTW dari cross-attention) | `-ml 1`, README menyebut **"experimental"** | `align()` — wav2vec2 forced alignment |
| Batching | `BatchedInferencePipeline` | tidak setara | ya, 70× RT (klaim README) |
| Windows | wheel + cuBLAS/cuDNN 12 | MSVC/MinGW, CUDA | butuh CUDA toolkit 12.8 |
| Instalasi | ringan (tanpa torch) | paling ringan | berat (torch ~2–3 GB) [EST] |

Sumber: <https://github.com/ggml-org/whisper.cpp> (bagian *Word-level timestamp (experimental)*, `-ml 1`), <https://github.com/m-bain/whisperX>.

### 4.2 Cara mendapatkan timestamp per kata

**faster-whisper** (paling murah, tanpa model tambahan):

```python
segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=True)
for seg in segments:
    for w in seg.words:
        print(w.start, w.end, w.word, w.probability)
```

Kontrak ini eksplisit di README (`word_timestamps=True` → `segment.words[].start/end/word`).

**WhisperX align** (akurasi lebih tinggi, khusus untuk karaoke):

```python
model_a, meta = whisperx.load_align_model(language_code="id", device="cuda")
result = whisperx.align(segments, model_a, meta, audio, "cuda")
```

Yang saya verifikasi langsung di source: `whisperx/alignment.py` baris 71 membuka `DEFAULT_ALIGN_MODELS_HF`, dan baris 107 berisi:

```python
"id": "cahya/wav2vec2-large-xlsr-indonesian",
```

Sumber: <https://raw.githubusercontent.com/m-bain/whisperX/main/whisperx/alignment.py> (baris 71–108). **[KODE]** Ini menjawab pertanyaan kritis "apakah WhisperX bisa align bahasa Indonesia" — **ya, model default-nya sudah tersedia**, tidak perlu cari model sendiri. Model `cahya/wav2vec2-large-xlsr-indonesian` berlisensi Apache-2.0, non-gated, ~100 k unduhan (HF API, diakses 6 Nov 2026).

Keterbatasan yang diakui README WhisperX: kata yang tidak ada di kamus model align (mis. `"2014."`, `"£13.60"`) **tidak mendapat timing**; overlapping speech tidak ditangani baik. Untuk podcast Indonesia dengan code-switching (ID/EN) dan angka, ini akan muncul — perlu fallback ke timestamp faster-whisper untuk token yang gagal align.

### 4.3 Ukuran model yang layak

- **`large-v3-turbo`** — 808.878.080 parameter (~809 M), lisensi MIT di HF, daftar bahasa mencakup `id`. Ini pilihan default untuk 8 GB: akurasi mendekati large, biaya komputasi ~setengah. Sumber: <https://huggingface.co/openai/whisper-large-v3-turbo> (HF API: `safetensors.total = 808878080`, `license: mit`).
- **`large-v3`** — 1.543.490.560 parameter (~1,54 B), model card di HF bertanda `apache-2.0`. Untuk 12 GB, fp16 + batch 8 masih nyaman (benchmark large-v2 batch 8 = 6,09 GB).
- **`medium`/`small`** — untuk fallback CPU. README menyebut small int8 CPU: 1m42s per 13 menit (≈7,6× realtime, 8 thread i7-12700K).

Catatan lisensi yang sering salah dikutip: kode openai/whisper MIT, tetapi **model card large-v3 di HF tertulis `apache-2.0`**, sedangkan `large-v3-turbo` tertulis `mit`. Keduanya permissive; tetap catat perbedaan ini di NOTICE aplikasi.

### 4.4 Rekomendasi

**faster-whisper untuk ASR + WhisperX hanya untuk tahap `align()`**, bukan menjalankan pipeline WhisperX penuh. Alasan: WhisperX penuh menarik torch + pyannote sekaligus (instalasi besar, konflik versi CUDA), sementara kita hanya butuh forced alignment-nya. Risiko yang harus diterima: menambah dependency torch.

Jika ukuran installer jadi masalah, rilis "lite" tanpa torch memakai `word_timestamps=True` bawaan faster-whisper — akurasi timestamp lebih rendah, tapi cukup untuk caption 2–3 kata per baris.

---

## 5. Pertanyaan 2 — Diarisasi speaker offline

### 5.1 Kandidat dan status

| Kandidat | Status di Windows | Lisensi | Catatan |
|---|---|---|---|
| **pyannote.audio community-1** | Ya (Python + torch) | MIT (kode), **CC-BY-4.0** (bobot) | gated `auto` di HF, perlu accept terms sekali |
| pyannote.audio 3.1 (legacy) | Ya | MIT (kode & bobot) | akurasi lebih rendah dari community-1 |
| NVIDIA NeMo (Sortformer) | **Tidak** | Apache-2.0 (kode), CC-BY-4.0 (Sortformer v2) | support matrix: Windows = "No support yet" |
| Alternatif cloud | — | — | di luar ruang lingkup (offline) |

Bukti NeMo: tabel *Support matrix* di <https://github.com/NVIDIA/NeMo> mencantumkan baris `windows - amd64/x64_64` → **"No support yet"** untuk pip maupun container. **[KODE]** Ini bukan preferensi, ini blocker: NeMo tidak bisa jadi dependency aplikasi Windows.

### 5.2 Kualitas: angka resmi pyannote

Dari README pyannote.audio (tabel *Benchmark*, update 2025-09), DER % (lebih rendah lebih baik):

| Benchmark | legacy 3.1 | community-1 | precision-2 (cloud) |
|---|---|---|---|
| AMI (IHM) | 18,8 | **17,0** | 12,9 |
| DIHARD 3 (full) | 21,4 | **20,2** | 14,7 |
| CALLHOME (part 2) | 28,5 | **26,7** | 16,6 |
| VoxConverse | 11,2 | **11,2** | 8,5 |
| AVA-AVD | 49,7 | **44,6** | 37,1 |

Kecepatan self-hosted: **31 detik per jam audio** (AMI IHM, ~1 jam/file) di H100 80 GB; DIHARD 37 s/jam. Sumber: <https://github.com/pyannote/pyannote-audio>.

Ini angka di H100. Di RTX 4060/3060, asumsikan 3–5× lebih lambat [EST] — masih jauh lebih cepat dari realtime, jadi bukan bottleneck.

### 5.3 Kualitas pada audio podcast Indonesia — temuan terpenting

Saya tidak menemukan benchmark resmi pyannote untuk bahasa Indonesia. Yang ada: preprint arXiv 2601.03684 (Januari 2026, Universitas Indonesia), *Domain Adaptation of the Pyannote Diarization Pipeline for Conversational Indonesian Audio*:

- Baseline `pyannote/segmentation-3.0` **zero-shot pada audio Indonesia: DER 53,47 %**.
- Setelah fine-tune dengan 2 jam data sintetis (TTS): DER ~34 %.
- Setelah fine-tune 25 jam data sintetis: **DER 29,24 %**, precision 77,78 %, recall 99,06 %, F1 87,14 %.

Sumber: <https://arxiv.org/html/2601.03684v1> (Abstrak & §IV-A).

**Cara membaca angka ini dengan jujur:**
1. Ini **preprint**, bukan benchmark peer-reviewed, dan datanya **sintetis** (edge-tts + Pydub), bukan podcast asli.
2. Yang diuji adalah `segmentation-3.0` (komponen segmentation), bukan pipeline `community-1` end-to-end. Metrik utamanya terlihat dihitung pada deteksi overlap, sehingga DER 53 % **tidak boleh** langsung dibaca sebagai "setengah transkrip salah speaker" untuk podcast 2 orang.
3. Arah sinyalnya tetap jelas: performa model English-centric **turun drastis** pada percakapan Indonesia, dan fine-tuning domain memberi perbaikan besar (24 poin absolut).

Konsekuensi desain: **jangan** menjadikan diarisasi otomatis sebagai satu-satunya sumber label speaker. Sediakan UI koreksi manual "speaker → wajah" dan batasi `num_speakers`/`min/max_speakers` (podcast umumnya 2–3) karena memberi batas jumlah speaker terbukti menaikkan akurasi pipeline (opsi `num_speakers` didokumentasikan di model card).

### 5.4 Lisensi & HF token — Detail yang menentukan untuk aplikasi offline

- Bobot: **CC-BY-4.0**, `gated: "auto"` (HF API). Artinya: komersial **diizinkan** dengan atribusi, tapi perlu menerima user conditions sekali.
- Model card menyediakan bagian **"Offline use"** eksplisit: clone pipeline ke disk, lalu `Pipeline.from_pretrained('/path/...')` — "works without internet connection". Ini jalur yang harus dipakai: **bundle snapshot di installer, jangan panggil HF saat runtime**.
- pyannote.audio punya **telemetry** opsional (mengirim metrik anonim saat `Pipeline.from_pretrained`). Untuk klaim "100 % offline", set `PYANNOTE_METRICS_ENABLED=0` di proses aplikasi. Sumber: README bagian *Telemetry*.

Kewajiban CC-BY-4.0: cantumkan atribusi "pyannote/speaker-diarization-community-1, © pyannoteAI, CC-BY-4.0" di About/NOTICE, dan sertakan link lisensi. Ini murah, tapi **wajib**.

---

## 6. Pertanyaan 3 — Active speaker detection + face tracking

### 6.1 Perbandingan kandidat

| Model/library | Lisensi | Akurasi | Beban | Layak preview? | Layak export? |
|---|---|---|---|---|---|
| **MediaPipe BlazeFace** | Apache-2.0 | cukup untuk 1–3 wajah | 2,94 ms/frame CPU; input 128×128 | **Ya** | Cukup |
| MediaPipe Face Landmarker | Apache-2.0 | + 478 landmark, blendshape | ringan | Ya | Ya (untuk crop presisi) |
| InsightFace (SCRFD/RetinaFace) | kode MIT, **bobot non-komersial** | tinggi | sedang | Tidak | **Tidak boleh** (lisensi) |
| YOLOv8/YOLO11-face | **AGPL-3.0** | tinggi | sedang | Tidak | Tidak (kecuali beli lisensi enterprise) |
| RetinaFace (implementasi MIT) | bervariasi per repo | tinggi | sedang | Tidak | Perlu audit bobot |
| **TalkNet-ASD** | MIT | tinggi | berat | Tidak | Ya |
| **Light-ASD** | MIT | mAP 94,06 % (AVA val) | ringan | Mungkin (crop kecil) | **Ya** |

Bukti lisensi (GitHub API, 6 Nov 2026): `google-ai-edge/mediapipe` → Apache-2.0; `Junhua-Liao/Light-ASD` → MIT; `TaoRuijie/TalkNet-ASD` → MIT; `ultralytics/ultralytics` → AGPL-3.0 (README: "AGPL-3.0 ... or Ultralytics Enterprise License"); `deepinsight/insightface` → **tanpa field license**, README menyatakan: *"The training data containing the annotation (and the models trained with these data) are available for non-commercial research purposes only."*

Kalimat InsightFace itu adalah jebakan lisensi paling mahal di daftar ini: kode MIT, **bobot tidak boleh dipakai komersial**. Banyak proyek open source memakainya tanpa sadar.

### 6.2 Angka performa

- **MediaPipe BlazeFace short-range**: 2,94 ms CPU / 7,41 ms GPU per frame (Pixel 6), input 128×128, float16. Sumber: <https://ai.google.dev/edge/mediapipe/solutions/vision/face_detector> (tabel *Task benchmarks*).
- **Light-ASD**: mAP **94,06 %** pada AVA-ActiveSpeaker validation; F1 **95,5 %** rata-rata di Columbia ASD setelah fine-tune TalkSet (Bell 97,7 / Boll 86,3 / Lieb 98,2 / Long 99,0 / Sick 96,3). Sumber: <https://github.com/Junhua-Liao/Light-ASD>.
- **TalkNet-ASD**: repo tidak memuat tabel benchmark di README (hanya instruksi train/test), jadi klaim akurasinya tidak bisa saya kutip dari sumber primer. **[KODE]** Ini alasan memilih Light-ASD: angka tersedia dan dapat diverifikasi.

### 6.3 Arsitektur dua tingkat (preview vs export)

**Preview (harus ≥ 10 fps di layar):**
1. Decode proxy 540p (FFmpeg/PyAV), sampling 5–8 fps.
2. BlazeFace → bbox wajah.
3. IoU tracker sederhana (atau ByteTrack) → `face_track_id`.
4. Tidak menjalankan ASD. Cukup tampilkan kotak + indikasi speaker aktif dari **timestamp diarisasi** (murah, sudah ada).

**Export (boleh 10–60 detik per menit video):**
1. Deteksi wajah pada frame asli, hanya pada segmen ada suara (dari VAD).
2. Bangun face track; ambil crop 96×96 per track per frame (input Light-ASD kecil).
3. Jalankan Light-ASD per track → skor per frame.
4. Binding ke speaker (lihat 6.4).
5. Baru hitung crop path (lihat §7).

### 6.4 Mapping diarisasi → wajah (sinkronisasi audio-visual)

Ini bagian yang tidak disediakan library mana pun secara siap pakai; harus dibuat sendiri. Algoritma yang saya usulkan:

1. **Sumbu waktu tunggal.** Semua komponen menghasilkan `(start, end)` pada timeline audio 16 kHz. Jangan pernah memakai waktu relatif per komponen.
2. **Kandidat**: untuk setiap turn diarisasi `S_i` (speaker X, t0–t1), kumpulkan semua face track yang punya frame di interval itu (dengan margin ±200 ms untuk jeda bibir).
3. **Skor**: rata-rata (atau persentil-75) skor Light-ASD tiap track pada interval tersebut → `score(track, turn)`.
4. **Assignment global**: selesaikan sebagai masalah penugasan (Hungarian / `scipy.optimize.linear_sum_assignment`) antara label speaker unik dan face track unik, memakai matriks skor agregat sepanjang klip. Ini jauh lebih stabil daripada memutuskan per turn, karena satu kesalahan di satu turn tidak merusak seluruh video.
5. **Konsistensi**: kunci hasil assignment; untuk turn dengan margin skor tipis (<0,1), fallback ke wajah terbesar/terdekat tengah, dan tandai "perlu review".
6. **Verifikasi lip-sync (opsional)**: SyncNet (MIT, <https://github.com/joonson/syncnet_python>) untuk memvalidasi pasangan audio-video pada window 0,2 s saat skor ASD ambigu.
7. **Output**: `speaker_id → face_track_id` + confidence, disimpan sebagai JSON agar bisa diedit user tanpa menjalankan ulang inferensi.

Alternatif praktis jika ASD terlalu berat: binding berbasis **wajah dominan per segmen** (wajah dengan area terbesar & paling tengah). Untuk podcast 2 orang kamera statis, ini sering sudah cukup — dan jauh lebih murah. Saya sarankan ini sebagai default, ASD sebagai opsi "akurasi tinggi".

---

## 7. Pertanyaan 4 — Auto-reframe / crop vertikal

### 7.1 Library yang sudah ada

- **KazKozDev/auto-vertical-reframe** (MIT) — pipeline lengkap: PySceneDetect `AdaptiveDetector` → YOLOv11-seg + ByteTrack → MediaPipe face/pose + saliency → subject ranking → "smoothed camera path" → FFmpeg. Punya preset `talking_head`, `max step-per-frame`, `motion damping`, `subject lock`. Sumber: <https://github.com/KazKozDev/auto-vertical-reframe>.
  - **Jebakan:** repo MIT, tapi dependency intinya **Ultralytics YOLOv11 (AGPL-3.0)**. Kalau kode ini dipakai apa adanya di produk komersial tertutup, AGPL ikut menular. Yang boleh diadopsi: **algoritma dan struktur `CameraObservation`/`CameraState`**, bukan dependency YOLO-nya.
- **obi19999/smart-video-reframe** — ada di daftar topic GitHub, belum saya audit.
- Tidak ada library khusus "crop smoothing" yang matang; ini biasanya ditulis sendiri (~100 baris numpy).

### 7.2 Strategi smoothing yang saya rekomendasikan

Urutan filter (dari murah ke mahal), dijalankan pada sumbu X dan Y terpisah:

1. **Deadband** — abaikan pergerakan < 2 % lebar crop. Membunuh jitter wajah saat bicara.
2. **EMA** — `x_t = α·x_target + (1-α)·x_{t-1}`, α ≈ 0,12–0,20 pada 30 fps. Cukup untuk 90 % kasus.
3. **Kalman filter constant-velocity** — state `[pos, vel]`, process noise rendah, measurement noise dari confidence deteksi. Dipakai bila ada gerakan kamera/dolly; ini yang membuat pan terasa "kamera operator", bukan "kotak mengikuti wajah".
4. **Batasan fisik** — clamp kecepatan (mis. ≤ 6 % lebar frame per frame) dan akselerasi; ini yang mencegah "snap" saat face track berpindah.
5. **Reset saat cut** — deteksi scene (PySceneDetect) → reset state Kalman, jangan interpolasi melewati cut.
6. **Safe area** — crop tidak boleh memotong dagu/dahi; sisakan headroom ~8 % di atas bbox wajah.

Untuk 2 pembicara: union bbox + zoom-out bertahap (max zoom-out dibatasi, mis. 1,4×) dengan histeresis 0,5 s agar tidak "pumping".

Semua parameter di atas adalah **titik awal**, bukan hasil tuning pada konten Indonesia. Wajib diuji dengan 10 clip nyata.

---

## 8. Pertanyaan 5 — Scene/silence detection & auto-cut filler

### 8.1 Scene detection

**PySceneDetect 0.7.2** (rilis 11 Okt 2026), BSD-3-Clause:

```python
from scenedetect import detect, ContentDetector
scenes = detect("video.mp4", ContentDetector())
```

Detector yang tersedia (dari dokumentasi API): `ContentDetector` (HSV weighted), `AdaptiveDetector` (rolling average, lebih tahan gerakan kamera), `ThresholdDetector` (fade in/out), `HistogramDetector`, `HashDetector`. Backend: OpenCV / PyAV / MoviePy. Sumber: <https://www.scenedetect.com/docs/latest/api.html>, <https://github.com/Breakthrough/PySceneDetect>.

Catatan operasional: PySceneDetect butuh FFmpeg/mkvmerge **hanya** untuk fitur split video; untuk analisis saja tidak perlu.

### 8.2 Silence detection

Dua jalur:

- **`ffmpeg silencedetect`** (filter audio, output ke stderr): ambang `-30dB`, durasi min 0,35 s. Cocok untuk dead-air podcaster.
- **auto-editor** (Unlicense — domain publik, paling aman secara lisensi): default `--edit audio:threshold=0.04,stream=all`, `--margin 0.2sec` untuk menyisakan napas sebelum/sesudah potongan. Sumber: <https://github.com/WyattBlue/auto-editor> (README baris 34–50).

Rekomendasi: pakai VAD (Silero) untuk keputusan "ada suara", `silencedetect` untuk verifikasi, dan auto-editor hanya sebagai referensi algoritma — bukan dependency, karena kita sudah punya timeline dari ASR.

### 8.3 Auto-cut filler word (um/uh) — ini lebih sulit dari kelihatannya

Masalah: Whisper **cenderung tidak menuliskan** filler seperti "eee"/"emm" secara konsisten; ia "membersihkan" transkrip. Kalau filler hanya dicari dari teks ASR, hasilnya akan under-detect dan tidak deterministik.

Pendekatan yang realistis:

1. **Kandidat dari alignment**: jalankan forced alignment (WhisperX) → dapat interval tiap kata.
2. **Gap analysis**: cari gap antar kata > 180–250 ms yang **bukan** silence (ada energi suara). Gap berenergi = kandidat filler/artefak.
3. **Leksikon Indonesia**: `eee, emm, hmm, apa ya, gitu, kayak, nah, kan, sih, deh` — dengan aturan: hanya potong jika durasi < 400 ms dan tidak mengubah makna (kata seperti "kan"/"nah" sering bermakna, jadi default **jangan** dipotong otomatis; tampilkan sebagai saran).
4. **Keputusan**: potong hanya jika (a) terdeteksi di teks ASR, atau (b) user menandainya di UI. Jangan auto-potong berbasis gap murni — risiko memotong jeda dramatis.
5. **Eksekusi**: karena potongan banyak dan pendek, jangan re-encode per potongan. Bangun `select`/`concat` filter atau render per segmen lalu concat dengan `-c copy` bila codec/timebase kompatibel.

**Tingkat keyakinan: rendah-menengah.** Tidak ada library siap pakai untuk filler removal Bahasa Indonesia yang saya temukan; ini pekerjaan riset kecil sendiri, dan harus divalidasi dengan sampel nyata.

---

## 9. Pertanyaan 6 — LLM lokal untuk skoring hook/viral

### 9.1 Runtime

| Runtime | Lisensi | Status untuk produk komersial |
|---|---|---|
| **llama.cpp** (`llama-server`) | MIT | **Aman** — bundle exe, kontrol penuh, OpenAI-compatible API |
| Ollama | MIT | Aman, tapi menambah service/daemon + updater sendiri |
| LM Studio | Proprietary (Element Labs) | **Tidak boleh** — Terms §1 menyatakan lisensi "personal, non-commercial purposes", §4.2 melarang "commercial or business purpose" |

Bukti LM Studio: <https://lmstudio.ai/terms> — §1 ("for the sole purpose of using the Services for your personal, non-commercial purposes") dan §4.2 ("Use Company Properties or any part thereof for any commercial or business purpose" dilarang). Ini diskualifikasi langsung.

Untuk Ollama: lisensi MIT (GitHub API), tapi arsitekturnya daemon terpisah yang harus di-install user. Untuk aplikasi desktop yang harus "hidup sendiri", **llama.cpp yang di-bundle** lebih terkontrol: satu proses anak, port lokal, dimatikan saat aplikasi keluar.

### 9.2 Model 7–8B yang muat di 8 GB

| Model | Quant | Ukuran file | Lisensi | Catatan |
|---|---|---|---|---|
| **Qwen3-8B-Instruct** | Q4_K_M | **4,68 GB** | Apache-2.0 | 8,19 B param; punya mode thinking (bisa dimatikan) |
| Qwen2.5-7B-Instruct | Q4_K_M | 4,36 GB (2 shard) | Apache-2.0 | 7,62 B param, lebih hemat, tanpa thinking |
| Qwen3-4B | Q4_K_M | ~2,5 GB | Apache-2.0 | untuk 8 GB yang ingin VRAM lega |

Ukuran file diverifikasi via HF API `tree?recursive=true` (6 Nov 2026): `Qwen3-8B-Q4_K_M.gguf` = 4,68 GB; `qwen2.5-7b-instruct-q4_k_m` = 3,72 + 0,64 GB.

Anggaran VRAM 8 GB: 4,68 GB bobot + KV cache. KV cache Qwen3-8B (32 layer, GQA) pada 8k context ≈ 0,8–1,2 GB [EST] → total ~5,5–6 GB. **Muat bersamaan dengan ASR (2–3 GB) akan OOM** → harus sekuensial atau pakai model 4B.

Kualitas skoring: ini bukan tugas reasoning berat — cukup klasifikasi/ranking dengan output JSON. Qwen3-8B Q4 sudah lebih dari cukup; jangan tergoda model 14B+ karena tidak muat dan tidak perlu.

### 9.3 Struktur output yang dijamin

Ollama mendukung `format` = JSON schema (termasuk via `response_format` OpenAI-compatible), dan menyarankan temperature 0 + schema di prompt. Sumber: <https://docs.ollama.com/capabilities/structured-outputs>. Untuk llama.cpp, ekivalennya GBNF grammar / `json_schema` di `llama-server`.

Skema yang saya usulkan:

```json
{"clips":[{"start":12.4,"end":41.2,"hook_score":0,"retention_score":0,
 "reason":"...","hook_text":"...","risk":"..."}]}
```

### 9.4 Alternatif berbasis embedding (lebih murah & deterministik)

- `sentence-transformers` (Apache-2.0) + `paraphrase-multilingual-MiniLM-L12-v2` (117,6 M param, Apache-2.0, 27,7 jt unduhan) — jalan di CPU, ~50 ms per kalimat.
- **Cara pakai**: bangun "hook library" (100–300 kalimat pembuka viral berbahasa Indonesia), embed; skor setiap kandidat segmen dengan cosine similarity ke centroid/klaster hook. Hasilnya skor 0–1 yang stabil dan bisa dijelaskan.
- **Kombinasi terbaik**: embedding untuk shortlist 30 kandidat → LLM untuk rerank 10 teratas + alasan. Total biaya: satu kali inferensi LLM untuk 10 item, bukan 100.

Ini juga mitigasi saat VRAM sempit: embedding selalu bisa jalan, LLM bisa di-skip.

---

## 10. Pertanyaan 7 — Rendering & caption karaoke

### 10.1 MoviePy vs FFmpeg langsung

- **MoviePy** (MIT): API nyaman, tapi render dilakukan per frame di Python → untuk 1080×1920 durasi 60 s, ini lambat dan memori-heavy. Layak untuk prototipe/eksperimen, **tidak** untuk produksi.
- **FFmpeg filter_complex**: satu proses, satu pass encode, tanpa memindahkan frame ke Python. Ini yang harus jadi jalur produksi.
- **PyAV**: berguna untuk decode/encode in-process bila butuh akses frame (mis. untuk overlay custom), tapi untuk caption + crop, filter graph lebih sederhana.

### 10.2 Caption: drawtext vs libass/ASS

| Pendekatan | Kelebihan | Kekurangan |
|---|---|---|
| `drawtext` per kata | kontrol penuh, tanpa file ASS | 1 filter per kata → filter graph ratusan node, startup lambat, susah di-debug |
| **ASS + libass (`subtitles` filter)** | satu file teks, animasi kaya, karaoke native, mudah di-cache | butuh generate ASS yang benar; font harus tersedia |

**Pilih ASS + libass.** libass (ISC) adalah renderer ASS/SSA yang "mostly compatible with VSFilter" (README, rilis 0.17.5 / 24 Jun 2026). Dukungan karaoke terverifikasi di source `libass/ass_parse.c`:

```
849:  state->effect_type = EF_KARAOKE_KF;
857:  state->effect_type = EF_KARAOKE_KO;
865:  state->effect_type = EF_KARAOKE;
```

Sumber: <https://raw.githubusercontent.com/libass/libass/master/libass/ass_parse.c> (baris 849–865). **[KODE]** Artinya `\k`, `\kf`, `\ko` benar-benar diimplementasikan, bukan sekadar diklaim.

Contoh baris ASS karaoke per kata (durasi dalam centisecond):

```
Dialogue: 0,0:00:12.40,0:00:13.10,Cap,,0,0,0,,{\k20}Jadi {\k35}ini {\k15}rahasia
```

Untuk efek "highlight per kata" gaya CapCut: warna sekunder (`\2c`) untuk pre-highlight + `\kf` untuk wipe; atau `\t` untuk scale pop. Semua ini dirender libass, jadi konsisten antara preview (libass di app) dan export.

**Penting untuk konsistensi preview↔export:** pakai **libass yang sama** di kedua jalur (mis. `libass` via FFmpeg untuk export, dan `libass`/`mpv` untuk preview). Kalau preview dirender dengan canvas/HTML5 dan export dengan libass, hasilnya akan beda (font fallback, kerning, border).

### 10.3 NVENC

- `h264_nvenc`, `hevc_nvenc`, `av1_nvenc` tersedia di FFmpeg; encode dilakukan di NVENC block GPU (terpisah dari CUDA core, jadi tidak berebut dengan inferensi secara signifikan).
- Kecepatan: jauh lebih cepat dari x264 pada preset lambat; kualitas per bitrate sedikit di bawah x264 `slow` [EST — perlu uji sendiri].
- **Lisensi**: NVENC bukan masalah lisensi untuk aplikasi (tidak ada royalti), **tapi** build FFmpeg yang dipakai harus LGPL. Jika build mengandung `--enable-gpl` (mis. karena libx264), seluruh binary jadi GPL.

### 10.4 Kombinasi filter yang disarankan (satu pass)

```
[0:v]crop=w=ih*9/16:h=ih:x='<x(t)>':y=0,scale=1080:1920:flags=lanczos,
     ass=captions.ass:fontsdir=fonts[v]
```

Catatan teknis: ekspresi `x(t)` hanya bisa berisi fungsi matematis, **bukan** array hasil tracking. Untuk crop path non-linear, ada dua opsi:
1. **Pre-render crop path** menjadi file video proxy yang sudah di-crop (paling sederhana, satu pass tambahan).
2. **`sendcmd`/`zmq`** untuk mengirim perintah crop per frame (kompleks, rapuh).
3. **Zoompan/overlay** dengan keyframe dari file — paling mudah di-debug: render video yang sudah di-crop & scale, lalu pass kedua burn ASS (2 pass, tapi tiap pass sederhana dan parallelizable).

Rekomendasi: **2 pass** (crop+scale → burn subtitle+audio) meski terlihat boros, karena (a) tiap pass bisa di-CPU-kan/di-GPU-kan terpisah, (b) mudah resume jika gagal, (c) menghindari filter graph raksasa yang susah di-debug.

---

## 11. Anggaran VRAM & strategi 8 GB vs 12 GB

Kunci: **jangan menjalankan semua model bersamaan**. Pipeline harus sekuensial dengan unload eksplisit (`del model; gc.collect(); torch.cuda.empty_cache()`).

| Tahap | Model | VRAM 8 GB | VRAM 12 GB |
|---|---|---|---|
| 1. ASR | large-v3-turbo int8_float16 | 1,6–2,8 GB [EST] | large-v3 fp16 batch 8: ~6,1 GB (terukur large-v2) |
| 2. Align | wav2vec2 Indonesian | ~0,6–1 GB [EST] | sama |
| 3. Diarisasi | pyannote community-1 | ~1,0–1,5 GB [EST] | sama |
| 4. Face + ASD | MediaPipe + Light-ASD | <1,5 GB [EST] | sama |
| 5. LLM | Qwen3-8B Q4_K_M | 4,68 GB + KV ~1 GB | sama, context lebih besar |
| 6. Encode | NVENC | ~0,5–1 GB | sama |

**Implikasi 8 GB:** tahap 1–4 bisa berjalan dengan model ASR tetap di VRAM (total ~4–5 GB). LLM **tidak bisa** bersamaan dengan ASR large → pilihan: (a) unload ASR dulu, (b) pakai Qwen3-4B, (c) jalankan LLM di CPU (lambat, tapi offline tetap jalan).

**Fallback CPU (wajib ada):**
- ASR: faster-whisper `small` int8 (RAM 1,5 GB, ~7,6× RT pada 8 thread).
- Align: model wav2vec2 di CPU — lambat, tapi tetap jalan.
- Diarisasi: pyannote di CPU — bisa 5–10× lebih lambat dari GPU [EST]; untuk video 30 menit bisa jadi 10–20 menit. Tampilkan progress.
- LLM: llama.cpp CPU (Q4 8B ≈ 5–8 token/s pada CPU modern) — cukup untuk 10 kandidat.

**Deteksi GPU & degradasi:** aplikasi harus memilih profil saat start (GPU 8 GB / GPU 12 GB / CPU) dan menyimpan pilihan di config, bukan menebak setiap run.

---

## 12. Matriks lisensi komersial (jawaban pertanyaan 8)

| Komponen | Lisensi | Boleh dijual? | Kewajiban / risiko |
|---|---|---|---|
| faster-whisper (kode) | MIT | Ya | sertakan notice |
| CTranslate2 | MIT | Ya | — |
| Whisper weights (`large-v3-turbo`) | MIT | Ya | — |
| Whisper weights (`large-v3`) | Apache-2.0 (model card HF) | Ya | NOTICE |
| WhisperX | BSD-2-Clause | Ya | notice |
| `cahya/wav2vec2-large-xlsr-indonesian` | Apache-2.0 | Ya | notice |
| Silero VAD | MIT | Ya | notice |
| pyannote.audio (kode) | MIT | Ya | notice |
| **pyannote community-1 (bobot)** | **CC-BY-4.0** | **Ya** | **atribusi wajib**; gated → bundle manual |
| MediaPipe | Apache-2.0 | Ya | notice + patent grant |
| **InsightFace (bobot)** | **non-commercial** | **TIDAK** | pelanggaran lisensi jika dipakai komersial |
| **Ultralytics YOLO** | **AGPL-3.0** | **Tidak** (kecuali beli enterprise) | wajib open-source seluruh aplikasi jika dipakai |
| TalkNet-ASD / Light-ASD | MIT | Ya | notice |
| ByteTrack | MIT | Ya | notice |
| PySceneDetect | BSD-3-Clause | Ya | notice |
| auto-editor | Unlicense | Ya | none |
| **FFmpeg** | **LGPL-2.1+**, tapi jadi **GPL** jika `--enable-gpl` | Ya **hanya** build LGPL | distribute source FFmpeg, dynamic link, **jangan libx264** |
| libass | ISC | Ya | notice |
| OpenH264 | BSD-2-Clause | Ya | Cisco patent license; ada kewajiban binari |
| llama.cpp | MIT | Ya | notice |
| Ollama | MIT | Ya | jika dibundel, ukuran installer naik |
| **LM Studio** | proprietary | **TIDAK** | Terms melarang penggunaan komersial |
| Qwen3-8B / Qwen2.5-7B | Apache-2.0 | Ya | notice |
| sentence-transformers | Apache-2.0 | Ya | notice |
| `paraphrase-multilingual-MiniLM-L12-v2` | Apache-2.0 | Ya | notice |
| MoviePy | MIT | Ya | hanya untuk prototipe |

### Checklist kepatuhan minimum

1. **Jangan** pernah build FFmpeg dengan `--enable-gpl` atau `--enable-nonfree`. Checklist resmi FFmpeg menyebut eksplisit: *"Make sure your program is not using any GPL libraries (notably libx264)"* (<https://www.ffmpeg.org/legal.html>).
2. Sediakan halaman **"Third-party notices"** yang memuat: MIT/BSD/Apache texts + atribusi CC-BY-4.0 pyannote.
3. Cantumkan di About: *"This software uses libraries from the FFmpeg project under the LGPLv2.1"* + link source.
4. **Audit bobot model**, bukan hanya kode. Tiga jebakan: InsightFace, YOLO, dan model apa pun yang di-download dari sumber tidak jelas.
5. Jika memakai NVENC: tidak ada royalti, tapi tetap butuh driver NVIDIA; sediakan fallback OpenH264/`libopenh264` untuk mesin tanpa NVENC.

**Catatan:** ini bukan nasihat hukum. Untuk aplikasi yang benar-benar dijual, mintakan review ke counsel dengan daftar di atas.

---

## 13. Arsitektur pipeline yang diusulkan

```
[Input video]
   │  FFmpeg probe + proxy 540p
   ▼
[1] Audio extract 16k mono (FFmpeg)
   ▼
[2] VAD (Silero)  ──► segmen bersuara
   ▼
[3] ASR faster-whisper large-v3-turbo (word_timestamps=True)
   ▼
[4] Align WhisperX + wav2vec2-id  ──► kata + start/end presisi
   ▼
[5] Diarisasi pyannote community-1 ──► turn speaker
   ▼
[6] Face detect (MediaPipe) + ByteTrack ──► face track
   ▼
[7] Light-ASD (opsional) ──► skor per track/frame
   ▼
[8] Binding speaker ↔ face (Hungarian) ──► speaker_map.json
   ▼
[9] Kandidat klip: scene cut + hook scoring (embedding → LLM)
   ▼
[10] Crop path per klip (deadband → EMA → Kalman → clamp)
   ▼
[11] Render: pass 1 crop+scale (NVENC) ──► pass 2 ASS burn + audio
   ▼
[Output 1080×1920 MP4]
```

Prinsip: **setiap tahap menghasilkan artefak JSON di disk** (transkrip, diarisasi, face track, crop path, skor). Ini membuat (a) tahap bisa diulang tanpa mengulang semuanya, (b) user bisa mengedit, (c) debugging jauh lebih mudah, (d) cocok untuk aplikasi offline yang harus tahan crash.

---

## 14. Gap & hal yang belum terbukti

| # | Gap | Dampak | Cara menutup |
|---|---|---|---|
| G1 | **Tidak ada angka DER pyannote community-1 pada podcast Indonesia** | tinggi — ini komponen paling rapuh | buat eval set 10–20 klip (2–4 speaker), anotasi RTTM manual, ukur DER sendiri |
| G2 | Paper Indonesia hanya menguji `segmentation-3.0` dengan data sintetis | tinggi — angka 53 % tidak bisa dipakai sebagai ekspektasi produk | replikasi dengan audio nyata; bandingkan 3.1 vs community-1 |
| G3 | Tidak ada benchmark Light-ASD pada footage podcast Indonesia | sedang | uji manual 20 klip; bandingkan vs baseline "wajah dominan" |
| G4 | Akurasi timestamp kata pada code-switching ID/EN dan angka | sedang | uji 100 kata acak, hitung median error (ms) |
| G5 | Kecepatan pyannote di RTX 4060/3060 belum diukur (angka resmi H100) | rendah | benchmark lokal, catat s/audio-hour |
| G6 | Filler-word removal Indonesia belum ada library | sedang | riset kecil + UI review manual |
| G7 | Kualitas NVENC vs x264 pada bitrate target (mis. 8 Mbps 1080×1920) | rendah | uji VMAF/SSIM 5 klip |
| G8 | Lisensi `cahya/wav2vec2...` sudah dicek (Apache-2.0), tapi **dataset** pelatihannya tidak diaudit | rendah | catat sebagai risiko; model card tidak menyebut dataset terlarang |

**Yang saya hentikan pencariannya:** benchmark TalkNet-ASD (repo tidak memuat angka, dan saya sudah punya Light-ASD yang terverifikasi), dan alternatif diarisasi non-pyannote di Windows (NeMo dinyatakan tidak support; tidak ada kandidat lain yang matang). Keduanya tidak akan mengubah keputusan.

---

## 15. Rekomendasi berikutnya (urut ROI)

1. **Bangun eval set Indonesia (paling mendesak).** 10–20 klip podcast 2–4 speaker, 3–10 menit, dengan ground truth: transkrip kata, RTTM speaker, dan daftar wajah per speaker. Tanpa ini, semua keputusan di atas hanya teori. Perkiraan usaha: 2–3 hari.
2. **Ukur deret waktu nyata** pada RTX 8 GB: ASR turbo int8 → align → diarisasi, catat detik per menit audio dan puncak VRAM. Ini yang menentukan apakah "1 klip 60 detik dari video 60 menit" selesai < 10 menit.
3. **Prototipe render ASS karaoke** dengan 1 klip: buktikan `\kf` + font + border tampil sama di preview dan export. Ini risiko visual terbesar (hasil jelek = produk jelek).
4. **Uji binding speaker↔wajah** pada 3 video: baseline "wajah dominan" vs Light-ASD. Kemungkinan besar baseline sudah cukup untuk podcast statis — dan itu menghemat 1 model + waktu export.
5. **Putuskan jalur LLM**: bundle llama.cpp + Qwen3-8B (4,68 GB) atau Qwen3-4B. Ukuran installer jadi konsekuensi langsung.

---

## 16. Daftar sumber (diakses 6 November 2026)

**Transkripsi**
- faster-whisper (README, benchmark, word timestamps): <https://github.com/SYSTRAN/faster-whisper>
- whisper.cpp (Windows, CUDA, word-level `-ml 1` "experimental"): <https://github.com/ggml-org/whisper.cpp>
- WhisperX (pipeline, 70× RT, batasan): <https://github.com/m-bain/whisperX>
- WhisperX alignment — daftar model per bahasa (`id` di baris 107): <https://raw.githubusercontent.com/m-bain/whisperX/main/whisperx/alignment.py>
- `openai/whisper-large-v3-turbo` (809 M param, MIT): <https://huggingface.co/openai/whisper-large-v3-turbo>
- `openai/whisper-large-v3` (1,54 B param, Apache-2.0 per model card): <https://huggingface.co/openai/whisper-large-v3>
- `cahya/wav2vec2-large-xlsr-indonesian` (Apache-2.0): <https://huggingface.co/cahya/wav2vec2-large-xlsr-indonesian>

**Diarisasi**
- pyannote.audio (benchmark DER, telemetry, instalasi): <https://github.com/pyannote/pyannote-audio>
- `pyannote/speaker-diarization-community-1` (offline use, CC-BY-4.0, gated): <https://huggingface.co/pyannote/speaker-diarization-community-1>
- HF API metadata (license cc-by-4.0, gated auto): <https://huggingface.co/api/models/pyannote/speaker-diarization-community-1>
- NeMo (support matrix Windows = No support): <https://github.com/NVIDIA/NeMo>
- Prasetyo et al., *Domain Adaptation of the Pyannote Diarization Pipeline for Conversational Indonesian Audio*, arXiv:2601.03684: <https://arxiv.org/html/2601.03684v1>

**Wajah / ASD**
- MediaPipe Face Detector (BlazeFace, latency 2,94 ms): <https://ai.google.dev/edge/mediapipe/solutions/vision/face_detector>
- MediaPipe repo (Apache-2.0): <https://github.com/google-ai-edge/mediapipe>
- InsightFace (kode MIT, bobot non-komersial): <https://github.com/deepinsight/insightface>
- Ultralytics YOLO (AGPL-3.0 / enterprise): <https://github.com/ultralytics/ultralytics>
- Light-ASD (mAP 94,06 %, MIT): <https://github.com/Junhua-Liao/Light-ASD>
- TalkNet-ASD (MIT): <https://github.com/TaoRuijie/TalkNet-ASD>
- SyncNet (MIT): <https://github.com/joonson/syncnet_python>
- ByteTrack (MIT): <https://github.com/ifzhang/ByteTrack>

**Reframe / scene / cut**
- auto-vertical-reframe (MIT, pipeline + jebakan YOLO AGPL): <https://github.com/KazKozDev/auto-vertical-reframe>
- PySceneDetect API & detector: <https://www.scenedetect.com/docs/latest/api.html>
- PySceneDetect repo (BSD-3, v0.7.2): <https://github.com/Breakthrough/PySceneDetect>
- auto-editor (Unlicense, `--edit audio:threshold`, `--margin`): <https://github.com/WyattBlue/auto-editor>

**LLM / embedding**
- llama.cpp (MIT): <https://github.com/ggml-org/llama.cpp>
- Ollama (MIT): <https://github.com/ollama/ollama>
- Ollama structured outputs (JSON schema): <https://docs.ollama.com/capabilities/structured-outputs>
- LM Studio Terms (non-commercial): <https://lmstudio.ai/terms>
- `Qwen/Qwen3-8B` (Apache-2.0): <https://huggingface.co/Qwen/Qwen3-8B>
- `Qwen/Qwen2.5-7B-Instruct` (Apache-2.0): <https://huggingface.co/Qwen/Qwen2.5-7B-Instruct>
- sentence-transformers (Apache-2.0): <https://github.com/UKPLab/sentence-transformers>
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`: <https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2>

**Rendering / lisensi**
- FFmpeg legal (LGPL vs GPL, larangan libx264): <https://www.ffmpeg.org/legal.html>
- libass (ISC, rilis 0.17.5): <https://github.com/libass/libass>
- libass karaoke (`EF_KARAOKE`, `_KF`, `_KO`) di `ass_parse.c` baris 849–865: <https://raw.githubusercontent.com/libass/libass/master/libass/ass_parse.c>
- ASS override tags (referensi format): <https://aegisub.org/docs/latest/ass_tags/>
- MoviePy (MIT): <https://github.com/Zulko/moviepy>
- OpenH264 (BSD-2): <https://github.com/cisco/openh264>
