# Sains Hook & Viralitas Short Video
### Dasar bukti untuk fitur scoring ClipperGod

**Status:** riset literatur + data platform, dikumpulkan 6 November 2026
**Ruang lingkup:** TikTok, Instagram Reels, YouTube Shorts (format 9:16 vertikal)
**Pertanyaan yang dijawab:** apa yang secara empiris membuat short video bertahan ditonton dan menyebar, dan parameter apa yang bisa langsung dipakai sebagai aturan algoritma?

---

## 1. Ringkasan eksekutif

**Tingkat keyakinan keseluruhan: sedang-tinggi untuk struktur retensi, rendah untuk taksonomi hook dan prediksi viralitas.**

1. **Gerbang 3 detik itu nyata, tapi angka "40–65% drop" yang beredar tidak punya sumber.** Satu-satunya data skala besar yang bisa ditelusuri berasal dari Meta (2016): **65% orang yang menonton 3 detik pertama bertahan sampai 10 detik, dan 45% sampai 30 detik** [S1]. Itu berarti sekitar **35% hilang di 0–3 detik** — bukan 65%.
2. **Kurva retensi berbentuk nose–body–tail.** Drop terbesar ada di awal ("nose", ~2% durasi pertama), lalu turun landai, lalu ada infleksi di akhir [S16]. Memotong durasi menaikkan persentase tonton: satu video dipotong dari 5'51" ke 2'33" menaikkan average percentage viewed dari **16% ke 42%** [S16].
3. **Pacing punya titik optimum, bukan "makin cepat makin baik".** 50 TikTok talking-head terbaik berdurasi rata-rata **0,37 cut/detik (≈22 cut/menit)**, rentang 0,13–0,82 cut/s (≈8–49 cut/menit) [S13]. Eksperimen N=242 menunjukkan pacing tinggi justru **menurunkan** sustained engagement [S13].
4. **Caption punya standar angka yang jelas** (warisan subtitle broadcast): maksimum **2 baris**, **20 CPS** untuk dewasa, **160–180 wpm** [S9][S10]. Standar 42 karakter/baris berasal dari frame 16:9; untuk 9:16 dipakai **32 karakter/baris**. Efek caption terhadap watch time: **+12%** (tes internal Meta) [S1].
5. **Prediksi viralitas dari konten saja lemah.** Korelasi skor kualitas visual dengan average watch time hanya **0,084–0,290** [S17]. Pola view di hari-hari pertama jauh lebih kuat daripada fitur visual [S18]. Tidak ada model publik yang layak disebut "prediktor viralitas" dari konten mentah.

**Implikasi utama untuk ClipperGod:** bangun **ranking heuristic yang bisa dikalibrasi**, bukan "viral probability". Skor harus dinyatakan sebagai *potensi* (0–100) dengan komponen yang bisa diaudit, lalu dilatih ulang memakai analytics milik user.

---

## 2. Metode dan grading bukti

Setiap klaim diberi tingkat bukti:

| Tingkat | Definisi | Contoh dalam dokumen ini |
|---|---|---|
| **T1** | Dokumentasi resmi platform atau paper peer-reviewed | YouTube Help, Instagram Help, Netflix TTSG, CHI 2024, JOBEM 2000 |
| **T2** | Data skala besar dari industri, metodologi dilaporkan | Meta internal tests, studi 3,3 miliar views, Socialinsider 40,7 juta video |
| **T3** | Blog praktisi / vendor, angka tanpa metodologi terbuka | Klaim "hook X menaikkan retensi 23%" |

Aturan yang dipakai: **T3 tidak pernah dipakai sebagai dasar parameter**, hanya sebagai hipotesis yang ditandai. Kalau dua sumber bertingkat sama berkonflik, konfliknya ditulis, bukan diratakan.

Catatan penting: tidak ada platform yang mempublikasikan kurva retensi agregat atau bobot algoritmanya. Semua angka retensi di bawah ini adalah **proksi**, bukan kebenaran internal platform.

---

## 3. Hook 3 detik pertama

### 3.1 Apa yang benar-benar terukur

Data terbaik yang tersedia publik adalah funnel 3 detik Meta:

| Titik | Persentase penonton yang bertahan | Sumber |
|---|---|---|
| Menonton 3 detik pertama | 100% (basis) | [S1] |
| Bertahan sampai 10 detik | **65%** | [S1] |
| Bertahan sampai 30 detik | **45%** | [S1] |

Dari sini: **~35% hilang antara 0–3 detik**, lalu **~31% dari sisanya** hilang antara 10–30 detik. Perhatikan bahwa drop terbesar tetap di jendela awal, tetapi tidak sebesar yang diklaim blog-blog.

Meta juga mengukur nilai iklan, bukan retensi murni: **hingga 47% nilai kampanye video tersampaikan dalam 3 detik pertama, dan 74% dalam 10 detik pertama** [S1]. Angka ini sering dikutip sebagai "3 detik menentukan segalanya"; yang sebenarnya diukur adalah *ad recall/brand lift*, bukan watch-through. Konteksnya iklan mobile 2016, bukan TikTok organik 2026.

### 3.2 Taksonomi hook: mana yang punya bukti

Taksonomi populer (pertanyaan, kontradiksi, angka, ancaman, curiosity gap) **tidak punya studi retensi per-tipe yang dipublikasikan**. Yang bisa dipertanggungjawabkan hanya lapisan psikologisnya:

