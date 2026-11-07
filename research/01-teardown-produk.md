# Teardown Produk AI Clipper — Bahan Perbandingan Fitur untuk ClipperGod

**Tanggal riset:** 6 November 2026
**Pertanyaan yang dijawab:** Fitur bernama apa saja yang benar-benar ada di tiap tool clipper, bagaimana mekanisme fitur kuncinya, apa yang unik, apa yang tidak bisa dilakukan, dan berapa harganya?
**Cakupan:** OpusClip, Submagic, CapCut, Klap, Vizard, Descript, 2short.ai, Munch, Reap, Ssemble, HeyGen.
**Batasan:** Semua bukti diambil dari dokumentasi resmi, halaman harga, dan diskusi publik. Tidak ada uji coba akun berbayar. Angka harga mengikuti halaman resmi per tanggal riset dan bisa berbeda per region.

---

## 1. Ringkasan Temuan

1. **Hanya OpusClip yang mempublikasikan komposisi skor viralitasnya** (Hook / Flow / Value / Trend, skala 0–99). Tool lain menyebut "virality score" tanpa mendokumentasikan komponen apa pun — jadi skor mereka tidak bisa direplikasi maupun dibandingkan secara adil.
2. **Auto-reframe di semua tool komersial berporos pada active speaker, bukan pada subjek apa pun.** OpusClip menyebut sinyalnya eksplisit: "voice and motion cues". Untuk objek non-manusia, semuanya jatuh ke tracking manual (klik objek per scene).
3. **Caption per kata bukan fitur terpisah — itu efek samping dari transkrip ber-word-timestamp.** Descript membuktikannya paling telanjang: setiap kata punya boundary start/end yang bisa digeser manual di wordbar, dan menggeser kata menggeser video.
4. **Kelemahan paling konsisten di seluruh kategori: potongan yang tidak koheren** (mulai/berhenti di tengah kalimat, splice acak, konteks hilang). Ini keluhan berulang di Reddit dan alasan utama user tetap melakukan review manual.
5. **Tidak ada satu pun tool yang offline/on-device.** Semua memproses di cloud, semua berbayar per menit/kredit, dan semua menyimpan file user di server mereka. Ini ruang kosong terbesar untuk ClipperGod.

---

## 2. Tabel Perbandingan Fitur (nama persis seperti di produk)

Legend: ✅ ada & dinamai · ◐ ada tapi terbatas/varian · — tidak ada · ? tidak terverifikasi

