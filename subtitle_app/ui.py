"""Tkinter application shell for the subtitle workflow."""

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from dotenv import dotenv_values

from .core import (
    AUDIO_ONLY_EXTENSIONS,
    VIDEO_TRIM_ENCODING_PROFILES,
    apply_padding_to_silence_intervals,
    build_audio_filter_graph,
    build_av_filter_graph,
    calculate_auto_speech_protection,
    calculate_speech_protection_profile,
    build_fast_video_copy_plan,
    condense_keep_intervals,
    create_ffmpeg_safe_output_path,
    detect_silence_intervals,
    fast_trim_audio_with_stream_copy,
    fast_trim_video_with_stream_copy,
    finalize_ffmpeg_output_path,
    get_audio_cleanup_filter_chain,
    get_fast_audio_copy_profile,
    get_media_duration,
    get_media_stream_info,
    invert_intervals,
    merge_close_intervals,
    optimize_intervals_for_fast_audio_copy,
    resolve_ffmpeg_path,
    resolve_ffprobe_path,
    should_use_fast_audio_concat,
    split_intervals_into_batches,
    snap_numeric_value,
    write_ffmpeg_concat_list,
    _normalize_codec_name,
)
from .embedding import SubtitleEmbedder
from .fonts import FontSettings, FontSettingsWindow, SimplePreviewWindow
from .transcription import VideoTranscriber
from .translation import SRTConverter, SRTTranslator

SILENCE_THRESHOLD_STEP = 0.5
SILENCE_DURATION_STEP = 0.05
SPEECH_PROTECTION_STEP = 0.05
SPEECH_PROTECTION_AUTO_MIN = 0.20
SPEECH_PROTECTION_AUTO_MAX = 0.70
SPEECH_PROTECTION_MANUAL_MIN = 0.10
SPEECH_PROTECTION_MANUAL_MAX = 1.00
API_ENV_KEYS = ("GROQ_API_KEY", "OPENROUTER_API_KEY")
UI_LANGUAGE_OPTIONS = {
    'tr': 'Türkçe',
    'en': 'English',
}
UI_TEXTS = {
    'tr': {
        'window_title': "🎬 SSR&SET",
        'header_title': "🎬 SSR&SET",
        'tab_main': "📝 Ana İşlemler",
        'tab_font': "🎨 Yazı Tipi",
        'tab_silence': "🔇 Sessizlik Budama",
        'tab_settings': "⚙️ Ayarlar",
        'tab_help': "❓ Yardım",
        'status_ready': "✅ Hazır",
        'ready_short': "Hazır",
        'missing_short': "Eksik",
        'font_tab_title': " 🎨 Mevcut Yazı Tipi Ayarları ",
        'font_edit': "✏️ Düzenle",
        'font_preview': "👁️ Önizleme",
        'font_save_as': "💾 Farklı Kaydet",
        'font_load': "📂 Yükle",
        'font_info': "ℹ️ Font ayarları otomatik olarak kaydediliyor\n📁 Konum: {path}",
        'menu_file': "📁 Dosya",
        'menu_open_video': "🎥 Video Aç",
        'menu_open_srt': "📄 SRT Aç",
        'menu_open_output_folder': "📂 Çıktı Klasörünü Aç",
        'menu_exit': "🚪 Çıkış",
        'menu_edit': "✏️ Düzenle",
        'menu_font_settings': "⚙️ Font Ayarları",
        'menu_preview': "👁️ Önizleme",
        'menu_save_settings': "💾 Ayarları Kaydet",
        'menu_view': "👁️ Görünüm",
        'view_main': "📝 Ana İşlemler",
        'view_font': "🎨 Yazı Tipi",
        'view_silence': "🔇 Sessizlik Budama",
        'view_settings': "⚙️ Ayarlar",
        'view_help': "❓ Yardım",
        'view_status_bar': "📊 Durum Çubuğunu Göster",
        'menu_process': "🚀 İşlemler",
        'process_transcribe': "🎙️ Transkript Et",
        'process_translate': "🌍 Çevir/Düzelt",
        'process_embed': "🎬 Altyazı Göm",
        'menu_help': "❓ Yardım",
        'help_guide': "📖 Kullanım Kılavuzu",
        'help_troubleshooting': "⚠️ Sorun Giderme",
        'help_about': "ℹ️ Hakkında",
        'main_file_frame': " 📁 Video ve Çıktı Ayarları ",
        'label_video_file': "Video Dosyası:",
        'label_output_name': "Çıktı Adı (opsiyonel):",
        'transcription_frame': " 🎙️ Transkripsiyon Ayarları ",
        'label_transcription_language': "🌐 Transkripsiyon Dili:",
        'transcribe_button': "🚀 Transkript Et",
        'translation_frame': " 🌍 Çeviri ve Düzeltme Ayarları ",
        'label_existing_srt': "Mevcut SRT Dosyası:",
        'label_translation_model': "🤖 Çeviri Modeli:",
        'label_source_language': "📤 Kaynak Dil:",
        'label_target_language': "📥 Hedef Dil:",
        'fix_spelling': "✏️ Yazım Hatalarını Düzelt",
        'translate_button': "🔄 Çevir/Düzelt",
        'embedding_frame': " 🎞️ Altyazı Gömme Ayarları ",
        'label_srt_file': "SRT Dosyası:",
        'label_subtitle_type': "⚙️ Altyazı Tipi:",
        'soft_subtitles': "📦 Yumuşak (MKV)",
        'hard_subtitles': "🔒 Sabit (MP4)",
        'embed_button': "🎬 Altyazı Göm",
        'browse_button': "📂 Gözat",
        'settings_api_title': " 🔑 API Ayarları ",
        'settings_api_info': "Groq ve OpenRouter API anahtarlarını buradan girip kaydedebilirsiniz.\nKaydedilen anahtarlar yeni işlemlerde hemen kullanılır.",
        'show_keys': "Anahtarları Göster",
        'save_api_keys': "💾 API Key Kaydet",
        'open_api_env': "📂 api.env Aç",
        'settings_language_title': " 🌐 Arayüz Dili ",
        'label_interface_language': "Arayüz Dili:",
        'language_note': "Dil seçimi kaydedilir. Değişiklik bir sonraki açılışta uygulanır.",
        'language_saved_title': "✅ Dil Kaydedildi",
        'language_saved_message': "Arayüz dili kaydedildi.\nDeğişiklik uygulamayı yeniden açtığınızda uygulanacak.",
        'settings_advanced_title': " 🔧 Gelişmiş Ayarları ",
        'label_default_output_name': "Varsayılan Çıktı Adı:",
        'auto_save_settings': "🔄 Ayarları Otomatik Kaydet",
        'clean_temp_files': "🗑️ Geçici Dosyaları Temizle",
        'help_tab_quickstart_title': " 🚀 Hızlı Başlangıç ",
        'help_tab_shortcuts_title': " ⌨️ Klavye Kısayolları ",
        'help_tab_quick_actions_title': " ⚡ Hızlı İşlemler ",
        'help_tab_browse_video': "📂 Video Seç",
        'help_tab_help': "❓ Yardım",
        'footer_subtitle': "Basit Sessizlik Temizleme ve Altyazı Gömme Aracı",
        'help_window_title': "📖 Kullanım Kılavuzu",
        'troubleshooting_window_title': "⚠️ Sorun Giderme",
        'about_window_title': "ℹ️ Hakkında",
        'about_title': "🎬 SSR&SET",
        'about_version': "Versiyon 2.0",
        'open_env_warning_title': "⚠️ Uyarı",
        'open_env_warning_message': "api.env dosyası bulunamadı.\nLütfen uygulama klasöründe api.env dosyası oluşturun.",
        'output_folder_warning_message': "Henüz bir çıktı klasörü oluşturulmamış.",
        'select_video_warning_message': "Önce bir video dosyası seçin.",
    },
    'en': {
        'window_title': "🎬 SSR&SET",
        'header_title': "🎬 SSR&SET",
        'tab_main': "📝 Main",
        'tab_font': "🎨 Font",
        'tab_silence': "🔇 Silence Trim",
        'tab_settings': "⚙️ Settings",
        'tab_help': "❓ Help",
        'status_ready': "✅ Ready",
        'ready_short': "Ready",
        'missing_short': "Missing",
        'font_tab_title': " 🎨 Current Font Settings ",
        'font_edit': "✏️ Edit",
        'font_preview': "👁️ Preview",
        'font_save_as': "💾 Save As",
        'font_load': "📂 Load",
        'font_info': "ℹ️ Font settings are saved automatically\n📁 Location: {path}",
        'menu_file': "📁 File",
        'menu_open_video': "🎥 Open Video",
        'menu_open_srt': "📄 Open SRT",
        'menu_open_output_folder': "📂 Open Output Folder",
        'menu_exit': "🚪 Exit",
        'menu_edit': "✏️ Edit",
        'menu_font_settings': "⚙️ Font Settings",
        'menu_preview': "👁️ Preview",
        'menu_save_settings': "💾 Save Settings",
        'menu_view': "👁️ View",
        'view_main': "📝 Main",
        'view_font': "🎨 Font",
        'view_silence': "🔇 Silence Trim",
        'view_settings': "⚙️ Settings",
        'view_help': "❓ Help",
        'view_status_bar': "📊 Show Status Bar",
        'menu_process': "🚀 Actions",
        'process_transcribe': "🎙️ Transcribe",
        'process_translate': "🌍 Translate/Fix",
        'process_embed': "🎬 Embed Subtitles",
        'menu_help': "❓ Help",
        'help_guide': "📖 User Guide",
        'help_troubleshooting': "⚠️ Troubleshooting",
        'help_about': "ℹ️ About",
        'main_file_frame': " 📁 Video and Output Settings ",
        'label_video_file': "Video File:",
        'label_output_name': "Output Name (optional):",
        'transcription_frame': " 🎙️ Transcription Settings ",
        'label_transcription_language': "🌐 Transcription Language:",
        'transcribe_button': "🚀 Transcribe",
        'translation_frame': " 🌍 Translation and Correction Settings ",
        'label_existing_srt': "Existing SRT File:",
        'label_translation_model': "🤖 Translation Model:",
        'label_source_language': "📤 Source Language:",
        'label_target_language': "📥 Target Language:",
        'fix_spelling': "✏️ Fix Spelling",
        'translate_button': "🔄 Translate/Fix",
        'embedding_frame': " 🎞️ Subtitle Embedding Settings ",
        'label_srt_file': "SRT File:",
        'label_subtitle_type': "⚙️ Subtitle Type:",
        'soft_subtitles': "📦 Soft (MKV)",
        'hard_subtitles': "🔒 Hard (MP4)",
        'embed_button': "🎬 Embed Subtitles",
        'browse_button': "📂 Browse",
        'settings_api_title': " 🔑 API Settings ",
        'settings_api_info': "You can enter and save your Groq and OpenRouter API keys here.\nSaved keys are used immediately for new tasks.",
        'show_keys': "Show Keys",
        'save_api_keys': "💾 Save API Keys",
        'open_api_env': "📂 Open api.env",
        'settings_language_title': " 🌐 Interface Language ",
        'label_interface_language': "Interface Language:",
        'language_note': "The selected language is saved. Changes apply the next time you open the app.",
        'language_saved_title': "✅ Language Saved",
        'language_saved_message': "Interface language was saved.\nThe change will apply when you reopen the app.",
        'settings_advanced_title': " 🔧 Advanced Settings ",
        'label_default_output_name': "Default Output Name:",
        'auto_save_settings': "🔄 Auto Save Settings",
        'clean_temp_files': "🗑️ Clean Temporary Files",
        'help_tab_quickstart_title': " 🚀 Quick Start ",
        'help_tab_shortcuts_title': " ⌨️ Keyboard Shortcuts ",
        'help_tab_quick_actions_title': " ⚡ Quick Actions ",
        'help_tab_browse_video': "📂 Select Video",
        'help_tab_help': "❓ Help",
        'footer_subtitle': "Simple Silence Remover and Subtitle Embed Tool",
        'help_window_title': "📖 User Guide",
        'troubleshooting_window_title': "⚠️ Troubleshooting",
        'about_window_title': "ℹ️ About",
        'about_title': "🎬 SSR&SET",
        'about_version': "Version 2.0",
        'open_env_warning_title': "⚠️ Warning",
        'open_env_warning_message': "api.env file was not found.\nPlease create an api.env file in the application folder.",
        'output_folder_warning_message': "No output folder has been created yet.",
        'select_video_warning_message': "Select a video file first.",
    },
}

