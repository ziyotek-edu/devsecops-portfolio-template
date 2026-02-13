"""
DevSecOps Portfolio Dashboard
=============================
A professional developer portfolio that doubles as a living demonstration
of the DevSecOps pipeline that builds, scans, and deploys it.

GitHub App credentials are stored in Vault. If Vault or GitHub are
unavailable, the app degrades gracefully — static content always renders.

Environment variables:
    STUDENT_NAME        Your full name
    GITHUB_USERNAME     Your GitHub username
    GITHUB_REPO         Repository name (default: container-devsecops-template)
    VAULT_ADDR          Vault server address (default: http://vault.default:8200)
    VAULT_TOKEN         Vault token for authentication
    VAULT_SECRET_PATH   Path to GitHub App credentials in Vault
                        (default: secret/data/github-app)
    APP_VERSION         Set by the CI pipeline (git SHA short)
    ENVIRONMENT         Injected from K8s namespace via Downward API
    POD_NAME            Kubernetes pod name
    POD_NAMESPACE       Kubernetes namespace
    POD_IP              Pod IP address
    NODE_NAME           Kubernetes node name
    PORT                Server port (default: 5000)
    BIO                 Short professional bio
    LINKEDIN_URL        LinkedIn profile URL (optional)
    WEBSITE_URL         Personal website URL (optional)
"""

import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone

# GitHub App auth
import jwt
import requests
from flask import Flask, jsonify, render_template

# Vault client
try:
    import hvac
except ImportError:
    hvac = None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# Identity
STUDENT_NAME = os.environ.get("STUDENT_NAME", "Your Name")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "your-github-username")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "container-devsecops-template")
BIO = os.environ.get("BIO", "DevOps engineer building secure, automated infrastructure.")
LINKEDIN_URL = os.environ.get("LINKEDIN_URL", "")
WEBSITE_URL = os.environ.get("WEBSITE_URL", "")

# Vault
VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://vault.default:8200")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "")
VAULT_SECRET_PATH = os.environ.get("VAULT_SECRET_PATH", "secret/data/github-app")

# Deployment metadata (Kubernetes Downward API)
APP_VERSION = os.environ.get("APP_VERSION", "local")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
POD_NAME = os.environ.get("POD_NAME", socket.gethostname())
POD_NAMESPACE = os.environ.get("POD_NAMESPACE", "unknown")
POD_IP = os.environ.get("POD_IP", "unknown")
NODE_NAME = os.environ.get("NODE_NAME", "unknown")

# GitHub API
GITHUB_API = "https://api.github.com"

# ---------------------------------------------------------------------------
# GitHub App Authentication
# ---------------------------------------------------------------------------