| Kapabilitas | OpusClip | Submagic | CapCut | Klap | Vizard | Descript | 2short.ai | Munch | Reap | Ssemble | HeyGen |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Auto clip long→short | **AI Clipping**, **AI Copilot** (timeframe/length/topics/prompt) | **Magic Clips**, **Clip Maker** | **Long Video to Shorts**, **AI Highlights**, **AI clip maker** | AI Clipping | AI clipping | **Create clips from your content** | AI video analysis | **Auto-clip projects** | AI Clipping | AI Clipping | — (bukan clipper) |
| Skor viralitas | **Virality Score** (0–99) | — | — | **virality score** | — | — | — | ◐ **real-time keywords analytics** | **AI Virality Score** | — | — |
| Auto reframe / crop | **AI Reframe**, **Reframe Anything** (Alpha), **7 layouts**: Fill/Fit/Split/Three/Four/Screenshare/Gameplay | ◐ crop 9:16 di editor | **Smart Cropping, Resizing and Subject Tracking** | **active-speaker reframing** | **Auto reframe** | ◐ **Speaker framing**, **Center active speaker**, **Automatic Multicam** | **Center stage facial tracking** | **Auto-Crop videos to 9:16** | **Auto speaker detection & tracking**, **Dynamic layout switch** | ? | — |
| Tracking subjek manual | **Subject Tracking** → **Tracker** (klik objek per scene) | — | ◐ **Tracking** (di panel teks/objek) | — | — | ◐ manual di scene editor | ◐ **advanced editing and cropping** | — | — | — | — |
| Caption otomatis | **AI captions** | **AI Auto Captions** | **Auto captions** / **AI captions** | animated captions | **Auto subtitling** | **Automatic transcription** + **Captions** | **One-click animated subtitles** | **Unlimited automated subtitles** | **AI Captions** | ◐ | ◐ (di translator) |
| Preset animasi caption | **Animated caption templates** | **Caption Templates** (Standard vs Premium) | **Caption templates**, **Caption Boost**, **Style captions with AI**, style Glow/Trending/Aesthetic | animated captions | template + **AI emojis** | ◐ style caption terbatas | animated subtitles | — | **50+ animated caption presets** | **viral templates** | — |
| Emoji / keyword highlight | **Auto emoji and keyword highlights** | **animated emojis** | ◐ via text preset | ? | **AI emojis**, **AI highlight keywords** | — | — | — | **AI Emoji insertion**, **AI Keyword highlighting** | — | — |
| Auto zoom | — | **Auto Zoom** (6 gaya, disinkron ke transkrip) | ◐ keyframe manual | — | — | — | — | — | — | — | — |
| B-roll | **AI B-roll** (image/stock/AI video via Agent Opus) | **Magic B-rolls** (Storyblocks) | ◐ stock/template | b-roll di editor | **AI B-rolls** | ◐ stock media | — | — | **AI B-Roll** (stock) | — | — |
| Sound effect / musik | **AI sound effects**, **Add music** (Pro+) | **Sounds Effects**, **Music Background** | ✅ library besar | ? | — | ◐ audio effects | — | — | ◐ stock library | — | — |
| Hapus jeda / filler | **Speech cleanup** (pause & filler), **bad takes** | **Auto Cut**, **AI Remove silences**, **AI Filler words** | ◐ manual | ? | ? | **Filler words**, **Shorten Word Gaps**, **Edit for Clarity** | — | ◐ **Silence removal – SOON** | **AI Filler word removal** (coming soon) | — | — |
| Text-based editing | **Text & timeline-based editing** | ◐ via subtitle | — | — | — | **Edit like a doc** + **wordbar** | — | — | **Transcript-based editing** | — | — |
| Audio enhance | **Speech enhancement** | **AI Clean audio** | ◐ | — | — | **Studio Sound** | — | — | ◐ **Background noise removal** (soon) | — | — |
| Eye contact | **Eye contact correction** (Pro+) | **AI Eye Contact** | — | — | — | **Eye Contact** | — | — | — | — | ◐ avatar |
| Brand kit / template | **Brand template** (1 → 4 → custom), **Intro/outro cards**, **Brand vocabulary** | Custom templates, custom fonts | **Brand kit** (Teams) | — | **Brand templates**, **Brand kit**, custom fonts | **Brand Studio** | **Brand presets** | — | **Brand caption templates**, logo overlay | — | **Brand kit** |
| Dubbing / terjemah | **Video dubbing** (Pro+) | **AI Video Translator** (100+ bahasa) | ◐ | ? | subtitle translation | **Translate & dub** | — | — | 80+ bahasa dubbing | — | **Video Translation** (175 bahasa) |
| Publish / scheduler | Social scheduler, multi-profile | Publishing + analytics | ◐ share | Scheduling + publishing | Schedule post | Export/share | — | — | **Content calendar scheduler**, **AI-suggested posting times** | **Schedule and Post** | — |
| API / otomasi | Video Editing API, Scheduler API, **MCP connector**, Zapier | Video Editing API | — | API (bayar terpisah) | API | API, Zapier, MCP | — | — | REST API, **CLI access**, **MCP-ready** | API, MCP | API |

### Catatan nama fitur yang mudah salah kutip

- OpusClip: **"ClipAnything"** adalah nama model clipping multimodal, bukan nama tombol; tombolnya tetap AI Clipping dengan mode prompt. **"Reframe Anything"** masih berlabel **Alpha** di dokumentasi.
- CapCut: yang benar-benar ada di desktop adalah tab **Text → Auto captions**; **"AI Highlights"** dan **"Long Video to Shorts"** adalah alur terpisah di halaman utama.
- Submagic: tidak ada fitur bernama "sound effect AI" — namanya **"Sounds Effects"**, dan ia hidup di dalam alur **Magic B-rolls**.
- Descript: **"Studio Sound"** dan **"Eye Contact"** keduanya dihitung sebagai **AI Credits** pada plan sekarang, bukan gratis.

---

## 3. Mekanisme di Balik Fitur Kunci

### 3.1 Skor viralitas

**OpusClip — satu-satunya yang terdokumentasi.** Skor 0–99, dihitung dari empat dimensi yang disebut eksplisit:

> "**Hook**: Does the introduction grab attention and directly relate to the main topic of the video? **Flow**: Does the video flow logically from one part to the next, with a satisfying conclusion? **Value**: Does the video offer value, resonate emotionally... **Trend**: Is the video aligned with current trends and audience interests?"
> — help.opus.pro/docs/article/virality-score

Detail operasional yang penting untuk positioning:
- Skor diberikan **per klip**, dan hasil default **diurutkan dari skor tertinggi** — artinya skor berfungsi sebagai ranking, bukan sekadar label.
- Pada mode ClipAnything, ada faktor tambahan: relevansi terhadap prompt user.
- **Tidak tersedia di plan Free**; hanya Starter/Pro. (Dokumentasi menyebut "Pro and Starter", tabel harga menandai Free dengan "-".)
- **Bobot antar dimensi tidak dipublikasikan.** Tidak ada angka, tidak ada model name, tidak ada ambang batas. Ini penting: klaim "AI memprediksi viral" tidak bisa diverifikasi dari luar.

