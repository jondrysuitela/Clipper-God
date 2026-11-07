# ClipperGod — Spec Produk & Teknis

**Versi:** 0.1 (draft untuk review)
**Tanggal:** 6 November 2026
**Basis:** `research/01-teardown-produk.md`, `research/02-stack-offline.md`, `research/03-sains-hook-viral.md`

---

## 1. Ringkasan

ClipperGod adalah aplikasi desktop Windows yang memotong video panjang (podcast, webinar, interview, stream) menjadi klip vertikal siap-posting — **100% offline**, tanpa kredit, tanpa upload ke server siapa pun.

Posisi di pasar:

| Sumbu | Kompetitor | ClipperGod |
|---|---|---|
| Biaya | $6–40/bln, dihitung per menit sumber | Nol. Tanpa batas durasi |
| Privasi | Master video disimpan 3–29 hari di server mereka | Tidak pernah keluar dari disk |
| Batas potongan | Output AI + perbaikan manual | Aturan deterministik yang bisa dilihat & diubah |
| Framing | Aktif-speaker dari audio + motion | Visual-first (ASD), tahan crosstalk |
| Skor | Angka tunggal tanpa kalibrasi | Per komponen + alasan + bisa dilatih ulang |

**Bukan** aplikasi editing umum. Fokus: dari satu video panjang → N klip siap posting, dalam sekali duduk.

---

## 2. Prinsip desain

1. **Batas potongan lebih penting daripada skor.** Semua kompetitor kalah di keluhan yang sama: klip mulai/berhenti di tempat salah. Skor yang bagus tidak menyelamatkan klip yang terpotong di tengah kalimat.
2. **Caption = transkrip = timeline.** Satu struktur data (bukti: Descript wordbar). Tiga struktur terpisah = setiap perbaikan caption berantakan.
3. **Setiap tahap menghasilkan artefak JSON di disk.** Bisa diulang tanpa mengulang semuanya, bisa diedit user, tahan crash.
4. **Jujur soal ketidakpastian.** Kalau confidence rendah, tandai "perlu review" — jangan pura-pura yakin.
5. **Transkrip dan waktunya sama di preview dan export.** Preview Studio memakai overlay browser yang bisa diubah tanpa render; export final memakai libass. Framing dan hasil caption final hanya bisa dipastikan setelah render.

---

## 3. Peta fitur

### P0 — tanpa ini produknya tidak jadi produk

| Fitur | Deskripsi | Basis |
|---|---|---|
| **Import & Proxy** | Tarik file/URL lokal, generate proxy 540p untuk scrubbing | — |
| **Auto Transcribe** | faster-whisper + word timestamp, bahasa auto-detect (ID/EN/campur) | riset 02 §4 |
| **Semantic Boundary Engine** | Batas klip di-snap ke jeda aman; larangan potong di tengah kalimat/klausa; punchline guard | riset 01 §5.1a, 03 §12.8 |
| **Candidate Generator** | 10–60 kandidat klip dengan durasi target (reach/watch/story) | riset 03 §12.7 |
| **Viral Potential Score** | 0–100, terurai 6 komponen + alasan tekstual + hard gates | riset 03 §12.1 |
| **Auto Caption Karaoke** | ASS + libass, highlight per kata, font & efek, 3–5 kata/baris | riset 02 §10.2, 03 §12.4 |
| **Face-Aware Caption Placement** | Caption menghindari bbox wajah + safe zone platform | **baru** |
| **Auto Reframe 9:16** | Face track + crop path (deadband→EMA→Kalman→clamp) | riset 02 §7 |
| **Export 1080×1920** | NVENC, -14 LUFS, true peak -1 dBTP, faststart | riset 03 §12.5, §12.7 |

### P1 — yang membuatnya terasa profesional

| Fitur | Deskripsi |
|---|---|
| **Speaker Timeline** | Binding speaker→wajah, JSON editable, warna caption per speaker, badge "perlu review" |
| **Layout Engine** | Fill / Fit / Split / Three / Screenshare / Gameplay (30:70) |
| **Punch-in Zoom** | 1.08–1.20× tiap 3–5 s, dipicu energi audio + emphasis |
| **Silence & Filler Cut** | Buang jeda ≥0.35 s gaya seamless; filler hanya disarankan, tidak auto-potong |
| **Auto Emoji & Keyword Highlight** | Emoji relevan per cue, maksimal 1 per 5 detik |
| **Burned-in Subtitle Rescue** | OCR deteksi subtitle bawaan → crop / mask / offset |
| **Hook A/B Lab** | 3 varian 3 detik pertama dari body yang sama |
| **Clip DNA** | Fingerprint episode, cegah klip duplikat lintas upload |

### P2 — pembeda jangka panjang

| Fitur | Deskripsi |
|---|---|
| **Multicam Auto-Switch** | Sync kamera terpisah via audio fingerprint, switch per speaker |
| **Brand Kit & Template** | Font, warna, logo, intro/outro, posisi caption |
| **Batch Queue** | Antrean 20+ video, jalan semalam |
| **Kalibrasi Skor** | Import analytics (CSV) → refit bobot VPS via ridge regression |
| **B-roll Lokal** | Library folder user, dipilih via embedding |

