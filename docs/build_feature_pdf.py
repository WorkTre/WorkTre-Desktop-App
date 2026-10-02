"""
Build WorkTre Feature Document PDF with real application screenshots.
"""
from __future__ import annotations

import os
import shutil
from io import BytesIO

from PIL import Image as PILImage, ImageChops
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PRIMARY = HexColor("#01a78d")
PRIMARY_DARK = HexColor("#017a68")
SECONDARY = HexColor("#002f34")
LIGHT = HexColor("#f4fbf9")
GRAY = HexColor("#5a6a6d")
LINE = HexColor("#d7e6e3")

SCREENSHOT_DIR = r"C:\Users\navee\AppData\Local\Temp\cursor\screenshots"
ASSETS = r"D:\Projects\WorkTre Desktop\WorkTre-Desktop-App\src\assets\images"
DOCS = r"D:\Projects\WorkTre Desktop\WorkTre-Desktop-App\docs"
IMG_OUT = os.path.join(DOCS, "feature-pdf-images")
PDF_PATH = os.path.join(DOCS, "WorkTre-Feature-Document.pdf")

SCREENSHOTS = [
    "web-welcome-hero.png",
    "web-features-attendance.png",
    "web-pricing.png",
    "web-login.png",
    "desktop-login.png",
    "desktop-dashboard.png",
    "desktop-settings.png",
    "desktop-settings-privacy.png",
    "desktop-break-logs.png",
    "desktop-break-modal.png",
    "desktop-trust-notice.png",
]


def crop_whitespace(src: str, dest: str, bg=(255, 255, 255), pad: int = 8) -> None:
    im = PILImage.open(src).convert("RGB")
    bg_im = PILImage.new("RGB", im.size, bg)
    diff = ImageChops.difference(im, bg_im)
    bbox = diff.getbbox()
    if bbox:
        left, top, right, bottom = bbox
        left = max(0, left - pad)
        top = max(0, top - pad)
        right = min(im.width, right + pad)
        bottom = min(im.height, bottom + pad)
        im = im.crop((left, top, right, bottom))
    im.save(dest, "PNG", optimize=True)


def collect_images() -> dict:
    os.makedirs(IMG_OUT, exist_ok=True)
    paths = {}
    for name in SCREENSHOTS:
        src = os.path.join(SCREENSHOT_DIR, name)
        dest = os.path.join(IMG_OUT, name)
        if os.path.exists(src):
            crop_whitespace(src, dest)
            paths[name] = dest
        elif os.path.exists(dest):
            paths[name] = dest
    logo_src = os.path.join(ASSETS, "logo.png")
    logo_dest = os.path.join(IMG_OUT, "logo.png")
    if os.path.exists(logo_src):
        shutil.copy2(logo_src, logo_dest)
        paths["logo.png"] = logo_dest
    splash = os.path.join(ASSETS, "splash.png")
    if os.path.exists(splash):
        dest = os.path.join(IMG_OUT, "splash.png")
        shutil.copy2(splash, dest)
        paths["splash.png"] = dest
    return paths


def fitted_image(path: str, max_w: float, max_h: float) -> Image:
    with PILImage.open(path) as im:
        w, h = im.size
    scale = min(max_w / w, max_h / h)
    return Image(path, width=w * scale, height=h * scale)


