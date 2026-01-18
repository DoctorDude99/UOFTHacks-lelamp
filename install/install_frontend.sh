#!/bin/bash
#
# Frontend Installation Script
#
# The WebUI frontend is pre-built and included in frontend/dist/
# This script optionally installs Node.js for development/rebuilding.
#
# Usage:
#   ./install_frontend.sh           # Interactive - ask about Node.js
#   ./install_frontend.sh --dev     # Install Node.js for development
#   ./install_frontend.sh --check   # Just check if frontend is ready
#   ./install_frontend.sh -y        # Skip prompts (no Node.js)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Parse arguments
INSTALL_NODEJS=false
CHECK_ONLY=false
SKIP_CONFIRM=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dev|--nodejs)
            INSTALL_NODEJS=true
            shift
            ;;
        --check)
            CHECK_ONLY=true
            shift
            ;;
        -y|--yes|--skip-confirm)
            SKIP_CONFIRM=true
            shift
            ;;
        --help|-h)
            echo "Frontend Installation Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dev, --nodejs   Install Node.js for frontend development"
            echo "  --check           Check if frontend is ready (no installation)"
            echo "  -y, --yes         Skip confirmation prompts (no Node.js)"
            echo "  --help            Show this help message"
            echo ""
            echo "The frontend is pre-built in frontend/dist/ and works without Node.js."
            echo "Only install Node.js if you plan to modify the frontend source."
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# Find project root
if [ -f "$SCRIPT_DIR/../frontend/dist/index.html" ]; then
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
elif [ -f "./frontend/dist/index.html" ]; then
    PROJECT_ROOT="$(pwd)"
else
    PROJECT_ROOT="${LELAMP_DIR:-$HOME/boxbots_lelampruntime}"
fi