| Tipe hook | Dasar teoritis | Bukti retensi | Status |
|---|---|---|---|
| **Curiosity gap** | Information-gap theory: rasa penasaran muncul saat perhatian terfokus pada celah pengetahuan [S23] | Tidak ada angka per-tipe | **T1 untuk teori, tanpa data retensi** |
| **Pertanyaan** | Memaksa retrieval/active processing | Klaim "+23% retensi" dari vendor, tanpa dataset [T3] | **T3, jangan dipakai sebagai bobot** |
| **Kontradiksi / negasi** | Prediction error memicu orienting response; dipakai sebagai micro-disruption di [S13] | Ada efek pada sustained engagement, tapi bukan khusus hook | **T2 tidak langsung** |
| **Angka / listicle** | Chunking & expectancy | Tidak ditemukan studi | **Tidak terverifikasi** |
| **Ancaman / loss** | Negativity bias (literatur umum) | Tidak ditemukan studi short-video | **Tidak terverifikasi** |
| **Pattern interrupt visual** | Motion onset captures attention; cut menaikkan arousal [S14] | Ada: cut pada awal menaikkan liking [S13] | **T1/T2** |

**Kesimpulan jujur:** taksonomi hook adalah folklore industri yang dibungkus teori psikologi. Yang bisa dipakai ClipperGod bukan "tipe hook mana yang viral", melainkan **proksi struktural**: apakah ada gerakan di frame pertama, apakah suara mulai <0,3 detik, apakah ada kata pemicu (tanya/angka/negasi/kata ganti "kamu"), dan apakah ada perubahan visual dalam 1,5 detik.

### 3.3 Jendela 3 detik sebagai gerbang, bukan takdir

Snap (90.000 video, 10–60 detik) memakai metrik **ECR = P(watch > 5 detik)** khusus untuk mengukur "kemampuan video menahan penonton di awal" [S17]. Ini pengakuan implisit dari platform bahwa **5 detik pertama** adalah unit analisis yang lebih stabil daripada 3 detik. Untuk ClipperGod, artinya: ukur hook pada **0–3 detik**, tapi evaluasi keberhasilannya pada **5 detik**.

Data CHI 2024 memperkuat bahwa gerbang awal bukan segalanya: **55% video yang direkomendasikan TikTok tidak ditonton sampai habis, dan sebagian besar di-skip sebelum setengah durasi** [S11]. Jadi bahkan video yang lolos 3 detik masih bisa mati di tengah.

---

## 4. Kurva retensi, loop, dan durasi

### 4.1 Bentuk kurva: nose–body–tail

Altman & Jimenez (2019) menganalisis retensi YouTube dan merumuskan tiga segmen [S16]:

- **Nose** — kira-kira **2% durasi pertama** video. Di sini terjadi "large drop in engagement at the very beginning".
- **Body** — penurunan landai sepanjang tengah.
- **Tail** — infleksi lain di akhir (penonton keluar saat credits/outro).

Mereka juga mendokumentasikan anomali penting: **retensi YouTube bisa melebihi 100%** karena penonton menarik ulang ke awal dan menonton lagi [S16]. Ini bukti langsung bahwa replay/loop bukan mitos — ia terlihat di data platform.

**Contoh angka yang bisa dipakai sebagai jangkar:** video 5'51" dipotong menjadi 2'33" menaikkan average percentage viewed dari **16% → 42%**, dan average viewed duration naik 2,625× [S16]. Ini bukan bukti kausal murni (kontennya juga berubah), tapi arahnya konsisten dengan argumen "durasi lebih pendek menaikkan completion".

### 4.2 Durasi vs completion: data yang saling bertentangan

| Sumber | Temuan | Konteks |
|---|---|---|
| Meta [S1] | 45% penonton 3 detik bertahan sampai 30 detik | Iklan feed, 2016 |
| Studi 3,3 miliar views [S12] | Shorts dengan average view duration **>50 detik** menghasilkan rata-rata **4,1 juta views** | 5.400 Shorts, 33 channel |
| Socialinsider [S19][S19b] | TikTok **~2 menit** paling tinggi engagement & views; Reels **60–90 detik** paling tinggi | 40,7 juta video TikTok [S19b] |
| Opus.pro [T3] | 21–34 detik completion terbaik (62% vs 48% untuk >60 detik) | Vendor, metodologi tidak terbuka |
| CHI 2024 [S11] | 55% rekomendasi tidak ditonton habis | 9,2 juta view, 347 user |

**Cara membaca konflik ini:** engagement rate (like/comment/share per view) dan completion rate adalah metrik berbeda dengan optimum berbeda. Video 2 menit bisa menang di engagement karena memberi ruang cerita, sementara video 21–34 detik menang di completion. **Jangan satukan menjadi satu target durasi.** Untuk ClipperGod, sediakan mode: `reach` (21–34 s), `watch_time` (35–60 s), `story` (60–90 s).

Yang jelas dari [S12]: bukan durasi absolut yang menang, tapi **average view duration absolut**. Shorts >50 detik rata-rata menghasilkan 4,1 juta views — masuk akal karena total detik tonton lebih besar.

### 4.3 Loop dan replay

Bukti yang ada:

- Instagram menghitung **setiap play dan replay** sebagai view; loop menambah hitungan [S20b, T3, konsisten dengan dokumentasi Meta tentang "views" sebagai play/replay].
- YouTube retention bisa >100% karena rewatch [S16].
- TikTok memutar video berulang secara default (loop), sehingga akhir video menyambung ke awal; [S13] mengukur **rewatch** sebagai bagian dari sustained engagement.
- Eksperimen [S13] mengukur **rewatch** sebagai bagian dari sustained engagement, dan menemukan bahwa overlapping cuts pada pace rendah menaikkan completion/rewatch.

**Yang tidak ada:** koefisien publik "loop menaikkan reach sebesar X%". Klaim seperti itu tidak bisa diverifikasi. Yang bisa dioperasionalkan: **seam end-to-start** (frame terakhir mirip frame pertama) menurunkan biaya kognitif saat loop, dan **hindari outro/CTA panjang** karena tail adalah titik drop.

---

## 5. Pacing: cut, shot length, zoom, silence

### 5.1 Benchmark cut rate (data lapangan)

Dost & Huang (2026) mengambil 50 TikTok talking-head berperforma tinggi, mendeteksi scene boundary dengan PySceneDetect, dan mendapat [S13]:

