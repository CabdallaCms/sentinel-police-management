"""Directorate & specialised-service routes (Phase 3).  Called from app.server for every /api path it does not own.

    GET   /api/directorate/vocabularies | /api/directorate/units
    Clearance  (intake local, decision / signing / printing national)
      POST  /api/clearance-applications            {unit, purpose, applicant:{...}, applicant_photo, applicant_docs[], guardian:{...}, ...}
      GET   /api/clearance-applications?status=&unit=&person=
      GET   /api/clearance-applications/{ref}
      POST  /api/clearance-applications/{ref}/decision   {decision: approve|reject, notes}     (also /approve, /reject)
      GET   /api/clearance-applications/{ref}/certificate           signed certificate (not logged)
      POST  /api/clearance-applications/{ref}/print                 signed certificate + print log entry
      GET   /api/verify/{certificate_number}       PUBLIC, no login: validity + masked holder
    CID
      POST/GET /api/crime-cases           GET/PATCH /api/crime-cases/{ref}
      POST /api/crime-cases/{ref}/evidence | /participants
      GET/POST /api/suspect-alerts        POST /api/suspect-alerts/{ref}/lift   {reason}
    HR
      POST/GET /api/officers              GET /api/officers/{ref}      POST /api/officers/{ref}/duty-status {status, reason}
      POST/GET /api/conduct (also /submit) GET /api/conduct/{ref}      POST /api/conduct/{ref}/review {decision, notes}
    Administration (data, not code)
      GET/POST /api/admin/units           PATCH /api/admin/units/{code}   POST /api/admin/units/{code}/move {parent}
      GET/POST /api/admin/assignments     POST /api/admin/assignments/{id}/revoke
"""
import re

from ..identity.errors import ValidationError
from . import cid, clearance, conduct, officers, structure

REF = r'([A-Za-z0-9][A-Za-z0-9-]{2,63})'


def _q(qs, key):
    v = (qs.get(key) or [''])[0].strip()
    return v or None


def _n(qs, key, default):
    try:
        return int((qs.get(key) or [default])[0])
    except ValueError:
        return default


def public_verify(conn, number: str):
    return clearance.verify_public(conn, number)


