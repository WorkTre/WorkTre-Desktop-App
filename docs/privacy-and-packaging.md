# WorkTre App — Privacy & packaging (one-pager)

**For sales, security reviews, and customer onboarding.**  
Product name on the device: **WorkTre App** (not “agent” or “monitor”).

---

## What we capture

| Captured | Default | Notes |
|---|---|---|
| Attendance login / logout | On | Required for time & pay |
| Shift timer & breaks | On | Matches company shift rules |
| Idle / away time | On | When the employee steps away |
| Activity heartbeat (~5 min) | On | Powers “online / idle / stale” on the dashboard |
| Screenshots | **Company-controlled** | Only if the employer enables them for that user. Upload is form-encoded and includes a desk token in the body when the app has one. Captures over 6 MB of base64 are re-encoded as JPEG and downscaled |
| App / URL tracking | **Off** | Not enabled |

Heartbeats may queue offline and sync when the device reconnects, so hours are not silently lost.

---

## Privacy defaults employees can see

1. **First-run notice** — clear explanation of what is recorded; employee acknowledges.
2. **Screenshot consent** — required again if the company turns screenshots on.
3. **Blur on by default** — Gaussian blur before upload (Medium / radius 8). Employee can set Light / Medium / Strong / Off in **Settings**.
4. **Settings shows the truth** — what’s tracked, SSL on/off, last heartbeat, idle state, queued offline heartbeats.
5. **No silent spyware framing** — managers see “WorkTre App online,” not a hidden agent.

---

## What managers see (trust, not surveillance theatre)

On the company dashboard (scoped by role):

- **Online / idle / stale** from the last heartbeat  
- Attendance alerts, capacity, and payroll readiness — **only for their scope**
- Super Admin → all companies · Owner / HR / Finance → own company · Dept managers → their departments · Employees → self only  
- Payroll / money panels only with **View Salaries** (not every manager)

Employees get a self-serve home: my status, leave, “why I’m flagged,” and WorkTre App health.

---

## Security & packaging (Windows)

| Topic | Practice |
|---|---|
| Transport | TLS certificate verification enabled (`VERIFY_SSL = True`) |
| Updates | Signed / checksummed update path (placeholders skipped until set) |
| Build | PyInstaller single-file exe (Windows) |
| Install path for non-IT | Download → run → log in with WorkTre credentials → first heartbeat appears on dashboard within minutes |
| Data store (device) | Local prefs (blur, consent) under app data; Remember me and the screenshot token use Windows DPAPI (current user). No separate “spy” service |
| Screenshot token | Issued after password login. Renewed before expiry. Revoked on logout. Attendance does not stop if the token cannot be refreshed |

**Pilot checklist (copy for the customer)**  
1. Install WorkTre App on 5–10 pilot PCs  
2. Log in as each pilot user  
3. Confirm Settings → What’s tracked matches company policy  
4. Manager opens Dashboard → WorkTre App trust shows online after ~5 minutes  
5. Run Attendance Alerts + payroll close-out for one period  

---

## One-line pitch (privacy)

> WorkTre App records time for correct pay — with blur-by-default screenshots (only if you enable them), no app/URL tracking, and a dashboard status employees can see themselves.

---

## Next integration options

- ~~Slack / Teams: notify manager when high-severity attendance alerts appear~~ **Shipped** — Integrations UI + `/notifycron/run`
- Payroll export polish: CSV handoff already on Dashboard close-out — map columns to the customer’s payroll vendor  

---

*Internal path: desktop `docs/privacy-and-packaging.md` · dashboard close-out + role dashboards ship in the WorkTre web app.*