- **Mean: 0,37 cut/detik** (SD 0,17) → **≈22 cut/menit**
- **Range: 0,13–0,82 cut/s** → **≈8–49 cut/menit**
- Persentil 16/50/84: **0,189 / 0,331 / 0,517 cut/s** → **≈11 / 20 / 31 cut/menit**

Ini angka paling konkret yang tersedia untuk "cuts per minute ideal" di short-form. Perhatikan: ini **deskriptif** (video yang sudah sukses), bukan eksperimen.

### 5.2 Eksperimen: lebih cepat ≠ lebih baik

Eksperimen 2×3 + control, N=242, video talking-head 20 detik yang sama, hanya gaya cut dan frekuensi yang diubah [S13]:

| Kondisi | Efek pada likes (interactive) | Efek pada completion/rewatch (sustained) |
|---|---|---|
| Seamless cut (buang silence, kontinuitas terjaga), medium | **+0,829** (p<0,001) | tidak signifikan |
| Seamless cut, high | **+0,843** (p<0,001) | tidak signifikan |
| Overlapping cut (audio overlap, disrupsi), low | tidak signifikan | **+1,396** (p<0,001) |
| Overlapping cut, medium | tidak signifikan | **+1,602** (p<0,001) |
| Overlapping cut, high | tidak signifikan | +0,329 (tidak signifikan) |

Skala 7 poin. R² = 0,125 untuk likes dan 0,243 untuk sustained engagement [S13].

**Tiga kesimpulan operasional:**
1. **Silence removal (seamless cut) menaikkan likes** — tapi hanya kalau frekuensinya minimal medium. Memotong silence terlalu jarang tidak berpengaruh.
2. **Disrupsi kecil (overlap) menaikkan completion hanya pada pace rendah–medium.** Di pace tinggi, keunggulannya hilang.
3. **Pacing tinggi menurunkan sustained engagement secara keseluruhan.** "Makin banyak cut makin viral" salah.

### 5.3 Zoom / jump cut / punch-in

Tidak ada studi yang mengisolasi efek "punch-in zoom" terhadap retensi. Yang ada: jump cut sebagai kategori (di atas), dan literatur film yang menunjukkan shot length menurun serta motion meningkat selama 75 tahun, dengan argumen bahwa sutradara makin mengontrol atensi penonton [S15]. **Zoom punch-in harus diperlakukan sebagai hipotesis desain, bukan parameter terbukti.** Rekomendasi: pakai sebagai *pattern interrupt* setiap 3–5 detik, tapi jangan pernah melebihi cut rate tinggi di [S13].

### 5.4 Hubungan dengan teori beban kognitif

Lang et al. (2000) menemukan bahwa **meningkatnya rate of edits menaikkan physiological arousal, self-reported arousal, dan memory** [S14]. Judul papernya sendiri bertanya "can an edit be too much?" — dan literatur berikutnya (dikutip [S13]) memakai model limited-capacity: setiap cut memakan sumber daya pemrosesan, sehingga manfaatnya punya plafon. Ini menjelaskan kenapa data lapangan menunjukkan optimum, bukan monoton naik.

---

## 6. Caption: kecepatan baca, safe zone, dampak

### 6.1 Standar angka yang bisa langsung dipakai

| Parameter | Nilai | Sumber |
|---|---|---|
| Maksimum baris | **2 baris** | [S8][S9] |
| Maksimum karakter/baris | **42 karakter** | [S9] |
| Reading speed dewasa | **20 CPS** (ceiling) | [S9] |
| Reading speed anak | **17 CPS** | [S9] |
| Kecepatan kata (broadcast) | **160–180 wpm** | [S10] |
| Durasi minimum per cue | **5/6 detik = 0,833 s** | [S8] |
| Durasi maksimum per cue | **7 detik** | [S8] |

Catatan penting: 42 karakter/baris adalah standar **subtitle film 16:9**, bukan caption 9:16. Pada frame 1080×1920 dengan margin aman, lebar teks efektif lebih sempit; **32–36 karakter/baris** lebih realistis. Angka 20 CPS adalah batas atas keterbacaan, bukan target; untuk caption bergaya CapCut yang muncul-hilang, **12–18 CPS** lebih aman.

Konversi ke kata: Bahasa Indonesia rata-rata ~5,5 karakter/kata (termasuk spasi). 20 CPS ≈ **3,6 kata/detik**; 160–180 wpm ≈ **2,7–3,0 kata/detik**. Untuk caption 1 baris, **3–5 kata** adalah rentang yang konsisten dengan keduanya.

### 6.2 Dampak caption pada watch time

Satu angka yang bisa dipertanggungjawabkan: **captioned video ads menaikkan video view time rata-rata 12%** (tes internal Meta) [S1]. Satu anekdot dari studi yang sama: A&W Canada melaporkan **+25% watch time** setelah menambahkan caption [S1].

Konteks yang membuat caption masuk akal:
- **41% video iklan di Facebook "basically meaningless without sound"** [S1].
- **80% orang bereaksi negatif** saat video mobile autoplay bersuara keras [S1].

Artinya caption bukan sekadar aksesibilitas; ia adalah **jalur komunikasi utama saat sound-off**. Tapi hati-hati: +12% itu iklan, bukan TikTok organik. Tidak ada studi independen yang mengukur efek caption pada retensi TikTok.

### 6.3 Safe zone

**Meta (resmi):** untuk 9:16 di Stories/Reels/Feed, jaga tepi atas, bawah, dan samping tetap bebas dari elemen penting; untuk disclaimer di Reels ads, sisakan **40% bagian bawah** kosong [S2]. Konversi yang dipakai industri: **atas 14% (270 px), bawah 35% (672 px), samping 6% (65 px)** pada 1080×1920 [S20].

