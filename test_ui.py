#!/usr/bin/env python3
"""Structural regression tests for the Sentinel front end (index.html).

Standard library only — no browser, no packages. It parses the single-page app
and enforces the platform-wide UI contract:

  1. no right-side slide-out drawers remain anywhere
  2. every dialog is a centered modal over a dark blurred backdrop with a
     fixed header, internally scrolling body and sticky footer
  3. every register table lives in a fixed-height card with a sticky <thead>
  4. every table's rightmost column is a standardized "Actions" column
  5. status pills use the shared palette (red / green / blue / purple)
  6. every inline event handler and every literal getElementById target resolves
     (catches a renamed function or a removed element id)

Usage:
    python3 test_ui.py
"""
import re
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(ROOT, 'index.html')

FAILURES = []


def check(label, condition, detail=''):
    if condition:
        print('  PASS  ' + label)
    else:
        FAILURES.append(label)
        print('  FAIL  ' + label + (('  -> ' + str(detail)) if detail else ''))


def section(title):
    print('\n== ' + title + ' ==')


def main():
    src = open(HTML, encoding='utf-8').read()
    style = re.search(r'<style>(.*?)</style>', src, re.S).group(1)
    script = re.search(r'<script>(.*?)</script>', src, re.S).group(1)

    section('1 · drawers are fully removed')
    leftovers = [m for m in re.findall(r'[A-Za-z-]*[Dd]rawer[A-Za-z-]*', src)]
    check('no "drawer" identifier survives in HTML/CSS/JS', not leftovers, sorted(set(leftovers)))
    check('no slide-in right offset in CSS', 'right:-520px' not in style)

    section('2 · centered modal contract')
    check('backdrop element exists', 'id="overlay"' in src)
    check('modal dialog element exists', 'id="modal"' in src)
    check('modal has header / body / footer',
          all(x in src for x in ('class="modal-head"', 'id="modalBody"', 'id="modalFoot"')))
    check('close button calls closeModal()',
          re.search(r'class="iconbtn"[^>]*onclick="closeModal\(\)"', src) is not None)
    check('backdrop click closes the modal',
          'onclick="if(event.target===this)closeModal()"' in src)
    check('Escape key closes the modal', "e.key==='Escape'" in script)
    check('openModal / closeModal defined',
          'function openModal(' in script and 'function closeModal(' in script)
    check('modal is centred with flexbox',
          re.search(r'\.overlay\{[^}]*align-items:center[^}]*justify-content:center', style) is not None)
    check('backdrop is dark + backdrop-filter: blur(4px)',
          re.search(r'\.overlay\{[^}]*background:#[0-9a-f]{8}', style) is not None
          and 'backdrop-filter:blur(4px)' in style)
    check('body max-height:80vh with internal scroll only',
          re.search(r'\.modal-body\{[^}]*max-height:80vh[^}]*overflow-y:auto', style) is not None)
    check('header is pinned (position:sticky; top:0)',
          re.search(r'\.modal-head\{[^}]*position:sticky[^}]*top:0', style) is not None)
    check('footer is sticky at the bottom',
          re.search(r'\.modal-foot\{[^}]*position:sticky[^}]*bottom:0', style) is not None)
    check('background scroll is locked while a modal is open',
          'body.modal-open{overflow:hidden}' in style and "classList.add('modal-open')" in script)

    section('3 · table card + frozen column headers')
    check('table container has a fixed max-height calc(100vh - 280px)',
          re.search(r'\.table-wrap\{[^}]*max-height:calc\(100vh - 280px\)', style) is not None)
    check('table container scrolls internally',
          re.search(r'\.table-wrap\{[^}]*overflow:auto', style) is not None)
    check('<thead> is sticky at top:0',
          re.search(r'\.table thead,\.table thead th\{position:sticky;top:0', style) is not None)
    check('<thead> has a solid background colour',
          re.search(r'\.table thead,\.table thead th\{[^}]*background:#[0-9a-f]{6}', style) is not None)

    section('4 · every register table has a standardized Actions column')
    tables = re.findall(r'<table class="table">(.*?)</table>', src, re.S)
    check('found the 7 register tables', len(tables) == 7, len(tables))
    for i, t in enumerate(tables):
        head_block = re.search(r'<thead>.*?</thead>', t, re.S).group(0)
        # <th ...> only — must not match the <thead> tag itself
        heads = re.findall(r'<th(?:\s[^>]*)?>(.*?)</th>', head_block, re.S)
        last_th = re.findall(r'<th(?:\s[^>]*)?>', head_block)[-1]
        tbody = re.search(r'<tbody id="([^"]+)"', t)
        name = tbody.group(1) if tbody else 'table#%d' % i
        check('%s: header row has %d columns' % (name, len(heads)), len(heads) >= 4, len(heads))
        check('%s: rightmost column is "Actions"' % name,
              heads[-1].strip() == 'Actions' and 'col-actions' in last_th, heads[-1])
        check('%s: first column is "%s"' % (name, heads[0].strip()), heads[0].strip() != '', heads[0])
        check('%s: empty-state colspan matches %d columns' % (name, len(heads)),
              ('colspan="%d"' % len(heads)) in script)
    check('.col-actions cell style is defined', '.col-actions{' in style)

    section('5 · standardized status pill palette')
    for tone in ('red', 'green', 'blue', 'purple', 'amber', 'gray'):
        check('.badge.%s style defined' % tone, ('.badge.%s{' % tone) in style)
    tone_map = re.search(r'const BADGE_TONE=\{(.*?)\};', script, re.S).group(1)
    pairs = dict(re.findall(r"'([^']+)':'([a-z]+)'", tone_map))
    for text, expected in [('active alert', 'red'), ('flagged match', 'red'),
                           ('cleared', 'green'), ('no active alert', 'green'),
                           ('manual entry', 'blue'), ('direct intelligence listing', 'blue')]:
        check("'%s' -> %s pill" % (text, expected), pairs.get(text) == expected, pairs.get(text))
    check('linked case renders through casePill() as purple',
          "function casePill(caseId){return pill(caseId,'purple')}" in script)
    check('no ad-hoc badge colours left in the row renderers',
          not re.search(r'class="badge (red|green|blue|amber|gray)"', script))

    section('6 · every inline handler resolves to a defined function')
    defined = set(re.findall(r'function\s+([A-Za-z_$][\w$]*)\s*\(', script))
    defined |= set(re.findall(r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(', script))
    builtins = {'if', 'return', 'typeof', 'encodeURIComponent', 'String', 'Number', 'JSON', 'Math',
                'Array', 'Object', 'Date', 'parseInt', 'parseFloat', 'setTimeout', 'clearTimeout',
                'fetch', 'Promise', 'event', 'stopPropagation', 'preventDefault', 'new', 'await'}
    handlers = re.findall(r'on(?:click|input|change|submit)="([^"]*)"', src)
    check('found inline handlers to verify', len(handlers) > 10, len(handlers))
    called = set()
    for h in handlers:
        called |= set(re.findall(r'([A-Za-z_$][\w$]*)\s*\(', h))
    unknown = sorted(c for c in called - defined - builtins)
    check('all %d distinct handler functions are defined' % len(called), not unknown, unknown)

    section('7 · every literal element id used by the JS exists')
    static_ids = set(re.findall(r'id="([^"$]+)"', src))
    # ids generated from templates, e.g. id="${prefix}-first" with prefix 'cp' -> cp-first
    prefixes = {'cp', 'gd', 'pd', 'sp', 'fp', 'air', 'cw'}
    template_suffix = set(re.findall(r'id="\$\{prefix\}-([^"]+)"', src))
    template_plain = set(re.findall(r'id="\$\{prefix\}([^"]+)"', src))
    dynamic = set()
    for p in prefixes:
        dynamic |= {p + '-' + s for s in template_suffix}
        dynamic |= {p + s for s in template_plain}
    referenced = set(re.findall(r"getElementById\('([^']+)'\)", script))
    referenced |= set(re.findall(r"val\('([^']+)'\)", script))
    missing = sorted(r for r in referenced if r not in static_ids and r not in dynamic)
    check('all %d referenced ids exist' % len(referenced), not missing, missing)

    section('8 · every register tbody is written by a renderer')
    tbodies = set(re.findall(r'<tbody id="([^"]+)"', src))
    for tb in sorted(tbodies):
        check('%s is rendered' % tb, (tb + '.innerHTML=') in script or
              ("getElementById('%s')" % tb) in script)

    print()
    if FAILURES:
        print('%d UI CHECK(S) FAILED' % len(FAILURES))
        return 1
    print('ALL UI TESTS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