**Klap / Reap — ada skornya, mekanismenya tidak dibuka.**
- Klap: "Every plan includes AI clipping, with a virality score, active-speaker reframing and animated captions" (FAQ harga Klap). Tidak ada halaman mekanisme.
- Reap: menyebut **"AI clipping with multi-signal analysis"** dan **"Genre-specific models — Optimized for Talking Head, Presentation, and Gaming content"**. Ini satu-satunya kompetitor yang menyatakan modelnya dipecah per genre (OpusClip punya "genre-specific reframing model" untuk reframe, bukan untuk scoring).

**Yang tidak ada skornya sama sekali:** Submagic, CapCut, Vizard, 2short.ai, Ssemble. Munch mendekati dengan **"real-time keywords analytics"** dan **"Match generated clips to trends on social media"** — itu analitik kata kunci/volume pencarian, bukan prediksi retensi.

> **Tingkat keyakinan: tinggi** untuk komposisi OpusClip (dokumentasi resmi), **rendah** untuk tool lain (tidak ada dokumentasi; klaim hanya di halaman marketing).

### 3.2 Auto-reframe: bagaimana crop dipilih

Ini bagian yang paling banyak salah dipahami. Yang sebenarnya terjadi di OpusClip:

> "**Automatic Detection:** OpusClip identifies the active speaker using **voice and motion cues**. **Smooth Camera Shifting:** The frame adjusts gradually to follow the speaker's movements, avoiding jarring jumps."
> — help.opus.pro/docs/article/subject-tracking

Jadi pemilihan crop bukan "deteksi wajah lalu tengahkan", melainkan **fusi dua sinyal: siapa yang bicara (audio) + siapa yang bergerak (visual)**, lalu kamera virtual digeser bertahap (bukan cut) agar tidak terlihat seperti lompatan.

Lapisan di atasnya adalah **layout engine**, bukan crop bebas. Tujuh layout OpusClip punya aturan masing-masing:
- **Fill** — speaker di-crop memenuhi 9:16.
- **Fit** — video asli dipotong ke 4:3, sisanya padding opaque atas-bawah.
- **Split** — dua speaker, **hanya jalan kalau keduanya sudah tampil bersamaan di frame asli**.
- **Three / Four** — panel 3–4 speaker, syarat sama (harus tampil bersama di frame asli).
- **Screenshare** — layar di atas, speaker di bawah; kalau screenshare tidak terdeteksi, sistem **jatuh ke layout alternatif**.
- **Gameplay** — rasio tetap **30% speaker di atas, 70% gameplay di bawah**.

Konsekuensi yang jarang disebut: **Split/Three/Four tidak bisa menciptakan sudut kamera yang tidak ada.** Kalau podcast direkam satu frame lebar, layout multi-panel hanya membagi frame itu, bukan memotong per orang.

Tool lain:
- **CapCut** — "auto subject tracking and seamless size adaptation from 16:9 to 9:16"; tracking tersedia sebagai panel **Tracking** yang bisa diatur manual.
- **2short.ai** — **"Center stage facial tracking"**: "Our AI uses facial tracking technology to automatically keep them at the center of the screen." Ini murni facial, **tanpa sinyal audio** — penjelasan mengapa hasilnya lebih goyah pada percakapan dua orang.
- **Descript** — **"Center active speaker"** + **"Automatic Multicam"**; ini yang paling matang untuk multicam karena memang punya track kamera terpisah.
- **Vizard / Reap / Munch / Klap** — menyebut auto reframe / speaker tracking tanpa menjelaskan sinyal.
- **Submagic, Ssemble, HeyGen** — tidak punya auto-reframe berbasis speaker sebagai fitur bernama.

> **Tingkat keyakinan: tinggi** untuk OpusClip dan 2short (dokumentasi eksplisit), **sedang** untuk CapCut/Descript (nama fitur resmi, mekanisme internal tidak dibuka).

### 3.3 Caption di-timing per kata

Mekanisme yang bisa dibuktikan dari dokumentasi:

**Descript — paling transparan.** Transkrip **di-align ke audio per kata**, dan setiap kata punya boundary start/end yang bisa digeser:

> "Descript automatically aligns your transcript with your script audio so that your edits remove only the portion of audio corresponding with a given word... you can make adjustments to its start and end boundaries in the wordbar."
> — help.descript.com/script-editing/the-wordbar

Dan menggeser kata **menggeser video**, bukan hanya teks:
> "Dragging right will extend the word gap and do one of two things: Add a gap clip if the script media is audio-only. **Add a freeze frame if the script media contains video.**"

