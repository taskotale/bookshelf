import base64
import io

from PIL import Image

from conftest import page_text, register


def tiny_png_bytes():
    buffer = io.BytesIO()
    Image.new('RGBA', (8, 8), (255, 0, 0, 128)).save(buffer, format='PNG')
    return buffer.getvalue()


def add_manual_book(client, title='Test Book', author='Some Author', shelf=None, image=None):
    data = {'add': 'manual', 'title': title, 'author': author, 'language': 'en'}
    if image is not None:
        data['manual_image'] = (io.BytesIO(image), 'cover.png', 'image/png')
    response = client.post('/add_book', data=data, content_type='multipart/form-data')
    assert response.status_code == 302 and response.headers['Location'].endswith('/add_book_confirm')
    assert client.get('/add_book_confirm').status_code == 200
    response = client.post('/add_book_confirm', data={'confirm': 'first', 'bookshelf_choice': shelf or 'None'})
    if shelf:
        assert response.status_code == 200  # placement step
        response = client.post('/add_book_confirm', data={'confirm': 'location', 'height': 1, 'width': 1})
    assert response.status_code == 302 and response.headers['Location'].endswith('/added_book')
    response = client.get('/added_book', follow_redirects=True)
    assert response.status_code == 200
    return response


# --- pages that used to crash -------------------------------------------------

def test_login_page_and_login_required(client):
    assert client.get('/login').status_code == 200
    response = client.get('/')
    assert response.status_code == 302 and response.headers['Location'].endswith('/login')


def test_guest_login_and_empty_collection(guest_client):
    response = guest_client.get('/')
    assert response.status_code == 200
    assert b'Your shelf is empty' in response.data
    assert b'read-only' in response.data  # demo banner


def test_page_out_of_range_does_not_crash(guest_client):
    for page in (1, 99, -5, 'abc'):
        assert guest_client.get(f'/?page={page}').status_code == 200


def test_random_with_no_unread_books(guest_client):
    response = guest_client.get('/?random=true')
    assert response.status_code == 200
    assert b'No unread books' in response.data


def test_borrowed_filter(guest_client):
    assert guest_client.get('/?borrowed=true').status_code == 200


def test_unknown_shelf_redirects(guest_client):
    for shelf in (999, 'abc'):
        response = guest_client.get(f'/?shelf_id={shelf}')
        assert response.status_code == 302 and response.headers['Location'].endswith('/browse')


def test_missing_book_details_redirects(guest_client):
    for book in (99999, 'abc', ''):
        response = guest_client.get(f'/book_details?id={book}')
        assert response.status_code == 302


def test_confirm_and_added_without_session_redirect(guest_client):
    for url in ('/add_book_confirm', '/added_book'):
        response = guest_client.get(url)
        assert response.status_code == 302 and response.headers['Location'].endswith('/add_book')


def test_delete_missing_shelf(user_client):
    response = user_client.post('/browse', data={'delete': 999}, follow_redirects=True)
    assert response.status_code == 200
    assert b'does not exist' in response.data


def test_search_with_no_results_anywhere(guest_client):
    response = guest_client.get('/?find=zzzqqq')
    assert response.status_code == 200
    assert b'Nothing found' in response.data


def test_online_search_results_render(app_module, guest_client, monkeypatch):
    cover = base64.b64encode(tiny_png_bytes()).decode()
    monkeypatch.setattr(app_module, 'search_for_books', lambda q, max_results=10: [
        {'title': 'Online Book', 'author': 'Web Author', 'language': 'EN', 'cover': cover, 'link': 'http://example.com'}])
    response = guest_client.get('/?find=online')
    assert response.status_code == 200
    assert b'Online Book' in response.data and b'Add to collection' in response.data


def test_404_page(client):
    response = client.get('/no-such-page')
    assert response.status_code == 404
    assert "doesn't exist" in page_text(response)


