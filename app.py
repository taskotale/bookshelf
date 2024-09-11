import re
import os

from api_requests import get_book_data, search_for_books
from base64 import b64encode, b64decode
from cs50 import SQL
from flask import Flask, redirect, render_template, request, session, url_for
from flask_session import Session
from helpers import login_required, paginate, validateEmail, validatePass, validateUser
from io import BytesIO
from image import compress, check_file_type
from PIL import Image  # delete after transferring to separate file.py
from pyzbar.pyzbar import decode
from random import choice
from werkzeug.security import check_password_hash, generate_password_hash

from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv

# using helper function for login required

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

app.config['SECURITY_PASSWORD_SALT'] = os.getenv("SECURITY_PASSWORD_SALT")
# mail sending config
app.config['MAIL_SERVER'] = 'live.smtp.mailtrap.io'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = ('api')
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")


mail = Mail(app)
## TEST CHANGE

def generate_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])


def confirm_token(token, expiration=1800):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=expiration
        )
        return email
    except Exception:
        return False


def send(userEmail):
    message = Message(
        subject='test hello',
        recipients=[userEmail],
        sender=('Tahir from BOOKSHELF app', 'noreply@mujic.me')
    )
    token = generate_token(userEmail)
    reset_url = url_for('reset_password', token=token, _external=True)
    message.body = reset_url
    mail.send(message)
    return 'message sent'


db_path = 'bookshelf.db'

# Check if the database file exists
if os.path.exists(db_path):
    # Database exists, use the relative path
    db = SQL('sqlite:///bookshelf.db')
else:
    # Database doesn't exist, use absolute path
    db = SQL('sqlite:////home/taskotale/bookshelf/bookshelf.db')

app.config['SESSION_PERMANENT'] = False
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)