**TikTok:** TikTok Ads Help menyatakan elemen kunci "must be within the safe zone or they may be covered or cropped", tapi **tidak mempublikasikan angka piksel** [S24]. Pengukuran pihak ketiga berkonflik:

| Sumber | Atas | Bawah | Samping |
|---|---|---|---|
| sprites.ai [T3] | 130 px | 484 px | 44 kiri / 140 kanan |
| blitzreels [T3] | 240 px | 660 px | 120 px |
| getkoro [T3] | 130 px | 484 px | 140 kanan |

**Rekomendasi konservatif ClipperGod:** irisan aman semua platform pada 1080×1920 adalah **x = 120–960 (840 px), y = 270–1260 (990 px)**. Kotak ini aman untuk TikTok, Reels, dan Shorts sekaligus. Jangan menaruh caption di luar kotak itu.

---

## 7. Audio

### 7.1 Loudness normalization

Tidak ada platform short-form yang mempublikasikan target LUFS resmi. Yang tersedia adalah target platform musik/video panjang:

| Platform | Playback level | Perilaku | Sumber |
|---|---|---|---|
| YouTube | **-14 LUFS** | turn down only | [S21][S22] |
| Spotify (default) | **-14 LUFS** | turn down & up | [S21][S22] |
| Apple Music | **-16 LUFS** | turn down & up | [S21][S22] |
| TIDAL / Amazon / Deezer | -14 / -14 / -15 LUFS | turn down only | [S21] |
| TikTok / Instagram Reels | **tidak dipublikasikan** | — | [S21] |

Bukti tambahan: **-1 dBTP** adalah ceiling yang disarankan karena encoding lossy (AAC) bisa menaikkan true peak [S21]. Spotify bahkan merekomendasikan **-2 dBTP** untuk master yang lebih keras dari -14 LUFS [S21].

**Untuk ClipperGod:** target **-14 LUFS integrated, true peak ≤ -1 dBTP** adalah pilihan paling defensible — bukan karena TikTok mempublikasikannya, tapi karena itu level normalisasi YouTube/Spotify dan konvensi produksi yang paling luas. Tandai di UI sebagai "standar industri", bukan "spesifikasi TikTok".

### 7.2 Musik bed dan SFX

Tidak ada angka publik tentang rasio voice:music yang optimal untuk short-form. Praktik yang bisa dipertahankan: **voice -16 s/d -14 LUFS, music bed -24 s/d -18 LUFS** (≈ -6 s/d -10 dB di bawah voice), ducking saat speech. Ini konvensi mix, bukan temuan eksperimen — beri label demikian di dokumen produk.

Yang **ada** buktinya: sound-off viewing tinggi (41% video tak bermakna tanpa suara) dan reaksi negatif terhadap audio keras [S1]. Konsekuensinya: **jangan mengandalkan audio saja untuk menyampaikan hook**; caption dan teks di layar harus membawa pesan yang sama.

---

## 8. Prediksi viralitas otomatis: seberapa akurat?

### 8.1 Bukti bahwa fitur visual lemah

SnapUGC (90.000 video Snapchat, 10–60 detik, >2.000 views per video) menguji korelasi skor kualitas visual (VQA) dengan average watch time, dipecah per kelompok durasi [S17]:

| Kelompok durasi | Korelasi MOS vs average watch time |
|---|---|
| 19–21 s | **0,084** |
| 29–31 s | **0,156** |
| 39–41 s | **0,290** |
| 49–51 s | **0,289** |

Korelasinya sangat rendah. Artinya: **video yang "terlihat bagus" tidak otomatis ditonton lama.** Paper yang sama memperkenalkan dua metrik yang lebih stabil: **NAWP** (normalized average watch percentage) dan **ECR** = P(watch > 5 s); keduanya berdistribusi bimodal — penonton cenderung skip cepat, atau menonton relatif lama [S17].

### 8.2 Sinyal mana yang paling prediktif

| Sinyal | Kekuatan | Bukti |
|---|---|---|
| **View/like awal (early dynamics)** | Paling kuat | Model early-view menurunkan relative squared error hingga **20%** vs baseline, terutama untuk video dengan lonjakan awal lalu turun tajam [S18] |
| **Fitur sosial** (creator/follower) | Diduga kuat, tidak diuji di sesi ini | Tidak ada pengukuran langsung yang dikutip |
| **Fitur visual/konten** | Lemah–sedang | Korelasi 0,08–0,29 [S17] |
| **Metadata** (durasi, hashtag, waktu posting) | Sedang | Dipakai sebagai fitur di [S25] dan [S26] |
| **Audio/musik** | Belum terkuantifikasi | Dimasukkan sebagai fitur multimodal, tapi tidak ada effect size publik |

Paper multimodal terbaru (INFORMS 2024 Data Challenge) memang melaporkan peningkatan akurasi dengan menggabungkan video, audio, teks, dan metadata [S25][S26], tetapi **tidak ada satu pun yang melaporkan akurasi level "memprediksi viral" dengan validasi out-of-sample yang bisa direplikasi**. Klaim AUC 0,9+ di blog vendor harus dicurigai.

### 8.3 Kesimpulan yang jujur

**Tidak ada model publik yang bisa memprediksi viralitas dari konten mentah dengan akurasi yang layak dipercaya.** Yang bisa dilakukan:
- Memprediksi **engagement relatif** dalam satu niche/akun (lebih mudah, karena varians konteks dikurangi).
- Memberi **skor heuristik** yang berkorelasi moderat dengan retensi.
- Menggunakan **early signals** setelah publish (bukan sebelum) untuk memutuskan iterasi.

Untuk ClipperGod: jangan menjual "viral probability". Jual **"potential score"** dengan komponen yang bisa dijelaskan, dan kalibrasi ke data user.

---

## 9. Spesifikasi teknis platform (per November 2026)

