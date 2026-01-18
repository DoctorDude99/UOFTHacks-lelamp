#!/bin/bash
#
# install_ollama.sh - Install Ollama for local LLM inference
#
# Ollama provides local language model inference for the local AI pipeline.
# This script installs Ollama and pulls lightweight models suitable for Raspberry Pi 5.
#
# Usage:
#   ./install_ollama.sh                    # Interactive install
#   ./install_ollama.sh -y                 # Non-interactive install
#   ./install_ollama.sh --model phi3:mini  # Install specific model
#   ./install_ollama.sh --list-models      # List recommended models
#   ./install_ollama.sh --uninstall        # Remove Ollama
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Default model - ultra lightweight for Pi5
DEFAULT_MODEL="gemma3:270m"

# Recommended models for Pi5 (sorted by size, smallest first)
declare -A MODEL_INFO=(
    ["gemma3:270m"]="Gemma 3 270M - Smallest, ultra-fast (~292MB)"
    ["tinyllama"]="TinyLlama 1.1B - Very fast, basic capability (~637MB)"
    ["gemma3:1b"]="Gemma 3 1B - Ultra light, fast responses (~815MB)"
    ["qwen2.5:1.5b"]="Qwen 2.5 1.5B - Alibaba's efficient model (~986MB)"
    ["llama3.2:1b"]="Llama 3.2 1B - Good balance of speed/quality (~1.3GB)"
    ["gemma2:2b"]="Gemma 2 2B - Google's compact model (~1.6GB)"
    ["phi3:mini"]="Phi-3 Mini - Microsoft's efficient model (~2.3GB)"
)

# Models to install by default
DEFAULT_MODELS=(
    "gemma3:270m"
)

# Script variables
ACTION="install"
SELECTED_MODEL=""
INSTALL_DEFAULT_MODELS=true

show_help() {
    echo "Ollama Installation for LeLamp"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -y, --yes            Non-interactive mode"
    echo "  --model <name>       Install only a specific model"
    echo "  --list-models        List recommended models for Pi5"
    echo "  --status             Show installation status"
    echo "  --uninstall          Remove Ollama installation"
    echo ""
    echo "Recommended models for Raspberry Pi 5:"
    for model in "gemma3:270m" "tinyllama" "gemma3:1b" "qwen2.5:1.5b" "llama3.2:1b" "gemma2:2b" "phi3:mini"; do
        if [[ -v MODEL_INFO[$model] ]]; then
            echo "  • $model"
            echo "      ${MODEL_INFO[$model]}"
        fi
    done
    echo ""
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --model)
                SELECTED_MODEL="$2"
                INSTALL_DEFAULT_MODELS=false
                shift 2
                ;;
            --list-models)
                ACTION="list-models"
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

# Check if Ollama is installed
is_ollama_installed() {
    command -v ollama &> /dev/null
}

# Check if Ollama service is running
is_ollama_running() {
    systemctl is-active --quiet ollama 2>/dev/null
}

# Install Ollama binary
install_ollama_binary() {
    print_header "Installing Ollama"

    if is_ollama_installed; then
        local version=$(ollama --version 2>&1 | head -1)
        print_success "Ollama already installed: $version"
        return 0
    fi

    print_info "Downloading and installing Ollama..."
    print_info "This may take a few minutes..."

    # Use official install script
    if curl -fsSL https://ollama.com/install.sh | sh; then
        print_success "Ollama installed successfully"
    else
        print_error "Failed to install Ollama"
        return 1
    fi

    # Wait for service to start
    sleep 2

    # Verify installation
    if is_ollama_installed; then
        local version=$(ollama --version 2>&1 | head -1)
        print_success "Ollama version: $version"
    else
        print_error "Ollama installation verification failed"
        return 1
    fi
}

# Start Ollama service
start_ollama_service() {
    if ! is_ollama_running; then
        print_info "Starting Ollama service..."
        sudo systemctl start ollama 2>/dev/null || true
        sleep 2
    fi

    if is_ollama_running; then
        print_success "Ollama service is running"
    else
        print_warning "Ollama service may not be running"
    fi
}

# Pull a model
pull_model() {
    local model="$1"

    print_info "Pulling model: $model"
    print_info "This may take several minutes depending on your connection..."

    if ollama pull "$model"; then
        print_success "Model '$model' downloaded successfully"
        return 0
    else
        print_error "Failed to pull model: $model"
        return 1
    fi
}

# List installed models
list_installed_models() {
    if ! is_ollama_installed; then
        echo "Ollama not installed"
        return
    fi

    ollama list 2>/dev/null || echo "No models installed"
}

# List recommended models
list_models() {
    print_header "Recommended Models for Raspberry Pi 5"

    echo ""
    echo "Ultra-light (fastest, ~1GB RAM):"
    echo "  • gemma3:1b      - ${MODEL_INFO[gemma3:1b]}"
    echo "  • tinyllama       - ${MODEL_INFO[tinyllama]}"
    echo "  • qwen2.5:1.5b   - ${MODEL_INFO[qwen2.5:1.5b]}"
    echo ""
    echo "Light (good balance, ~2GB RAM):"
    echo "  • llama3.2:1b    - ${MODEL_INFO[llama3.2:1b]}"
    echo "  • gemma2:2b      - ${MODEL_INFO[gemma2:2b]}"
    echo ""
    echo "Medium (better quality, ~3GB RAM):"
    echo "  • phi3:mini      - ${MODEL_INFO[phi3:mini]}"
    echo ""
    echo "Currently installed:"
    list_installed_models
    echo ""
    echo "Install a model with:"
    echo "  $0 --model <model-name>"
    echo "  ollama pull <model-name>"
    echo ""
}

