"""Subtitle embedding helpers and encoder detection."""

import subprocess
from pathlib import Path

from .core import (
    create_ffmpeg_safe_output_path,
    finalize_ffmpeg_output_path,
    get_media_stream_info,
    resolve_ffmpeg_path,
    resolve_ffprobe_path,
)


class SubtitleEmbedder:
    # GPU encoder cache: detect once per ffmpeg binary and codec family.
    _gpu_encoder_cache = {}

    @staticmethod
    def check_ffmpeg(ffmpeg_path=None):
        ffmpeg_binary = resolve_ffmpeg_path(ffmpeg_path)
        try:
            subprocess.run([ffmpeg_binary, '-version'], capture_output=True, check=True)
            return True
        except Exception:
            return False

    @staticmethod
    def detect_gpu_encoder(ffmpeg_path=None, preferred_codec='h264'):
        """
        Detect the best usable encoder for the current system.
        """
        ffmpeg_binary = resolve_ffmpeg_path(ffmpeg_path)
        codec_family = 'hevc' if str(preferred_codec).lower() in {'hevc', 'h265', 'x265'} else 'h264'
        cache = SubtitleEmbedder._gpu_encoder_cache
        if not isinstance(cache, dict):
            cache = {}
            SubtitleEmbedder._gpu_encoder_cache = cache

        cache_key = f"{ffmpeg_binary}|{codec_family}"
        if cache_key in cache:
            return cache[cache_key]

        print(f"GPU encoder tespit ediliyor... (codec: {codec_family})")

        try:
            result = subprocess.run(
                [ffmpeg_binary, '-hide_banner', '-encoders'],
                capture_output=True,
                text=True,
                check=True
            )
            available_encoders = result.stdout
        except Exception:
            print("FFmpeg encoder listesi alinamadi, CPU encoder kullanilacak")
            fallback_encoder = 'libx265' if codec_family == 'hevc' else 'libx264'
            cache[cache_key] = {
                'encoder': fallback_encoder,
                'name': f"CPU ({fallback_encoder})",
                'preset_support': True,
                'codec_family': codec_family,
            }
            return cache[cache_key]

        import platform

        system = platform.system()
        if system == "Darwin":
            encoders_to_test = [
                ('hevc_videotoolbox', 'Apple VideoToolbox HEVC', False),
                ('libx265', 'CPU (libx265)', True),
                ('libx264', 'CPU (libx264)', True),
            ] if codec_family == 'hevc' else [
                ('h264_videotoolbox', 'Apple VideoToolbox', False),
                ('libx264', 'CPU (libx264)', True),
            ]
        elif system in {"Windows", "Linux"}:
            encoders_to_test = [
                ('hevc_nvenc', 'NVIDIA NVENC HEVC', True),
                ('hevc_amf', 'AMD AMF HEVC', True),
                ('hevc_qsv', 'Intel Quick Sync HEVC', True),
                ('libx265', 'CPU (libx265)', True),
                ('libx264', 'CPU (libx264)', True),
            ] if codec_family == 'hevc' else [
                ('h264_nvenc', 'NVIDIA NVENC', True),
                ('h264_amf', 'AMD AMF', True),
                ('h264_qsv', 'Intel Quick Sync', True),
                ('libx264', 'CPU (libx264)', True),
            ]
        else:
            encoders_to_test = [
                ('libx265', 'CPU (libx265)', True),
                ('libx264', 'CPU (libx264)', True),
            ] if codec_family == 'hevc' else [('libx264', 'CPU (libx264)', True)]

        encoder_test_args = {
            'h264_amf': ['-usage', 'transcoding'],
            'hevc_amf': ['-usage', 'transcoding'],
            'h264_videotoolbox': ['-realtime', 'true'],
            'hevc_videotoolbox': ['-realtime', 'true'],
        }

        for encoder, name, preset_support in encoders_to_test:
            if encoder not in available_encoders:
                continue

            try:
                test_cmd = [
                    ffmpeg_binary,
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-f', 'lavfi',
                    '-i', 'color=c=black:s=320x240:d=1',
                    '-frames:v', '1',
                    '-c:v', encoder,
                ]
                test_cmd.extend(encoder_test_args.get(encoder, []))
                test_cmd.extend(['-f', 'null', '-'])

                result = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    print(f"GPU encoder tespit edildi: {name} ({encoder})")
                    cache[cache_key] = {
                        'encoder': encoder,
                        'name': name,
                        'preset_support': preset_support,
                        'codec_family': codec_family,
                    }
                    return cache[cache_key]
            except Exception:
                continue

        print("GPU encoder bulunamadi, CPU encoder kullanilacak")
        fallback_encoder = 'libx265' if codec_family == 'hevc' and 'libx265' in available_encoders else 'libx264'
        cache[cache_key] = {
            'encoder': fallback_encoder,
            'name': f"CPU ({fallback_encoder})",
            'preset_support': True,
            'codec_family': codec_family,
        }
        return cache[cache_key]

    @staticmethod
    def embed_soft_subtitles(video_path, srt_path, output_path=None, progress_callback=None, font_settings=None, ffmpeg_path=None):
        ffmpeg_binary = resolve_ffmpeg_path(ffmpeg_path)
        if not SubtitleEmbedder.check_ffmpeg(ffmpeg_binary):
            print("ffmpeg bulunamadi!")
            return None

        if output_path is None:
            video_p = Path(video_path)
            output_path = video_p.parent / f"{video_p.stem}_soft_subtitles.mkv"

        if progress_callback:
            progress_callback("status", "Yumusak altyazi ekleniyor...")

        requested_output_path = Path(output_path)
        ffmpeg_output_path = create_ffmpeg_safe_output_path(requested_output_path)

        cmd = [
            ffmpeg_binary,
            '-i', video_path,
            '-i', srt_path,
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-c:s', 'srt',
            '-metadata:s:s:0', 'language=tur',
            '-metadata:s:s:0', 'title=Turkish',
            '-disposition:s:0', 'default',
            str(ffmpeg_output_path),
            '-y',
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            final_output_path = finalize_ffmpeg_output_path(ffmpeg_output_path, requested_output_path)
            if progress_callback:
                progress_callback("status", "Yumusak altyazi eklendi!")
            print(f"Yumusak altyazi eklendi: {final_output_path}")
            return str(final_output_path)
        except subprocess.CalledProcessError as error:
            print(f"Yumusak altyazi ekleme hatasi: {error.stderr.decode()}")
            return None

    @staticmethod
    def get_video_resolution(video_path, ffmpeg_path=None):
        """Get video width and height."""
        try:
            media_info = get_media_stream_info(video_path, resolve_ffprobe_path(resolve_ffmpeg_path(ffmpeg_path)))
            return media_info.get('width'), media_info.get('height')
        except Exception:
            pass
        return None, None

    @staticmethod
    def calculate_adaptive_font_size(base_font_size, video_width, video_height):
        """Adjust font size based on video resolution."""
        if not video_width or not video_height:
            return base_font_size

        reference_width = 1920
        reference_height = 1080
        is_vertical = video_height > video_width

        if is_vertical:
            scale_factor = min(video_width / reference_width, video_height / reference_height)
            adaptive_size = int(base_font_size * scale_factor * 0.55)
            print(f"Dikey video tespit edildi ({video_width}x{video_height})")
        else:
            scale_factor = min(video_width / reference_width, video_height / reference_height)
            adaptive_size = int(base_font_size * scale_factor)

        min_size = 14
        max_size = 72
        original_size = base_font_size

        if adaptive_size < min_size:
            print(f"Uyari: Hesaplanan font boyutu ({adaptive_size}) cok kucuk. Minimum {min_size} kullanilacak.")
            adaptive_size = min_size
        elif adaptive_size > max_size:
            print(f"Uyari: Hesaplanan font boyutu ({adaptive_size}) cok buyuk. Maksimum {max_size} kullanilacak.")
            adaptive_size = max_size
        elif abs(adaptive_size - original_size) > 10:
            video_type = "dikey" if is_vertical else "yatay"
            print(f"Font boyutu ayarlandi: {original_size} -> {adaptive_size} ({video_type} video icin optimize)")

        return adaptive_size

    @staticmethod
    def embed_hard_subtitles(video_path, srt_path, output_path=None, progress_callback=None, font_settings=None, ffmpeg_path=None):
        ffmpeg_binary = resolve_ffmpeg_path(ffmpeg_path)
        if not SubtitleEmbedder.check_ffmpeg(ffmpeg_binary):
            print("ffmpeg bulunamadi!")
            return None

        if output_path is None:
            video_p = Path(video_path)
            output_path = video_p.parent / f"{video_p.stem}_hard_subtitles.mp4"

        if progress_callback:
            progress_callback("status", "Sabit altyazi ekleniyor...")

        requested_output_path = Path(output_path)
        ffmpeg_output_path = create_ffmpeg_safe_output_path(requested_output_path)

        srt_path_escaped = str(Path(srt_path).resolve()).replace('\\', '/').replace(':', '\\:')
        subtitle_filter = f"subtitles='{srt_path_escaped}'"

        if font_settings:
            force_style_parts = []

            if font_settings.use_adaptive_size:
                video_width, video_height = SubtitleEmbedder.get_video_resolution(video_path, ffmpeg_binary)
                final_font_size = SubtitleEmbedder.calculate_adaptive_font_size(
                    font_settings.font_size,
                    video_width,
                    video_height,
                )
                print(f"Otomatik boyut: {font_settings.font_size} -> {final_font_size} (video: {video_width}x{video_height})")
            else:
                final_font_size = font_settings.font_size
                print(f"Sabit boyut kullaniliyor: {final_font_size}")

            if font_settings.font_family:
                force_style_parts.append(f"FontName={font_settings.font_family}")

            if final_font_size:
                force_style_parts.append(f"FontSize={final_font_size}")

            if font_settings.font_color:
                color_hex = font_settings.font_color.lstrip('#')
                if len(color_hex) == 6:
                    red, green, blue = color_hex[0:2], color_hex[2:4], color_hex[4:6]
                    bgr_color = f"{blue}{green}{red}"
                    force_style_parts.append(f"PrimaryColour=&H00{bgr_color}")

            if font_settings.outline_color:
                outline_hex = font_settings.outline_color.lstrip('#')
                if len(outline_hex) == 6:
                    red, green, blue = outline_hex[0:2], outline_hex[2:4], outline_hex[4:6]
                    bgr_outline = f"{blue}{green}{red}"
                    force_style_parts.append(f"OutlineColour=&H00{bgr_outline}")

            if font_settings.outline_width:
                force_style_parts.append(f"Outline={font_settings.outline_width}")

            force_style_parts.append("Bold=1" if font_settings.bold else "Bold=0")
            force_style_parts.append("Italic=1" if font_settings.italic else "Italic=0")

            if force_style_parts:
                force_style_str = ",".join(force_style_parts)
                subtitle_filter += f":force_style='{force_style_str}'"

        gpu_info = SubtitleEmbedder.detect_gpu_encoder(ffmpeg_binary)
        encoder = gpu_info['encoder']
        encoder_name = gpu_info['name']

        cmd = [ffmpeg_binary, '-hwaccel', 'auto', '-i', video_path, '-vf', subtitle_filter, '-c:v', encoder]

        if encoder == 'h264_nvenc':
            cmd.extend([
                '-preset', 'p1',
                '-rc', 'constqp',
                '-qp', '28',
                '-b:v', '0',
            ])
        elif encoder == 'h264_amf':
            cmd.extend([
                '-usage', 'lowlatency',
                '-quality', 'speed',
                '-rc', 'cqp',
                '-qp_i', '26',
                '-qp_p', '26',
            ])
        elif encoder == 'h264_qsv':
            cmd.extend([
                '-preset', 'veryfast',
                '-global_quality', '25',
            ])
        elif encoder == 'h264_videotoolbox':
            cmd.extend([
                '-realtime', 'true',
                '-b:v', '5M',
                '-allow_sw', '1',
            ])
        else:
            cmd.extend([
                '-preset', 'ultrafast',
                '-crf', '26',
            ])

        cmd.extend([
            '-c:a', 'copy',
            '-movflags', '+faststart',
            str(ffmpeg_output_path),
            '-y',
        ])

        print(f"Video isleniyor ({encoder_name})...")

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            final_output_path = finalize_ffmpeg_output_path(ffmpeg_output_path, requested_output_path)
            if progress_callback:
                progress_callback("status", "Sabit altyazi eklendi!")
            print(f"Sabit altyazi eklendi: {final_output_path}")
            return str(final_output_path)
        except subprocess.CalledProcessError as error:
            try:
                err = error.stderr.decode() if hasattr(error, 'stderr') and error.stderr else str(error)
            except Exception:
                err = str(error)
            print(f"Sabit altyazi ekleme hatasi: {err}")
            return None