| Parameter | TikTok | Instagram Reels | YouTube Shorts |
|---|---|---|---|
| Rasio | 9:16 | 1,91:1 – 9:16 (9:16 disarankan) | 9:16 atau 1:1 |
| Resolusi | 1080×1920 | 1080×1920, min 720 px | 1080×1920 |
| Durasi maks | **60 menit upload** / 10 menit rekam in-app [S7] | **20 menit** in-app; **>3 menit tidak direkomendasikan ke audiens baru** [S6] | **3 menit** (upload ≥ 15 Okt 2024) [S3] |
| Frame rate | 30 fps umum | min **30 fps** [S5] | 30/60 fps |
| Format | MP4/MOV, H.264, AAC | MP4/MOV | MP4, H.264 High Profile, 4:2:0, AAC-LC 48 kHz [S4] |
| Bitrate video | tidak dipublikasikan | tidak dipublikasikan | **8 Mbps** (1080p 24–30 fps), **12 Mbps** (48–60 fps) [S4] |
| Bitrate audio | tidak dipublikasikan | tidak dipublikasikan | **384 kbps stereo** [S4] |
| Safe zone | tidak dipublikasikan (lihat §6.3) | atas 14% / bawah 35% / samping 6% [S2][S20] | aman di kotak yang sama |
| Catatan | — | Reels >3 menit tidak direkomendasikan ke audiens baru [S6] | Shorts >1 menit + Content ID claim = blokir global [S3] |

**Rekomendasi export ClipperGod:** 1080×1920, 30 fps, H.264 High Profile, 4:2:0, AAC 48 kHz 320–384 kbps, video **10–12 Mbps VBR**, GOP = setengah frame rate, `moov` atom di depan (fast start), audio **-14 LUFS / -1 dBTP**.

---

## 10. Tabel konflik dan hal yang belum terbukti

| Klaim populer | Status | Penjelasan |
|---|---|---|
| "40–65% penonton drop di 3 detik pertama" | **Tidak terverifikasi** | Tidak ada sumber primer. Meta [S1] mengimplikasikan ~35%. |
| "Hook pertanyaan menaikkan retensi 23%" | **Tidak terverifikasi** | Klaim vendor [T3], tanpa dataset. |
| "Caption menaikkan watch time 12%" | **Terverifikasi, konteks iklan** | Tes internal Meta 2016 [S1], bukan TikTok organik. |
| "Cut setiap 2–3 detik selalu lebih baik" | **Bertentangan dengan bukti** | [S13] menunjukkan pacing tinggi menurunkan sustained engagement. |
| "Video 21–34 detik paling viral" | **Sebagian** | Benar untuk completion, tidak untuk total watch time [S12][S19]. |
| "TikTok menormalkan audio ke -14 LUFS" | **Tidak terverifikasi** | Tidak dipublikasikan; -14 adalah konvensi [S21]. |
| "Safe zone TikTok = 130/484 px" | **Berkonflik** | Pengukuran pihak ketiga berbeda (130/484 vs 240/660) [T3]. |
| "Model AI bisa prediksi viral dengan akurasi 90%" | **Tidak didukung** | Korelasi fitur visual 0,08–0,29 [S17]; early dynamics lebih kuat [S18]. |

---

## 11. Daftar sumber

**S1.** Meta Business News, *Capture Attention with Updated Features for Video Ads* (2016). https://www.facebook.com/business/news/updated-features-for-video-ads — 65% penonton 3 s bertahan ke 10 s; 45% ke 30 s; 47% nilai di 3 s pertama; caption +12% view time; 41% video tak bermakna tanpa suara; 80% reaksi negatif pada audio keras.

**S2.** Meta Business Help, *About text overlays and the safe zone for ads in Stories and Reels*. https://www.facebook.com/business/help/980593475366490 — tepi 9:16 harus bebas elemen penting; disclaimer: 40% bawah kosong.

**S3.** YouTube Help, *Understand three-minute YouTube Shorts*. https://support.google.com/youtube/answer/15424877 — Shorts ≤3 menit untuk upload ≥15 Okt 2024; Shorts >1 menit dengan claim diblokir global.

**S4.** YouTube Help, *YouTube recommended upload encoding settings*. https://support.google.com/youtube/answer/1722171 — H.264 High Profile, 4:2:0, AAC-LC 48 kHz; 1080p 8 Mbps (24–30 fps) / 12 Mbps (48–60 fps); audio stereo 384 kbps.

**S5.** Instagram Help, *Reel size & aspect ratios*. https://help.instagram.com/1038071743007909 — rasio 1,91:1–9:16; min 30 fps; min resolusi 720 px.

**S6.** Instagram Help, *How do I record an Instagram Reel?* https://help.instagram.com/2720958398006062 — rekam/edit hingga 20 menit; Reels >3 menit tidak direkomendasikan ke audiens baru.

**S7.** TikTok Support, *Camera tools*. https://support.tiktok.com/en/using-tiktok/creating-videos/camera-tools — rekam ≤10 menit; upload ≤60 menit.

**S8.** Netflix Partner Help, *Timed Text Style Guide: General Requirements*. https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617 — durasi min 5/6 s, max 7 s; maksimum 2 baris.

**S9.** Netflix Partner Help, *English (USA) Timed Text Style Guide*. https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977 — 42 karakter/baris; 20 CPS dewasa; 17 CPS anak; maks 2 baris.

**S10.** BBC, *Subtitle Guidelines* v1.2.5 (Maret 2026). https://www.bbc.co.uk/accessibility/forproducts/guides/subtitles — 160–180 wpm; ~10% penonton broadcast memakai subtitle rutin, hingga 35% untuk sebagian konten online; panduan 9:16 ditambahkan.

**S11.** Zannettou et al., *Analyzing User Engagement with TikTok's Short Format Video Recommendations using Data Donations*, CHI 2024, arXiv:2301.04945. https://arxiv.org/abs/2301.04945 — 347 user, 9,2 juta rekomendasi; attention stabil ~45%; 55% video tidak ditonton habis; mayoritas skip sebelum setengah.

