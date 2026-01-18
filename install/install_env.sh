#!/bin/bash
#
# install_env.sh - Configure environment variables (.env file)
#
# Sets up API keys and credentials for:
#   - OpenAI API
#   - LiveKit (URL, API Key, API Secret)
#   - Spotify (optional)
#
# Usage:
#   ./install_env.sh                              # Interactive
#   ./install_env.sh --openai-key <KEY>           # Set OpenAI key
#   ./install_env.sh --livekit-url <URL>          # Set LiveKit URL
#   ./install_env.sh --check                      # Check current config
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
OPENAI_KEY=""
LIVEKIT_URL=""
LIVEKIT_API_KEY=""
LIVEKIT_API_SECRET=""

show_help() {
    echo "LeLamp Environment Configuration"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --openai-key <KEY>         Set OpenAI API key"
    echo "  --livekit-url <URL>        Set LiveKit URL"
    echo "  --livekit-key <KEY>        Set LiveKit API key"
    echo "  --livekit-secret <SECRET>  Set LiveKit API secret"
    echo "  --check                    Check current configuration"
    echo "  --generate-livekit         Generate LiveKit credentials via CLI"
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --openai-key)
                OPENAI_KEY="$2"
                shift 2
                ;;
            --livekit-url)
                LIVEKIT_URL="$2"
                shift 2
                ;;
            --livekit-key)
                LIVEKIT_API_KEY="$2"
                shift 2
                ;;
            --livekit-secret)
                LIVEKIT_API_SECRET="$2"
                shift 2
                ;;
            --check)
                ACTION="check"
                shift
                ;;
            --generate-livekit)
                ACTION="generate-livekit"
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

# Check current configuration
check_env() {
    print_header "Environment Configuration Status"

    LELAMP_DIR=$(get_lelamp_dir)
    ENV_FILE="$LELAMP_DIR/.env"

    if [ ! -f "$ENV_FILE" ]; then
        print_warning ".env file not found at $ENV_FILE"
        return 1
    fi

    print_success ".env file exists at $ENV_FILE"
    echo ""

    # Check for required variables (without revealing values)
    if grep -q "^OPENAI_API_KEY=" "$ENV_FILE" && ! grep -q "^OPENAI_API_KEY=$" "$ENV_FILE"; then
        print_success "OPENAI_API_KEY is set"
    else
        print_warning "OPENAI_API_KEY is not set"
    fi

    if grep -q "^LIVEKIT_URL=" "$ENV_FILE" && ! grep -q "^LIVEKIT_URL=$" "$ENV_FILE"; then
        print_success "LIVEKIT_URL is set"
    else
        print_warning "LIVEKIT_URL is not set"
    fi

    if grep -q "^LIVEKIT_API_KEY=" "$ENV_FILE" && ! grep -q "^LIVEKIT_API_KEY=$" "$ENV_FILE"; then
        print_success "LIVEKIT_API_KEY is set"
    else
        print_warning "LIVEKIT_API_KEY is not set"
    fi

    if grep -q "^LIVEKIT_API_SECRET=" "$ENV_FILE" && ! grep -q "^LIVEKIT_API_SECRET=$" "$ENV_FILE"; then
        print_success "LIVEKIT_API_SECRET is set"
    else
        print_warning "LIVEKIT_API_SECRET is not set"
    fi

    # Optional: Spotify
    if grep -q "^SPOTIFY_CLIENT_ID=" "$ENV_FILE"; then
        print_info "SPOTIFY_CLIENT_ID is configured (optional)"
    fi
}

# Generate LiveKit credentials
generate_livekit() {
    print_header "Generate LiveKit Credentials"

    if ! command_exists lk; then
        print_error "LiveKit CLI (lk) not found"
        print_info "Install it with: ./install/install_livekit.sh"
        return 1
    fi

    # Check if we're in a headless environment
    if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
        print_warning "Headless environment detected - cannot open browser"
        echo ""
        echo "To get LiveKit credentials, you have two options:"
        echo ""
        echo "  ${BLUE}Option 1: LiveKit Cloud Dashboard (Recommended)${NC}"
        echo "    1. Visit: https://cloud.livekit.io"
        echo "    2. Sign up or log in"
        echo "    3. Create a new project (or use existing)"
        echo "    4. Go to Settings > Keys"
        echo "    5. Copy your URL, API Key, and API Secret"
        echo ""
        echo "  ${BLUE}Option 2: Run on a machine with a browser${NC}"
        echo "    On another computer with LiveKit CLI installed, run:"
        echo "      lk app env"
        echo "    Then copy the credentials here"
        echo ""
        return 1
    fi

    print_info "Generating LiveKit credentials using 'lk app env'..."
    print_info "This will open a browser to authenticate with LiveKit Cloud..."

    LELAMP_DIR=$(get_lelamp_dir)
    cd "$LELAMP_DIR"

    if lk app env -w > .env.local 2>/dev/null; then
        print_success "LiveKit credentials generated to .env.local"

        # Extract credentials
        LIVEKIT_URL=$(grep "^LIVEKIT_URL=" .env.local | cut -d'=' -f2-)
        LIVEKIT_API_KEY=$(grep "^LIVEKIT_API_KEY=" .env.local | cut -d'=' -f2-)
        LIVEKIT_API_SECRET=$(grep "^LIVEKIT_API_SECRET=" .env.local | cut -d'=' -f2-)

        print_info "URL: $LIVEKIT_URL"
        print_info "API Key: $LIVEKIT_API_KEY"
        print_info "API Secret: [hidden]"

        return 0
    else
        print_error "Failed to generate LiveKit credentials"
        return 1
    fi
}