# Show installation status
show_status() {
    print_header "Ollama Installation Status"

    echo ""

    # Check binary
    if is_ollama_installed; then
        local version=$(ollama --version 2>&1 | head -1)
        print_success "Ollama binary: installed"
        echo "  Version: $version"
    else
        print_warning "Ollama binary: not installed"
        return
    fi

    echo ""

    # Check service
    if is_ollama_running; then
        print_success "Ollama service: running"
    else
        print_warning "Ollama service: not running"
    fi

    echo ""

    # List models
    echo "Installed models:"
    local models=$(ollama list 2>/dev/null)
    if [ -n "$models" ]; then
        echo "$models" | while read -r line; do
            echo "  $line"
        done
    else
        echo "  (none)"
    fi

    echo ""
}

# Uninstall Ollama
uninstall_ollama() {
    print_header "Uninstalling Ollama"

    if ! is_ollama_installed; then
        print_info "Ollama is not installed"
        return 0
    fi

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This will remove:"
        echo "  - Ollama binary"
        echo "  - Ollama service"
        echo "  - All downloaded models (~/.ollama)"
        echo ""
        if ! ask_yes_no "Remove Ollama installation?" "n"; then
            print_info "Uninstall cancelled"
            return 0
        fi
    fi

    # Stop service
    sudo systemctl stop ollama 2>/dev/null || true
    sudo systemctl disable ollama 2>/dev/null || true

    # Remove binary
    sudo rm -f /usr/local/bin/ollama

    # Remove service file
    sudo rm -f /etc/systemd/system/ollama.service
    sudo systemctl daemon-reload

    # Remove models directory
    rm -rf ~/.ollama

    print_success "Ollama uninstalled"
}

# Update LeLamp config for local AI
update_config() {
    local model="$1"

    print_info "Updating LeLamp config for local AI..."

    local config_file="$HOME/.lelamp/config.yaml"
    local lelamp_dir="${LELAMP_DIR:-$HOME/lelampv2}"
    local venv_python="$lelamp_dir/.venv/bin/python"

    if [ -f "$config_file" ]; then
        # Use venv Python which has PyYAML installed
        if [ -x "$venv_python" ]; then
            "$venv_python" << EOF
import yaml

config_path = "$config_file"
model = "$model"

try:
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}

    # Set local AI model
    config.setdefault('local_ai', {})
    config['local_ai']['ollama_model'] = model
    config['local_ai']['ollama_enabled'] = True

    with open(config_path, 'w') as f:
        yaml.safe_dump(config, f, default_flow_style=False)

    print(f"Config updated: ollama_model = {model}")
except Exception as e:
    print(f"Warning: Could not update config: {e}")
EOF
        else
            print_warning "Venv Python not found - config not updated"
        fi
    fi
}

# Main installation
install_ollama() {
    print_header "Ollama Installation for Local AI"

    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "This will install Ollama for local LLM inference."
        echo ""
        echo "Ollama enables fully offline AI conversations without"
        echo "cloud APIs - everything runs on your Raspberry Pi 5."
        echo ""
        echo "Installation includes:"
        echo "  - Ollama runtime (~200MB)"
        if [ "$INSTALL_DEFAULT_MODELS" = "true" ]; then
            echo "  - Default model: $DEFAULT_MODEL (~292MB)"
        else
            echo "  - Model: $SELECTED_MODEL"
        fi
        echo ""
        echo "Requirements:"
        echo "  - ~1-2GB disk space"
        echo "  - ~1-2GB RAM during inference"
        echo ""
        if ! ask_yes_no "Continue with installation?" "y"; then
            print_info "Installation cancelled"
            return 0
        fi
    fi

    # Install Ollama binary
    install_ollama_binary || return 1

    # Start service
    start_ollama_service

    # Pull models
    if [ "$INSTALL_DEFAULT_MODELS" = "true" ]; then
        print_header "Downloading AI Model"
        for model in "${DEFAULT_MODELS[@]}"; do
            pull_model "$model" || print_warning "Failed to pull $model"
        done
        update_config "${DEFAULT_MODELS[0]}"
    else
        if [ -n "$SELECTED_MODEL" ]; then
            print_header "Downloading AI Model"
            pull_model "$SELECTED_MODEL" || return 1
            update_config "$SELECTED_MODEL"
        fi
    fi

    # Test
    echo ""
    print_info "Testing Ollama..."
    if ollama list &>/dev/null; then
        print_success "Ollama is working correctly"
    else
        print_warning "Ollama may not be working correctly"
    fi

    echo ""
    print_success "Ollama installation complete!"
    echo ""
    echo "Installed models:"
    ollama list 2>/dev/null || echo "  (none)"
    echo ""
    echo "Usage:"
    echo "  ollama run gemma3:1b              # Chat in terminal"
    echo "  ollama pull <model>                # Download more models"
    echo "  ollama list                        # List installed models"
    echo ""
    echo "To use with LeLamp local AI pipeline:"
    echo "  Set pipeline.type: local in config.yaml"
    echo ""
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            install_ollama
            ;;
        list-models)
            list_models
            ;;
        status)
            show_status
            ;;
        uninstall)
            uninstall_ollama
            ;;
    esac
}

main "$@"