**S12.** A. Lacombled, *Cracking the YouTube Shorts Algorithm: A Study of 3.3 Billion Views* (Medium, 2023). https://medium.com/@antoinelacombled/cracking-the-youtube-shorts-algorithm-a-study-of-3-3-billion-views-4711fdf7931b — 5.400 Shorts, 33 channel; avg view duration >50 s → 4,1 juta views; VVSA <60% perform buruk, 70–90% lebih baik.

**S13.** F. Dost & Y. Huang, *Jump Cut Editing Style and Transition Frequency Differentially Affect Interactive and Sustained Engagement in Short-Form Video*, Marketing Trends Congress 2026. https://archives.marketing-trends-congress.com/2026/pages/PDF/paper_professor_DOST_HUANG.pdf — 50 TikTok, mean 0,37 cut/s (0,13–0,82); eksperimen N=242; seamless +0,829/+0,843 likes; overlapping +1,396/+1,602 sustained; pacing tinggi menurunkan sustained; R² 0,125/0,243.

**S14.** A. Lang, S. Zhou, N. Schwartz, P. D. Bolls, R. F. Potter, *The Effects of Edits on Arousal, Attention, and Memory for Television Messages*, JOBEM 44(1):94–109, 2000. https://doi.org/10.1207/s15506878jobem4401_7 — rate of edits menaikkan arousal, attention, dan memory.

**S15.** J. E. Cutting et al., *Quicker, Faster, Darker: Changes in Hollywood Film over 75 Years*, i-Perception 2(6):569–576, 2011. https://journals.sagepub.com/doi/10.1068/i0441aap — 160 film 1935–2010; shot length menurun; motion meningkat; durasi shot pendek punya motion lebih tinggi; tujuannya mengontrol atensi.

**S16.** E. Altman & T. Jimenez, *Measuring Audience Retention in YouTube*, VALUETOOLS 2019. https://inria.hal.science/hal-02053300 — nose (2% awal) – body – tail; retensi bisa >100% karena rewatch; pemotongan 5'51" → 2'33" menaikkan APV 16% → 42%.

**S17.** D. Li et al., *Delving Deep into Engagement Prediction of Short Videos*, arXiv:2410.00289 (2024). https://arxiv.org/html/2410.00289v1 — 90.000 video Snapchat 10–60 s; korelasi MOS vs average watch time 0,084–0,290; metrik NAWP dan ECR = P(watch >5 s).

**S18.** H. Pinto, J. M. Almeida, M. A. Gonçalves, *Using Early View Patterns to Predict the Popularity of YouTube Videos*, WSDM 2013. https://dl.acm.org/doi/10.1145/2433396.2433443 — model early-view menurunkan relative squared error hingga 20%.

**S19.** Socialinsider, *Social Media Video Statistics* (2026). https://www.socialinsider.io/social-media-benchmarks/social-media-video-statistics — Reels 60–90 s paling tinggi engagement & views; TikTok ~2 menit paling tinggi.

**S19b.** Socialinsider, *2026 TikTok Benchmarks*. https://www.socialinsider.io/social-media-benchmarks/tiktok — TikTok engagement rate by views 4,20% (2025), analisis 40,7 juta video.

**S20.** Sprout Social, *Social Media Video Specs Guide* (16 Oktober 2026). https://sproutsocial.com/insights/social-media-video-specs-guide — tabel spesifikasi; Meta safe zone 14%/35%/6% = 270/672/65 px pada 1080×1920; Reels 20 menit (3 menit untuk reach); Shorts 3 menit.

**S20b.** Instagram/Meta, *Views* counting — setiap play dan replay dihitung sebagai view (diringkas di Sprout Social dan liputan industri). https://www.socialpilot.co/instagram-marketing/instagram-views-metrics-changes

**S21.** MeterPlugs, *Streaming Loudness* (Oktober 2026). https://www.meterplugs.com/blog/streaming-loudness.html — YouTube -14 LUFS turn-down-only; Spotify -14; Apple -16; -1 dBTP; Spotify -2 dBTP untuk master >-14 LUFS.

**S22.** iZotope, *Mastering for Streaming Platforms*. https://www.izotope.com/community/blog/mastering-for-streaming-platforms — tabel reference level; 87% user Spotify tidak mengubah default -14 LUFS.

**S23.** G. Loewenstein, *The Psychology of Curiosity: A Review and Reinterpretation*, Psychological Bulletin 116(1):75–98, 1994. https://www.cmu.edu/dietrich/sds/docs/loewenstein/PsychofCuriosity.pdf — information-gap theory.

**S24.** TikTok Ads Help, *Specifications for TikTok Interactive add-on: Download Card*. https://ads.tiktok.com/resources/help/article/tiktok-interactive-add-on-download-card-ad-specifications — elemen kunci harus di dalam safe zone atau akan terpotong/tertutup.

**S25.** J. Lu et al., *Multi-modal and Metadata Capture Model for Micro Video Popularity Prediction*, arXiv:2502.17038 (2025). https://arxiv.org/abs/2502.17038 — model 3M menggabungkan video, audio, deskripsi, dan metadata; peserta INFORMS 2024 Data Mining Challenge; melaporkan peningkatan akurasi vs baseline tag-based, tanpa angka validasi independen di abstract.

**S26.** H. Liu et al., *Multi-Modal Video Feature Extraction for Popularity Prediction*, arXiv:2501.01422 (2025). https://arxiv.org/abs/2501.01422 — prediksi view/like/comment/share dari fitur video, caption, hashtag, durasi, frame count, frame rate, dan time online; peserta INFORMS 2024 Data Challenge.

> Catatan akses: semua URL diakses 6 November 2026. Angka dari blog pihak ketiga (T3) ditandai di teks dan tidak dipakai sebagai bobot final.

---

## 12. Implikasi untuk fitur ClipperGod