Ini membuktikan satu hal arsitektural: **caption, transkrip, dan potongan video adalah satu struktur data yang sama**. Bukan tiga lapisan terpisah.

**OpusClip — bukti tidak langsung yang kuat.** Captions Editor bekerja per kata: klik satu kata → edit teks; select beberapa kata → bisa "correct, remove captions only, or **delete both the captions and the video** for the selected words". Perilaku "hapus kata = hapus potongan video" hanya mungkin kalau ada **word-level timestamp** yang dipakai bersama oleh caption dan cut. (help.opus.pro/docs/article/change-captions)

**CapCut — per kata tapi manual-heavy.** Auto captions menghasilkan baris; user mengedit teks/timing di timeline, lalu menambah **Animation** per klip teks. Tidak ada indikasi UI word-level alignment otomatis seperti Descript; gaya "satu kata muncul sekaligus" dicapai lewat preset animasi + pemecahan baris, bukan lewat model timing kata.

**Submagic — timing diturunkan dari baris subtitle.** Auto Zoom "perfectly matching various zoom styles to your transcript" dan "Sync Zooms with Your Transcript" — efek visual dipicu pada **boundary baris transkrip**, bukan pada timestamp kata individual.

> **Inferensi (belum terbukti dari dokumen mana pun):** di semua tool, timestamp kata hampir pasti berasal dari output ASR yang menyertakan word timestamps, bukan dari forced alignment terpisah. Tidak ada vendor yang mempublikasikan model ASR atau metode alignment-nya. **Jangan kutip sebagai fakta.**

### 3.4 Mekanisme lain yang layak dicatat

- **ClipAnything (OpusClip)** — menganalisis **setiap frame** lewat tiga modalitas: visual, audio, sentimen; mengenali objek, scene, aksi, suara, emosi, teks. Tiap scene diberi rating potensi viral, lalu prompt user memfilter. Klaim pembeda: bekerja pada **video tanpa dialog**.
- **Eye Contact (Descript)** — "uses AI to **redirect your gaze to the lens**". Batasan operasional yang diakui sendiri: hanya **satu wajah** dalam frame, wajah harus besar & terang, **tidak jalan pada variable frame rate**, butuh koneksi internet, dan **melewati bagian** di mana subjek menoleh jauh. Ini fitur yang paling jujur mendokumentasikan kegagalannya.
- **Auto Zoom (Submagic)** — 6 gaya zoom, satu tombol, dipasang lewat **Magic B-rolls**; bisa juga ditambah manual per baris subtitle.
- **AI Highlights (CapCut)** — "automatically identify key moments based on **speech patterns**". Jadi sinyalnya audio/transkrip, bukan visual. (capcut.com/tools/long-video-to-shorts)

---

## 4. Fitur Pembeda (hanya satu tool yang punya)

| Fitur | Tool | Kenapa sulit ditiru |
|---|---|---|
| **ClipAnything** — clipping multimodal dengan prompt, jalan di video tanpa dialog | OpusClip | Butuh video-understanding per frame (bukan cuma ASR); kompetitor semua berbasis transkrip |
| **Virality Score yang komponennya dipublikasikan** (Hook/Flow/Value/Trend) | OpusClip | Bukan teknologinya yang sulit, tapi keberanian mendokumentasikan — dan itu jadi alat marketing |
| **Reframe Anything (Alpha)** — tracking objek non-manusia otomatis | OpusClip | Umumnya masih manual; ini yang paling dekat "auto" untuk objek |
| **7 layout siap pakai** termasuk Screenshare & Gameplay 30/70 | OpusClip | Layout engine + deteksi screenshare; lainnya hanya crop atau split sederhana |
| **Wordbar** — boundary per kata yang bisa digeser, menggeser video | Descript | Butuh model data unified transcript+timeline; arsitektur termahal untuk dibangun |
| **Edit like a doc** — hapus teks = hapus video | Descript | Sama seperti di atas; ini inti produk, bukan fitur tambahan |
| **Studio Sound** | Descript | Enhancement audio kelas produksi, bukan noise gate |
| **Regenerate / Smooth jump cuts** — memperbaiki audio di titik potong | Descript | Unik; tidak ada kompetitor yang mengisi celah audio antar cut |
| **Long Video to Shorts + AI Highlights** sebagai alur native di app editor | CapCut | Gratis, terintegrasi ke editor yang sudah dipakai 100 juta+ orang |
| **Caption Boost / Style captions with AI** | CapCut | Ekosistem preset & font terbesar; efek teks jadi moat, bukan AI-nya |
| **6 gaya Auto Zoom tersinkron transkrip** | Submagic | Detail kecil yang menghasilkan "rasa" editing manusia |
| **AI Actors** (aktor AI di dalam video) | Submagic | Arah produk berbeda: bukan clipper, tapi short-form studio |
| **Romanized script support** (Hinglish, Arabizi, Roman Urdu) | Reap | Sangat spesifik pasar Asia Selatan/Timur Tengah; tidak ada kompetitor yang menyebut ini |
| **CLI access + MCP-ready + on-device TTS voiceover** | Reap | Paling "developer-first" di kategori ini |
| **Wajib caption yang sudah ada** (batasan, bukan fitur) | 2short.ai | Model bisnis termurah karena tidak membayar ASR sendiri |
| **Video Translation 175 bahasa + avatar** | HeyGen | Bukan clipper; ini yang paling jauh dari kategori dan justru menunjukkan batas kategori |