check_frontend() {
    print_header "Checking Frontend Status"

    local dist_dir="$PROJECT_ROOT/frontend/dist"
    local frontend_dir="$PROJECT_ROOT/frontend"

    # Check pre-built files
    if [ -f "$dist_dir/index.html" ] && [ -d "$dist_dir/dist-assets" ]; then
        print_success "Pre-built frontend found in frontend/dist/"
        local js_files=$(ls -1 "$dist_dir/dist-assets"/*.js 2>/dev/null | wc -l)
        local css_files=$(ls -1 "$dist_dir/dist-assets"/*.css 2>/dev/null | wc -l)
        print_info "  Assets: $js_files JS files, $css_files CSS files"
        FRONTEND_READY=true
    else
        print_warning "Pre-built frontend NOT found in frontend/dist/"
        print_info "You may need to build the frontend or pull latest from git"
        FRONTEND_READY=false
    fi

    # Check source files
    if [ -f "$frontend_dir/package.json" ]; then
        print_success "Frontend source found in frontend/"
        SOURCE_EXISTS=true
    else
        print_info "Frontend source not found (optional for running)"
        SOURCE_EXISTS=false
    fi

    # Check Node.js
    if command -v node &> /dev/null; then
        local node_version=$(node --version)
        print_success "Node.js installed: $node_version"
        NODEJS_INSTALLED=true
    else
        print_info "Node.js not installed (optional - only needed for development)"
        NODEJS_INSTALLED=false
    fi

    # Check npm
    if command -v npm &> /dev/null; then
        local npm_version=$(npm --version)
        print_success "npm installed: $npm_version"
    fi

    echo ""
    if [ "$FRONTEND_READY" = true ]; then
        print_success "Frontend is ready to serve!"
    else
        print_warning "Frontend needs to be built or pulled from git"
    fi
}

install_nodejs() {
    print_header "Installing Node.js"

    # Check if already installed
    if command -v node &> /dev/null; then
        local current_version=$(node --version)
        print_info "Node.js already installed: $current_version"

        if [ "$SKIP_CONFIRM" != "true" ]; then
            if ! ask_yes_no "Reinstall/update Node.js?" "n"; then
                print_info "Keeping existing Node.js installation"
                return 0
            fi
        else
            return 0
        fi
    fi

    print_info "Installing Node.js LTS via NodeSource..."

    # Install NodeSource repository for Node.js LTS
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -

    # Install Node.js
    sudo apt-get install -y nodejs

    # Verify installation
    if command -v node &> /dev/null; then
        print_success "Node.js installed: $(node --version)"
        print_success "npm installed: $(npm --version)"
    else
        print_error "Node.js installation failed"
        return 1
    fi
}

install_dependencies() {
    print_header "Installing Frontend Dependencies"

    local frontend_dir="$PROJECT_ROOT/frontend"

    if [ ! -f "$frontend_dir/package.json" ]; then
        print_error "Frontend source not found at $frontend_dir"
        return 1
    fi

    cd "$frontend_dir"

    print_info "Running npm install..."
    npm install

    print_success "Dependencies installed"
}

build_frontend() {
    print_header "Building Frontend"

    local frontend_dir="$PROJECT_ROOT/frontend"

    if [ ! -f "$frontend_dir/package.json" ]; then
        print_error "Frontend source not found at $frontend_dir"
        return 1
    fi

    cd "$frontend_dir"

    print_info "Running npm run build..."
    npm run build

    if [ -f "$PROJECT_ROOT/frontend/dist/index.html" ]; then
        print_success "Frontend built successfully to frontend/dist/"
    else
        print_error "Build completed but output not found"
        return 1
    fi
}

main() {
    print_header "LeLamp Frontend Setup"

    init_script

    # Check current status
    check_frontend

    # If check only, exit here
    if [ "$CHECK_ONLY" = true ]; then
        exit 0
    fi

    # If frontend is ready and not installing Node.js, we're done
    if [ "$FRONTEND_READY" = true ] && [ "$INSTALL_NODEJS" = false ] && [ "$SKIP_CONFIRM" = true ]; then
        print_success "Frontend is ready, no additional setup needed"
        exit 0
    fi

    # With -y flag and no dist/, we MUST install Node.js and build
    if [ "$FRONTEND_READY" = false ] && [ "$SKIP_CONFIRM" = true ]; then
        print_info "Frontend not built - installing Node.js and building..."
        INSTALL_NODEJS=true
    fi

    # Ask about Node.js installation (interactive mode)
    if [ "$INSTALL_NODEJS" = false ] && [ "$SKIP_CONFIRM" != "true" ]; then
        echo ""
        echo "The frontend is pre-built and ready to use."
        echo "Node.js is only needed if you want to modify the frontend source code."
        echo ""
        echo "Installing Node.js adds ~200MB and is NOT required for normal operation."
        echo ""

        if ask_yes_no "Install Node.js for frontend development?" "n"; then
            INSTALL_NODEJS=true
        fi
    fi

    # Install Node.js if requested
    if [ "$INSTALL_NODEJS" = true ]; then
        install_nodejs

        # Install dependencies
        if [ "$SOURCE_EXISTS" = true ]; then
            if [ "$SKIP_CONFIRM" = true ] || ask_yes_no "Install frontend npm dependencies?" "y"; then
                install_dependencies
            fi
        fi

        # Build frontend (auto-build with -y if dist/ doesn't exist)
        if [ "$SOURCE_EXISTS" = true ] && command -v npm &> /dev/null; then
            if [ "$FRONTEND_READY" = false ] && [ "$SKIP_CONFIRM" = true ]; then
                build_frontend
            elif [ "$SKIP_CONFIRM" != "true" ] && ask_yes_no "Build frontend now?" "n"; then
                build_frontend
            fi
        fi
    fi

    print_header "Frontend Setup Complete"

    if [ "$FRONTEND_READY" = true ]; then
        print_success "WebUI is ready at http://<pi-ip>:8000"
    fi

    if [ "$INSTALL_NODEJS" = true ]; then
        echo ""
        echo "Development commands (run from frontend/ directory):"
        echo "  npm run dev      # Start dev server with hot reload"
        echo "  npm run build    # Build for production (outputs to frontend/dist/)"
        echo "  npm run lint     # Check for code issues"
    fi
}

main
