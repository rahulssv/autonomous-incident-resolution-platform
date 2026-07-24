#!/bin/sh
# Write a kubeconfig the kubernetes-mcp container can actually use.
#
#   ./scripts/kind-kubeconfig.sh [cluster-name]
#   docker-compose -f docker-compose.yml -f docker-compose.kind.yml up -d
#
# The host kubeconfig points at https://127.0.0.1:<random-port>, which inside a
# container resolves to the container itself. 'kind get kubeconfig --internal'
# emits the in-network address instead (https://<cluster>-control-plane:6443),
# which the API server's TLS cert already covers as a SAN — so certificate
# verification stays on.
#
# The output holds client credentials; it is written under .kube/ which is
# gitignored. Re-run it whenever the cluster is recreated.
set -eu

cluster=${1:-shopfast-local}
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
dest="$repo_root/.kube/airp-kind.yaml"

if ! command -v kind >/dev/null 2>&1; then
    echo "kind is not on PATH." >&2
    exit 1
fi
if ! kind get clusters 2>/dev/null | grep -qx "$cluster"; then
    echo "No kind cluster named '$cluster'. Existing: $(kind get clusters 2>/dev/null | tr '\n' ' ')" >&2
    exit 1
fi

mkdir -p "$repo_root/.kube"
umask 077
kind get kubeconfig --name "$cluster" --internal > "$dest"

echo "Wrote $dest (server: $(grep -m1 'server:' "$dest" | tr -d ' '))"
echo "Set in .env:  AIRP_KUBECONFIG_HOST_PATH=$dest"
