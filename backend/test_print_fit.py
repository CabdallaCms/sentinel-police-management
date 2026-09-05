#!/usr/bin/env python3
"""Print-template contract tests for application.html / certificate.html.

Encodes the Fingerprint Unit template specification:

  1. EXACT A4 PRINT RULES — both documents print on ONE A4 portrait page with
     8mm @page margins, exact color reproduction (print-color-adjust), and all
     web chrome (toolbar / buttons / badges / banners / toasts) hidden.
  2. OFFICIAL EMBLEM PLACEMENT — application.html carries the police emblem
     ONLY as the centred low-opacity watermark; certificate.html carries it in
     BOTH the letterhead masthead AND the centred watermark.
  3. DYNAMIC BINDINGS — every DOM id the templates bind (4-part legal name,
     DOB, National ID/Passport, phone, address, gender, occupation, purpose
     chips, guardian/guarantor, 35x45 photo box, serial + QR placeholders)
     survives, together with the backend endpoints, session checks and the
     mandatory 12-hour review-lock logic.
  4. SINGLE-PAGE HEIGHT BUDGET — a conservative worst-case estimate of the
     printed content height (computed from the actual CSS values, generous
     wrap allowances included) fits inside one A4 page minus the @page
     margins, with a documented safety slack.

Usage:  python3 backend/test_print_fit.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)

PT_TO_MM = 25.4 / 72.0          # 1pt = 0.3528mm
PX_TO_MM = 25.4 / 96.0          # CSS px at 96dpi
A4_H_MM, A4_W_MM = 297.0, 210.0
PAGE_MARGIN_MM = 8.0            # @page margin from the spec
SAFETY_MM = 8.0                 # engine rounding slack we insist on
OPACITY_MIN, OPACITY_MAX = 0.08, 0.12   # watermark band from the spec

FAILURES = []


def check(name, ok, detail=''):
    print(('ok: ' if ok else 'FAIL: ') + name + ((' -> ' + detail) if detail and not ok else ''))
    if not ok:
        FAILURES.append(name)


def css_block(html, selector):
    """Return the body of the last `selector{...}` rule (no nesting in our CSS)."""
    out = []
    for m in re.finditer(re.escape(selector) + r'\s*\{([^}]*)\}', html):
        out.append(m.group(1))
    return out[-1] if out else ''


def num(block, prop, default=0.0):
    """Length property in mm. Accepts pt/px/mm units; returns default if absent."""
    m = re.search(re.escape(prop) + r'\s*:\s*(-?[\d.]+)(pt|px|mm)', block)
    if not m:
        return default
    v, unit = float(m.group(1)), m.group(2)
    return v * {'pt': PT_TO_MM, 'px': PX_TO_MM, 'mm': 1.0}[unit]


def unitless(block, prop, default=None):
    m = re.search(re.escape(prop) + r'\s*:\s*(-?[\d.]+)\s*(?:;|\})', block)
    return float(m.group(1)) if m else default


def line_mm(block, fallback_font_pt, fallback_lh=1.2):
    """Height of one text line for a rule that sets font-size (and maybe line-height)."""
    fs = num(block, 'font-size', fallback_font_pt * PT_TO_MM)
    lh = re.search(r'line-height\s*:\s*([\d.]+)', block)
    factor = float(lh.group(1)) if lh else fallback_lh
    return fs * factor


# ---------------------------------------------------------------------------
# Load templates
# ---------------------------------------------------------------------------
app = open(os.path.join(PROJECT, 'application.html'), encoding='utf-8').read()
cert = open(os.path.join(PROJECT, 'certificate.html'), encoding='utf-8').read()

A4_RULE = '@page{size:A4 portrait;margin:8mm}'
APP_HIDE = ['.toolbar', '.btn', '.badge', '.toast', '.lockbar']   # all chrome on the form
CERT_HIDE = ['.toolbar', '.btn', '.badge']                        # all chrome on the certificate

# ---------------------------------------------------------------------------
# 1. Exact A4 print rules
# ---------------------------------------------------------------------------
def print_block_of(html):
    m = re.search(r'@media print\s*\{(.*?)\n  \}', html, re.S)
    return re.sub(r'\s+', ' ', m.group(1)) if m else ''


for name, html in (('application.html', app), ('certificate.html', cert)):
    pb = print_block_of(html)
    check(f'{name}: @media print block present', bool(pb))
    check(f'{name}: exact A4 @page rule (size: A4 portrait; margin: 8mm)', A4_RULE in pb)
    flat = pb.replace(' ', '')
    check(f'{name}: print-color-adjust: exact (incl. -webkit prefix)',
          'print-color-adjust:exact!important' in flat
          and '-webkit-print-color-adjust:exact!important' in flat)

    # The on-screen sheet must not force a full A4 min-height onto the paper
    # (297mm content + 16mm margins would guarantee a second blank page).
    page_print = css_block(pb, '.page').replace(' ', '')
    check(f'{name}: .page print override drops min-height/margins',
          'min-height:0' in page_print and 'margin:0' in page_print)

for name, html, hide in (('application.html', app, APP_HIDE), ('certificate.html', cert, CERT_HIDE)):
    pb = print_block_of(html)
    for sel in hide:
        shown = re.search(re.escape(sel) + r'[^{]*\{[^}]*display:\s*none', pb)
        check(f'{name}: {sel} hidden when printing', bool(shown))

# ---------------------------------------------------------------------------
# 2. Official emblem placement
# ---------------------------------------------------------------------------
check('application.html: emblem appears exactly ONCE (watermark only)',
      app.count('images/police_logo.png') == 1)
app_wm = css_block(app, '.watermark')
check('application.html: watermark is centred (top/left 50% + translate)',
      'top:50%' in app_wm.replace(' ', '') and 'left:50%' in app_wm.replace(' ', '')
      and 'translate(-50%,-50%)' in app_wm.replace(' ', ''))
opacity = unitless(app_wm, 'opacity')
check('application.html: watermark opacity inside the 0.08-0.12 spec band',
      opacity is not None and OPACITY_MIN <= opacity <= OPACITY_MAX, f'opacity={opacity}')
check('application.html: watermark blends onto the paper (mix-blend-mode:multiply)',
      'mix-blend-mode:multiply' in app_wm.replace(' ', ''))
check('application.html: watermark sits behind the content (z-index 0 + overlay)',
      'z-index:0' in app_wm.replace(' ', '') and 'z-index:1' in css_block(app, '.content').replace(' ', ''))
app_body = app.split('</head>')[1]
check('application.html: no header/letterhead logo element',
      'header-logo' not in app_body and 'logo-wrap' not in app_body and 'crest' not in app_body)

check('certificate.html: emblem appears exactly TWICE (masthead + watermark)',
      cert.count('images/police_logo.png') == 2)
cert_wm = css_block(cert, '.watermark')
check('certificate.html: watermark is centred (top/left 50% + translate)',
      'top:50%' in cert_wm.replace(' ', '') and 'left:50%' in cert_wm.replace(' ', '')
      and 'translate(-50%,-50%)' in cert_wm.replace(' ', ''))
opacity = unitless(cert_wm, 'opacity')
check('certificate.html: watermark opacity inside the 0.08-0.12 spec band',
      opacity is not None and OPACITY_MIN <= opacity <= OPACITY_MAX, f'opacity={opacity}')
check('certificate.html: watermark blends onto the paper (mix-blend-mode:multiply)',
      'mix-blend-mode:multiply' in cert_wm.replace(' ', ''))
check('certificate.html: crest in the top masthead',
      '.crest img' in cert and 'cert-masthead' in cert)
check('certificate.html: official title (CERTIFICATE OF GOOD CONDUCT)',
      'CERTIFICATE OF GOOD CONDUCT' in cert)
check('certificate.html: ornate frame + seal + dual signatures present',
      '.cert-frame' in cert and '.seal' in cert and '.sig-block' in cert)

# ---------------------------------------------------------------------------
# 3. Dynamic bindings, endpoints, auth and the 12h review lock
# ---------------------------------------------------------------------------
APP_IDS = ['statusBadge', 'approveBtn', 'lockbar', 'toast', 'photoContainer',
           'appFullName', 'appMotherName', 'appNationalId', 'appPassport',
           'appDob', 'appPob', 'appGender', 'appPhone', 'appEmail', 'appAddress',
           'appOccupation', 'appPurpose', 'purposeChips', 'appNotes',
           'appAppDocs', 'appGuardDocs',
           'guarantorName', 'guarantorId', 'guarantorRel', 'guarantorPhone',
           'guarantorAddr', 'guarantorOcc',
           'appSerial', 'appSubmitted', 'qrBox']
for el in APP_IDS:
    check(f'application.html: #{el} present', f'id="{el}"' in app)

# hooks shared by both documents (the certificate page relies on the
# authenticated record endpoint + 401 handling; only application.html needs
# the explicit /api/me role resolution for the admin bypass)
COMMON_HOOKS = ['REVIEW_LOCK_HOURS=12',                     # mandatory review window
                "/api/clearance-applications/'+id",         # record endpoint
                'sentinel_token', 'sentinelSession',        # auth storage keys
                'function forceSignIn(',                    # hard re-login
                'function dmy(']                            # date binding helper
APP_HOOKS = COMMON_HOOKS + ['/api/me',                      # session/role check (admin bypass)
                            'function reviewLock(',         # client-side lock
                            "fetch('/api/fingerprint/applications/'+id+'/approve'"]
for name, html, hooks in (('application.html', app, APP_HOOKS),
                          ('certificate.html', cert, COMMON_HOOKS)):
    for hook in hooks:
        check(f'{name}: keeps `{hook.rstrip("(")}`', hook in html)

check('application.html: 4-part legal name binding',
      'first_name' in app and 'fourth_name' in app and "fill('appFullName'" in app)
check('application.html: purpose selector chips render',
      'function renderPurposeChips(' in app
      and "PURPOSE_CHIPS=['Education','Travel','Employment','Citizenship','Licence']" in app)
check('application.html: 35x45 mm photo box + applicant photo binding',
      'width:35mm' in app.replace(' ', '') and 'height:45mm' in app.replace(' ', '')
      and 'applicant_photo||a.photo_path' in app.replace(' ', ''))
check('application.html: serial + QR placeholders',
      "fill('appSerial'" in app and "fill('appSubmitted'" in app and 'id="qrBox"' in app)
check('certificate.html: unlock gate (approved + certificate number)',
      "a.status==='Approved'&&a.certificate_number" in cert)

# ---------------------------------------------------------------------------
# 4. Single-page height budget (worst case, printed at A4 - 2x8mm margins)
# ---------------------------------------------------------------------------
avail = A4_H_MM - 2 * PAGE_MARGIN_MM


def budget_application():
    """Conservative worst-case printed height of application.html, in mm.

    Values are read from the stylesheet; wrap allowances deliberately
    OVER-estimate line counts, so a passing budget means real engines
    have room to spare.
    """
    h = 0.0
    # masthead: 3 text lines + underline padding + double rule
    h += (line_mm(css_block(app, '.masthead .t1'), 12.5, 1.15)
          + line_mm(css_block(app, '.masthead .t2'), 10, 1.15)
          + line_mm(css_block(app, '.masthead .t3'), 7.5, 1.15)
          + 4 * PX_TO_MM + 3 * PX_TO_MM)
    # title + its margins (shorthand `margin:2.5mm 0 1.2mm 0`)
    h += line_mm(css_block(app, '.title'), 15, 1.35) + 2.5 + 1.2
    # meta row: the 45mm portrait photo cell dominates; caption single line
    h += 45 + 3 * PX_TO_MM + line_mm(css_block(app, '.photo-cap'), 6.5, 1.35) + 1.0
    h += 2.0  # .meta margin-bottom (`margin:0 0 2mm 0`)
    # four section bars
    sec = css_block(app, '.sec')
    h += 4 * (line_mm(sec, 9, 1.2) + 5 * PX_TO_MM + num(sec, 'margin-top'))
    # ruled grid rows: bold label + entry on ONE line (~9pt leading + padding)
    row_h = line_mm(css_block(app, '.v'), 9, 1.25) + 3 * PX_TO_MM + 1 * PX_TO_MM
    h += 7 * row_h + 2 * row_h        # Section 01: 7 rows + 2 wrap allowances
    # Section 02: chips row + recorded purpose + notes + 2 attachment rows
    chips, pline, pbox, drow = (css_block(app, '.chip'), css_block(app, '.purpose-line'),
                                css_block(app, '.purpose-box'), css_block(app, '.doc-row'))
    h += (line_mm(chips, 8, 1.3) + 3 * PX_TO_MM + 2.8 * PX_TO_MM
          + line_mm(pline, 8, 1.3) + num(pline, 'margin-top') + num(pline, 'padding-top') + 1 * PX_TO_MM
          + 3 * (line_mm(drow, 8, 1.35) + num(drow, 'margin-top') + num(drow, 'padding-top') + 1 * PX_TO_MM)
          + 2 * num(pbox, 'padding-top', 1.8) + 1 * PX_TO_MM)
    h += 3 * row_h + 2 * row_h        # Section 03: 3 rows + 2 wrap allowances
    # Section 04: two declaration boxes — body lines derived per box from the
    # actual text (0.58em avg char width, +1 slack line each)
    stm, body, sig = css_block(app, '.stm'), css_block(app, '.stm .body'), css_block(app, '.sig')
    fs_body = num(body, 'font-size', 7.8 * PT_TO_MM)
    width_mm = A4_W_MM - 2 * PAGE_MARGIN_MM - 7.0            # page minus stm padding/border
    chars_per_line = max(20.0, width_mm / (0.58 * fs_body))
    boxes = re.findall(r'<span class="body">(.*?)</span>', app, re.S)
    total_decl_lines = 0
    for box in boxes:
        text = re.sub(r'<[^>]+>', '', box)
        total_decl_lines += min(6, -(-len(text.strip()) // int(chars_per_line)) + 1)
    one = (2 * num(stm, 'padding-top', 2.0) + 1 * PX_TO_MM
           + num(sig, 'margin-top', 1.6) + line_mm(sig, 8, 1.3) + 8 * PX_TO_MM)
    h += len(boxes) * one + total_decl_lines * line_mm(body, 7.8, 1.25) + 2 * num(stm, 'margin-top', 1.5)
    # footer: stripe + one line (nowrap enforced) + padding + margin
    h += (2 * PX_TO_MM + line_mm(css_block(app, '.foot .body'), 8, 1.3)
          + 6 * PX_TO_MM + num(css_block(app, '.foot'), 'margin-top'))
    return h


def budget_certificate():
    """Conservative worst-case printed height of the rebuilt certificate, in mm."""
    h = 0.0
    # ornate frame chrome: outer border+padding and inner rule+padding, top+bottom
    frame, inner = css_block(cert, '.cert-frame'), css_block(cert, '.cert-inner')
    chrome_v = (4 * PX_TO_MM + num(frame, 'padding-top', 2.2) + 1.5 * PX_TO_MM
                + num(inner, 'padding-top', 5.5))
    chrome_b = (4 * PX_TO_MM + num(frame, 'padding-top', 2.2) + 1.5 * PX_TO_MM
                + num(inner, 'padding-top', 5.0))
    h += chrome_v + chrome_b
    # masthead: crest + 3 lines + padding + gold rule
    h += (num(css_block(cert, '.crest img'), 'width', 23.0)
          + line_mm(css_block(cert, '.cm-t1'), 13, 1.2)
          + line_mm(css_block(cert, '.cm-t2'), 10, 1.2)
          + line_mm(css_block(cert, '.cm-t3'), 7.5, 1.2)
          + num(css_block(cert, '.cert-masthead'), 'padding-top', 2.5) + 1.5 * PX_TO_MM)
    # title band + italic lead-in + centred name with gold underline
    h += (line_mm(css_block(cert, '.cert-title h1'), 19.5, 1.2) + 4.5 + 1.0
          + line_mm(css_block(cert, '.cert-sub'), 10, 1.4) + 1.5
          + line_mm(css_block(cert, '.cert-name'), 17.5, 1.2) + 1.0 + 2.0)
    # certification prose: ~480 chars over ~100 chars/line at 10.5pt/1.6
    prose = css_block(cert, '.cert-prose')
    fs_prose = num(prose, 'font-size', 10.5 * PT_TO_MM)
    chars_per_line = max(40.0, (A4_W_MM - 2 * PAGE_MARGIN_MM - 8.0) / (0.50 * fs_prose))
    prose_text = re.sub(r'<[^>]+>', '', re.search(r'<div class="cert-prose">(.*?)</div>', cert, re.S).group(1))
    prose_lines = min(10, -(-len(prose_text.strip()) // int(chars_per_line)))
    h += prose_lines * line_mm(prose, 10.5, 1.6)
    # details panel: 12 grid slots in 6 rows (label + value + row gap)
    d_dl, d_dv = css_block(cert, '.d-item .dl'), css_block(cert, '.d-item .dv')
    rows = -(-cert.count('ditem(') // 2)
    h += (rows * (line_mm(d_dl, 6.6, 1.2) + line_mm(d_dv, 9.5, 1.2)
                  + num(css_block(cert, '.details'), 'padding-top', 2.2) / 2.0 + 1.1)
          + 2 * num(css_block(cert, '.details'), 'padding-top', 2.2) + 2 * 1.5 * PX_TO_MM)
    # issue ribbon
    issue = css_block(cert, '.cert-issue')
    h += (num(issue, 'margin-top', 3.2) + 2 * num(issue, 'padding-top', 1.4)
          + line_mm(issue, 8.5, 1.3) + 1.5 * PX_TO_MM)
    # signatures row: the 33mm seal block dominates the two signature stacks
    h += (num(css_block(cert, '.cert-signatures'), 'margin-top', 5.0)
          + num(css_block(cert, '.seal'), 'width', 31.0)
          + num(css_block(cert, '.sig-script'), 'height', 8.5) * 0      # parallel to seal
          + num(css_block(cert, '.sig-line'), 'height', 5.5) + 1.2
          + line_mm(css_block(cert, '.sig-role'), 7.4, 1.2))
    # declaration + footer
    h += (num(css_block(cert, '.cert-declare'), 'margin-top', 3.5)
          + 2 * line_mm(css_block(cert, '.cert-declare'), 7.8, 1.3))
    h += (2 * PX_TO_MM + line_mm(css_block(cert, '.foot .body'), 8, 1.3)
          + 6 * PX_TO_MM + num(css_block(cert, '.foot'), 'margin-top'))
    return h


b_app, b_cert = budget_application(), budget_certificate()
print(f'     [budget] application.html worst case {b_app:.1f}mm / {avail:.0f}mm available')
print(f'     [budget] certificate.html worst case {b_cert:.1f}mm / {avail:.0f}mm available')
check('application.html: worst-case print height fits one A4 page (+safety)',
      b_app <= avail - SAFETY_MM)
check('certificate.html: worst-case print height fits one A4 page (+safety)',
      b_cert <= avail - SAFETY_MM)

print()
if FAILURES:
    print(f'PRINT TEMPLATE TESTS FAILED ({len(FAILURES)}):')
    for f in FAILURES:
        print('  -', f)
    sys.exit(1)
print('ALL PRINT TEMPLATE TESTS PASSED')
