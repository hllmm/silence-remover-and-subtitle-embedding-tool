# Minimal FFmpeg Build for `modular_app`

Bu klasor, uygulamanin kullandigi FFmpeg yuzey alanina gore daraltilmis bir Windows build akisi icin hazirlandi.

Amac:
- `ffmpeg.exe` ve `ffprobe.exe` disinda gereksiz programlari atmak
- uygulamanin kullandigi codec, filter, muxer ve demuxer setini korumak
- istenirse `NVENC`, `AMF`, `QSV` ve `libx265` gibi daha buyuk parcalari kapatabilmek

## Profil Mantigi

`balanced`:
- onerilen profil
- uygulamanin destekledigi konteynerler ve yaygin codec'ler acik
- `subtitles` filtresi, `libass`, `libx264`, `libmp3lame`, `libvorbis`, `aac`, `flac`, `pcm_s16le` acik
- opsiyonel olarak `NVENC`, `AMF`, `QSV`, `libx265`

`aggressive`:
- daha kucuk build
- decode tarafi daha dar
- girdi dosyalariniz agirlikla `H.264/H.265/AAC/MP3/FLAC/Vorbis/Opus/PCM` ise mantikli

## Neleri Kapsiyor

Bu build, repodaki gercek kullanimlara gore su alanlari hedefler:

- altyazi gommede `subtitles` filtresi ve `SRT` akisi
- sessizlik tespiti icin `silencedetect`
- transkripsiyon oncesi temizleme icin `silenceremove`
- hafif dip ses / cizirti temizligi icin `afftdn`, `anlmdn`, `highpass`, `lowpass`, `adeclick`
- ses/video parcali trim icin `trim`, `atrim`, `setpts`, `asetpts`, `afade`, `concat`
- hizli ses/video birlestirme icin `concat` demuxer ve `mpegts`/`adts`/`mov`/`mp4` muxer'lari
- GPU encoder tespiti icin `lavfi` input ve `color` source

## Gerekli Ortam

1. MSYS2 kurun:

```powershell
winget install -e --id MSYS2.MSYS2
```

2. MSYS2'yi en az bir kez guncelleyin.
`ucrt64.exe` acip:

```bash
pacman -Syu
```

Gerekirse shell'i kapatip ayni komutu bir kez daha calistirin.

## Hizli Kullanim

Onerilen build:

```powershell
powershell -ExecutionPolicy Bypass -File .\modular_app\tools\ffmpeg-minimal\build_ffmpeg_msys2.ps1 `
  -Profile balanced `
  -InstallDeps
```

Daha kucuk, CPU odakli build:

```powershell
powershell -ExecutionPolicy Bypass -File .\modular_app\tools\ffmpeg-minimal\build_ffmpeg_msys2.ps1 `
  -Profile aggressive `
  -EnableNvenc:$false `
  -EnableAmf:$false `
  -EnableQsv:$false `
  -EnableX265:$false `
  -InstallDeps
```

Varsayilan cikti:

```text
modular_app\ffmpeg-custom\<profile>\
```

Bu klasorde sunlar bulunur:
- `ffmpeg.exe`
- `ffprobe.exe`
- gereken DLL'ler
- `ffmpeg-buildconf.txt`
- `ffmpeg-encoders.txt`, `ffmpeg-decoders.txt`, `ffmpeg-filters.txt` ...
- `profile-components.txt`
- `licenses\`

## Parametreler

`-Profile`
- `balanced` veya `aggressive`

`-FFmpegRef`
- varsayilan: `release/7.1`
- ornek: `master`, `n8.0`, belirli commit SHA

`-EnableNvenc`
- NVIDIA encoder'lari ekler

`-EnableAmf`
- AMD AMF encoder'larini ekler

`-EnableQsv`
- Intel Quick Sync encoder'larini ekler

`-EnableX265`
- `libx265` CPU HEVC fallback'ini ekler
- bunu kapatirsan HEVC kaynakta CPU fallback H.264'e donebilir

`-InstallDeps`
- MSYS2 icinde gerekli paketleri `pacman` ile kurar

`-Clean`
- profile ait eski build klasorlerini temizler

## Bu Build'in Bilincli Olarak Tutuldugu Sinirlar

- ag yok: `--disable-network`
- `ffplay` yok
- sadece `ffmpeg` ve `ffprobe` var
- tum codec/filter seti acik degil; uygulamanin kullandigi set acik

Bu yuzden rastgele internet akisi, nadir formatlar veya uygulamada hic kullanilmayan filtreler bu build'de olmayabilir. Bu kasitli.

## Uygulama Ile Kullanma

Uygulama artik su yolu otomatik tercih eder:

```text
modular_app\ffmpeg-custom\balanced\ffmpeg.exe
```

Istersen yine `FFmpeg Yolu` alanindan manuel olarak da gosterebilirsin.

Elle gostermek istersen:

```text
modular_app\ffmpeg-custom\balanced\ffmpeg.exe
```

`ffprobe.exe` ayni klasorde oldugu surece kod mevcut `resolve_ffprobe_path(...)` mantigi ile onu bulur.

## Neden Bu Kadar Genis Ama Hala "Minimal"

Tam agresif bir `--disable-everything` build yapip sadece 3-5 decoder birakmak daha kucuk olurdu, ama bu uygulama:
- kullanicidan gelen farkli MP4/MKV/MOV/AVI dosyalarini aciyor
- ses dosyalarini da isliyor
- hem filter graph hem concat hem subtitle render kullaniyor
- GPU ve CPU fallback'leri birlikte barindiriyor

Bu nedenle burada secilen profil "uygulama-safe minimum" mantigiyla hazirlandi.