---

## 5. Gap & Keluhan User (yang TIDAK bisa dilakukan tool ini)

### 5.1 Keluhan struktural (berulang, lintas tool)

**a) Potongan tidak koheren — keluhan nomor satu.**

Dari r/podcasting (thread "How do yall feel about opus clips?", 2023, masih dikomentari sampai 2026):
> "I tried it, and I hate it. It's pretty good at giving me ideas of which parts of my episode I should use, but I'm always like **you didn't use the good parts** it always cuts out the funny or important parts. Some of the score descriptions say oh it lacks consistency and a clear explanation of the story, and I'm like **YOU SKIPPED THE EXPLANATION!!!**"

> "It will randomly **splice pieces of an episode together that make zero sense**." — komentar di thread yang sama

> "terrible, i paid for a year, ive barely used 3 videos after they edited over 100, **literally all errors all bad edits, random corner angles**, just awful" — komentar di thread yang sama

Dari r/editors (thread "Are these 'easy-edit' apps actually useful?"):
> "I used Opusclip for the first time yesterday... **they were wildly all over the place** for many of the moments identified. Ended up going back into the raw and just cutting it all from my multiclip."

Review pihak ketiga mengonfirmasi pola yang sama secara kuantitatif:
> "10 were unusable (**cut mid-sentence, missed punchline, or the clip itself was about a topic the AI misread**)." — scalereach.ai/blog/opus-clip-review (Mei 2026)

**Implikasi produk:** masalahnya bukan akurasi transkrip, tapi **pemahaman batas semantik** (di mana sebuah ide mulai dan selesai). Ini yang belum dipecahkan siapa pun dan justru peluang terdiferensiasi.

**b) Wajah/objek rusak saat reframe.**
> "I tried both munch and opus, neither got the results I wanted, **faces of my guests were being messed up by their AI**." — r/podcasting

Review independen menyebut kasus spesifik: "Chaotic multi-speaker **crosstalk confuses the reframing, which chases the wrong face** or cuts a thought mid-sentence." — academy.techpresso.co (Juli 2026)

**c) Edit hasil AI tetap harus diperbaiki manual.**
> "now that it removes filler words and pauses, **it does not do a great job at it. I still have to actually fix those edits**." — OP r/podcasting, setelah berlangganan

**d) Caption aneh / tidak bisa dikontrol sepenuhnya.**
> "The captions are weird, but if you look at the captions of other successful shorts, they are also suspiciously weird, so." — OP r/podcasting

**e) Output AI terasa generik.**
> "all Descript videos have a similar feeling, so they're not going to stand out in the public eye." — r/editors
> "**There's no such thing as a truly one-click solution...YET.**" — r/editors

**f) B-roll tidak konsisten antar platform.**
> "when I add AI B Roll sometimes **the B roll doesn't show up on tik tok but does on yt shorts**." — r/podcasting

### 5.2 Batasan keras yang diakui dokumentasi resmi

Ini bukan keluhan user — ini dinyatakan vendor sendiri, jadi paling bisa dipercaya:

| Batasan | Tool | Sumber |
|---|---|---|
| Split/Three/Four **hanya jalan jika semua speaker sudah tampil bersamaan di frame asli** | OpusClip | layout-and-reframing |
| Screenshare layout **jatuh ke layout lain** kalau screenshare tidak terdeteksi | OpusClip | layout-and-reframing |
| Caption yang sudah **burned-in tidak bisa dihapus** | OpusClip | change-captions |
| **Tidak bisa** memproses video dengan **variable frame rate**; gagal pada **lebih dari satu orang**; **butuh online** | Descript Eye Contact | eye-contact |
| Eye Contact **melewati bagian** saat subjek menoleh jauh / keluar frame | Descript Eye Contact | eye-contact |
| **Hanya bisa memproses video yang sudah punya caption** | 2short.ai | FAQ pricing |
| **Maksimal 20 menit segmen** per input video | Ssemble | FAQ pricing |
| **Silence removal belum ada** — ditandai "SOON" | Munch | pricing |
| **Filler word removal & noise removal masih "Coming soon"** | Reap | pricing |
| Video **Web** harus **< 20 menit** | CapCut | resource subtitle |
| **Harus online**; file disimpan di server (3–29 hari tergantung plan) | OpusClip | pricing |

