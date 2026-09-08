"""
Bookshelf 1.0 (legacy)

The original 2024 version of the app, kept online as-is for portfolio purposes with
stability fixes only. Version 2.0 is being built separately; see README.md.
"""
import os
import re
import secrets
from base64 import b64decode, b64encode
from io import BytesIO
from random import choice
from uuid import uuid4

from cs50 import SQL
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from itsdangerous import URLSafeTimedSerializer
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash

from api_requests import get_book_data, search_for_books
from helpers import login_required, paginate, validateEmail, validatePass, validateUser
from image import check_file_type, compress, open_image, to_rgb

try:
    # Barcode decoding needs the zbar system library. The app must still boot without it.
    from pyzbar.pyzbar import decode as decode_barcode
except Exception:  # ImportError, or OSError when libzbar is missing
    decode_barcode = None

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail as SendGridMail
except ImportError:
    SendGridAPIClient = None
    SendGridMail = None

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv('BOOKSHELF_DB', os.path.join(BASE_DIR, 'bookshelf.db'))
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema.sql')

# Image paths are stored in the database in this relative form (the original app did this),
# and turned into URLs by the `image_url` template filter.
BOOK_IMG_DIR = 'static/book_img'
SHELF_IMG_DIR = 'static/shelf_img'
GENERIC_BOOK_COVER = 'static/book_img/generic_book.jpg'
GENERIC_SHELF_IMAGE = './static/shelf_img/generic.png'

BOOKS_PER_PAGE = 5
APP_VERSION = '1.0'
# Shown in the footer on every page. Point it at version 2.0 once that is live.
V2_URL = os.getenv('V2_URL', 'https://github.com/taskotale/bookshelf')
# "Explore as Guest" logs visitors into this account.
DEMO_USER_ID = int(os.getenv('DEMO_USER_ID', '1'))
# Guests cannot add, edit or delete anything, so a stranger cannot wipe the demo data.
DEMO_READ_ONLY = os.getenv('DEMO_READ_ONLY', '1') != '0'

app = Flask(__name__)

secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    # Without a secret key Flask cannot sign sessions and every page would crash.
    # Fall back to a per-process key so the app still runs; sessions just won't survive a restart.
    print('WARNING: SECRET_KEY is not set. Using a temporary key; add SECRET_KEY to .env.')
    secret_key = secrets.token_hex(32)
app.config['SECRET_KEY'] = secret_key
app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT', 'bookshelf-password-reset')
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(BASE_DIR, 'flask_session')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # uploads bigger than 16 MB get a friendly error
Session(app)


def abs_path(relative):
    """Turn a DB-stored path like './static/x.jpg' into an absolute filesystem path."""
    return os.path.join(BASE_DIR, relative.lstrip('./'))


def open_database():
    """Open the SQLite database, creating it from schema.sql on first run."""
    fresh = not os.path.exists(DB_PATH)
    if fresh:
        open(DB_PATH, 'a').close()
    database = SQL('sqlite:///' + DB_PATH)
    if fresh:
        with open(SCHEMA_PATH) as schema:
            for statement in schema.read().split(';'):
                if statement.strip():
                    database.execute(statement.strip() + ';')
        # A guest account so "Explore as Guest" works on a fresh install (id 1).
        database.execute(
            "INSERT INTO users (username, hash, email) VALUES (?, ?, ?);",
            'guest', generate_password_hash(secrets.token_hex(16)), None,
        )
    return database


db = open_database()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_filename(text):
    """Keep only characters that are safe in a filename."""
    return re.sub(r'[^\w.-]', '', text, flags=re.UNICODE)[:80] or 'book'


def get_books():
    return db.execute(
        "SELECT id, title, author, image FROM books WHERE user_id = ? ORDER BY id;", session['user_id'])


def get_book(book_id):
    """A book that belongs to the logged-in user, or None."""
    if book_id is None:
        return None
    rows = db.execute("SELECT * FROM books WHERE id = ? AND user_id = ?;", book_id, session['user_id'])
    return rows[0] if rows else None


def get_shelf(shelf_id):
    """A bookshelf that belongs to the logged-in user, or None."""
    if shelf_id is None:
        return None
    rows = db.execute("SELECT * FROM bookshelves WHERE id = ? AND user_id = ?;", shelf_id, session['user_id'])
    return rows[0] if rows else None


