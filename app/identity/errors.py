"""Service-level errors.  The HTTP adapter maps each to a status code."""


class IdentityError(Exception):
    status = 400
    code = 'error'

    def __init__(self, message, **extra):
        super().__init__(message)
        self.message = message
        self.extra = extra

    def payload(self):
        return {'error': self.code, 'message': self.message, **self.extra}


class PermissionDenied(IdentityError):
    status, code = 403, 'permission_denied'


class FieldLocked(IdentityError):
    """One or more locked identity fields would have been changed.  Nothing was written."""
    status, code = 403, 'field_locked'


class ValidationError(IdentityError):
    status, code = 422, 'validation_error'


class NotFound(IdentityError):
    status, code = 404, 'not_found'


class NeedsConfirmation(IdentityError):
    """A possible duplicate exists; the officer must link to it or explicitly confirm a new record."""
    status, code = 409, 'possible_duplicate'


class IdentifierInUse(IdentityError):
    status, code = 409, 'identifier_in_use'


class Duplicate(IdentityError):
    """The same record was already filed (e.g. the same passenger on the same flight and day)."""
    status, code = 409, 'duplicate_record'


class ReviewLocked(IdentityError):
    """The mandatory review window has not elapsed (legacy: HTTP 400 `review_period_active`)."""
    status, code = 400, 'review_period_active'