### 5.3 Gap yang tidak dilakukan siapa pun (peluang ClipperGod)

1. **Offline / on-device.** Tidak ada satu pun dari 11 tool yang menjalankan ASR + clipping sepenuhnya di mesin user. Descript punya aplikasi desktop, tapi transkripsi dan AI-nya tetap butuh koneksi (didokumentasikan di syarat Eye Contact: "requires a network connection"). Semua menagih per menit/kredit sumber dan menyimpan master video di server mereka.
2. **Biaya per menit yang tidak naik.** Model kredit (1 kredit = 1 menit sumber di OpusClip/Vizard; 1 kredit = 1 video 20 menit di Ssemble) membuat biaya naik linear terhadap panjang podcast. Aplikasi desktop tidak punya struktur biaya itu.
3. **Kontrol batas potongan.** Tidak ada tool yang membiarkan user menentukan aturan "jangan pernah potong di tengah kalimat" secara eksplisit — semuanya output AI + edit manual.
4. **Layout multi-kamera sejati.** OpusClip butuh semua speaker sudah dalam satu frame. Tidak ada yang melakukan multicam sync + auto-switch untuk rekaman kamera terpisah, kecuali Descript lewat Automatic Multicam.
5. **Konsistensi gaya antar output.** Brand template ada, tapi tidak ada yang menjamin hook, pacing, dan caption style konsisten lintas 50 klip.

---

## 6. Harga & Batasan Tier (posisi pasar per 6 Nov 2026)

| Tool | Free | Entry | Mid | Top | Unit biaya | Catatan penting |
|---|---|---|---|---|---|---|
| **OpusClip** | $0, 60 kredit/bln, watermark, hanya 9:16, tanpa virality score | **Starter $15/bln** (150 kredit) | **Pro $29/bln** (~$14.50/bln annual, 300 kredit, 2 seat) | Enterprise (custom) | 1 kredit ≈ 1 menit sumber | Virality score, eye contact, dubbing, AI sound effects, brand template 4× = **Pro+**. Free/Starter hanya 1 template. Export Free dibatasi 3 hari |
| **Submagic** | — (tanpa CC) | Starter (15 video/bln, **maks 2 menit/video**, 1080p) | **Pro $40/bln** (40 video, 5 menit/video, 2K) | **Business $120/bln** (100 video, 30 menit, 4K/60fps) | per video/bulan | Custom font & custom vocabulary **hanya Business**; eye contact & AI Actors **bukan** di Starter |
| **CapCut** | Gratis (editor penuh) | **Pro SGD 23.48/bln** | Ultra SGD 100.98/bln | Teams SGD 11.74/seat | kredit AI + langganan | Harga terregionalisasi — yang terbaca versi SGD, nominal IDR berbeda. Auto captions tersedia di Free (lihat konflik data §7.4). Ini baseline gratis kategori |
| **Klap** | 1 video trial, tanpa download | **Basic $29/bln** ($14.50 annual, 100 klip) | **Pro $79/bln** ($39.50, 300 klip) | **Pro+ $189/bln** ($94.50, 1.000 klip) | per klip | Durasi sumber **sampai 3 jam**; virality score + active-speaker reframe di **semua** plan berbayar; API terpisah ($0.44/video, $0.32/short) |
| **Vizard** | 60 kredit/bln, 720p, 3 hari storage | Creator (7.200–74.400 kredit/thn) | Business (seat + brand kit) | Custom | **1 kredit = 1 menit** | Harga dolar tidak ter-render di halaman (JS dinamis) — **belum terverifikasi**. Free: upload 60 menit, 1 GB |
| **Descript** | Free (watermark, menit terbatas) | Hobbyist | Creator | Business/Enterprise | Media minutes + **AI Credits** | Eye Contact & Studio Sound **memotong AI Credits**; export dibatasi kuota menit |
| **2short.ai** | 30 menit analisis/bln | **Lite $9.90/bln** (5 jam) | **Pro $19.90/bln** (15 jam) | **Premium $49.90/bln** (50 jam) | per jam analisis | **Semua fitur terbuka di semua plan** — yang dibedakan hanya jam. Termurah di kategori ini |
| **Munch** | ada (fitur dibatasi) | Pro (auto-clip 100 menit) | — | Enterprise (quotation) | per menit upload | **Harga dolar tidak ter-render** — belum terverifikasi. Silence removal masih "SOON" |
| **Reap** | $0, 1 jam, watermark, 720p | **Creator $9.99/bln** (10 jam, 1080p) | **Studio $29/bln** (20 jam, 4K, 3 user) | Enterprise | per jam sumber | API + CLI + MCP di **semua plan berbayar** — pembeda terkuat |
| **Ssemble** | ada | **Pro $6/bln** ($72/thn, 360 kredit) | **Expert $12/bln** ($144/thn, 840) | **Business $24/bln**, Custom $40 | 1 kredit = 1 video (20 menit) | Termurah per video; **maks 20 menit segmen**; kredit **tidak roll over** |
| **HeyGen** | $0, 3 video, watermark, 1 menit | **Creator $29/bln** (600 kredit, 1080p) | **Pro $49/bln** (1.000 kredit, 4K, 30 menit) | **Business $149/bln** | kredit | Bukan clipper; harga dicantumkan untuk konteks bahwa "video AI" di segmen ini berharga $29–149 |

