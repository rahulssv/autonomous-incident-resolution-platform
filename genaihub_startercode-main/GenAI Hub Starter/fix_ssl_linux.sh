#!/usr/bin/env bash
set -euo pipefail

# Creates a trusted CA bundle for Python requests/OpenSSL usage and persists
# SSL environment variables across shell sessions.
#
# Usage:
#   chmod +x fix_ssl_linux.sh
#   ./fix_ssl_linux.sh

cert_file="$HOME/generated-cert-bundle.pem"
profile_snippet="$HOME/.python-ssl-fix-env.sh"
source_line='[ -f "$HOME/.python-ssl-fix-env.sh" ] && . "$HOME/.python-ssl-fix-env.sh"'

persist_env() {
  local profile="$1"

  if [[ ! -f "$profile" ]]; then
    : > "$profile"
  fi

  if ! grep -Fqx "$source_line" "$profile"; then
    printf '\n%s\n' "$source_line" >> "$profile"
  fi
}

copy_system_bundle() {
  local candidate
  for candidate in \
    /etc/ssl/certs/ca-certificates.crt \
    /etc/pki/tls/certs/ca-bundle.crt \
    /etc/ssl/ca-bundle.pem \
    /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem \
    /etc/ssl/cert.pem; do
    if [[ -r "$candidate" ]]; then
      cp "$candidate" "$cert_file"
      return 0
    fi
  done

  return 1
}

assemble_bundle_from_dirs() {
  local temp_file
  local file_found=false
  temp_file="$(mktemp)"

  cleanup() {
    rm -f "$temp_file"
  }
  trap cleanup RETURN

  : > "$temp_file"

  while IFS= read -r -d '' cert_path; do
    cat "$cert_path" >> "$temp_file"
    printf '\n' >> "$temp_file"
    file_found=true
  done < <(find /etc/ssl/certs /usr/local/share/ca-certificates /etc/pki/ca-trust/source/anchors -type f \( -name '*.crt' -o -name '*.pem' \) -print0 2>/dev/null || true)

  if [[ "$file_found" == true && -s "$temp_file" ]]; then
    mv "$temp_file" "$cert_file"
    trap - RETURN
    return 0
  fi

  return 1
}

if ! copy_system_bundle && ! assemble_bundle_from_dirs; then
  echo "[ERROR] No readable Linux CA bundle or certificate directory was found."
  echo "[HINT] Ensure CA certificates are installed on your system and try again."
  exit 1
fi

cat > "$profile_snippet" <<EOF
export SSL_CERT_FILE="$cert_file"
export REQUESTS_CA_BUNDLE="$cert_file"
EOF

export SSL_CERT_FILE="$cert_file"
export REQUESTS_CA_BUNDLE="$cert_file"

updated_existing_profile=false
for profile in "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" "$HOME/.zshrc"; do
  if [[ -f "$profile" ]]; then
    persist_env "$profile"
    updated_existing_profile=true
  fi
done

if [[ "$updated_existing_profile" == false ]]; then
  persist_env "$HOME/.profile"
fi

echo "[SUCCESS] Certificate bundle created: $cert_file"
echo "[SUCCESS] Environment exports written: $profile_snippet"
echo "[NEXT] Open a new terminal, or run: source \"$profile_snippet\""
