# fonts/

Folder ini dipakai libass saat membakar caption (`ass=...:fontsdir=...`).
`runner.py` mengisinya otomatis kalau folder ini ada.

Kenapa penting: kalau font yang diminta caption tidak ada di sistem, libass
diam-diam memakai font lain — hasilnya beda dari preview dan dari mesin lain.

Cara pakai:

1. Taruh file font (`.ttf`/`.otf`) di folder ini, mis. `Montserrat-ExtraBold.ttf`.
2. Sebut nama keluarganya di config caption, mis. `"font": "Montserrat ExtraBold"`.
3. Kalau nama tidak cocok, `fc-scan`/FontForge bisa memastikan nama keluarga aslinya.

Lisensi font adalah tanggung jawab Anda: jangan menaruh font berbayar di repo.
Montserrat, Inter, dan Open Sans berlisensi OFL (boleh dibundel).