def captioned_image(path: str, caption: str, styles, max_w, max_h=92 * mm):
    img = fitted_image(path, max_w, max_h)
    cap = Paragraph(caption, styles["Caption"])
    return KeepTogether([img, Spacer(1, 2 * mm), cap, Spacer(1, 5 * mm)])


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(SECONDARY)
    canvas.rect(0, A4[1] - 10 * mm, A4[0], 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, A4[1] - 11.2 * mm, A4[0], 1.2 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(16 * mm, A4[1] - 7 * mm, "WorkTre Feature Document")
    canvas.drawRightString(A4[0] - 16 * mm, A4[1] - 7 * mm, "Desktop App  +  Web Application")

    canvas.setFillColor(PRIMARY)
    canvas.rect(0, 0, A4[0], 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(16 * mm, 4 * mm, "Confidential  |  For sales, onboarding, and security reviews")
    canvas.drawRightString(A4[0] - 16 * mm, 4 * mm, f"Page {doc.page}")
    canvas.restoreState()


def cover_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(white)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFillColor(SECONDARY)
    canvas.rect(0, A4[1] - 28 * mm, A4[0], 28 * mm, fill=1, stroke=0)
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, A4[1] - 30 * mm, A4[0], 2.2 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawCentredString(A4[0] / 2, A4[1] - 16 * mm, "WORKTRE  ·  WORK SMARTER  MANAGE BETTER")
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, 0, A4[0], 18 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(A4[0] / 2, 7 * mm, "Bioncos Global — IT Solutions  ·  worktre.com")
    canvas.restoreState()


def make_styles():
    base = getSampleStyleSheet()
    styles = {
        "CoverTitle": ParagraphStyle(
            "CoverTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=28, textColor=SECONDARY, alignment=TA_CENTER, leading=34, spaceAfter=6,
        ),
        "CoverSub": ParagraphStyle(
            "CoverSub", parent=base["Normal"], fontName="Helvetica",
            fontSize=12, textColor=GRAY, alignment=TA_CENTER, leading=18,
        ),
        "H1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=16, textColor=SECONDARY, spaceBefore=8, spaceAfter=8, leading=20,
        ),
        "H2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12.5, textColor=PRIMARY_DARK, spaceBefore=8, spaceAfter=5, leading=16,
        ),
        "Body": ParagraphStyle(
            "Body", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, textColor=SECONDARY, leading=13.5, alignment=TA_JUSTIFY, spaceAfter=4,
        ),
        "Bullet": ParagraphStyle(
            "Bullet", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, textColor=SECONDARY, leading=13, leftIndent=2,
        ),
        "Caption": ParagraphStyle(
            "Caption", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8, textColor=GRAY, alignment=TA_CENTER, leading=11, spaceAfter=2,
        ),
        "TableHead": ParagraphStyle(
            "TableHead", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8, textColor=white, leading=11, alignment=TA_CENTER,
        ),
        "TableCell": ParagraphStyle(
            "TableCell", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, textColor=SECONDARY, leading=11,
        ),
        "Quote": ParagraphStyle(
            "Quote", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=10.5, textColor=SECONDARY, leading=15, alignment=TA_CENTER,
            leftIndent=10, rightIndent=10, spaceBefore=8, spaceAfter=8,
        ),
        "FooterNote": ParagraphStyle(
            "FooterNote", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, textColor=GRAY, leading=11,
        ),
    }
    return styles


def table(data, col_widths, header=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold") if header else ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY) if header else ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("TEXTCOLOR", (0, 0), (-1, 0), white) if header else ("TEXTCOLOR", (0, 0), (-1, 0), SECONDARY),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT]),
    ]
    t.setStyle(TableStyle(style))
    return t


def bullets(items, styles):
    return ListFlowable(
        [ListItem(Paragraph(i, styles["Bullet"]), leftIndent=8, bulletColor=PRIMARY) for i in items],
        bulletType="bullet",
        start="circle",
        leftIndent=12,
        bulletFontSize=8,
        spaceBefore=2,
        spaceAfter=6,
    )


def cell(text, styles, head=False):
    return Paragraph(text, styles["TableHead"] if head else styles["TableCell"])


