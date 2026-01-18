#!/bin/bash
#
# install_repository.sh - Clone or update LeLamp repository
#
# Usage:
#   ./install_repository.sh                    # Interactive
#   ./install_repository.sh -y                 # Clone without prompting
#   ./install_repository.sh --update           # Update existing repo
#   ./install_repository.sh --branch <BRANCH>  # Specify branch
#   ./install_repository.sh --dir <PATH>       # Specify target directory
#

set -e

# Get script directory and source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Script-specific variables
ACTION="install"
REPO_URL="https://github.com/humancomputerlab/boxbots_lelampruntime.git"
BRANCH="12Vruntime-agent"
TARGET_DIR="$HOME/lelamp"

show_help() {
    echo "LeLamp Repository Setup"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --update             Update existing repository"
    echo "  --branch <BRANCH>    Specify branch (default: $BRANCH)"
    echo "  --dir <PATH>         Target directory (default: $TARGET_DIR)"
    echo "  --fresh              Remove existing and clone fresh"
    show_help_footer
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --update)
                ACTION="update"
                shift
                ;;
            --branch)
                BRANCH="$2"
                shift 2
                ;;
            --dir)
                TARGET_DIR="$2"
                shift 2
                ;;
            --fresh)
                ACTION="fresh"
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

# Clone repository
clone_repo() {
    print_header "Cloning LeLamp Repository"

    print_info "Repository: $REPO_URL"
    print_info "Branch: $BRANCH"
    print_info "Target: $TARGET_DIR"
    echo ""

    if [ -d "$TARGET_DIR" ]; then
        print_warning "Directory $TARGET_DIR already exists"

        if [ "$SKIP_CONFIRM" != "true" ]; then
            echo "Options:"
            echo "  1) Remove and clone fresh"
            echo "  2) Update existing (git pull)"
            echo "  3) Cancel"
            read -p "Enter choice [1-3]: " choice < "$INPUT_DEVICE"

            case $choice in
                1)
                    print_info "Removing existing directory..."
                    rm -rf "$TARGET_DIR"
                    ;;
                2)
                    update_repo
                    return
                    ;;
                3)
                    print_info "Cancelled"
                    return 0
                    ;;
                *)
                    print_error "Invalid choice"
                    return 1
                    ;;
            esac
        else
            print_info "Using existing directory"
            update_repo
            return
        fi
    fi

    print_info "Cloning repository..."
    git clone -b "$BRANCH" "$REPO_URL" "$TARGET_DIR"

    print_success "Repository cloned to $TARGET_DIR"

    # Create config.yaml from example if it doesn't exist
    if [ ! -f "$TARGET_DIR/config.yaml" ]; then
        if [ -f "$TARGET_DIR/system/config.example.yaml" ]; then
            print_info "Creating config.yaml from example template..."
            cp "$TARGET_DIR/system/config.example.yaml" "$TARGET_DIR/config.yaml"
            print_success "config.yaml created"
        else
            print_warning "config.example.yaml not found - config.yaml will be created on first run"
        fi
    fi
}

# Update existing repository
update_repo() {
    print_header "Updating LeLamp Repository"

    if [ ! -d "$TARGET_DIR" ]; then
        print_error "Repository not found at $TARGET_DIR"
        print_info "Run without --update to clone"
        return 1
    fi

    cd "$TARGET_DIR"

    print_info "Pulling latest changes..."
    git pull

    print_success "Repository updated"

    # Create config.yaml from example if it doesn't exist
    if [ ! -f "$TARGET_DIR/config.yaml" ]; then
        if [ -f "$TARGET_DIR/system/config.example.yaml" ]; then
            print_info "Creating config.yaml from example template..."
            cp "$TARGET_DIR/system/config.example.yaml" "$TARGET_DIR/config.yaml"
            print_success "config.yaml created"
        fi
    fi
}

# Fresh clone (remove and re-clone)
fresh_clone() {
    print_header "Fresh Clone of LeLamp Repository"

    if [ -d "$TARGET_DIR" ]; then
        if [ "$SKIP_CONFIRM" != "true" ]; then
            if ! ask_yes_no "This will delete $TARGET_DIR and clone fresh. Continue?"; then
                print_info "Cancelled"
                return 0
            fi
        fi

        print_info "Removing existing directory..."
        rm -rf "$TARGET_DIR"
    fi

    clone_repo
}

# Main function
main() {
    init_script
    parse_args "$@"

    case $ACTION in
        install)
            clone_repo
            ;;
        update)
            update_repo
            ;;
        fresh)
            fresh_clone
            ;;
    esac
}

# Run main function
main "$@"
