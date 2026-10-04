# PandaMirror20
PandaMirror 20 Windows Android multi-mirror prototype

## Status project
Proyek ini adalah iterasi fungsional yang dirancang untuk Windows 10 64-bit, dengan struktur GUI utama dan logic mirroring Android via ADB + scrcpy. Fitur inti yang sudah ada di source version ini mencakup:
- deteksi perangkat Android via ADB,
- kontrol per device (pilih, mirror, stop),
- grid multi-device dalam satu jendela,
- pilihan resolusi dan FPS,
- status koneksi, leader selection,
- starter build Windows via PyInstaller,
- mekanisme pengiriman input leader ke follower menggunakan adb shell input.

## Catatan penting
- Ini belum final hardware-validated untuk 20 HP secara real-time. Pengujian yang benar-benar meyakinkan hanya bisa dilakukan di mesin Windows dengan perangkat Android fisik nyata.
- Untuk kualitas input dan keandalan di banyak device sekaligus, diperlukan uji pada hardware nyata untuk menyesuaikan resolusi, durasi swipe, dan delay forwarding.
- Build final EXE disarankan memakai mesin Windows 10 64-bit dan folder tools yang memuat `platform-tools/adb.exe` serta `scrcpy/scrcpy.exe`.

## Struktur folder yang dibutuhkan
Taruh file berikut di folder proyek:
- `tools/platform-tools/adb.exe`
- `tools/scrcpy/scrcpy.exe` dan file pendukungnya

## Menjalankan source
Windows:
```
py -3 -m pip install -r requirements.txt
py -3 main.py
```

## Build Windows
```
build_windows.bat
```
Hasil build tersedia di `dist/PandaMirror20/`.

## Catatan distribusi
Build yang bersifat `onedir` adalah pilihan yang paling aman karena ADB dan scrcpy tetap perlu file DLL/native pendukungnya. Jika Anda ingin versi yang benar-benar final dan dapat didownload sebagai EXE siap pakai, build perlu dijalankan di mesin Windows 10 64-bit dengan perangkat Android yang siap diuji.