Bagian ini menerjemahkan temuan menjadi **parameter yang bisa langsung masuk kode**. Yang bertanda **[BUKTI]** berasal dari sumber T1/T2; yang bertanda **[HIPOTESIS]** adalah pilihan desain yang harus dikalibrasi.

### 12.1 Arsitektur skor

**Nama di UI:** *Viral Potential Score* (VPS), 0–100 — label Indonesia: **"Skor Potensi Viral"**. Jangan sebut "probability".

```
VPS = 0.30*H + 0.20*R + 0.15*C + 0.15*A + 0.10*L + 0.10*P
```

Bobot awal ini **[HIPOTESIS]** — belum ada studi yang memvalidasi weighting. Simpan di config, bukan hard-code, supaya bisa dilatih ulang.

**Hard gates** (kalau gagal, VPS di-cap maksimum 40, apa pun skornya):
- Tidak ada speech onset di 0,6 detik pertama.
- Caption keluar dari safe box.
- Audio clipping (true peak > 0 dBTP) atau integrated loudness < -20 LUFS.
- Durasi < 8 detik (tidak cukup untuk loop/cerita).

### 12.2 Parameter hook (H)

| Parameter | Nilai | Status |
|---|---|---|
| `hook_window_start` | 0,0 s | [BUKTI] Meta [S1] |
| `hook_window_end` | 3,0 s | [BUKTI] Meta [S1] |
| `hook_eval_point` | 5,0 s | [BUKTI] ECR Snap [S17] |
| `speech_onset_max` | 0,30 s | [HIPOTESIS] |
| `dead_air_head_max` | 0,25 s | [HIPOTESIS] |
| `first_motion_required` | ya, dalam 0,5 s | [BUKTI tidak langsung] Cutting [S15] |
| `visual_change_within` | 1,5 s | [HIPOTESIS] |
| `greeting_blacklist` | "hai", "guys", "jadi", "oke", "selamat datang" | [HIPOTESIS] |
| `hook_token_bonus` | tanda tanya, angka, negasi ("jangan", "salah", "berhenti", "bukan"), "kamu" | [HIPOTESIS] |

**Komposisi H (0–100):**

| Komponen | Bobot |
|---|---|
| Speech onset ≤0,30 s | 20 |
| Gerakan/optical flow di frame pertama | 15 |
| Wajah terdeteksi di frame pertama | 10 |
| Hook token dalam 12 kata pertama | 25 |
| Tidak ada greeting/intro | 15 |
| Perubahan visual dalam 1,5 s | 15 |

### 12.3 Parameter retensi & pacing (R)

| Parameter | Nilai | Status |
|---|---|---|
| `cuts_per_min_target` | **15–30** | [BUKTI] 0,37 cut/s ≈ 22/menit [S13] |
| `cuts_per_min_soft_cap` | **40** | [BUKTI] batas atas 0,82 cut/s ≈ 49, tapi pacing tinggi menurunkan sustained [S13] |
| `cuts_per_min_floor` | **10** | [BUKTI] persentil 16 = 0,189 cut/s [S13] |
| `median_shot_length` | **1,8–4,0 s** | [BUKTI tidak langsung] turunan cut rate |
| `silence_remove_threshold` | **-35 dBFS**, min silence **0,35 s** | [HIPOTESIS] |
| `silence_remove_style` | seamless (pertahankan kontinuitas) | [BUKTI] seamless ↑likes [S13] |
| `punch_in_interval` | 3–5 s | [HIPOTESIS] |
| `punch_in_scale` | 1,08–1,20× | [HIPOTESIS] |
| `overlap_cut_allowed` | hanya kalau cut rate < 25/menit | [BUKTI] overlapping hanya menang di low/medium pace [S13] |

**Fungsi skor R:**

```
if 15 <= cpm <= 30: R_pace = 100
elif 30 < cpm <= 40: R_pace = 100 - (cpm-30)*4      # turun ke 60
elif cpm > 40: R_pace = max(0, 60 - (cpm-40)*3)
elif 10 <= cpm < 15: R_pace = 70 + (cpm-10)*6        # 70→100
else: R_pace = max(0, cpm*7)                          # <10 terlalu statis
```

Tambahan penalti: gap >0,6 s di tengah speech (-10 per gap, maks -30); shot >6 s tanpa gerakan (-15).

### 12.4 Parameter caption (C)

| Parameter | Nilai | Status |
|---|---|---|
| `caption_max_lines` | **2** | [BUKTI] Netflix [S8][S9] |
| `caption_max_chars_per_line` | **32** (9:16), 42 untuk 16:9 | [BUKTI]+[HIPOTESIS] 42 = standar 16:9 [S9]; 32 = adaptasi lebar 9:16 |
| `caption_max_cps` | **18** (target 12–16) | [BUKTI] ceiling 20 CPS [S9] |
| `caption_min_duration` | **0,83 s** | [BUKTI] Netflix 5/6 s [S8] |
| `caption_max_duration` | **1,8 s** (short-form), 7 s untuk subtitle film | [BUKTI]/[HIPOTESIS] |
| `caption_words_per_line` | **3–5 kata** | [BUKTI tidak langsung] 160–180 wpm [S10] |
| `caption_safe_box` | **x 120–960, y 270–1260** (1080×1920) | [BUKTI] Meta 14/35/6% [S2][S20] |
| `caption_font_min_height` | **48 px** pada 1080 lebar | [HIPOTESIS] |
| `caption_highlight` | 1–3 kata per cue | [HIPOTESIS] |

**Aturan layout:** caption harus berada di dalam safe box, tidak menutup wajah (face bbox), dan tidak menabrak UI platform. Kalau wajah berada di zona caption, geser caption ke atas/bawah, jangan perkecil font di bawah 48 px.

### 12.5 Parameter audio (A)

