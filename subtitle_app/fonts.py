"""Font settings models and font-related Tkinter dialogs."""

import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog, ttk

class FontSettings:
    def __init__(self):
        self.font_family = "Arial"
        self.font_size = 24
        self.font_color = "#FFFFFF"
        self.outline_color = "#000000"
        self.outline_width = 2
        self.background_color = "#000000"
        self.background_opacity = 0.5
        self.position_x = 50
        self.position_y = 85
        self.bold = False
        self.italic = False
        self.use_adaptive_size = False  # Otomatik boyut ayarı
        
    def to_dict(self):
        return {
            'font_family': self.font_family,
            'font_size': self.font_size,
            'font_color': self.font_color,
            'outline_color': self.outline_color,
            'outline_width': self.outline_width,
            'background_color': self.background_color,
            'background_opacity': self.background_opacity,
            'position_x': self.position_x,
            'position_y': self.position_y,
            'bold': self.bold,
            'italic': self.italic,
            'use_adaptive_size': self.use_adaptive_size
        }
    
    def from_dict(self, data):
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

# Simple Preview Window
class SimplePreviewWindow:
    def __init__(self, parent, font_settings):
        self.parent = parent
        self.font_settings = font_settings
        self._preview_after_id = None
        self.window = tk.Toplevel(parent)
        self.window.title("🎬 Altyazı Önizleme")
        self.window.geometry("640x480")
        self.window.configure(bg='#2b2b2b')
        
        # Title
        title_label = tk.Label(self.window, text="Altyazı Önizleme", 
                              font=('Segoe UI', 14, 'bold'), 
                              bg='#2b2b2b', fg='white')
        title_label.pack(pady=10)
        
        self.canvas = tk.Canvas(self.window, width=640, height=360, bg='black', highlightthickness=0)
        self.canvas.pack(pady=10)
        
        text_frame = tk.Frame(self.window, bg='#2b2b2b')
        text_frame.pack(pady=5)
        
        tk.Label(text_frame, text="Örnek Metin:", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=5)
        self.text_var = tk.StringVar(value="Örnek altyazı metni")
        self.text_entry = tk.Entry(text_frame, textvariable=self.text_var, width=50, 
                                   font=('Segoe UI', 10), relief=tk.FLAT, 
                                   bg='#3c3c3c', fg='white', insertbackground='white')
        self.text_entry.pack(side=tk.LEFT, padx=5)
        self.text_entry.bind('<KeyRelease>', self.on_text_change)
        
        self.update_preview()
    
    def on_text_change(self, event=None):
        if self._preview_after_id is not None:
            self.window.after_cancel(self._preview_after_id)
        self._preview_after_id = self.window.after(60, self.update_preview)
    
    def update_preview(self):
        self._preview_after_id = None
        self.canvas.delete("all")
        
        sample_text = self.text_var.get()
        x = 320
        y = int(360 * self.font_settings.position_y / 100)
        font_weight = "bold" if self.font_settings.bold else "normal"
        font_style = font_weight
        if self.font_settings.italic:
            font_style += " italic"
        
        # Background
        if self.font_settings.background_opacity > 0:
            try:
                bg_color = self.font_settings.background_color
                text_width = len(sample_text) * 8
                text_height = 20
                padding = 10
                self.canvas.create_rectangle(
                    x - text_width//2 - padding, y - text_height//2 - padding,
                    x + text_width//2 + padding, y + text_height//2 + padding,
                    fill=bg_color, outline=""
                )
            except:
                pass
        
        # Outline
        if self.font_settings.outline_width > 0:
            try:
                for dx in range(-self.font_settings.outline_width, self.font_settings.outline_width + 1):
                    for dy in range(-self.font_settings.outline_width, self.font_settings.outline_width + 1):
                        if dx != 0 or dy != 0:
                            self.canvas.create_text(
                                x + dx, y + dy, text=sample_text,
                                fill=self.font_settings.outline_color,
                                font=(self.font_settings.font_family, self.font_settings.font_size, font_weight)
                            )
            except:
                pass
        
        # Main text
        try:
            self.canvas.create_text(
                x, y, text=sample_text,
                fill=self.font_settings.font_color,
                font=(self.font_settings.font_family, self.font_settings.font_size, font_style)
            )
        except:
            self.canvas.create_text(x, y, text=sample_text, fill="white", font=("Arial", 16))
    
    def refresh(self):
        self.update_preview()