def user_bookshelves():
    return db.execute(
        "SELECT id, width, height, description, image FROM bookshelves WHERE user_id = ? ORDER BY id;",
        session['user_id'])


def demo_blocked(redirect_to='/'):
    """Return a redirect if the guest account tries to change something."""
    if DEMO_READ_ONLY and session.get('demo'):
        flash('The guest account is read-only. Register your own account to add and edit books.')
        return redirect(redirect_to)
    return None


def generic_book_cover():
    img = Image.open(abs_path(GENERIC_BOOK_COVER))
    img.load()
    return img


def cover_to_base64(cover):
    buffer = BytesIO()
    to_rgb(cover).save(buffer, format='JPEG')
    return b64encode(buffer.getvalue()).decode('utf-8')


def remove_file_if_unused(relative_path):
    """Delete a stored image unless another row still points at it."""
    if not relative_path or relative_path == GENERIC_SHELF_IMAGE or relative_path == GENERIC_BOOK_COVER:
        return
    still_used = db.execute("SELECT COUNT(*) AS n FROM books WHERE image = ?;", relative_path)[0]['n']
    if still_used:
        return
    try:
        os.remove(abs_path(relative_path))
    except OSError:
        pass


@app.template_filter('image_url')
def image_url(path):
    """DB paths look like 'static/book_img/x.jpg' or './static/shelf_img/x.jpg'."""
    if not path:
        return url_for('static', filename='book_img/generic_book.jpg')
    relative = path.lstrip('./')
    if relative.startswith('static/'):
        relative = relative[len('static/'):]
    return url_for('static', filename=relative)


@app.context_processor
def inject_globals():
    return {
        'app_version': APP_VERSION,
        'v2_url': V2_URL,
        'demo_read_only': DEMO_READ_ONLY and session.get('demo', False),
    }


@app.after_request
def after_request(response):
    # Pages must not be cached (they depend on who is logged in); images may be.
    if not request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Expires'] = '0'
        response.headers['Pragma'] = 'no-cache'
    return response


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', code=404, message="That page doesn't exist."), 404


@app.errorhandler(413)
def too_large(error):
    return render_template('error.html', code=413, message='That file is too large. Please upload an image under 16 MB.'), 413


@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', code=500, message='Something went wrong on our side. Please try again.'), 500


# ---------------------------------------------------------------------------
# Password reset (kept minimal: it only works when SendGrid is configured)
# ---------------------------------------------------------------------------
def generate_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])


def confirm_token(token, expiration=1800):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        return serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=expiration)
    except Exception:
        return False


def send_reset_email(user_email):
    api_key = os.getenv('SENDGRID_API_KEY')
    sender = os.getenv('MAIL_DEFAULT_SENDER')
    if not (SendGridAPIClient and api_key and sender):
        return 'Password reset by email is not available in this version. Please contact the site owner.'

    reset_url = url_for('reset_password', token=generate_token(user_email), _external=True)
    message = SendGridMail(
        from_email=sender,
        to_emails=user_email,
        subject='Bookshelf password reset',
        html_content=(
            '<p>Click the link below to choose a new Bookshelf password. It is valid for 30 minutes.</p>'
            f'<p><a href="{reset_url}">{reset_url}</a></p>'
        ),
    )
    try:
        SendGridAPIClient(api_key).send(message)
    except Exception as e:
        print(f'SendGrid error: {e}')
        return 'We could not send the reset email right now. Please try again later.'
    return 'We sent an email with a link to reset your password.'


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset_email = confirm_token(token)
    if not reset_email:
        return render_template('login.html', message='Link is not valid or expired')

    rows = db.execute("SELECT id, username FROM users WHERE email = ?;", reset_email)
    if not rows:
        return render_template('login.html', message='Link is not valid or expired')
    user = rows[0]

    if request.method == 'POST':
        new_password = request.form.get('new-password') or ''
        confirmation = request.form.get('confirmation') or ''
        valid = validatePass(new_password, confirmation)
        if valid is not True:
            return render_template('reset_password.html', username=user['username'], token=token, message=valid)
        db.execute("UPDATE users SET hash = ? WHERE id = ?;", generate_password_hash(new_password), user['id'])
        return render_template('login.html', message='Password successfully changed')

    return render_template('reset_password.html', username=user['username'], token=token)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------
