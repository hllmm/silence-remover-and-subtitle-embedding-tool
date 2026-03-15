"""Core media probing, silence detection, and fast trim helpers."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from bisect import bisect_left, bisect_right
from functools import lru_cache
from pathlib import Path

AUDIO_ONLY_EXTENSIONS = {'.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg'}
FAST_AUDIO_COPY_PROFILES = (
    {
        'name': 'mp3',
        'extensions': {'.mp3'},
        'codecs': {'mp3'},
        'segment_extension': '.mp3',
        'max_segments': 60,
        'min_segment_duration': 0.35,
        'extract_flags': ['-write_xing', '0'],
        'concat_flags': ['-write_xing', '0'],
    },
    {
        'name': 'aac',
        'extensions': {'.aac', '.m4a'},
        'codecs': {'aac'},
        'segment_extension': '.aac',
        'max_segments': 72,
        'min_segment_duration': 0.20,
        'extract_flags': ['-f', 'adts'],
        'concat_flags': [],
        'output_flags_map': {
            '.aac': [],
            '.m4a': ['-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart'],
            '.mp4': ['-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart'],
            '.mov': ['-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart'],
        },
        'requires_codec_match': True,
    },
    {
        'name': 'flac',
        'extensions': {'.flac'},
        'codecs': {'flac'},
        'segment_extension': '.flac',
        'max_segments': 80,
        'min_segment_duration': 0.15,
        'extract_flags': [],
        'concat_flags': [],
    },
    {
        'name': 'wav',
        'extensions': {'.wav'},
        'codecs': {
            'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_f32le',
            'pcm_f64le', 'pcm_u8', 'pcm_alaw', 'pcm_mulaw'
        },
        'segment_extension': '.wav',
        'max_segments': 100,
        'min_segment_duration': 0.10,
        'extract_flags': [],
        'concat_flags': [],
    },
)
FAST_AUDIO_COPY_GAP_THRESHOLDS = (0.25, 0.4, 0.6, 0.85, 1.10, 1.45)
FAST_VIDEO_COPY_KEYFRAME_TOLERANCE = 0.20
FAST_VIDEO_COPY_MAX_SEGMENTS = 90
FAST_VIDEO_COPY_VIDEO_CODECS = {'h264', 'hevc'}
FAST_VIDEO_COPY_AUDIO_CODECS = {'', 'aac', 'mp3', 'ac3', 'eac3'}
VIDEO_TRIM_ENCODING_PROFILES = {
    'Hız': {
        'key': 'speed',
        'batch_size_large': 60,
        'batch_size_small': 84,
    },
    'Dengeli': {
        'key': 'balanced',
        'batch_size_large': 48,
        'batch_size_small': 72,
    },
    'Kalite': {
        'key': 'quality',
        'batch_size_large': 36,
        'batch_size_small': 60,
    },
}


def _get_step_precision(step):
    step_text = f"{float(step):.10f}".rstrip('0').rstrip('.')
    if '.' not in step_text:
        return 0
    return len(step_text.split('.', 1)[1])


def snap_numeric_value(value, step, minimum=None, maximum=None):
    numeric_value = float(value)
    minimum_value = float(minimum) if minimum is not None else None
    maximum_value = float(maximum) if maximum is not None else None

    if minimum_value is not None:
        numeric_value = max(numeric_value, minimum_value)
    if maximum_value is not None:
        numeric_value = min(numeric_value, maximum_value)

    step_value = float(step)
    if step_value > 0:
        base_value = minimum_value if minimum_value is not None else 0.0
        numeric_value = base_value + round((numeric_value - base_value) / step_value) * step_value
        if minimum_value is not None:
            numeric_value = max(numeric_value, minimum_value)
        if maximum_value is not None:
            numeric_value = min(numeric_value, maximum_value)
        numeric_value = round(numeric_value, _get_step_precision(step_value))

    return numeric_value


MOV_FAMILY_ALIAS_SUFFIXES = {'.mp4', '.m4a', '.3gp', '.3g2', '.mj2'}
DEFAULT_AUDIO_CLEANUP_PROFILE = 'safe'
AUDIO_CLEANUP_PROFILES = {
    'safe': {
        'name': 'Guvenli',
        'filters': (
            'highpass=f=70',
            'afftdn=nr=10:nf=-34:tn=1',
        ),
    },
    'balanced': {
        'name': 'Dengeli',
        'filters': (
            'highpass=f=65',
            'lowpass=f=12000',
            'afftdn=nr=12:nf=-32:tn=1',
        ),
    },
    'strong': {
        'name': 'Guclu',
        'filters': (
            'highpass=f=75',
            'lowpass=f=10000',
            'afftdn=nr=16:nf=-30:tn=1',
            'adeclick=w=20:o=2:a=1',
        ),
    },
}


def _normalize_audio_filter_chain(audio_filters):
    if not audio_filters:
        return ''

    if isinstance(audio_filters, str):
        return audio_filters.strip().strip(',')

    parts = []
    for item in audio_filters:
        item_text = str(item or '').strip().strip(',')
        if item_text:
            parts.append(item_text)
    return ",".join(parts)


def get_audio_cleanup_filter_chain(profile=DEFAULT_AUDIO_CLEANUP_PROFILE):
    profile_key = str(profile or '').strip().lower()
    if not profile_key or profile_key in {'off', 'none', 'kapali', 'disabled', 'false'}:
        return ''

    profile_data = AUDIO_CLEANUP_PROFILES.get(profile_key)
    if profile_data is None:
        profile_data = AUDIO_CLEANUP_PROFILES[DEFAULT_AUDIO_CLEANUP_PROFILE]
    return ",".join(profile_data['filters'])


def create_ffmpeg_safe_output_path(output_path, temp_dir_name='subtitle_ascii_outputs'):
    output_path = Path(output_path)
    output_path_str = str(output_path)
    requested_suffix = output_path.suffix.lower()

    requires_temp_output = (
        os.name == 'nt' and
        (not output_path_str.isascii() or requested_suffix in MOV_FAMILY_ALIAS_SUFFIXES)
    )
    if not requires_temp_output:
        return output_path

    safe_root = Path(tempfile.gettempdir()) / temp_dir_name
    safe_root.mkdir(parents=True, exist_ok=True)

    safe_stem = re.sub(r'[^A-Za-z0-9._-]+', '_', output_path.stem).strip('._')
    if not safe_stem:
        safe_stem = 'output'
    safe_stem = safe_stem[:48]

    safe_suffix = output_path.suffix or '.tmp'
    if safe_suffix.lower() in MOV_FAMILY_ALIAS_SUFFIXES:
        safe_suffix = '.mov'
    safe_name = f"{safe_stem}_{uuid.uuid4().hex[:10]}{safe_suffix}"
    return safe_root / safe_name


def finalize_ffmpeg_output_path(actual_output_path, requested_output_path):
    actual_output_path = Path(actual_output_path)
    requested_output_path = Path(requested_output_path)

    try:
        same_path = actual_output_path.resolve() == requested_output_path.resolve()
    except OSError:
        same_path = False

    if same_path:
        return requested_output_path

    requested_output_path.parent.mkdir(parents=True, exist_ok=True)
    if requested_output_path.exists():
        requested_output_path.unlink()

    shutil.move(str(actual_output_path), str(requested_output_path))
    return requested_output_path


def _resolve_existing_tool_path(candidate):
    try:
        candidate_path = Path(candidate)
    except Exception:
        return None

    try:
        if candidate_path.exists():
            return str(candidate_path.resolve())
    except OSError:
        return None

    return None


def resolve_ffmpeg_path(ffmpeg_path=None):
    if ffmpeg_path:
        resolved_explicit = _resolve_existing_tool_path(ffmpeg_path)
        if resolved_explicit:
            return resolved_explicit
        ffmpeg_name = Path(str(ffmpeg_path)).name.lower()
        if ffmpeg_name not in {'ffmpeg', 'ffmpeg.exe'}:
            return str(ffmpeg_path)

    app_root = Path(__file__).resolve().parents[1]
    candidate_paths = (
        app_root / 'ffmpeg-custom' / 'balanced' / 'ffmpeg.exe',
        app_root / 'ffmpeg-custom' / 'aggressive' / 'ffmpeg.exe',
        app_root / 'ffmpeg.exe',
        Path('ffmpeg.exe'),
    )
    for candidate in candidate_paths:
        resolved_candidate = _resolve_existing_tool_path(candidate)
        if resolved_candidate:
            return resolved_candidate

    return 'ffmpeg'


def resolve_ffprobe_path(ffmpeg_path=None):
    ffmpeg_path = str(ffmpeg_path) if ffmpeg_path else resolve_ffmpeg_path()

    if ffmpeg_path:
        ffmpeg_name = Path(ffmpeg_path).name.lower()
        if ffmpeg_name == 'ffmpeg.exe':
            sibling = _resolve_existing_tool_path(Path(ffmpeg_path).with_name('ffprobe.exe'))
            if sibling:
                return sibling
        if ffmpeg_name == 'ffmpeg':
            sibling = _resolve_existing_tool_path(Path(ffmpeg_path).with_name('ffprobe'))
            if sibling:
                return sibling
        if 'ffmpeg.exe' in ffmpeg_path.lower():
            sibling = _resolve_existing_tool_path(ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe'))
            if sibling:
                return sibling
        if ffmpeg_path != 'ffmpeg' and 'ffmpeg' in ffmpeg_path.lower():
            sibling = _resolve_existing_tool_path(ffmpeg_path.replace('ffmpeg', 'ffprobe'))
            if sibling:
                return sibling

    app_root = Path(__file__).resolve().parents[1]
    candidate_paths = (
        app_root / 'ffmpeg-custom' / 'balanced' / 'ffprobe.exe',
        app_root / 'ffmpeg-custom' / 'aggressive' / 'ffprobe.exe',
        app_root / 'ffprobe.exe',
        Path('ffprobe.exe'),
    )
    for candidate in candidate_paths:
        resolved_candidate = _resolve_existing_tool_path(candidate)
        if resolved_candidate:
            return resolved_candidate

    return 'ffprobe'


def _parse_media_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _parse_media_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _build_media_cache_key(media_path):
    resolved_path = Path(media_path).resolve()
    file_stat = resolved_path.stat()
    return str(resolved_path), file_stat.st_mtime_ns, file_stat.st_size


def _parse_media_stream_info(data):
    video_stream = None
    audio_stream = None

    for stream in data.get('streams', []):
        codec_type = stream.get('codec_type')
        if codec_type == 'video' and video_stream is None:
            video_stream = stream
        elif codec_type == 'audio' and audio_stream is None:
            audio_stream = stream

    format_info = data.get('format', {})
    return {
        'format_name': format_info.get('format_name'),
        'format_bit_rate': _parse_media_int(format_info.get('bit_rate')),
        'duration': _parse_media_float(format_info.get('duration')),
        'video_codec': (video_stream or {}).get('codec_name'),
        'video_bit_rate': _parse_media_int((video_stream or {}).get('bit_rate')),
        'width': _parse_media_int((video_stream or {}).get('width')),
        'height': _parse_media_int((video_stream or {}).get('height')),
        'audio_codec': (audio_stream or {}).get('codec_name'),
        'audio_bit_rate': _parse_media_int((audio_stream or {}).get('bit_rate')),
    }


@lru_cache(maxsize=256)
def _probe_media_stream_info_cached(media_path, ffprobe_path, modified_ns, file_size):
    try:
        cmd = [
            str(ffprobe_path),
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(media_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout or "{}")
    except Exception:
        return {}

    return _parse_media_stream_info(data)


def get_media_stream_info(media_path, ffprobe_path):
    try:
        cache_key = _build_media_cache_key(media_path)
    except OSError:
        return {}

    return dict(
        _probe_media_stream_info_cached(
            cache_key[0],
            str(ffprobe_path),
            cache_key[1],
            cache_key[2]
        )
    )


def get_media_duration(media_path, ffprobe_path):
    return get_media_stream_info(media_path, ffprobe_path).get('duration')


def _normalize_codec_name(codec_name):
    codec_name = str(codec_name or '').strip().lower()
    return 'hevc' if codec_name == 'h265' else codec_name


def _parse_format_names(format_name):
    return {
        part.strip().lower()
        for part in str(format_name or '').split(',')
        if part.strip()
    }


def get_fast_audio_concat_flags(profile, output_path):
    output_suffix = Path(output_path).suffix.lower()
    output_flags_map = profile.get('output_flags_map') or {}
    return list(output_flags_map.get(output_suffix, profile.get('concat_flags', [])))


def optimize_intervals_for_fast_audio_copy(input_path, media_info, keep_intervals):
    profile = get_fast_audio_copy_profile(input_path, media_info)
    if not profile or not keep_intervals:
        return list(keep_intervals), profile

    optimized_intervals = list(keep_intervals)
    if should_use_fast_audio_concat(input_path, media_info, optimized_intervals):
        return optimized_intervals, profile

    condensed = condense_keep_intervals(
        optimized_intervals,
        target_max_segments=profile['max_segments'],
        gap_thresholds=FAST_AUDIO_COPY_GAP_THRESHOLDS,
        short_clip_threshold=1.25
    )
    if should_use_fast_audio_concat(input_path, media_info, condensed):
        return condensed, profile

    return optimized_intervals, profile


@lru_cache(maxsize=64)
def _probe_video_keyframes_cached(media_path, ffprobe_path, modified_ns, file_size):
    try:
        cmd = [
            str(ffprobe_path),
            '-v', 'error',
            '-skip_frame', 'nokey',
            '-select_streams', 'v:0',
            '-show_frames',
            '-show_entries', 'frame=best_effort_timestamp_time',
            '-of', 'json',
            str(media_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout or "{}")
    except Exception:
        return ()

    keyframes = []
    for frame in data.get('frames', []):
        timestamp = _parse_media_float(frame.get('best_effort_timestamp_time'))
        if timestamp is not None:
            keyframes.append(timestamp)

    return tuple(sorted(set(keyframes)))


def get_video_keyframe_times(video_path, ffprobe_path, total_duration=None):
    try:
        cache_key = _build_media_cache_key(video_path)
    except OSError:
        return []

    keyframes = list(
        _probe_video_keyframes_cached(
            cache_key[0],
            str(ffprobe_path),
            cache_key[1],
            cache_key[2]
        )
    )

    if not keyframes or abs(keyframes[0]) > 0.001:
        keyframes.insert(0, 0.0)

    if total_duration and (not keyframes or abs(keyframes[-1] - total_duration) > 0.001):
        keyframes.append(total_duration)

    return keyframes


def _find_previous_keyframe(keyframes, timestamp):
    if not keyframes:
        return None
    index = bisect_right(keyframes, timestamp + 0.0005) - 1
    if index < 0:
        return None
    return keyframes[index]


def _find_next_keyframe(keyframes, timestamp):
    if not keyframes:
        return None
    index = bisect_left(keyframes, timestamp - 0.0005)
    if index >= len(keyframes):
        return None
    return keyframes[index]


def build_fast_video_copy_plan(video_path, ffprobe_path, media_info, keep_intervals, total_duration,
                               keyframe_tolerance=FAST_VIDEO_COPY_KEYFRAME_TOLERANCE):
    if not keep_intervals or not total_duration:
        return None

    if len(keep_intervals) > FAST_VIDEO_COPY_MAX_SEGMENTS:
        return None

    input_suffix = Path(video_path).suffix.lower()
    if input_suffix not in {'.mp4', '.mov', '.mkv'}:
        return None

    video_codec = _normalize_codec_name((media_info or {}).get('video_codec'))
    audio_codec = _normalize_codec_name((media_info or {}).get('audio_codec'))

    if video_codec not in FAST_VIDEO_COPY_VIDEO_CODECS:
        return None

    if audio_codec not in FAST_VIDEO_COPY_AUDIO_CODECS:
        return None

    keyframes = get_video_keyframe_times(video_path, ffprobe_path, total_duration=total_duration)
    if len(keyframes) <= 1:
        return None

    planned_intervals = []
    max_boundary_error = 0.0

    for start, end in keep_intervals:
        snapped_start = _find_previous_keyframe(keyframes, start)
        snapped_end = _find_next_keyframe(keyframes, end)

        if snapped_start is None or snapped_end is None:
            return None

        start_slack = max(0.0, start - snapped_start)
        end_slack = max(0.0, snapped_end - end)
        max_boundary_error = max(max_boundary_error, start_slack, end_slack)

        if start_slack > keyframe_tolerance or end_slack > keyframe_tolerance:
            return None

        if snapped_end - snapped_start < 0.05:
            return None

        planned_intervals.append((snapped_start, snapped_end))

    planned_intervals = merge_close_intervals(planned_intervals, gap_threshold=0.001)
    removed_duration = total_duration - sum(end - start for start, end in planned_intervals)
    if removed_duration < 0.1:
        return None

    return {
        'intervals': planned_intervals,
        'video_codec': video_codec,
        'audio_codec': audio_codec,
        'removed_duration': removed_duration,
        'max_boundary_error': max_boundary_error,
        'keyframe_count': len(keyframes),
    }


def fast_trim_video_with_stream_copy(ffmpeg_path, input_path, copy_plan, output_path, progress_callback=None):
    if not copy_plan or not copy_plan.get('intervals'):
        raise RuntimeError("Hızlı video kopya planı bulunamadı")

    audio_codec = copy_plan['audio_codec']

    with tempfile.TemporaryDirectory(prefix="subtitle_video_fastcopy_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        total_segments = len(copy_plan['intervals'])
        concat_file = temp_dir / "concat_list.ffconcat"
        normalized_input = str(Path(input_path).resolve()).replace('\\', '/').replace("'", "'\\''")
        concat_lines = ['ffconcat version 1.0']

        for index, (start, end) in enumerate(copy_plan['intervals'], start=1):
            concat_lines.append(f"file '{normalized_input}'")
            concat_lines.append(f"inpoint {start:.6f}")
            concat_lines.append(f"outpoint {end:.6f}")
            if progress_callback:
                progress_callback(index, total_segments)

        concat_file.write_text("\n".join(concat_lines) + "\n", encoding='utf-8')

        concat_cmd = [
            str(ffmpeg_path),
            '-hide_banner',
            '-loglevel', 'error',
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-fflags', '+genpts',
            '-avoid_negative_ts', 'make_zero',
            '-c', 'copy',
        ]

        output_suffix = Path(output_path).suffix.lower()
        if output_suffix in {'.mp4', '.mov'} and audio_codec == 'aac':
            concat_cmd.extend(['-bsf:a', 'aac_adtstoasc'])
        if output_suffix in {'.mp4', '.mov'}:
            concat_cmd.extend(['-movflags', '+faststart'])

        concat_cmd.append(str(output_path))
        result = subprocess.run(concat_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or
                "Video kopya parçaları birleştirilemedi"
            )


def parse_silence_intervals(silence_log, total_duration=None):
    intervals = []
    silence_start = None

    for line in silence_log.splitlines():
        if 'silence_start:' in line:
            try:
                silence_start = float(line.split('silence_start:')[1].strip().split()[0])
            except Exception:
                silence_start = None
        elif 'silence_end:' in line and silence_start is not None:
            try:
                silence_end = float(line.split('silence_end:')[1].strip().split()[0].split('|')[0])
                intervals.append((silence_start, silence_end))
            except Exception:
                pass
            finally:
                silence_start = None

    if silence_start is not None and total_duration is not None and silence_start < total_duration:
        intervals.append((silence_start, total_duration))

    return intervals


def detect_silence_intervals(ffmpeg_path, input_path, threshold_db, min_duration, total_duration=None, audio_filters=None):
    filter_chain = _normalize_audio_filter_chain(audio_filters)
    silence_filter = f'silencedetect=noise={threshold_db}dB:d={min_duration}'
    if filter_chain:
        silence_filter = f'{filter_chain},{silence_filter}'

    cmd = [
        str(ffmpeg_path),
        '-hide_banner',
        '-i', str(input_path),
        '-vn', '-sn', '-dn',
        '-ac', '1',
        '-ar', '16000',
        '-af', silence_filter,
        '-f', 'null',
        '-'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0 and 'silence_' not in (result.stderr or ''):
        raise RuntimeError(result.stderr.strip() or "Sessizlik tespiti başarısız oldu")

    return parse_silence_intervals(result.stderr or "", total_duration=total_duration)


def calculate_auto_speech_protection(threshold_db, min_duration):
    threshold_value = float(threshold_db)
    min_duration_value = max(float(min_duration), 0.05)

    threshold_aggressiveness = min(max((threshold_value + 42.0) / 18.0, 0.0), 1.0)
    short_silence_penalty = min(max((0.35 - min_duration_value) / 0.25, 0.0), 1.0)
    long_silence_relief = min(max((min_duration_value - 0.85) / 0.75, 0.0), 1.0)

    recommended_protection = (
        0.30
        + (threshold_aggressiveness * 0.18)
        - (short_silence_penalty * 0.04)
        - (long_silence_relief * 0.06)
    )
    return snap_numeric_value(recommended_protection, 0.05, minimum=0.20, maximum=0.70)


def calculate_speech_protection_profile(threshold_db, min_duration, protection_level=0.35):
    threshold_value = float(threshold_db)
    min_duration_value = max(float(min_duration), 0.05)
    if protection_level is None:
        base_protection = calculate_auto_speech_protection(threshold_value, min_duration_value)
    else:
        base_protection = snap_numeric_value(protection_level, 0.05, minimum=0.0, maximum=1.0)

    threshold_aggressiveness = min(max((threshold_value + 40.0) / 15.0, 0.0), 1.0)
    short_silence_penalty = min(max((0.35 - min_duration_value) / 0.25, 0.0), 1.0)
    edge_boost = max(0.0, (threshold_aggressiveness * 0.18) - (short_silence_penalty * 0.05))

    padding_after_speech = snap_numeric_value(
        (base_protection * 0.7) + edge_boost,
        0.05,
        minimum=0.12,
        maximum=0.95,
    )
    padding_before_speech = snap_numeric_value(
        base_protection + 0.15 + edge_boost,
        0.05,
        minimum=0.20,
        maximum=1.25,
    )
    keep_silence = snap_numeric_value(
        (base_protection * 0.6) + (edge_boost * 0.5),
        0.05,
        minimum=0.10,
        maximum=0.60,
    )

    return {
        'speech_protection': base_protection,
        'padding_after_speech': padding_after_speech,
        'padding_before_speech': padding_before_speech,
        'keep_silence': keep_silence,
    }


def merge_close_intervals(intervals, gap_threshold=0.2):
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda item: item[0])
    merged = [ordered[0]]

    for start, end in ordered[1:]:
        current_start, current_end = merged[-1]
        if start - current_end < gap_threshold:
            merged[-1] = (current_start, max(current_end, end))
        else:
            merged.append((start, end))

    return merged


def apply_padding_to_silence_intervals(intervals, total_duration, padding_after_speech=0.25, padding_before_speech=0.5):
    padded = []

    for start, end in intervals:
        if start <= 0.0001:
            adjusted_start = min(0.5, total_duration)
        else:
            adjusted_start = min(max(start + padding_after_speech, 0.0), total_duration)

        adjusted_end = end if end >= total_duration else max(0.0, end - padding_before_speech)
        adjusted_end = min(adjusted_end, total_duration)

        if adjusted_start < adjusted_end:
            padded.append((adjusted_start, adjusted_end))

    return padded


def invert_intervals(cut_intervals, total_duration, min_clip_duration=0.1):
    if total_duration is None:
        return []

    keep_intervals = []
    last_end = 0.0

    for start, end in sorted(cut_intervals, key=lambda item: item[0]):
        start = max(0.0, min(start, total_duration))
        end = max(start, min(end, total_duration))

        if start > last_end:
            duration = start - last_end
            if duration >= min_clip_duration:
                keep_intervals.append((last_end, start))

        last_end = max(last_end, end)

    if total_duration > last_end:
        duration = total_duration - last_end
        if duration >= min_clip_duration:
            keep_intervals.append((last_end, total_duration))

    return keep_intervals


def condense_keep_intervals(
    keep_intervals,
    target_max_segments=120,
    gap_thresholds=(0.25, 0.4, 0.6, 0.85),
    short_clip_threshold=1.0
):
    if len(keep_intervals) <= 1:
        return keep_intervals

    condensed = sorted(keep_intervals, key=lambda item: item[0])

    for gap_threshold in gap_thresholds:
        merged = [condensed[0]]

        for start, end in condensed[1:]:
            prev_start, prev_end = merged[-1]
            gap = start - prev_end
            prev_duration = prev_end - prev_start
            current_duration = end - start

            should_merge = gap <= gap_threshold
            if not should_merge and gap <= gap_threshold * 1.5:
                should_merge = (
                    prev_duration <= short_clip_threshold or
                    current_duration <= short_clip_threshold
                )

            if should_merge:
                merged[-1] = (prev_start, end)
            else:
                merged.append((start, end))

        condensed = merged
        if len(condensed) <= target_max_segments:
            break

    return condensed


def split_intervals_into_batches(intervals, batch_size):
    if batch_size <= 0:
        return [intervals]
    return [intervals[index:index + batch_size] for index in range(0, len(intervals), batch_size)]


def write_ffmpeg_concat_list(file_paths, concat_file_path):
    with open(concat_file_path, 'w', encoding='utf-8') as concat_file:
        for file_path in file_paths:
            normalized_path = str(Path(file_path).resolve()).replace('\\', '/').replace("'", "'\\''")
            concat_file.write(f"file '{normalized_path}'\n")


def get_fast_audio_copy_profile(input_path, media_info):
    suffix = Path(input_path).suffix.lower()
    audio_codec = _normalize_codec_name((media_info or {}).get('audio_codec'))
    format_names = _parse_format_names((media_info or {}).get('format_name'))

    for profile in FAST_AUDIO_COPY_PROFILES:
        extension_match = suffix in profile['extensions']
        codec_match = audio_codec in profile['codecs']
        required_formats = profile.get('format_names')
        format_match = not required_formats or bool(format_names & required_formats)

        if profile.get('requires_codec_match'):
            if (extension_match or codec_match) and codec_match and format_match:
                return profile
            continue

        if (extension_match or codec_match) and format_match:
            return profile

    return None


def should_use_fast_audio_concat(input_path, media_info, keep_intervals):
    profile = get_fast_audio_copy_profile(input_path, media_info)
    if not profile:
        return False

    if not keep_intervals or len(keep_intervals) > profile['max_segments']:
        return False

    min_segment_duration = profile['min_segment_duration']
    return all((end - start) >= min_segment_duration for start, end in keep_intervals)


def fast_trim_audio_with_stream_copy(ffmpeg_path, input_path, keep_intervals, output_path, media_info, progress_callback=None):
    profile = get_fast_audio_copy_profile(input_path, media_info)
    if not profile:
        raise RuntimeError("Bu ses formatı için hızlı kopyalama desteklenmiyor")

    created_segments = []

    with tempfile.TemporaryDirectory(prefix="subtitle_audio_fasttrim_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        total_segments = len(keep_intervals)

        for index, (start, end) in enumerate(keep_intervals, start=1):
            duration = max(0.0, end - start)
            if duration < 0.05:
                continue

            segment_path = temp_dir / f"segment_{index:03d}{profile['segment_extension']}"
            cmd = [
                str(ffmpeg_path),
                '-hide_banner',
                '-loglevel', 'error',
                '-y',
                '-ss', f"{start:.6f}",
                '-t', f"{duration:.6f}",
                '-i', str(input_path),
                '-map', '0:a:0',
                '-vn', '-sn', '-dn',
                '-c:a', 'copy',
                '-map_metadata', '-1',
            ]
            cmd.extend(profile['extract_flags'])
            cmd.append(str(segment_path))
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    result.stderr.strip() or
                    f"{profile['name'].upper()} parçası oluşturulamadı ({index}/{total_segments})"
                )
            if not segment_path.exists() or segment_path.stat().st_size <= 0:
                raise RuntimeError(
                    f"{profile['name'].upper()} parçası boş üretildi ({index}/{total_segments})"
                )

            created_segments.append(segment_path)
            if progress_callback:
                progress_callback(index, total_segments)

        if not created_segments:
            raise RuntimeError("Hiç ses parçası oluşturulamadı")

        concat_file = temp_dir / "concat_list.txt"
        write_ffmpeg_concat_list(created_segments, concat_file)

        concat_cmd = [
            str(ffmpeg_path),
            '-hide_banner',
            '-loglevel', 'error',
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',
            '-map_metadata', '-1',
        ]
        concat_cmd.extend(get_fast_audio_concat_flags(profile, output_path))
        concat_cmd.append(str(output_path))
        result = subprocess.run(concat_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or
                f"{profile['name'].upper()} parçaları birleştirilemedi"
            )


def build_audio_filter_graph(intervals, add_fades=False, audio_post_filters=None):
    filter_parts = []
    input_labels = []
    post_filter_chain = _normalize_audio_filter_chain(audio_post_filters)

    for index, (start, end) in enumerate(intervals):
        duration = max(0.0, end - start)
        fade_duration = min(0.01, duration / 2.1) if add_fades else 0.0
        fade_out_start = max(duration - fade_duration, 0.0)

        chain = f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS"
        if add_fades and fade_duration > 0:
            chain += (
                f",afade=t=in:ss=0:d={fade_duration:.6f}"
                f",afade=t=out:st={fade_out_start:.6f}:d={fade_duration:.6f}"
            )
        chain += f"[a{index}]"
        filter_parts.append(chain)
        input_labels.append(f"[a{index}]")

    if len(input_labels) == 1:
        if not post_filter_chain:
            return ";".join(filter_parts), input_labels[0]

        filter_parts.append(f"{input_labels[0]}{post_filter_chain}[aout]")
        return ";".join(filter_parts), "[aout]"

    concat_output_label = "[aout]"
    if post_filter_chain:
        concat_output_label = "[aout_raw]"

    filter_parts.append(f"{''.join(input_labels)}concat=n={len(input_labels)}:v=0:a=1{concat_output_label}")
    if post_filter_chain:
        filter_parts.append(f"{concat_output_label}{post_filter_chain}[aout]")
    return ";".join(filter_parts), "[aout]"


def build_av_filter_graph(intervals, include_video=True, audio_post_filters=None):
    filter_parts = []
    concat_inputs = []
    post_filter_chain = _normalize_audio_filter_chain(audio_post_filters)

    for index, (start, end) in enumerate(intervals):
        duration = max(0.0, end - start)
        fade_duration = min(0.01, duration / 2.1)
        fade_out_start = max(duration - fade_duration, 0.0)

        if include_video:
            filter_parts.append(
                f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{index}]"
            )
            concat_inputs.append(f"[v{index}]")

        filter_parts.append(
            f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:ss=0:d={fade_duration:.6f},"
            f"afade=t=out:st={fade_out_start:.6f}:d={fade_duration:.6f}[a{index}]"
        )
        concat_inputs.append(f"[a{index}]")

    if include_video:
        audio_output_label = "[aout]"
        if post_filter_chain:
            audio_output_label = "[aout_raw]"
        filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(intervals)}:v=1:a=1[vout]{audio_output_label}")
        if post_filter_chain:
            filter_parts.append(f"{audio_output_label}{post_filter_chain}[aout]")
        return ";".join(filter_parts), ['-map', '[vout]', '-map', '[aout]']

    audio_output_label = "[aout]"
    if post_filter_chain:
        audio_output_label = "[aout_raw]"
    filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(intervals)}:v=0:a=1{audio_output_label}")
    if post_filter_chain:
        filter_parts.append(f"{audio_output_label}{post_filter_chain}[aout]")
    return ";".join(filter_parts), ['-map', '[aout]']


def remap_concatenated_time(timestamp, time_map):
    if not time_map:
        return timestamp

    for item in time_map:
        if timestamp <= item['chunk_end'] + 0.001:
            local_offset = max(0.0, min(timestamp - item['chunk_start'], item['source_end'] - item['source_start']))
            return item['source_start'] + local_offset

    last_item = time_map[-1]
    return last_item['source_end']
