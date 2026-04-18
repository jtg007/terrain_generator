#!/bin/bash
#
# terrain.sh - Smart launcher for Empires Terrain Generator
# Handles venv management, system probing, and provides interactive menus
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

VENV_DIR="venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
REQUIREMENTS_FILE="config/requirements.txt"
OUTPUT_DIR="output"
LAST_VMF="$OUTPUT_DIR/terrain.vmf"

# ═══════════════════════════════════════════════════════════════════════════
# TERMINAL STYLING
# ═══════════════════════════════════════════════════════════════════════════

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
NC='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
INVERT='\033[7m'

BOX_TL='┌'
BOX_TR='┐'
BOX_BL='└'
BOX_BR='┘'
BOX_H='─'
BOX_V='│'

# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL STATE
# ═══════════════════════════════════════════════════════════════════════════

PROTON_PATH=""
SYSTEM_CHECK_PASSED=0
SYSTEM_CHECK_DONE=0

declare -A PYTHON_IMPORTS=(
    ["worldengine"]="worldengine"
    ["Pillow"]="PIL"
    ["numpy"]="numpy"
    ["vmflib"]="vmflib"
    ["PySide6"]="PySide6"
)

# ═══════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

print_box() {
    local title="$1"
    local width=52
    local padding=$(( (width - ${#title}) / 2 ))
    
    echo -e "${CYAN}${BOX_TL}$(printf '%*s' $width '' | tr ' ' "$BOX_H")${BOX_TR}${NC}"
    echo -e "${CYAN}${BOX_V}${NC}${BOLD}${CYAN}$(printf '%*s' $padding '')${title}$(printf '%*s' $((width - padding - ${#title})) '')${NC}${CYAN}${BOX_V}${NC}"
    echo -e "${CYAN}${BOX_BL}$(printf '%*s' $width '' | tr ' ' "$BOX_H")${BOX_BR}${NC}"
}

print_msg() {
    echo -e "${WHITE}$1${NC}"
}

print_error() {
    echo -e "${RED}${BOLD}✗${NC} ${RED}$1${NC}"
}

print_success() {
    echo -e "${GREEN}${BOLD}✓${NC} ${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${BOLD}⚠${NC} ${YELLOW}$1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} ${BLUE}$1${NC}"
}

print_header() {
    echo ""
    print_box "TERRAIN GENERATOR"
    echo ""
    echo -e "${DIM}Empires Mod displacement terrain VMF generator${NC}"
    echo ""
}

ask_question() {
    local prompt="$1"
    local default="$2"
    echo -ne "${CYAN}${prompt}${NC}"
    if [ -n "$default" ]; then
        echo -ne " ${DIM}[$default]${NC}"
    fi
    echo -n ": "
    read -r answer
    echo "$answer"
}

ask_yes_no() {
    local prompt="$1"
    local default="${2:-n}"
    local yn=""
    while true; do
        echo -ne "${CYAN}${prompt}${NC} ${DIM}[${default,,}/${default^^}]${NC}: " >&2
        read -r yn
        yn="${yn:-$default}"
        case "$yn" in
            [Yy]*) echo "yes"; return 0 ;;
            [Nn]*) echo "no"; return 0 ;;
        esac
        echo -e "${YELLOW}Please answer yes or no${NC}" >&2
    done
}

wait_enter() {
    if [ -t 0 ]; then
        echo ""
        echo -ne "${DIM}Press ${CYAN}Enter${DIM} to continue...${NC}"
        read -r
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
# VENV MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

check_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        return 1
    fi
    if [ ! -f "$VENV_PYTHON" ]; then
        return 1
    fi
    if ! "$VENV_PYTHON" --version &>/dev/null; then
        return 1
    fi
    return 0
}

get_venv_python_version() {
    if check_venv; then
        "$VENV_PYTHON" --version 2>/dev/null | sed 's/Python //'
    else
        echo "not found"
    fi
}

setup_venv() {
    echo -e "${DIM}Setting up virtual environment...${NC}"
    echo ""
    
    if [ -d "$VENV_DIR" ]; then
        echo -ne "${YELLOW}Venv exists but may be incomplete. Recreating...${NC} "
        rm -rf "$VENV_DIR"
        echo -e "${GREEN}Done${NC}"
    fi
    
    echo -ne "${WHITE}Creating venv with system Python3...${NC} "
    if python3 -m venv "$VENV_DIR"; then
        echo -e "${GREEN}Done${NC}"
    else
        echo -e "${RED}Failed${NC}"
        return 1
    fi
    
    echo -ne "${WHITE}Upgrading pip...${NC} "
    if "$VENV_PIP" install --upgrade pip &>/dev/null; then
        echo -e "${GREEN}Done${NC}"
    else
        echo -e "${YELLOW}Warning${NC}"
    fi
    
    local pkg_count
    pkg_count=$(grep -cvE '^\s*$|^\s*#' "$REQUIREMENTS_FILE" 2>/dev/null) || pkg_count=5
    echo -ne "${WHITE}Installing dependencies ($pkg_count packages)...${NC} "
    if "$VENV_PIP" install -r "$REQUIREMENTS_FILE" &>/dev/null; then
        echo -e "${GREEN}Done${NC}"
    else
        echo -e "${RED}Failed${NC}"
        return 1
    fi
    
    pkg_count=$("$VENV_PIP" list 2>/dev/null | wc -l)
    echo -e "${GREEN}✓ Setup complete! ($pkg_count packages installed)${NC}"
    echo ""
    
    return 0
}

check_venv_deps() {
    if ! check_venv; then
        return 1
    fi
    
    local required_packages=(
        "worldengine"
        "Pillow"
        "numpy"
        "vmflib"
        "PySide6"
    )
    
    local missing=()
    for pkg in "${required_packages[@]}"; do
        local import_name="${PYTHON_IMPORTS[$pkg]:-$pkg}"
        if ! "$VENV_PYTHON" -c "import ${import_name}" 2>/dev/null; then
            missing+=("$pkg")
        fi
    done
    
    if [ ${#missing[@]} -gt 0 ]; then
        return 1
    fi
    
    return 0
}

# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM PROBE
# ═══════════════════════════════════════════════════════════════════════════

check_python3() {
    if command -v python3 &>/dev/null; then
        local version
        version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")') || return 1
        echo "✓ Python 3 found (v$version)"
        return 0
    else
        echo "✗ Python 3 not found"
        return 1
    fi
}

check_display() {
    if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
        echo "✓ Display available (GUI supported)"
        return 0
    else
        echo "⚠ No display detected (GUI disabled)"
        return 1
    fi
}

find_proton_installations() {
    local proton_paths=()
    
    _find_steam_libraries() {
        local steam_base="$1"
        local libraries=("$steam_base")
        
        local vdf_file="$steam_base/steamapps/libraryfolders.vdf"
        if [ -f "$vdf_file" ]; then
            while IFS= read -r line; do
                if [[ "$line" == *'"path"'* ]]; then
                    local lib_path
                    # Extract the path using bash regex
                    if [[ "$line" =~ \"path\"[[:space:]]*\"([^\"]*)\" ]]; then
                        lib_path="${BASH_REMATCH[1]}"
                        lib_path="${lib_path/~/$HOME}"
                        if [ -d "$lib_path" ]; then
                            libraries+=("$lib_path")
                        fi
                    fi
                fi
            done < "$vdf_file"
        fi
        
        printf '%s\n' "${libraries[@]}"
    }
    
    _check_proton_in_library() {
        local library_path="$1"
        local proton_dir=""
        local proton_name=""
        
        if [ -d "$library_path/steamapps/common" ]; then
            for proton_dir in "$library_path/steamapps/common"/Proton* \
                              "$library_path/steamapps/common"/proton*; do
                if [ -d "$proton_dir" ] && [ -f "$proton_dir/proton" ]; then
                    proton_name=$(basename "$proton_dir")
                    proton_paths+=("$proton_name|$proton_dir|$proton_dir/proton")
                fi
            done
        fi
        
        if [ -d "$library_path/steamapps/compatibilitytools.d" ]; then
            for proton_dir in "$library_path/steamapps/compatibilitytools.d"/*; do
                if [ -d "$proton_dir" ] && [ -f "$proton_dir/proton" ]; then
                    proton_name=$(basename "$proton_dir")
                    if [[ ! " ${proton_paths[*]} " =~ \ ${proton_name}\| ]]; then
                        proton_paths+=("$proton_name|$proton_dir|$proton_dir/proton")
                    fi
                fi
            done
        fi
        
        if [ -d "$library_path/steamapps/compatibility" ]; then
            for proton_dir in "$library_path/steamapps/compatibility"/proton*; do
                if [ -d "$proton_dir" ] && [ -f "$proton_dir/proton" ]; then
                    proton_name=$(basename "$proton_dir" | sed 's/_/ /g')
                    if [[ ! " ${proton_paths[*]} " =~ \ ${proton_name}\| ]]; then
                        proton_paths+=("$proton_name|$proton_dir|$proton_dir/proton")
                    fi
                fi
            done
        fi
    }
    
    _check_system_proton() {
        local system_paths=(
            "/usr/share/steam/compatibilitytools.d"
            "/usr/local/share/steam/compatibilitytools.d"
            "/opt/steam/compatibilitytools.d"
            "$HOME/.local/share/steam/compatibilitytools.d"
            "/usr/share/proton"
            "/usr/local/share/proton"
            "/opt/proton"
        )
        
        for sys_path in "${system_paths[@]}"; do
            if [ -d "$sys_path" ]; then
                for subdir in "$sys_path"/*; do
                    if [ -d "$subdir" ] && [ -f "$subdir/proton" ]; then
                        local proton_name
                        proton_name=$(basename "$subdir")
                        if [[ ! " ${proton_paths[*]} " =~ \ ${proton_name}\| ]]; then
                            proton_paths+=("System: $proton_name|$subdir|$subdir/proton")
                        fi
                    fi
                done
            fi
        done
    }
    
    local steam_base_paths=(
        "$HOME/.steam/steam"
        "$HOME/.steam/steam/steamapps"
        "$HOME/.local/share/Steam"
        "$HOME/.local/share/Steam/steamapps"
        "$HOME/.steam/debian-installation"
        "$HOME/.steam/debian-installation/steamapps"
    )
    
    local all_libraries=()
    for steam_base in "${steam_base_paths[@]}"; do
        if [ -d "$steam_base" ]; then
            local library_root
            library_root=$(dirname "$steam_base") || continue
            if [[ ! " ${all_libraries[*]} " =~ \ ${library_root}\  ]]; then
                all_libraries+=("$library_root")
                while IFS= read -r lib; do
                    if [ -n "$lib" ] && [[ ! " ${all_libraries[*]} " =~ \ ${lib}\  ]]; then
                        all_libraries+=("$lib")
                    fi
                done < <(_find_steam_libraries "$library_root")
            fi
        fi
    done
    
    for library in "${all_libraries[@]}"; do
        _check_proton_in_library "$library"
    done
    
    _check_system_proton
    
    if [ ${#proton_paths[@]} -gt 0 ]; then
        printf '%s\n' "${proton_paths[@]}" | sort -u
    fi
}

check_wine_proton() {
    local proton_list
    proton_list=$(find_proton_installations)
    
    if [ -n "$proton_list" ]; then
        echo "✓ Found Proton installations:"
        echo "$proton_list" | while IFS='|' read -r name path bin; do
            echo "  • $name"
        done
        return 0
    else
        echo "⚠ No Proton found (compile disabled)"
        return 1
    fi
}

select_proton() {
    local proton_list
    proton_list=$(find_proton_installations)
    local options=()
    local index=1
    
    while IFS='|' read -r name path bin; do
        if [ -n "$name" ]; then
            options+=("$name|$path|$bin")
            echo "  [$index] $name"
            ((index++))
        fi
    done <<< "$proton_list"
    
    if [ ${#options[@]} -eq 0 ]; then
        print_error "No Proton installations found!"
        return 1
    fi
    
    echo ""
    local choice
    choice=$(ask_question "Select Proton version" "1")
    
    if [ -z "$choice" ]; then
        choice=1
    fi
    
    local selected_index=$((choice - 1))
    if [ "$selected_index" -ge 0 ] && [ "$selected_index" -lt ${#options[@]} ]; then
        local selected="${options[$selected_index]}"
        PROTON_PATH=$(echo "$selected" | cut -d'|' -f3)
        print_success "Selected: $(echo "$selected" | cut -d'|' -f1)"
        return 0
    else
        print_error "Invalid selection"
        return 1
    fi
}

ensure_proton() {
    if [ -n "$PROTON_PATH" ] && [ -f "$PROTON_PATH" ]; then
        return 0
    fi
    
    local proton_list
    proton_list=$(find_proton_installations)
    if [ -z "$proton_list" ]; then
        print_error "No Proton installations found!"
        print_info "Install Proton via Steam (Settings > Compatibility > Tools)"
        return 1
    fi
    
    echo ""
    print_info "Select Proton version for VBSP compilation:"
    echo ""
    select_proton
    return $?
}

probe_system() {
    if [ $SYSTEM_CHECK_DONE -eq 1 ]; then
        return $SYSTEM_CHECK_PASSED
    fi
    
    echo -e "${DIM}Checking system...${NC}"
    echo ""
    
    check_python3
    local python_ok=$?
    
    check_display
    local display_ok=$?
    
    check_wine_proton
    local proton_ok=$?
    
    echo ""
    
    SYSTEM_CHECK_DONE=1
    
    if [ $python_ok -ne 0 ]; then
        print_error "Python 3 is required but not found!"
        print_info "Install Python 3: sudo apt install python3 python3-venv"
        SYSTEM_CHECK_PASSED=1
        return 1
    fi
    
    SYSTEM_CHECK_PASSED=0
    return 0
}

ensure_venv() {
    if ! check_venv; then
        print_warning "Virtual environment not found or incomplete"
        setup_venv || return 1
    elif ! check_venv_deps; then
        print_warning "Some dependencies are missing"
        local reinstall
        reinstall=$(ask_yes_no "Reinstall dependencies?" "Y")
        if [ "$reinstall" = "yes" ]; then
            setup_venv || return 1
        else
            return 1
        fi
    else
        echo -e "${GREEN}✓${NC} Using existing venv ($(get_venv_python_version))"
    fi
    return 0
}

# ═══════════════════════════════════════════════════════════════════════════
# MENU FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

show_main_menu() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}              ${BOLD}${CYAN}TERRAIN GENERATOR${NC}                           ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    local display_ok=0
    if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
        display_ok=1
    fi
    
    echo -e "  ${WHITE}[1]${NC}  ${BOLD}GUI Mode${NC}        Interactive application"
    [ $display_ok -eq 0 ] && echo -e "                      ${DIM}(display required)${NC}"
    echo -e "  ${WHITE}[2]${NC}  ${BOLD}CLI Mode${NC}        Command-line terrain generation"
    echo -e "  ${WHITE}[3]${NC}  ${BOLD}Compile VMF${NC}     Build BSP from VMF file"
    echo ""
    echo -e "  ${WHITE}[4]${NC}  ${BOLD}Setup/Update${NC}    Reinstall dependencies"
    echo -e "  ${WHITE}[5]${NC}  ${BOLD}Help${NC}           Usage information"
    echo ""
    echo -e "  ${WHITE}[Q]${NC}  ${BOLD}Quit${NC}"
    echo ""
    
    echo -ne "${CYAN}Select option${NC}: "
    read -r choice
    echo ""
    
    case "$choice" in
        1) 
            if [ $display_ok -eq 0 ]; then
                print_error "GUI requires a display. Start a desktop session or use X forwarding."
                wait_enter
                return 0
            fi
            run_gui
            ;;
        2) show_cli_menu ;;
        3) run_compile ;;
        4) run_setup ;;
        5) show_help ;;
        Q|q) 
            echo -e "${DIM}Goodbye!${NC}"
            exit 0
            ;;
        *) 
            print_error "Invalid option: $choice"
            wait_enter
            ;;
    esac
    
    return 0
}

show_cli_menu() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}              ${BOLD}${CYAN}CLI TERRAIN GENERATION${NC}                      ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    echo -e "  Generating terrain with custom options..."
    echo ""
    run_cli
}

show_help() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}              ${BOLD}${CYAN}HELP & USAGE${NC}                                 ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    echo -e "${BOLD}Usage:${NC}"
    echo -e "  ${WHITE}./terrain.sh [OPTIONS]${NC}"
    echo ""
    
    echo -e "${BOLD}Options:${NC}"
    echo -e "  ${WHITE}--gui${NC}                 Launch GUI mode"
    echo -e "  ${WHITE}--cli [ARGS]${NC}           CLI mode (optional args)"
    echo -e "  ${WHITE}--compile [VMF]${NC}        Compile VMF to BSP"
    echo -e "  ${WHITE}--setup${NC}                Reinstall dependencies"
    echo -e "  ${WHITE}--help${NC}                 Show this help"
    echo ""
    
    echo ""
    
    echo -e "${BOLD}CLI Arguments (passed to Python script):${NC}"
    echo -e "  ${WHITE}--seed N${NC}               Random seed for noise"
    echo -e "  ${WHITE}--tiles-x N${NC}            Tiles in X direction"
    echo -e "  ${WHITE}--tiles-y N${NC}            Tiles in Y direction"
    echo -e "  ${WHITE}--skip-erosion${NC}         Skip hydraulic erosion"
    echo -e "  ${WHITE}--export-heightmap${NC}      Save heightmap PNG"
    echo ""
    
    echo -e "${BOLD}CLI Examples:${NC}"
    echo -e "  ${DIM}./terrain.sh --cli${NC}                     Interactive CLI"
    echo -e "  ${DIM}./terrain.sh --cli --seed 42${NC}           Terrain with seed 42"
    echo -e "  ${DIM}./terrain.sh --cli --tiles-x 24 --tiles-y 20${NC}"
    echo ""
    
    echo -e "${BOLD}Requirements:${NC}"
    echo -e "  ${DIM}• Python 3.8+${NC}"
    echo -e "  ${DIM}• Steam with Proton (for compilation)${NC}"
    echo -e "  ${DIM}• X11/Wayland display server (for GUI)${NC}"
    echo ""
    
    wait_enter
}

# ═══════════════════════════════════════════════════════════════════════════
# ACTION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

run_gui() {
    echo -e "${DIM}Launching GUI...${NC}"
    echo ""
    
    if ! probe_system; then
        wait_enter
        return 1
    fi
    
    if ! ensure_venv; then
        wait_enter
        return 1
    fi
    
    echo ""
    echo -e "${GREEN}Starting Terrain Generator GUI...${NC}"
    echo ""
    
    "$VENV_PYTHON" tools/terrain_generator.py
    
    local exit_code=$?
    echo ""
    if [ $exit_code -eq 0 ]; then
        print_success "GUI closed"
    else
        print_error "GUI exited with code $exit_code"
    fi
    
    wait_enter
    return $exit_code
}

run_cli() {
    local extra_args=()
    while [ $# -gt 0 ]; do
        extra_args+=("$1")
        shift
    done
    
    echo -e "${DIM}CLI Terrain Generation${NC}"
    echo ""
    
    if ! probe_system; then
        wait_enter
        return 1
    fi
    
    if ! ensure_venv; then
        wait_enter
        return 1
    fi
    
    echo ""
    
    local cmd=("$VENV_PYTHON" tools/generate_organic_vmf.py)
    
    echo -e "${GREEN}Generating terrain with custom options...${NC}"
    
    if [ ${#extra_args[@]} -gt 0 ]; then
        cmd+=("${extra_args[@]}")
    fi
    
    echo -e "${DIM}Command: ${WHITE}${cmd[*]}${NC}"
    echo ""
    
    "${cmd[@]}"
    
    local exit_code=$?
    echo ""
    if [ $exit_code -eq 0 ]; then
        print_success "Terrain generated successfully!"
        print_info "Output: $OUTPUT_DIR/terrain.vmf"
    else
        print_error "Generation failed with code $exit_code"
    fi
    
    wait_enter
    return $exit_code
}

run_compile() {
    echo -e "${DIM}Compiling VMF to BSP${NC}"
    echo ""
    
    if ! probe_system; then
        wait_enter
        return 1
    fi
    
    if ! ensure_venv; then
        wait_enter
        return 1
    fi
    
    # Select Proton
    if ! ensure_proton; then
        print_info "Compile requires Proton. Install via Steam."
        wait_enter
        return 1
    fi
    
    # Find VMF to compile
    local vmf_file="$LAST_VMF"
    
    if [ ! -f "$vmf_file" ]; then
        echo -ne "${YELLOW}No default VMF found. Enter path: ${NC}"
        read -r vmf_file
    else
        echo -e "Found last VMF: ${WHITE}$vmf_file${NC}"
        local use_default
        use_default=$(ask_yes_no "Use this file?" "Y")
        if [ "$use_default" != "yes" ]; then
            echo -ne "${CYAN}Enter VMF path: ${NC}"
            read -r vmf_file
        fi
    fi
    
    if [ ! -f "$vmf_file" ]; then
        print_error "VMF file not found: $vmf_file"
        wait_enter
        return 1
    fi
    
    echo ""
    echo -e "${GREEN}Compiling ${WHITE}$vmf_file${NC}${GREEN} with Proton...${NC}"
    echo ""
    
    # Set environment for Proton
    export PROTON_PATH
    export STEAM_COMPAT_DATA_PATH="${HOME}/.steam/steam"
    
    "$VENV_PYTHON" tools/compile_vmf.py "$vmf_file"
    
    local exit_code=$?
    echo ""
    if [ $exit_code -eq 0 ]; then
        print_success "Compilation successful!"
    else
        print_error "Compilation failed with code $exit_code"
    fi
    
    wait_enter
    return $exit_code
}

run_setup() {
    echo -e "${DIM}Setup / Update${NC}"
    echo ""
    
    if ! probe_system; then
        wait_enter
        return 1
    fi
    
    if check_venv; then
        local reinstall
        reinstall=$(ask_yes_no "Recreate virtual environment?" "N")
        if [ "$reinstall" != "yes" ]; then
            echo "Keeping existing venv."
            wait_enter
            return 0
        fi
    fi
    
    setup_venv
    local exit_code=$?
    
    wait_enter
    return $exit_code
}

# ═══════════════════════════════════════════════════════════════════════════
# ARGUMENT PARSING
# ═══════════════════════════════════════════════════════════════════════════

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --gui)
                probe_system || exit 1
                ensure_venv || exit 1
                run_gui
                exit $?
                ;;
            --cli)
                shift
                probe_system || exit 1
                ensure_venv || exit 1
                local preset=""
                if [ $# -gt 0 ] && [[ ! "$1" =~ ^-- ]]; then
                    preset="$1"
                    shift
                fi
                run_cli "$preset" "$@"
                exit $?
                ;;
            --compile)
                shift
                probe_system || exit 1
                ensure_venv || exit 1
                if [ $# -gt 0 ]; then
                    LAST_VMF="$1"
                fi
                run_compile
                exit $?
                ;;
            --setup)
                probe_system || exit 1
                run_setup
                exit $?
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
        shift
    done
}

# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

main() {
    if [ $# -gt 0 ]; then
        parse_args "$@"
        exit $?
    fi
    
    print_header
    
    probe_system
    local probe_ok=$?
    
    if [ $probe_ok -eq 0 ]; then
        ensure_venv || true
    fi
    
    wait_enter
    
    while true; do
        clear
        print_header
        probe_system &>/dev/null
        ensure_venv &>/dev/null || true
        echo ""
        show_main_menu
    done
}

main "$@"
