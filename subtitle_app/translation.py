"""Subtitle translation and SRT conversion helpers."""

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

class SRTTranslator:
    def __init__(self, model="microsoft/mai-ds-r1:free"):
        load_dotenv('api.env', override=True)
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError("❌ OPENROUTER_API_KEY bulunamadı!")
        
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = model
        self._base_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/video-transcriber",
            "X-Title": "SSR&SET - Simple Silence Remover and Subtitle Embed Tool"
        }
        self._thread_local = threading.local()
        print(f"✅ OpenRouter API bağlantısı kuruldu! Model: {self.model}")

    def get_language_name(self, lang_code):
        lang_map = {
            'tr': 'Türkçe', 'en': 'İngilizce', 'es': 'İspanyolca', 'fr': 'Fransızca',
            'de': 'Almanca', 'it': 'İtalyanca', 'pt': 'Portekizce', 'ru': 'Rusça',
            'ja': '日本語', 'ko': '한국어', 'zh': '中文', 'ar': 'العربية'
        }
        return lang_map.get(lang_code, lang_code.upper())

    def _get_http_session(self):
        session = getattr(self._thread_local, 'session', None)
        if session is None:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            self._thread_local.session = session
        return session

    def call_openrouter_api(self, messages, max_retries=3):
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4000
        }
        session = self._get_http_session()
        
        for attempt in range(max_retries):
            try:
                response = session.post(
                    self.api_url,
                    headers=self._base_headers,
                    json=data,
                    timeout=60
                )
                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    if attempt == max_retries - 1:
                        raise Exception(f"API çağrısı başarısız: {response.status_code} - {response.text}")
            except requests.exceptions.Timeout:
                if attempt == max_retries - 1:
                    raise Exception("API çağrısı zaman aşımına uğradı")
            except Exception as e:
                if attempt == max_retries - 1:
                    raise

    @staticmethod
    def _parse_numbered_response(text):
        translated_map = {}
        for line in text.strip().split('\n'):
            stripped_line = line.strip()
            if '. ' not in stripped_line:
                continue

            parts = stripped_line.split('. ', 1)
            if parts[0].isdigit():
                translated_map[int(parts[0])] = parts[1].strip()
        return translated_map

    @staticmethod
    def _normalize_text_for_comparison(text):
        normalized = re.sub(r'\s+', ' ', str(text or '').strip().lower())
        return normalized

    def _validate_batch_translation(self, original_segments, translated_batch, batch_index, source_language, target_language):
        if target_language == source_language:
            return

        if not translated_batch:
            raise ValueError(f"Batch {batch_index + 1} boş çeviri üretti")

        unchanged_count = 0
        comparable_count = 0

        for original_segment, translated_segment in zip(original_segments, translated_batch):
            original_text = self._normalize_text_for_comparison(original_segment.get('text'))
            translated_text = self._normalize_text_for_comparison(translated_segment.get('text'))

            if not original_text or not translated_text:
                continue

            comparable_count += 1
            if original_text == translated_text:
                unchanged_count += 1

        if comparable_count and unchanged_count == comparable_count:
            raise ValueError(
                f"Batch {batch_index + 1} için model çeviri yerine metni aynen geri döndürdü"
            )

    def translate_batch(self, batch_segments, batch_index, target_lang_name, source_lang_name, source_language, target_language, fix_spelling):
        """Tek bir batch'i çevir"""
        if not batch_segments:
            return []
            
        texts_to_translate = [f"{i+1}. {segment['text']}" for i, segment in enumerate(batch_segments)]
        combined_text = "\n".join(texts_to_translate)
        
        # Eğer kaynak ve hedef dil aynıysa, sadece düzeltme yap (çeviri değil)
        if target_language == source_language:
            system_prompt = (
                "Sen altyazi metni duzeltme yapan deterministik bir motorsun. "
                "Yalnizca verilen numarali satirlarin ciktilarini uretirsin. "
                "Her girdi satiri icin ayni numarayla tek bir cikti satiri verirsin. "
                "Satir ekleme, silme, birlestirme veya bolme yapmazsin. "
                "Aciklama, baslik, not, kod blogu veya ekstra metin yazmazsin. "
                "Sadece yazim, noktalama ve kucuk dil bilgisi duzeltmeleri yaparsin; anlami degistirmezsin. "
                "Cikti bicimi kesinlikle `1. ...` seklindedir."
            )
            prompt = f"""Aşağıdaki {source_lang_name} numaralı altyazı satırlarını aynı dilde düzelt.

Çıktı kuralları:
- Sadece numaralı satırlar döndür.
- Her girdi satırı için aynı numarayla tek çıktı satırı üret.
- Satır sırasını koru.
- Anlamı değiştirme; yalnızca yazım, noktalama ve küçük dil bilgisi düzeltmeleri yap.
- Ek açıklama, başlık, not veya kod bloğu yazma.

Metin:
{combined_text}"""
        else:
            # Farklı diller ise çeviri yap - senkronizasyon için özel talimat
            system_prompt = (
                "Sen altyazi cevirisi yapan deterministik bir ceviri motorsun. "
                "Yalnizca verilen numarali satirlarin ciktilarini uretirsin. "
                "Her girdi satiri icin ayni numarayla tek bir cikti satiri verirsin. "
                "Satir ekleme, silme, birlestirme veya bolme yapmazsin. "
                "Aciklama, baslik, not, kod blogu veya ekstra metin yazmazsin. "
                "Ceviri kisa, dogal ve altyaziya uygun olur. "
                "Anlami korur, gereksiz dolgu kelimelerini cikarir. "
                "Hedef dil kaynak dilden farkliysa metni aynen geri dondurmezsin. "
                "Cikti bicimi kesinlikle `1. ...` seklindedir."
            )
            prompt = f"""Aşağıdaki {source_lang_name} numaralı altyazı satırlarını {target_lang_name} diline çevir.

Çıktı kuralları:
- Sadece numaralı satırlar döndür.
- Aynı sıra ve aynı numaraları koru.
- Her çıktı tek satır olsun.
- Altyazı için kısa, doğal ve okunaklı çevir.
- Gerekirse cümleyi kısalt ama anlamı koru.
- Ek açıklama, başlık, not veya kod bloğu yazma.
- Kaynak metni aynen kopyalama.

Metin:
{combined_text}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        try:
            result = self.call_openrouter_api(messages)
            
            if not result or not result.strip():
                raise ValueError(f"Batch {batch_index + 1} için boş yanıt alındı")

            translated_map = self._parse_numbered_response(result)
            if not translated_map:
                raise ValueError(
                    f"Batch {batch_index + 1} yanıtı numaralı formatta çözülemedi. "
                    f"Model yanıtı: {result[:300]}"
                )
            
            translated_batch = []
            for i, segment in enumerate(batch_segments):
                original_index = i + 1
                cleaned_text = translated_map.get(original_index, segment['text'])
                
                new_segment = segment.copy()
                new_segment['text'] = cleaned_text
                translated_batch.append(new_segment)

            self._validate_batch_translation(
                batch_segments,
                translated_batch,
                batch_index,
                source_language,
                target_language
            )
                
            return translated_batch
            
        except Exception as e:
            print(f"❌ Batch {batch_index + 1} hatası: {e}")
            raise

    def translate_and_correct_segments(self, segments, target_language, source_language="tr", fix_spelling=True, progress_callback=None):
        target_lang_name = self.get_language_name(target_language)
        source_lang_name = self.get_language_name(source_language)
        print(f"🌍 Toplu çeviri yapılıyor: {source_lang_name} -> {target_lang_name} ({len(segments)} segment)")
        
        if not segments:
            return []
        
        # ⚡ PARALEL İŞLEME: Segmentleri batch'lere böl
        BATCH_SIZE = 20  # Her batch'te 20 segment (API limitlerine göre ayarlanabilir)
        batches = [segments[i:i + BATCH_SIZE] for i in range(0, len(segments), BATCH_SIZE)]
        
        print(f"⚡ {len(batches)} batch paralel olarak işlenecek...")
        
        translated_segments = []
        completed_batches = 0
        batch_failures = []
        
        # ThreadPoolExecutor ile paralel işleme
        # API rate limit'e dikkat etmek için max_workers sınırla
        max_workers = 5 
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {
                executor.submit(
                    self.translate_batch, 
                    batch, i, target_lang_name, source_lang_name, 
                    source_language, target_language, fix_spelling
                ): i 
                for i, batch in enumerate(batches)
            }
            
            # Sonuçları toplamak için geçici liste (sıralamayı korumak için)
            batch_results = [None] * len(batches)
            
            for future in as_completed(future_to_batch):
                batch_index = future_to_batch[future]
                completed_batches += 1
                
                if progress_callback:
                    progress = (completed_batches / len(batches)) * 100
                    progress_callback("status", f"📝 Çevriliyor: Batch {completed_batches}/{len(batches)}...")
                    progress_callback("progress", progress)
                
                try:
                    batch_result = future.result()
                    batch_results[batch_index] = batch_result
                    print(f"✅ Batch {batch_index + 1}/{len(batches)} tamamlandı")
                except Exception as e:
                    print(f"❌ Batch {batch_index + 1} hatası: {e}")
                    batch_failures.append(f"Batch {batch_index + 1}: {e}")
        
        if batch_failures:
            failure_summary = "\n".join(batch_failures[:5])
            raise RuntimeError(
                "Çeviri tamamlanamadı. OpenRouter isteği veya model yanıtı başarısız oldu.\n"
                f"{failure_summary}"
            )

        # Sonuçları birleştir
        for batch_result in batch_results:
            if batch_result:
                translated_segments.extend(batch_result)
        
        # Çeviri sonrası senkronizasyon optimizasyonu
        if target_language != source_language:
            translated_segments = self.optimize_translation_timing(translated_segments, segments)
        
        if progress_callback: 
            progress_callback("progress", 100)
            progress_callback("status", "✅ Çeviri tamamlandı!")
        
        return translated_segments

    def optimize_translation_timing(self, translated_segments, original_segments):
        """Çeviri sonrası timing optimizasyonu"""
        # print("🔄 Çeviri senkronizasyonu optimize ediliyor...") # Log kirliliğini azalt
        
        optimized_segments = []
        
        for i, (translated, original) in enumerate(zip(translated_segments, original_segments)):
            # Orijinal ve çevrilmiş metin uzunluklarını karşılaştır
            original_len = len(original['text'])
            translated_len = len(translated['text'])
            
            # Uzunluk oranı
            length_ratio = translated_len / original_len if original_len > 0 else 1.0
            
            # Segment süresi
            duration = original['end'] - original['start']
            
            new_segment = translated.copy()
            
            # Eğer çeviri çok uzunsa ve segment kısaysa, süreyi biraz uzat
            if length_ratio > 1.3 and duration < 3.0:
                # Sonraki segment ile arasında boşluk varsa, biraz uzat
                if i < len(original_segments) - 1:
                    next_start = original_segments[i + 1]['start']
                    gap = next_start - original['end']
                    
                    if gap > 0.3:  # 300ms'den fazla boşluk varsa
                        extension = min(gap * 0.5, 0.5)  # Maksimum 500ms uzat
                        new_segment['end'] = original['end'] + extension
                        # print(f"📏 Segment {i+1} uzatıldı: +{extension:.2f}s (uzun çeviri)")
            
            # Eğer çeviri çok kısaysa, süreyi biraz kısalt
            elif length_ratio < 0.7 and duration > 1.0:
                reduction = min(duration * 0.2, 0.3)  # Maksimum 300ms kısalt
                new_segment['end'] = original['end'] - reduction
                # print(f"📏 Segment {i+1} kısaltıldı: -{reduction:.2f}s (kısa çeviri)")
            
            optimized_segments.append(new_segment)
        
        # Overlap kontrolü ve düzeltme
        for i in range(len(optimized_segments) - 1):
            current = optimized_segments[i]
            next_seg = optimized_segments[i + 1]
            
            if current['end'] > next_seg['start']:
                # Overlap var, düzelt
                current['end'] = next_seg['start'] - 0.1  # 100ms boşluk bırak
        
        return optimized_segments

    def translate_srt_file(self, srt_path, target_language, source_language="tr", fix_spelling=True, progress_callback=None, output_dir=None):
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"SRT dosyası bulunamadı: {srt_path}")
        
        print(f"📖 SRT dosyası okunuyor: {srt_path}")
        segments = SRTConverter.srt_to_segments(srt_path)
        print(f"📊 Toplam {len(segments)} segment bulundu")
        print(f"🔄 Kaynak dil: {source_language}, Hedef dil: {target_language}")
        
        try:
            translated_segments = self.translate_and_correct_segments(segments, target_language, source_language, fix_spelling, progress_callback)
        except Exception as e:
            print(f"❌ Çeviri sırasında hata oluştu: {e}")
            raise Exception(f"Çeviri başarısız oldu: {str(e)}")
        
        srt_path_obj = Path(srt_path)
        output_parent = Path(output_dir) if output_dir else srt_path_obj.parent
        os.makedirs(output_parent, exist_ok=True)
        
        if fix_spelling and target_language == source_language:
            new_srt_path = output_parent / f"{srt_path_obj.stem}_corrected.srt"
        else:
            new_srt_path = output_parent / f"{srt_path_obj.stem}_{target_language}.srt"
        
        SRTConverter.segments_to_srt(translated_segments, str(new_srt_path))
        print(f"✅ Çevrilmiş SRT kaydedildi: {new_srt_path}")
        return str(new_srt_path)

class SRTConverter:
    @staticmethod
    def format_time(seconds):
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        millis = int((seconds - total_seconds) * 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

    @staticmethod
    def parse_time(time_str):
        parts = time_str.replace(',', '.').split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

    @staticmethod
    def json_to_srt(json_data, srt_path):
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, item in enumerate(json_data):
                start = SRTConverter.format_time(item["start"])
                end = SRTConverter.format_time(item["end"])
                f.write(f"{i + 1}\n{start} --> {end}\n{item['text'].strip()}\n\n")
        print(f"🎯 SRT dosyası oluşturuldu: {srt_path}")

    @staticmethod
    def json_file_to_srt(json_path, srt_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        SRTConverter.json_to_srt(data, srt_path)

    @staticmethod
    def srt_to_segments(srt_path):
        segments = []
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        blocks = content.split('\n\n')
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                time_line = lines[1]
                start_str, end_str = time_line.split(' --> ')
                text = '\n'.join(lines[2:])
                segments.append({
                    'start': SRTConverter.parse_time(start_str),
                    'end': SRTConverter.parse_time(end_str),
                    'text': text
                })
        return segments

    @staticmethod
    def segments_to_srt(segments, srt_path):
        """Segmentleri SRT formatında kaydet - çakışma kontrolü ile"""
        # Son kontrol: Çakışmaları tespit et ve düzelt
        cleaned_segments = []
        MIN_GAP = 0.05
        
        for i, segment in enumerate(segments):
            current = segment.copy()
            
            # Önceki segment ile çakışma kontrolü
            if cleaned_segments:
                prev = cleaned_segments[-1]
                
                # Çakışma varsa düzelt
                if current['start'] < prev['end']:
                    overlap = prev['end'] - current['start']
                    print(f"⚠️ SRT yazarken çakışma tespit edildi (Segment {i}): {overlap:.2f}s")
                    
                    # Önceki segmentin bitişini çek
                    prev['end'] = current['start'] - MIN_GAP
                    
                    # Önceki segment çok kısa olmasın
                    if prev['end'] <= prev['start']:
                        prev['end'] = prev['start'] + 0.1
                    
                    print(f"✅ Düzeltildi: Segment {i-1} bitiş: {prev['end']:.2f}s, Segment {i} başlangıç: {current['start']:.2f}s")
            
            # Segment süresini kontrol et
            duration = current['end'] - current['start']
            if duration < 0.1:
                current['end'] = current['start'] + 0.5
                print(f"⚠️ Segment {i} çok kısa ({duration:.2f}s), 0.5s'ye uzatıldı")
            
            cleaned_segments.append(current)
        
        # SRT dosyasını yaz
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(cleaned_segments):
                start = SRTConverter.format_time(segment["start"])
                end = SRTConverter.format_time(segment["end"])
                f.write(f"{i + 1}\n{start} --> {end}\n{segment['text'].strip()}\n\n")
        
        print(f"🎯 SRT dosyası oluşturuldu: {srt_path} ({len(cleaned_segments)} segment)")
