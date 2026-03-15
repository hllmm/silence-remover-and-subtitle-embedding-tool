"""Groq transcription pipeline and chunk orchestration."""

import json
import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from .core import (
    apply_padding_to_silence_intervals,
    build_audio_filter_graph,
    build_av_filter_graph,
    calculate_speech_protection_profile,
    condense_keep_intervals,
    detect_silence_intervals,
    fast_trim_audio_with_stream_copy,
    get_audio_cleanup_filter_chain,
    get_media_duration,
    get_media_stream_info,
    invert_intervals,
    merge_close_intervals,
    optimize_intervals_for_fast_audio_copy,
    remap_concatenated_time,
    resolve_ffmpeg_path,
    resolve_ffprobe_path,
    should_use_fast_audio_concat,
    split_intervals_into_batches,
    write_ffmpeg_concat_list,
)
from .embedding import SubtitleEmbedder

class VideoTranscriber:
    def __init__(
        self,
        ffmpeg_path=None,
        silence_threshold=-40,
        min_silence_duration=0.5,
        speech_protection=0.35,
        remove_silence=False,
        remove_background_noise=False,
        audio_cleanup_profile='safe',
    ):
        load_dotenv('api.env', override=True)
        self.api_key = os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("❌ GROQ_API_KEY bulunamadı!")
        
        # ffmpeg yolu belirtilmemişse, önce workspace'deki ffmpeg.exe'yi kontrol et
        if not ffmpeg_path:
            workspace_ffmpeg = Path('ffmpeg.exe')
            if workspace_ffmpeg.exists():
                ffmpeg_path = str(workspace_ffmpeg.resolve())
                print(f"✅ Workspace'deki ffmpeg kullanılıyor: {ffmpeg_path}")
            else:
                ffmpeg_path = 'ffmpeg'
        
        self.ffmpeg_path = resolve_ffmpeg_path(ffmpeg_path)
        self.ffprobe_path = resolve_ffprobe_path(self.ffmpeg_path)
        # Groq client'ı timeout ile oluştur (300 saniye = 5 dakika)
        self.client = Groq(
            api_key=self.api_key,
            timeout=300.0  # 5 dakika timeout
        )
        
        # Sessizlik budama ayarları
        self.silence_threshold = silence_threshold  # dB cinsinden (örn: -40dB)
        self.min_silence_duration = min_silence_duration  # saniye cinsinden
        self.speech_protection = speech_protection  # konuşma kenarları için koruma payı
        self.remove_silence = remove_silence  # Sessizlik budama aktif mi?
        self.remove_background_noise = remove_background_noise
        self.audio_cleanup_profile = audio_cleanup_profile if remove_background_noise else 'off'
        self.audio_cleanup_filter = get_audio_cleanup_filter_chain(self.audio_cleanup_profile)
        
        print("✅ Groq API bağlantısı kuruldu! (Timeout: 300s)")
        if self.remove_silence:
            print(
                f"🔇 Sessizlik budama aktif: "
                f"Eşik={self.silence_threshold}dB, "
                f"Min süre={self.min_silence_duration}s, "
                f"Koruma={self.speech_protection}s"
            )
        if self.audio_cleanup_filter:
            print(f"🔉 Dip ses temizleme aktif: profil={self.audio_cleanup_profile}")

    def extract_audio(self, video_path, audio_path):
        try:
            # ⚡ Tüm CPU çekirdeklerini kullan (threads=0)
            cmd = [self.ffmpeg_path, '-threads', '0', '-i', video_path, '-vn']
            if self.audio_cleanup_filter:
                cmd.extend(['-af', self.audio_cleanup_filter])
            cmd.extend(['-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_path, '-y'])
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as exc:
            error_output = (exc.stderr or exc.stdout or str(exc)).strip()
            print(f"❌ Ses çıkarma hatası: {error_output}")
            return False
        except Exception as exc:
            print(f"❌ Ses çıkarma genel hatası: {exc}")
            return False
    
    def remove_silence_from_audio(self, audio_path, output_path, progress_callback=None):
        """
        Audacity tarzı sessizlik budama - sessiz bölümleri tespit edip kaldırır (HIZLANDIRILMIŞ)
        NOT: Bu fonksiyon sadece transkripsiyon için kullanılır (ses dosyası üzerinde)
        """
        try:
            if progress_callback:
                progress_callback("status", "🔇 Sessizlik budama işlemi başlatılıyor...")
            
            print(f"🔇 Sessizlik budama: {audio_path}")
            protection_profile = calculate_speech_protection_profile(
                self.silence_threshold,
                self.min_silence_duration,
                self.speech_protection
            )
            keep_silence = protection_profile['keep_silence']
            print(
                f"   Eşik: {self.silence_threshold}dB, "
                f"Min süre: {self.min_silence_duration}s, "
                f"Koruma: {protection_profile['speech_protection']}s, "
                f"Korunan sessizlik: {keep_silence}s"
            )
            audio_filter_chain = (
                f'silenceremove='
                f'start_periods=1:'
                f'start_duration={self.min_silence_duration}:'
                f'start_threshold={self.silence_threshold}dB:'
                f'start_silence={keep_silence}:'
                f'stop_periods=-1:'
                f'stop_duration={self.min_silence_duration}:'
                f'stop_threshold={self.silence_threshold}dB:'
                f'stop_silence={keep_silence}:'
                f'detection=rms'
            )
            if self.audio_cleanup_filter:
                audio_filter_chain = f'{self.audio_cleanup_filter},{audio_filter_chain}'
             
            # HIZLANDIRMA OPTİMİZASYONLARI:
            # 1. Tek geçişte hem başlangıç hem bitiş sessizliklerini kaldır
            # 2. RMS tespiti kullan (peak yerine - daha hızlı)
            # 3. Daha agresif parametreler
            
            cmd = [
                self.ffmpeg_path,
                '-i', audio_path,
                '-af', audio_filter_chain,
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-threads', '0',  # Tüm CPU çekirdeklerini kullan
                output_path,
                '-y'
            ]
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # Dosya boyutlarını karşılaştır
            original_size = os.path.getsize(audio_path) / (1024 * 1024)
            trimmed_size = os.path.getsize(output_path) / (1024 * 1024)
            reduction = ((original_size - trimmed_size) / original_size) * 100 if original_size > 0 else 0
            
            print(f"✅ Sessizlik budama tamamlandı!")
            print(f"   Orijinal: {original_size:.2f}MB → Budanmış: {trimmed_size:.2f}MB")
            print(f"   Azalma: {reduction:.1f}%")
            
            if progress_callback:
                progress_callback("status", f"✅ Sessizlik budama tamamlandı! (%{reduction:.1f} azalma)")
            
            return True
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if hasattr(e, 'stderr') and e.stderr else str(e)
            print(f"❌ Sessizlik budama hatası: {error_msg}")
            if progress_callback:
                progress_callback("status", "⚠️ Sessizlik budama başarısız, orijinal ses kullanılacak")
            return False
        except Exception as e:
            print(f"❌ Sessizlik budama genel hatası: {e}")
            if progress_callback:
                progress_callback("status", "⚠️ Sessizlik budama başarısız, orijinal ses kullanılacak")
            return False

    def get_audio_duration(self, audio_path):
        return get_media_duration(audio_path, self.ffprobe_path)

    def _cleanup_temp_file(self, temp_file, retries=5, delay_seconds=0.25):
        if not temp_file:
            return

        temp_path = Path(temp_file)
        for attempt in range(retries):
            try:
                if not temp_path.exists():
                    return

                temp_path.unlink()
                print(f"🧹 Geçici dosya temizlendi: {temp_path.name}")
                return
            except FileNotFoundError:
                return
            except PermissionError as exc:
                if attempt == retries - 1:
                    print(f"⚠️ Geçici dosya temizlenemedi: {temp_path.name} - {exc}")
                    return
                time.sleep(delay_seconds)
            except OSError as exc:
                if getattr(exc, "winerror", None) == 32 and attempt < retries - 1:
                    time.sleep(delay_seconds)
                    continue

                print(f"⚠️ Geçici dosya temizlenemedi: {temp_path.name} - {exc}")
                return

    def check_file_size(self, file_path, max_size_mb=19):
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        print(f"📊 Dosya boyutu: {file_size:.1f}MB")
        return file_size <= max_size_mb

    def split_audio(self, audio_path, max_size_mb=19, max_duration_sec=870):
        chunks = []
        base_name = Path(audio_path).stem
        temp_dir = Path(tempfile.gettempdir())
        
        try:
            total_duration = self.get_audio_duration(audio_path)
            if not total_duration:
                return [{'path': Path(audio_path), 'start_time': 0, 'duration': 0}]
            
            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            
            chunks_by_duration = 1
            if total_duration > max_duration_sec:
                chunks_by_duration = int(total_duration / max_duration_sec) + 1
            
            chunks_by_size = 1
            if file_size_mb > max_size_mb:
                chunks_by_size = int(file_size_mb / max_size_mb) + 1
            
            num_chunks = max(chunks_by_duration, chunks_by_size)
            
            if num_chunks <= 1:
                return [{'path': Path(audio_path), 'start_time': 0, 'duration': total_duration}]
            
            chunk_duration = total_duration / num_chunks
            print(f"📦 Ses dosyası, süre (> {max_duration_sec}s) veya boyut (> {max_size_mb}MB) limiti nedeniyle {num_chunks} parçaya bölünüyor.")
            
            for i in range(num_chunks):
                start_time = i * chunk_duration
                chunk_path = temp_dir / f"{base_name}_chunk_{i:03d}.wav"
                
                # ⚡ OPTİMİZE: -ss parametresini -i'den önce koy (daha hızlı seek)
                if i == num_chunks - 1:
                    duration_to_process = total_duration - start_time
                    cmd = [self.ffmpeg_path, '-ss', str(start_time), '-i', audio_path,
                           '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(chunk_path), '-y']
                else:
                    duration_to_process = chunk_duration
                    cmd = [self.ffmpeg_path, '-ss', str(start_time), '-t', str(duration_to_process), '-i', audio_path,
                           '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(chunk_path), '-y']
                
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    chunk_info = {
                        'path': chunk_path,
                        'start_time': start_time,
                        'duration': duration_to_process
                    }
                    chunks.append(chunk_info)
                except subprocess.CalledProcessError as e:
                    print(f"❌ Ses parçalama hatası (chunk {i}): {e.stderr.decode()}")
                    return [{'path': Path(audio_path), 'start_time': 0, 'duration': total_duration}]
            
            return chunks
        except Exception as e:
            print(f"❌ Ses parçalama sırasında genel hata: {e}")
            return [{'path': Path(audio_path), 'start_time': 0, 'duration': self.get_audio_duration(audio_path) or 0}]

    def _map_chunk_timestamp(self, timestamp, chunk_info):
        time_map = chunk_info.get('time_map')
        if time_map:
            return remap_concatenated_time(timestamp, time_map)
        return timestamp + chunk_info.get('start_time', 0)

    def build_speech_chunks(self, audio_path, keep_intervals, max_size_mb=19, max_duration_sec=870, progress_callback=None):
        if not keep_intervals:
            return []

        total_duration = self.get_audio_duration(audio_path) or sum(end - start for start, end in keep_intervals)
        file_size_bytes = os.path.getsize(audio_path)
        bytes_per_second = file_size_bytes / total_duration if total_duration else 32000
        max_duration_by_size = (max_size_mb * 1024 * 1024 * 0.95) / bytes_per_second if bytes_per_second else max_duration_sec
        target_duration = min(max_duration_sec, max_duration_by_size) if max_duration_by_size else max_duration_sec
        target_duration = max(30.0, target_duration)

        normalized_intervals = []
        for start, end in keep_intervals:
            cursor = start
            while end - cursor > target_duration:
                normalized_intervals.append((cursor, cursor + target_duration))
                cursor += target_duration
            if end - cursor >= 0.1:
                normalized_intervals.append((cursor, end))

        grouped_intervals = []
        current_group = []
        current_duration = 0.0
        max_intervals_per_chunk = 75

        for interval in normalized_intervals:
            interval_duration = interval[1] - interval[0]
            if current_group and (
                current_duration + interval_duration > target_duration or len(current_group) >= max_intervals_per_chunk
            ):
                grouped_intervals.append(current_group)
                current_group = [interval]
                current_duration = interval_duration
            else:
                current_group.append(interval)
                current_duration += interval_duration

        if current_group:
            grouped_intervals.append(current_group)

        chunks = []
        base_name = Path(audio_path).stem
        temp_dir = Path(tempfile.gettempdir())

        for chunk_index, interval_group in enumerate(grouped_intervals):
            if progress_callback:
                progress_callback(
                    "status",
                    f"✂️ Konuşma parçaları hazırlanıyor ({chunk_index + 1}/{len(grouped_intervals)})..."
                )

            chunk_path = temp_dir / f"{base_name}_speech_{chunk_index:03d}.wav"
            filter_complex, output_label = build_audio_filter_graph(interval_group)

            time_map = []
            local_offset = 0.0
            for start, end in interval_group:
                duration = end - start
                time_map.append({
                    'chunk_start': local_offset,
                    'chunk_end': local_offset + duration,
                    'source_start': start,
                    'source_end': end
                })
                local_offset += duration

            with tempfile.NamedTemporaryFile(mode='w', suffix=".ffscript", delete=False, encoding='utf-8') as filter_file:
                filter_file.write(filter_complex)
                filter_script_path = filter_file.name

            try:
                cmd = [
                    self.ffmpeg_path,
                    '-hide_banner',
                    '-y',
                    '-i', str(audio_path),
                    '-filter_complex_script', filter_script_path,
                    '-map', output_label,
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    '-threads', '0',
                    str(chunk_path)
                ]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Konuşma parçası oluşturulamadı: {e.stderr or e}") from e
            finally:
                try:
                    os.unlink(filter_script_path)
                except OSError:
                    pass

            chunks.append({
                'path': chunk_path,
                'start_time': interval_group[0][0],
                'duration': local_offset,
                'time_map': time_map
            })

        return chunks

    def transcribe_audio_file(self, audio_path, language="tr", max_retries=3):
        """
        Ses dosyasını transkript et (retry mekanizması ile)
        """
        for attempt in range(max_retries):
            try:
                print(f"🔄 API çağrısı başlatılıyor: {os.path.basename(audio_path)} (Deneme {attempt + 1}/{max_retries})")
                start_time = time.time()
                
                with open(audio_path, "rb") as file:
                    file_content = file.read()
                    file_size_mb = len(file_content) / (1024 * 1024)
                    print(f"📊 Dosya boyutu: {file_size_mb:.2f}MB")
                    
                    print(f"⏳ API'ye gönderiliyor... (Bu işlem 10-60 saniye sürebilir)")
                    transcription = self.client.audio.transcriptions.create(
                        file=(os.path.basename(audio_path), file_content),
                        model="whisper-large-v3",
                        language=language if language != "auto" else None,
                        response_format="verbose_json",
                        temperature=0,
                        timestamp_granularities=["word"]
                    )
                    
                    elapsed = time.time() - start_time
                    print(f"✅ API yanıtı alındı ({elapsed:.1f}s)")
                    return transcription
                    
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"❌ Transkript hatası (Deneme {attempt + 1}/{max_retries}, {elapsed:.1f}s): {e}")
                
                # Son denemeyse hata fırlat
                if attempt == max_retries - 1:
                    print(f"❌ Tüm denemeler başarısız oldu!")
                    import traceback
                    traceback.print_exc()
                    raise
                
                # Tekrar denemeden önce bekle (exponential backoff)
                wait_time = 2 ** attempt  # 1s, 2s, 4s...
                print(f"⏳ {wait_time} saniye bekleniyor...")
                time.sleep(wait_time)
    
    def _process_single_chunk(self, chunk_info, language, max_chars_per_line):
        """Tek bir chunk'ı işle (paralel işleme için)"""
        chunk_path = chunk_info['path']
        segments = []
        detected_language = None
        result = None

        try:
            print(f"🎯 Chunk işleme başladı: {chunk_path.name if hasattr(chunk_path, 'name') else chunk_path}")
            result = self.transcribe_audio_file(str(chunk_path), language)
            print(f"🎯 Chunk transkript tamamlandı, segment işleniyor...")
            
            # Word-level timestamps kullan
            words = []
            if hasattr(result, 'words'):
                words = result.words
            elif isinstance(result, dict) and 'words' in result:
                words = result['words']
            
            if words:
                word_list = []
                for word_data in words:
                    if isinstance(word_data, dict):
                        raw_start = word_data.get('start', 0)
                        raw_end = word_data.get('end', 0)
                        word_text = word_data.get('word', '')
                    else:
                        raw_start = getattr(word_data, 'start', 0)
                        raw_end = getattr(word_data, 'end', 0)
                        word_text = getattr(word_data, 'word', '')

                    mapped_start = self._map_chunk_timestamp(raw_start, chunk_info)
                    mapped_end = self._map_chunk_timestamp(raw_end, chunk_info)
                    if mapped_end <= mapped_start:
                        mapped_end = mapped_start + 0.05

                    word_list.append({
                        'word': word_text,
                        'start': mapped_start,
                        'end': mapped_end
                    })
                
                segments = self.split_long_segments_by_words(word_list, max_chars=max_chars_per_line, max_duration=5.0)
                
                processed_segments = []
                for segment in segments:
                    segment_dict = {
                        'start': segment['start'],
                        'end': segment['end'],
                        'text': segment['text'].strip()
                    }
                    if segment_dict['text']:
                        processed_segments.append(segment_dict)
                segments = processed_segments
            else:
                # Fallback: segment-level kullan
                result_segments = []
                if hasattr(result, 'segments'):
                    result_segments = result.segments
                elif isinstance(result, dict) and 'segments' in result:
                    result_segments = result['segments']
                
                for segment in result_segments:
                    if isinstance(segment, dict):
                        segment_dict = {
                            'start': self._map_chunk_timestamp(segment.get('start', 0), chunk_info),
                            'end': self._map_chunk_timestamp(segment.get('end', 0), chunk_info),
                            'text': segment.get('text', '').strip()
                        }
                    else:
                        segment_dict = {
                            'start': self._map_chunk_timestamp(getattr(segment, 'start', 0), chunk_info),
                            'end': self._map_chunk_timestamp(getattr(segment, 'end', 0), chunk_info),
                            'text': getattr(segment, 'text', '').strip()
                        }
                    
                    if segment_dict['end'] <= segment_dict['start']:
                        segment_dict['end'] = segment_dict['start'] + 0.1

                    if segment_dict['text']:
                        segments.append(segment_dict)
        
        except Exception as e:
            print(f"❌ Chunk işleme hatası: {e}")
        
        # Dil bilgisini de döndür
        if result and hasattr(result, 'language'):
            detected_language = result.language
            
        return segments, detected_language
    
    def _transcribe_chunks_parallel(self, audio_chunks, language, max_chars_per_line, progress_callback=None):
        """Chunk'ları paralel olarak işle (HIZLANDIRMA + UI OPTİMİZASYONU)"""
        all_segments = []
        completed = 0
        detected_language = None
        last_update_time = 0
        UPDATE_INTERVAL = 0.5  # UI'yi her 0.5 saniyede bir güncelle (kasma önleme)
        
        # ⚡ ThreadPoolExecutor ile paralel işleme (artırılmış worker sayısı)
        max_workers = min(len(audio_chunks), 10)  # Maksimum 10 paralel işlem (API limiti izin veriyorsa)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Tüm chunk'ları gönder
            future_to_chunk = {
                executor.submit(self._process_single_chunk, chunk, language, max_chars_per_line): i 
                for i, chunk in enumerate(audio_chunks)
            }
            
            # Tamamlananları topla
            chunk_results = [None] * len(audio_chunks)
            
            for future in as_completed(future_to_chunk):
                chunk_index = future_to_chunk[future]
                completed += 1
                
                # UI güncellemelerini throttle et (kasma önleme)
                current_time = time.time()
                should_update = (current_time - last_update_time) >= UPDATE_INTERVAL or completed == len(audio_chunks)
                
                if progress_callback and should_update:
                    progress_callback("status", f"📝 Parça {completed}/{len(audio_chunks)} tamamlandı...")
                    progress_callback("progress", (completed / len(audio_chunks)) * 100)
                    last_update_time = current_time
                
                try:
                    segments, chunk_language = future.result()
                    chunk_results[chunk_index] = segments
                    
                    # İlk başarılı chunk'tan dili al
                    if chunk_language and not detected_language:
                        detected_language = chunk_language
                        
                    print(f"✅ Chunk {chunk_index + 1} tamamlandı ({len(segments)} segment)")
                except Exception as e:
                    print(f"❌ Chunk {chunk_index + 1} hatası: {e}")
                    chunk_results[chunk_index] = []
        
        # Sonuçları sırayla birleştir
        for segments in chunk_results:
            if segments:
                all_segments.extend(segments)
        
        return all_segments, detected_language
    
    def _transcribe_chunks_sequential(self, audio_chunks, language, max_chars_per_line, progress_callback=None):
        """Chunk'ları sırayla işle (tek chunk için + UI OPTİMİZASYONU)"""
        all_segments = []
        detected_language = None
        last_update_time = 0
        UPDATE_INTERVAL = 0.5  # UI'yi her 0.5 saniyede bir güncelle (kasma önleme)
        
        for i, chunk_info in enumerate(audio_chunks):
            # UI güncellemelerini throttle et (kasma önleme)
            current_time = time.time()
            should_update = (current_time - last_update_time) >= UPDATE_INTERVAL or i == len(audio_chunks) - 1
            
            if progress_callback and should_update:
                progress_callback("status", f"📝 Parça {i+1}/{len(audio_chunks)} işleniyor...")
                progress_callback("progress", (i / len(audio_chunks)) * 100)
                last_update_time = current_time
            
            segments, chunk_language = self._process_single_chunk(chunk_info, language, max_chars_per_line)
            all_segments.extend(segments)
            
            # İlk başarılı chunk'tan dili al
            if chunk_language and not detected_language:
                detected_language = chunk_language
                print(f"✅ Dil otomatik olarak algılandı: {detected_language}")
        
        return all_segments, detected_language

    def split_long_segments_by_words(self, words, max_chars=80, max_duration=3.0):
        """Word-level timestamps kullanarak uzun cümleleri parçalara böler ve çakışmaları önler"""
        if not words:
            return []
        
        segments = []
        MIN_SEGMENT_GAP = 0.05  # Segmentler arası minimum boşluk
        
        current_segment = {
            'start': words[0].get('start', 0),
            'end': words[0].get('end', 0),
            'text': words[0].get('word', '').strip()
        }
        
        for word_data in words[1:]:
            word = word_data.get('word', '').strip()
            word_start = word_data.get('start', current_segment['end'])
            word_end = word_data.get('end', word_start)
            
            # Yeni kelimeyi eklediğimizde segment uzunluğunu kontrol et
            potential_text = current_segment['text'] + ' ' + word
            potential_duration = word_end - current_segment['start']
            
            # Eğer segment çok uzun olacaksa veya süre limiti aşılacaksa, yeni segment başlat
            if len(potential_text) > max_chars or potential_duration > max_duration:
                # Mevcut segmenti kaydet (bitiş zamanını bir miktar erkene çek)
                if current_segment['text']:
                    # Çakışmayı önlemek için segment bitişini yeni segment başlangıcından önceye al
                    current_segment['end'] = min(current_segment['end'], word_start - MIN_SEGMENT_GAP)
                    
                    # Segment süresinin pozitif olduğundan emin ol
                    if current_segment['end'] <= current_segment['start']:
                        current_segment['end'] = current_segment['start'] + 0.1
                    
                    segments.append(current_segment)
                
                # Yeni segment başlat (önceki segmentten sonra başladığından emin ol)
                safe_start = word_start
                if segments:
                    safe_start = max(word_start, segments[-1]['end'] + MIN_SEGMENT_GAP)
                
                current_segment = {
                    'start': safe_start,
                    'end': max(word_end, safe_start + 0.1),  # Minimum süre garantisi
                    'text': word
                }
            else:
                # Kelimeyi mevcut segmente ekle
                current_segment['text'] = potential_text
                current_segment['end'] = word_end
        
        # Son segmenti ekle
        if current_segment['text']:
            # Son segment için de çakışma kontrolü
            if segments and current_segment['start'] < segments[-1]['end']:
                current_segment['start'] = segments[-1]['end'] + MIN_SEGMENT_GAP
            
            # Segment süresinin pozitif olduğundan emin ol
            if current_segment['end'] <= current_segment['start']:
                current_segment['end'] = current_segment['start'] + 0.5
            
            segments.append(current_segment)
        
        return segments

    def merge_segments_seamlessly(self, all_segments):
        """Segmentleri birleştir ve çakışmaları önle"""
        if len(all_segments) <= 1:
            return all_segments
        
        # Başlangıç zamanına göre sırala
        all_segments.sort(key=lambda x: x['start'])
        corrected_segments = []
        
        MIN_GAP = 0.1  # Segmentler arası minimum boşluk (saniye)
        
        for i, segment in enumerate(all_segments):
            if i == 0:
                corrected_segments.append(segment.copy())
            else:
                prev_segment = corrected_segments[-1]
                current_segment = segment.copy()
                
                # Çakışma kontrolü: Mevcut segment öncekinden önce başlıyorsa
                if current_segment['start'] < prev_segment['end']:
                    overlap = prev_segment['end'] - current_segment['start']
                    print(f"⚠️ Çakışma tespit edildi! Segment {i} ve {i+1} arasında {overlap:.2f}s örtüşme")
                    
                    # Önceki segmentin bitişini, mevcut segmentin başlangıcından MIN_GAP önceye çek
                    prev_segment['end'] = max(
                        prev_segment['start'] + 0.1,  # Minimum segment süresi
                        current_segment['start'] - MIN_GAP
                    )
                    print(f"✅ Düzeltildi: Önceki segment {prev_segment['end']:.2f}s'de bitiyor")
                
                # Çok küçük boşlukları kontrol et
                gap = current_segment['start'] - prev_segment['end']
                if gap < 0:
                    # Negatif boşluk (hala çakışma var), mevcut segmenti ileriye kaydır
                    current_segment['start'] = prev_segment['end'] + MIN_GAP
                    print(f"⚠️ Segment {i+1} başlangıcı düzeltildi: {current_segment['start']:.2f}s")
                
                # Segment süresini kontrol et (çok kısa olmamalı)
                segment_duration = current_segment['end'] - current_segment['start']
                if segment_duration < 0.1:
                    current_segment['end'] = current_segment['start'] + 0.5  # Minimum 0.5 saniye
                
                corrected_segments.append(current_segment)
                
                # Büyük boşlukları raporla
                if gap > 1.0:
                    print(f"ℹ️ Segment {i} ve {i+1} arasında {gap:.1f}s boşluk")
        
        return corrected_segments

    def transcribe_video(self, video_path, language="tr", progress_callback=None):
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video dosyası bulunamadı: {video_path}")
        
        print(f"🎬 Video işleniyor: {video_path}")
        
        # Video çözünürlüğünü kontrol et ve dikey video için karakter uzunluğunu ayarla
        try:
            from pathlib import Path as PathLib
            video_width, video_height = SubtitleEmbedder.get_video_resolution(video_path, self.ffmpeg_path)
            is_vertical = video_height and video_width and video_height > video_width
            
            if is_vertical:
                # Dikey videolar için daha kısa satırlar (ekran dar olduğu için)
                max_chars_per_line = 35  # Dikey video için optimize
                print(f"📱 Dikey video tespit edildi ({video_width}x{video_height}) - Karakter limiti: {max_chars_per_line}")
            else:
                # Yatay videolar için standart
                max_chars_per_line = 80
                if video_width and video_height:
                    print(f"🖥️ Yatay video ({video_width}x{video_height}) - Karakter limiti: {max_chars_per_line}")
        except:
            # Hata durumunda varsayılan değer
            max_chars_per_line = 80
            is_vertical = False
        
        temp_audio_fd, temp_audio_path = tempfile.mkstemp(suffix=".wav")
        os.close(temp_audio_fd)

        try:
            if progress_callback: 
                progress_callback("status", "🎵 Videodan ses çıkarılıyor...")
            
            audio_extracted = self.extract_audio(video_path, temp_audio_path)
            if not audio_extracted:
                print("❌ Ses çıkarmada hata!")
                return None

            MAX_DURATION_SECONDS = 900
            audio_duration = self.get_audio_duration(temp_audio_path)
            audio_chunks = []

            if self.remove_silence and audio_duration:
                try:
                    if progress_callback:
                        progress_callback("status", "🔍 Sessizlikler tespit ediliyor...")

                    silence_intervals = detect_silence_intervals(
                        self.ffmpeg_path,
                        temp_audio_path,
                        self.silence_threshold,
                        self.min_silence_duration,
                        total_duration=audio_duration
                    )
                    protection_profile = calculate_speech_protection_profile(
                        self.silence_threshold,
                        self.min_silence_duration,
                        self.speech_protection
                    )
                    print(f"🔍 {len(silence_intervals)} ham sessizlik aralığı tespit edildi")

                    silence_intervals = merge_close_intervals(silence_intervals, gap_threshold=0.2)
                    silence_intervals = apply_padding_to_silence_intervals(
                        silence_intervals,
                        audio_duration,
                        padding_after_speech=protection_profile['padding_after_speech'],
                        padding_before_speech=protection_profile['padding_before_speech']
                    )
                    silence_intervals = merge_close_intervals(silence_intervals, gap_threshold=0.05)
                    keep_intervals = invert_intervals(silence_intervals, audio_duration, min_clip_duration=0.1)
                    condensed_intervals = condense_keep_intervals(keep_intervals, target_max_segments=100)
                    if len(condensed_intervals) != len(keep_intervals):
                        print(f"🔗 Konuşma aralıkları birleştirildi: {len(keep_intervals)} → {len(condensed_intervals)}")
                    keep_intervals = condensed_intervals

                    if keep_intervals and not (
                        len(keep_intervals) == 1 and
                        abs(keep_intervals[0][0]) < 0.001 and
                        abs(keep_intervals[0][1] - audio_duration) < 0.1
                    ):
                        audio_chunks = self.build_speech_chunks(
                            temp_audio_path,
                            keep_intervals,
                            max_size_mb=19,
                            max_duration_sec=MAX_DURATION_SECONDS - 30,
                            progress_callback=progress_callback
                        )
                        print(f"✂️ Sessizlik atlandı, {len(audio_chunks)} konuşma parçası hazırlandı")
                    else:
                        print("ℹ️ Anlamlı sessizlik budaması bulunamadı, tam ses kullanılacak")
                except Exception as e:
                    print(f"⚠️ Sessizlik optimizasyonu atlandı: {e}")

            if not audio_chunks:
                is_oversized = not self.check_file_size(temp_audio_path)
                is_overlong = audio_duration and audio_duration > MAX_DURATION_SECONDS

                if is_oversized or is_overlong:
                    if is_overlong and not is_oversized:
                        print(f"🕒 Ses süresi ({audio_duration:.0f}s) {MAX_DURATION_SECONDS}s limitini aştığı için bölünecek.")
                    if progress_callback:
                        progress_callback("status", "📦 Ses dosyası parçalara bölünüyor...")
                    audio_chunks = self.split_audio(temp_audio_path)
                else:
                    audio_chunks = [{'path': Path(temp_audio_path), 'start_time': 0, 'duration': audio_duration}]
            
            print(f"🔊 Ses transkript ediliyor ({len(audio_chunks)} parça)...")
            print(f"📋 Chunk detayları: {[{'path': str(c['path']), 'duration': c.get('duration', 0)} for c in audio_chunks]}")
            all_segments = []
            detected_language = None
            
            # 🚀 PARALEL İŞLEME: Birden fazla chunk varsa paralel işle
            if len(audio_chunks) > 1:
                print(f"⚡ Paralel işleme aktif: {len(audio_chunks)} parça eş zamanlı işlenecek")
                all_segments, detected_language = self._transcribe_chunks_parallel(
                    audio_chunks, language, max_chars_per_line, progress_callback
                )
            else:
                # Tek chunk için normal işleme
                print(f"🔄 Sıralı işleme aktif: 1 parça işlenecek")
                all_segments, detected_language = self._transcribe_chunks_sequential(
                    audio_chunks, language, max_chars_per_line, progress_callback
                )
            
            if detected_language:
                print(f"✅ Dil tespit edildi: {detected_language}")
            
            if progress_callback: 
                progress_callback("status", "✅ Transkript tamamlandı!")
            
            all_segments = self.merge_segments_seamlessly(all_segments)
            all_segments.sort(key=lambda x: x['start'])
            
            final_lang = detected_language if language == "auto" and detected_language else language
            final_result = {
                'segments': all_segments,
                'language': final_lang,
                'text': ' '.join([seg['text'] for seg in all_segments])
            }
            
            return final_result
            
        finally:
            temp_files_to_clean = {temp_audio_path}

            if 'audio_chunks' in locals():
                for chunk in audio_chunks:
                    chunk_path = chunk.get('path')
                    if chunk_path:
                        temp_files_to_clean.add(str(chunk_path))

            for temp_file in temp_files_to_clean:
                self._cleanup_temp_file(temp_file)

    def save_json(self, result, output_path):
        segments_data = []
        for segment in result['segments']:
            segments_data.append({
                "start": round(segment['start'], 3),
                "end": round(segment['end'], 3),
                "text": segment['text'].strip()
            })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(segments_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 JSON dosyası kaydedildi: {output_path}")
        return segments_data
