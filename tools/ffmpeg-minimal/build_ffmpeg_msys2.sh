#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${PROFILE:-balanced}"
FFMPEG_REF="${FFMPEG_REF:-release/7.1}"
WORK_DIR="${WORK_DIR:-$SCRIPT_DIR/work}"
SRC_DIR="${SRC_DIR:-$WORK_DIR/src/ffmpeg}"
BUILD_DIR="${BUILD_DIR:-$WORK_DIR/build/$PROFILE}"
PREFIX_DIR="${PREFIX_DIR:-$WORK_DIR/prefix/$PROFILE}"
OUTPUT_DIR="${OUTPUT_DIR:-$WORK_DIR/output/$PROFILE}"
ENABLE_NVENC="${ENABLE_NVENC:-1}"
ENABLE_AMF="${ENABLE_AMF:-1}"
ENABLE_QSV="${ENABLE_QSV:-1}"
ENABLE_X265="${ENABLE_X265:-1}"
INSTALL_DEPS="${INSTALL_DEPS:-0}"
CLEAN="${CLEAN:-0}"

if [[ "${MSYSTEM:-}" != "UCRT64" ]]; then
    echo "Bu script MSYS2 UCRT64 ortaminda calistirilmalidir."
    echo "PowerShell sarmalayici zaten C:\\msys64\\usr\\bin\\bash.exe ile cagri yapiyor."
    exit 1
fi

export PATH="/ucrt64/bin:/usr/bin:$PATH"

declare -a protocols demuxers muxers bsfs filters indevs encoders decoders parsers
declare -a configure_flags dependency_packages license_names
declare -a extra_decoders extra_parsers

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Gerekli komut bulunamadi: $1"
        exit 1
    }
}

append_unique() {
    local array_name="$1"
    local value
    shift
    for value in "$@"; do
        eval "case \" \${${array_name}[*]} \" in *\" ${value} \"*) ;; *) ${array_name}+=(\"${value}\") ;; esac"
    done
}

enable_component_list() {
    local kind="$1"
    shift
    local item
    for item in "$@"; do
        configure_flags+=("--enable-${kind}=${item}")
    done
}