class GitHubAppAuth:
    """
    Authenticates as a GitHub App installation.

    Flow:
    1. Read App ID + private key from Vault
    2. Generate a JWT signed with the private key
    3. Exchange the JWT for an installation access token
    4. Use the token for GitHub API calls

    The installation token expires after 1 hour. We refresh it
    automatically when it's within 5 minutes of expiry.
    """

    def __init__(self):
        self._app_id = None
        self._private_key = None
        self._installation_id = None
        self._token = None
        self._token_expires_at = 0
        self._vault_error = None
        self._github_error = None
        self._initialized = False

    @property
    def available(self):
        return self._token is not None and time.time() < self._token_expires_at

    @property
    def vault_error(self):
        return self._vault_error

    @property
    def github_error(self):
        return self._github_error

    def initialize(self):
        """Load credentials from Vault and obtain an installation token."""
        self._vault_error = None
        self._github_error = None

        # Step 1: Read credentials from Vault
        if not self._load_from_vault():
            return False

        # Step 2: Generate JWT and get installation token
        if not self._get_installation_token():
            return False

        self._initialized = True
        return True

    def get_headers(self):
        """Return Authorization headers for GitHub API calls."""
        if not self.available:
            if not self.initialize():
                return None
        return {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _load_from_vault(self):
        """Read GitHub App credentials from Vault."""
        if hvac is None:
            self._vault_error = "hvac library not installed"
            return False

        if not VAULT_TOKEN:
            self._vault_error = "VAULT_TOKEN not set"
            return False

        try:
            client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
            if not client.is_authenticated():
                self._vault_error = "Vault authentication failed"
                return False

            # Read from KV v2
            secret = client.secrets.kv.v2.read_secret_version(
                path="github-app",
                mount_point="secret",
            )
            data = secret["data"]["data"]

            self._app_id = data.get("app_id")
            self._private_key = data.get("private_key")
            self._installation_id = data.get("installation_id")

            if not all([self._app_id, self._private_key, self._installation_id]):
                self._vault_error = "Missing fields in Vault secret (need app_id, private_key, installation_id)"
                return False

            return True

        except hvac.exceptions.VaultError as exc:
            self._vault_error = f"Vault error: {exc}"
            return False
        except Exception as exc:
            self._vault_error = f"Unexpected error reading Vault: {exc}"
            return False

    def _generate_jwt(self):
        """Generate a JWT signed with the GitHub App private key."""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # issued at (60s drift allowance)
            "exp": now + (10 * 60),  # expires in 10 minutes
            "iss": str(self._app_id),
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def _get_installation_token(self):
        """Exchange the JWT for an installation access token."""
        try:
            encoded_jwt = self._generate_jwt()
            resp = requests.post(
                f"{GITHUB_API}/app/installations/{self._installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {encoded_jwt}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10,
            )
            if resp.status_code != 201:
                self._github_error = f"GitHub token exchange failed: {resp.status_code} {resp.text[:200]}"
                return False

            data = resp.json()
            self._token = data["token"]
            # Parse expiry — GitHub returns ISO 8601
            expires_str = data.get("expires_at", "")
            if expires_str:
                expires_dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                # Refresh 5 minutes early
                self._token_expires_at = expires_dt.timestamp() - 300
            else:
                # Fallback: assume 55 minutes
                self._token_expires_at = time.time() + 3300

            return True

        except requests.RequestException as exc:
            self._github_error = f"GitHub API unreachable: {exc}"
            return False
        except Exception as exc:
            self._github_error = f"Token exchange error: {exc}"
            return False


# Singleton auth instance
github_auth = GitHubAppAuth()

# ---------------------------------------------------------------------------
# GitHub API Helpers (all fail gracefully)
# ---------------------------------------------------------------------------


def _github_get(path, params=None):
    """Make an authenticated GET request to the GitHub API. Returns None on failure."""
    headers = github_auth.get_headers()
    if headers is None:
        return None
    try:
        resp = requests.get(
            f"{GITHUB_API}{path}",
            headers=headers,
            params=params or {},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        app.logger.warning("GitHub API %s returned %s", path, resp.status_code)
        return None
    except requests.RequestException as exc:
        app.logger.warning("GitHub API request failed: %s", exc)
        return None


def get_user_profile():
    """Fetch the authenticated GitHub user's profile (avatar, bio, etc.)."""
    data = _github_get(f"/users/{GITHUB_USERNAME}")
    if data is None:
        return None
    return {
        "avatar_url": data.get("avatar_url", ""),
        "name": data.get("name", STUDENT_NAME),
        "bio": data.get("bio", ""),
        "public_repos": data.get("public_repos", 0),
        "followers": data.get("followers", 0),
        "html_url": data.get("html_url", f"https://github.com/{GITHUB_USERNAME}"),
    }


def get_recent_commits(limit=5):
    """Fetch recent commits to the portfolio repo."""
    data = _github_get(
        f"/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/commits",
        params={"per_page": limit},
    )
    if data is None:
        return None
    commits = []
    for c in data[:limit]:
        commits.append({
            "sha": c["sha"][:7],
            "message": c["commit"]["message"].split("\n")[0][:80],
            "author": c["commit"]["author"]["name"],
            "date": c["commit"]["author"]["date"],
            "url": c["html_url"],
        })
    return commits


def get_workflow_runs(limit=5):
    """Fetch recent GitHub Actions workflow runs."""
    data = _github_get(
        f"/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/actions/runs",
        params={"per_page": limit},
    )
    if data is None:
        return None
    runs = []
    for r in data.get("workflow_runs", [])[:limit]:
        runs.append({
            "id": r["id"],
            "name": r["name"],
            "status": r["status"],
            "conclusion": r.get("conclusion", "in_progress"),
            "branch": r["head_branch"],
            "sha": r["head_sha"][:7],
            "created_at": r["created_at"],
            "url": r["html_url"],
        })
    return runs


def get_packages():
    """Fetch container packages from GHCR for this user."""
    data = _github_get(
        f"/users/{GITHUB_USERNAME}/packages",
        params={"package_type": "container"},
    )
    if data is None:
        return None
    packages = []
    for p in data[:5]:
        packages.append({
            "name": p["name"],
            "url": p.get("html_url", ""),
            "visibility": p.get("visibility", "unknown"),
            "created_at": p.get("created_at", ""),
        })
    return packages


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def home():
    """Landing page — the professional business card."""
    profile = get_user_profile()

    return render_template(
        "index.html",
        student_name=STUDENT_NAME,
        github_username=GITHUB_USERNAME,
        bio=BIO,
        linkedin_url=LINKEDIN_URL,
        website_url=WEBSITE_URL,
        app_version=APP_VERSION,
        environment=ENVIRONMENT,
        profile=profile,
    )


@app.route("/dashboard")
def dashboard():
    """Pipeline dashboard — live data from GitHub + deployment metadata."""
    profile = get_user_profile()
    commits = get_recent_commits()
    workflow_runs = get_workflow_runs()
    packages = get_packages()

    # Connection status for the dashboard
    integrations = {
        "vault": {
            "status": "connected" if github_auth._initialized and not github_auth.vault_error else "disconnected",
            "error": github_auth.vault_error,
        },
        "github": {
            "status": "connected" if github_auth.available else "disconnected",
            "error": github_auth.github_error,
        },
    }

    return render_template(
        "dashboard.html",
        student_name=STUDENT_NAME,
        github_username=GITHUB_USERNAME,
        github_repo=GITHUB_REPO,
        bio=BIO,
        app_version=APP_VERSION,
        environment=ENVIRONMENT,
        pod_name=POD_NAME,
        pod_namespace=POD_NAMESPACE,
        pod_ip=POD_IP,
        node_name=NODE_NAME,
        profile=profile,
        commits=commits,
        workflow_runs=workflow_runs,
        packages=packages,
        integrations=integrations,
    )


@app.route("/api/status")
def api_status():
    """
    JSON status endpoint — used by integration tests in the CI pipeline.

    Returns connectivity status for all integrations and deployment metadata.
    """
    return jsonify({
        "status": "healthy",
        "version": APP_VERSION,
        "environment": ENVIRONMENT,
        "student": {
            "name": STUDENT_NAME,
            "github_username": GITHUB_USERNAME,
        },
        "deployment": {
            "pod_name": POD_NAME,
            "pod_namespace": POD_NAMESPACE,
            "pod_ip": POD_IP,
            "node_name": NODE_NAME,
            "hostname": socket.gethostname(),
        },
        "integrations": {
            "vault": "connected" if github_auth._initialized and not github_auth.vault_error else "disconnected",
            "github_api": "connected" if github_auth.available else "disconnected",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/health")
def health():
    """
    Health check for Kubernetes probes.
    Always returns healthy — the app works without GitHub/Vault.
    """
    return jsonify({"status": "healthy", "version": APP_VERSION})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _try_initial_auth():
    """Attempt GitHub auth at startup (non-blocking)."""
    if github_auth.initialize():
        app.logger.info("GitHub App authentication successful")
    else:
        app.logger.warning(
            "GitHub App auth unavailable — dashboard will show static content. "
            "Vault: %s | GitHub: %s",
            github_auth.vault_error or "ok",
            github_auth.github_error or "ok",
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print("╔══════════════════════════════════════════════════╗")
    print("║  DevSecOps Portfolio Dashboard                   ║")
    print(f"║  Student: {STUDENT_NAME:<39s} ║")
    print(f"║  Version: {APP_VERSION:<39s} ║")
    print(f"║  Port:    {str(port):<39s} ║")
    print("╚══════════════════════════════════════════════════╝")

    # Try auth in background so startup isn't blocked by Vault/GitHub
    auth_thread = threading.Thread(target=_try_initial_auth, daemon=True)
    auth_thread.start()

    app.run(host="0.0.0.0", port=port)
