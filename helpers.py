from flask import redirect, session
from functools import wraps

import re

from email_validator import validate_email, EmailNotValidError
from flask_mail import Mail, Message




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

# splits list into sublist 
def paginate (list, per_page):
    if not per_page:
        per_page = 10
    pages = [list[x:x+per_page] for x in range(0, len(list), per_page)]
    return pages


def validateEmail (email):
    try:
        emailInfo = validate_email(email, check_deliverability=True)
        return emailInfo.normalized
    except EmailNotValidError as e:
        return e
    


def validatePass(password, repeatPass):
            if password != repeatPass:
                return 'password not matching'
            elif len(password) < 3:
                return 'password too short'
            # currently no need for additional security check

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