# Create or update .env file
setup_env() {
    print_header "Environment Configuration"

    LELAMP_DIR=$(get_lelamp_dir)
    ENV_FILE="$LELAMP_DIR/.env"

    # Check if .env already exists
    if [ -f "$ENV_FILE" ]; then
        print_warning ".env file already exists"
        if [ "$SKIP_CONFIRM" != "true" ]; then
            if ! ask_yes_no "Do you want to recreate it?"; then
                print_info "Keeping existing .env file"
                return 0
            fi
        else
            print_info "Keeping existing .env file"
            return 0
        fi
    fi

    # Collect credentials
    if [ "$SKIP_CONFIRM" != "true" ]; then
        echo "You'll need the following credentials:"
        echo "  - OpenAI API Key (required)"
        echo "  - LiveKit credentials (can be generated or entered manually)"
        echo ""

        if ! ask_yes_no "Configure environment now?" "y"; then
            print_info "Skipping environment configuration"
            print_info "Create .env manually later based on .env.example"
            return 0
        fi
    fi

    # Get OpenAI API Key
    if [ -z "$OPENAI_KEY" ]; then
        if [ "$SKIP_CONFIRM" = "true" ]; then
            print_warning "OpenAI API Key not provided - skipping (set later via WebUI or .env)"
            OPENAI_KEY=""
        else
            read -p "Enter OpenAI API Key: " OPENAI_KEY < "$INPUT_DEVICE"
            if [ -z "$OPENAI_KEY" ]; then
                print_error "OpenAI API Key is required"
                return 1
            fi
        fi
    fi

    # Get LiveKit credentials
    if [ -z "$LIVEKIT_URL" ] || [ -z "$LIVEKIT_API_KEY" ] || [ -z "$LIVEKIT_API_SECRET" ]; then
        if [ "$SKIP_CONFIRM" != "true" ]; then
            echo ""
            echo "LiveKit credentials:"
            echo "  1) Enter manually"
            echo "  2) Generate via LiveKit CLI (requires browser)"
            echo "  3) Skip (configure later)"
            read -p "Enter choice [1-3]: " lk_choice < "$INPUT_DEVICE"

            case $lk_choice in
                1)
                    read -p "Enter LIVEKIT_URL (e.g., wss://your-project.livekit.cloud): " LIVEKIT_URL < "$INPUT_DEVICE"
                    read -p "Enter LIVEKIT_API_KEY: " LIVEKIT_API_KEY < "$INPUT_DEVICE"
                    read -p "Enter LIVEKIT_API_SECRET: " LIVEKIT_API_SECRET < "$INPUT_DEVICE"
                    ;;
                2)
                    generate_livekit || true
                    ;;
                3)
                    print_info "Skipping LiveKit configuration"
                    ;;
            esac
        fi
    fi

    # Create .env file
    print_info "Creating .env file..."

    cat > "$ENV_FILE" << EOF
OPENAI_API_KEY=$OPENAI_KEY
EOF

    if [ -n "$LIVEKIT_URL" ] && [ -n "$LIVEKIT_API_KEY" ] && [ -n "$LIVEKIT_API_SECRET" ]; then
        cat >> "$ENV_FILE" << EOF
LIVEKIT_URL=$LIVEKIT_URL
LIVEKIT_API_KEY=$LIVEKIT_API_KEY
LIVEKIT_API_SECRET=$LIVEKIT_API_SECRET

# Spotify API credentials (optional - for Spotify integration)
# Requires Spotify Premium subscription
# Setup instructions:
#   1. Go to https://developer.spotify.com/dashboard
#   2. Create app (name: LeLamp, description: LeLamp)
#   3. Set Redirect URI: http://127.0.0.1:8888/callback
#   4. Enable: Web API and Web Playback SDK
#   5. Copy Client ID and Client Secret below
# SPOTIFY_CLIENT_ID=""
# SPOTIFY_CLIENT_SECRET=""
EOF
        print_success ".env file created with OpenAI and LiveKit credentials"
    else
        cat >> "$ENV_FILE" << EOF
# Add LiveKit credentials below
# Get them from: https://cloud.livekit.io (Settings > Keys)
# LIVEKIT_URL=wss://your-project.livekit.cloud
# LIVEKIT_API_KEY=
# LIVEKIT_API_SECRET=

# Spotify API credentials (optional - for Spotify integration)
# Requires Spotify Premium subscription
# Setup instructions:
#   1. Go to https://developer.spotify.com/dashboard
#   2. Create app (name: LeLamp, description: LeLamp)
#   3. Set Redirect URI: http://127.0.0.1:8888/callback
#   4. Enable: Web API and Web Playback SDK
#   5. Copy Client ID and Client Secret below
# SPOTIFY_CLIENT_ID=""
# SPOTIFY_CLIENT_SECRET=""
EOF
        print_warning ".env file created with OpenAI key only"
        print_info "Add LiveKit credentials later by editing: $ENV_FILE"
    fi

    # Secure the file
    chmod 600 "$ENV_FILE"
    print_info "File permissions set to 600 (owner read/write only)"
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            setup_env
            ;;
        check)
            check_env
            ;;
        generate-livekit)
            generate_livekit
            ;;
    esac

    # Mark environment setup as complete in config.yaml
    mark_setup_complete "environment"
}

# Run main function
main "$@"