def route(conn, actor, method, path, qs, body):
    """-> (result, status) or None when the path is not ours."""
    if path == '/api/directorate/vocabularies' and method == 'GET':
        return structure.vocabularies(conn, actor), 200
    if path == '/api/directorate/units' and method == 'GET':
        return structure.directorate_units(conn, actor), 200

    # ---- clearance ------------------------------------------------------------------------------
    if path == '/api/clearance-applications':
        if method == 'POST':
            return clearance.file_application(conn, actor, body), 201
        if method == 'GET':
            return clearance.list_applications(conn, actor, status=_q(qs, 'status'), unit=_q(qs, 'unit'),
                                               person_ref=_q(qs, 'person'), limit=_n(qs, 'limit', 50)), 200
    m = re.match(r'^/api/clearance-applications/' + REF + r'(?:/(decision|approve|reject|certificate|print))?$', path)
    if m:
        ref, act = m.groups()
        if act is None and method == 'GET':
            return clearance.get_application(conn, actor, ref), 200
        if act in ('decision', 'approve', 'reject') and method == 'POST':
            decision = body.get('decision') if act == 'decision' else act
            return clearance.decide(conn, actor, ref, decision, body.get('notes')), 200
        if act == 'certificate' and method == 'GET':
            return clearance.certificate(conn, actor, ref, log_print=False), 200
        if act == 'print' and method == 'POST':
            return clearance.certificate(conn, actor, ref, log_print=True), 200

    # ---- CID ------------------------------------------------------------------------------------
    if path == '/api/crime-cases':
        if method == 'POST':
            return cid.create_case(conn, actor, body), 201
        if method == 'GET':
            return cid.list_cases(conn, actor, status=_q(qs, 'status'), q=_q(qs, 'q'), limit=_n(qs, 'limit', 50)), 200
    m = re.match(r'^/api/crime-cases/' + REF + r'(?:/(evidence|participants))?$', path)
    if m:
        ref, sub = m.groups()
        if sub is None and method == 'GET':
            return cid.get_case(conn, actor, ref), 200
        if sub is None and method == 'PATCH':
            changes = body.get('changes', body)
            if not isinstance(changes, dict):
                raise ValidationError('`changes` must be an object')
            return cid.update_case(conn, actor, ref, changes), 200
        if sub == 'evidence' and method == 'POST':
            return cid.add_evidence(conn, actor, ref, body), 201
        if sub == 'participants' and method == 'POST':
            return cid.add_participants(conn, actor, ref, body), 201
    if path == '/api/suspect-alerts':
        if method == 'GET':
            return cid.list_alerts(conn, actor, status=_q(qs, 'status') or 'Active alert', limit=_n(qs, 'limit', 100)), 200
        if method == 'POST':
            return cid.create_alert(conn, actor, body), 201
    m = re.match(r'^/api/suspect-alerts/' + REF + r'/lift$', path)
    if m and method == 'POST':
        return cid.lift_alert(conn, actor, m.group(1), body.get('reason')), 200

    # ---- HR -------------------------------------------------------------------------------------
    if path == '/api/officers':
        if method == 'POST':
            return officers.register_officer(conn, actor, body), 201
        if method == 'GET':
            return officers.list_officers(conn, actor, q=_q(qs, 'q'), unit=_q(qs, 'unit'), duty_status=_q(qs, 'duty_status'),
                                          limit=_n(qs, 'limit', 100)), 200
    m = re.match(r'^/api/officers/' + REF + r'(?:/(duty-status))?$', path)
    if m:
        ref, sub = m.groups()
        if sub is None and method == 'GET':
            return officers.get_officer(conn, actor, ref), 200
        if sub and method == 'POST':
            return officers.set_duty_status(conn, actor, ref, body.get('status'), body.get('reason')), 200
    if path in ('/api/conduct', '/api/conduct/submit'):
        if method == 'POST':
            return conduct.submit(conn, actor, body), 201
        if method == 'GET' and path == '/api/conduct':
            return conduct.list_conduct(conn, actor, status=_q(qs, 'status'), officer=_q(qs, 'officer'),
                                        limit=_n(qs, 'limit', 100)), 200
    m = re.match(r'^/api/conduct/' + REF + r'(?:/(review))?$', path)
    if m:
        ref, sub = m.groups()
        if sub is None and method == 'GET':
            return conduct.get_conduct(conn, actor, ref), 200
        if sub and method == 'POST':
            return conduct.review(conn, actor, ref, body.get('decision'), body.get('notes')), 200

    # ---- administration ---------------------------------------------------------------------------
    if path == '/api/admin/units':
        if method == 'GET':
            return structure.list_units(conn, actor, parent=_q(qs, 'parent')), 200
        if method == 'POST':
            return structure.create_unit(conn, actor, body), 201
    m = re.match(r'^/api/admin/units/' + REF + r'(?:/(move))?$', path)
    if m:
        code, sub = m.groups()
        if sub is None and method == 'PATCH':
            return structure.update_unit(conn, actor, code, body.get('changes', body)), 200
        if sub == 'move' and method == 'POST':
            return structure.move_unit(conn, actor, code, body.get('parent')), 200
    if path == '/api/admin/assignments':
        if method == 'GET':
            return structure.list_assignments(conn, actor, unit=_q(qs, 'unit'), user=_q(qs, 'user')), 200
        if method == 'POST':
            return structure.grant(conn, actor, body), 201
    m = re.match(r'^/api/admin/assignments/(\d+)/revoke$', path)
    if m and method == 'POST':
        return structure.revoke(conn, actor, int(m.group(1))), 200
    return None
