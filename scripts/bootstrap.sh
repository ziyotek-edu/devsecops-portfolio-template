#!/usr/bin/env bash
# =============================================================================
# Bootstrap — kind + ArgoCD + Vault in one shot
# =============================================================================
#
# This script creates a local Kubernetes cluster with everything you need:
#   1. kind cluster
#   2. ArgoCD (via Helm)
#   3. Vault in dev mode (via Helm) — simpler than Week 5's sealed Vault
#
# After this script runs, you need to:
#   1. Create your GitHub App and download the private key
#   2. Run vault/setup.sh to store credentials
#   3. Edit argocd/application.yaml with your repo URL
#   4. Apply the ArgoCD Application
#
# Usage:
#   ./scripts/bootstrap.sh
# =============================================================================

set -euo pipefail

CLUSTER_NAME="portfolio"

echo "╔══════════════════════════════════════════════════╗"
echo "║  DevSecOps Portfolio — Local Bootstrap            ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Create kind cluster ──────────────────────────────────────────────

if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "Cluster '${CLUSTER_NAME}' already exists. Reusing."
else
    echo "Creating kind cluster '${CLUSTER_NAME}'..."
    kind create cluster --name "$CLUSTER_NAME" --wait 60s
fi

kubectl cluster-info --context "kind-${CLUSTER_NAME}"
echo ""
echo "✓ Cluster ready"
echo ""

# ── Step 2: Install ArgoCD ───────────────────────────────────────────────────

echo "Installing ArgoCD..."
helm repo add argo https://argoproj.github.io/argo-helm 2>/dev/null || true
helm repo update argo

helm upgrade --install argocd argo/argo-cd \
    --namespace argocd \
    --create-namespace \
    -f argocd/install-values.yaml \
    --wait --timeout 5m

echo ""
echo "✓ ArgoCD installed"

# Get admin password
ARGO_PASS=$(kubectl get secret argocd-initial-admin-secret -n argocd \
    -o jsonpath='{.data.password}' | base64 -d)
echo ""
echo "  ArgoCD UI:   http://localhost:8080  (after port-forward)"
echo "  Username:    admin"
echo "  Password:    ${ARGO_PASS}"
echo ""

# ── Step 3: Install Vault (dev mode for simplicity) ─────────────────────────

echo "Installing Vault (dev mode)..."
helm repo add hashicorp https://helm.releases.hashicorp.com 2>/dev/null || true
helm repo update hashicorp

# Dev mode Vault — auto-unsealed, root token is "root"
# Good enough for local development. Students already learned
# sealed Vault in Week 5.
helm upgrade --install vault hashicorp/vault \
    --set "server.dev.enabled=true" \
    --set "server.dev.devRootToken=root" \
    --set "injector.enabled=false" \
    --set "server.resources.requests.memory=64Mi" \
    --set "server.resources.requests.cpu=50m" \
    --set "server.resources.limits.memory=256Mi" \
    --set "server.resources.limits.cpu=200m" \
    --wait --timeout 3m

echo ""
echo "✓ Vault installed (dev mode)"
echo ""
echo "  Vault:       http://localhost:8200  (after port-forward)"
echo "  Root Token:  root"
echo ""

# ── Step 4: Create the portfolio namespace ───────────────────────────────────

kubectl create namespace portfolio --dry-run=client -o yaml | kubectl apply -f -

# ── Done ─────────────────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════"
echo ""
echo "Bootstrap complete. Next steps:"
echo ""
echo "  1. Create a GitHub App:"
echo "     https://github.com/settings/apps/new"
echo ""
echo "  2. Store credentials in Vault:"
echo "     export VAULT_TOKEN=root"
echo "     ./vault/setup.sh <APP_ID> <INSTALL_ID> <KEY_FILE>"
echo ""
echo "  3. Edit argocd/application.yaml with your repo URL"
echo ""
echo "  4. Apply the ArgoCD Application:"
echo "     kubectl apply -f argocd/application.yaml"
echo ""
echo "  5. Port-forward to see your app:"
echo "     kubectl port-forward -n argocd svc/argocd-server 8080:443 &"
echo "     kubectl port-forward -n portfolio svc/portfolio-svc 5000:80 &"
echo ""
echo "═══════════════════════════════════════════════════"