**Pola harga yang perlu dicatat:**
- **Rentang pasar clipper: $6–$40/bulan.** Ssemble di bawah, Submagic di atas. OpusClip $15–29 adalah anchor pasar.
- **Semua model berbasis volume sumber** (menit atau klip), bukan berbasis fitur — kecuali Submagic yang membatasi **durasi per video** (2 menit di Starter). Itu pembatas paling menyakitkan di kategori ini.
- **Fitur "mahal" (eye contact, dubbing, brand template, custom font) sengaja dikunci di tier atas** — pola konsisten di OpusClip, Submagic, Reap.

---

## 7. Konflik Data yang Ditemukan (jangan diam-diam dipilih salah satu)

1. **Jumlah bahasa Submagic.** Halaman auto-zoom: "**48+ supported languages**". Halaman utama & AI caption: "**123 languages**". Dua klaim di situs yang sama. Kemungkinan besar 48 = bahasa caption, 123 = bahasa dengan kualitas penuh/translation, tapi tidak ada penjelasan resmi.
2. **Batas segmen Ssemble.** FAQ menulis "you can select up to a **20-minute** segment", lalu contoh di kalimat berikutnya: "if you have a 60-minute original video, you can select a maximum **10-minute** segment". **Kontradiksi internal** di satu jawaban FAQ.
3. **Fitur OpusClip di Free.** Tabel harga menandai beberapa fitur dengan ikon centang di kolom Free padahal dokumentasi lain menyebut fitur tersebut hanya untuk plan berbayar (mis. virality score). Tabel harga kemungkinan tidak konsisten per komponen.
4. **CapCut: auto caption gratis atau berbayar?** Halaman resource menyatakan auto captions tersedia di semua platform tanpa menyebut paywall; halaman pricing menjual "AI features" sebagai keunggulan Pro. **Tidak ada pernyataan eksplisit** bahwa Auto captions gratis. Jangan klaim salah satu arah tanpa uji langsung.

---

## 8. Yang Belum Terverifikasi (jangan dipakai sebagai fakta)

- **Harga Munch dan Vizard dalam dolar.** Kedua halaman merender harga via JS; yang tertangkap hanya struktur plan. Perlu browser atau cek checkout.
- **Mekanisme virality score Klap, Reap, Munch.** Tidak ada dokumentasi. Hanya nama fitur.
- **Sinyal apa yang dipakai CapCut/Vizard/Reap untuk auto-reframe.** Tidak dibuka.
- **Apakah semua vendor memakai ASR dengan word timestamps** atau forced alignment terpisah. Tidak ada yang mempublikasikan. (Bagian 3.3 sudah ditandai inferensi.)
- **Kualitas output sebenarnya.** Semua bukti di dokumen ini adalah dokumentasi + persepsi user, **bukan hasil uji**. Perbandingan kualitas butuh uji dengan video yang sama di semua tool.
- **Submagic: jumlah & nama preset caption.** Halaman harga hanya membedakan "Standard" vs "Premium"; nama preset individual tidak terdaftar di halaman publik yang diakses.

---

## 9. Daftar Sumber (25 URL, semuanya diakses 6 Nov 2026)

**Dokumentasi resmi — OpusClip**
1. https://help.opus.pro/docs/article/virality-score — komposisi Virality Score (Hook/Flow/Value/Trend), skala 0–99, akses Starter/Pro.
2. https://help.opus.pro/docs/article/9947095-clip-anything — ClipAnything: analisis per frame (visual/audio/sentimen), rating per scene, prompt, Reframe Anything (Alpha).
3. https://help.opus.pro/docs/article/layout-and-reframing — 7 layout + aturan masing-masing (Fill/Fit/Split/Three/Four/Screenshare/Gameplay 30:70).
4. https://help.opus.pro/docs/article/subject-tracking — active speaker via "voice and motion cues", manual Tracker untuk objek non-manusia.
5. https://help.opus.pro/docs/article/change-captions — editor caption per kata; hapus kata = hapus video; caption burned-in tidak bisa dihapus.
6. https://www.opus.pro/pricing — matriks fitur per tier (virality, eye contact, dubbing, brand template, batas export).

