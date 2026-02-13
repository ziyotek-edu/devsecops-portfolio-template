#!/usr/bin/env bash
# =============================================================================
# Vault Setup — Store GitHub App credentials
# =============================================================================
#
# Prerequisites:
#   - Vault is running and unsealed on the kind cluster
#   - You have your GitHub App private key file
#   - You know your App ID and Installation ID
#
# Usage:
#   ./vault/setup.sh <APP_ID> <INSTALLATION_ID> <PATH_TO_PRIVATE_KEY>
#
# Example:
#   ./vault/setup.sh 123456 78901234 ~/Downloads/my-app.2025-02-13.private-key.pem
# =============================================================================

set -euo pipefail

APP_ID="${1:?Usage: $0 <APP_ID> <INSTALLATION_ID> <PATH_TO_PRIVATE_KEY>}"
INSTALLATION_ID="${2:?Usage: $0 <APP_ID> <INSTALLATION_ID> <PATH_TO_PRIVATE_KEY>}"
PRIVATE_KEY_FILE="${3:?Usage: $0 <APP_ID> <INSTALLATION_ID> <PATH_TO_PRIVATE_KEY>}"

if [ ! -f "$PRIVATE_KEY_FILE" ]; then
    echo "Error: Private key file not found: $PRIVATE_KEY_FILE"
    exit 1
fi

echo "╔══════════════════════════════════════════════════╗"
echo "║  Vault Setup — GitHub App Credentials            ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "App ID:          $APP_ID"
echo "Installation ID: $INSTALLATION_ID"
echo "Private Key:     $PRIVATE_KEY_FILE"
echo ""

# Port-forward Vault if not already accessible
if ! curl -sf http://localhost:8200/v1/sys/health > /dev/null 2>&1; then
    echo "Starting Vault port-forward..."
    kubectl port-forward -n default svc/vault 8200:8200 &
    PF_PID=$!
    sleep 2
    trap "kill $PF_PID 2>/dev/null || true" EXIT
fi

# Get Vault root token (stored during bootstrap)
if [ -z "${VAULT_TOKEN:-}" ]; then
    echo ""
    echo "Enter your Vault root token (from bootstrap output):"
    read -rs VAULT_TOKEN
    export VAULT_TOKEN
fi

export VAULT_ADDR="http://localhost:8200"

# Verify Vault is reachable and authenticated
if ! vault status > /dev/null 2>&1; then
    echo "Error: Cannot connect to Vault at $VAULT_ADDR"
    exit 1
fi

echo ""
echo "Vault connection verified ✓"

# Enable KV v2 if not already enabled
vault secrets enable -path=secret kv-v2 2>/dev/null || true

# Read the private key
PRIVATE_KEY=$(cat "$PRIVATE_KEY_FILE")

# Store the GitHub App credentials
vault kv put secret/github-app \
    app_id="$APP_ID" \
    installation_id="$INSTALLATION_ID" \
    private_key="$PRIVATE_KEY"

echo ""
echo "✓ GitHub App credentials stored at secret/github-app"
echo ""

# Verify
echo "Verifying..."
vault kv get -field=app_id secret/github-app > /dev/null
echo "✓ app_id readable"
vault kv get -field=installation_id secret/github-app > /dev/null
echo "✓ installation_id readable"
vault kv get -field=private_key secret/github-app > /dev/null
echo "✓ private_key readable"

echo ""
echo "Done. Your app can now authenticate with GitHub via Vault."

# Create the Kubernetes secret with the Vault token
# so the portfolio app can authenticate with Vault
echo ""
echo "Creating Kubernetes secret with Vault token..."
kubectl create secret generic vault-token \
    --namespace=portfolio \
    --from-literal=token="$VAULT_TOKEN" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "✓ vault-token secret created in portfolio namespace"
echo ""
echo "=== Setup Complete ==="