def build():
    imgs = collect_images()
    styles = make_styles()
    page_w, _ = A4
    content_w = page_w - 32 * mm

    story = []

    # ---- Cover (drawn on dark canvas) ----
    story.append(Spacer(1, 36 * mm))
    if "logo.png" in imgs:
        logo = fitted_image(imgs["logo.png"], 90 * mm, 22 * mm)
        logo.hAlign = "CENTER"
        story.append(logo)
    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph("Feature Document", styles["CoverTitle"]))
    story.append(Paragraph(
        "WorkTre Desktop App  &amp;  WorkTre Web Application",
        styles["CoverSub"],
    ))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "Workforce operations: accurate time on the employee PC,<br/>attendance, payroll, and HR in the browser.",
        styles["CoverSub"],
    ))
    story.append(Spacer(1, 22 * mm))
    story.append(Paragraph("September 2026  ·  Version 2.2.3  ·  worktre.com", styles["CoverSub"]))
    story.append(PageBreak())

    # ---- Intro ----
    story.append(Paragraph("1. How the two products fit together", styles["H1"]))
    story.append(Paragraph(
        "WorkTre is a workforce operations platform. Employees clock time on the <b>Desktop App</b>. "
        "Managers run attendance, payroll, HR, and alerts in the <b>Web Application</b>. "
        "Both share the same employee account, company rules, and SOAP/web services.",
        styles["Body"],
    ))
    story.append(table(
        [
            [cell(h, styles, True) for h in ["", "Desktop App", "Web Application"]],
            [cell("Who uses it", styles), cell("Employees on a PC (Windows first)", styles),
             cell("Super Admin, Owner, HR, Finance, managers, employees", styles)],
            [cell("Primary job", styles), cell("Clock-in, shift timer, breaks, idle, optional screenshots", styles),
             cell("Attendance, payroll, leaves, HR, reports, alerts", styles)],
            [cell("Runs on", styles), cell("Installed Windows app (WebView2)", styles),
             cell("Browser at worktre.com", styles)],
            [cell("Produces", styles), cell("Login/logout, heartbeats, idle windows, breaks, screenshots", styles),
             cell("Policies, approvals, salaries, reports, dashboards", styles)],
        ],
        [32 * mm, 72 * mm, 74 * mm],
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Typical day", styles["H2"]))
    story.append(bullets([
        "Employee installs WorkTre App, logs in with WorkTre credentials.",
        "App sends login + computer name + IP, then a heartbeat about every 5 minutes.",
        "Manager opens the web Dashboard and sees online / idle / stale, attendance gaps, and payroll readiness.",
        "Employee can open the full web app from the Desktop App (“Open in Browser”).",
    ], styles))

    if "web-welcome-hero.png" in imgs:
        story.append(captioned_image(
            imgs["web-welcome-hero.png"],
            "Figure 1. WorkTre web marketing site (worktre.com/welcome) — product positioning.",
            styles, content_w, 78 * mm,
        ))

    # ---- Desktop ----
    story.append(Paragraph("2. WorkTre Desktop Application", styles["H1"]))
    story.append(Paragraph(
        "Product name on the device: <b>WorkTre App</b> (not “agent” or “monitor”). "
        "Current installer <b>2.2.3</b>, per-user install under %LOCALAPPDATA%\\WorkTre. "
        "Screens below are captured from the real Desktop UI.",
        styles["Body"],
    ))

    if "desktop-login.png" in imgs:
        story.append(captioned_image(
            imgs["desktop-login.png"],
            "Figure 2. Desktop App login — email/password, Remember me, Forgot Password, version stamp.",
            styles, content_w, 72 * mm,
        ))

    story.append(Paragraph("2.1 Login and identity", styles["H2"]))
    story.append(bullets([
        "Email + password against WorkTre SOAP (worktre.com web services).",
        "Remember me — credentials stored encrypted locally in %APPDATA%\\WorkTre.",
        "Forgot password opens the web reset flow.",
        "IP allow-list: unregistered IPs are blocked; employee can request access.",
        "Login payload includes computer name, app version, and IP.",
        "Crash login restores session after an unexpected close. Single-instance lock per PC.",
    ], styles))

    if "desktop-dashboard.png" in imgs:
        story.append(captioned_image(
            imgs["desktop-dashboard.png"],
            "Figure 3. Desktop home — live shift timer, shift window, login/break/logout timeline, break controls.",
            styles, content_w, 72 * mm,
        ))

    story.append(Paragraph("2.2 Shift, attendance, and breaks", styles["H2"]))
    story.append(bullets([
        "Live circular shift timer with hours remaining vs scheduled shift.",
        "Login time, total break time, and logout status on the home screen.",
        "Resume-from-server so a restart does not reset the day’s clock.",
        "Open in Browser — SSO-style link into the web app.",
        "Start / end break from play / pause. Break types come from the company.",
        "Dedicated break timer while on break. Inactivity is its own break type.",
    ], styles))

    if "desktop-break-modal.png" in imgs:
        story.append(captioned_image(
            imgs["desktop-break-modal.png"],
            "Figure 4. Break picker — company break types, optional comment, start break.",
            styles, content_w, 78 * mm,
        ))
    if "desktop-break-logs.png" in imgs:
        story.append(captioned_image(
            imgs["desktop-break-logs.png"],
            "Figure 5. Break Logs — time, type, duration, with pagination.",
            styles, content_w, 72 * mm,
        ))

    story.append(Paragraph("2.3 Idle, heartbeats, and screenshots", styles["H2"]))
    story.append(bullets([
        "Native Windows idle detection (GetLastInputInfo).",
        "Warning after inactivity (default 5 minutes), then auto-logout (default 10 minutes).",
        "Completed idle windows (start + end) are sent on the heartbeat.",
        "Heartbeat (~5 minutes) powers online / idle / stale on the web dashboard.",
        "Offline queue — heartbeats sync when the network returns.",
        "Screenshots only if the company enables them; all monitors; blur before upload (Off / Light / Medium / Strong).",
        "Employee acknowledges screenshot consent. App / URL tracking is not enabled.",
    ], styles))

    if "desktop-settings.png" in imgs:
        story.append(captioned_image(
            imgs["desktop-settings.png"],
            "Figure 6. Desktop Settings — app health, privacy notice, and what is tracked on this device.",
            styles, content_w, 78 * mm,
        ))
    if "desktop-settings-privacy.png" in imgs:
        story.append(captioned_image(
            imgs["desktop-settings-privacy.png"],
            "Figure 7. Screenshot privacy — blur level (Medium recommended) before upload.",
            styles, content_w, 72 * mm,
        ))
    if "desktop-trust-notice.png" in imgs:
        story.append(captioned_image(
            imgs["desktop-trust-notice.png"],
            "Figure 8. First-login trust notice — employee acknowledges monitoring and screenshot policy.",
            styles, content_w, 78 * mm,
        ))

    story.append(Paragraph("2.4 Windows shell, updates, and packaging", styles["H2"]))
    story.append(bullets([
        "Minimize to system tray (Restore / Settings / Quit) with native notifications.",
        "Always-on-top inactivity warnings and native confirmation dialogs.",
        "Auto-start at Windows logon (installer Run registry key).",
        "Start Menu + Desktop shortcuts; Add/Remove Programs uninstall.",
        "In-app auto-update (.exe download, UAC elevation if needed).",
        "TLS certificate verification on SOAP/API. Encrypted remember-me store.",
        "PyInstaller Windows .exe + Inno Setup per-user installer (no admin required).",
    ], styles))
    story.append(Paragraph(
        "In-app <b>Notifications</b> inbox and <b>Profile</b> screens are still placeholders (“Coming Soon”). "
        "The avatar still loads from the web app.",
        styles["FooterNote"],
    ))

    # ---- Web ----
    story.append(Paragraph("3. WorkTre Web Application", styles["H1"]))
    story.append(Paragraph(
        "Browser product at <b>worktre.com</b>. Role-based menus (Interfaces + permissions). "
        "Employees, managers, HR, Finance, Owners, and Super Admin each see a different home.",
        styles["Body"],
    ))

    if "web-login.png" in imgs:
        story.append(captioned_image(
            imgs["web-login.png"],
            "Figure 9. Web application login — Remember me, password reset, register.",
            styles, content_w, 78 * mm,
        ))

    story.append(Paragraph("3.1 Role-scoped home dashboard", styles["H2"]))
    story.append(table(
        [
            [cell("Role", styles, True), cell("What they see", styles, True)],
            [cell("Super Admin", styles), cell("Company picker; all companies they administer", styles)],
            [cell("Owner / HR / Finance", styles),
             cell("Own company KPIs; payroll/money panels only with View Salaries", styles)],
            [cell("Department managers", styles),
             cell("Their departments — capacity, exceptions, attrition", styles)],
            [cell("Employees", styles),
             cell("Self-serve: my status today, leave, why I’m flagged, WorkTre App health", styles)],
        ],
        [48 * mm, 130 * mm],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Dashboard blocks (by role) include:", styles["Body"]))
    story.append(bullets([
        "Today’s attendance summary and 7-day trend; recent absences and pending leave count.",
        "Payroll close-out / readiness (pay-period blockers, verify/lock progress).",
        "Money queue (salaries, loans, advances, bonuses) and HR request queue.",
        "Team trust — WorkTre App online / idle / stale from the last heartbeat.",
        "Capacity, attrition, and attendance alerts preview.",
        "Restaurant / hospitality extras (low-stock alerts) when that industry is set.",
    ], styles))

    if "web-features-attendance.png" in imgs:
        story.append(captioned_image(
            imgs["web-features-attendance.png"],
            "Figure 10. Web product features — attendance, payroll, HR, and additional systems.",
            styles, content_w, 72 * mm,
        ))

    story.append(Paragraph("3.2 Attendance, shifts, breaks, and leaves", styles["H2"]))
    story.append(bullets([
        "Real-time attendance by employee, department, company, and date range.",
        "Worked hours vs shift hours, late/absent flags, Excel-style export.",
        "Attendance Alerts inbox: short hours, no login, idle logout, missing punches — with “why?” explanations.",
        "Attendance correction requests, biometric import, office IP allow-list, geo-location, IP overrides.",
        "Shift definitions, bulk update, change approvals, schedules, and swaps.",
        "Company break types and break approval requests.",
        "Leave types, requests, pending/rejected, special leaves, encashment, carry-forward, holidays.",
    ], styles))

    story.append(Paragraph("3.3 Payroll, HR, and operations", styles["H2"]))
    story.append(bullets([
        "Salaries: calculate, verify, lock by department/account; period close-out on the Dashboard.",
        "Tax slabs, bank sheets, provident fund, SESSI, EOBI, overtime, bonuses, advances, loans, insurance, incentives, fines, payslips.",
        "Multi-company setup, employee profiles/import, designations, reporting lines, roles and interface permissions.",
        "HR forms: joining, employment proof, probation-end, internship, transfer, requisitions, feedback.",
        "Company assets, retentions, expenses, stock orders.",
        "Restaurant / Hospitality Ops when the industry flag is set.",
    ], styles))

    story.append(Paragraph("3.4 Screenshots, integrations, and security", styles["H2"]))
    story.append(bullets([
        "Screenshot gallery (only if the company enabled capture) plus owner/Super Admin privacy settings (consent, retention, who can view).",
        "Slack and Microsoft Teams webhooks for high-severity attendance alerts.",
        "Email notifications, Google Calendar connector, scheduled payroll/attendance crons.",
        "SOAP web services consumed by the Desktop App; auto-login from Desktop into the web session.",
        "Role-based Interfaces + named permissions (e.g. View Salaries, View Attendance Alerts).",
        "Office IP allow-list; Super Admin vs company-scoped data; lock screen; password reset.",
    ], styles))

    if "web-pricing.png" in imgs:
        story.append(captioned_image(
            imgs["web-pricing.png"],
            "Figure 11. Public pricing on worktre.com — Basic / Standard / Premium per user.",
            styles, content_w, 72 * mm,
        ))

    story.append(Paragraph(
        "Desktop <b>does not</b> send app/URL tracking. A legacy Tracking endpoint exists in the web codebase; "
        "it is not used by the current Desktop App.",
        styles["FooterNote"],
    ))

    # ---- Shared ----
    story.append(Paragraph("4. Shared platform capabilities", styles["H1"]))
    story.append(Paragraph(
        "Company-wide rules are configured in the web app and enforced on the employee PC.",
        styles["Body"],
    ))
    story.append(table(
        [
            [cell(h, styles, True) for h in ["Capability", "Configured in Web", "Enforced in Desktop"]],
            [cell("Login / logout attendance", styles), cell("Dashboard, Attendance", styles), cell("Clock in/out", styles)],
            [cell("Shift window", styles), cell("Shifts", styles), cell("Shift timer", styles)],
            [cell("Break types", styles), cell("Breaks", styles), cell("Break picker", styles)],
            [cell("Idle warning / logout", styles), cell("Service settings", styles), cell("Idle monitor", styles)],
            [cell("Screenshots on/off", styles), cell("Employee / screenshot settings", styles), cell("Capture + blur + consent", styles)],
            [cell("Allowed office IPs", styles), cell("Office IPs", styles), cell("Login block + request access", styles)],
            [cell("Online / idle / stale", styles), cell("Dashboard trust panel", styles), cell("Heartbeat every ~5 min", styles)],
            [cell("App version", styles), cell("Version report", styles), cell("Auto-update", styles)],
        ],
        [52 * mm, 64 * mm, 62 * mm],
    ))

    story.append(Paragraph("5. What is captured vs not captured", styles["H1"]))
    story.append(table(
        [
            [cell(h, styles, True) for h in ["Captured", "Default", "Where it shows"]],
            [cell("Attendance login / logout", styles), cell("On", styles), cell("Desktop + Web Attendance", styles)],
            [cell("Shift timer &amp; breaks", styles), cell("On", styles), cell("Desktop + Web", styles)],
            [cell("Idle / away time", styles), cell("On", styles), cell("Desktop + Web alerts", styles)],
            [cell("Activity heartbeat (~5 min)", styles), cell("On", styles), cell("Web “WorkTre App online”", styles)],
            [cell("Screenshots", styles), cell("Company-controlled", styles), cell("Web gallery if enabled", styles)],
            [cell("App / URL tracking", styles), cell("Off in Desktop App", styles), cell("Not used by current client", styles)],
        ],
        [58 * mm, 48 * mm, 72 * mm],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Heartbeats may queue offline so hours are not silently lost.",
        styles["Body"],
    ))

    story.append(Paragraph("6. Who should use which product", styles["H1"]))
    story.append(bullets([
        "<b>Employees — Desktop App</b> to clock a shift, take breaks, and stay visible as online for payroll.",
        "<b>Managers — Web Application</b> to approve leave, clear attendance exceptions, run payroll, or see team capacity.",
        "<b>HR / Finance — Web Application</b> for salaries, taxes, banks, loans, bonuses, and period close-out.",
        "<b>Super Admin — Web Application</b> for multi-company setup, roles, IPs, screenshot policy, and Slack/Teams integrations.",
    ], styles))

    story.append(Paragraph("7. Packaging and support notes", styles["H1"]))
    story.append(table(
        [
            [cell("Topic", styles, True), cell("Practice", styles, True)],
            [cell("Desktop install", styles),
             cell("Download installer → run (no admin) → log in → first heartbeat on dashboard within minutes", styles)],
            [cell("Desktop data on device", styles),
             cell("%APPDATA%\\WorkTre (prefs, logs, encrypted remember-me)", styles)],
            [cell("Transport", styles), cell("TLS verification enabled for SOAP/API", styles)],
            [cell("Web", styles),
             cell("Role dashboards, payroll close-out, attendance alerts, integrations", styles)],
            [cell("Pilot checklist", styles),
             cell("5–10 PCs → log in → Settings matches policy → manager sees online in ~5 minutes → run alerts + one payroll close-out", styles)],
        ],
        [42 * mm, 136 * mm],
    ))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("8. One-line summary", styles["H1"]))
    story.append(Paragraph(
        "WorkTre App records time for correct pay on the employee PC. WorkTre Web turns that time into attendance, "
        "alerts, payroll, and HR — with blur-by-default screenshots only if the company enables them, no app/URL "
        "tracking from the desktop client, and a dashboard status employees can see themselves.",
        styles["Quote"],
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Images in this PDF are screenshots of the live Desktop UI (served from the application assets) "
        "and the production web site at worktre.com. Dashboard sample name is for illustration.",
        styles["FooterNote"],
    ))

    def first_page(canvas, doc):
        cover_header_footer(canvas, doc)

    def later_pages(canvas, doc):
        header_footer(canvas, doc)

    doc = SimpleDocTemplate(
        PDF_PATH,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title="WorkTre Feature Document",
        author="WorkTre / Bioncos Global",
        subject="Desktop App and Web Application features",
    )
    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    print(f"Wrote {PDF_PATH}")
    print(f"Images: {IMG_OUT}")
    missing = [n for n in SCREENSHOTS if n not in imgs]
    if missing:
        print("Missing screenshots:", ", ".join(missing))


if __name__ == "__main__":
    build()