**Dokumentasi resmi — Submagic**
7. https://www.submagic.co/pricing — tier & batas (15/40/100 video, 2/5/30 menit per video, 1080p/2K/4K).
8. https://www.submagic.co/features/auto-zooms — Auto Zoom 6 gaya, disinkron ke transkrip, lewat Magic B-rolls.

**Dokumentasi resmi — CapCut**
9. https://www.capcut.com/resource/how-to-add-subtitle-in-capcut — alur Auto captions desktop/web/mobile, Caption Boost, Style captions with AI, batas 20 menit di Web.
10. https://www.capcut.com/tools/long-video-to-shorts — Long Video to Shorts, AI Highlights ("based on speech patterns"), Smart Cropping + Subject Tracking.
11. https://www.capcut.com/pricing — harga Pro/Ultra/Teams (SGD), free tier.

**Dokumentasi resmi — Descript**
12. https://help.descript.com/effects-animations-transitions/eye-contact — Eye Contact: redirect gaze, batasan (1 wajah, VFR, online, skip).
13. https://help.descript.com/script-editing/the-wordbar — alignment per kata, boundary editable, drag kata → freeze frame.

**Halaman harga — tool lain**
14. https://klap.app/pricing/ — $29/$79/$189; 100/300/1.000 klip; 3 jam sumber; API terpisah.
15. https://vizard.ai/pricing — model kredit (1 kredit = 1 menit), 60 kredit free, fitur per plan (auto reframe, AI emoji, brand kit).
16. https://2short.ai/pricing — $9.90/$19.90/$49.90; syarat "hanya video yang sudah punya caption".
17. https://www.getmunch.com/pricing — auto-clip 100 menit, auto-crop 9:16, silence removal "SOON".
18. https://reap.video/pricing — $9.99/$29; multi-signal analysis, genre models, romanized script, CLI/MCP.
19. https://www.ssemble.com/pricing — $6/$12/$24/$40; 1 kredit = 1 video 20 menit; batas segmen.
20. https://www.heygen.com/pricing — $29/$49/$149; 175 bahasa; konteks segmen avatar/translation.

**Diskusi & review (bukti keluhan)**
21. https://www.reddit.com/r/podcasting/comments/14zzbpk/how_do_yall_feel_about_opus_clips — kutipan: potongan acak, wajah rusak, filler removal masih manual, B-roll hilang di TikTok.
22. https://www.reddit.com/r/editors/comments/1m6bt2b/are_these_easyedit_apps_actually_useful_or_just — kutipan: "wildly all over the place", output Descript terasa seragam, "no such thing as a truly one-click solution".
23. https://www.scalereach.ai/blog/opus-clip-review — review pihak ketiga: 10 dari sampel klip tidak terpakai (cut mid-sentence, punchline hilang). **Sekunder.**
24. https://academy.techpresso.co/reviews/is-opus-clip-worth-it — review: crosstalk membuat reframe mengejar wajah salah. **Sekunder.**
25. https://quso.ai/blog/opus-clip-pricing — angka harga OpusClip (Free 60 kredit, Starter $15/150, Pro $29). **Sekunder**, dipakai karena tabel resmi tidak merender harga.

---

## 10. Implikasi untuk ClipperGod (ringkas, untuk diskusi lanjutan)

Tiga hal yang paling menentukan dari teardown ini:

1. **Menang di batas potongan, bukan di skor.** Semua kompetitor kalah di keluhan yang sama: klip mulai/berhenti di tempat yang salah. Skor viralitas yang tidak transparan tidak menyelesaikan itu. Aturan deterministik yang bisa dilihat user ("jangan potong di tengah kalimat", "selesaikan ide") lebih bernilai daripada skor 0–99.
2. **Caption = transkrip = timeline.** Bukti Descript menunjukkan ini keputusan arsitektur, bukan fitur. Kalau ClipperGod menyimpan tiga struktur terpisah, setiap perbaikan caption akan berantakan.
3. **Offline adalah positioning, bukan sekadar fitur.** Semua 11 tool memproses di cloud dan menagih per menit. Desktop offline menghapus dua keberatan sekaligus (biaya per menit & privasi) — dan itu tidak bisa ditiru kompetitor tanpa membongkar model bisnis mereka.

---

*Dokumen ini bukti-first: setiap klaim mekanisme punya URL, dan setiap inferensi ditandai. Bagian 7 dan 8 sengaja mempertahankan ketidakpastian daripada merapikannya.*