copy_runtime_deps() {
    local binary_path="$1"
    local dep_path

    while read -r dep_path; do
        [[ -n "$dep_path" ]] || continue
        case "$dep_path" in
            /ucrt64/bin/*)
                cp -f "$dep_path" "$OUTPUT_DIR/"
                ;;
        esac
    done < <(ldd "$binary_path" | awk '/=>/ { print $3 }')
}

copy_license_dir() {
    local name="$1"
    local source_dir="/ucrt64/share/licenses/$name"
    local target_dir="$OUTPUT_DIR/licenses/$name"

    if [[ -d "$source_dir" ]]; then
        mkdir -p "$target_dir"
        cp -R "$source_dir"/. "$target_dir/"
    fi
}

write_component_report() {
    cat >"$OUTPUT_DIR/profile-components.txt" <<EOF
profile=$PROFILE
ffmpeg_ref=$FFMPEG_REF
enable_nvenc=$ENABLE_NVENC
enable_amf=$ENABLE_AMF
enable_qsv=$ENABLE_QSV
enable_x265=$ENABLE_X265

protocols=${protocols[*]}
demuxers=${demuxers[*]}
muxers=${muxers[*]}
bsfs=${bsfs[*]}
filters=${filters[*]}
indevs=${indevs[*]}
encoders=${encoders[*]}
decoders=${decoders[*]}
parsers=${parsers[*]}
EOF
}

install_dependencies() {
    local packages=(
        git
        make
        diffutils
        nasm
        mingw-w64-ucrt-x86_64-gcc
        mingw-w64-ucrt-x86_64-pkgconf
        mingw-w64-ucrt-x86_64-libass
        mingw-w64-ucrt-x86_64-lame
        mingw-w64-ucrt-x86_64-libvorbis
        mingw-w64-ucrt-x86_64-x264
    )

    if [[ "$ENABLE_X265" == "1" ]]; then
        packages+=(mingw-w64-ucrt-x86_64-x265)
    fi
    if [[ "$ENABLE_NVENC" == "1" ]]; then
        packages+=(mingw-w64-ucrt-x86_64-ffnvcodec-headers)
    fi
    if [[ "$ENABLE_AMF" == "1" ]]; then
        packages+=(mingw-w64-ucrt-x86_64-amf-headers)
    fi
    if [[ "$ENABLE_QSV" == "1" ]]; then
        packages+=(mingw-w64-ucrt-x86_64-libvpl)
    fi

    echo "MSYS2 bagimliliklari kuruluyor..."
    pacman -S --noconfirm --needed "${packages[@]}"
}

configure_profile() {
    protocols=(file pipe)
    demuxers=(mov matroska avi mp3 wav flac aac ogg concat mpegts srt)
    muxers=(mov mp4 matroska mp3 wav flac ogg adts null mpegts)
    bsfs=(aac_adtstoasc)
    filters=(
        aformat aresample format scale afade atrim asetpts trim setpts concat
        silencedetect silenceremove subtitles color
        afftdn anlmdn highpass lowpass adeclick
    )
    indevs=(lavfi)
    encoders=(aac flac pcm_s16le srt libmp3lame libvorbis libx264)
    decoders=(
        aac ac3 eac3 flac mp3float vorbis opus
        pcm_s16le pcm_s24le pcm_s32le pcm_f32le pcm_f64le pcm_u8 pcm_alaw pcm_mulaw
        subrip wrapped_avframe h264 hevc mpeg4 mpeg2video mjpeg
    )
    parsers=(aac ac3 flac h264 hevc mjpeg mpegaudio mpeg4video mpegvideo opus vorbis)
    license_names=(libass lame libvorbis x264)

    case "$PROFILE" in
        balanced)
            extra_decoders=(av1 vp8 vp9 vc1 prores h263)
            extra_parsers=(av1 vp8 vp9 vc1)
            ;;
        aggressive)
            extra_decoders=()
            extra_parsers=()
            ;;
        *)
            echo "Bilinmeyen profil: $PROFILE"
            exit 1
            ;;
    esac

    append_unique decoders "${extra_decoders[@]}"
    append_unique parsers "${extra_parsers[@]}"

    if [[ "$ENABLE_X265" == "1" ]]; then
        encoders+=(libx265)
        license_names+=(x265)
    fi
    if [[ "$ENABLE_NVENC" == "1" ]]; then
        encoders+=(h264_nvenc hevc_nvenc)
        license_names+=(ffnvcodec-headers)
    fi
    if [[ "$ENABLE_AMF" == "1" ]]; then
        encoders+=(h264_amf hevc_amf)
        license_names+=(amf-headers)
    fi
    if [[ "$ENABLE_QSV" == "1" ]]; then
        encoders+=(h264_qsv hevc_qsv)
        license_names+=(libvpl)
    fi
}

prepare_source() {
    mkdir -p "$(dirname "$SRC_DIR")"
    if [[ ! -d "$SRC_DIR/.git" ]]; then
        git clone https://github.com/FFmpeg/FFmpeg.git "$SRC_DIR"
    fi

    git -C "$SRC_DIR" fetch --tags --force origin
    git -C "$SRC_DIR" checkout --force "$FFMPEG_REF"
    git -C "$SRC_DIR" clean -fdx
}

build_ffmpeg() {
    rm -rf "$BUILD_DIR" "$PREFIX_DIR" "$OUTPUT_DIR"
    mkdir -p "$BUILD_DIR" "$PREFIX_DIR" "$OUTPUT_DIR" "$OUTPUT_DIR/licenses"

    configure_flags=(
        --prefix="$PREFIX_DIR"
        --target-os=mingw32
        --arch=x86_64
        --pkg-config=pkg-config
        --disable-autodetect
        --disable-doc
        --disable-htmlpages
        --disable-manpages
        --disable-podpages
        --disable-txtpages
        --disable-debug
        --disable-network
        --disable-postproc
        --disable-ffplay
        --disable-shared
        --enable-static
        --enable-small
        --enable-gpl
        --disable-everything
        --enable-ffmpeg
        --enable-ffprobe
        --enable-libass
        --enable-libmp3lame
        --enable-libvorbis
        --enable-libx264
    )

    if [[ "$ENABLE_X265" == "1" ]]; then
        configure_flags+=(--enable-libx265)
    fi
    if [[ "$ENABLE_NVENC" == "1" ]]; then
        configure_flags+=(--enable-ffnvcodec --enable-nvenc)
    fi
    if [[ "$ENABLE_AMF" == "1" ]]; then
        configure_flags+=(--enable-amf)
    fi
    if [[ "$ENABLE_QSV" == "1" ]]; then
        if grep -q -- '--enable-libvpl' "$SRC_DIR/configure"; then
            configure_flags+=(--enable-libvpl)
        else
            configure_flags+=(--enable-libmfx)
        fi
    fi

    enable_component_list protocol "${protocols[@]}"
    enable_component_list demuxer "${demuxers[@]}"
    enable_component_list muxer "${muxers[@]}"
    enable_component_list bsf "${bsfs[@]}"
    enable_component_list filter "${filters[@]}"
    enable_component_list indev "${indevs[@]}"
    enable_component_list encoder "${encoders[@]}"
    enable_component_list decoder "${decoders[@]}"
    enable_component_list parser "${parsers[@]}"

    pushd "$BUILD_DIR" >/dev/null
    "$SRC_DIR/configure" "${configure_flags[@]}"
    make -j"$(nproc)"
    make install
    strip "$PREFIX_DIR/bin/ffmpeg.exe" "$PREFIX_DIR/bin/ffprobe.exe" || true
    popd >/dev/null
}

package_output() {
    cp -f "$PREFIX_DIR/bin/ffmpeg.exe" "$OUTPUT_DIR/"
    cp -f "$PREFIX_DIR/bin/ffprobe.exe" "$OUTPUT_DIR/"

    copy_runtime_deps "$PREFIX_DIR/bin/ffmpeg.exe"
    copy_runtime_deps "$PREFIX_DIR/bin/ffprobe.exe"

    "$OUTPUT_DIR/ffmpeg.exe" -hide_banner -version >"$OUTPUT_DIR/ffmpeg-version.txt"
    "$OUTPUT_DIR/ffmpeg.exe" -hide_banner -buildconf >"$OUTPUT_DIR/ffmpeg-buildconf.txt"
    "$OUTPUT_DIR/ffmpeg.exe" -hide_banner -encoders >"$OUTPUT_DIR/ffmpeg-encoders.txt"
    "$OUTPUT_DIR/ffmpeg.exe" -hide_banner -decoders >"$OUTPUT_DIR/ffmpeg-decoders.txt"
    "$OUTPUT_DIR/ffmpeg.exe" -hide_banner -filters >"$OUTPUT_DIR/ffmpeg-filters.txt"
    "$OUTPUT_DIR/ffmpeg.exe" -hide_banner -muxers >"$OUTPUT_DIR/ffmpeg-muxers.txt"
    "$OUTPUT_DIR/ffmpeg.exe" -hide_banner -demuxers >"$OUTPUT_DIR/ffmpeg-demuxers.txt"
    "$OUTPUT_DIR/ffmpeg.exe" -hide_banner -bsfs >"$OUTPUT_DIR/ffmpeg-bsfs.txt"
    "$OUTPUT_DIR/ffprobe.exe" -hide_banner -version >"$OUTPUT_DIR/ffprobe-version.txt"

    write_component_report

    local file_name
    for file_name in COPYING* LICENSE*; do
        if [[ -f "$SRC_DIR/$file_name" ]]; then
            cp -f "$SRC_DIR/$file_name" "$OUTPUT_DIR/licenses/"
        fi
    done

    local license_name
    for license_name in "${license_names[@]}"; do
        copy_license_dir "$license_name"
    done
}

main() {
    if [[ "$INSTALL_DEPS" == "1" ]]; then
        require_cmd pacman
        install_dependencies
    fi

    require_cmd git
    require_cmd make
    require_cmd pkg-config
    require_cmd nasm
    require_cmd strip
    require_cmd awk
    require_cmd sed
    require_cmd ldd

    if [[ "$CLEAN" == "1" ]]; then
        rm -rf "$BUILD_DIR" "$PREFIX_DIR" "$OUTPUT_DIR"
    fi

    configure_profile
    prepare_source
    build_ffmpeg
    package_output

    echo
    echo "FFmpeg custom build hazir:"
    echo "  $OUTPUT_DIR"
}

main "$@"
