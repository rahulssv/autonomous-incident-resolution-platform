#!/usr/bin/env bash
# fix_ssl_macos.sh
# Exports macOS system keychain certificates to a PEM bundle and configures
# Python (requests / httpx / OpenAI SDK) to trust them.
# Run once, then open a new terminal (or `source ~/.python-ssl-fix-env.sh`).

set -euo pipefail

cert_file="$HOME/generated-cert-bundle.pem"
profile_snippet="$HOME/.python-ssl-fix-env.sh"
source_line='[ -f "$HOME/.python-ssl-fix-env.sh" ] && . "$HOME/.python-ssl-fix-env.sh"'
keychains=(
  "/System/Library/Keychains/SystemRootCertificates.keychain"
  "/Library/Keychains/System.keychain"
)

persist_env() {
  local profile="$1"

  if [[ ! -f "$profile" ]]; then
    : > "$profile"
  fi

  if ! grep -Fqx "$source_line" "$profile"; then
    printf '\n%s\n' "$source_line" >> "$profile"
  fi
}

if ! command -v security >/dev/null 2>&1; then
  echo "The 'security' command is required to export certificates on macOS."
  exit 1
fi

temp_file="$(mktemp)"
cleanup() {
  rm -f "$temp_file"
}
trap cleanup EXIT

found_keychain=false
: > "$temp_file"

for keychain in "${keychains[@]}"; do
  if [[ -r "$keychain" ]]; then
    security find-certificate -a -p "$keychain" >> "$temp_file"
    printf '\n' >> "$temp_file"
    found_keychain=true
  fi
done

if [[ "$found_keychain" == false || ! -s "$temp_file" ]]; then
  echo "No readable system keychains with certificates were found."
  exit 1
fi

mv "$temp_file" "$cert_file"
trap - EXIT

cat > "$profile_snippet" <<EOF
export SSL_CERT_FILE="$cert_file"
export REQUESTS_CA_BUNDLE="$cert_file"
EOF

export SSL_CERT_FILE="$cert_file"
export REQUESTS_CA_BUNDLE="$cert_file"

updated_existing_profile=false
for profile in "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile"; do
  if [[ -f "$profile" ]]; then
    persist_env "$profile"
    updated_existing_profile=true
  fi
done

if [[ "$updated_existing_profile" == false ]]; then
  persist_env "$HOME/.profile"
fi

echo ""
echo "Certificate bundle created at:  $cert_file"
echo "Environment exports written to: $profile_snippet"
echo ""
echo "Open a new terminal, or run:"
echo "  source \"$profile_snippet\""