| Parameter | Nilai | Status |
|---|---|---|
| `target_lufs` | **-14 LUFS** integrated | [BUKTI konvensi] YouTube/Spotify [S21][S22] |
| `true_peak_max` | **-1 dBTP** | [BUKTI] [S21] |
| `voice_lufs` | -16 s/d -14 | [HIPOTESIS] |
| `music_bed_lufs` | -24 s/d -18 | [HIPOTESIS] |
| `voice_to_music_min` | **6 dB** | [HIPOTESIS] |
| `ducking` | -6 dB saat speech | [HIPOTESIS] |
| `silence_gate` | -40 dBFS | [HIPOTESIS] |

Skor A: 100 jika -15 ≤ LUFS ≤ -13 dan TP ≤ -1; turun 10 per 1 LUFS di luar rentang; 0 jika clipping. Kurva penalti ini **[HIPOTESIS]**.

### 12.6 Parameter loop & ending (L)

| Parameter | Nilai | Status |
|---|---|---|
| `loop_similarity` | SSIM frame terakhir vs pertama **> 0,60** | [HIPOTESIS] |
| `outro_max` | **1,5 s** | [HIPOTESIS] |
| `end_card_max` | 5% durasi | [HIPOTESIS] |
| `last_frame_hold` | ≤0,5 s | [HIPOTESIS] |

Dasar: tail adalah titik drop [S16]; replay dihitung sebagai view [S20b]; rewatch masuk metrik sustain [S13].

### 12.7 Parameter platform (P)

| Parameter | Nilai | Status |
|---|---|---|
| `resolution` | 1080×1920 | [BUKTI] [S3][S5][S20] |
| `aspect` | 9:16 | [BUKTI] |
| `fps` | 30 | [BUKTI] min 30 [S5] |
| `video_bitrate` | **8 Mbps minimum, 10–12 Mbps disarankan** | [BUKTI] YouTube 8/12 Mbps [S4] |
| `audio_bitrate` | 320–384 kbps AAC, 48 kHz | [BUKTI] [S4] |
| `pix_fmt` | yuv420p | [BUKTI] [S4] |
| `profile` | High, GOP = fps/2 | [BUKTI] [S4] |
| `faststart` | ya | [BUKTI] [S4] |
| `dur_reach` | 21–34 s | [T2] konflik, lihat §4.2 |
| `dur_watch` | 35–60 s | [T2] [S12] |
| `dur_story` | 60–90 s | [T2] [S19] |
| `dur_hard_max` | 180 s (Shorts) | [BUKTI] [S3] |

### 12.8 Aturan keputusan praktis (bisa langsung ditulis ke spec)

1. **Hook window = 0–3 s; evaluasi di 5 s.** Kalau speech belum mulai pada 0,6 s → tolak klip.
2. **Cut rate target 15–30 cut/menit, hard cap 40.** Jangan pernah "percepat karena terlihat membosankan"; percepat hanya kalau cut rate < 15.
3. **Buang silence ≥0,35 s dengan gaya seamless.** Jangan tambah overlap kalau cut rate sudah >25/menit.
4. **Caption maks 2 baris, 32 karakter/baris, 3–5 kata, 12–18 CPS, durasi 0,83–1,8 s.**
5. **Caption safe box x 120–960, y 270–1260.** Di luar itu = hard fail.
6. **Target audio -14 LUFS, true peak -1 dBTP; voice ≥6 dB di atas music bed.**
7. **Pilih durasi sesuai tujuan:** reach 21–34 s, watch time 35–60 s, story 60–90 s. Jangan campur.
8. **Loop seam:** akhir harus menyambung ke awal (SSIM >0,60); outro ≤1,5 s.
9. **Jangan tampilkan "viral probability".** Tampilkan VPS + alasan per komponen ("hook 82: speech mulai 0,2 s, ada pertanyaan, ada gerakan").
10. **Kalibrasi:** simpan VPS + analytics user (watch time, completion, replay). Hitung Spearman per komponen. Target realistis: **ρ 0,25–0,40** untuk iterasi awal; di atas 0,50 baru boleh disebut "prediktif".

### 12.9 Yang harus diukur ulang setelah 100–300 klip

- Bobot H/R/C/A/L/P (mulai dari 30/20/15/15/10/10, refit dengan regresi ridge).
- Ambang `punch_in_scale` dan interval.
- Apakah hook token benar-benar prediktif di niche user (mungkin tidak).
- Apakah `loop_similarity` berkorelasi dengan replay rate.
- Apakah durasi optimal user berbeda dari benchmark global.

**Metode kalibrasi minimal:** kumpulkan minimal 100 klip dengan VPS dan metrik aktual; hitung korelasi Spearman; kalau ρ < 0,2, skor belum layak ditampilkan sebagai angka tunggal — tampilkan sebagai checklist saja.

---

## 13. Batasan riset ini

1. **Tidak ada akses ke data internal platform.** Semua angka retensi adalah proksi dari studi pihak ketiga atau data iklan.
2. **Sebagian besar bukti retensi berasal dari 2016–2024.** Platform berubah; angka Meta 2016 mungkin tidak lagi sama persis.
3. **Tidak ada studi per-tipe hook.** Taksonomi di §3.2 adalah kerangka teori, bukan hasil validasi.
4. **Konflik durasi belum terselesaikan.** Engagement vs completion memang punya optimum berbeda; jangan dipaksa satu angka.
5. **Loudness TikTok/Reels tidak dipublikasikan.** -14 LUFS adalah konvensi, bukan spesifikasi resmi.
6. **Safe zone TikTok hanya dari pengukuran pihak ketiga** dan angkanya berkonflik.
7. **Effect size music/SFX tidak ditemukan.** Parameter di §12.5 adalah konvensi mix.

---

*Dokumen ini disusun untuk pengambilan keputusan produk, bukan publikasi akademik. Setiap parameter bertanda [HIPOTESIS] wajib dikalibrasi sebelum dipakai sebagai klaim pemasaran.*
