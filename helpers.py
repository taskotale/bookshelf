import re
from functools import wraps

from email_validator import EmailNotValidError, validate_email
from flask import redirect, session


def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/0.12/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def paginate(items, per_page):
    """Split a list into a list of pages (sublists)."""
    if not per_page:
        per_page = 10
    return [items[x:x + per_page] for x in range(0, len(items), per_page)]


def validateEmail(email):
    """Return the normalized email, or the EmailNotValidError explaining why it is invalid."""
    try:
        # No DNS deliverability check: it needs outbound DNS, which shared hosts may block,
        # and a failed lookup used to make registration impossible.
        info = validate_email(email, check_deliverability=False)
        return info.normalized
    except EmailNotValidError as e:
        return e


def validatePass(password, repeatPass):
    if password != repeatPass:
        return 'password not matching'
    elif len(password) < 3:
        return 'password too short'
    elif not re.search('[a-z]', password):
        return 'password must contain a lower case letter'
    elif not re.search('[A-Z]', password):
        return 'password must contain a capital letter'
    elif not re.search('[0-9]', password):
        return 'password must contain a number'
    else:
        return True


def validateUser(user_exist, email_exist):
    if user_exist != []:
        return 'username already exists'
    elif email_exist != []:
        return 'email already registered'
    else:
        return True