# Font Settings Window
class FontSettingsWindow:
    def __init__(self, parent, font_settings, preview_callback=None, save_callback=None):
        self.parent = parent
        self.font_settings = font_settings
        self.preview_callback = preview_callback
        self.save_callback = save_callback
        self.window = tk.Toplevel(parent)
        self.window.title("⚙️ Yazı Tipi Ayarları")
        self.window.geometry("450x680")
        self.window.configure(bg='#2b2b2b')
        
        self.create_widgets()
        self.load_current_settings()
    
    def create_widgets(self):
        # Main container
        main_frame = tk.Frame(self.window, bg='#2b2b2b')
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Font Family
        font_frame = tk.LabelFrame(main_frame, text=" 🔤 Yazı Tipi ", bg='#2b2b2b', 
                                  fg='white', font=('Segoe UI', 10, 'bold'))
        font_frame.pack(padx=5, pady=8, fill="x")
        
        tk.Label(font_frame, text="Font Ailesi:", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 9)).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        
        # Font combo ve ekleme butonu için frame
        font_select_frame = tk.Frame(font_frame, bg='#2b2b2b')
        font_select_frame.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        
        self.font_family_var = tk.StringVar()
        self.font_families = [
            "Arial", "Times New Roman", "Helvetica", "Verdana", "Calibri", 
            "Comic Sans MS", "Segoe UI", "Consolas", "Georgia", "Courier New",
            "Tahoma", "Trebuchet MS", "Impact", "Lucida Console", "Palatino Linotype",
            "Century Gothic", "Franklin Gothic Medium", "Garamond", "Book Antiqua",
            "Arial Black", "Cambria", "Candara", "Constantia", "Corbel"
        ]
        self.font_combo = ttk.Combobox(font_select_frame, textvariable=self.font_family_var, 
                                      values=self.font_families, font=('Segoe UI', 9))
        self.font_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.font_combo.bind('<<ComboboxSelected>>', self.on_setting_change)
        
        # Özel font ekleme butonu
        add_font_btn = tk.Button(font_select_frame, text="➕", 
                                command=self.add_custom_font, width=3,
                                bg='#28a745', fg='white', relief=tk.FLAT, 
                                font=('Segoe UI', 10, 'bold'), cursor='hand2')
        add_font_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        tk.Label(font_frame, text="Boyut:", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 9)).grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.font_size_var = tk.IntVar()
        self.font_size_spin = ttk.Spinbox(font_frame, from_=8, to=72, 
                                         textvariable=self.font_size_var, width=15, 
                                         font=('Segoe UI', 9))
        self.font_size_spin.grid(row=1, column=1, padx=10, pady=8, sticky="w")
        self.font_size_spin.bind('<KeyRelease>', self.on_setting_change)
        
        # Font Style
        style_frame = tk.Frame(font_frame, bg='#2b2b2b')
        style_frame.grid(row=2, column=0, columnspan=2, pady=8, sticky="ew")
        
        self.bold_var = tk.BooleanVar()
        self.italic_var = tk.BooleanVar()
        
        bold_check = tk.Checkbutton(style_frame, text="Kalın", variable=self.bold_var, 
                                   command=self.on_setting_change, bg='#2b2b2b', 
                                   fg='white', selectcolor='#404040', 
                                   font=('Segoe UI', 9), activebackground='#2b2b2b')
        bold_check.pack(side=tk.LEFT, padx=10)
        
        italic_check = tk.Checkbutton(style_frame, text="İtalik", variable=self.italic_var, 
                                     command=self.on_setting_change, bg='#2b2b2b', 
                                     fg='white', selectcolor='#404040', 
                                     font=('Segoe UI', 9), activebackground='#2b2b2b')
        italic_check.pack(side=tk.LEFT, padx=10)
        
        # Adaptive Size
        adaptive_frame = tk.Frame(font_frame, bg='#2b2b2b')
        adaptive_frame.grid(row=3, column=0, columnspan=2, pady=8, sticky="ew")
        
        self.adaptive_size_var = tk.BooleanVar()
        adaptive_check = tk.Checkbutton(adaptive_frame, 
                                       text="📐 Otomatik Boyut (Video çözünürlüğüne göre ayarla)", 
                                       variable=self.adaptive_size_var, 
                                       command=self.on_setting_change, bg='#2b2b2b', 
                                       fg='#ffc107', selectcolor='#404040', 
                                       font=('Segoe UI', 9), activebackground='#2b2b2b')
        adaptive_check.pack(side=tk.LEFT, padx=10)
        
        # Uyarı etiketi
        self.adaptive_warning = tk.Label(adaptive_frame, 
                                        text="⚠️ Kapalı: Belirlediğiniz boyut kullanılır",
                                        bg='#2b2b2b', fg='#6c757d', 
                                        font=('Segoe UI', 8, 'italic'))
        self.adaptive_warning.pack(side=tk.LEFT, padx=5)
        
        font_frame.columnconfigure(1, weight=1)
        
        # Colors
        color_frame = tk.LabelFrame(main_frame, text=" 🎨 Renkler ", bg='#2b2b2b', 
                                   fg='white', font=('Segoe UI', 10, 'bold'))
        color_frame.pack(padx=5, pady=8, fill="x")
        
        tk.Label(color_frame, text="Metin Rengi:", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 9)).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.font_color_var = tk.StringVar()
        self.font_color_button = tk.Button(color_frame, text="Renk Seç", 
                                          command=self.choose_font_color, width=12, 
                                          relief=tk.FLAT, font=('Segoe UI', 9))
        self.font_color_button.grid(row=0, column=1, padx=10, pady=8)
        
        tk.Label(color_frame, text="Çerçeve Rengi:", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 9)).grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.outline_color_var = tk.StringVar()
        self.outline_color_button = tk.Button(color_frame, text="Renk Seç", 
                                             command=self.choose_outline_color, width=12, 
                                             relief=tk.FLAT, font=('Segoe UI', 9))
        self.outline_color_button.grid(row=1, column=1, padx=10, pady=8)
        
        tk.Label(color_frame, text="Çerçeve Kalınlığı:", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 9)).grid(row=2, column=0, padx=10, pady=8, sticky="w")
        self.outline_width_var = tk.IntVar()
        self.outline_width_spin = ttk.Spinbox(color_frame, from_=0, to=10, 
                                             textvariable=self.outline_width_var, 
                                             width=15, font=('Segoe UI', 9))
        self.outline_width_spin.grid(row=2, column=1, padx=10, pady=8)
        self.outline_width_spin.bind('<KeyRelease>', self.on_setting_change)
        
        # Background
        bg_frame = tk.LabelFrame(main_frame, text=" 📐 Arka Plan ", bg='#2b2b2b', 
                                fg='white', font=('Segoe UI', 10, 'bold'))
        bg_frame.pack(padx=5, pady=8, fill="x")
        
        tk.Label(bg_frame, text="Arka Plan Rengi:", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 9)).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.bg_color_var = tk.StringVar()
        self.bg_color_button = tk.Button(bg_frame, text="Renk Seç", 
                                        command=self.choose_bg_color, width=12, 
                                        relief=tk.FLAT, font=('Segoe UI', 9))
        self.bg_color_button.grid(row=0, column=1, padx=10, pady=8)
        
        tk.Label(bg_frame, text="Saydamlık:", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 9)).grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.bg_opacity_var = tk.DoubleVar()
        self.bg_opacity_scale = ttk.Scale(bg_frame, from_=0.0, to=1.0, 
                                         variable=self.bg_opacity_var, orient=tk.HORIZONTAL, 
                                         command=self.on_setting_change)
        self.bg_opacity_scale.grid(row=1, column=1, padx=10, pady=8, sticky="ew")
        
        bg_frame.columnconfigure(1, weight=1)
        
        # Position
        pos_frame = tk.LabelFrame(main_frame, text=" 📍 Konum ", bg='#2b2b2b', 
                                 fg='white', font=('Segoe UI', 10, 'bold'))
        pos_frame.pack(padx=5, pady=8, fill="x")
        
        tk.Label(pos_frame, text="Yatay Konum (%):", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 9)).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.pos_x_var = tk.IntVar()
        self.pos_x_scale = ttk.Scale(pos_frame, from_=0, to=100, variable=self.pos_x_var, 
                                    orient=tk.HORIZONTAL, command=self.on_setting_change)
        self.pos_x_scale.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        
        tk.Label(pos_frame, text="Dikey Konum (%):", bg='#2b2b2b', fg='white', 
                font=('Segoe UI', 9)).grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.pos_y_var = tk.IntVar()
        self.pos_y_scale = ttk.Scale(pos_frame, from_=0, to=100, variable=self.pos_y_var, 
                                    orient=tk.HORIZONTAL, command=self.on_setting_change)
        self.pos_y_scale.grid(row=1, column=1, padx=10, pady=8, sticky="ew")
        
        pos_frame.columnconfigure(1, weight=1)
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg='#2b2b2b')
        button_frame.pack(padx=5, pady=15, fill="x")
        
        preview_btn = tk.Button(button_frame, text="👁️ Önizleme", 
                               command=self.show_preview, bg='#0d7377', fg='white', 
                               relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                               padx=15, pady=8, cursor='hand2')
        preview_btn.pack(side=tk.LEFT, padx=5)
        
        default_btn = tk.Button(button_frame, text="🔄 Varsayılan", 
                               command=self.reset_to_default, bg='#ff6b6b', fg='white', 
                               relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                               padx=15, pady=8, cursor='hand2')
        default_btn.pack(side=tk.LEFT, padx=5)
        
        # Otomatik kaydet butonu
        auto_save_btn = tk.Button(button_frame, text="💾 Kaydet", 
                                 command=self.auto_save_settings, bg='#ffc107', fg='black', 
                                 relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                                 padx=15, pady=8, cursor='hand2')
        auto_save_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(button_frame, text="❌ İptal", 
                              command=self.window.destroy, bg='#6c757d', fg='white', 
                              relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                              padx=15, pady=8, cursor='hand2')
        cancel_btn.pack(side=tk.RIGHT, padx=5)
        
        save_btn = tk.Button(button_frame, text="✅ Uygula & Kapat", 
                            command=self.save_settings, bg='#28a745', fg='white', 
                            relief=tk.FLAT, font=('Segoe UI', 9, 'bold'), 
                            padx=15, pady=8, cursor='hand2')
        save_btn.pack(side=tk.RIGHT, padx=5)
    
    def load_current_settings(self):
        self.font_family_var.set(self.font_settings.font_family)
        self.font_size_var.set(self.font_settings.font_size)
        self.bold_var.set(self.font_settings.bold)
        self.italic_var.set(self.font_settings.italic)
        self.font_color_var.set(self.font_settings.font_color)
        self.outline_color_var.set(self.font_settings.outline_color)
        self.outline_width_var.set(self.font_settings.outline_width)
        self.bg_color_var.set(self.font_settings.background_color)
        self.bg_opacity_var.set(self.font_settings.background_opacity)
        self.pos_x_var.set(self.font_settings.position_x)
        self.pos_y_var.set(self.font_settings.position_y)
        self.adaptive_size_var.set(self.font_settings.use_adaptive_size)
        
        self.update_color_buttons()
        self.update_adaptive_warning()
    
    def update_color_buttons(self):
        try:
            self.font_color_button.config(bg=self.font_color_var.get())
            self.outline_color_button.config(bg=self.outline_color_var.get())
            self.bg_color_button.config(bg=self.bg_color_var.get())
        except:
            pass
    
    def choose_font_color(self):
        color = colorchooser.askcolor(color=self.font_color_var.get())[1]
        if color:
            self.font_color_var.set(color)
            self.font_color_button.config(bg=color)
            self.on_setting_change()
    
    def choose_outline_color(self):
        color = colorchooser.askcolor(color=self.outline_color_var.get())[1]
        if color:
            self.outline_color_var.set(color)
            self.outline_color_button.config(bg=color)
            self.on_setting_change()
    
    def choose_bg_color(self):
        color = colorchooser.askcolor(color=self.bg_color_var.get())[1]
        if color:
            self.bg_color_var.set(color)
            self.bg_color_button.config(bg=color)
            self.on_setting_change()
    
    def on_setting_change(self, event=None):
        self.font_settings.font_family = self.font_family_var.get()
        self.font_settings.font_size = self.font_size_var.get()
        self.font_settings.bold = self.bold_var.get()
        self.font_settings.italic = self.italic_var.get()
        self.font_settings.font_color = self.font_color_var.get()
        self.font_settings.outline_color = self.outline_color_var.get()
        self.font_settings.outline_width = self.outline_width_var.get()
        self.font_settings.background_color = self.bg_color_var.get()
        self.font_settings.background_opacity = self.bg_opacity_var.get()
        self.font_settings.position_x = self.pos_x_var.get()
        self.font_settings.position_y = self.pos_y_var.get()
        self.font_settings.use_adaptive_size = self.adaptive_size_var.get()
        
        self.update_adaptive_warning()
        
        if self.preview_callback:
            self.preview_callback()
    
    def update_adaptive_warning(self):
        """Adaptive size uyarısını güncelle"""
        if self.adaptive_size_var.get():
            self.adaptive_warning.config(
                text="✅ Açık: Video çözünürlüğüne göre otomatik ayarlanır",
                fg='#28a745'
            )
        else:
            self.adaptive_warning.config(
                text="⚠️ Kapalı: Belirlediğiniz boyut kullanılır",
                fg='#6c757d'
            )
    
    def show_preview(self):
        if not hasattr(self, 'preview_window') or not self.preview_window.window.winfo_exists():
            self.preview_window = SimplePreviewWindow(self.window, self.font_settings)
        else:
            self.preview_window.refresh()
            self.preview_window.window.lift()
    
    def reset_to_default(self):
        self.font_settings = FontSettings()
        self.load_current_settings()
        if self.preview_callback:
            self.preview_callback()
    
    def auto_save_settings(self):
        """Otomatik kaydet (save_callback kullanarak)"""
        if self.save_callback:
            self.save_callback()
        if self.preview_callback:
            self.preview_callback()
    
    def save_settings(self):
        """Uygula ve kapat"""
        if self.save_callback:
            self.save_callback()
        if self.preview_callback:
            self.preview_callback()
        self.window.destroy()
    
    def add_custom_font(self):
        """Kullanıcının özel font eklemesini sağla"""
        font_name = simpledialog.askstring(
            "Özel Font Ekle",
            "Font adını girin:\n(Örn: 'Roboto', 'Open Sans', 'Montserrat')\n\nNot: Font sisteminizde yüklü olmalıdır.",
            parent=self.window
        )
        
        if font_name and font_name.strip():
            font_name = font_name.strip()
            
            # Font zaten listede mi kontrol et
            if font_name in self.font_families:
                messagebox.showinfo("Bilgi", f"'{font_name}' zaten listede mevcut!", parent=self.window)
                return
            
            # Font'u listeye ekle
            self.font_families.append(font_name)
            self.font_families.sort()  # Alfabetik sırala
            
            # Combobox'ı güncelle
            self.font_combo['values'] = self.font_families
            self.font_family_var.set(font_name)
            
            # Ayarları güncelle
            self.on_setting_change()
            
            messagebox.showinfo("Başarılı", 
                              f"'{font_name}' font listesine eklendi!\n\nNot: Font sisteminizde yüklü değilse varsayılan font kullanılacaktır.",
                              parent=self.window)
