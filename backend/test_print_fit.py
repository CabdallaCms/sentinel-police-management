#!/usr/bin/env python3
"""Print-template contract tests for application.html / certificate.html.

The templates are the OFFICIAL SOURCE BLUEPRINTS (Somali application form +
bilingual certificate of good conduct), hard-overwritten from the attached
sources. This suite pins that contract:

  1. EXACT A4 PRINT RULES — the blueprint @page rules (application:
     `@page{size:A4;margin:0}` + `.page{padding:6mm 8mm 4mm 8mm}`;
     certificate: `@page { size: A4 portrait; margin: 0; }`), the added
     print-color-adjust: exact, and all web chrome hidden on paper.
  2. OFFICIAL EMBLEM PLACEMENT — application.html carries the emblem ONLY as
     the centred low-opacity watermark (top 52% / left 50%, opacity 0.08,
     z-index 2 above nothing behind content z-index 1); certificate.html
     carries it in BOTH the letterhead masthead (.logo-wrap) AND the centred
     watermark (z-index 10).
  3. DYNAMIC BINDINGS — every id the client-side scripts bind (all applicant
     identity fields, purpose, guardian/guarantor, photo boxes, certificate
     number/issue date, officer line) survives, together with the fetch
     endpoints, token auth and the mandatory 12-hour review-lock logic.
  4. BLUEPRINT FIDELITY — the official titles, Somali section headers,
     Arabic letterhead block, footer text and the certificate search-result
     wording are present verbatim.
  5. SINGLE-PAGE HEIGHT BUDGET — a conservative worst-case estimate of the
     printed content height (computed from the actual CSS values, generous
     wrap allowances included) fits one A4 page (@page margin 0 -> 297mm)
     with a documented safety slack.

Usage:  python3 backend/test_print_fit.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)

PT_TO_MM = 25.4 / 72.0          # 1pt = 0.3528mm
PX_TO_MM = 25.4 / 96.0          # CSS px at 96dpi
A4_H_MM = 297.0                 # @page margin is 0 in both blueprints
SAFETY_MM = 8.0                 # engine rounding slack we insist on
OPACITY_MIN, OPACITY_MAX = 0.08, 0.12   # watermark band from the spec

FAILURES = []


def check(name, ok, detail=''):
    print(('ok: ' if ok else 'FAIL: ') + name + ((' -> ' + detail) if detail and not ok else ''))
    if not ok:
        FAILURES.append(name)


def strip_comments(html):
    """Remove HTML comments (blueprint notes mention {% static %} verbatim)."""
    return re.sub(r'<!--.*?-->', '', html, flags=re.S)


def css_block(html, selector):
    """Return the body of the last `selector{...}` rule (no nesting in our CSS)."""
    out = []
    for m in re.finditer(re.escape(selector) + r'\s*\{([^}]*)\}', html):
        out.append(m.group(1))
    return out[-1] if out else ''


def nested_block(html, opener, first=True):
    """Return the body of `opener { ... }` with proper brace matching
    (needed for @media print blocks that contain nested rules)."""
    pattern = re.escape(opener) + r'\s*\{'
    m = None
    for it in re.finditer(pattern, html):
        m = it
        if first:
            break
    if not m:
        return ''
    i = m.end()                      # just after the opening '{'
    depth, j = 1, i
    while j < len(html) and depth:
        if html[j] == '{':
            depth += 1
        elif html[j] == '}':
            depth -= 1
        j += 1
    return html[i:j - 1] if depth == 0 else ''


def all_print_blocks(html):
    """Concatenate every @media print block (blueprint + added chrome rules)."""
    out = []
    for m in re.finditer(r'@media print\s*\{', html):
        out.append(nested_block(html[m.start():], '@media print'))
    return ' '.join(out)


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
# Load templates (HTML comments stripped: the blueprint notes quote
# {% static %} verbatim, which is documentation — not an unresolved tag)
# ---------------------------------------------------------------------------
app = strip_comments(open(os.path.join(PROJECT, 'application.html'), encoding='utf-8').read())
cert = strip_comments(open(os.path.join(PROJECT, 'certificate.html'), encoding='utf-8').read())

# ---------------------------------------------------------------------------
# 1. Exact A4 print rules (the blueprint @page rules, verbatim)
# ---------------------------------------------------------------------------
# application.html — blueprint print block
app_print = nested_block(app, '@media print')
check('application.html: blueprint @page rule (@page{size:A4;margin:0})',
      '@page{size:A4;margin:0}' in app_print.replace(' ', ''))
check('application.html: blueprint .page print padding (6mm 8mm 4mm 8mm)',
      'padding:6mm8mm4mm8mm' in app_print.replace(' ', ''))
check('application.html: SINGLE-SHEET FIX (.page min-height dropped on paper)',
      'min-height:0' in app_print.replace(' ', '') and 'height:auto' in app_print.replace(' ', ''))
# certificate.html — blueprint top-level @page + print block
check('certificate.html: blueprint @page rule (size: A4 portrait; margin: 0)',
      bool(re.search(r'@page\s*\{\s*size:\s*A4 portrait\s*;\s*margin:\s*0\s*;\s*\}', cert)))
cert_print = nested_block(cert, '@media print')
check('certificate.html: print block keeps cream sheet + drops shadow/margin',
      '#FFF9E7' in cert_print and 'margin:0' in cert_print.replace(' ', '')
      and 'box-shadow:none' in cert_print.replace(' ', ''))

for name, html, hide in (('application.html', app, ['.toolbar', '.lockbar', '.toast']),
                         ('certificate.html', cert, ['.toolbar'])):
    pb = all_print_blocks(html)
    for sel in hide:
        shown = re.search(re.escape(sel) + r'[^{]*\{[^}]*display:\s*none', pb)
        check(f'{name}: {sel} hidden when printing', bool(shown))
    flat = pb.replace(' ', '')
    check(f'{name}: print-color-adjust: exact (incl. -webkit prefix)',
          'print-color-adjust:exact!important' in flat
          and '-webkit-print-color-adjust:exact!important' in flat)

# ---------------------------------------------------------------------------
# 2. Official emblem placement
# ---------------------------------------------------------------------------
check('application.html: emblem appears exactly ONCE (watermark only)',
      app.count('images/police_logo.png') == 1)
check('application.html: no Django static tag left unresolved',
      '{% static' not in app and '{{' not in app)
app_wm = css_block(app, '.watermark')
check('application.html: watermark at top 52% / left 50% + translate (blueprint)',
      'top:52%' in app_wm.replace(' ', '') and 'left:50%' in app_wm.replace(' ', '')
      and 'translate(-50%,-50%)' in app_wm.replace(' ', ''))
opacity = unitless(app_wm, 'opacity')
check('application.html: watermark opacity 0.08 (inside the 0.08-0.12 band)',
      opacity is not None and OPACITY_MIN <= opacity <= OPACITY_MAX, f'opacity={opacity}')
check('application.html: watermark behind the content (z-index 2 vs content 1)',
      'z-index:2' in app_wm.replace(' ', '')
      and 'z-index:1' in css_block(app, '.content').replace(' ', ''))

check('certificate.html: emblem appears exactly TWICE (masthead + watermark)',
      cert.count('images/police_logo.png') == 2)
check('certificate.html: no Django static tag left unresolved',
      '{% static' not in cert and '{{' not in cert)
cert_wm = css_block(cert, '.watermark')
check('certificate.html: watermark at top 52% / left 50% + translate (blueprint)',
      'top:52%' in cert_wm.replace(' ', '') and 'left:50%' in cert_wm.replace(' ', '')
      and 'translate(-50%,-50%)' in cert_wm.replace(' ', ''))
opacity = unitless(cert_wm, 'opacity')
check('certificate.html: watermark opacity 0.08 (inside the 0.08-0.12 band)',
      opacity is not None and OPACITY_MIN <= opacity <= OPACITY_MAX, f'opacity={opacity}')
check('certificate.html: crest in the letterhead masthead (.logo-wrap img)',
      '.logo-wrap img' in cert and num(css_block(cert, '.letterhead .logo-wrap img'), 'width') > 0)
check('certificate.html: watermark above the sheet (blueprint z-index 10)',
      'z-index:10' in cert_wm.replace(' ', ''))
sig = css_block(cert, '.sig-block')
check('certificate.html: signature block centred above the footer bar',
      'margin:26pxauto0auto' in sig.replace(' ', '') and 'text-align:center' in sig.replace(' ', ''))

# ---------------------------------------------------------------------------
# 3.5 Official emblem asset (blue-and-silver circular seal, transparent bg)
# ---------------------------------------------------------------------------
import struct as _struct
with open(os.path.join(PROJECT, 'images', 'police_logo.png'), 'rb') as _f:
    _png = _f.read()
_w, _h = _struct.unpack('>II', _png[16:24])
check('images/police_logo.png: PNG asset present and square (seal)',
      _png[:8] == b'\x89PNG\r\n\x1a\n' and _w == _h and _w >= 512,
      f'{_w}x{_h}')
check('images/police_logo.png: alpha channel (transparent outside the ring)',
      _png[25] == 6, f'colortype={_png[25]}')

# ---------------------------------------------------------------------------
# 3. Dynamic bindings, endpoints, auth and the 12h review lock
# ---------------------------------------------------------------------------
APP_IDS = ['statusBadge', 'approveBtn', 'lockbar', 'toast', 'photoContainer',
           'appFullName', 'appMotherName', 'appNationalId', 'appPassport',
           'appDob', 'appPob', 'appGender', 'appPhone', 'appEmail', 'appAddress',
           'appPurpose',
           'guarantorName', 'guarantorId', 'guarantorRel', 'guarantorPhone',
           'guarantorAddr', 'guarantorOcc']
for el in APP_IDS:
    check(f'application.html: #{el} present', f'id="{el}"' in app)

CERT_IDS = ['statusBadge', 'printBtn', 'sheet', 'certNumber', 'certIssued',
            'certFullName', 'certMotherName', 'certDob', 'certPob',
            'certNationality', 'certPassport', 'certNationalId',
            'certResidence', 'certOccupation', 'certPurpose', 'certOfficer',
            'certPhotoBox']
for el in CERT_IDS:
    check(f'certificate.html: #{el} present', f'id="{el}"' in cert)

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
check('application.html: 35x45 mm photo caption + applicant photo binding',
      '35×45 mm' in app and 'applicant_photo||a.photo_path' in app.replace(' ', ''))
check('certificate.html: unlock gate (approved + certificate number)',
      "a.status==='Approved'&&a.certificate_number" in cert)
check('certificate.html: long-date + uppercase filters mirrored (d F Y / upper)',
      'function dmyLong(' in cert and 'function upper(' in cert)

# ---------------------------------------------------------------------------
# 4. Blueprint fidelity (official wording, verbatim)
# ---------------------------------------------------------------------------
for marker in ['CODSIGA SHAHAADADA DAMBI-LA\'AANTA',
               'NORTHEASTERN POLICE FORCE • CRIMINAL INVESTIGATION DIRECTORATE (2026)',
               'PCC-2026-DIGITAL-01',
               'QAYBTA 01', 'QAYBTA 02', 'QAYBTA 03', 'QAYBTA 04',
               'MAGACA SHARCIGA AH OO BUUXA', 'DAMMIINKA (GUARANTOR)',
               'OGOLAANSHAHA &amp; SAXIIXA DAMMIINKA', 'OGOLAANSHAHA &amp; SAXIIXA CODSAHA',
               'Hoggaanka Baadhista Dembiyada Ee DG.Waqooyi Bari Soomaaliya',
               'Waaxda Faraha Iyo Hubinta', '+252-2754131',
               '<html lang="so">']:
    check(f'application.html: blueprint marker `{marker[:44]}`', marker in app)

for marker in ['CERTIFICATE OF GOOD CONDUCT', '(POLICE CLEARANCE CERTIFICATE)',
               'TO WHOM IT MAY CONCERN', 'NO ADVERSE CRIMINAL RECORD FOUND',
               'Las Anod, HQ', 'North East Police Force',
               'Criminal Investigation Directorate',
               'قوة شرطة ولاية الشمال الشرقي', 'مديرية التحقيقات الجنآئي',
               'HOGAANKA BAADHISTA DEMBIYADA DG WAQOOYI BARI SOOMAALIYA',
               'WAAXDA FARAHA EE KAYDINTA IYO HUBINTA DEMBILA\'AANTA',
               'Six (6) Months from date of issue',
               'Chief of Fingerprint Unit', 'Dhamme. Shugri Jaamac Diiriye',
               'Hogaanka Baadhista Dembiyada Ee DG.Waqooyi Bari Soomaaliya-Waaxda Faraha Iyo  Hubinta +252-2754131',
               '<html lang="en">']:
    check(f'certificate.html: blueprint marker `{marker[:44]}`', marker in cert)

# ---------------------------------------------------------------------------
# 5. Single-page height budget (worst case; @page margin 0 -> 297mm usable)
# ---------------------------------------------------------------------------
avail = A4_H_MM


def budget_application():
    """Conservative worst-case printed height of application.html, in mm."""
    h = 0.0
    # header: 2 lines + underline padding + rule + bottom margin
    h += (line_mm(css_block(app, '.hdr .t1'), 9, 1.3)
          + line_mm(css_block(app, '.hdr .t2'), 9.5, 1.3)
          + 3 * PX_TO_MM + 2 * PX_TO_MM + num(css_block(app, '.hdr'), 'margin-bottom', 1.06))
    # title + margins
    ti = css_block(app, '.title')
    h += line_mm(ti, 15, 1.3) + num(ti, 'margin-top', 1.06) + num(ti, 'margin-bottom', 0.79)
    # photo: 36mm box + border + caption + wrap margins
    h += (36.0 + 3 * PX_TO_MM + line_mm(css_block(app, '.photo-cap'), 7, 1.35)
          + 1 * PX_TO_MM + 2 * PX_TO_MM + 3 * PX_TO_MM)
    # intro: 2 justified lines + margins
    h += 2 * line_mm(css_block(app, '.intro'), 8.5, 1.3) + 2 * PX_TO_MM + 4 * PX_TO_MM
    # four section bars (3px vertical padding each)
    sec = css_block(app, '.sec')
    h += 4 * (line_mm(sec, 9, 1.3) + 6 * PX_TO_MM + num(sec, 'margin-top', 0.79))
    # grid rows: bold label stacked over the 9.5pt value line (inline style)
    row_h = (line_mm(css_block(app, '.lab'), 8.5, 1.3) + 9.5 * PT_TO_MM * 1.3
             + 2 * PX_TO_MM + 6 * PX_TO_MM + 1 * PX_TO_MM)
    h += 6 * row_h + 2 * 9.5 * PT_TO_MM * 1.3       # Section 01 + 2 wrap allowances
    # Section 02 purpose box
    h += 10 * PT_TO_MM * 1.35 + 8 * PX_TO_MM + 2 * PX_TO_MM
    h += 3 * row_h + 9.5 * PT_TO_MM * 1.3           # Section 03 + 1 wrap allowance
    # Section 04: two declaration boxes (3 body lines + signature line each)
    stm, body, sig = css_block(app, '.stm'), css_block(app, '.stm .body'), css_block(app, '.sig')
    one = (2 * num(stm, 'padding-top', 0.79) + 1 * PX_TO_MM
           + 3 * line_mm(body, 8, 1.3)
           + num(sig, 'margin-top', 0.79) + 9 * PX_TO_MM + line_mm(sig, 8.5, 1.3))
    h += 2 * one + 2 * num(stm, 'margin-top', 0.53)
    # footer
    h += (num(css_block(app, '.foot'), 'margin-top', 1.32) + 2 * PX_TO_MM
          + line_mm(css_block(app, '.foot .body'), 8.5, 1.35) + 8 * PX_TO_MM)
    return h


def budget_certificate():
    """Conservative worst-case printed height of certificate.html, in mm."""
    h = 0.0
    # letterhead block (blueprint min-height, scaled up to fill the page)
    h += num(css_block(cert, '.letterhead'), 'min-height', 35.7)
    # two Somali header lines + divider + margins
    hl = css_block(cert, '.header-line')
    h += 2 * (line_mm(hl, 11, 1.45) + num(hl, 'margin-top', 1.06))
    dv = css_block(cert, '.divider')
    h += num(dv, 'height', 0.53) + num(dv, 'margin-top', 1.59) + num(dv, 'margin-bottom', 2.12)
    # titles
    h += (line_mm(css_block(cert, '.main-title'), 16, 1.45) + 4 * PX_TO_MM
          + line_mm(css_block(cert, '.sub-title'), 10.5, 1.45) + 2 * PX_TO_MM)
    # HQ line + meta + to-whom
    h += (num(css_block(cert, '.hq-line'), 'margin-top', 3.7) + line_mm(css_block(cert, '.hq-line'), 10.5, 1.45))
    h += (num(css_block(cert, '.cert-meta'), 'margin-top', 0.79) + line_mm(css_block(cert, '.cert-meta'), 10.5, 1.45))
    tw = css_block(cert, '.to-whom')
    h += num(tw, 'margin-top', 4.23) + line_mm(tw, 11, 1.45)
    # intro body: 3 justified lines
    bt = css_block(cert, '.body-text')
    h += 3 * line_mm(bt, 10, 1.45) + num(bt, 'margin-top', 1.85)
    # details table: 10 rows (header + 9 fields) beside a 150px photo box
    dtd = css_block(cert, 'table.details td')
    rows_h = 10 * (line_mm(dtd, 10.5, 1.45) + 6 * PX_TO_MM) + 5 * PX_TO_MM
    photo_h = num(css_block(cert, '.photo-box'), 'height', 39.69) + 2 * PX_TO_MM
    h += max(rows_h, photo_h) + num(css_block(cert, '.details-wrap'), 'margin-top', 3.17)
    # search-result heading + 5 lines
    sh = css_block(cert, '.section-heading')
    h += num(sh, 'margin-top', 4.76) + line_mm(sh, 11, 1.45)
    h += 5 * line_mm(bt, 10, 1.45) + num(bt, 'margin-top', 1.85)
    # purpose + validity meta rows
    mr = css_block(cert, '.meta-row')
    h += 2 * (num(mr, 'margin-top', 2.12) + line_mm(mr, 10.5, 1.45))
    # signature block (centered)
    sb = css_block(cert, '.sig-block')
    h += (num(sb, 'margin-top', 6.88) + line_mm(css_block(cert, '.sig-line'), 10.5, 1.45)
          + 4 * PX_TO_MM + line_mm(css_block(cert, '.closing-name'), 10.5, 1.45) + 2 * PX_TO_MM
          + line_mm(css_block(cert, '.closing-role'), 10, 1.45) + 1 * PX_TO_MM)
    # footer-bar is absolutely positioned -> no flow height
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