@app.after_request
def after_request(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Expires'] = 0
    response.headers['Pragma'] = 'no-cache'
    return response


def get_books():
    books = db.execute(
        "SELECT id, title, author, image FROM books WHERE user_id=?", session['user_id'])
    return books


books_to_show = ['']


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset_email = confirm_token(token)

    if not reset_email:
        return render_template('login.html', message='Link is not valid or expired')
    if request.method == 'POST':
        user = db.execute(
            "SELECT * FROM users WHERE email = ?;", reset_email
        )
        user_id = user[0]['id']
        user_email = user[0]['email']
        username = user[0]['username']
        new_password = request.form.get('new-password')
        confirmation = request.form.get('confirmation')
        # make logic for pass change stopped here
        if reset_email == user_email:
            validNewPassword = validatePass(new_password, confirmation)
            print(validNewPassword)
            if validNewPassword == True:
                hash_new_password = generate_password_hash(new_password)
                db.execute(
                    "UPDATE users SET hash = ? WHERE id = ?;", hash_new_password, user_id
                )
            else:
                return render_template('reset_password.html', username=username, token=token, message=validNewPassword)
        else:
            return render_template('reset_password.html', username=username, token=token, message='Something went wrong. Please try again')
        return render_template('login.html', message='Password Successfully Changed')
    else:
        user = db.execute(
            "SELECT * FROM users WHERE email = ?;", reset_email
        )
        username = user[0]['username']
        return render_template('reset_password.html', username=username, token=token)


@app.route('/')
@login_required
def index():
    query_request = str(request.args.get('find'))
    bookshelves_request = str(request.args.get('shelf_id'))
    random = request.args.get('random')
    borrowed = request.args.get('borrowed')
    message = 'Your book collection'
    if query_request != 'None':
        # added for potential deeper search
        # query_request_split = query_request.split()
        books = db.execute("SELECT id,title, author, image FROM books WHERE user_id = ? AND title LIKE ? OR author LIKE ?;",
                           session['user_id'], '%'+query_request+'%', '%'+query_request+'%')
        if books == []:
            message = 'You dont have this book but you can check it out online!'
            books = search_for_books(query_request)
            if books == None:
                books = []
        else:
            message = 'Search result for: ' + query_request.title()
    elif bookshelves_request != 'None':
        books = db.execute(
            "SELECT id,title, author, image FROM books WHERE bookshelf_id = ?", bookshelves_request)
        shelf_desc = db.execute(
            "SELECT description FROM bookshelves WHERE id = ?;", bookshelves_request)
        message = 'You have these books on ' + shelf_desc[0]['description']
    elif random:
        unread_books = db.execute(
            "SELECT id,title, author, image FROM books WHERE user_id=? AND status IS NULL", session['user_id'])
        books = [choice(unread_books)]
    elif borrowed:
        books = db.execute(
            "SELECT id, title, author, image FROM books WHERE user_id=? AND borrowed IS NOT NULL", session[
                'user_id']
        )
    else:
        books = get_books()

    if books == []:
        message = 'Book not found'

    page = request.args.get('page', 0, type=int)
    pages = paginate(books, 5)
    if pages == []:
        pages.append('')
    books_to_show[0] = pages

    return render_template('index.html', books=pages[page], page_num=page, total=len(pages)-1, message=message, book_num=len(books))


@app.route('/add_book', methods=['GET', 'POST'])
@login_required
def add_book():
    if request.method == 'POST':
        input_type = request.form.get('add')

        if input_type == 'isbn':
            isbn = request.form.get('isbn')
            if isbn == '':
                return render_template('add_book.html', message='Please input something'), 404
            book = get_book_data(isbn)
            if book == False:
                return render_template('add_book.html', message='Please Try Again Or input Manually'), 404

        elif input_type == 'manual':
            manual_image = request.files['manual_image']
            if manual_image:
                if check_file_type(manual_image):
                    cover = Image.open(manual_image)
                    cover.resize((128, 196))
                else:
                    return render_template('add_book.html', message='File not supported')
            else:
                cover = Image.open('static/book_img/generic_book.jpg')
            book = {
                'title': request.form.get('title').title().strip(),
                'author': [request.form.get('author').title().strip()],
                'language': request.form.get('language').lower(),
                'cover': cover
            }

        elif input_type == 'bc-img':
            uploaded_image = request.files['barcode_img']
            if check_file_type(uploaded_image):
                image = Image.open(uploaded_image)
            else:
                return render_template('add_book.html', message='File not supported')

            barcode = decode(image)
            barcode = str(barcode[0][0])
            barcode = re.findall('\d+', barcode)[0]
            book = get_book_data(barcode)

        session['book'] = book
        return redirect('/add_book_confirm')
        # return render_template('add_book.html', message='Successfully added: '+book['title'])
    else:
        return render_template('add_book.html')


@app.route('/add_book_from_find', methods=['GET', 'POST'])
@login_required
def book_from_find():
    encoded_image = request.form.get('cover')
    image_bytes = b64decode(encoded_image)
    image_bytes_io = BytesIO(image_bytes)
    cover = Image.open(image_bytes_io)
    book = {
        'title': request.form.get('title').title(),
        'author': [request.form.get('author').title()],
        'language': request.form.get('language').lower(),
        'cover': cover
    }
    session['book'] = book
    return redirect('/add_book_confirm')


@app.route('/add_book_confirm', methods=['GET', 'POST'])
@login_required
def confirm_book():
    book = session.get('book')
    if request.method == 'POST':
        get_action = request.form.get('confirm')
        if get_action == 'first':
            status = request.form.get('status')
            session['book'].update({
                'status': status
            })
            selected_bookshelf = request.form.get('bookshelf_choice')
            if selected_bookshelf != 'None':
                selected_data = db.execute(
                    "SELECT image, height, width, description FROM bookshelves WHERE id=? AND user_id =?;", selected_bookshelf, session['user_id'])[0]
                if selected_data['image'] == None:
                    selected_data['image'] = './static/shelf_img/generic.png'
                session['book'].update({
                    'bookshelf_id': selected_bookshelf
                })
                return render_template('add_book_confirm.html', message='Where on this bookshelf?', selected=selected_data)
            else:
                return redirect('/added_book')
        else:
            height = request.form.get('height')
            width = request.form.get('width')
            session['book'].update({
                'location_x': width,
                'location_y': height
            })
            return redirect('/added_book')
    else:
        image = book['cover']
        image_bytes = BytesIO()
        image.save(image_bytes, format='JPEG')
        image_bytes = image_bytes.getvalue()
        encoded_image = b64encode(image_bytes).decode('utf-8')
        if len(book['author']) != 1:
            authors = ''
            for auth in book['author']:
                authors += auth + ', '
            book['author'] = [authors[:-2]]

        bookshelves = db.execute(
            "SELECT id, description FROM bookshelves WHERE user_id =?;", session['user_id'])
        check_duplicate = db.execute(
            "SELECT id FROM books WHERE title = ? AND author = ? AND language = ? AND user_id = ?",
            book['title'], book['author'], book['language'], session['user_id'])
        if check_duplicate != []:
            return render_template('add_book_confirm.html', message='You already have this book: ' + book['title'] + '\nAdd anyway?',
                                   book=book, cover=encoded_image, bookshelves=bookshelves)
        return render_template('add_book_confirm.html', book=book, cover=encoded_image, bookshelves=bookshelves)


@app.route('/added_book')
@login_required
def push_book_to_db():
    book = session.get('book')
    # save cover image if any
    path = ''
    if book['cover'] != None:
        authors = ''
        # since author is a list with multiple possible authors
        # making a string out of it so we can concat in a str
        for author in book['author']:
            authors += author

        authors = authors.replace('/', '_')
        book_title = book['title'].replace('/', '_')
        path = 'static/book_img/' + book_title + authors + '.jpg'
        path = path.replace(' ', '')

        book['cover'].save(path, quality=100)

    message = "Successfully added" + book['title']

    if 'bookshelf_id' in book:
        shelf = db.execute(
            "SELECT description FROM bookshelves WHERE id = ?;", book['bookshelf_id'])
        message += ' on ' + shelf[0]['description'] + ' shelf'
        db.execute("INSERT INTO books (title, author, language, image, location_x, location_y, user_id, status, bookshelf_id) VALUES (?,?,?,?,?,?,?,?,?);",
                   book['title'], book['author'], book['language'], path, book['location_x'], book['location_y'],
                   session['user_id'], book['status'], book['bookshelf_id'])
    else:
        db.execute("INSERT INTO books (title, author, language, image, user_id, status) VALUES (?,?,?,?,?,?);",
                   book['title'], book['author'], book['language'], path, session['user_id'], book['status'])

    session.pop('book')

    return redirect('/')


@app.route('/add_bookshelf', methods=['GET', 'POST'])
@login_required
def add_bookshelf():
    if request.method == 'POST':
        width = request.form.get('width')
        height = request.form.get('height')
        description = request.form.get('description')

        # using the PIL module for image manipulation
        uploaded_image = request.files['image']

        # transfer image function to separate .py

        if width.isnumeric() and height.isnumeric() and int(width) > 0 and int(height) > 0:
            width = int(width)
            height = int(height)
            db.execute("INSERT INTO bookshelves (width, height, description, user_id) VALUES (?,?,?,?);",
                       width, height, description, session['user_id'])
            bookshelf_id = db.execute(
                "SELECT id FROM bookshelves WHERE user_id = ? ORDER BY id DESC LIMIT 1;", session['user_id'])
            if uploaded_image:
                if not check_file_type(uploaded_image):
                    return render_template('add_bookshelf.html', message='File not supported')
                path = './static/shelf_img/' + 'bsi' + \
                    str(bookshelf_id[0]['id']) + '.jpg'
                db.execute("UPDATE bookshelves SET image = ? WHERE id =?;",
                           path, bookshelf_id[0]['id'])
                compress(uploaded_image, path)
            else:
                db.execute("UPDATE bookshelves SET image = ? WHERE id =?;",
                           './static/shelf_img/generic.png', bookshelf_id[0]['id'])

            return render_template('add_bookshelf.html', message='Successfully Added')
        else:
            return render_template('add_bookshelf.html', message='Please insert a valid bookshelf size')
    else:
        return render_template('add_bookshelf.html')


@app.route('/book_details', methods=['GET', 'POST'])
@login_required
def book_details():
    if request.method == 'POST':

        data = request.form
        loc_x = data['selected-max-width']
        loc_y = data['selected-max-height']
        if 'location-input' in data:
            loc = data['location-input']

        if data['submit'] == 'delete':
            book_id = data['book_id']
            db.execute("DELETE FROM books WHERE id =?;", book_id)
            return redirect('/')

        if 'status' in data:
            status = data['status']
        else:
            status = None
        if 'borrowed' in data:
            borrowed = data['borrowed']
            loc = 'None'
        else:
            borrowed = None

        if 'note' in data:
            note = data['note']
            if note == '':
                note = 'None'
        else:
            note = 'None'

        if loc == 'None':
            loc_y = None
            loc_x = None
            loc = (None,)

        # current = db.execute(
        #     "SELECT bookshelf_id from books where id = ? ", data['edit-book'])
        db.execute(
            "UPDATE books SET title = ?, author = ?, language = ?, location_y = ?, location_x = ?, status = ?, borrowed =?, note = ?, bookshelf_id = ? WHERE id = ?;",
            data['title'], data['author'], data['language'], loc_y, loc_x, status, borrowed, note,
            loc, data['book_id']
        )
        return redirect('/')
    else:
        page = request.args.get('page', 0, type=int)

        book_id = request.args.get('id')
        book_details = db.execute(
            "SELECT id, title, author, language, status, borrowed, note, bookshelf_id, location_x, location_y FROM books WHERE id = ?;", book_id
        )
        shelf = db.execute(
            "SELECT description FROM bookshelves WHERE id=?;", book_details[0]['bookshelf_id'])

        bookshelves = db.execute(
            "SELECT id, width, height, description FROM bookshelves WHERE user_id =?;", session['user_id'])
        # return render_template('index.html', books=pages[page], page_num=page, total=len(pages)-1)
        return render_template('book_details.html', books=books_to_show[0][page], book_details=book_details[0], shelf=shelf, bookshelves=bookshelves)


@app.route('/browse')
@login_required
def browse():
    message = 'Your shelves'
    if 'delete' in request.args:
        shelf_id = request.args.get('delete')
        check_books = db.execute(
            "SELECT COUNT (*) AS count FROM books WHERE bookshelf_id = ?;", shelf_id)
        if check_books[0]['count'] < 1:
            shelf = db.execute(
                "SELECT description, image FROM bookshelves WHERE id = ? AND user_id =?;", shelf_id, session['user_id'])
            if shelf[0]['image'] != './static/shelf_img/generic.png':
                os.remove(shelf[0]['image'])
            db.execute("DELETE FROM bookshelves WHERE id = ? AND user_id =?;",
                       shelf_id, session['user_id'])
            message = 'successfully deleted'
        else:
            message = 'You cant delete a bookshelf that has books on it'

    bookshelves = db.execute(
        "SELECT id, width, height, description, image FROM bookshelves WHERE user_id =?;", session['user_id'])
    return render_template('browse.html', bookshelves=bookshelves, message=message)

# reused code from previous problem for login, logout and register


@app.route('/login', methods=['GET', 'POST'])
def login():
    # clear if any user already connected
    session.clear()

    if request.method == 'POST':
        if not request.form.get('username'):
            return render_template('login.html', message='Please input name')
        elif not request.form.get('password'):
            return render_template('login.html', message='Please input password')

        user = db.execute(
            "SELECT * FROM users WHERE username = ?",
            request.form.get('username')
        )

        if len(user) != 1 or not check_password_hash(
            user[0]['hash'], request.form.get('password')
        ):
            return render_template('login.html', message='Username or password incorrect')

        # Remember which user has logged in
        session['user_id'] = user[0]['id']

        # successful login
        return redirect('/')
    else:
        return render_template('login.html')


@app.route('/forgot_password', methods=['GET', 'POST'])
def changePassword():
    if request.method == 'POST':
        email = request.form.get('email')
        existingUserEmail = db.execute(
            "SELECT email FROM users WHERE email = ?;", email
        )
        if existingUserEmail == []:
            return render_template('forgot_password.html', message='There is no user with this email in our database.\r\n Try registering a new account')
        else:
            send(email)
            return render_template('login.html', message='We sent you an email with the activation code')
    return render_template('forgot_password.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/register', methods=['GET', 'POST'])
def register():
    '''Register user'''
    if request.method == 'POST':
        #  first we get the posted info from the user
        username = request.form.get('username')
        password = request.form.get('password')
        repeatPass = request.form.get('confirmation')
        email = request.form.get('user-email')

        if not request.form.get('username'):
            return render_template('register.html', message='Please input name')
        elif not request.form.get('user-email'):
            return render_template('register.html', message='Please enter email')
        elif not request.form.get('password'):
            return render_template('register.html', message='Please input password')
        elif not request.form.get('confirmation'):
            return render_template('register.html', message='Please confirm password')

        user_exist = db.execute(
            "SELECT username FROM users WHERE username = ?;", username
        )
        email_exist = db.execute(
            "SELECT email FROM users WHERE email = ?;", email
        )

        validName = validateUser(user_exist, email_exist)
        validEmail = validateEmail(email)
        validPass = validatePass(password, repeatPass)

        if validName == True:
            if not isinstance(validEmail, ValueError):
                if validPass == True:
                    hash_password = generate_password_hash(password)
                    db.execute(
                        "INSERT INTO users (username, hash, email) VALUES (?, ?, ?);",
                        username,
                        hash_password,
                        email,
                    )
                    return redirect('/')
                else:
                    # error not (validPass)
                    return render_template('register.html', message=validPass)
            else:
                return render_template('register.html', message=validEmail)
        else:
            # error not valid (validName)
            return render_template('register.html', message=validName)
    else:
        return render_template('register.html')
