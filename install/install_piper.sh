#!/bin/bash
#
# install_piper.sh - Install Piper TTS for local voice synthesis
#
# Piper is a fast, local neural text-to-speech system.
# This script downloads the Piper binary and voice models for Raspberry Pi 5.
#
# Usage:
#   ./install_piper.sh                    # Interactive install
#   ./install_piper.sh -y                 # Non-interactive install
#   ./install_piper.sh --voice amy        # Install specific voice
#   ./install_piper.sh --list-voices      # List available voices
#   ./install_piper.sh --uninstall        # Remove Piper
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Piper version and URLs
PIPER_VERSION="2023.11.14-2"
PIPER_RELEASE_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}"
PIPER_VOICES_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

# Installation paths (relative to LELAMP_DIR)
PIPER_DIR=""  # Set in init
PIPER_BIN=""
VOICES_DIR=""

# Default voice to install
DEFAULT_VOICE="en_US-ryan-medium"

# All voices to install by default
DEFAULT_VOICES=(
    "en_US-ryan-medium"
    "en_US-amy-medium"
    "en_US-lessac-medium"
    "en_GB-alan-medium"
    "en_GB-alba-medium"
)

# Available voices (subset of most useful ones)
declare -A VOICE_INFO=(
    ["en_US-ryan-medium"]="Ryan (US Male) - Clear, natural voice"
    ["en_US-amy-medium"]="Amy (US Female) - Warm, friendly voice"
    ["en_US-lessac-medium"]="Lessac (US Male) - Professional voice"
    ["en_US-libritts-high"]="LibriTTS (US) - High quality multi-speaker"
    ["en_GB-alan-medium"]="Alan (UK Male) - British accent"
    ["en_GB-alba-medium"]="Alba (UK Female) - British accent"
)

# Script variables
ACTION="install"
SELECTED_VOICE=""
INSTALL_ALL_VOICES=true

show_help() {
    echo "Piper TTS Installation for LeLamp"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -y, --yes            Non-interactive mode (install all voices)"
    echo "  --voice <name>       Install only a specific voice"
    echo "  --all-voices         Install all default voices (default behavior)"
    echo "  --list-voices        List available voices"
    echo "  --status             Show installation status"
    echo "  --uninstall          Remove Piper installation"
    echo ""
    echo "Default voices installed:"
    for voice in "${DEFAULT_VOICES[@]}"; do
        echo "  • $voice - ${VOICE_INFO[$voice]}"
    done
    echo ""
    echo "Additional voices available:"
    for voice in "${!VOICE_INFO[@]}"; do
        local is_default=false
        for dv in "${DEFAULT_VOICES[@]}"; do
            if [ "$voice" = "$dv" ]; then
                is_default=true
                break
            fi
        done
        if [ "$is_default" = "false" ]; then
            echo "  • $voice - ${VOICE_INFO[$voice]}"
        fi
    done
    echo ""
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --voice)
                SELECTED_VOICE="$2"
                INSTALL_ALL_VOICES=false
                shift 2
                ;;
            --all-voices)
                INSTALL_ALL_VOICES=true
                shift
                ;;
            --list-voices)
                ACTION="list-voices"
                shift
                ;;
            --uninstall|--remove)
                ACTION="uninstall"
                shift
                ;;
            --status)
                ACTION="status"
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            -y|--yes|--skip-confirm)
                SKIP_CONFIRM=true
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
}

init_paths() {
    LELAMP_DIR=$(get_lelamp_dir)
    PIPER_DIR="$LELAMP_DIR/piper"
    PIPER_BIN="$PIPER_DIR/piper"
    VOICES_DIR="$PIPER_DIR/voices"
}

# Detect architecture
get_piper_arch() {
    local arch=$(uname -m)
    case $arch in
        aarch64)
            echo "aarch64"
            ;;
        armv7l)
            echo "armv7l"
            ;;
        x86_64)
            echo "amd64"
            ;;
        *)
            print_error "Unsupported architecture: $arch"
            exit 1
            ;;
    esac
}