@app.route('/')
@login_required
def index():
    user_id = session['user_id']
    query = (request.args.get('find') or '').strip()
    message = 'Your book collection'
    books = []

    if query:
        pattern = '%' + query + '%'
        books = db.execute(
            "SELECT id, title, author, image FROM books WHERE user_id = ? AND (title LIKE ? OR author LIKE ?) ORDER BY id;",
            user_id, pattern, pattern)
        if books:
            message = f'Found in your collection: {query}'
        else:
            books = search_for_books(query)
            if books:
                message = f'Not on your shelf. Online results for "{query}"'
            else:
                message = f'Nothing found for "{query}", on your shelf or online.'
    elif request.args.get('shelf_id') is not None:
        shelf = get_shelf(to_int(request.args.get('shelf_id')))
        if shelf is None:
            flash('That bookshelf does not exist.')
            return redirect(url_for('browse'))
        books = db.execute(
            "SELECT id, title, author, image FROM books WHERE bookshelf_id = ? AND user_id = ? ORDER BY location_y, location_x;",
            shelf['id'], user_id)
        message = f"Books on {shelf['description']}" if books else f"No books on {shelf['description']} yet"
    elif request.args.get('random'):
        unread = db.execute(
            "SELECT id, title, author, image FROM books WHERE user_id = ? AND status IS NULL;", user_id)
        if unread:
            books = [choice(unread)]
            message = 'How about this one?'
        else:
            message = 'No unread books left. Time to add some!'
    elif request.args.get('borrowed'):
        books = db.execute(
            "SELECT id, title, author, image FROM books WHERE user_id = ? AND borrowed IS NOT NULL ORDER BY id;", user_id)
        message = 'Books you have lent out' if books else 'You have not lent out any books'
    else:
        books = get_books()
        if not books:
            message = 'Your shelf is empty. Add your first book!'

    pages = paginate(books, BOOKS_PER_PAGE) or [[]]
    page = to_int(request.args.get('page')) or 0
    page = max(0, min(page, len(pages) - 1))
    nav_args = request.args.to_dict()
    nav_args.pop('page', None)

    return render_template(
        'index.html', books=pages[page], page_num=page, total=len(pages) - 1,
        message=message, book_num=len(books), nav_args=nav_args)


@app.route('/add_book', methods=['GET', 'POST'])
@login_required
def add_book():
    if request.method != 'POST':
        return render_template('add_book.html')
    blocked = demo_blocked(url_for('add_book'))
    if blocked:
        return blocked

    input_type = request.form.get('add')
    book = None

    if input_type == 'isbn':
        isbn = re.sub(r'[^0-9Xx]', '', request.form.get('isbn') or '')
        if not isbn:
            return render_template('add_book.html', message='Please enter an ISBN')
        book = get_book_data(isbn)
        if not book:
            return render_template('add_book.html', message='No book found for that ISBN. Try again or add it manually.')

    elif input_type == 'manual':
        title = (request.form.get('title') or '').strip()
        author = (request.form.get('author') or '').strip()
        if not title or not author:
            return render_template('add_book.html', message='Title and author are required')
        cover = None
        upload = request.files.get('manual_image')
        if upload and upload.filename:
            if not check_file_type(upload):
                return render_template('add_book.html', message='File not supported. Please upload a JPG, PNG, GIF or WebP image.')
            cover = open_image(upload)
            if cover is None:
                return render_template('add_book.html', message='That file could not be read as an image.')
            cover.thumbnail((400, 600))
        if cover is None:
            cover = generic_book_cover()
        book = {
            'title': title.title(),
            'author': [author.title()],
            'language': (request.form.get('language') or 'EN').upper(),
            'cover': cover,
        }

    elif input_type == 'bc-img':
        if decode_barcode is None:
            return render_template('add_book.html', message='Barcode scanning is not available on this server. Use ISBN or manual entry.')
        upload = request.files.get('barcode_img')
        if not upload or not upload.filename:
            return render_template('add_book.html', message='Please choose a photo of the barcode')
        if not check_file_type(upload):
            return render_template('add_book.html', message='File not supported. Please upload a JPG, PNG, GIF or WebP image.')
        photo = open_image(upload)
        if photo is None:
            return render_template('add_book.html', message='That file could not be read as an image.')
        digits = None
        for code in decode_barcode(photo):
            match = re.search(r'\d{10,13}', code.data.decode('utf-8', 'ignore'))
            if match:
                digits = match.group(0)
                break
        if not digits:
            return render_template('add_book.html', message='No barcode found in that photo. Make sure it is sharp, horizontal and well lit.')
        book = get_book_data(digits)
        if not book:
            return render_template('add_book.html', message=f'Barcode {digits} was read, but no book was found for it. Try adding it manually.')

    else:
        return render_template('add_book.html', message='Please pick how you want to add the book')

    session['book'] = book
    return redirect('/add_book_confirm')


