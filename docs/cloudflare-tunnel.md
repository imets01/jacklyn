# Sharing Jacklyn with friends through Cloudflare Tunnel

This guide puts Jacklyn on a normal link like `https://jacklyn.yourdomain.com` that you can send to friends,
**without opening any port on your router and without exposing your server to the internet.**

## How it works

```
 Friend's browser
      │  https://jacklyn.yourdomain.com
      ▼
 ┌──────────────────────────── Cloudflare ────────────────────────────┐
 │  HTTPS certificate · DDoS / bot protection                         │
 │  Cloudflare Access: "enter the code we emailed you"  ◄── lock #1   │
 │  (only email addresses you listed get past this point)             │
 └─────────────────────────────────┬──────────────────────────────────┘
                                   │  encrypted tunnel
                                   │  (opened OUTWARD by your server)
 ┌──────────── your server ────────▼──────────────────────────────────┐
 │  cloudflared ──► nginx (8080) ──► Jacklyn API ──► database          │
 │                  Jacklyn login: password + 2-step   ◄── lock #2     │
 │                  each person sees only their own data               │
 └────────────────────────────────────────────────────────────────────┘
```

- **No inbound connections.** The `cloudflared` container dials *out* to Cloudflare and keeps that connection
  open; requests come back through it. Your router stays closed, your home IP stays hidden, and port scanners
  find nothing.
- **Two independent locks.** Cloudflare Access stops strangers before they reach your server at all: they'd
  need an inbox on your allow-list. Behind it, Jacklyn's own login (invite-only accounts, Argon2 passwords,
  lockout, optional 2-step codes) protects each account and keeps friends' data apart.
- **Contained.** In Docker the tunnel connector can only talk to nginx. The API and database sit on a separate
  internal network, and every container runs as non-root with a read-only filesystem.
- **The trade-off.** Cloudflare decrypts HTTPS at its edge, so Cloudflare (not the internet) could technically
  see the traffic. That's normal for any site behind Cloudflare. If you don't want any third party in the path,
  use Tailscale instead: friends install an app, but nothing passes through anyone else.

## What you need

- A free **Cloudflare account**.
- A **domain managed by Cloudflare.** Buy one at Cloudflare Registrar (about $10/year), or point an existing
  domain's nameservers to Cloudflare. Quick tunnels on `trycloudflare.com` need no domain, but they can't use
  Access, so don't use them for real data.
- The server running Jacklyn with Docker Compose.

> Cloudflare renames dashboard menus now and then. The steps below use the names at the time of writing; if a
> label differs, look for the equivalent page ("Zero Trust", "Networks → Tunnels", "Access → Applications").

## 1. Claim Jacklyn locally first

Do the first-run setup *before* anything is reachable from outside:

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs backend | grep -A3 "setup token"
```

Open `http://localhost:8080` on the server, or from your PC through an SSH tunnel:
`ssh -L 8080:localhost:8080 you@your-server`. Then enter the setup token and create your admin account.
Turn on **Settings → Two-step verification** while you're there.

## 2. Create the tunnel

1. Open the Cloudflare dashboard, go to **Zero Trust → Networks → Tunnels**, and choose **Create a tunnel**.
2. Pick **Cloudflared** and name it `jacklyn`.
3. On the install screen choose **Docker** and copy the long token (everything after `--token`).
   Don't run their command; Jacklyn's compose file already contains the connector.
4. Put the token in `.env` on the server:

   ```bash
   CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...
   ```

   Treat it like a password: anyone with it can attach a connector to your tunnel.

## 3. Point a hostname at Jacklyn

In the tunnel's **Public Hostname** tab, add:

| Field | Value |
|---|---|
| Subdomain | `jacklyn` |
| Domain | `yourdomain.com` |
| Service type | `HTTP` |
| URL | `frontend:8080` |

`frontend` is the nginx container's name inside Docker, not `localhost`. TLS happens at Cloudflare, so plain
HTTP inside your server is correct.

## 4. Put Cloudflare Access in front (do this before sharing the link)

1. Go to **Zero Trust → Access → Applications → Add an application → Self-hosted**.
2. Set the application domain to `jacklyn.yourdomain.com`.
3. Add a policy named **Friends**, with action **Allow**, and the rule **Include → Emails** listing your address
   and your friends' addresses.
4. Under login methods, keep **One-time PIN**: visitors get a 6-digit code by email, so no extra accounts are
   needed.
5. Session duration: 1 week is a good balance.

From now on, anyone not on the list gets stopped by Cloudflare and never reaches your server.

## 5. Start the tunnel

```bash
docker compose --profile tunnel up -d --build
docker compose logs cloudflared | tail      # look for "Registered tunnel connection"
```

The tunnel shows **Healthy** in the dashboard. Open `https://jacklyn.yourdomain.com`: you'll get the Cloudflare
email-code screen first, then the Jacklyn sign-in.

## 6. Invite a friend

1. Add their email to the Access policy (step 4).
2. In Jacklyn go to **Settings → People → Invite someone**, create the link and send it privately
   (Signal or WhatsApp, not a public group).
3. They open the link, pass the Cloudflare email code, and create their account. Each link works once and
   expires.

They start with an empty portfolio and can only ever see their own data. As admin you can deactivate an account
(which signs them out at once) or create a password-reset link (for a forgotten password or a lost phone).

## Keeping it safe over time

- **Never publish ports.** The tunnel needs none. `JACKLYN_BIND` defaults to `127.0.0.1`; don't set it to
  `0.0.0.0` on a machine that's reachable from outside.
- **Back up the data volume.** It holds the database *and* `secret.key`, which decrypts stored 2FA secrets and
  broker tokens:

  ```bash
  docker run --rm -v jacklyn_jacklyn-data:/data -v "$PWD":/backup alpine \
    tar czf /backup/jacklyn-$(date +%F).tgz -C /data .
  ```

  Keep backups somewhere private: they contain everyone's financial data.
- **Update regularly:**
  `git pull && docker compose --profile tunnel pull && docker compose --profile tunnel up -d --build`.
- **Give it its own VM or LXC** on Proxmox rather than sharing a machine with other services.
- **Locked out?** On the server run
  `docker compose exec backend python -m app.cli reset-link you@example.com` and open the printed path on your
  Jacklyn address.

## Later: a public demo

Run the demo as a **separate instance**, ideally on a separate VM, with its own compose project and volume,
`JACKLYN_SEED_DEMO_DATA=true`, its own hostname, and no Access policy. Never put real data on it, and never
point it at your real database.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `502 Bad Gateway` from Cloudflare | Set the hostname's service URL to `http://frontend:8080`, and check that `docker compose ps` shows `frontend` healthy. |
| Tunnel stays "Inactive" | Check `docker compose logs cloudflared`; usually a missing or mistyped `CLOUDFLARE_TUNNEL_TOKEN`. |
| Signed in but immediately signed out | Open the site over `https://`. Leave `JACKLYN_COOKIE_SECURE=auto` (the default). |
| "Too many attempts" | Wait 15 minutes, or use an admin reset link. |