---

## 4. Arsitektur

```
[Video] ──FFmpeg probe + proxy 540p──┐
                                     ▼
              [1] Audio 16k mono ──► [2] VAD (Silero)
                                     ▼
              [3] ASR faster-whisper large-v3-turbo (word_timestamps)
                                     ▼
              [4] Align WhisperX + wav2vec2-id
                                     ▼
              [5] Diarisasi pyannote community-1
                                     ▼
              [6] Face detect MediaPipe + ByteTrack
                                     ▼
              [7] Light-ASD (opsional, akurasi tinggi)
                                     ▼
              [8] Binding speaker↔face (Hungarian)
                                     ▼
              [9] Candidate gen + Semantic Boundary + VPS
                                     ▼
             [10] Crop path per klip (deadband→EMA→Kalman→clamp)
                                     ▼
             [11] ASS karaoke + face-aware placement
                                     ▼
             [12] Render 2 pass: crop/scale → burn ASS + audio
                                     ▼
                    [1080×1920 MP4]
```

**Aturan:** tahap 3–8 dijalankan sekali per video; tahap 9–12 dijalankan per klip. Semua output tahap 3–8 = artefak JSON di `project/artifacts/`.

### Profil hardware (auto-detect saat first run)

| Profil | ASR | Diarisasi | LLM | Perkiraan 60 menit sumber |
|---|---|---|---|---|
| **GPU ≥8 GB** | large-v3-turbo int8_float16 | community-1 | Qwen3-8B Q4 (unload ASR dulu) | ~2–3 menit transkrip, klip pertama <10 menit |
| **GPU 4–6 GB** | medium int8 | community-1 | Qwen3-4B Q4 | ~5–8 menit transkrip |
| **CPU only** | small int8 | community-1 (CPU) | Qwen3-4B CPU | ~25–45 menit, tampilkan progress per tahap |

Model di-unload eksplisit antar tahap (`del` → `gc.collect()` → `empty_cache()`). Tanpa ini, 8 GB akan OOM.

---

## 5. Parameter resmi (dari riset, masuk config — bukan hard-code)

### Hook (H)
`hook_window` 0–3 s · `hook_eval_point` 5 s · `speech_onset_max` 0.30 s · `dead_air_head_max` 0.25 s · blacklist sapaan: "hai, guys, jadi, oke, selamat datang"

### Retensi & pacing (R)
`cpm_target` 15–30 · `cpm_soft_cap` 40 · `cpm_floor` 10 · `silence_remove` -35 dBFS, min 0.35 s, gaya seamless · `punch_in` 3–5 s, skala 1.08–1.20×

### Caption (C)
`max_lines` 2 · `max_chars_per_line` 32 (9:16) · `max_cps` 18 (target 12–16) · `min_duration` 0.83 s · `max_duration` 1.8 s · `words_per_line` 3–5 · `safe_box` x 120–960, y 270–1260 · `font_min_height` 48 px

### Audio (A)
`target_lufs` -14 · `true_peak_max` -1 dBTP · `voice_to_music_min` 6 dB · `ducking` -6 dB

### Loop & ending (L)
`loop_similarity` SSIM > 0.60 · `outro_max` 1.5 s

### Platform (P)
1080×1920 · 30 fps · 8 Mbps min (10–12 disarankan) · AAC 320 kbps 48 kHz · yuv420p · `faststart`

### Skor
```
VPS = 0.30*H + 0.20*R + 0.15*C + 0.15*A + 0.10*L + 0.10*P
```
Bobot awal = hipotesis, disimpan di config. **Hard gates** (gagal → VPS di-cap 40): tidak ada speech onset di 0.6 s pertama; caption keluar safe box; clipping (TP > 0 dBTP) atau loudness < -20 LUFS; durasi < 8 s.

---

## 6. Mesin inti

### 6.1 Semantic Boundary Engine (`core/boundaries.py`)

Untuk setiap kandidat `[start, end]`, geser ke batas aman terdekat dan tolak yang tidak bisa diselamatkan.

**Skor batas (0–1):**

| Sinyal | Bobot | Aturan |
|---|---|---|
| Pause setelah kata | 0.35 | ≥0.18 s = 1.0; 0.10–0.18 = linear; <0.10 = 0 |
| Akhir kalimat (. ? !) | 0.25 | ya = 1.0 |
| Kata terakhir bukan konjungsi/preposisi | 0.20 | dan, tapi, karena, yang, kalau, jadi, untuk, dengan, di, ke → 0 |
| Tidak di tengah filler | 0.10 | "eee, emm, hmm, apa ya" → 0 |
| Bukan awal sapaan | 0.10 | "jadi, oke, hai, guys" → 0 |

Ambang: **≥0.70 = aman**, 0.45–0.70 = geser ke kandidat berikutnya, <0.45 = tolak klip.

**Punchline guard:** kalau ada tawa/aplaus di `[end-1.5s, end+3s]` → geser `end` ke akhir tawa + 0.2 s, jangan potong sebelum reaksi selesai.