@app.route('/add_book_from_find', methods=['POST'])
@login_required
def book_from_find():
    blocked = demo_blocked('/')
    if blocked:
        return blocked
    title = (request.form.get('title') or '').strip()
    author = (request.form.get('author') or '').strip()
    if not title:
        flash('That search result had no title.')
        return redirect('/')
    cover = None
    encoded = request.form.get('cover')
    if encoded:
        try:
            cover = Image.open(BytesIO(b64decode(encoded)))
            cover.load()
        except Exception:
            cover = None
    if cover is None:
        cover = generic_book_cover()
    session['book'] = {
        'title': title.title(),
        'author': [author.title() or 'Unknown Author'],
        'language': (request.form.get('language') or 'EN').upper(),
        'cover': cover,
    }
    return redirect('/add_book_confirm')


@app.route('/add_book_confirm', methods=['GET', 'POST'])
@login_required
def confirm_book():
    book = session.get('book')
    if not book:
        return redirect('/add_book')

    if request.method == 'POST':
        if request.form.get('confirm') == 'first':
            book['status'] = 'True' if request.form.get('status') else None
            shelf = get_shelf(to_int(request.form.get('bookshelf_choice')))
            if shelf is None:
                book.pop('bookshelf_id', None)
                session['book'] = book
                return redirect('/added_book')
            book['bookshelf_id'] = shelf['id']
            session['book'] = book
            if not shelf['image']:
                shelf['image'] = GENERIC_SHELF_IMAGE
            return render_template('add_book_confirm.html', message='Where on this bookshelf?', selected=shelf)

        # second step: position on the shelf
        shelf = get_shelf(book.get('bookshelf_id'))
        height = to_int(request.form.get('height')) or 1
        width = to_int(request.form.get('width')) or 1
        if shelf:
            height = max(1, min(height, shelf['height']))
            width = max(1, min(width, shelf['width']))
        book['location_y'] = height
        book['location_x'] = width
        session['book'] = book
        return redirect('/added_book')

    # GET: show what we found and ask for status / shelf
    if isinstance(book['author'], list):
        book['author'] = [', '.join(book['author'])]
        session['book'] = book
    author_text = book['author'][0] if isinstance(book['author'], list) else book['author']

    duplicate = db.execute(
        "SELECT id FROM books WHERE title = ? AND author = ? AND user_id = ?;",
        book['title'], author_text, session['user_id'])
    message = f"You already have this book: {book['title']}. Add anyway?" if duplicate else None
    return render_template(
        'add_book_confirm.html', book=book, cover=cover_to_base64(book['cover']),
        bookshelves=user_bookshelves(), message=message)


@app.route('/added_book')
@login_required
def push_book_to_db():
    book = session.get('book')
    if not book:
        return redirect('/add_book')
    blocked = demo_blocked('/')
    if blocked:
        return blocked

    author = ', '.join(book['author']) if isinstance(book['author'], list) else str(book['author'])
    path = ''
    if book.get('cover') is not None:
        filename = f"{safe_filename(book['title'] + author)}-{uuid4().hex[:8]}.jpg"
        path = f'{BOOK_IMG_DIR}/{filename}'
        os.makedirs(abs_path(BOOK_IMG_DIR), exist_ok=True)
        to_rgb(book['cover']).save(abs_path(path), 'JPEG', quality=85)

    shelf = get_shelf(book.get('bookshelf_id'))
    db.execute(
        "INSERT INTO books (title, author, language, image, location_x, location_y, user_id, status, bookshelf_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
        book['title'], author, (book.get('language') or 'EN').upper(), path,
        book.get('location_x') if shelf else None, book.get('location_y') if shelf else None,
        session['user_id'], book.get('status'), shelf['id'] if shelf else None)

    session.pop('book', None)
    message = f"Added {book['title']}"
    if shelf:
        message += f" to {shelf['description']}"
    flash(message)
    return redirect('/')


