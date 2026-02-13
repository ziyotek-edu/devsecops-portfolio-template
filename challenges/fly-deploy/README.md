# Challenge: Deploy to Fly.io

You have a working portfolio running on Kubernetes locally. Nobody can see it. Fix that.

The goal: deploy the **same container image** to [Fly.io](https://fly.io) so you have a public URL worth putting on a resume. No cluster required — just your Dockerfile and a few environment variables.

## What You Already Know

Your app was designed to degrade gracefully. No Vault? No GitHub API? Static content still renders. That's the property you're going to exploit here — Fly.io has no Vault server, and that's fine.

## Prerequisites

- A Fly.io account (free tier covers this)
- `flyctl` installed ([docs](https://fly.io/docs/flyctl/install/))
- Your GitHub App credentials (the same App ID, Installation ID, and private key from the Vault setup)

## Step 1: Create a Fly App

Authenticate with `flyctl auth login`, then create a new app. Fly will want to pick a region — choose one close to you.

You don't need Fly's builders. You already have a Dockerfile at `app/Dockerfile` that produces a working image. Tell Fly to use it.

## Step 2: Write a `fly.toml`

Create a `fly.toml` either here in `challenges/fly-deploy/` or in the project root. The key things it needs:

- **Internal port**: your app listens on `5000` (check `app/Dockerfile:34` if you forgot)
- **Health check**: `GET /health` — the route already exists (`app/app.py:434`)
- **Dockerfile path**: point it at `app/Dockerfile`
- **Build context**: the Dockerfile copies from relative paths (`COPY app.py .`, `COPY templates/ templates/`), so your build context needs to be `app/`, not the repo root

Think about what that means for where you run `fly deploy` from, or how you set `[build]` in your `fly.toml`.

## Step 3: Handle Secrets Without Vault

On Kubernetes, your app reads GitHub credentials from Vault via the `hvac` library (`app/app.py:147-185`). On Fly.io, there's no Vault.

But look at `_load_from_vault()` — if Vault fails, `initialize()` returns `False` and the app runs without GitHub data. You have two choices:

**Option A: Skip it.** Deploy now. Your portfolio renders with static content. The dashboard shows "disconnected" for Vault and GitHub. This is a valid MVP — ship it and iterate.

**Option B: Add an env-var fallback.** Modify `_load_from_vault()` to check environment variables before reaching for Vault. Something like this inserted at the top of the method:

```python
def _load_from_vault(self):
    """Read GitHub App credentials from Vault, falling back to env vars."""
    # --- env-var fallback (works on Fly.io, CI, etc.) ---
    env_app_id = os.environ.get("GITHUB_APP_ID")
    env_key = os.environ.get("GITHUB_PRIVATE_KEY", "").replace("\\n", "\n")
    env_install_id = os.environ.get("GITHUB_INSTALLATION_ID")

    if all([env_app_id, env_key, env_install_id]):
        self._app_id = env_app_id
        self._private_key = env_key
        self._installation_id = env_install_id
        app.logger.info("Loaded GitHub credentials from environment variables")
        return True

    # --- original Vault path below (unchanged) ---
    if hvac is None:
        ...
```

Then set the secrets on Fly:

```
fly secrets set GITHUB_APP_ID=<id> GITHUB_INSTALLATION_ID=<id>
fly secrets set GITHUB_PRIVATE_KEY="$(cat path/to/private-key.pem)"
```

The `replace("\\n", "\n")` handles Fly's secret storage encoding PEM newlines as literal `\n`. Test locally with `export` first if you're not sure.

## Step 4: Set Your Identity

Your app reads `STUDENT_NAME`, `GITHUB_USERNAME`, `BIO`, and optional `LINKEDIN_URL` / `WEBSITE_URL` from environment variables. Set them:

```
fly secrets set STUDENT_NAME="..." GITHUB_USERNAME="..." BIO="..."
```

These aren't actually secrets, but `fly secrets set` is the simplest way to inject env vars into a Fly machine. If you want to be pedantic, use `[env]` in `fly.toml` for non-sensitive values.

## Step 5: Deploy

```
fly deploy
```

Watch the build logs. Fly pulls your Dockerfile, builds it remotely, and deploys the image. When it's healthy, you get a URL: `https://<your-app>.fly.dev`.

Hit `/health`, then `/`, then `/dashboard`. Verify what's working.

## Step 6: Kubernetes Metadata on Fly.io

Your app reads `POD_NAME`, `POD_NAMESPACE`, `POD_IP`, and `NODE_NAME` from Kubernetes Downward API environment variables. Those don't exist on Fly.io — check `app/app.py:68-74` to see what defaults they fall back to.

Fly provides its own runtime metadata: `FLY_REGION`, `FLY_ALLOC_ID`, `FLY_APP_NAME`, and others. These are injected automatically — you don't set them.

If the "unknown" defaults bother you on the dashboard, you could map Fly's variables onto the existing ones in your `fly.toml`:

```toml
[env]
  ENVIRONMENT = "fly"
```

Or modify `app.py` to prefer Fly's variables. Up to you — the dashboard already handles missing values.

## What You Proved

By deploying the same image to a completely different platform, you demonstrated that your container is actually portable. It doesn't depend on Kubernetes. It doesn't depend on Vault. The image is the artifact, and it runs anywhere that speaks OCI containers. That's the point.

## Stretch Goals

Things to try if you want to keep going:

- **Custom domain**: Point a real domain at your Fly app with `fly certs add`. HTTPS is automatic. Put *that* URL on your resume.
- **Deploy on merge**: Add a GitHub Actions workflow that runs `fly deploy` when a PR merges to `main`. You already have CI — now close the loop with CD to a public endpoint. Fly provides a `superfly/flyctl-actions` action to help.
- **Fly Postgres**: Fly offers managed Postgres. If you extend your portfolio to store visitor analytics or deployment history, you could wire up a database without touching Kubernetes. `fly postgres create` gets you started.
- **Multi-region**: Fly can run your app in multiple regions. Try `fly scale count 2 --region ord,sea` and think about what that means compared to Kubernetes replicas.
