# A public demo anyone can open

A second Jacklyn, on the internet, that a recruiter or a curious friend can look at without an account:
one button, straight into a portfolio full of invented data. It is a **separate instance** from the one
holding your money — separate machine, separate database, separate everything.

```
 anyone with the link
      │  https://demo.example.com
      ▼
 Cloudflare ──► cloudflared tunnel (outbound only, no open ports)
      │
      ▼  127.0.0.1:8080 on the public VM
   nginx ──► Jacklyn API ──► SQLite (demo data only)
```

## What demo mode changes

`JACKLYN_DEMO_MODE=true` turns one private instance into a public exhibit:

- **No sign-in wall.** The sign-in page becomes a short pitch and an *Open the demo* button. One click
  creates a normal session for the demo account.
- **No setup token.** On a fresh database the owner account is claimed automatically with a random
  password that is never shown or written down, so nobody can sign in by password either.
- **The app says so.** A banner on every page: the data is invented and resets regularly.
- **`JACKLYN_DEMO_SOURCE_URL`** adds a *Read the code* link, which for a demo aimed at recruiters is
  half the point.

Nothing else is relaxed: the CSRF checks, the Content-Security-Policy, the non-root read-only containers
and the per-user scoping all behave exactly as they do on your private instance.

> **The one rule.** Anyone who opens the demo lands in it as an admin, which means they can import files,
> delete accounts, restore backups — everything. That is fine on invented data and unacceptable on
> anything else. Never set `JACKLYN_DEMO_MODE=true` on an instance that has touched your real statements,
> and never copy your database onto it.

## Setting it up

On the public VM, in the clone (a deploy key per repository; see [home-server.md](home-server.md) if this
is a new machine):

```bash
cd ~/apps/jacklyn
printf '%s\n' \
  'JACKLYN_DEMO_MODE=true' \
  'JACKLYN_DEMO_SOURCE_URL=https://github.com/you/jacklyn' \
  'JACKLYN_BIND=127.0.0.1' > .env
docker compose up -d --build
```

`JACKLYN_BIND=127.0.0.1` keeps the only listener on loopback; cloudflared reaches it from inside the
machine, so nothing is open to your LAN either. Leave `JACKLYN_COOKIE_SECURE` at `auto`: Cloudflare
terminates HTTPS and forwards the proof, so cookies are `Secure` for visitors without breaking a local
`curl`.

If this instance was already started once and printed a setup token, ignore it — the next restart claims
the account for the demo. If someone already completed setup, demo mode signs visitors in as that admin
instead; start from an empty volume (`docker compose down -v`) if you would rather it be the seeded owner.

Check it before anyone else does:

```bash
curl -s localhost:8080/api/auth/session | grep -o '"demo":[a-z]*'
```

That should print `"demo":true`, and `ss -tlnp | grep 8080` should show `127.0.0.1` and nothing else.

## Putting it on a hostname

Follow [cloudflare-tunnel.md](cloudflare-tunnel.md) for the tunnel itself, with two deliberate
differences:

- **No Cloudflare Access policy.** Access is what keeps a friends-only instance private; a demo that asks
  for an email code is a demo nobody opens.
- **A hostname of its own**, e.g. `demo.example.com`, pointing at `http://localhost:8080`.

## Keeping it presentable

Visitors will change things — that is the point — but the next visitor should still find the portfolio
intact. Take one pristine copy, then put it back on a schedule.

Once the demo looks the way you want it:

```bash
cd ~/apps/jacklyn
docker compose stop backend
docker run --rm -v jacklyn_jacklyn-data:/data alpine sh -c 'rm -f /data/jacklyn.db-wal /data/jacklyn.db-shm && cp /data/jacklyn.db /data/demo-pristine.db'
docker compose start backend
```

Write the reset script (adjust the path if your clone is elsewhere):

```bash
sudo install -m 755 /dev/stdin /usr/local/bin/jacklyn-demo-reset <<'SCRIPT'
#!/bin/sh
# Put the pristine demo database back; everything a visitor did is discarded.
set -e
cd /home/ubuntu/apps/jacklyn
docker compose stop backend
docker run --rm -v jacklyn_jacklyn-data:/data alpine sh -c 'rm -f /data/jacklyn.db-wal /data/jacklyn.db-shm && cp /data/demo-pristine.db /data/jacklyn.db && chown 10001:10001 /data/jacklyn.db'
docker compose start backend
SCRIPT
```

Run it once by hand and check the app comes back, then put it on the hour:

```bash
sudo crontab -l 2>/dev/null | { cat; echo '0 * * * * /usr/local/bin/jacklyn-demo-reset'; } | sudo crontab -
```

Hourly is a good default: long enough that nobody is interrupted mid-look, short enough that a wrecked
demo fixes itself before the next person arrives. Market prices still refresh live, so the seeded tickers
move with the real market between resets.

## Living with it

**Updating.** `git pull && docker compose up -d --build`, then take a fresh pristine copy if the update
changed what the demo should show.

**Telling the two apart.** The banner is the quickest check; `docker compose exec backend printenv | grep
DEMO` is the certain one. Run that on your private instance now and then and expect nothing back.

**If the demo ever holds something real**, treat it as published: it was readable by anyone with the link.