@app.route('/add_bookshelf', methods=['GET', 'POST'])
@login_required
def add_bookshelf():
    if request.method != 'POST':
        return render_template('add_bookshelf.html')
    blocked = demo_blocked(url_for('add_bookshelf'))
    if blocked:
        return blocked

    width = to_int(request.form.get('width'))
    height = to_int(request.form.get('height'))
    description = (request.form.get('description') or '').strip()
    if not description:
        return render_template('add_bookshelf.html', message='Please give the shelf a name')
    if not width or not height or width < 1 or height < 1 or width > 100 or height > 100:
        return render_template('add_bookshelf.html', message='Please insert a valid bookshelf size (1 to 100)')

    photo = None
    upload = request.files.get('image')
    if upload and upload.filename:
        if not check_file_type(upload):
            return render_template('add_bookshelf.html', message='File not supported. Please upload a JPG, PNG, GIF or WebP image.')
        photo = open_image(upload)
        if photo is None:
            return render_template('add_bookshelf.html', message='That file could not be read as an image.')

    shelf_id = db.execute(
        "INSERT INTO bookshelves (width, height, description, image, user_id) VALUES (?, ?, ?, ?, ?);",
        width, height, description, GENERIC_SHELF_IMAGE, session['user_id'])
    if photo is not None:
        path = f'./{SHELF_IMG_DIR}/bsi{shelf_id}.jpg'
        os.makedirs(abs_path(SHELF_IMG_DIR), exist_ok=True)
        compress(photo, abs_path(path))
        db.execute("UPDATE bookshelves SET image = ? WHERE id = ?;", path, shelf_id)

    flash(f'Added the shelf "{description}"')
    return redirect(url_for('browse'))


@app.route('/book_details', methods=['GET', 'POST'])
@login_required
def book_details():
    if request.method == 'POST':
        blocked = demo_blocked('/')
        if blocked:
            return blocked
        data = request.form
        book = get_book(to_int(data.get('book_id')))
        if book is None:
            flash('Book not found.')
            return redirect('/')

        if data.get('submit') == 'delete':
            db.execute("DELETE FROM books WHERE id = ? AND user_id = ?;", book['id'], session['user_id'])
            remove_file_if_unused(book['image'])
            flash(f"Deleted {book['title']}")
            return redirect('/')

        title = (data.get('title') or '').strip() or book['title']
        author = (data.get('author') or '').strip() or book['author']
        language = (data.get('language') or book['language'] or 'EN').upper()
        status = 'True' if data.get('status') else None
        borrowed = 'True' if data.get('borrowed') else None
        note = (data.get('note') or '').strip() or None

        bookshelf_id, loc_x, loc_y = book['bookshelf_id'], book['location_x'], book['location_y']
        shelf_choice = data.get('location-input')
        if borrowed:
            # a lent-out book is not on any shelf
            bookshelf_id, loc_x, loc_y = None, None, None
        elif shelf_choice is not None:
            shelf = get_shelf(to_int(shelf_choice))
            if shelf is None:
                bookshelf_id, loc_x, loc_y = None, None, None
            else:
                new_x = to_int(data.get('selected-max-width'))
                new_y = to_int(data.get('selected-max-height'))
                if shelf['id'] != bookshelf_id or new_x is not None or new_y is not None:
                    loc_x = max(1, min(new_x or 1, shelf['width']))
                    loc_y = max(1, min(new_y or 1, shelf['height']))
                bookshelf_id = shelf['id']

        db.execute(
            "UPDATE books SET title = ?, author = ?, language = ?, location_y = ?, location_x = ?, status = ?, "
            "borrowed = ?, note = ?, bookshelf_id = ? WHERE id = ? AND user_id = ?;",
            title, author, language, loc_y, loc_x, status, borrowed, note, bookshelf_id,
            book['id'], session['user_id'])
        flash(f'Saved {title}')
        return redirect(url_for('index', page=to_int(data.get('page')) or 0))

    book = get_book(to_int(request.args.get('id')))
    if book is None:
        flash('Book not found.')
        return redirect('/')
    if book['note'] in (None, 'None'):
        book['note'] = ''
    book['language'] = (book['language'] or 'EN').upper()

    # the collection stays visible behind the modal
    books = get_books()
    pages = paginate(books, BOOKS_PER_PAGE) or [[]]
    page = to_int(request.args.get('page')) or 0
    page = max(0, min(page, len(pages) - 1))

    shelf = db.execute("SELECT description FROM bookshelves WHERE id = ?;", book['bookshelf_id']) if book['bookshelf_id'] else []
    return render_template(
        'book_details.html', books=pages[page], page_num=page, total=len(pages) - 1,
        message='Your book collection', book_num=len(books), nav_args={},
        book_details=book, shelf=shelf, bookshelves=user_bookshelves())


