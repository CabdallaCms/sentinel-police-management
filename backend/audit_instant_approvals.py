#!/usr/bin/env python3
"""Find clearance applications that were approved before the mandatory
12-hour review period elapsed.

A stale backend (one started before the review lock existed) approves
anything instantly. This tool walks the database, reconstructs who approved
each application and when, and lists every approval that broke the rule —
so the damage can be undone instead of guessed at.

Usage
-----
    python3 backend/audit_instant_approvals.py                 # report only
    python3 backend/audit_instant_approvals.py --revert        # undo them
    python3 backend/audit_instant_approvals.py --json          # machine output

Reverting sets the row back to 'Pending Review', clears the certificate
number and the reviewed_at stamp, and writes an audit event. The row then
falls under the normal gate again: it stays locked until
created_at + 12 hours.

Exit status is 1 when violations are found (and 0 when the database is
clean), so the command can be wired into a start-up check.
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('SENTINEL_DB', os.path.join(ROOT, 'sentinel.db'))
WINDOW_HOURS = 12.0

ADMIN_ROLE_KEYS = {'systemadmin', 'admin', 'administrator', 'sysadmin', 'superuser'}


def parse_stamp(value):
    """Parse a SQLite / ISO-8601 timestamp into an aware UTC datetime, or None."""
    s = (value or '').strip()
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        dt = None
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                dt = datetime.datetime.strptime(s.split('.', 1)[0], fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def approver_role(conn, application_id):
    """Role recorded by the APPROVE audit event for `application_id`.

    The handler writes details like "CL-12345678 by FingerprintUnit", so the
    role is whatever follows the last ' by '. Older builds that predate the
    gate may have no event at all — in that case the approval is treated as
    unattributed and, if it was too fast, reported as a violation.
    """
    row = conn.execute(
        "SELECT details FROM audit_events WHERE action='APPROVE' "
        "AND entity='clearance_application' AND entity_id=? ORDER BY id DESC LIMIT 1",
        (application_id,)).fetchone()
    if not row or not row['details']:
        return None
    match = re.search(r'\bby\s+(.+?)\s*(?:\(|$|\s{2,})', str(row['details']))
    if match:
        return match.group(1).strip()
    return str(row['details']).strip()


def is_admin_role(role):
    """Administrators legitimately bypass the review window."""
    return re.sub(r'[^a-z]', '', (role or '').lower()) in ADMIN_ROLE_KEYS


def scan(conn):
    """Return (violations, admin_bypassed) for the clearance register.

    `violations` holds every approval that broke the mandatory 12-hour review
    period. Approvals made by an administrator are not violations: the
    administrator bypass is part of the policy, not a defect.
    """
    violations, admin_bypassed = [], []
    rows = conn.execute(
        "SELECT application_id, purpose, status, certificate_number, "
        "created_at, reviewed_at FROM clearance_applications").fetchall()
    for row in rows:
        if (row['status'] or '').strip().lower() != 'approved':
            continue
        created = parse_stamp(row['created_at'])
        reviewed = parse_stamp(row['reviewed_at'])
        role = approver_role(conn, row['application_id'])
        if is_admin_role(role):
            # Administrators are exempt from the review period by design.
            admin_bypassed.append({'application_id': row['application_id'],
                                   'certificate_number': row['certificate_number'],
                                   'approved_by_role': role,
                                   'reviewed_at': row['reviewed_at']})
            continue
        if reviewed is None or created is None:
            # approved_at/created_at unusable -> cannot prove the window elapsed
            violations.append({
                'application_id': row['application_id'],
                'purpose': row['purpose'],
                'certificate_number': row['certificate_number'],
                'created_at': row['created_at'],
                'reviewed_at': row['reviewed_at'],
                'hours_elapsed': None,
                'hours_short': None,
                'approved_by_role': role,
                'violation': 'timestamp unusable — the 12h window cannot be proven',
            })
            continue
        hours = (reviewed - created).total_seconds() / 3600.0
        if hours >= WINDOW_HOURS:
            continue
        violations.append({
            'application_id': row['application_id'],
            'purpose': row['purpose'],
            'certificate_number': row['certificate_number'],
            'created_at': row['created_at'],
            'reviewed_at': row['reviewed_at'],
            'hours_elapsed': round(hours, 2),
            'hours_short': round(WINDOW_HOURS - hours, 2),
            'approved_by_role': role,
            'violation': f'approved {round(WINDOW_HOURS - hours, 2)}h before the '
                         f'mandatory {int(WINDOW_HOURS)}h review window closed',
        })
    return violations, admin_bypassed


def revert(conn, violations):
    """Put the listed applications back to 'Pending Review'."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    for item in violations:
        conn.execute(
            "UPDATE clearance_applications SET status='Pending Review', "
            "certificate_number=NULL, reviewed_at=NULL WHERE application_id=?",
            (item['application_id'],))
        conn.execute(
            "INSERT INTO audit_events(user_id,action,entity,entity_id,details) "
            "VALUES(?,?,?,?,?)",
            (None, 'REVERT', 'clearance_application', item['application_id'],
             f"approval reverted by audit_instant_approvals: {item['violation']}; "
             f"certificate {item['certificate_number']} voided at {now}"))
    conn.commit()
    return len(violations)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', default=DB_PATH, help='path to sentinel.db')
    ap.add_argument('--revert', action='store_true',
                    help='set violating applications back to Pending Review')
    ap.add_argument('--json', action='store_true', help='emit JSON')
    ap.add_argument('--yes', action='store_true', help='do not prompt before reverting')
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print(f'no database at {args.db}', file=sys.stderr)
        return 2

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    violations, admin_bypassed = scan(conn)

    if args.json:
        print(json.dumps({'database': os.path.abspath(args.db),
                          'window_hours': WINDOW_HOURS,
                          'violations': violations,
                          'admin_bypassed': admin_bypassed}, indent=2))
    else:
        print(f'database      : {os.path.abspath(args.db)}')
        print(f'review window : {int(WINDOW_HOURS)}h (administrators may bypass)')
        total = conn.execute("SELECT COUNT(*) FROM clearance_applications "
                             "WHERE status='Approved'").fetchone()[0]
        print(f'approved rows : {total}')
        print(f'violations    : {len(violations)}')
        print(f'admin bypasses: {len(admin_bypassed)} (allowed by policy)')
        for item in violations:
            print(f"  - {item['application_id']}  {item['purpose'] or '?'}")
            print(f"      created  {item['created_at']}   reviewed {item['reviewed_at']}")
            print(f"      by {item['approved_by_role'] or 'unknown'}")
            print(f"      {item['violation']}")

    if violations and args.revert:
        actionable = list(violations)
        if not args.yes and not args.json:
            answer = input(f'\nrevert {len(actionable)} approval(s) to Pending Review? [y/N] ')
            if answer.strip().lower() not in ('y', 'yes'):
                print('nothing reverted')
                return 1
        count = revert(conn, actionable)
        print(f'reverted {count} approval(s) — each is now Pending Review and '
              f'locked until created_at + {int(WINDOW_HOURS)}h')

    conn.close()
    return 1 if violations else 0


if __name__ == '__main__':
    sys.exit(main())