### 6.2 Caption Engine (`core/captions.py`)

Output ASS murni, dirender libass. Aturan:
- Pengelompokan cue: maks 5 kata, maks 2 baris × 32 char, durasi 0.83–1.8 s, CPS ≤18
- Karaoke: `{\kf<centisecond>}` per kata, warna sekunder untuk pre-highlight
- **Face-aware:** kalau kotak caption beririsan bbox wajah → pindah anchor (bawah→atas) di dalam safe box; font tidak pernah dikecilkan di bawah 48 px

### 6.3 VPS (`core/scoring.py`)

Setiap komponen mengembalikan (nilai 0–100, daftar alasan). UI menampilkan alasan, bukan cuma angka — "hook 82: speech mulai 0.2 s, ada pertanyaan, ada gerakan".

**Kalibrasi:** simpan VPS + analytics user; hitung Spearman per komponen. Target realistis ρ 0.25–0.40. Di bawah 0.2 → sembunyikan angka, tampilkan checklist.

---

## 7. Stack & lisensi

| Fungsi | Komponen | Lisensi |
|---|---|---|
| ASR | faster-whisper + large-v3-turbo | MIT |
| Align | WhisperX + cahya/wav2vec2-large-xlsr-indonesian | BSD-2 / Apache-2.0 |
| Diarisasi | pyannote community-1 | MIT (kode) / CC-BY-4.0 (bobot, wajib atribusi) |
| Wajah | MediaPipe BlazeFace + ByteTrack | Apache-2.0 / MIT |
| Active speaker | Light-ASD | MIT |
| Scene | PySceneDetect | BSD-3 |
| LLM | llama.cpp + Qwen3-8B Q4_K_M | MIT / Apache-2.0 |
| Embedding | paraphrase-multilingual-MiniLM-L12-v2 | Apache-2.0 |
| Render | FFmpeg **LGPL tanpa** `--enable-gpl`, libass | LGPL-2.1+ / ISC |

**Jebakan yang dilarang masuk build:** Ultralytics YOLO (AGPL-3.0), bobot InsightFace (non-komersial), FFmpeg `--enable-gpl` / libx264 (GPL), LM Studio (non-komersial).

**Kewajiban rilis:** halaman "Third-party notices" + atribusi pyannote CC-BY-4.0 + link source FFmpeg.

---

## 8. Struktur folder

```
clippergod/
  core/
    models.py        Word, Segment, Boundary, Cue, Candidate
    boundaries.py    Semantic Boundary Engine
    captions.py      ASS karaoke + face-aware placement
    scoring.py       VPS + hard gates
    reframe.py       crop path (deadband/EMA/Kalman)
    asr.py           faster-whisper + WhisperX align
    diarize.py       pyannote + binding speaker→face
    render.py        FFmpeg 2-pass
  ui/                (TBD: PySide6 atau Electron)
  config/
    params.toml      semua parameter §5
  tests/
docs/
research/
```

---

## 9. Roadmap

| Fase | Isi | Kriteria terima |
|---|---|---|
| **F1 — Fondasi** | model data, boundary engine, caption engine, VPS, test | Unit test hijau; ASS ter-render benar di libass; batch uji 20 kalimat tidak ada potongan tengah kalimat |
| **F2 — Pipeline nyata** | ASR, align, face track, crop path, render 2 pass | 1 video 60 menit → 10 klip 1080×1920 dengan caption karaoke, <15 menit total |
| **F3 — Cerdas** | diarisasi, speaker timeline, layout engine, hook A/B | Podcast 2 orang: warna caption per speaker benar ≥80% tanpa koreksi |
| **F4 — Poles** | UI/UX, preview libass, batch queue, brand kit | User bisa dari import ke export tanpa buka dokumentasi |
| **F5 — Kalibrasi** | import analytics, refit bobot, clip DNA | ρ ≥0.25 pada 100 klip |

---

## 10. Risiko

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Diarisasi Indonesia lemah (DER 53% preprint) | Warna caption salah | Framing pakai visual ASD; diarisasi hanya untuk warna + UI koreksi; eval set 10–20 klip wajib sebelum F3 |
| Model besar bikin installer 5–8 GB | Distribusi berat | Download model saat first-run (opsional), bundle hanya yang kecil |
| Font tidak tersedia saat render | Caption jatuh ke font default | Bundle font di `fonts/`, `fontsdir` eksplisit di filter libass |
| NVENC tidak ada di mesin user | Export lambat | Fallback OpenH264 (BSD-2), bukan libx264 |
| Sumber VFR (variabel frame rate) | A/V drift | Detect via ffprobe, transcode ke CFR di tahap proxy |

---

## 11. Yang sengaja TIDAK dibuat

- **Auto-post ke sosial media** — butuh server & token; melanggar premis offline.
- **Data tren realtime** — diganti heuristik hook token.
- **Stock b-roll berbayar** — diganti library lokal user.
- **Dubbing TTS kualitas cloud** — opsional nanti, kualitas lokal masih jauh.
- **Skor sebagai "probabilitas viral"** — tidak akan pernah ditampilkan sebagai persentase.