@app.route('/browse', methods=['GET', 'POST'])
@login_required
def browse():
    if request.method == 'POST':
        blocked = demo_blocked(url_for('browse'))
        if blocked:
            return blocked
        shelf = get_shelf(to_int(request.form.get('delete')))
        if shelf is None:
            flash('That bookshelf does not exist.')
        else:
            count = db.execute(
                "SELECT COUNT(*) AS n FROM books WHERE bookshelf_id = ? AND user_id = ?;",
                shelf['id'], session['user_id'])[0]['n']
            if count:
                flash("You can't delete a bookshelf that has books on it. Move them first.")
            else:
                db.execute("DELETE FROM bookshelves WHERE id = ? AND user_id = ?;", shelf['id'], session['user_id'])
                if shelf['image'] and shelf['image'] != GENERIC_SHELF_IMAGE:
                    try:
                        os.remove(abs_path(shelf['image']))
                    except OSError:
                        pass
                flash(f"Deleted the shelf \"{shelf['description']}\"")
        return redirect(url_for('browse'))

    return render_template('browse.html', bookshelves=user_bookshelves(), message='Your shelves')


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    session.clear()

    if request.method == 'POST':
        if request.form.get('demo_login') == 'true':
            if not db.execute("SELECT id FROM users WHERE id = ?;", DEMO_USER_ID):
                return render_template('login.html', message='The guest account is not set up on this server yet.')
            session['user_id'] = DEMO_USER_ID
            session['demo'] = True
            return redirect('/')

        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if not username:
            return render_template('login.html', message='Please input name')
        if not password:
            return render_template('login.html', message='Please input password')

        user = db.execute("SELECT * FROM users WHERE username = ?;", username)
        if len(user) != 1 or not check_password_hash(user[0]['hash'], password):
            return render_template('login.html', message='Username or password incorrect')

        session['user_id'] = user[0]['id']
        return redirect('/')

    return render_template('login.html')


@app.route('/forgot_password', methods=['GET', 'POST'])
def changePassword():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        if not email:
            return render_template('forgot_password.html', message='Please enter your email address')
        if not db.execute("SELECT id FROM users WHERE email = ?;", email):
            return render_template('forgot_password.html', message='There is no account with that email address.')
        return render_template('login.html', message=send_reset_email(email))
    return render_template('forgot_password.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method != 'POST':
        return render_template('register.html')

    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    repeatPass = request.form.get('confirmation') or ''
    email = (request.form.get('user-email') or '').strip()

    if not username:
        return render_template('register.html', message='Please input name')
    if not email:
        return render_template('register.html', message='Please enter email')
    if not password:
        return render_template('register.html', message='Please input password')
    if not repeatPass:
        return render_template('register.html', message='Please confirm password')

    user_exist = db.execute("SELECT username FROM users WHERE username = ?;", username)
    email_exist = db.execute("SELECT email FROM users WHERE email = ?;", email)

    validName = validateUser(user_exist, email_exist)
    if validName is not True:
        return render_template('register.html', message=validName)
    validEmail = validateEmail(email)
    if isinstance(validEmail, ValueError):
        return render_template('register.html', message=str(validEmail))
    validPass = validatePass(password, repeatPass)
    if validPass is not True:
        return render_template('register.html', message=validPass)

    user_id = db.execute(
        "INSERT INTO users (username, hash, email) VALUES (?, ?, ?);",
        username, generate_password_hash(password), validEmail)
    session.clear()
    session['user_id'] = user_id
    flash(f'Welcome, {username}! Start by adding a book or building a shelf.')
    return redirect('/')