def test_forgot_and_reset_password_pages(client):
    assert client.get('/forgot_password').status_code == 200
    response = client.post('/forgot_password', data={'email': 'nobody@example.com'})
    assert response.status_code == 200 and b'no account' in response.data
    response = client.get('/reset_password/not-a-real-token')
    assert response.status_code == 200 and b'not valid' in response.data


def test_forgot_password_known_email_without_sendgrid(client):
    register(client, 'resetme', email='resetme@example.com')
    client.get('/logout')
    response = client.post('/forgot_password', data={'email': 'resetme@example.com'})
    assert response.status_code == 200
    assert b'not available' in response.data


def test_version_footer_present(client):
    response = client.get('/login')
    assert b'Version 2.0' in response.data and b'v1.0' in response.data


# --- the main flows -------------------------------------------------------------

def test_register_logs_in_and_validates(client):
    response = register(client, 'newuser', email='new@example.com', password='weak')
    assert b'password' in response.data  # rejected: too short / no capital / no number
    response = register(client, 'newuser', email='new@example.com')
    assert response.status_code == 200 and b'Welcome, newuser' in response.data
    response = register(client, 'newuser', email='other@example.com')
    assert b'username already exists' in response.data


def test_full_book_lifecycle(app_module, user_client):
    # shelf without a photo
    response = user_client.post('/add_bookshelf', data={'width': 3, 'height': 2, 'description': 'Test Shelf'},
                                content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200 and b'Test Shelf' in response.data
    shelf_id = app_module.db.execute("SELECT id FROM bookshelves WHERE description = 'Test Shelf';")[0]['id']

    # a PNG with transparency used to crash the JPEG save
    response = add_manual_book(user_client, title='lifecycle book', shelf=shelf_id, image=tiny_png_bytes())
    assert b'Lifecycle Book' in response.data
    book = app_module.db.execute("SELECT * FROM books WHERE title = 'Lifecycle Book';")[0]
    assert book['bookshelf_id'] == shelf_id and book['location_x'] == 1 and book['location_y'] == 1
    assert book['language'] == 'EN'

    # details page shows the cover and the shelf
    response = user_client.get(f"/book_details?id={book['id']}&page=0")
    assert response.status_code == 200
    assert b'Test Shelf' in response.data and book['image'].encode() in response.data

    # editing only the title keeps the shelf position (it used to be wiped)
    response = user_client.post('/book_details', data={
        'book_id': book['id'], 'submit': 'edit', 'title': 'Renamed Book', 'author': book['author'],
        'language': 'HR', 'location-input': str(shelf_id), 'selected-max-height': '', 'selected-max-width': '',
        'note': 'hello', 'status': 'True'}, follow_redirects=True)
    assert response.status_code == 200
    book = app_module.db.execute("SELECT * FROM books WHERE id = ?;", book['id'])[0]
    assert book['title'] == 'Renamed Book' and book['language'] == 'HR' and book['note'] == 'hello'
    assert book['bookshelf_id'] == shelf_id and book['location_x'] == 1 and book['location_y'] == 1
    assert book['status'] == 'True'

    # shelf with books cannot be deleted
    response = user_client.post('/browse', data={'delete': shelf_id}, follow_redirects=True)
    assert "can't delete" in page_text(response)

    # random picks only unread books: none left
    assert b'No unread books' in user_client.get('/?random=true').data

    # delete the book, then the shelf
    response = user_client.post('/book_details', data={'book_id': book['id'], 'submit': 'delete'}, follow_redirects=True)
    assert b'Deleted Renamed Book' in response.data
    assert app_module.db.execute("SELECT id FROM books WHERE id = ?;", book['id']) == []
    response = user_client.post('/browse', data={'delete': shelf_id}, follow_redirects=True)
    assert b'Deleted the shelf' in response.data


def test_search_finds_own_books_and_pagination(user_client):
    for i in range(6):
        add_manual_book(user_client, title=f'paginated {i}', author='Same Author')
    response = user_client.get('/')
    assert b'Page 1 of 2' in response.data and b'Next' in response.data
    response = user_client.get('/?page=1')
    assert b'Page 2 of 2' in response.data and b'Previous' in response.data
    response = user_client.get('/?find=same author')
    assert b'Found in your collection' in response.data and b'Found 6 book(s)' in response.data


def test_add_book_from_search_result(user_client):
    cover = base64.b64encode(tiny_png_bytes()).decode()
    response = user_client.post('/add_book_from_find', data={
        'title': 'found online', 'author': 'web author', 'language': 'en', 'cover': cover})
    assert response.status_code == 302
    assert user_client.get('/add_book_confirm').status_code == 200
    user_client.post('/add_book_confirm', data={'confirm': 'first', 'bookshelf_choice': 'None'})
    response = user_client.get('/added_book', follow_redirects=True)
    assert b'Found Online' in response.data


def test_add_book_validation_messages(user_client):
    response = user_client.post('/add_book', data={'add': 'isbn', 'isbn': ''})
    assert b'Please enter an ISBN' in response.data
    response = user_client.post('/add_book', data={'add': 'isbn', 'isbn': '123'})
    assert b'No book found' in response.data
    response = user_client.post('/add_book', data={'add': 'manual', 'title': '', 'author': ''})
    assert b'required' in response.data
    response = user_client.post('/add_book', data={'add': 'manual', 'title': 'x', 'author': 'y',
                                                    'manual_image': (io.BytesIO(b'not an image'), 'x.png', 'image/png')},
                                content_type='multipart/form-data')
    assert b'could not be read' in response.data
    response = user_client.post('/add_book', data={'add': 'nonsense'})
    assert response.status_code == 200
    response = user_client.post('/add_bookshelf', data={'width': 0, 'height': 'x', 'description': 'bad'},
                                content_type='multipart/form-data')
    assert b'valid bookshelf size' in response.data


# --- security ---------------------------------------------------------------------

def test_users_cannot_see_or_change_each_others_books(app_module, user_client):
    add_manual_book(user_client, title='private book', author='Owner')
    book = app_module.db.execute("SELECT * FROM books WHERE title = 'Private Book';")[0]
    shelf_id = app_module.db.execute(
        "INSERT INTO bookshelves (width, height, description, image, user_id) VALUES (1, 1, 'Private Shelf', ?, ?);",
        app_module.GENERIC_SHELF_IMAGE, book['user_id'])

    intruder = app_module.app.test_client()
    register(intruder, 'intruder', email='intruder@example.com')
    assert intruder.get(f"/book_details?id={book['id']}").status_code == 302
    assert intruder.get(f'/?shelf_id={shelf_id}').status_code == 302
    intruder.post('/book_details', data={'book_id': book['id'], 'submit': 'delete'})
    intruder.post('/book_details', data={'book_id': book['id'], 'submit': 'edit', 'title': 'hacked'})
    intruder.post('/browse', data={'delete': shelf_id})
    assert app_module.db.execute("SELECT title FROM books WHERE id = ?;", book['id'])[0]['title'] == 'Private Book'
    assert app_module.db.execute("SELECT id FROM bookshelves WHERE id = ?;", shelf_id) != []


def test_guest_account_is_read_only(app_module, guest_client):
    before = app_module.db.execute("SELECT COUNT(*) AS n FROM bookshelves;")[0]['n']
    response = guest_client.post('/add_bookshelf', data={'width': 1, 'height': 1, 'description': 'Guest Shelf'},
                                 content_type='multipart/form-data', follow_redirects=True)
    assert b'read-only' in response.data
    assert app_module.db.execute("SELECT COUNT(*) AS n FROM bookshelves;")[0]['n'] == before
    response = guest_client.post('/add_book', data={'add': 'manual', 'title': 'x', 'author': 'y'}, follow_redirects=True)
    assert b'read-only' in response.data