# Download and extract Piper binary
install_piper_binary() {
    print_header "Installing Piper Binary"

    local arch=$(get_piper_arch)
    local tarball="piper_linux_${arch}.tar.gz"
    local download_url="${PIPER_RELEASE_URL}/${tarball}"

    print_info "Architecture: $arch"
    print_info "Downloading Piper ${PIPER_VERSION}..."

    # Create directories
    mkdir -p "$PIPER_DIR"
    mkdir -p "$VOICES_DIR"

    # Download and extract
    local temp_dir=$(mktemp -d)
    cd "$temp_dir"

    if ! curl -fsSL -o "$tarball" "$download_url"; then
        print_error "Failed to download Piper from $download_url"
        rm -rf "$temp_dir"
        return 1
    fi

    print_info "Extracting..."
    tar -xzf "$tarball"

    # Move piper directory contents
    if [ -d "piper" ]; then
        cp -r piper/* "$PIPER_DIR/"
    else
        print_error "Unexpected archive structure"
        rm -rf "$temp_dir"
        return 1
    fi

    # Cleanup
    cd - > /dev/null
    rm -rf "$temp_dir"

    # Make binary executable
    chmod +x "$PIPER_BIN"

    # Verify installation
    if [ -x "$PIPER_BIN" ]; then
        print_success "Piper binary installed to $PIPER_DIR"
        return 0
    else
        print_error "Piper binary not found after installation"
        return 1
    fi
}

# Download a voice model
download_voice() {
    local voice_name="$1"

    print_info "Downloading voice: $voice_name"

    # Parse voice name (format: lang_REGION-speaker-quality)
    # Example: en_US-ryan-medium -> en/en_US/ryan/medium/en_US-ryan-medium.onnx
    local lang_region=$(echo "$voice_name" | cut -d'-' -f1)
    local lang=$(echo "$lang_region" | cut -d'_' -f1)
    local speaker=$(echo "$voice_name" | cut -d'-' -f2)
    local quality=$(echo "$voice_name" | cut -d'-' -f3)

    # Construct URLs (path is: lang/lang_REGION/speaker/quality/filename)
    local base_path="${lang}/${lang_region}/${speaker}/${quality}"
    local onnx_url="${PIPER_VOICES_URL}/${base_path}/${voice_name}.onnx"
    local json_url="${PIPER_VOICES_URL}/${base_path}/${voice_name}.onnx.json"

    local onnx_file="$VOICES_DIR/${voice_name}.onnx"
    local json_file="$VOICES_DIR/${voice_name}.onnx.json"

    # Download ONNX model
    print_info "  Downloading model file..."
    if ! curl -fsSL -o "$onnx_file" "$onnx_url"; then
        print_error "Failed to download voice model: $voice_name"
        print_info "URL: $onnx_url"
        return 1
    fi

    # Download JSON config
    print_info "  Downloading config file..."
    if ! curl -fsSL -o "$json_file" "$json_url"; then
        print_warning "Failed to download voice config (non-critical)"
    fi

    # Verify download
    if [ -f "$onnx_file" ]; then
        local size=$(du -h "$onnx_file" | cut -f1)
        print_success "Voice '$voice_name' installed ($size)"
        return 0
    else
        print_error "Voice file not found after download"
        return 1
    fi
}

# List available voices
list_voices() {
    print_header "Available Piper Voices"

    echo ""
    echo "Pre-configured voices (easy install):"
    echo ""
    for voice in "${!VOICE_INFO[@]}"; do
        local installed=""
        if [ -f "$VOICES_DIR/${voice}.onnx" ]; then
            installed=" [installed]"
        fi
        echo "  $voice"
        echo "    ${VOICE_INFO[$voice]}${installed}"
        echo ""
    done

    echo "More voices available at:"
    echo "  https://huggingface.co/rhasspy/piper-voices"
    echo ""
    echo "Install a voice with:"
    echo "  $0 --voice <voice-name>"
    echo ""
}

# Show installation status
show_status() {
    print_header "Piper Installation Status"

    echo ""
    echo "Installation directory: $PIPER_DIR"
    echo ""

    # Check binary
    if [ -x "$PIPER_BIN" ]; then
        print_success "Piper binary: installed"
        # Try to get version
        local version=$("$PIPER_BIN" --version 2>&1 || echo "unknown")
        echo "  Version: $version"
    else
        print_warning "Piper binary: not installed"
    fi

    echo ""

    # Check voices
    if [ -d "$VOICES_DIR" ]; then
        local voice_count=$(find "$VOICES_DIR" -name "*.onnx" 2>/dev/null | wc -l)
        if [ "$voice_count" -gt 0 ]; then
            print_success "Voices installed: $voice_count"
            echo ""
            for onnx in "$VOICES_DIR"/*.onnx; do
                if [ -f "$onnx" ]; then
                    local name=$(basename "$onnx")
                    local size=$(du -h "$onnx" | cut -f1)
                    echo "  - $name ($size)"
                fi
            done
        else
            print_warning "No voices installed"
        fi
    else
        print_warning "Voices directory not found"
    fi

    echo ""
}

# Uninstall Piper
uninstall_piper() {
    print_header "Uninstalling Piper"

    if [ ! -d "$PIPER_DIR" ]; then
        print_info "Piper is not installed"
        return 0
    fi

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This will remove:"
        echo "  - Piper binary"
        echo "  - All voice models"
        echo "  - Directory: $PIPER_DIR"
        echo ""
        if ! ask_yes_no "Remove Piper installation?" "n"; then
            print_info "Uninstall cancelled"
            return 0
        fi
    fi

    rm -rf "$PIPER_DIR"
    print_success "Piper uninstalled"
}

# Install dependencies
install_dependencies() {
    print_info "Checking dependencies..."

    # sox is needed for audio resampling
    if ! command -v sox &> /dev/null; then
        print_info "Installing sox..."
        sudo apt-get update
        sudo apt-get install -y sox libsox-fmt-all
    fi

    print_success "Dependencies installed"
}

# Main installation
install_piper() {
    print_header "Piper TTS Installation"

    # Calculate total size
    local voice_count=${#DEFAULT_VOICES[@]}
    local total_size=$((50 + voice_count * 60))  # ~50MB binary + ~60MB per voice

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This will install Piper TTS for local voice synthesis."
        echo ""
        echo "Piper provides fast, high-quality text-to-speech that runs"
        echo "entirely on your Raspberry Pi - no cloud API needed."
        echo ""
        echo "Installation includes:"
        echo "  - Piper binary (~50MB)"
        if [ "$INSTALL_ALL_VOICES" = "true" ]; then
            echo "  - ${voice_count} voice models (~60MB each):"
            for voice in "${DEFAULT_VOICES[@]}"; do
                echo "      • $voice"
            done
        else
            echo "  - Voice model: $SELECTED_VOICE (~60MB)"
        fi
        echo ""
        echo "Total download: ~${total_size}MB"
        echo ""
        if ! ask_yes_no "Continue with installation?" "y"; then
            print_info "Installation cancelled"
            return 0
        fi
    fi

    # Install dependencies
    install_dependencies

    # Install binary if needed
    if [ ! -x "$PIPER_BIN" ]; then
        install_piper_binary || return 1
    else
        print_success "Piper binary already installed"
    fi

    # Install voices
    if [ "$INSTALL_ALL_VOICES" = "true" ]; then
        print_header "Downloading Voice Models"
        local installed=0
        local total=${#DEFAULT_VOICES[@]}
        for voice in "${DEFAULT_VOICES[@]}"; do
            installed=$((installed + 1))
            echo ""
            echo "[$installed/$total] $voice"
            if [ ! -f "$VOICES_DIR/${voice}.onnx" ]; then
                download_voice "$voice" || print_warning "Failed to download $voice"
            else
                print_success "Voice '$voice' already installed"
            fi
        done
    else
        # Single voice installation
        if [ -z "$SELECTED_VOICE" ]; then
            SELECTED_VOICE="$DEFAULT_VOICE"
        fi
        if [ ! -f "$VOICES_DIR/${SELECTED_VOICE}.onnx" ]; then
            download_voice "$SELECTED_VOICE" || return 1
        else
            print_success "Voice '$SELECTED_VOICE' already installed"
        fi
    fi

    # Test installation
    echo ""
    print_info "Testing Piper installation..."
    local test_output=$("$PIPER_BIN" --help 2>&1 || true)
    if echo "$test_output" | grep -q "piper"; then
        print_success "Piper is working correctly"
    else
        print_warning "Piper may not be working correctly"
        print_info "Try running: $PIPER_BIN --help"
    fi

    echo ""
    print_success "Piper TTS installation complete!"
    echo ""
    echo "Voice models installed in: $VOICES_DIR"
    echo ""
    echo "To install additional voices:"
    echo "  $0 --voice <voice-name>"
    echo "  $0 --list-voices"
    echo ""
}

# Main function
main() {
    init_script
    parse_args "$@"
    init_paths

    case $ACTION in
        install)
            install_piper
            ;;
        list-voices)
            list_voices
            ;;
        status)
            show_status
            ;;
        uninstall)
            uninstall_piper
            ;;
    esac
}

main "$@"