class SubtitleApp:
    def __init__(self, master):
        self.master = master
        master.title(UI_TEXTS['tr']['window_title'])
        master.geometry("900x750")
        master.configure(bg='#1e1e1e')
        
        # Modern stil
        self.setup_styles()
        
        # Initialize font settings
        self.font_settings = FontSettings()
        
        # Config directory
        self.config_dir = Path.home() / ".video_transcriber"
        self.config_dir.mkdir(exist_ok=True)
        self.app_settings_file = self.config_dir / "app_settings.json"
        self.models_config_file = self.config_dir / "translation_models.json"
        self.font_config_file = self.config_dir / "font_settings.json"
        self.api_env_file = Path('api.env')
        
        # Load font settings
        self.load_default_font_settings()
        
        # Variables
        self.video_path = tk.StringVar()
        self.output_name = tk.StringVar()
        self.language = tk.StringVar(value="tr")
        self.source_language = tk.StringVar(value="auto")  # EKLE: Kaynak dil değişkeni
        self.target_language = tk.StringVar(value="en")
        self.srt_path_translate = tk.StringVar()
        self.groq_api_key_var = tk.StringVar()
        self.openrouter_api_key_var = tk.StringVar()
        self.ui_language_var = tk.StringVar(value='tr')
        self.show_api_keys_var = tk.BooleanVar(value=False)
        self.api_status_var = tk.StringVar()
        self.show_status_var = tk.BooleanVar(value=True)  # Durum çubuğu göster
        
        # Sessizlik budama ayarları
        self.remove_silence_var = tk.BooleanVar(value=False)
        self.remove_background_noise_var = tk.BooleanVar(value=False)
        self.silence_threshold_var = tk.DoubleVar(value=-40.0)  # dB
        self.min_silence_duration_var = tk.DoubleVar(value=0.5)  # saniye
        self.speech_protection_var = tk.DoubleVar(value=0.35)  # saniye
        self.manual_speech_protection_var = tk.BooleanVar(value=False)
        self.manual_video_speech_protection_var = tk.BooleanVar(value=False)
        self.video_remove_background_noise_var = tk.BooleanVar(value=False)
        self.video_trim_profile_var = tk.StringVar(value='Hız')
        
        # Load saved models or use defaults
        self.translation_models = self.load_models()
        self.translation_model = tk.StringVar(value=self.translation_models[0] if self.translation_models else "")
        self.load_app_settings()
        self.load_api_keys_from_env()
        
        self.create_widgets()

    def get_ui_language(self):
        language_code = self.ui_language_var.get().strip().lower()
        if language_code not in UI_LANGUAGE_OPTIONS:
            return 'tr'
        return language_code

    def tr(self, key, **kwargs):
        language_code = self.get_ui_language()
        template = UI_TEXTS.get(language_code, UI_TEXTS['tr']).get(key, UI_TEXTS['tr'].get(key, key))
        return template.format(**kwargs)

    def load_app_settings(self):
        if not self.app_settings_file.exists():
            return

        try:
            with open(self.app_settings_file, 'r', encoding='utf-8') as settings_file:
                data = json.load(settings_file)
        except Exception as exc:
            print(f"⚠️ Uygulama ayarları yükleme hatası: {exc}")
            return

        saved_language = str(data.get('ui_language', 'tr')).strip().lower()
        if saved_language in UI_LANGUAGE_OPTIONS:
            self.ui_language_var.set(saved_language)

    def save_app_settings(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            temp_file = self.app_settings_file.with_suffix('.tmp')
            data = {
                'ui_language': self.get_ui_language(),
            }
            with open(temp_file, 'w', encoding='utf-8') as settings_file:
                json.dump(data, settings_file, ensure_ascii=False, indent=2)

            if self.app_settings_file.exists():
                self.app_settings_file.unlink()
            temp_file.rename(self.app_settings_file)
            return True
        except Exception as exc:
            print(f"❌ Uygulama ayarları kaydetme hatası: {exc}")
            return False

    def get_ui_language_display(self):
        return UI_LANGUAGE_OPTIONS.get(self.get_ui_language(), UI_LANGUAGE_OPTIONS['tr'])

    def apply_ui_language_selection(self, selected_display_name):
        for language_code, display_name in UI_LANGUAGE_OPTIONS.items():
            if display_name == selected_display_name:
                self.ui_language_var.set(language_code)
                return language_code
        self.ui_language_var.set('tr')
        return 'tr'

    def on_ui_language_selected(self, selected_display_name):
        self.apply_ui_language_selection(selected_display_name)
        if self.save_app_settings():
            messagebox.showinfo(self.tr('language_saved_title'), self.tr('language_saved_message'))

    def get_transcription_language_options(self):
        if self.get_ui_language() == 'en':
            return {
                'Auto Detect': 'auto',
                'Turkish': 'tr',
                'English': 'en',
                'German': 'de',
                'Spanish': 'es',
                'French': 'fr',
                'Russian': 'ru',
                'Japanese': 'ja',
                'Chinese': 'zh',
            }

        return {
            'Otomatik Algıla': 'auto',
            'Türkçe': 'tr',
            'İngilizce': 'en',
            'Almanca': 'de',
            'İspanyolca': 'es',
            'Fransızca': 'fr',
            'Rusça': 'ru',
            'Japonca': 'ja',
            'Çince': 'zh',
        }

    def get_source_language_options(self):
        if self.get_ui_language() == 'en':
            return {
                'Auto Detect': 'auto',
                'Turkish': 'tr',
                'English': 'en',
                'German': 'de',
                'Spanish': 'es',
                'French': 'fr',
                'Italian': 'it',
                'Portuguese': 'pt',
                'Russian': 'ru',
                'Japanese': 'ja',
                'Chinese': 'zh',
                'Korean': 'ko',
                'Arabic': 'ar',
            }

        return {
            'Otomatik Algıla': 'auto',
            'Türkçe': 'tr',
            'İngilizce': 'en',
            'Almanca': 'de',
            'İspanyolca': 'es',
            'Fransızca': 'fr',
            'İtalyanca': 'it',
            'Portekizce': 'pt',
            'Rusça': 'ru',
            'Japonca': 'ja',
            'Çince': 'zh',
            'Korece': 'ko',
            'Arapça': 'ar',
        }

    def get_target_language_options(self):
        options = self.get_source_language_options().copy()
        options.pop('Auto Detect', None)
        options.pop('Otomatik Algıla', None)
        return options

    def get_help_popup_content(self):
        if self.get_ui_language() == 'en':
            return """
🎬 SSR&SET - Simple Silence Remover and Subtitle Embed Tool

📋 CORE WORKFLOWS:

1. 🎙️ Video Transcription:
   • Select a video file (MP4, AVI, MKV, MOV)
   • Choose the transcription language
   • Click "Transcribe"
   • JSON and SRT files are created when the job finishes

2. 🌍 SRT Translation/Correction:
   • Select an existing SRT file or use the last transcription result
   • Choose source and target language
   • Enable spelling correction when needed
   • Select a translation model
   • Click "Translate/Fix"

3. 🎬 Subtitle Embedding:
   • Select the video file and SRT file
   • Choose Soft (MKV) or Hard (MP4) subtitles
   • Click "Embed Subtitles"

🎨 FONT SETTINGS:

• Adjust font family and size
• Change text and outline colors
• Configure background color and transparency
• Set subtitle position
• Apply bold and italic styles

⌨️ SHORTCUTS:

Ctrl+O    - Open video
Ctrl+Shift+O - Open SRT
Ctrl+F    - Font settings
Ctrl+P    - Preview
Ctrl+S    - Save settings
Ctrl+T    - Transcribe
Ctrl+R    - Translate/Fix
Ctrl+E    - Embed subtitles
Ctrl+Q    - Exit

📁 OUTPUT STRUCTURE:

For each video, a "video_name_ciktilar" folder is created:
├── transcription/     (Original transcripts)
├── translation/       (Translated/corrected files)
└── embedded/          (Videos with subtitles)

⚠️ IMPORTANT NOTES:

• The bundled FFmpeg package is used automatically
• Groq API key is required for transcription
• OpenRouter API key is required for translation
• Large videos are split automatically
• Long tasks run in the background
            """

        return """
🎬 SSR&SET - Simple Silence Remover and Subtitle Embed Tool

📋 TEMEL İŞLEMLER:

1. 🎙️ Video Transkripti:
   • Video dosyasını seçin (MP4, AVI, MKV, MOV)
   • Transkripsiyon dilini ayarlayın
   • "Transkript Et" butonuna tıklayın
   • İşlem tamamlandığında JSON ve SRT dosyaları oluşturulur

2. 🌍 SRT Çeviri/Düzeltme:
   • Mevcut SRT dosyasını seçin veya önceki transkript sonucunu kullanın
   • Kaynak ve hedef dili seçin
   • Gerekirse yazım düzeltmeyi açın
   • Çeviri modelini seçin
   • "Çevir/Düzelt" butonuna tıklayın

3. 🎬 Altyazı Gömme:
   • Video dosyasını ve SRT dosyasını seçin
   • Yumuşak (MKV) veya Sabit (MP4) altyazı tipini seçin
   • "Altyazı Göm" butonuna tıklayın

🎨 YAZI TİPİ AYARLARI:

• Font ailesi ve boyutu ayarlayın
• Metin ve çerçeve renklerini değiştirin
• Arka plan rengi ve saydamlığını ayarlayın
• Altyazı konumunu belirleyin
• Kalın ve italik stiller uygulayın

⌨️ KLAVYE KISA YOLLARI:

Ctrl+O    - Video aç
Ctrl+Shift+O - SRT aç
Ctrl+F    - Font ayarları
Ctrl+P    - Önizleme
Ctrl+S    - Ayarları kaydet
Ctrl+T    - Transkript et
Ctrl+R    - Çevir/Düzelt
Ctrl+E    - Altyazı göm
Ctrl+Q    - Çıkış

📁 ÇIKTI YAPISI:

Her video için bir "videon_adı_ciktilar" klasörü oluşturulur:
├── transcription/     (Orijinal transkriptler)
├── translation/       (Çevrilmiş/düzeltilmiş dosyalar)
└── embedded/          (Altyazı gömülmüş videolar)

⚠️ ÖNEMLİ NOTLAR:

• Uygulama paketindeki FFmpeg otomatik kullanılır
• Groq API anahtarı gerekli (transkript için)
• OpenRouter API anahtarı gerekli (çeviri için)
• Büyük videolar otomatik olarak parçalanır
• İşlemler arka planda çalışır
            """

    def get_troubleshooting_popup_content(self):
        if self.get_ui_language() == 'en':
            return """
⚠️ TROUBLESHOOTING

1. "FFmpeg not found":
   ✓ Check the `ffmpeg-custom/balanced` folder
   ✓ Make sure `ffmpeg.exe` and `ffprobe.exe` still exist
   ✓ Re-copy the app if bundled files are missing

2. API connection errors:
   ✓ Check your internet connection
   ✓ Verify your API keys
   ✓ Inspect `api.env`

3. Transcription failed:
   ✓ Verify the video format is supported
   ✓ Make sure the video has audio
   ✓ Check the Groq API key

4. Translation issues:
   ✓ Try a different model
   ✓ Verify the OpenRouter API key

5. Subtitle embed issues:
   ✓ Check the input video and SRT files
   ✓ Make sure there is enough disk space
   ✓ Try soft subtitles if hard subtitles fail
            """

        return """
⚠️ SORUN GİDERME

1. "FFmpeg bulunamadı" Hatası:
   ✓ `ffmpeg-custom/balanced` klasörünü kontrol edin
   ✓ `ffmpeg.exe` ve `ffprobe.exe` dosyalarının mevcut olduğundan emin olun
   ✓ Paket dosyaları eksikse uygulamayı tekrar kopyalayın

2. API bağlantı hataları:
   ✓ İnternet bağlantınızı kontrol edin
   ✓ API anahtarlarınızı doğrulayın
   ✓ `api.env` dosyasını kontrol edin

3. Transkript başarısız:
   ✓ Video formatının desteklendiğinden emin olun
   ✓ Videoda ses olduğundan emin olun
   ✓ Groq API anahtarını kontrol edin

4. Çeviri sorunları:
   ✓ Farklı bir model deneyin
   ✓ OpenRouter API anahtarını doğrulayın

5. Altyazı gömme sorunları:
   ✓ Girdi video ve SRT dosyalarını kontrol edin
   ✓ Yeterli disk alanı olduğundan emin olun
   ✓ Hard subtitle hata verirse soft subtitle deneyin
            """

    def get_help_tab_quickstart_text(self):
        if self.get_ui_language() == 'en':
            return """1. Select your video file (MP4, AVI, MKV)
2. Choose the transcription language
3. Click "Transcribe"
4. Wait for the result and review the SRT file
5. Translate if needed
6. Embed subtitles into the video"""

        return """1. Video dosyanızı seçin (MP4, AVI, MKV)
2. Transkripsiyon dili seçin
3. "Transkript Et" butonuna tıklayın
4. Sonucu bekleyin ve SRT dosyasını inceleyin
5. Gerekirse çeviri yapın
6. Video'ya altyazı ekleyin"""

    def get_help_tab_shortcuts_text(self):
        if self.get_ui_language() == 'en':
            return """Ctrl+O    - Open video
Ctrl+Shift+O - Open SRT
Ctrl+F    - Font settings
Ctrl+P    - Preview
Ctrl+S    - Save settings
Ctrl+T    - Transcribe
Ctrl+R    - Translate/Fix
Ctrl+E    - Embed subtitles
Ctrl+Q    - Exit"""

        return """Ctrl+O    - Video aç
Ctrl+Shift+O - SRT aç
Ctrl+F    - Font ayarları
Ctrl+P    - Önizleme
Ctrl+S    - Ayarları kaydet
Ctrl+T    - Transkript et
Ctrl+R    - Çevir/Düzelt
Ctrl+E    - Altyazı göm
Ctrl+Q    - Çıkış"""

    def get_about_description(self):
        if self.get_ui_language() == 'en':
            return """
SSR&SET (Simple Silence Remover and Subtitle Embed Tool)
helps you transcribe video files, translate subtitles,
and embed subtitles back into your videos.

🚀 Features:
• Automatic subtitle generation from video (Groq API)
• Multilingual translation (OpenRouter AI)
• Soft and hard subtitle support
• Customizable font settings
• Modern user interface
• Keyboard shortcuts
            """

        return """
SSR&SET (Simple Silence Remover and Subtitle Embed Tool),
video dosyalarınızı altyazıya dönüştürmenizi,
altyazıları farklı dillere çevirmenizi ve videolarınıza
altyazı eklemenizi sağlar.

🚀 Özellikler:
• Video'dan otomatik altyazı çıkarma (Groq API)
• Çok dilli çeviri (OpenRouter AI)
• Yumuşak ve sabit altyazı desteği
• Özelleştirilebilir font ayarları
• Modern kullanıcı arayüzü
• Klavye kısayolları
            """

    def get_about_tech_text(self):
        if self.get_ui_language() == 'en':
            return """
🔧 Technologies:
• Python 3.x + Tkinter
• Groq API (Whisper Large V3)
• OpenRouter AI Models
• FFmpeg
• Modern UI Design
            """

        return """
🔧 Teknolojiler:
• Python 3.x + Tkinter
• Groq API (Whisper Large V3)
• OpenRouter AI Models
• FFmpeg
• Modern UI Design
            """

    def bind_mousewheel(self, widget):
        """Widget'a mouse wheel scroll özelliği ekle (Canvas veya Text)"""
        def on_mousewheel(event):
            # Windows ve Linux için farklı delta değerleri
            if event.num == 5 or event.delta < 0:
                widget.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                widget.yview_scroll(-1, "units")
        
        # Windows ve MacOS için
        widget.bind("<MouseWheel>", on_mousewheel)
        # Linux için
        widget.bind("<Button-4>", on_mousewheel)
        widget.bind("<Button-5>", on_mousewheel)
    
    def setup_styles(self):
        """Modern stil ayarları"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Modern renkler
        bg_color = '#1e1e1e'
        fg_color = '#ffffff'
        accent_color = '#0d7377'
        secondary_color = '#323232'
        
        # Notebook stili
        style.configure('TNotebook', background=bg_color, borderwidth=0)
        style.configure('TNotebook.Tab', background=secondary_color, foreground=fg_color, 
                       padding=[20, 10], font=('Segoe UI', 10, 'bold'))
        style.map('TNotebook.Tab', background=[('selected', accent_color)], 
                 foreground=[('selected', fg_color)])
        
        # Frame stili
        style.configure('TFrame', background=bg_color)
        style.configure('TLabelframe', background=bg_color, foreground=fg_color, 
                       borderwidth=2, relief='ridge')
        style.configure('TLabelframe.Label', background=bg_color, foreground=fg_color, 
                       font=('Segoe UI', 10, 'bold'))
        
        # Label stili
        style.configure('TLabel', background=bg_color, foreground=fg_color, 
                       font=('Segoe UI', 9))
        
        # Entry stili
        style.configure('TEntry', fieldbackground='#2b2b2b', foreground=fg_color, 
                       borderwidth=1, relief='flat')
        
        # Combobox stili
        style.configure('TCombobox', 
                       fieldbackground='#3c3c3c',  # Daha açık koyu gri
                       foreground='#ffffff',        # Beyaz yazı
                       background='#2b2b2b',        # Buton arka planı
                       borderwidth=1,
                       arrowcolor='#ffffff',        # Ok rengi
                       selectbackground='#0d7377',  # Seçili öğe arka planı
                       selectforeground='#ffffff')  # Seçili öğe yazı rengi
        
        # Combobox açılır liste stili
        style.map('TCombobox',
                 fieldbackground=[('readonly', '#3c3c3c')],
                 foreground=[('readonly', '#ffffff')],
                 selectbackground=[('readonly', '#0d7377')],
                 selectforeground=[('readonly', '#ffffff')])
        
        # Combobox listbox için özel ayar (Windows için)
        self.master.option_add('*TCombobox*Listbox.background', '#3c3c3c')
        self.master.option_add('*TCombobox*Listbox.foreground', '#ffffff')
        self.master.option_add('*TCombobox*Listbox.selectBackground', '#0d7377')
        self.master.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
        
        # Progressbar stili
        style.configure('TProgressbar', background=accent_color, troughcolor=secondary_color, 
                       borderwidth=0, thickness=20)

    def _normalize_model_list(self, models):
        normalized_models = []
        for model_name in models or []:
            if not isinstance(model_name, str):
                continue
            cleaned_name = model_name.strip()
            if cleaned_name and cleaned_name not in normalized_models:
                normalized_models.append(cleaned_name)
        return normalized_models

    def _refresh_model_combo(self):
        if hasattr(self, 'model_combo'):
            self.model_combo['values'] = self.translation_models

        current_model = self.translation_model.get().strip()
        if current_model in self.translation_models:
            self.translation_model.set(current_model)
        elif self.translation_models:
            self.translation_model.set(self.translation_models[0])
        else:
            self.translation_model.set("")

    def load_models(self):
        """Kaydedilmiş modelleri yükle; varsayılan model ekleme."""
        if self.models_config_file.exists():
            try:
                with open(self.models_config_file, 'r', encoding='utf-8') as f:
                    loaded_models = json.load(f)
                    if isinstance(loaded_models, list):
                        print(f"✅ Modeller yüklendi: {self.models_config_file}")
                        return self._normalize_model_list(loaded_models)
            except Exception as e:
                print(f"⚠️ Model yükleme hatası: {e}")
        
        return []

    def save_models(self, show_message=True):
        """Mevcut model listesini kaydet"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.translation_models = self._normalize_model_list(self.translation_models)
            temp_file = self.models_config_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.translation_models, f, ensure_ascii=False, indent=2)
            
            if self.models_config_file.exists():
                self.models_config_file.unlink()
            temp_file.rename(self.models_config_file)
            self._refresh_model_combo()

            if show_message:
                messagebox.showinfo("✅ Başarılı", 
                                  f"Model listesi kaydedildi!\n\n📁 Konum:\n{self.models_config_file}")
            print(f"✅ Modeller kaydedildi: {self.models_config_file}")
            return True
        except Exception as e:
            if show_message:
                messagebox.showerror("❌ Hata", 
                                   f"Model listesi kaydedilemedi:\n\n{str(e)}\n\nKonum: {self.models_config_file}")
            print(f"❌ Model kaydetme hatası: {e}")
            return False

    def load_default_font_settings(self):
        """Varsayılan font ayarlarını yükle"""
        if self.font_config_file.exists():
            try:
                with open(self.font_config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.font_settings.from_dict(data)
                    print(f"✅ Font ayarları yüklendi: {self.font_config_file}")
            except Exception as e:
                print(f"⚠️ Font ayarları yükleme hatası: {e}")

    def save_default_font_settings(self):
        """Font ayarlarını otomatik kaydet"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            temp_file = self.font_config_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.font_settings.to_dict(), f, ensure_ascii=False, indent=2)
            
            if self.font_config_file.exists():
                self.font_config_file.unlink()
            temp_file.rename(self.font_config_file)
            
            messagebox.showinfo("✅ Başarılı", 
                              f"Font ayarları kaydedildi!\n\n📁 Konum:\n{self.font_config_file}")
            print(f"✅ Font ayarları kaydedildi: {self.font_config_file}")
        except Exception as e:
            messagebox.showerror("❌ Hata", 
                               f"Font ayarları kaydedilemedi:\n\n{str(e)}")
            print(f"❌ Font kaydetme hatası: {e}")

    def create_widgets(self):
        # Create menu bar
        self.create_menu_bar()
        
        # Header
        header_frame = tk.Frame(self.master, bg='#0d7377', height=80)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        header_label = tk.Label(header_frame, text=self.tr('header_title'), 
                               bg='#0d7377', fg='white', 
                               font=('Segoe UI', 18, 'bold'))
        header_label.pack(expand=True, pady=(10, 0))
        
        # 🚀 GPU Encoder bilgisi (Async yükleme)
        self.encoder_label = tk.Label(header_frame, text="🎮 Encoder: Aranıyor...", 
                                bg='#0d7377', fg='#dddddd', 
                                font=('Segoe UI', 9, 'italic'))
        self.encoder_label.pack(pady=(0, 5))
        
        # Async olarak GPU bilgisini yükle
        import threading
        threading.Thread(target=self.load_gpu_info_async, daemon=True).start()
        
        # Create notebook for tabs
        notebook = ttk.Notebook(self.master)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Store notebook reference for switching
        self.notebook = notebook
        
        # Main tab
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text=self.tr('tab_main'))
        
        # Font settings tab
        font_tab = ttk.Frame(notebook)
        notebook.add(font_tab, text=self.tr('tab_font'))
        
        # Silence removal tab
        silence_tab = ttk.Frame(notebook)
        notebook.add(silence_tab, text=self.tr('tab_silence'))
        
        # Settings tab
        settings_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text=self.tr('tab_settings'))
        
        # Help tab
        help_tab = ttk.Frame(notebook)
        notebook.add(help_tab, text=self.tr('tab_help'))
        
        self.create_main_tab(main_tab)
        self.create_font_tab(font_tab)
        self.create_silence_tab(silence_tab)
        self.create_settings_tab(settings_tab)
        self.create_help_tab(help_tab)
        
        # Progress Bar and Status (bottom of main window)
        progress_frame = tk.Frame(self.master, bg='#1e1e1e')
        progress_frame.pack(fill="x", padx=10, pady=10)
        self.progress_frame = progress_frame  # Store reference
        
        self.progress = ttk.Progressbar(progress_frame, orient="horizontal", 
                                       length=400, mode="determinate")
        self.progress.pack(pady=5)
        
        self.status_label = tk.Label(progress_frame, text=self.tr('status_ready'), 
                                     bg='#1e1e1e', fg='#4caf50', 
                                     font=('Segoe UI', 10, 'bold'))
        self.status_label.pack(pady=5)

    def load_gpu_info_async(self):
        """GPU bilgisini arka planda yükle"""
        try:
            gpu_info = SubtitleEmbedder.detect_gpu_encoder()
            encoder_text = f"🎮 Encoder: {gpu_info['name']}"
            encoder_color = '#00ff00' if 'GPU' in gpu_info['name'] or 'NVENC' in gpu_info['name'] or 'VideoToolbox' in gpu_info['name'] or 'AMF' in gpu_info['name'] or 'Quick Sync' in gpu_info['name'] else '#ffaa00'
            
            # UI güncelleme (ana thread'de yapılmalı)
            self.master.after(0, lambda: self.encoder_label.config(text=encoder_text, fg=encoder_color))
        except Exception as e:
            print(f"GPU info error: {e}")
            self.master.after(0, lambda: self.encoder_label.config(text="🎮 Encoder: CPU (libx264)", fg='#ffaa00'))

    def create_main_tab(self, parent):
        # Scrollable frame
        canvas = tk.Canvas(parent, bg='#1e1e1e', highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 🖱️ Mouse wheel scroll desteği ekle
        self.bind_mousewheel(canvas)
        
        # File Selection Frame
        file_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('main_file_frame'))
        file_frame.pack(padx=15, pady=10, fill="x")
        
        self.create_file_row(file_frame, self.tr('label_video_file'), self.video_path, 
                            self.browse_video, 0, "🎥")
        self.create_file_row(file_frame, self.tr('label_output_name'), self.output_name, 
                            None, 1, "📝")
        
        # Transcription Frame
        transcribe_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('transcription_frame'))
        transcribe_frame.pack(padx=15, pady=10, fill="x")
        
        lang_row = tk.Frame(transcribe_frame, bg='#1e1e1e')
        lang_row.pack(fill="x", padx=10, pady=10)
        
        tk.Label(lang_row, text=self.tr('label_transcription_language'), bg='#1e1e1e', 
                fg='white', font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=5)
        
        self.language_options = self.get_transcription_language_options()
        default_transcription_language = 'Auto Detect' if self.get_ui_language() == 'en' else 'Otomatik Algıla'
        self.language_selection = tk.StringVar(value=default_transcription_language)
        self.language_combo = ttk.Combobox(lang_row, textvariable=self.language_selection, 
                                         values=list(self.language_options.keys()), 
                                         state="readonly", width=20, 
                                         font=('Segoe UI', 9))
        self.language_combo.pack(side=tk.LEFT, padx=10)
        
        transcribe_btn = tk.Button(lang_row, text=self.tr('transcribe_button'), 
                                  command=self.start_transcription_thread,
                                  bg='#28a745', fg='white', relief=tk.FLAT, 
                                  font=('Segoe UI', 9, 'bold'), padx=20, pady=8, 
                                  cursor='hand2')
        transcribe_btn.pack(side=tk.RIGHT, padx=5)
        
        # Translation Frame
        translate_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('translation_frame'))
        translate_frame.pack(padx=15, pady=10, fill="x")
        
        self.create_file_row(translate_frame, self.tr('label_existing_srt'), 
                            self.srt_path_translate, self.browse_srt_for_translation, 
                            0, "📄")
        
        # Model selection with save button
        model_row = tk.Frame(translate_frame, bg='#1e1e1e')
        model_row.pack(fill="x", padx=10, pady=10)
        
        tk.Label(model_row, text=self.tr('label_translation_model'), bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=5)
        
        self.model_combo = ttk.Combobox(model_row, textvariable=self.translation_model, 
                                       values=self.translation_models, state="readonly", 
                                       font=('Segoe UI', 9))
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        add_model_btn = tk.Button(model_row, text="➕", command=self.add_model, 
                                 width=3, bg='#28a745', fg='white', relief=tk.FLAT, 
                                 font=('Segoe UI', 10, 'bold'), cursor='hand2')
        add_model_btn.pack(side=tk.LEFT, padx=2)
        
        remove_model_btn = tk.Button(model_row, text="➖", command=self.remove_model, 
                                     width=3, bg='#dc3545', fg='white', relief=tk.FLAT, 
                                     font=('Segoe UI', 10, 'bold'), cursor='hand2')
        remove_model_btn.pack(side=tk.LEFT, padx=2)
        
        save_models_btn = tk.Button(model_row, text="💾", command=self.save_models, 
                                    width=3, bg='#0d7377', fg='white', relief=tk.FLAT, 
                                    font=('Segoe UI', 10, 'bold'), cursor='hand2')
        save_models_btn.pack(side=tk.LEFT, padx=2)
        
        # ====== KAYNAK VE HEDEF DİL SATIRI (YENİ) ======
        lang_row = tk.Frame(translate_frame, bg='#1e1e1e')
        lang_row.pack(fill="x", padx=10, pady=10)
        
        # Kaynak Dil
        tk.Label(lang_row, text=self.tr('label_source_language'), bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=5)
        
        self.source_lang_options = self.get_source_language_options()
        default_source_language = 'Auto Detect' if self.get_ui_language() == 'en' else 'Otomatik Algıla'
        self.source_language_selection = tk.StringVar(value=default_source_language)
        source_combo = ttk.Combobox(lang_row, textvariable=self.source_language_selection,
                                  values=list(self.source_lang_options.keys()),
                                  state="readonly", width=18, font=('Segoe UI', 9))
        source_combo.pack(side=tk.LEFT, padx=10)
        
        # Hedef Dil
        tk.Label(lang_row, text=self.tr('label_target_language'), bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=5)
        
        self.target_lang_options = self.get_target_language_options()
        default_target_language = 'English' if self.get_ui_language() == 'en' else 'İngilizce'
        self.target_language_selection = tk.StringVar(value=default_target_language)
        target_combo = ttk.Combobox(lang_row, textvariable=self.target_language_selection,
                                  values=list(self.target_lang_options.keys()),
                                  state="readonly", width=18, font=('Segoe UI', 9))
        target_combo.pack(side=tk.LEFT, padx=10)
        
        # Yazım düzeltme ve çevir butonu
        action_row = tk.Frame(translate_frame, bg='#1e1e1e')
        action_row.pack(fill="x", padx=10, pady=10)
        
        self.fix_spelling_var = tk.BooleanVar()
        fix_check = tk.Checkbutton(action_row, text=self.tr('fix_spelling'), 
                                  variable=self.fix_spelling_var, bg='#1e1e1e', 
                                  fg='white', selectcolor='#404040', 
                                  font=('Segoe UI', 9), activebackground='#1e1e1e')
        fix_check.pack(side=tk.LEFT, padx=10)
        
        translate_btn = tk.Button(action_row, text=self.tr('translate_button'), 
                                 command=self.start_translation_thread, bg='#17a2b8', 
                                 fg='white', relief=tk.FLAT, 
                                 font=('Segoe UI', 9, 'bold'), padx=20, pady=8, 
                                 cursor='hand2')
        translate_btn.pack(side=tk.RIGHT, padx=5)
        
        # Embedding Frame
        embed_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('embedding_frame'))
        embed_frame.pack(padx=15, pady=10, fill="x")
        
        self.video_path_embed = tk.StringVar()
        self.create_file_row(embed_frame, self.tr('label_video_file'), self.video_path_embed, 
                            self.browse_video_for_embedding, 0, "🎥")
        self.srt_path_embed = tk.StringVar()
        self.create_file_row(embed_frame, self.tr('label_srt_file'), self.srt_path_embed, 
                            self.browse_srt_for_embedding, 1, "📄")
        
        embed_type_row = tk.Frame(embed_frame, bg='#1e1e1e')
        embed_type_row.pack(fill="x", padx=10, pady=10)
        
        tk.Label(embed_type_row, text=self.tr('label_subtitle_type'), bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=5)
        
        self.embed_type = tk.StringVar(value="soft")
        
        soft_radio = tk.Radiobutton(embed_type_row, text=self.tr('soft_subtitles'), 
                                   variable=self.embed_type, value="soft", 
                                   bg='#1e1e1e', fg='white', selectcolor='#404040', 
                                   font=('Segoe UI', 9), activebackground='#1e1e1e')
        soft_radio.pack(side=tk.LEFT, padx=10)
        
        hard_radio = tk.Radiobutton(embed_type_row, text=self.tr('hard_subtitles'), 
                                   variable=self.embed_type, value="hard", 
                                   bg='#1e1e1e', fg='white', selectcolor='#404040', 
                                   font=('Segoe UI', 9), activebackground='#1e1e1e')
        hard_radio.pack(side=tk.LEFT, padx=10)
        
        embed_btn = tk.Button(embed_type_row, text=self.tr('embed_button'), 
                             command=self.start_embedding_thread, bg='#6f42c1', 
                             fg='white', relief=tk.FLAT, 
                             font=('Segoe UI', 9, 'bold'), padx=20, pady=8, 
                             cursor='hand2')
        embed_btn.pack(side=tk.RIGHT, padx=5)

    def create_file_row(self, parent, label_text, text_var, browse_cmd, row, icon=""):
        row_frame = tk.Frame(parent, bg='#1e1e1e')
        row_frame.pack(fill="x", padx=10, pady=8)
        
        label = tk.Label(row_frame, text=f"{icon} {label_text}", bg='#1e1e1e', 
                        fg='white', font=('Segoe UI', 9))
        label.pack(side=tk.LEFT, padx=5)
        
        entry = tk.Entry(row_frame, textvariable=text_var, bg='#2b2b2b', 
                        fg='white', relief=tk.FLAT, font=('Segoe UI', 9), 
                        insertbackground='white')
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        if browse_cmd:
            browse_btn = tk.Button(row_frame, text=self.tr('browse_button'), command=browse_cmd, 
                                  bg='#0d7377', fg='white', relief=tk.FLAT, 
                                  font=('Segoe UI', 8, 'bold'), padx=10, pady=5, 
                                  cursor='hand2')
            browse_btn.pack(side=tk.RIGHT, padx=5)

    def create_font_tab(self, parent):
        # Font settings display
        settings_frame = tk.LabelFrame(parent, text=self.tr('font_tab_title'), 
                                      bg='#1e1e1e', fg='white', 
                                      font=('Segoe UI', 11, 'bold'))
        settings_frame.pack(padx=15, pady=15, fill="both", expand=True)
        
        # Current settings display
        self.font_info_label = tk.Label(settings_frame, text="", justify=tk.LEFT, 
                                       bg='#1e1e1e', fg='white', 
                                       font=('Segoe UI', 10))
        self.font_info_label.pack(padx=15, pady=15, anchor="w")
        
        # Buttons
        button_frame = tk.Frame(settings_frame, bg='#1e1e1e')
        button_frame.pack(pady=15)
        
        edit_btn = tk.Button(button_frame, text=self.tr('font_edit'), 
                            command=self.open_font_settings, bg='#0d7377', 
                            fg='white', relief=tk.FLAT, 
                            font=('Segoe UI', 10, 'bold'), padx=20, pady=10, 
                            cursor='hand2')
        edit_btn.pack(side=tk.LEFT, padx=5)
        
        preview_btn = tk.Button(button_frame, text=self.tr('font_preview'), 
                               command=self.show_preview, bg='#17a2b8', 
                               fg='white', relief=tk.FLAT, 
                               font=('Segoe UI', 10, 'bold'), padx=20, pady=10, 
                               cursor='hand2')
        preview_btn.pack(side=tk.LEFT, padx=5)
        
        save_btn = tk.Button(button_frame, text=self.tr('font_save_as'), 
                            command=self.save_font_settings, bg='#28a745', 
                            fg='white', relief=tk.FLAT, 
                            font=('Segoe UI', 10, 'bold'), padx=20, pady=10, 
                            cursor='hand2')
        save_btn.pack(side=tk.LEFT, padx=5)
        
        load_btn = tk.Button(button_frame, text=self.tr('font_load'), 
                            command=self.load_font_settings, bg='#6f42c1', 
                            fg='white', relief=tk.FLAT, 
                            font=('Segoe UI', 10, 'bold'), padx=20, pady=10, 
                            cursor='hand2')
        load_btn.pack(side=tk.LEFT, padx=5)
        
        # Info label
        info_label = tk.Label(settings_frame, 
                             text=self.tr('font_info', path=self.font_config_file), 
                             bg='#1e1e1e', fg='#888888', font=('Segoe UI', 8), 
                             justify=tk.LEFT)
        info_label.pack(pady=10)
        
        self.update_font_info()

    def create_menu_bar(self):
        """Menu bar oluştur"""
        menubar = tk.Menu(self.master, bg='#2b2b2b', fg='white', activebackground='#0d7377', activeforeground='white')
        self.master.config(menu=menubar)
        
        # Dosya menüsü
        file_menu = tk.Menu(menubar, tearoff=0, bg='#2b2b2b', fg='white', activebackground='#0d7377', activeforeground='white')
        menubar.add_cascade(label=self.tr('menu_file'), menu=file_menu)
        file_menu.add_command(label=self.tr('menu_open_video'), command=self.browse_video, accelerator="Ctrl+O")
        file_menu.add_command(label=self.tr('menu_open_srt'), command=self.browse_srt_for_translation, accelerator="Ctrl+Shift+O")
        file_menu.add_separator()
        file_menu.add_command(label=self.tr('menu_open_output_folder'), command=self.open_output_folder, accelerator="Ctrl+Shift+D")
        file_menu.add_separator()
        file_menu.add_command(label=self.tr('menu_exit'), command=self.master.quit, accelerator="Ctrl+Q")
        
        # Düzenle menüsü
        edit_menu = tk.Menu(menubar, tearoff=0, bg='#2b2b2b', fg='white', activebackground='#0d7377', activeforeground='white')
        menubar.add_cascade(label=self.tr('menu_edit'), menu=edit_menu)
        edit_menu.add_command(label=self.tr('menu_font_settings'), command=self.open_font_settings, accelerator="Ctrl+F")
        edit_menu.add_command(label=self.tr('menu_preview'), command=self.show_preview, accelerator="Ctrl+P")
        edit_menu.add_separator()
        edit_menu.add_command(label=self.tr('menu_save_settings'), command=self.save_default_font_settings, accelerator="Ctrl+S")
        
        # Görünüm menüsü
        view_menu = tk.Menu(menubar, tearoff=0, bg='#2b2b2b', fg='white', activebackground='#0d7377', activeforeground='white')
        menubar.add_cascade(label=self.tr('menu_view'), menu=view_menu)
        view_menu.add_command(label=self.tr('view_main'), command=lambda: self.switch_to_tab(0))
        view_menu.add_command(label=self.tr('view_font'), command=lambda: self.switch_to_tab(1))
        view_menu.add_command(label=self.tr('view_silence'), command=lambda: self.switch_to_tab(2))
        view_menu.add_command(label=self.tr('view_settings'), command=lambda: self.switch_to_tab(3))
        view_menu.add_command(label=self.tr('view_help'), command=lambda: self.switch_to_tab(4))
        view_menu.add_separator()
        view_menu.add_checkbutton(label=self.tr('view_status_bar'), variable=self.show_status_var, command=self.toggle_status_bar)
        
        # İşlemler menüsü
        process_menu = tk.Menu(menubar, tearoff=0, bg='#2b2b2b', fg='white', activebackground='#0d7377', activeforeground='white')
        menubar.add_cascade(label=self.tr('menu_process'), menu=process_menu)
        process_menu.add_command(label=self.tr('process_transcribe'), command=self.start_transcription_thread, accelerator="Ctrl+T")
        process_menu.add_command(label=self.tr('process_translate'), command=self.start_translation_thread, accelerator="Ctrl+R")
        process_menu.add_command(label=self.tr('process_embed'), command=self.start_embedding_thread, accelerator="Ctrl+E")
        
        # Yardım menüsü
        help_menu = tk.Menu(menubar, tearoff=0, bg='#2b2b2b', fg='white', activebackground='#0d7377', activeforeground='white')
        menubar.add_cascade(label=self.tr('menu_help'), menu=help_menu)
        help_menu.add_command(label=self.tr('help_guide'), command=self.show_help)
        help_menu.add_command(label=self.tr('help_troubleshooting'), command=self.show_troubleshooting)
        help_menu.add_separator()
        help_menu.add_command(label=self.tr('help_about'), command=self.show_about)
        
        # Klavye kısayolları
        self.master.bind('<Control-o>', lambda e: self.browse_video())
        self.master.bind('<Control-O>', lambda e: self.browse_srt_for_translation())
        self.master.bind('<Control-f>', lambda e: self.open_font_settings())
        self.master.bind('<Control-p>', lambda e: self.show_preview())
        self.master.bind('<Control-s>', lambda e: self.save_default_font_settings())
        self.master.bind('<Control-t>', lambda e: self.start_transcription_thread())
        self.master.bind('<Control-r>', lambda e: self.start_translation_thread())
        self.master.bind('<Control-e>', lambda e: self.start_embedding_thread())
        self.master.bind('<Control-q>', lambda e: self.master.quit())

    def switch_to_tab(self, tab_index):
        """Belirtilen sekmeye geç"""
        try:
            self.notebook.select(tab_index)
        except:
            pass

    def toggle_status_bar(self):
        """Durum çubuğunu göster/gizle"""
        if self.show_status_var.get():
            self.progress_frame.pack(fill="x", padx=10, pady=10)
        else:
            self.progress_frame.pack_forget()

    def open_output_folder(self):
        """Son çıktı klasörünü aç"""
        video_file = self.video_path.get()
        if video_file:
            video_p = Path(video_file)
            output_dir = video_p.parent / f"{video_p.stem}_ciktilar"
            if output_dir.exists():
                if os.name == 'nt':  # Windows
                    os.startfile(output_dir)
                elif os.name == 'posix':  # macOS/Linux
                    subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', str(output_dir)])
            else:
                messagebox.showwarning(self.tr('open_env_warning_title'), self.tr('output_folder_warning_message'))
        else:
            messagebox.showwarning(self.tr('open_env_warning_title'), self.tr('select_video_warning_message'))

    def _open_path(self, target_path):
        target_path = Path(target_path)
        if not target_path.exists():
            raise FileNotFoundError(f"Dosya bulunamadı: {target_path}")

        if os.name == 'nt':
            os.startfile(target_path)
        elif os.name == 'posix':
            subprocess.run(
                ['open' if sys.platform == 'darwin' else 'xdg-open', str(target_path)],
                check=True
            )

    def load_api_keys_from_env(self):
        """API anahtarlarını api.env dosyasından yükle"""
        env_values = dotenv_values(self.api_env_file) if self.api_env_file.exists() else {}
        self.groq_api_key_var.set(env_values.get('GROQ_API_KEY') or '')
        self.openrouter_api_key_var.set(env_values.get('OPENROUTER_API_KEY') or '')
        self.refresh_api_status()

    def refresh_api_status(self):
        """API anahtar durum etiketini güncelle"""
        groq_ready = bool(self.groq_api_key_var.get().strip())
        openrouter_ready = bool(self.openrouter_api_key_var.get().strip())
        groq_status = self.tr('ready_short') if groq_ready else self.tr('missing_short')
        openrouter_status = self.tr('ready_short') if openrouter_ready else self.tr('missing_short')
        self.api_status_var.set(f"Groq: {groq_status} | OpenRouter: {openrouter_status}")

    def toggle_api_key_visibility(self):
        """API anahtar giriş alanlarını göster/gizle"""
        entry_mask = '' if self.show_api_keys_var.get() else '*'
        if hasattr(self, 'groq_api_entry'):
            self.groq_api_entry.config(show=entry_mask)
        if hasattr(self, 'openrouter_api_entry'):
            self.openrouter_api_entry.config(show=entry_mask)

    def save_api_keys(self):
        """API anahtarlarını api.env dosyasına kaydet"""
        env_values = {}
        if self.api_env_file.exists():
            env_values.update(dotenv_values(self.api_env_file))

        env_values['GROQ_API_KEY'] = self.groq_api_key_var.get().strip()
        env_values['OPENROUTER_API_KEY'] = self.openrouter_api_key_var.get().strip()

        existing_lines = []
        if self.api_env_file.exists():
            existing_lines = self.api_env_file.read_text(encoding='utf-8').splitlines()

        updated_lines = []
        seen_keys = set()
        for line in existing_lines:
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith('#') or '=' not in line:
                updated_lines.append(line)
                continue

            key, _ = line.split('=', 1)
            normalized_key = key.strip()
            if normalized_key not in API_ENV_KEYS:
                updated_lines.append(line)
                continue

            seen_keys.add(normalized_key)
            value = env_values.get(normalized_key, '')
            if value:
                updated_lines.append(f"{normalized_key}={value}")

        for key in API_ENV_KEYS:
            if key not in seen_keys and env_values.get(key):
                updated_lines.append(f"{key}={env_values[key]}")

        content = '\n'.join(updated_lines).rstrip()
        self.api_env_file.write_text(f"{content}\n" if content else '', encoding='utf-8')

        for key in API_ENV_KEYS:
            value = env_values.get(key, '').strip()
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

        self.refresh_api_status()
        messagebox.showinfo(
            "✅ Başarılı",
            "API anahtarları kaydedildi.\n\nYeni işlemlerde hemen kullanılabilir.",
        )

    def open_env_file(self):
        """.env dosyasını aç"""
        env_file = self.api_env_file
        if env_file.exists():
            if os.name == 'nt':  # Windows
                os.startfile(env_file)
            elif os.name == 'posix':  # macOS/Linux
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', str(env_file)])
        else:
            messagebox.showwarning("⚠️ Uyarı", 
                                 "api.env dosyası bulunamadı.\n"
                                 "Lütfen uygulama klasöründe api.env dosyası oluşturun.")

    def clean_temp_files(self):
        """Geçici dosyaları temizle"""
        temp_dir = Path(tempfile.gettempdir())
        subtitle_temp_files = list(temp_dir.glob("*_chunk_*.wav"))
        subtitle_temp_files.extend(list(temp_dir.glob("*.wav")))
        
        if not subtitle_temp_files:
            messagebox.showinfo("ℹ️ Bilgi", "Temizlenecek geçici dosya bulunamadı.")
            return
        
        if messagebox.askyesno("❓ Onay", 
                               f"{len(subtitle_temp_files)} geçici dosya bulundu.\n"
                               "Temizlenmesini istediğinize emin misiniz?"):
            cleaned = 0
            for file in subtitle_temp_files:
                try:
                    file.unlink()
                    cleaned += 1
                except:
                    pass
            
            messagebox.showinfo("✅ Tamamlandı", 
                              f"{cleaned} geçici dosya temizlendi.")
        else:
            messagebox.showinfo("ℹ️ Bilgi", "İşlem iptal edildi.")

    def show_help(self):
        """Yardım penceresi göster"""
        help_window = tk.Toplevel(self.master)
        help_window.title(self.tr('help_window_title'))
        help_window.geometry("700x600")
        help_window.configure(bg='#2b2b2b')
        
        # Scrollable text widget
        text_frame = tk.Frame(help_window, bg='#2b2b2b')
        text_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        help_text = tk.Text(text_frame, wrap=tk.WORD, font=('Segoe UI', 10), 
                           bg='#1e1e1e', fg='white', relief=tk.FLAT)
        scrollbar = tk.Scrollbar(text_frame, orient="vertical", command=help_text.yview)
        help_text.configure(yscrollcommand=scrollbar.set)
        
        help_content = self.get_help_popup_content()
        
        help_text.insert('1.0', help_content)
        help_text.config(state=tk.DISABLED)
        
        help_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 🖱️ Mouse wheel scroll desteği ekle
        self.bind_mousewheel(help_text)

    def show_troubleshooting(self):
        """Sorun giderme penceresi"""
        trouble_window = tk.Toplevel(self.master)
        trouble_window.title(self.tr('troubleshooting_window_title'))
        trouble_window.geometry("650x500")
        trouble_window.configure(bg='#2b2b2b')
        
        # Text widget with scrollbar
        text_frame = tk.Frame(trouble_window, bg='#2b2b2b')
        text_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        trouble_text = tk.Text(text_frame, wrap=tk.WORD, font=('Segoe UI', 10), 
                              bg='#1e1e1e', fg='white', relief=tk.FLAT)
        scrollbar = tk.Scrollbar(text_frame, orient="vertical", command=trouble_text.yview)
        trouble_text.configure(yscrollcommand=scrollbar.set)
        
        trouble_content = self.get_troubleshooting_popup_content()
        
        trouble_text.insert('1.0', trouble_content)
        trouble_text.config(state=tk.DISABLED)
        
        trouble_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 🖱️ Mouse wheel scroll desteği ekle
        self.bind_mousewheel(trouble_text)

    def show_about(self):
        """Hakkında penceresi"""
        about_window = tk.Toplevel(self.master)
        about_window.title(self.tr('about_window_title'))
        about_window.geometry("500x400")
        about_window.configure(bg='#2b2b2b')
        
        # Center the window
        about_window.transient(self.master)
        about_window.grab_set()
        
        # Main content
        main_frame = tk.Frame(about_window, bg='#2b2b2b')
        main_frame.pack(expand=True, fill='both', padx=20, pady=20)
        
        # App icon/title
        title_label = tk.Label(main_frame, text=self.tr('about_title'), 
                              bg='#2b2b2b', fg='#0d7377', 
                              font=('Segoe UI', 16, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # Version
        version_label = tk.Label(main_frame, text=self.tr('about_version'), 
                                bg='#2b2b2b', fg='white', 
                                font=('Segoe UI', 12))
        version_label.pack()
        
        # Description
        desc_text = self.get_about_description()
        
        desc_label = tk.Label(main_frame, text=desc_text, 
                             bg='#2b2b2b', fg='white', 
                             font=('Segoe UI', 10), justify='left')
        desc_label.pack(pady=20)
        
        # Technologies used
        tech_text = self.get_about_tech_text()
        
        tech_label = tk.Label(main_frame, text=tech_text, 
                             bg='#2b2b2b', fg='#cccccc', 
                             font=('Segoe UI', 9), justify='left')
        tech_label.pack()
        
        # Copyright
        copyright_label = tk.Label(main_frame, text="© 2024 SSR&SET", 
                                  bg='#2b2b2b', fg='#888888', 
                                  font=('Segoe UI', 8))
        copyright_label.pack(side='bottom', pady=10)

    def update_font_info(self):
        adaptive_status = "Açık (Otomatik)" if self.font_settings.use_adaptive_size else "Kapalı (Sabit)"
        info_text = f"""📝 Font Ailesi: {self.font_settings.font_family}
📏 Boyut: {self.font_settings.font_size} {'📐 ' + adaptive_status if True else ''}
🎨 Renk: {self.font_settings.font_color}
�️Ç Çerçeve Rengi: {self.font_settings.outline_color}
📐 Çerçeve Kalınlığı: {self.font_settings.outline_width}
🎭 Arka Plan Rengi: {self.font_settings.background_color}
�  Arka Plan Saydamlığı: {self.font_settings.background_opacity:.2f}
� KKonum: X={self.font_settings.position_x}%, Y={self.font_settings.position_y}%
�  Kalın: {'Evet' if self.font_settings.bold else 'Hayır'}
📖 İtalik: {'Evet' if self.font_settings.italic else 'Hayır'}"""
        self.font_info_label.config(text=info_text)

    def open_font_settings(self):
        FontSettingsWindow(self.master, self.font_settings, 
                          self.update_font_info, self.save_default_font_settings)

    def show_preview(self):
        try:
            if not hasattr(self, 'preview_window') or not self.preview_window.window.winfo_exists():
                self.preview_window = SimplePreviewWindow(self.master, self.font_settings)
            else:
                self.preview_window.refresh()
                self.preview_window.window.lift()
        except Exception as e:
            messagebox.showerror("❌ Hata", f"Önizleme açılırken hata: {e}")

    def save_font_settings(self):
        """Manuel farklı kaydet"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.font_settings.to_dict(), f, ensure_ascii=False, indent=2)
                messagebox.showinfo("✅ Başarılı", f"Font ayarları kaydedildi:\n{filename}")
            except Exception as e:
                messagebox.showerror("❌ Hata", f"Kaydetme hatası: {e}")

    def load_font_settings(self):
        """Dosyadan yükle"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.font_settings.from_dict(data)
                self.update_font_info()
                # Otomatik kaydet
                self.save_default_font_settings()
                messagebox.showinfo("✅ Başarılı", f"Font ayarları yüklendi:\n{filename}")
            except Exception as e:
                messagebox.showerror("❌ Hata", f"Font ayarları yüklenirken hata: {e}")

    # File browser methods
    # 🧹 REFACTORED: Birleştirilmiş dosya tarayıcı fonksiyonları
    def _browse_file(self, file_type, target_vars):
        """Genel dosya tarayıcı - kod tekrarını azaltır"""
        filetypes_map = {
            'video': [("Video files", "*.mp4 *.avi *.mkv *.mov"), ("All files", "*.*")],
            'srt': [("SRT files", "*.srt"), ("All files", "*.*")],
            'executable': [("Executable files", "*.exe *.bin"), ("All files", "*.*")]
        }
        
        filename = filedialog.askopenfilename(filetypes=filetypes_map.get(file_type, [("All files", "*.*")]))
        if filename:
            # Birden fazla değişkene aynı değeri ata
            for var in target_vars:
                var.set(filename)
    
    def browse_video(self):
        self._browse_file('video', [self.video_path, self.video_path_embed])
    
    def browse_srt_for_translation(self):
        self._browse_file('srt', [self.srt_path_translate])
    
    def browse_video_for_embedding(self):
        self._browse_file('video', [self.video_path_embed])
    
    def browse_srt_for_embedding(self):
        self._browse_file('srt', [self.srt_path_embed])

    def add_model(self):
        new_model = simpledialog.askstring("➕ Model Ekle", 
                                          "Yeni OpenRouter model adını girin:", 
                                          parent=self.master)
        if new_model and new_model.strip():
            new_model = new_model.strip()
            if new_model not in self.translation_models:
                self.translation_models.append(new_model)
                self.translation_model.set(new_model)
                if self.save_models(show_message=False):
                    messagebox.showinfo("✅ Başarılı", 
                                      f"Model eklendi ve kaydedildi: {new_model}")
            else:
                messagebox.showwarning("⚠️ Uyarı", "Bu model zaten listede mevcut!")

    def remove_model(self):
        current = self.translation_model.get().strip()
        if not current:
            messagebox.showwarning("⚠️ Uyarı", 
                                 "Lütfen listeden silmek istediğiniz modeli seçin.")
            return

        if current not in self.translation_models:
            messagebox.showerror("❌ Hata", "Seçili model listede bulunamadı.")
            return

        if not messagebox.askyesno("❓ Modeli Sil", 
                                   f"'{current}' modelini listeden silmek istediğinize emin misiniz?"):
            return

        self.translation_models.remove(current)
        if self.save_models(show_message=False):
            messagebox.showinfo("✅ Başarılı", 
                              f"Model silindi ve kaydedildi: {current}")
        
    def update_progress(self, type, value):
        """Thread-safe UI güncelleme fonksiyonu"""
        def _update():
            if type == "status":
                self.status_label.config(text=value)
                # Status rengini güncelle
                if "✅" in value or "tamamlandı" in value.lower():
                    self.status_label.config(fg='#4caf50')
                elif "❌" in value or "hata" in value.lower():
                    self.status_label.config(fg='#f44336')
                elif "🔄" in value:
                    self.status_label.config(fg='#2196f3')
                else:
                    self.status_label.config(fg='#ff9800')
            elif type == "progress":
                self.progress['value'] = value
        
        # Thread-safe UI güncellemesi için after() kullan
        self.master.after(0, _update)

    # Threading methods for long operations
    def start_transcription_thread(self):
        video_file = self.video_path.get()
        output_name = self.output_name.get()
        selected_language_name = self.language_selection.get()
        lang = self.language_options[selected_language_name]
        
        if not video_file:
            messagebox.showerror("❌ Hata", "Lütfen bir video dosyası seçin.")
            return
        
        self.progress['value'] = 0
        self.status_label.config(text="🚀 İşlem başlatılıyor...")
        threading.Thread(target=self._run_transcription, 
                        args=(video_file, output_name, lang)).start()

    def _run_transcription(self, video_file, output_name, lang):
        try:
            video_p = Path(video_file)
            base_output_dir = video_p.parent / f"{video_p.stem}_ciktilar"
            transcription_dir = base_output_dir / "transcription"
            os.makedirs(transcription_dir, exist_ok=True)
            
            transcriber = VideoTranscriber(
                silence_threshold=self.silence_threshold_var.get(),
                min_silence_duration=self.min_silence_duration_var.get(),
                speech_protection=self.speech_protection_var.get(),
                remove_silence=self.remove_silence_var.get(),
                remove_background_noise=self.remove_background_noise_var.get(),
            )
            result = transcriber.transcribe_video(video_file, language=lang, 
                                                 progress_callback=self.update_progress)
            
            if not result:
                messagebox.showerror("❌ Hata", "Transkript başarısız oldu.")
                self.update_progress("status", "❌ Hata")
                self.progress['value'] = 0
                return
            
            base_name = output_name if output_name else video_p.stem
            json_path = transcription_dir / f"{base_name}.json"
            srt_path = transcription_dir / f"{base_name}.srt"
            
            json_data = transcriber.save_json(result, str(json_path))
            SRTConverter.json_to_srt(json_data, str(srt_path))
            
            detected_lang = result.get('language')
            success_message = f"✅ Transkript tamamlandı!\n\n📁 Çıktı klasörü:\n{transcription_dir}"
            
            if detected_lang:
                self.language.set(detected_lang)
                display_lang_name = detected_lang
                for name, code in self.language_options.items():
                    if code == detected_lang:
                        display_lang_name = name
                        break
                success_message = f"✅ Transkript tamamlandı!\n\n🌐 Algılanan Dil: {display_lang_name}\n\n📁 Çıktı klasörü:\n{transcription_dir}"
            
            messagebox.showinfo("🎉 Başarılı", success_message)
            self.update_progress("status", "✅ Transkript tamamlandı!")
            self.progress['value'] = 100
            
            self.srt_path_translate.set(str(srt_path))
            self.srt_path_embed.set(str(srt_path))
            
        except Exception as e:
            messagebox.showerror("❌ Hata", 
                               f"Transkripsiyon sırasında bir hata oluştu:\n{e}")
            self.update_progress("status", "❌ Hata oluştu")
            self.progress['value'] = 0

    def start_translation_thread(self):
        srt_file = self.srt_path_translate.get()
        
        # DİL SEÇİMLERİNİ AL
        source_lang_name = self.source_language_selection.get()
        target_lang_name = self.target_language_selection.get()
        
        source_lang = self.source_lang_options.get(source_lang_name, 'auto')
        target_lang = self.target_lang_options.get(target_lang_name, 'en')
        
        fix_spelling = self.fix_spelling_var.get()
        model_name = self.translation_model.get()
        
        if not srt_file:
            messagebox.showerror("❌ Hata", "Lütfen çevrilecek bir SRT dosyası seçin.")
            return
        
        # Yazım düzeltme kontrolü
        if fix_spelling and source_lang != target_lang:
            if not messagebox.askyesno("❓ Onay",
                                       "Yazım düzeltme seçili ama kaynak ve hedef diller farklı.\n\n"
                                       f"'{source_lang_name}' → '{target_lang_name}' çevirisi yapılacak.\n\n"
                                       "Devam etmek istiyor musunuz?"):
                return
        
        if not model_name:
            messagebox.showerror("❌ Hata", "Lütfen bir çeviri modeli seçin.")
            return
        
        self.progress['value'] = 0
        self.status_label.config(text=f"🔄 Çeviri başlatılıyor: {source_lang_name} → {target_lang_name}...")
        threading.Thread(target=self._run_translation, 
                        args=(srt_file, target_lang, source_lang, fix_spelling, model_name)).start()

    def _run_translation(self, srt_file, target_lang, source_lang, fix_spelling, model_name):
        try:
            srt_p = Path(srt_file)
            base_output_dir = None
            
            if srt_p.parent.name == "transcription" and srt_p.parent.parent.name.endswith("_ciktilar"):
                base_output_dir = srt_p.parent.parent
            else:
                base_output_dir = srt_p.parent / f"{srt_p.stem}_ciktilar"
            
            translation_dir = base_output_dir / "translation"
            
            # KAYNAK DİL OTOMATİK ALGILAMA
            if source_lang == 'auto':
                # Transkripsiyon dilinden al
                detected = self.language.get() if self.language.get() else 'tr'
                print(f"🔍 Kaynak dil otomatik algılandı: {detected}")
                source_lang = detected
            
            translator = SRTTranslator(model=model_name)
            processed_srt_path = translator.translate_srt_file(
                srt_file, target_lang, source_lang, fix_spelling, 
                progress_callback=self.update_progress, output_dir=translation_dir
            )
            
            # Dil isimlerini al
            source_name = self.get_language_display_name(source_lang)
            target_name = self.get_language_display_name(target_lang)
            
            messagebox.showinfo("🎉 Başarılı", 
                              f"✅ Çeviri tamamlandı!\n\n"
                              f"📤 Kaynak: {source_name}\n"
                              f"📥 Hedef: {target_name}\n\n"
                              f"📄 Yeni dosya:\n{processed_srt_path}")
            self.update_progress("status", "✅ Çeviri tamamlandı!")
            self.progress['value'] = 100
            
            self.srt_path_embed.set(processed_srt_path)
            
        except Exception as e:
            messagebox.showerror("❌ Hata", 
                               f"Çeviri/Düzeltme sırasında bir hata oluştu:\n{e}")
            self.update_progress("status", "❌ Hata oluştu")
            self.progress['value'] = 0

    def start_embedding_thread(self):
        video_file_embed = self.video_path_embed.get()
        srt_file_embed = self.srt_path_embed.get()
        embed_type = self.embed_type.get()
        
        if not video_file_embed or not srt_file_embed:
            messagebox.showerror("❌ Hata", "Lütfen video ve SRT dosyalarını seçin.")
            return
        
        self.progress['value'] = 0
        self.status_label.config(text="🔄 Altyazı gömme başlatılıyor...")
        threading.Thread(target=self._run_embedding, 
                        args=(video_file_embed, srt_file_embed, embed_type)).start()

    def _run_embedding(self, video_file_embed, srt_file_embed, embed_type):
        try:
            video_p = Path(video_file_embed)
            srt_p = Path(srt_file_embed)
            base_output_dir = None
            
            if srt_p.parent.name in ["transcription", "translation"] and srt_p.parent.parent.name.endswith("_ciktilar"):
                base_output_dir = srt_p.parent.parent
            elif (video_p.parent / f"{video_p.stem}_ciktilar").exists():
                base_output_dir = video_p.parent / f"{video_p.stem}_ciktilar"
            else:
                base_output_dir = video_p.parent / f"{video_p.stem}_ciktilar"
            
            embed_dir = base_output_dir / "embedded"
            os.makedirs(embed_dir, exist_ok=True)
            
            output_video_path = None
            
            if embed_type == "soft":
                output_path = embed_dir / f"{video_p.stem}_softsub.mkv"
                output_video_path = SubtitleEmbedder.embed_soft_subtitles(
                    video_file_embed, srt_file_embed, output_path=output_path, 
                    progress_callback=self.update_progress, font_settings=self.font_settings
                )
            elif embed_type == "hard":
                output_path = embed_dir / f"{video_p.stem}_hardsub.mp4"
                output_video_path = SubtitleEmbedder.embed_hard_subtitles(
                    video_file_embed, srt_file_embed, output_path=output_path, 
                    progress_callback=self.update_progress, font_settings=self.font_settings
                )
            
            if output_video_path:
                self.update_progress("status", "✅ Altyazı eklendi!")
                self.progress['value'] = 100
                should_open_video = messagebox.askyesno(
                    "🎉 Başarılı",
                    f"✅ Altyazı videoya gömüldü!\n\n🎬 Video:\n{output_video_path}\n\n"
                    f"Oluşan videoyu açmak istiyor musunuz?"
                )
                if should_open_video:
                    try:
                        self._open_path(output_video_path)
                    except Exception as open_error:
                        messagebox.showerror(
                            "❌ Hata",
                            f"Oluşan video açılamadı:\n{open_error}"
                        )
            else:
                messagebox.showerror("❌ Hata", 
                                   "Altyazı gömme başarısız oldu.\nPaket içi FFmpeg dosyalarının mevcut olduğundan emin olun.")
                self.update_progress("status", "❌ Hata oluştu")
                self.progress['value'] = 0
                
        except Exception as e:
            messagebox.showerror("❌ Hata", 
                               f"Altyazı gömme sırasında bir hata oluştu:\n{e}")
            self.update_progress("status", "❌ Hata oluştu")
            self.progress['value'] = 0

    # Silence Removal Tab
    def create_silence_tab(self, parent):
        """Sessizlik budama sekmesi oluştur"""
        # Scrollable container
        canvas = tk.Canvas(parent, bg='#1e1e1e', highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        main_frame = tk.Frame(canvas, bg='#1e1e1e')
        
        main_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=main_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 🖱️ Mouse wheel scroll desteği ekle
        self.bind_mousewheel(canvas)
        
        # Title
        title_label = tk.Label(main_frame, text="🔇 Sessizlik Budama (Silence Removal)", 
                              bg='#1e1e1e', fg='white', 
                              font=('Segoe UI', 16, 'bold'))
        title_label.pack(pady=(20, 10), padx=20)
        
        # Description
        desc_label = tk.Label(main_frame, 
                             text="Video veya ses dosyalarındaki sessiz bölümleri otomatik olarak kaldırın.\n"
                                  "Altyazı transkripsiyon veya bağımsız video işleme için kullanabilirsiniz.", 
                             bg='#1e1e1e', fg='#aaaaaa', 
                             font=('Segoe UI', 10), justify='center')
        desc_label.pack(pady=(0, 20), padx=20)
        
        # ============ BAĞIMSIZ VİDEO İŞLEME BÖLÜMÜ ============
        video_process_frame = tk.LabelFrame(main_frame, text=" 🎬 Bağımsız Video İşleme ", 
                                           bg='#1e1e1e', fg='white', 
                                           font=('Segoe UI', 13, 'bold'),
                                           relief=tk.RIDGE, bd=2)
        video_process_frame.pack(fill="x", padx=20, pady=10)
        
        video_desc = tk.Label(video_process_frame, 
                             text="Video dosyanızı seçin, sessizlik budama ayarlarını yapın ve işleyin.", 
                             bg='#1e1e1e', fg='#aaaaaa', 
                             font=('Segoe UI', 9), justify='left')
        video_desc.pack(padx=15, pady=(10, 5), anchor='w')
        
        # Video seçimi
        video_select_frame = tk.Frame(video_process_frame, bg='#1e1e1e')
        video_select_frame.pack(fill="x", padx=15, pady=10)
        
        tk.Label(video_select_frame, text="Video/Ses Dosyası:", 
                bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=5)
        
        self.silence_video_path = tk.StringVar()
        video_entry = tk.Entry(video_select_frame, textvariable=self.silence_video_path, 
                              bg='#2b2b2b', fg='white', relief=tk.FLAT, 
                              font=('Segoe UI', 9), insertbackground='white')
        video_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        browse_video_btn = tk.Button(video_select_frame, text="📂 Gözat", 
                                     command=self.browse_silence_video, 
                                     bg='#0d7377', fg='white', 
                                     relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                                     padx=15, pady=5, cursor='hand2')
        browse_video_btn.pack(side=tk.RIGHT, padx=5)
        
        # Sessizlik budama ayarları (video için)
        video_settings_frame = tk.LabelFrame(video_process_frame, text=" ⚙️ Sessizlik Budama Ayarları ", 
                                            bg='#1e1e1e', fg='white', 
                                            font=('Segoe UI', 10, 'bold'))
        video_settings_frame.pack(fill="x", padx=15, pady=10)
        
        # Eşik değeri
        video_threshold_frame = tk.Frame(video_settings_frame, bg='#1e1e1e')
        video_threshold_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Label(video_threshold_frame, text="Sessizlik Eşiği (dB):", 
                bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=5)
        
        self.video_silence_threshold_var = tk.DoubleVar(value=-40.0)
        video_threshold_scale = ttk.Scale(video_threshold_frame, from_=-60, to=-20, 
                                         variable=self.video_silence_threshold_var, 
                                         orient=tk.HORIZONTAL, length=250,
                                         command=self.update_video_threshold_label)
        video_threshold_scale.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.video_threshold_spinbox = ttk.Spinbox(
            video_threshold_frame,
            from_=-60.0,
            to=-20.0,
            increment=0.5,
            textvariable=self.video_silence_threshold_var,
            width=7,
            command=lambda: self.update_video_threshold_label(self.video_silence_threshold_var.get())
        )
        self.video_threshold_spinbox.pack(side=tk.LEFT, padx=(0, 8))
        self.video_threshold_spinbox.bind(
            "<KeyRelease>",
            lambda event: self.update_video_threshold_label(self.video_silence_threshold_var.get())
        )
        self.video_threshold_spinbox.bind(
            "<FocusOut>",
            lambda event: self.update_video_threshold_label(self.video_silence_threshold_var.get())
        )
        
        self.video_threshold_label = tk.Label(video_threshold_frame, 
                                              text=f"{self.video_silence_threshold_var.get():.1f} dB", 
                                              bg='#1e1e1e', fg='#0d7377', 
                                              font=('Segoe UI', 10, 'bold'), width=9)
        self.video_threshold_label.pack(side=tk.LEFT, padx=5)
        
        # Minimum süre
        video_duration_frame = tk.Frame(video_settings_frame, bg='#1e1e1e')
        video_duration_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Label(video_duration_frame, text="Min. Sessizlik Süresi (sn):", 
                bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=5)
        
        self.video_min_silence_var = tk.DoubleVar(value=0.5)
        video_duration_scale = ttk.Scale(video_duration_frame, from_=0.1, to=2.0, 
                                        variable=self.video_min_silence_var, 
                                        orient=tk.HORIZONTAL, length=250,
                                        command=self.update_video_duration_label)
        video_duration_scale.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.video_duration_spinbox = ttk.Spinbox(
            video_duration_frame,
            from_=0.1,
            to=2.0,
            increment=0.05,
            textvariable=self.video_min_silence_var,
            width=7,
            command=lambda: self.update_video_duration_label(self.video_min_silence_var.get())
        )
        self.video_duration_spinbox.pack(side=tk.LEFT, padx=(0, 8))
        self.video_duration_spinbox.bind(
            "<KeyRelease>",
            lambda event: self.update_video_duration_label(self.video_min_silence_var.get())
        )
        self.video_duration_spinbox.bind(
            "<FocusOut>",
            lambda event: self.update_video_duration_label(self.video_min_silence_var.get())
        )
        
        self.video_duration_label = tk.Label(video_duration_frame, 
                                             text=f"{self.video_min_silence_var.get():.2f} sn", 
                                             bg='#1e1e1e', fg='#0d7377', 
                                             font=('Segoe UI', 10, 'bold'), width=9)
        self.video_duration_label.pack(side=tk.LEFT, padx=5)

        video_protection_frame = tk.Frame(video_settings_frame, bg='#1e1e1e')
        video_protection_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(video_protection_frame, text="Konuşma Koruması:",
                bg='#1e1e1e', fg='white',
                font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=5)

        self.video_manual_protection_check = tk.Checkbutton(
            video_protection_frame,
            text="Elle ayarla",
            variable=self.manual_video_speech_protection_var,
            command=self.toggle_video_manual_protection,
            bg='#1e1e1e',
            fg='white',
            selectcolor='#404040',
            activebackground='#1e1e1e',
            font=('Segoe UI', 9)
        )
        self.video_manual_protection_check.pack(side=tk.LEFT, padx=(0, 8))

        self.video_speech_protection_var = tk.DoubleVar(value=0.35)
        self.video_protection_scale = ttk.Scale(
            video_protection_frame,
            from_=SPEECH_PROTECTION_MANUAL_MIN,
            to=SPEECH_PROTECTION_MANUAL_MAX,
            variable=self.video_speech_protection_var,
            orient=tk.HORIZONTAL,
            length=250,
            command=self.update_video_protection_label
        )
        self.video_protection_scale.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.video_protection_spinbox = ttk.Spinbox(
            video_protection_frame,
            from_=SPEECH_PROTECTION_MANUAL_MIN,
            to=SPEECH_PROTECTION_MANUAL_MAX,
            increment=SPEECH_PROTECTION_STEP,
            textvariable=self.video_speech_protection_var,
            width=7,
            command=lambda: self.update_video_protection_label(self.video_speech_protection_var.get())
        )
        self.video_protection_spinbox.pack(side=tk.LEFT, padx=(0, 8))
        self.video_protection_spinbox.bind(
            "<KeyRelease>",
            lambda event: self.update_video_protection_label(self.video_speech_protection_var.get())
        )
        self.video_protection_spinbox.bind(
            "<FocusOut>",
            lambda event: self.update_video_protection_label(self.video_speech_protection_var.get())
        )

        self.video_protection_label = tk.Label(
            video_protection_frame,
            text=f"{self.video_speech_protection_var.get():.2f} sn",
            bg='#1e1e1e',
            fg='#0d7377',
            font=('Segoe UI', 10, 'bold'),
            width=9
        )
        self.video_protection_label.pack(side=tk.LEFT, padx=5)

        self.video_protection_info_label = tk.Label(
            video_settings_frame,
            text="💡 İsterseniz elle ayarlayabilirsiniz; otomatik modda eşik yükseldikçe koruma artar, minimum süre düştüğünde şişmez.",
            bg='#1e1e1e',
            fg='#666666',
            font=('Segoe UI', 8)
        )
        self.video_protection_info_label.pack(fill="x", padx=15, pady=(0, 5))

        video_cleanup_frame = tk.Frame(video_settings_frame, bg='#1e1e1e')
        video_cleanup_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.video_cleanup_check = tk.Checkbutton(
            video_cleanup_frame,
            text="🔉 Dip/Cızırtı Temizle (güvenli preset)",
            variable=self.video_remove_background_noise_var,
            bg='#1e1e1e',
            fg='white',
            selectcolor='#404040',
            activebackground='#1e1e1e',
            font=('Segoe UI', 10, 'bold')
        )
        self.video_cleanup_check.pack(side=tk.LEFT, padx=5)

        tk.Label(
            video_settings_frame,
            text="💡 Bu seçenek açıkken ses filtresi uygulanır; hızlı kopya modları kapanır ve çıktı biraz daha yavaş hazırlanır.",
            bg='#1e1e1e',
            fg='#666666',
            font=('Segoe UI', 8)
        ).pack(fill="x", padx=15, pady=(0, 5))

        video_profile_frame = tk.Frame(video_settings_frame, bg='#1e1e1e')
        video_profile_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(video_profile_frame, text="İşleme Profili:",
                bg='#1e1e1e', fg='white',
                font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=5)

        self.video_profile_combo = ttk.Combobox(
            video_profile_frame,
            textvariable=self.video_trim_profile_var,
            values=list(VIDEO_TRIM_ENCODING_PROFILES.keys()),
            state="readonly",
            width=14
        )
        self.video_profile_combo.pack(side=tk.LEFT, padx=10)

        profile_hint = tk.Label(
            video_settings_frame,
            text="💡 Hız = en hızlı, Dengeli = önerilen, Kalite = daha yavaş ama daha temiz çıktı",
            bg='#1e1e1e', fg='#666666',
            font=('Segoe UI', 8), justify='left'
        )
        profile_hint.pack(padx=15, pady=(0, 10), anchor='w')

        # İşlem butonu
        process_video_btn = tk.Button(video_process_frame, text="🚀 Videoyu İşle", 
                                      command=self.process_video_silence, 
                                      bg='#28a745', fg='white', 
                                      relief=tk.FLAT, font=('Segoe UI', 11, 'bold'), 
                                      padx=30, pady=12, cursor='hand2')
        process_video_btn.pack(pady=15)
        
        # Progress bar (video için)
        self.video_progress_var = tk.DoubleVar()
        self.video_progress_bar = ttk.Progressbar(video_process_frame, 
                                                  variable=self.video_progress_var, 
                                                  maximum=100, mode='determinate')
        self.video_progress_bar.pack(fill="x", padx=15, pady=(0, 10))
        
        self.video_status_label = tk.Label(video_process_frame, text="", 
                                           bg='#1e1e1e', fg='#aaaaaa', 
                                           font=('Segoe UI', 9))
        self.video_status_label.pack(pady=(0, 15))
        
        # Ayırıcı
        separator = ttk.Separator(main_frame, orient='horizontal')
        separator.pack(fill='x', padx=20, pady=20)
        
        # ============ ALTYAZI TRANSKRİPSİYON AYARLARI ============
        subtitle_frame = tk.LabelFrame(main_frame, text=" 📝 Altyazı Transkripsiyon Ayarları ", 
                                      bg='#1e1e1e', fg='white', 
                                      font=('Segoe UI', 13, 'bold'),
                                      relief=tk.RIDGE, bd=2)
        subtitle_frame.pack(fill="x", padx=20, pady=10)
        
        subtitle_desc = tk.Label(subtitle_frame, 
                                text="Bu ayarlar Ana İşlemler sekmesindeki transkripsiyon için kullanılır.", 
                                bg='#1e1e1e', fg='#aaaaaa', 
                                font=('Segoe UI', 9), justify='left')
        subtitle_desc.pack(padx=15, pady=(10, 5), anchor='w')

        cleanup_frame = tk.Frame(subtitle_frame, bg='#1e1e1e')
        cleanup_frame.pack(fill="x", padx=20, pady=(5, 0))

        self.cleanup_check = tk.Checkbutton(
            cleanup_frame,
            text="🔉 Dip/Cızırtı Temizle (güvenli preset)",
            variable=self.remove_background_noise_var,
            bg='#1e1e1e',
            fg='white',
            selectcolor='#404040',
            activebackground='#1e1e1e',
            font=('Segoe UI', 10, 'bold')
        )
        self.cleanup_check.pack(side=tk.LEFT)

        cleanup_hint = tk.Label(
            subtitle_frame,
            text="💡 Transkripsiyon öncesi highpass + FFT tabanlı hafif gürültü azaltma uygulanır.",
            bg='#1e1e1e',
            fg='#666666',
            font=('Segoe UI', 8)
        )
        cleanup_hint.pack(padx=20, pady=(2, 8), anchor='w')
        
        # Enable/Disable
        enable_frame = tk.Frame(subtitle_frame, bg='#1e1e1e')
        enable_frame.pack(fill="x", padx=20, pady=15)
        
        enable_check = tk.Checkbutton(enable_frame, 
                                     text="🔇 Transkripsiyon için Sessizlik Budamayı Etkinleştir", 
                                     variable=self.remove_silence_var, 
                                     bg='#1e1e1e', fg='white', 
                                     selectcolor='#404040', 
                                     font=('Segoe UI', 11, 'bold'), 
                                     activebackground='#1e1e1e',
                                     command=self.toggle_silence_controls)
        enable_check.pack(side=tk.LEFT)
        
        # Settings Frame
        settings_frame = tk.LabelFrame(subtitle_frame, text=" ⚙️ Sessizlik Budama Ayarları ", 
                                      bg='#1e1e1e', fg='white', 
                                      font=('Segoe UI', 10, 'bold'))
        settings_frame.pack(fill="x", padx=20, pady=10)
        
        # Threshold Setting
        threshold_frame = tk.LabelFrame(settings_frame, text=" 📊 Sessizlik Eşiği ", 
                                       bg='#1e1e1e', fg='white', 
                                       font=('Segoe UI', 10, 'bold'))
        threshold_frame.pack(fill="x", padx=20, pady=10)
        
        threshold_desc = tk.Label(threshold_frame, 
                                 text="Hangi ses seviyesinin 'sessiz' sayılacağını belirler (dB cinsinden)", 
                                 bg='#1e1e1e', fg='#888888', 
                                 font=('Segoe UI', 9), justify='left')
        threshold_desc.pack(padx=10, pady=(10, 5), anchor='w')
        
        threshold_control = tk.Frame(threshold_frame, bg='#1e1e1e')
        threshold_control.pack(fill="x", padx=10, pady=10)
        
        tk.Label(threshold_control, text="Eşik Değeri:", 
                bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=5)
        
        self.threshold_scale = ttk.Scale(threshold_control, from_=-60, to=-20, 
                                        variable=self.silence_threshold_var, 
                                        orient=tk.HORIZONTAL, length=300,
                                        command=self.update_threshold_label)
        self.threshold_scale.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.threshold_spinbox = ttk.Spinbox(
            threshold_control,
            from_=-60.0,
            to=-20.0,
            increment=0.5,
            textvariable=self.silence_threshold_var,
            width=7,
            command=lambda: self.update_threshold_label(self.silence_threshold_var.get())
        )
        self.threshold_spinbox.pack(side=tk.LEFT, padx=(0, 8))
        self.threshold_spinbox.bind(
            "<KeyRelease>",
            lambda event: self.update_threshold_label(self.silence_threshold_var.get())
        )
        self.threshold_spinbox.bind(
            "<FocusOut>",
            lambda event: self.update_threshold_label(self.silence_threshold_var.get())
        )
        
        self.threshold_value_label = tk.Label(threshold_control, 
                                             text=f"{self.silence_threshold_var.get():.1f} dB", 
                                             bg='#1e1e1e', fg='#0d7377', 
                                             font=('Segoe UI', 10, 'bold'), width=9)
        self.threshold_value_label.pack(side=tk.LEFT, padx=5)
        
        threshold_info = tk.Label(threshold_frame, 
                                 text="💡 Önerilen: -40dB (Daha düşük değer = daha hassas)", 
                                 bg='#1e1e1e', fg='#666666', 
                                 font=('Segoe UI', 8))
        threshold_info.pack(padx=10, pady=(0, 10), anchor='w')
        
        # Duration Setting
        duration_frame = tk.LabelFrame(settings_frame, text=" ⏱️ Minimum Sessizlik Süresi ", 
                                      bg='#1e1e1e', fg='white', 
                                      font=('Segoe UI', 10, 'bold'))
        duration_frame.pack(fill="x", padx=20, pady=10)
        
        duration_desc = tk.Label(duration_frame, 
                                text="Ne kadar süren sessizliklerin kaldırılacağını belirler (saniye cinsinden)", 
                                bg='#1e1e1e', fg='#888888', 
                                font=('Segoe UI', 9), justify='left')
        duration_desc.pack(padx=10, pady=(10, 5), anchor='w')
        
        duration_control = tk.Frame(duration_frame, bg='#1e1e1e')
        duration_control.pack(fill="x", padx=10, pady=10)
        
        tk.Label(duration_control, text="Süre:", 
                bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=5)
        
        self.duration_scale = ttk.Scale(duration_control, from_=0.1, to=2.0, 
                                       variable=self.min_silence_duration_var, 
                                       orient=tk.HORIZONTAL, length=300,
                                       command=self.update_duration_label)
        self.duration_scale.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.duration_spinbox = ttk.Spinbox(
            duration_control,
            from_=0.1,
            to=2.0,
            increment=0.05,
            textvariable=self.min_silence_duration_var,
            width=7,
            command=lambda: self.update_duration_label(self.min_silence_duration_var.get())
        )
        self.duration_spinbox.pack(side=tk.LEFT, padx=(0, 8))
        self.duration_spinbox.bind(
            "<KeyRelease>",
            lambda event: self.update_duration_label(self.min_silence_duration_var.get())
        )
        self.duration_spinbox.bind(
            "<FocusOut>",
            lambda event: self.update_duration_label(self.min_silence_duration_var.get())
        )
        
        self.duration_value_label = tk.Label(duration_control, 
                                            text=f"{self.min_silence_duration_var.get():.2f} sn", 
                                            bg='#1e1e1e', fg='#0d7377', 
                                            font=('Segoe UI', 10, 'bold'), width=9)
        self.duration_value_label.pack(side=tk.LEFT, padx=5)
        
        duration_info = tk.Label(duration_frame, 
                                text="💡 Önerilen: 0.5 saniye (Daha uzun = daha az budama)", 
                                bg='#1e1e1e', fg='#666666', 
                                font=('Segoe UI', 8))
        duration_info.pack(padx=10, pady=(0, 10), anchor='w')

        protection_frame = tk.LabelFrame(settings_frame, text=" 🛡️ Konuşma Koruması ", 
                                        bg='#1e1e1e', fg='white', 
                                        font=('Segoe UI', 10, 'bold'))
        protection_frame.pack(fill="x", padx=20, pady=10)

        protection_desc = tk.Label(
            protection_frame,
            text="İsterseniz elle ayarlayabilirsiniz; otomatik modda ana etki eşiktedir, çok kısa minimum süre korumayı şişirmez.",
            bg='#1e1e1e',
            fg='#888888',
            font=('Segoe UI', 9),
            justify='left'
        )
        protection_desc.pack(padx=10, pady=(10, 5), anchor='w')

        protection_control = tk.Frame(protection_frame, bg='#1e1e1e')
        protection_control.pack(fill="x", padx=10, pady=10)

        self.protection_mode_label = tk.Label(
            protection_control,
            text="Otomatik Pay:",
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 10)
        )
        self.protection_mode_label.pack(side=tk.LEFT, padx=5)

        self.manual_protection_check = tk.Checkbutton(
            protection_control,
            text="Elle ayarla",
            variable=self.manual_speech_protection_var,
            command=self.toggle_manual_protection,
            bg='#1e1e1e',
            fg='white',
            selectcolor='#404040',
            activebackground='#1e1e1e',
            font=('Segoe UI', 9)
        )
        self.manual_protection_check.pack(side=tk.LEFT, padx=(0, 8))

        self.protection_scale = ttk.Scale(
            protection_control,
            from_=SPEECH_PROTECTION_MANUAL_MIN,
            to=SPEECH_PROTECTION_MANUAL_MAX,
            variable=self.speech_protection_var,
            orient=tk.HORIZONTAL,
            length=300,
            command=self.update_protection_label
        )
        self.protection_scale.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.protection_spinbox = ttk.Spinbox(
            protection_control,
            from_=SPEECH_PROTECTION_MANUAL_MIN,
            to=SPEECH_PROTECTION_MANUAL_MAX,
            increment=SPEECH_PROTECTION_STEP,
            textvariable=self.speech_protection_var,
            width=7,
            command=lambda: self.update_protection_label(self.speech_protection_var.get())
        )
        self.protection_spinbox.pack(side=tk.LEFT, padx=(0, 8))
        self.protection_spinbox.bind(
            "<KeyRelease>",
            lambda event: self.update_protection_label(self.speech_protection_var.get())
        )
        self.protection_spinbox.bind(
            "<FocusOut>",
            lambda event: self.update_protection_label(self.speech_protection_var.get())
        )

        self.protection_value_label = tk.Label(
            protection_control,
            text=f"{self.speech_protection_var.get():.2f} sn",
            bg='#1e1e1e',
            fg='#0d7377',
            font=('Segoe UI', 10, 'bold'),
            width=9
        )
        self.protection_value_label.pack(side=tk.LEFT, padx=5)

        self.protection_info_label = tk.Label(
            protection_frame,
            text="💡 Otomatik modda eşik yükseldikçe koruma artar; minimum süre düştüğünde koruma gereksiz büyümez.",
            bg='#1e1e1e',
            fg='#666666',
            font=('Segoe UI', 8)
        )
        self.protection_info_label.pack(padx=10, pady=(0, 10), anchor='w')
        
        # Info Box
        info_frame = tk.LabelFrame(main_frame, text=" ℹ️ Bilgi ", 
                                  bg='#1e1e1e', fg='white', 
                                  font=('Segoe UI', 11, 'bold'))
        info_frame.pack(fill="x", padx=20, pady=20)
        
        info_text = """
🎯 Sessizlik Budama Nedir?

Sessizlik budama, ses dosyasındaki sessiz (veya çok düşük sesli) bölümleri 
otomatik olarak tespit edip kaldırır. Bu sayede:

✅ Transkripsiyon süresi kısalır
✅ API maliyeti azalır
✅ İşlem daha hızlı tamamlanır
✅ Gereksiz sessizlikler temizlenir

⚙️ Nasıl Çalışır?

1. Ses dosyası analiz edilir
2. Belirlenen eşiğin altındaki sesler "sessiz" olarak işaretlenir
3. Minimum süreyi aşan sessizlikler kaldırılır
4. Sessiz olmayan konuşma parçaları transkript için kullanılır

⚠️ Önemli Notlar:

• Çok düşük eşik değerleri bazı konuşmaları da kaldırabilir
• Çok yüksek eşik değerleri sessizlikleri kaçırabilir
• Varsayılan ayarlar çoğu durum için uygundur
• İlk kullanımda varsayılan ayarlarla test edin
        """
        
        info_label = tk.Label(info_frame, text=info_text, 
                             bg='#1e1e1e', fg='#cccccc', 
                             font=('Segoe UI', 9), justify='left')
        info_label.pack(padx=15, pady=15, anchor='w')
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg='#1e1e1e')
        button_frame.pack(pady=20)
        
        reset_btn = tk.Button(button_frame, text="🔄 Varsayılana Dön", 
                             command=self.reset_silence_settings, 
                             bg='#ff6b6b', fg='white', 
                             relief=tk.FLAT, font=('Segoe UI', 10, 'bold'), 
                             padx=20, pady=10, cursor='hand2')
        reset_btn.pack(side=tk.LEFT, padx=5)
        
        test_btn = tk.Button(button_frame, text="🧪 Test Et", 
                            command=self.test_silence_removal, 
                            bg='#17a2b8', fg='white', 
                            relief=tk.FLAT, font=('Segoe UI', 10, 'bold'), 
                            padx=20, pady=10, cursor='hand2')
        test_btn.pack(side=tk.LEFT, padx=5)
        
        # Store controls for enable/disable
        self.silence_controls = [
            self.threshold_scale,
            self.threshold_spinbox,
            self.duration_scale,
            self.duration_spinbox,
            self.manual_protection_check,
            reset_btn, test_btn
        ]
        
        self.sync_video_auto_protection()
        self.sync_auto_protection()
        self.toggle_video_manual_protection()
        self.toggle_manual_protection()

        # Initial state
        self.toggle_silence_controls()

    def _snap_control_value(self, variable, value, step, minimum, maximum):
        try:
            source_value = variable.get() if value is None else value
            snapped_value = snap_numeric_value(
                source_value,
                step,
                minimum=minimum,
                maximum=maximum,
            )
        except (TypeError, ValueError, tk.TclError):
            return None

        try:
            current_value = float(variable.get())
        except (TypeError, ValueError, tk.TclError):
            current_value = None

        if current_value is None or abs(current_value - snapped_value) > 1e-9:
            variable.set(snapped_value)

        return snapped_value

    def _set_widget_state(self, widget, state):
        try:
            widget.config(state=state)
        except (tk.TclError, AttributeError):
            pass

    def _apply_manual_protection_mode(self, manual_var, scale, spinbox, label_widget, info_widget, parent_enabled=True):
        manual_enabled = bool(manual_var.get())
        input_state = 'normal' if (parent_enabled and manual_enabled) else 'disabled'
        self._set_widget_state(scale, input_state)
        self._set_widget_state(spinbox, input_state)

        if label_widget is not None:
            label_widget.config(text="Manuel Pay:" if manual_enabled else "Otomatik Pay:")

        if info_widget is not None:
            if manual_enabled:
                info_widget.config(
                    text="💡 Elle ayar açık. 0.05 sn adımlarla koruma payını doğrudan belirleyebilirsiniz."
                )
            else:
                info_widget.config(
                    text="💡 Otomatik modda eşik yükseldikçe koruma artar; minimum süre düştüğünde koruma gereksiz büyümez."
                )

    def _sync_auto_protection_value(self, threshold_var, duration_var, protection_var, manual_var=None, force=False):
        if manual_var is not None and manual_var.get() and not force:
            try:
                return float(protection_var.get())
            except (TypeError, ValueError, tk.TclError):
                return None

        try:
            protection_value = calculate_auto_speech_protection(
                threshold_var.get(),
                duration_var.get(),
            )
        except (TypeError, ValueError, tk.TclError):
            return None

        try:
            current_value = float(protection_var.get())
        except (TypeError, ValueError, tk.TclError):
            current_value = None

        if current_value is None or abs(current_value - protection_value) > 1e-9:
            protection_var.set(protection_value)

        return protection_value

    def sync_auto_protection(self, force=False):
        protection_value = self._sync_auto_protection_value(
            self.silence_threshold_var,
            self.min_silence_duration_var,
            self.speech_protection_var,
            manual_var=self.manual_speech_protection_var,
            force=force,
        )
        if protection_value is not None and hasattr(self, 'protection_value_label'):
            self.protection_value_label.config(text=f"{protection_value:.2f} sn")
        return protection_value

    def sync_video_auto_protection(self, force=False):
        protection_value = self._sync_auto_protection_value(
            self.video_silence_threshold_var,
            self.video_min_silence_var,
            self.video_speech_protection_var,
            manual_var=self.manual_video_speech_protection_var,
            force=force,
        )
        if protection_value is not None and hasattr(self, 'video_protection_label'):
            self.video_protection_label.config(text=f"{protection_value:.2f} sn")
        return protection_value

    def toggle_manual_protection(self):
        if not self.manual_speech_protection_var.get():
            self.sync_auto_protection(force=True)

        self._apply_manual_protection_mode(
            self.manual_speech_protection_var,
            getattr(self, 'protection_scale', None),
            getattr(self, 'protection_spinbox', None),
            getattr(self, 'protection_mode_label', None),
            getattr(self, 'protection_info_label', None),
            parent_enabled=self.remove_silence_var.get(),
        )
        self.update_protection_label(self.speech_protection_var.get())

    def toggle_video_manual_protection(self):
        if not self.manual_video_speech_protection_var.get():
            self.sync_video_auto_protection(force=True)

        self._apply_manual_protection_mode(
            self.manual_video_speech_protection_var,
            getattr(self, 'video_protection_scale', None),
            getattr(self, 'video_protection_spinbox', None),
            None,
            getattr(self, 'video_protection_info_label', None),
            parent_enabled=True,
        )
        self.update_video_protection_label(self.video_speech_protection_var.get())
    
    def update_threshold_label(self, value=None):
        """Eşik değeri etiketini güncelle"""
        numeric_value = self._snap_control_value(
            self.silence_threshold_var,
            value,
            SILENCE_THRESHOLD_STEP,
            -60.0,
            -20.0,
        )
        if numeric_value is None:
            return
        self.threshold_value_label.config(text=f"{numeric_value:.1f} dB")
        self.sync_auto_protection()
    
    def update_duration_label(self, value=None):
        """Süre değeri etiketini güncelle"""
        numeric_value = self._snap_control_value(
            self.min_silence_duration_var,
            value,
            SILENCE_DURATION_STEP,
            0.1,
            2.0,
        )
        if numeric_value is None:
            return
        self.duration_value_label.config(text=f"{numeric_value:.2f} sn")
        self.sync_auto_protection()

    def update_protection_label(self, value=None):
        """Konuşma koruması etiketini güncelle"""
        numeric_value = self._snap_control_value(
            self.speech_protection_var,
            value,
            SPEECH_PROTECTION_STEP,
            SPEECH_PROTECTION_MANUAL_MIN,
            SPEECH_PROTECTION_MANUAL_MAX,
        )
        if numeric_value is None:
            return
        self.protection_value_label.config(text=f"{numeric_value:.2f} sn")
    
    def update_video_threshold_label(self, value=None):
        """Video eşik değeri etiketini güncelle"""
        numeric_value = self._snap_control_value(
            self.video_silence_threshold_var,
            value,
            SILENCE_THRESHOLD_STEP,
            -60.0,
            -20.0,
        )
        if numeric_value is None:
            return
        self.video_threshold_label.config(text=f"{numeric_value:.1f} dB")
        self.sync_video_auto_protection()
    
    def update_video_duration_label(self, value=None):
        """Video süre değeri etiketini güncelle"""
        numeric_value = self._snap_control_value(
            self.video_min_silence_var,
            value,
            SILENCE_DURATION_STEP,
            0.1,
            2.0,
        )
        if numeric_value is None:
            return
        self.video_duration_label.config(text=f"{numeric_value:.2f} sn")
        self.sync_video_auto_protection()

    def update_video_protection_label(self, value=None):
        """Video konuşma koruması etiketini güncelle"""
        numeric_value = self._snap_control_value(
            self.video_speech_protection_var,
            value,
            SPEECH_PROTECTION_STEP,
            SPEECH_PROTECTION_MANUAL_MIN,
            SPEECH_PROTECTION_MANUAL_MAX,
        )
        if numeric_value is None:
            return
        self.video_protection_label.config(text=f"{numeric_value:.2f} sn")
    
    def toggle_silence_controls(self):
        """Sessizlik budama kontrollerini etkinleştir/devre dışı bırak"""
        state = 'normal' if self.remove_silence_var.get() else 'disabled'
        for control in self.silence_controls:
            try:
                control.config(state=state)
            except:
                pass
        if hasattr(self, 'manual_protection_check'):
            self.toggle_manual_protection()
    
    def browse_silence_video(self):
        """Sessizlik budama için video seç"""
        file_path = filedialog.askopenfilename(
            title="Video/Ses Dosyası Seçin",
            filetypes=[
                ("Video/Ses Dosyaları", "*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.mp3 *.wav *.m4a"),
                ("Video Dosyaları", "*.mp4 *.avi *.mkv *.mov *.flv *.wmv"),
                ("Ses Dosyaları", "*.mp3 *.wav *.m4a *.aac *.flac"),
                ("Tüm Dosyalar", "*.*")
            ]
        )
        if file_path:
            self.silence_video_path.set(file_path)
            self.video_status_label.config(text=f"✅ Dosya seçildi: {Path(file_path).name}")
    
    def process_video_silence(self):
        """Video için sessizlik budama işlemi"""
        video_path = self.silence_video_path.get()
        
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("❌ Hata", "Lütfen geçerli bir video/ses dosyası seçin!")
            return
        
        # Thread'de işle
        thread = threading.Thread(target=self._process_video_silence_thread, args=(video_path,))
        thread.daemon = True
        thread.start()
    
    def _process_video_silence_thread(self, video_path):
        """Video veya ses dosyasındaki sessizlikleri tek FFmpeg geçişiyle buda."""
        filter_script_path = None
        batch_temp_dir = None

        try:
            self.video_status_label.config(text="🔄 İşlem başlatılıyor...")
            self.video_progress_var.set(10)

            video_p = Path(video_path)
            output_dir = video_p.parent / f"{video_p.stem}_sessizlik_budanmis"
            output_dir.mkdir(exist_ok=True)

            self.video_status_label.config(text="🔍 Sessizlikler tespit ediliyor...")
            self.video_progress_var.set(25)

            ffmpeg_binary = resolve_ffmpeg_path()
            ffprobe_path = resolve_ffprobe_path(ffmpeg_binary)
            selected_trim_profile = VIDEO_TRIM_ENCODING_PROFILES.get(
                self.video_trim_profile_var.get(),
                VIDEO_TRIM_ENCODING_PROFILES['Dengeli']
            )
            selected_trim_profile_name = self.video_trim_profile_var.get()
            selected_trim_profile_key = selected_trim_profile['key']
            threshold = self.video_silence_threshold_var.get()
            min_duration = self.video_min_silence_var.get()
            speech_protection = self.video_speech_protection_var.get()
            audio_cleanup_filter = get_audio_cleanup_filter_chain(
                'safe' if self.video_remove_background_noise_var.get() else 'off'
            )
            protection_profile = calculate_speech_protection_profile(
                threshold,
                min_duration,
                speech_protection
            )
            if audio_cleanup_filter:
                print("🔉 Dip ses temizleme aktif: güvenli preset uygulanacak, hızlı kopya modları kapatıldı")
            media_info = get_media_stream_info(video_path, ffprobe_path)

            total_duration = get_media_duration(video_path, ffprobe_path)
            if not total_duration:
                raise Exception("Dosya süresi okunamadı")

            silence_intervals = detect_silence_intervals(
                ffmpeg_binary,
                video_path,
                threshold,
                min_duration,
                total_duration=total_duration,
                audio_filters=audio_cleanup_filter
            )
            print(f"🔍 {len(silence_intervals)} ham sessizlik aralığı tespit edildi")

            silence_intervals = merge_close_intervals(silence_intervals, gap_threshold=0.2)
            print(f"✅ {len(silence_intervals)} sessizlik aralığı (birleştirme sonrası)")

            if not silence_intervals:
                raise Exception("Sessizlik tespit edilemedi. Eşik değerini artırmayı deneyin.")

            self.video_status_label.config(text=f"✂️ Video ve ses kırpılıyor... Profil: {selected_trim_profile_name}")
            self.video_progress_var.set(45)

            silence_intervals = apply_padding_to_silence_intervals(
                silence_intervals,
                total_duration,
                padding_after_speech=protection_profile['padding_after_speech'],
                padding_before_speech=protection_profile['padding_before_speech']
            )
            silence_intervals = merge_close_intervals(silence_intervals, gap_threshold=0.05)
            print(
                "🛡️ Konuşma koruması uygulandı: "
                f"otomatik_pay={protection_profile['speech_protection']:.2f}s, "
                f"başlangıç={protection_profile['padding_before_speech']:.2f}s, "
                f"bitiş={protection_profile['padding_after_speech']:.2f}s"
            )

            min_clip_duration = 0.1
            keep_intervals = invert_intervals(silence_intervals, total_duration, min_clip_duration=min_clip_duration)
            if not keep_intervals:
                raise Exception(f"Hiç geçerli video parçası bulunamadı. Tüm parçalar {min_clip_duration}s'den kısa.\nEşik değerini azaltmayı veya minimum sessizlik süresini artırmayı deneyin.")

            condensed_intervals = condense_keep_intervals(keep_intervals, target_max_segments=120)
            if len(condensed_intervals) != len(keep_intervals):
                print(f"🔗 Konuşma aralıkları birleştirildi: {len(keep_intervals)} → {len(condensed_intervals)}")
            keep_intervals = condensed_intervals

            removed_duration = total_duration - sum(end - start for start, end in keep_intervals)
            if removed_duration < 0.1:
                raise Exception("Budanacak anlamlı sessizlik bulunamadı.")

            print(f"✂️ {len(keep_intervals)} konuşma aralığı tek geçişte işlenecek")
            self.video_status_label.config(
                text=f"✂️ {len(keep_intervals)} aralık hazırlandı, encode başlıyor... Profil: {selected_trim_profile_name}"
            )

            is_audio_only = video_p.suffix.lower() in AUDIO_ONLY_EXTENSIONS
            if is_audio_only:
                output_video = output_dir / f"{video_p.stem}_budanmis{video_p.suffix}"
            else:
                preferred_suffix = video_p.suffix.lower() if video_p.suffix.lower() in {'.mp4', '.mov', '.mkv'} else '.mp4'
                output_video = output_dir / f"{video_p.stem}_budanmis{preferred_suffix}"
            ffmpeg_output_video = create_ffmpeg_safe_output_path(output_video)

            source_video_codec = _normalize_codec_name(media_info.get('video_codec'))
            selected_video_encoder = None
            selected_encoder_name = None

            def extend_video_encode_options(cmd):
                source_video_bitrate = media_info.get('video_bit_rate')
                source_audio_bitrate = media_info.get('audio_bit_rate')
                format_bitrate = media_info.get('format_bit_rate')

                if not source_video_bitrate and format_bitrate:
                    source_video_bitrate = max(format_bitrate - (source_audio_bitrate or 128000), 300000)

                target_video_bitrate = source_video_bitrate or 1800000
                target_audio_bitrate = source_audio_bitrate or 128000
                target_audio_bitrate = min(max(target_audio_bitrate, 96000), 192000)

                print(
                    f"🎞️ Kaynak codec={source_video_codec or 'bilinmiyor'}, "
                    f"hedef encoder={selected_video_encoder} ({selected_encoder_name}), "
                    f"profil={selected_trim_profile_name}, video bitrate≈{target_video_bitrate // 1000}k, "
                    f"audio bitrate≈{target_audio_bitrate // 1000}k"
                )

                cmd.extend(['-c:v', selected_video_encoder, '-c:a', 'aac', '-b:a', str(target_audio_bitrate)])

                if selected_video_encoder in {'h264_nvenc', 'hevc_nvenc'}:
                    if selected_trim_profile_key == 'speed':
                        cmd.extend([
                            '-preset', 'p1',
                            '-rc', 'vbr',
                            '-cq', '24',
                            '-b:v', str(int(target_video_bitrate * 0.75)),
                            '-maxrate', str(int(target_video_bitrate * 0.95)),
                            '-bufsize', str(int(target_video_bitrate * 1.25))
                        ])
                    elif selected_trim_profile_key == 'quality':
                        cmd.extend([
                            '-preset', 'p5',
                            '-rc', 'vbr_hq',
                            '-cq', '19',
                            '-b:v', str(target_video_bitrate),
                            '-maxrate', str(int(target_video_bitrate * 1.2)),
                            '-bufsize', str(int(target_video_bitrate * 2.0))
                        ])
                    else:
                        cmd.extend([
                            '-preset', 'p3',
                            '-rc', 'vbr_hq',
                            '-cq', '21',
                            '-b:v', str(int(target_video_bitrate * 0.9)),
                            '-maxrate', str(int(target_video_bitrate * 1.05)),
                            '-bufsize', str(int(target_video_bitrate * 1.6))
                        ])
                elif selected_video_encoder in {'h264_amf', 'hevc_amf'}:
                    if selected_trim_profile_key == 'speed':
                        cmd.extend([
                            '-usage', 'lowlatency',
                            '-quality', 'speed',
                            '-rc', 'cqp',
                            '-qp_i', '26',
                            '-qp_p', '28'
                        ])
                    elif selected_trim_profile_key == 'quality':
                        cmd.extend([
                            '-usage', 'transcoding',
                            '-quality', 'quality',
                            '-rc', 'vbr_peak',
                            '-b:v', str(target_video_bitrate),
                            '-maxrate', str(int(target_video_bitrate * 1.2))
                        ])
                    else:
                        cmd.extend([
                            '-usage', 'lowlatency',
                            '-quality', 'speed',
                            '-rc', 'cqp',
                            '-qp_i', '24',
                            '-qp_p', '26'
                        ])
                elif selected_video_encoder in {'h264_qsv', 'hevc_qsv'}:
                    if selected_trim_profile_key == 'speed':
                        cmd.extend([
                            '-preset', 'veryfast',
                            '-global_quality', '26',
                            '-b:v', str(int(target_video_bitrate * 0.85)),
                            '-maxrate', str(target_video_bitrate)
                        ])
                    elif selected_trim_profile_key == 'quality':
                        cmd.extend([
                            '-preset', 'medium',
                            '-global_quality', '20',
                            '-b:v', str(target_video_bitrate),
                            '-maxrate', str(int(target_video_bitrate * 1.2))
                        ])
                    else:
                        cmd.extend([
                            '-preset', 'fast',
                            '-global_quality', '23',
                            '-b:v', str(int(target_video_bitrate * 0.95)),
                            '-maxrate', str(int(target_video_bitrate * 1.1))
                        ])
                elif selected_video_encoder in {'h264_videotoolbox', 'hevc_videotoolbox'}:
                    if selected_trim_profile_key == 'speed':
                        cmd.extend([
                            '-realtime', 'true',
                            '-allow_sw', '1',
                            '-b:v', str(int(target_video_bitrate * 0.85)),
                            '-maxrate', str(target_video_bitrate)
                        ])
                    elif selected_trim_profile_key == 'quality':
                        cmd.extend([
                            '-realtime', 'false',
                            '-allow_sw', '1',
                            '-b:v', str(target_video_bitrate),
                            '-maxrate', str(int(target_video_bitrate * 1.2))
                        ])
                    else:
                        cmd.extend([
                            '-realtime', 'false',
                            '-allow_sw', '1',
                            '-b:v', str(int(target_video_bitrate * 0.95)),
                            '-maxrate', str(int(target_video_bitrate * 1.1))
                        ])
                elif selected_video_encoder == 'libx265':
                    if selected_trim_profile_key == 'speed':
                        cmd.extend([
                            '-preset', 'superfast',
                            '-crf', '26',
                            '-x265-params',
                            f"vbv-maxrate={int(target_video_bitrate / 1000)}:vbv-bufsize={int(target_video_bitrate * 1.3 / 1000)}"
                        ])
                    elif selected_trim_profile_key == 'quality':
                        cmd.extend([
                            '-preset', 'medium',
                            '-crf', '20',
                            '-x265-params',
                            f"vbv-maxrate={int(target_video_bitrate * 1.2 / 1000)}:vbv-bufsize={int(target_video_bitrate * 2.0 / 1000)}"
                        ])
                    else:
                        cmd.extend([
                            '-preset', 'fast',
                            '-crf', '23',
                            '-x265-params',
                            f"vbv-maxrate={int(target_video_bitrate * 1.1 / 1000)}:vbv-bufsize={int(target_video_bitrate * 1.6 / 1000)}"
                        ])
                else:
                    if selected_trim_profile_key == 'speed':
                        cmd.extend([
                            '-preset', 'ultrafast',
                            '-crf', '26',
                            '-maxrate', str(target_video_bitrate),
                            '-bufsize', str(int(target_video_bitrate * 1.3)),
                            '-threads', '0'
                        ])
                    elif selected_trim_profile_key == 'quality':
                        cmd.extend([
                            '-preset', 'medium',
                            '-crf', '20',
                            '-maxrate', str(int(target_video_bitrate * 1.2)),
                            '-bufsize', str(int(target_video_bitrate * 2.0)),
                            '-threads', '0'
                        ])
                    else:
                        cmd.extend([
                            '-preset', 'veryfast',
                            '-crf', '23',
                            '-maxrate', str(int(target_video_bitrate * 1.1)),
                            '-bufsize', str(int(target_video_bitrate * 1.6)),
                            '-threads', '0'
                        ])

                return selected_video_encoder

            if is_audio_only:
                suffix = video_p.suffix.lower()
                fast_audio_intervals, fast_audio_profile = optimize_intervals_for_fast_audio_copy(
                    video_path,
                    media_info,
                    keep_intervals
                )
                if len(fast_audio_intervals) != len(keep_intervals):
                    print(
                        f"🔗 Ses hızlı modu için aralıklar birleştirildi: "
                        f"{len(keep_intervals)} → {len(fast_audio_intervals)}"
                    )

                def run_audio_encode_path():
                    nonlocal filter_script_path

                    filter_complex, output_label = build_audio_filter_graph(
                        keep_intervals,
                        add_fades=False,
                        audio_post_filters=audio_cleanup_filter
                    )

                    with tempfile.NamedTemporaryFile(mode='w', suffix=".ffscript", delete=False, encoding='utf-8') as filter_file:
                        filter_file.write(filter_complex)
                        filter_script_path = filter_file.name

                    self.video_status_label.config(text="🚀 Ses tek geçişte işleniyor...")
                    self.video_progress_var.set(60)

                    encode_cmd = [
                        ffmpeg_binary,
                        '-hide_banner',
                        '-y',
                        '-i', video_path,
                        '-filter_complex_script', filter_script_path,
                        '-map', output_label,
                        '-vn', '-sn', '-dn',
                        '-map_metadata', '-1',
                    ]

                    if suffix == '.mp3':
                        encode_cmd.extend(['-threads', '0', '-c:a', 'libmp3lame', '-q:a', '4'])
                    elif suffix == '.wav':
                        encode_cmd.extend(['-c:a', 'pcm_s16le'])
                    elif suffix == '.flac':
                        encode_cmd.extend(['-c:a', 'flac'])
                    elif suffix == '.ogg':
                        encode_cmd.extend(['-c:a', 'libvorbis', '-q:a', '5'])
                    else:
                        encode_cmd.extend(['-threads', '0', '-c:a', 'aac', '-b:a', '192k'])

                    encode_cmd.append(str(ffmpeg_output_video))
                    encode_result = subprocess.run(encode_cmd, capture_output=True, text=True)
                    if encode_result.returncode != 0:
                        print(f"❌ FFmpeg hatası:\n{encode_result.stderr}")
                        raise Exception(f"Ses oluşturma hatası: {encode_result.stderr}")

                fast_audio_mode = (
                    not audio_cleanup_filter and
                    fast_audio_profile is not None and
                    should_use_fast_audio_concat(video_path, media_info, fast_audio_intervals)
                )
                if fast_audio_mode and fast_audio_profile:
                    def update_fast_audio_progress(current_index, total_segments):
                        progress = 60 + int((current_index / max(total_segments, 1)) * 25)
                        self.video_progress_var.set(progress)
                        if current_index < total_segments:
                            self.video_status_label.config(
                                text=f"⚡ {fast_audio_profile['name'].upper()} hızlı mod: parça {current_index}/{total_segments} hazırlanıyor..."
                            )

                    try:
                        self.video_status_label.config(
                            text=f"⚡ {fast_audio_profile['name'].upper()} hızlı mod aktif: {len(fast_audio_intervals)} parça kayıpsız birleştiriliyor..."
                        )
                        self.video_progress_var.set(60)
                        fast_trim_audio_with_stream_copy(
                            ffmpeg_binary,
                            video_path,
                            fast_audio_intervals,
                            ffmpeg_output_video,
                            media_info,
                            progress_callback=update_fast_audio_progress
                        )
                        self.video_status_label.config(
                            text=f"🔗 {fast_audio_profile['name'].upper()} parçaları birleştirildi, doğrulanıyor..."
                        )
                        self.video_progress_var.set(88)
                    except Exception as fast_audio_error:
                        print(f"⚠️ Ses hızlı modu başarısız oldu, normal encode kullanılacak: {fast_audio_error}")
                        self.video_status_label.config(text="⚠️ Ses hızlı modu başarısız, normal encode kullanılıyor...")
                        self.video_progress_var.set(58)
                        run_audio_encode_path()
                else:
                    run_audio_encode_path()
            else:
                fast_video_copy_plan = None
                if not audio_cleanup_filter:
                    fast_video_copy_plan = build_fast_video_copy_plan(
                        video_path,
                        ffprobe_path,
                        media_info,
                        keep_intervals,
                        total_duration
                    )
                fast_video_completed = False

                if fast_video_copy_plan:
                    print(
                        f"⚡ Video hızlı kopya modu hazır: {len(fast_video_copy_plan['intervals'])} parça, "
                        f"keyframe toleransı≈{fast_video_copy_plan['max_boundary_error']:.3f}s"
                    )

                    def update_fast_video_progress(current_index, total_segments):
                        progress = 60 + int((current_index / max(total_segments, 1)) * 25)
                        self.video_progress_var.set(progress)
                        if current_index < total_segments:
                            self.video_status_label.config(
                                text=f"⚡ Video hızlı kopya modu: parça {current_index}/{total_segments} hazırlanıyor..."
                            )

                    try:
                        self.video_status_label.config(
                            text=f"⚡ Video hızlı kopya modu aktif: {len(fast_video_copy_plan['intervals'])} parça kayıpsız birleştiriliyor..."
                        )
                        self.video_progress_var.set(60)
                        fast_trim_video_with_stream_copy(
                            ffmpeg_binary,
                            video_path,
                            fast_video_copy_plan,
                            ffmpeg_output_video,
                            progress_callback=update_fast_video_progress
                        )
                        self.video_status_label.config(text="🔗 Video kopya parçaları birleştirildi, doğrulanıyor...")
                        self.video_progress_var.set(88)
                        fast_video_completed = True
                    except Exception as fast_video_error:
                        print(f"⚠️ Video hızlı kopya modu başarısız oldu, normal encode kullanılacak: {fast_video_error}")
                        self.video_status_label.config(text="⚠️ Video hızlı kopya modu başarısız, normal encode kullanılıyor...")
                        self.video_progress_var.set(58)

                if not fast_video_completed:
                    preferred_codec = 'hevc' if source_video_codec == 'hevc' else 'h264'
                    gpu_info = SubtitleEmbedder.detect_gpu_encoder(ffmpeg_binary, preferred_codec=preferred_codec)
                    selected_video_encoder = gpu_info['encoder']
                    selected_encoder_name = gpu_info['name']

                    batch_size = (
                        selected_trim_profile['batch_size_large']
                        if len(keep_intervals) > 120 else
                        selected_trim_profile['batch_size_small']
                    )
                    interval_batches = split_intervals_into_batches(keep_intervals, batch_size)
                    batch_temp_dir = tempfile.TemporaryDirectory(prefix="subtitle_silence_batches_")
                    batch_dir = Path(batch_temp_dir.name)
                    batch_outputs = []

                    print(f"📦 Video {len(interval_batches)} batch halinde işlenecek (profil: {selected_trim_profile_name})")
                    self.video_status_label.config(
                        text=f"📦 {len(interval_batches)} batch hazırlanıyor... Profil: {selected_trim_profile_name}"
                    )
                    self.video_progress_var.set(55)

                    for batch_index, interval_batch in enumerate(interval_batches, start=1):
                        batch_start = interval_batch[0][0]
                        batch_end = interval_batch[-1][1]
                        batch_duration = batch_end - batch_start
                        relative_intervals = [
                            (start - batch_start, end - batch_start)
                            for start, end in interval_batch
                        ]

                        batch_filter, map_args = build_av_filter_graph(
                            relative_intervals,
                            include_video=True,
                            audio_post_filters=audio_cleanup_filter
                        )
                        batch_script = batch_dir / f"batch_{batch_index:03d}.ffscript"
                        batch_output = batch_dir / f"batch_{batch_index:03d}.ts"
                        batch_script.write_text(batch_filter, encoding='utf-8')

                        batch_cmd = [
                            ffmpeg_binary,
                            '-hide_banner',
                            '-y',
                            '-threads', '0',
                            '-filter_threads', '0',
                            '-filter_complex_threads', '0',
                            '-hwaccel', 'auto',
                            '-ss', f"{batch_start:.6f}",
                            '-t', f"{batch_duration:.6f}",
                            '-i', video_path,
                            '-filter_complex_script', str(batch_script)
                        ]
                        batch_cmd.extend(map_args)
                        extend_video_encode_options(batch_cmd)
                        batch_cmd.extend(['-f', 'mpegts', str(batch_output)])

                        self.video_status_label.config(
                            text=f"🚀 Batch {batch_index}/{len(interval_batches)} encode ediliyor... Profil: {selected_trim_profile_name}"
                        )
                        result = subprocess.run(batch_cmd, capture_output=True, text=True)
                        try:
                            batch_script.unlink()
                        except OSError:
                            pass

                        if result.returncode != 0:
                            print(f"❌ Batch {batch_index} FFmpeg hatası:\n{result.stderr}")
                            raise Exception(f"Batch {batch_index} oluşturma hatası: {result.stderr}")

                        if not batch_output.exists() or batch_output.stat().st_size < 1000:
                            raise Exception(f"Batch {batch_index} çıktısı oluşturulamadı")

                        batch_outputs.append(batch_output)
                        progress = 55 + int((batch_index / len(interval_batches)) * 30)
                        self.video_progress_var.set(progress)

                    concat_file = batch_dir / "concat_list.txt"
                    write_ffmpeg_concat_list(batch_outputs, concat_file)

                    self.video_status_label.config(text="🔗 Batch dosyaları birleştiriliyor...")
                    concat_cmd = [
                        ffmpeg_binary,
                        '-hide_banner',
                        '-y',
                        '-f', 'concat',
                        '-safe', '0',
                        '-i', str(concat_file),
                        '-c', 'copy'
                    ]
                    if ffmpeg_output_video.suffix.lower() in {'.mp4', '.mov'}:
                        concat_cmd.extend(['-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart'])
                    concat_cmd.append(str(ffmpeg_output_video))

                    result = subprocess.run(concat_cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        print(f"❌ Concat FFmpeg hatası:\n{result.stderr}")
                        raise Exception(f"Batch birleştirme hatası: {result.stderr}")

            if not ffmpeg_output_video.exists() or ffmpeg_output_video.stat().st_size < 1000:
                raise Exception("Çıktı videosu oluşturulamadı veya bozuk")

            output_video = finalize_ffmpeg_output_path(ffmpeg_output_video, output_video)
            print(f"✅ Video başarıyla oluşturuldu: {output_video}")

            original_size = os.path.getsize(video_path) / (1024 * 1024)
            trimmed_size = os.path.getsize(output_video) / (1024 * 1024)
            reduction = ((original_size - trimmed_size) / original_size) * 100 if original_size > 0 else 0

            self.video_progress_var.set(95)

            new_duration = get_media_duration(output_video, ffprobe_path)
            if not new_duration:
                raise Exception("Çıktı süresi okunamadı")
            time_saved = total_duration - new_duration

            self.video_progress_var.set(100)
            self.video_status_label.config(
                text=f"✅ Tamamlandı! Boyut: %{reduction:.1f} azalma, Süre: {time_saved:.1f}s kısaldı\n📁 Çıktı: {output_video}"
            )

            messagebox.showinfo(
                "✅ Başarılı",
                f"Sessizlik budama tamamlandı!\n\n"
                f"📊 Boyut azalması: %{reduction:.1f}\n"
                f"⏱️ Süre azalması: {time_saved:.1f} saniye\n"
                f"🎬 Orijinal: {total_duration:.1f}s → Yeni: {new_duration:.1f}s\n\n"
                f"Çıktı dosyası:\n{output_video}\n\n"
                f"Klasörü açmak ister misiniz?"
            )
            
            if messagebox.askyesno("📂 Klasör", "Çıktı klasörünü açmak ister misiniz?"):
                if os.name == 'nt':
                    os.startfile(output_dir)
                elif os.name == 'posix':
                    subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', str(output_dir)])

        except Exception as e:
            self.video_progress_var.set(0)
            self.video_status_label.config(text=f"❌ Hata: {str(e)}")
            messagebox.showerror("❌ Hata", f"İşlem başarısız:\n{str(e)}")
        finally:
            if filter_script_path and os.path.exists(filter_script_path):
                try:
                    os.unlink(filter_script_path)
                except OSError:
                    pass
            if batch_temp_dir is not None:
                batch_temp_dir.cleanup()
    
    def reset_silence_settings(self):
        """Sessizlik budama ayarlarını varsayılana döndür"""
        if messagebox.askyesno("❓ Onay", 
                              "Sessizlik budama ayarlarını varsayılan değerlere döndürmek istediğinize emin misiniz?"):
            self.silence_threshold_var.set(-40.0)
            self.min_silence_duration_var.set(0.5)
            self.manual_speech_protection_var.set(False)
            self.remove_background_noise_var.set(False)
            self.update_threshold_label(-40.0)
            self.update_duration_label(0.5)
            self.toggle_manual_protection()
            messagebox.showinfo("✅ Başarılı", "Ayarlar varsayılan değerlere döndürüldü.")
    
    def test_silence_removal(self):
        """Sessizlik budama özelliğini test et"""
        video_file = self.video_path.get()
        if not video_file:
            messagebox.showwarning("⚠️ Uyarı", 
                                 "Test için önce bir video dosyası seçin.\n\n"
                                 "Ana İşlemler sekmesinden video seçebilirsiniz.")
            return
        
        if not self.remove_silence_var.get():
            messagebox.showinfo("ℹ️ Bilgi", 
                              "Sessizlik budama şu anda devre dışı.\n\n"
                              "Test etmek için önce 'Sessizlik Budamayı Etkinleştir' seçeneğini işaretleyin.")
            return
        
        messagebox.showinfo("🧪 Test", 
                          f"Sessizlik budama testi başlatılacak:\n\n"
                          f"📊 Eşik: {self.silence_threshold_var.get():.1f} dB\n"
                          f"⏱️ Min. Süre: {self.min_silence_duration_var.get():.2f} sn\n"
                          f"🛡️ {'Manuel' if self.manual_speech_protection_var.get() else 'Otomatik'} Koruma: {self.speech_protection_var.get():.2f} sn\n"
                          f"🔉 Dip ses temizleme: {'Açık' if self.remove_background_noise_var.get() else 'Kapalı'}\n\n"
                          f"Test, transkripsiyon işlemi sırasında otomatik olarak uygulanacaktır.\n"
                          f"Ana İşlemler sekmesinden 'Transkript Et' butonuna tıklayın.")

    # Settings Tab
    def create_settings_tab(self, parent):
        """Ayarlar sekmesi oluştur"""
        # Scrollable frame
        canvas = tk.Canvas(parent, bg='#1e1e1e', highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 🖱️ Mouse wheel scroll desteği ekle
        self.bind_mousewheel(canvas)
        
        # API Settings Frame
        api_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('settings_api_title'))
        api_frame.pack(padx=15, pady=10, fill="x")
        
        api_info = tk.Label(
            api_frame,
            text=self.tr('settings_api_info'),
            bg='#1e1e1e',
            fg='white',
            font=('Segoe UI', 10),
            justify='left'
        )
        api_info.pack(padx=10, pady=10, anchor='w')

        groq_row = tk.Frame(api_frame, bg='#1e1e1e')
        groq_row.pack(fill="x", padx=10, pady=5)

        tk.Label(groq_row, text="Groq API Key:", bg='#1e1e1e', fg='white',
                font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=5)

        self.groq_api_entry = tk.Entry(
            groq_row,
            textvariable=self.groq_api_key_var,
            bg='#2b2b2b',
            fg='white',
            relief=tk.FLAT,
            font=('Segoe UI', 9),
            insertbackground='white',
            show='*'
        )
        self.groq_api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.groq_api_entry.bind("<KeyRelease>", lambda event: self.refresh_api_status())

        openrouter_row = tk.Frame(api_frame, bg='#1e1e1e')
        openrouter_row.pack(fill="x", padx=10, pady=5)

        tk.Label(openrouter_row, text="OpenRouter Key:", bg='#1e1e1e', fg='white',
                font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=5)

        self.openrouter_api_entry = tk.Entry(
            openrouter_row,
            textvariable=self.openrouter_api_key_var,
            bg='#2b2b2b',
            fg='white',
            relief=tk.FLAT,
            font=('Segoe UI', 9),
            insertbackground='white',
            show='*'
        )
        self.openrouter_api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.openrouter_api_entry.bind("<KeyRelease>", lambda event: self.refresh_api_status())

        api_actions = tk.Frame(api_frame, bg='#1e1e1e')
        api_actions.pack(fill="x", padx=10, pady=(5, 8))

        show_keys_check = tk.Checkbutton(
            api_actions,
            text=self.tr('show_keys'),
            variable=self.show_api_keys_var,
            command=self.toggle_api_key_visibility,
            bg='#1e1e1e',
            fg='white',
            selectcolor='#404040',
            activebackground='#1e1e1e',
            font=('Segoe UI', 9)
        )
        show_keys_check.pack(side=tk.LEFT, padx=5)

        save_api_btn = tk.Button(
            api_actions,
            text=self.tr('save_api_keys'),
            command=self.save_api_keys,
            bg='#198754',
            fg='white',
            relief=tk.FLAT,
            font=('Segoe UI', 9, 'bold'),
            padx=15,
            pady=8,
            cursor='hand2'
        )
        save_api_btn.pack(side=tk.RIGHT, padx=5)

        env_btn = tk.Button(
            api_actions,
            text=self.tr('open_api_env'),
            command=self.open_env_file,
            bg='#0d7377',
            fg='white',
            relief=tk.FLAT,
            font=('Segoe UI', 9, 'bold'),
            padx=15,
            pady=8,
            cursor='hand2'
        )
        env_btn.pack(side=tk.RIGHT, padx=5)

        api_status_label = tk.Label(
            api_frame,
            textvariable=self.api_status_var,
            bg='#1e1e1e',
            fg='#0d7377',
            font=('Segoe UI', 9, 'bold'),
            justify='left'
        )
        api_status_label.pack(padx=10, pady=(0, 10), anchor='w')

        self.toggle_api_key_visibility()
        self.refresh_api_status()

        language_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('settings_language_title'))
        language_frame.pack(padx=15, pady=10, fill="x")

        language_row = tk.Frame(language_frame, bg='#1e1e1e')
        language_row.pack(fill="x", padx=10, pady=10)

        tk.Label(language_row, text=self.tr('label_interface_language'), bg='#1e1e1e', fg='white',
                font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=5)

        self.ui_language_display_var = tk.StringVar(value=self.get_ui_language_display())
        language_combo = ttk.Combobox(
            language_row,
            textvariable=self.ui_language_display_var,
            values=list(UI_LANGUAGE_OPTIONS.values()),
            state="readonly",
            width=16,
            font=('Segoe UI', 9)
        )
        language_combo.pack(side=tk.LEFT, padx=10)
        language_combo.bind(
            "<<ComboboxSelected>>",
            lambda event: self.on_ui_language_selected(self.ui_language_display_var.get())
        )

        language_note = tk.Label(
            language_frame,
            text=self.tr('language_note'),
            bg='#1e1e1e',
            fg='#aaaaaa',
            font=('Segoe UI', 9),
            justify='left'
        )
        language_note.pack(padx=10, pady=(0, 10), anchor='w')
        
        # Advanced Settings Frame
        advanced_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('settings_advanced_title'))
        advanced_frame.pack(padx=15, pady=10, fill="x")
        
        # Default output name
        output_row = tk.Frame(advanced_frame, bg='#1e1e1e')
        output_row.pack(fill="x", padx=10, pady=8)
        
        tk.Label(output_row, text=self.tr('label_default_output_name'), bg='#1e1e1e', fg='white', 
                font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=5)
        
        self.default_output_name = tk.StringVar()
        default_entry = tk.Entry(output_row, textvariable=self.default_output_name, 
                                bg='#2b2b2b', fg='white', relief=tk.FLAT, 
                                font=('Segoe UI', 9), insertbackground='white')
        default_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Auto-save settings
        self.auto_save_var = tk.BooleanVar(value=True)
        auto_save_check = tk.Checkbutton(advanced_frame, text=self.tr('auto_save_settings'), 
                                        variable=self.auto_save_var, bg='#1e1e1e', 
                                        fg='white', selectcolor='#404040', 
                                        font=('Segoe UI', 9), activebackground='#1e1e1e')
        auto_save_check.pack(padx=10, pady=5)
        
        # Clean temp files
        clean_btn = tk.Button(advanced_frame, text=self.tr('clean_temp_files'), 
                             command=self.clean_temp_files, bg='#dc3545', fg='white', 
                             relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                             padx=15, pady=8, cursor='hand2')
        clean_btn.pack(padx=10, pady=5)
        
    # Help Tab
    def create_help_tab(self, parent):
        """Yardım sekmesi oluştur"""
        # Scrollable frame
        canvas = tk.Canvas(parent, bg='#1e1e1e', highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 🖱️ Mouse wheel scroll desteği ekle
        self.bind_mousewheel(canvas)
        
        # Quick Start Guide
        quickstart_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('help_tab_quickstart_title'))
        quickstart_frame.pack(padx=15, pady=10, fill="x")
        
        quickstart_text = self.get_help_tab_quickstart_text()
        
        quickstart_label = tk.Label(quickstart_frame, text=quickstart_text, 
                                   bg='#1e1e1e', fg='white', font=('Segoe UI', 10), 
                                   justify='left')
        quickstart_label.pack(padx=10, pady=10)
        
        # Shortcuts Frame
        shortcuts_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('help_tab_shortcuts_title'))
        shortcuts_frame.pack(padx=15, pady=10, fill="x")
        
        shortcuts_text = self.get_help_tab_shortcuts_text()
        
        shortcuts_label = tk.Label(shortcuts_frame, text=shortcuts_text, 
                                  bg='#1e1e1e', fg='white', font=('Consolas', 9), 
                                  justify='left')
        shortcuts_label.pack(padx=10, pady=10)
        
        # Quick Actions Frame
        actions_frame = ttk.LabelFrame(scrollable_frame, text=self.tr('help_tab_quick_actions_title'))
        actions_frame.pack(padx=15, pady=10, fill="x")
        
        # Action buttons
        action_buttons_frame = tk.Frame(actions_frame, bg='#1e1e1e')
        action_buttons_frame.pack(pady=10)
        
        browse_btn = tk.Button(action_buttons_frame, text=self.tr('help_tab_browse_video'), 
                              command=self.browse_video, bg='#28a745', fg='white', 
                              relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                              padx=15, pady=8, cursor='hand2')
        browse_btn.pack(side=tk.LEFT, padx=5)
        
        preview_btn = tk.Button(action_buttons_frame, text=self.tr('font_preview'), 
                               command=self.show_preview, bg='#17a2b8', fg='white', 
                               relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                               padx=15, pady=8, cursor='hand2')
        preview_btn.pack(side=tk.LEFT, padx=5)
        
        font_btn = tk.Button(action_buttons_frame, text=self.tr('tab_font'), 
                            command=self.open_font_settings, bg='#6f42c1', fg='white', 
                            relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                            padx=15, pady=8, cursor='hand2')
        font_btn.pack(side=tk.LEFT, padx=5)
        
        help_btn = tk.Button(action_buttons_frame, text=self.tr('help_tab_help'), 
                            command=self.show_help, bg='#fd7e14', fg='white', 
                            relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                            padx=15, pady=8, cursor='hand2')
        help_btn.pack(side=tk.LEFT, padx=5)
        
        # Footer
        footer_frame = tk.Frame(scrollable_frame, bg='#1e1e1e', height=60)
        footer_frame.pack(fill="x", padx=15, pady=20)
        footer_frame.pack_propagate(False)
        
        footer_label = tk.Label(footer_frame, 
                               text="🎬 SSR&SET v2.0\n"
                                    f"{self.tr('footer_subtitle')}", 
                               bg='#1e1e1e', fg='#888888', font=('Segoe UI', 9), 
                               justify='center')
        footer_label.pack(expand=True)

    def open_env_file(self):
        """.env dosyasını aç"""
        env_file = self.api_env_file
        if env_file.exists():
            if os.name == 'nt':  # Windows
                os.startfile(env_file)
            elif os.name == 'posix':  # macOS/Linux
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', str(env_file)])
        else:
            messagebox.showwarning(
                self.tr('open_env_warning_title'),
                self.tr('open_env_warning_message')
            )

    def clean_temp_files(self):
        """Geçici dosyaları temizle"""
        temp_dir = Path(tempfile.gettempdir())
        subtitle_temp_files = list(temp_dir.glob("*_chunk_*.wav"))
        subtitle_temp_files.extend(list(temp_dir.glob("*.wav")))
        
        if not subtitle_temp_files:
            messagebox.showinfo("ℹ️ Bilgi", "Temizlenecek geçici dosya bulunamadı.")
            return
        
        if messagebox.askyesno("❓ Onay", 
                               f"{len(subtitle_temp_files)} geçici dosya bulundu.\n"
                               "Temizlenmesini istediğinize emin misiniz?"):
            cleaned = 0
            for file in subtitle_temp_files:
                try:
                    file.unlink()
                    cleaned += 1
                except:
                    pass
            
            messagebox.showinfo("✅ Tamamlandı", 
                              f"{cleaned} geçici dosya temizlendi.")
        else:
            messagebox.showinfo("ℹ️ Bilgi", "İşlem iptal edildi.")

    def get_language_display_name(self, lang_code):
        """Dil kodundan görüntü adı al"""
        for name, code in self.source_lang_options.items():
            if code == lang_code:
                return name
        return lang_code.upper()

def main_gui():
    root = tk.Tk()
    app = SubtitleApp(root)
    root.mainloop()
