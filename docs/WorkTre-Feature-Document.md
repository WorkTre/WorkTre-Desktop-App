# WorkTre Feature Document

**Products:** WorkTre Desktop App and WorkTre Web Application  
**Audience:** Sales, onboarding, customer success, security reviews, and product  
**Last updated:** September 2026  
**Live site:** [worktre.com](https://worktre.com) · Marketing: [worktre.com/welcome](https://worktre.com/welcome)

WorkTre is a workforce operations platform: employees clock time on the **Desktop App**, and managers run attendance, payroll, HR, and alerts in the **Web Application**. The two products share the same employee account, company rules, and SOAP/web services.

---

## 1. How the two products fit together

| | **Desktop App** | **Web Application** |
|---|---|---|
| **Who uses it** | Employees on a PC (Windows first) | Super Admin, Owner, HR, Finance, managers, and employees |
| **Primary job** | Accurate clock-in, shift timer, breaks, idle, optional screenshots | Company operations: attendance, payroll, leaves, HR, reports |
| **Runs on** | Installed Windows app (PyWebView + WebView2) | Browser at worktre.com |
| **Data it produces** | Login / logout, heartbeats, idle windows, break events, screenshots | Policies, approvals, salaries, reports, alerts, dashboards |
| **Data it consumes** | Shift times, break types, screenshot-on/off, IP allow-list | Heartbeats and attendance from the Desktop App |

**Typical day**

1. Employee installs WorkTre App, logs in with WorkTre credentials.  
2. App sends login + computer name + IP, then a heartbeat about every 5 minutes.  
3. Manager opens the web Dashboard and sees online / idle / stale, attendance gaps, and payroll readiness.  
4. Employee can open the full web app from the Desktop App (“Open in Browser”).

---

## 2. WorkTre Desktop Application

Product name on the device: **WorkTre App** (not “agent” or “monitor”).  
Current installer version: **2.2.3** · Per-user install under `%LOCALAPPDATA%\WorkTre`.

### 2.1 Login and identity

- Email + password login against WorkTre SOAP (`worktre.com` web services).
- **Remember me** — typed password stored with Windows DPAPI in `%APPDATA%\WorkTre`. An older Fernet file is migrated once, then removed.
- **Forgot password** opens the web reset flow.
- **IP allow-list** — if the PC’s IP is not registered, login is blocked and the employee can **request access**.
- Login payload includes **computer name**, **app version**, and **IP**.
- **Crash login** restores session after an unexpected close.
- **Single-instance lock** — only one WorkTre App window per PC.
- Auto-fill remembered user on startup.

### 2.2 Shift and attendance on the machine

- Live **circular shift timer** (hours remaining vs scheduled shift).
- Shift start/end from the company (GMT converted to local time).
- **Login time**, **total break time**, and **logout** status on the home screen.
- Resume-from-server so a restart does not reset the day’s clock.
- **Open in Browser** — SSO-style link into the web app (`autologin`).

### 2.3 Breaks

- Start / end break from play / pause.
- Break types come from the company (lunch, tea, training, meeting, and custom types).
- Optional **comment** on break start and end.
- Dedicated **break timer** while on break.
- **Break Logs** table (time, type, duration) with pagination.
- Inactivity is recorded as its own break type.

### 2.4 Idle and activity

- Native Windows idle detection (`GetLastInputInfo`).
- Warning after inactivity (default **5 minutes**), then auto-logout (default **10 minutes**) — values come from company service settings.
- Modal: “Are you still there?” / End inactivity break.
- Completed idle windows (start + end) are sent on the heartbeat for payroll/attendance.
- Heartbeat (~**5 minutes**) powers **online / idle / stale** on the web dashboard.
- **Offline queue** — heartbeats queue locally and sync when the network returns.

### 2.5 Screenshots (company-controlled)

- Taken only if the company sets `ScreenShotStatus` on for that employee.
- Captures **all monitors**.
- **Blur before upload** — Off / Light / Medium (default) / Strong.
- Employee must **acknowledge screenshot consent** if the company turns screenshots on.
- Uploaded to WorkTre (`ss_upload`) as a form-encoded body, with a desk token in that body when one is available. The token, username, and password are never placed in the URL. A capture whose base64 is over 12 MB is re-encoded as JPEG (quality 80) and downscaled until it fits. If a token cannot be issued or renewed, the upload still goes out without one and attendance keeps running.
- **App / URL tracking is not enabled** in the Desktop App.

### 2.6 Privacy and trust (employee-visible)

- First-login **trust notice** — what is recorded, in plain language.
- **Settings** shows:
  - App health (version, connection, last heartbeat, idle)
  - Privacy notice
  - What’s tracked (attendance, shift/breaks, idle, heartbeat, screenshots on/off)
  - SSL status and offline queue count
  - Screenshot blur control
- No silent “hidden agent” framing; managers see **WorkTre App online**.

### 2.7 Connectivity and notifications

- Online / offline overlay when the internet drops.
- Desktop **system-tray notifications** (login, logout, inactivity, connection, breaks).
- Login reminder if the app is running but the employee is not clocked in.
- Disconnect timeout can log the employee out after prolonged offline time.

### 2.8 Windows desktop shell

- Minimize to **system tray** (Restore / Settings / Quit).
- Native confirmation dialogs and always-on-top for inactivity warnings.
- **.ico** window and tray icons; Segoe UI styling.
- Auto-start at Windows logon (installer writes the Run registry key).
- Start Menu + Desktop shortcuts; Add/Remove Programs uninstall.
- In-app **auto-update** (version check, download `.exe`, UAC elevation if needed).

### 2.9 Security and packaging

- TLS certificate verification on SOAP/API calls.
- Encrypted local remember-me and screenshot-token store (Windows DPAPI, current user). Tokens and passwords are not written to logs.
- PyInstaller Windows `.exe` + Inno Setup per-user installer (no admin required).
- System resource logging (CPU / memory / disk) for support, not for manager dashboards.

### 2.10 Desktop screens not yet live

| Screen | Status |
|---|---|
| In-app **Notifications** inbox | Placeholder — “Coming Soon” |
| In-app **Profile** | Placeholder — “Coming Soon” (avatar still shows from web) |

---

## 3. WorkTre Web Application

Browser product at **worktre.com**. Role-based menus (Interfaces + permissions). Employees, managers, HR, Finance, Owners, and Super Admin each see a different home.

### 3.1 Home dashboard (role-scoped)

| Role | What they see |
|---|---|
| **Super Admin** | Company picker; all companies they administer |
| **Owner / HR / Finance** | Own company KPIs, payroll/money panels only with **View Salaries** |
| **Department managers** | Their departments — capacity, exceptions, attrition |
| **Employees** | Self-serve home: my status today, leave, “why I’m flagged,” WorkTre App health |

Dashboard blocks (by role):

- Today’s attendance summary and 7-day trend  
- Recent absences and pending leave count  
- **Payroll close-out / readiness** (pay period blockers, verify/lock progress)  
- Money queue (salaries, loans, advances, bonuses)  
- HR request queue  
- Team trust (WorkTre App online / idle / stale from last heartbeat)  
- Capacity and attrition  
- Attendance alerts preview  
- Restaurant/hospitality extras (low-stock alerts) when that industry is set  

### 3.2 Attendance and time

- Real-time attendance by employee, department, company, and date range  
- Worked hours vs shift hours, late/absent flags, Excel-style export  
- Attendance records and attendance reports  
- **Attendance Alerts** (exceptions inbox): short hours, no login, idle logout, missing punches  
- Plain-language **“why?”** explanations (rule-based; optional AI polish)  
- Attendance correction requests + approval queue  
- Weekly / overall employee reports  
- WorkTre App version and inactive-app reports  
- IP reports and office IP allow-list  
- Employee IP override (remote / exception IPs)  
- Office geo-location  
- Biometric import option  
- Punctuality requests  

### 3.3 Breaks

- Company break types and break reports  
- Break approval requests (pending / approve)  
- Training-break and QT-break reports  

### 3.4 Shifts

- Shift definitions and bulk “update all shifts”  
- Shift change approval requests  
- Shift reports (hours, days, stats, morning / afternoon / evening schedules)  
- Employee shift schedule and supervisor schedule  
- Shift swaps (request, pending, my swaps)  

### 3.5 Leaves and time off

- Leave types, leave records, requested / pending / rejected leaves  
- Special leaves and leave logs  
- Leave encashment (request, pending, record)  
- Leave carry-forward report  
- Overall leaves report  
- Holidays calendar  
- Time-off requests  

### 3.6 Payroll and compensation

- **Salaries** — calculate, verify, lock by department/account  
- **Period close-out** on the Dashboard (payroll readiness before payday)  
- Salary records and salaries report  
- Tax slabs and tax calculation  
- Bank accounts, bank sheets, bank reports  
- **Direct-deposit style** bank payout sheets  
- Provident fund, social security (SESSI), EOBI reports  
- Overtime (pending / approve) and OT reports  
- Bonuses (request, approve, reports)  
- Salary advances and increment requests  
- Loans and overall loans report  
- Insurance and insurance report  
- Incentives / fixed incentives reports  
- Fines (approval requests)  
- Payslip / PDF generation  

### 3.7 HR and employee lifecycle

- Multi-company and department setup  
- Employee profiles, search, import  
- Designations and reporting lines  
- Roles, temporary roles, interface access (page + permission matrix)  
- Joining form, employment proof, probation-end, internship completion  
- Transfer form and pending HR forms  
- Requisitions / profile requisitions  
- Feedback forms and replies  
- Employee card / blood-group reports  
- Company assets allocation  
- Retentions  
- COVID / vaccination reports (legacy compliance)  
- Privacy policy pages  

### 3.8 Screenshots and app trust (web side)

- Screenshot gallery for users whose company enabled capture  
- **Screenshot privacy settings** (owner / Super Admin): consent, retention, who can view others  
- WorkTre App online status from heartbeats  
- Desktop version report  

Desktop **does not** send app/URL tracking. A legacy Tracking endpoint exists in the web codebase; it is **not** used by the current Desktop App.

### 3.9 Requests and approvals (manager inbox)

Unified pending-request counts for:

- Leaves, breaks, attendance corrections  
- Shift changes and swaps  
- Overtime, salary increments, encashment  
- HR forms (joining, transfer, probation, feedback, requisitions)  

### 3.10 Expenses and operations

- Expense types, categories, purposes, budgets, tasks  
- Orders / stock orders  
- **Restaurant / Hospitality Ops** (industry flag): sales capture, low-stock alerts on dashboard  

### 3.11 Integrations and automation

- **Slack and Microsoft Teams** webhooks — notify managers on high-severity attendance alerts (`/notifycron/run`)  
- Email notifications and login notifications  
- Google Calendar connector  
- Scheduled crons (daily, weekly, monthly, yearly, salary, overtime)  
- SOAP web services consumed by the Desktop App  
- Auto-login from Desktop into the web session  

### 3.12 Security and access (web)

- Role-based Interfaces (menu) + named permissions (e.g. View Salaries, View Attendance Alerts)  
- Office IP allow-list; unregistered IPs can request access  
- Super Admin vs company-scoped data (Owner/HR see own company only)  
- Lock screen  
- Password reset / forgot password  

---

## 4. Shared platform capabilities

These are company-wide rules the **web app configures** and the **desktop app enforces**:

| Capability | Configured in Web | Enforced in Desktop |
|---|---|---|
| Login / logout attendance | Dashboard, Attendance | Clock in/out |
| Shift window | Shifts | Shift timer |
| Break types | Breaks | Break picker |
| Idle warning / logout minutes | Service settings | Idle monitor |
| Screenshots on/off | Employee / screenshot settings | Capture + blur + consent |
| Allowed office IPs | Office IPs | Login block + request access |
| Online / idle / stale | Dashboard trust panel | Heartbeat every ~5 min |
| App version | Version report | Auto-update |

---

## 5. What is captured vs not captured

| Captured | Default | Where it shows |
|---|---|---|
| Attendance login / logout | On | Desktop + Web Attendance |
| Shift timer & breaks | On | Desktop + Web |
| Idle / away time | On | Desktop + Web alerts |
| Activity heartbeat (~5 min) | On | Web “WorkTre App online” |
| Screenshots | **Company-controlled** | Web gallery if enabled |
| App / URL tracking | **Off** in Desktop App | Not used by current client |

Heartbeats may queue offline so hours are not silently lost.

---

## 6. Who should use which product

**Give employees the Desktop App** if they need to clock a shift, take breaks, and stay visible as online for payroll.

**Give managers the Web Application** if they need to approve leave, clear attendance exceptions, run payroll, or see team capacity.

**Give HR / Finance the Web Application** for salaries, taxes, banks, loans, bonuses, and period close-out.

**Give Super Admin the Web Application** for multi-company setup, roles, IPs, screenshot policy, and Slack/Teams integrations.

---

## 7. Packaging and support notes

| Topic | Practice |
|---|---|
| Desktop install | Download installer → run (no admin) → log in → first heartbeat on dashboard within minutes |
| Desktop data on device | `%APPDATA%\WorkTre` (prefs, logs, DPAPI remember-me and screenshot token) |
| Transport | TLS verification enabled for SOAP/API |
| Web | Role dashboards, payroll close-out, attendance alerts, integrations |
| Pilot checklist | 5–10 PCs → log in → Settings matches policy → manager sees online in ~5 minutes → run attendance alerts + one payroll close-out |

---

## 8. One-line summary

> **WorkTre App** records time for correct pay on the employee PC. **WorkTre Web** turns that time into attendance, alerts, payroll, and HR — with blur-by-default screenshots only if the company enables them, no app/URL tracking from the desktop client, and a dashboard status employees can see themselves.
