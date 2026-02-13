# DevSecOps Portfolio

A professional developer portfolio deployed through a complete DevSecOps pipeline. Every commit is linted, scanned for vulnerabilities, built into a container, validated against Kubernetes schemas, and integration tested — before it merges. Deployment happens automatically via GitOps.

This project demonstrates end-to-end ownership of a production deployment pipeline, from code quality to container security to Kubernetes orchestration.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          GitHub Actions CI/CD                           │
│                                                                         │
│  PR opened                                                              │
│    │                                                                    │
│    ├─► Code Quality ──► Dockerfile Scan ──► Build ──► Container Scan    │
│    │   (ruff, bandit)   (trivy, hadolint)             (trivy)           │
│    │                                                                    │
│    ├─► K8s Validation (kubeconform)                                     │
│    │                                                                    │
│    └─► Integration Test (health checks, API verification)               │
│                                                                         │
│  Merge to main                                                          │
│    │                                                                    │
│    ├─► Push to GHCR (tagged with git SHA)                               │
│    └─► Update k8s manifests with new image tag                          │
│                                                                         │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              ArgoCD                                     │
│                                                                         │
│  Watches repo ──► Detects manifest change ──► Syncs to Kubernetes       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Kubernetes (kind)                             │
│                                                                         │
│  ┌────────────┐  ┌──────────────────┐  ┌──────────────┐                 │
│  │   Vault    │  │  Portfolio App   │  │   ArgoCD     │                 │
│  │            │  │                  │  │              │                 │
│  │ GitHub App │◄─┤ Flask dashboard  │  │ GitOps       │                 │
│  │ credentials│  │ /dashboard       │  │ controller   │                 │
│  └────────────┘  │ /api/status      │  └──────────────┘                 │
│                  └──────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Pipeline Stages

| Stage | Tool | Purpose |
|-------|------|---------|
| Code Lint | [ruff](https://github.com/astral-sh/ruff) | Python linting and formatting |
| SAST | [bandit](https://github.com/PyCQA/bandit) | Python security analysis |
| Dockerfile Lint | [hadolint](https://github.com/hadolint/hadolint) | Dockerfile best practices |
| Dockerfile Scan | [Trivy](https://github.com/aquasecurity/trivy) | Dockerfile misconfiguration detection |
| Container Build | Docker BuildKit | Multi-stage build, non-root user |
| Container Scan | [Trivy](https://github.com/aquasecurity/trivy) | CVE scanning (fail on CRITICAL/HIGH) |
| K8s Validation | [kubeconform](https://github.com/yannh/kubeconform) | Kubernetes schema validation |
| Integration Test | curl + assertions | Endpoint health and response verification |
| Deployment | [ArgoCD](https://argo-cd.readthedocs.io/) | GitOps continuous delivery |
| Secrets | [HashiCorp Vault](https://www.vaultproject.io/) | GitHub App credential management |

## Quick Start

### Prerequisites

- Docker
- kind
- kubectl
- Helm
- GitHub account with a [GitHub App](https://github.com/settings/apps/new)

### Bootstrap

```bash
# Clone your fork
git clone https://github.com/<YOUR_USERNAME>/container-devsecops-template.git
cd container-devsecops-template

# Create the local cluster with ArgoCD + Vault
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh

# Store your GitHub App credentials in Vault
export VAULT_TOKEN=root
chmod +x vault/setup.sh
./vault/setup.sh <APP_ID> <INSTALLATION_ID> <PRIVATE_KEY_FILE>

# Edit argocd/application.yaml with your repo URL, then:
kubectl apply -f argocd/application.yaml

# Port-forward
kubectl port-forward -n argocd svc/argocd-server 8080:443 &
kubectl port-forward -n portfolio svc/portfolio-svc 5000:80 &
```

Visit `http://localhost:5000` for your portfolio and `http://localhost:8080` for the ArgoCD dashboard.

### Creating a GitHub App

1. Go to [Settings → Developer settings → GitHub Apps → New GitHub App](https://github.com/settings/apps/new)
2. Set the following:
   - **Name**: `<your-username>-portfolio` (must be unique)
   - **Homepage URL**: `https://github.com/<your-username>`
   - **Webhook**: Uncheck "Active" (not needed)
3. Permissions (Repository):
   - **Actions**: Read-only
   - **Contents**: Read-only
   - **Metadata**: Read-only
4. Click **Create GitHub App**
5. Note the **App ID** from the app settings page
6. Generate a **private key** (downloads a `.pem` file)
7. Click **Install App** → install on your account → select this repository
8. Note the **Installation ID** from the URL: `github.com/settings/installations/<ID>`

## Project Structure

```
container-devsecops-template/
├── .github/workflows/
│   └── ci.yaml              # DevSecOps pipeline
├── app/
│   ├── app.py               # Flask application
│   ├── Dockerfile            # Multi-stage, non-root
│   ├── requirements.txt
│   └── templates/            # Jinja2 templates
├── k8s/
│   ├── base/                 # Shared manifests
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── configmap.yaml
│   └── overlays/
│       └── local/            # Local kind cluster
├── argocd/
│   ├── install-values.yaml   # Helm values for ArgoCD
│   └── application.yaml      # ArgoCD Application
├── vault/
│   └── setup.sh              # Store GitHub App creds
├── scripts/
│   ├── bootstrap.sh          # One-command setup
│   └── teardown.sh           # Cleanup
└── challenges/
    └── fly-deploy/           # Deploy to Fly.io (bonus)
```

## License

MIT
