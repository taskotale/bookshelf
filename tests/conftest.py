"""
Tests run against a throwaway copy of the app in a temp directory, so the real
database and the images under static/ are never touched.
"""
import html
import importlib
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='session')
def app_module(tmp_path_factory):
    workdir = tmp_path_factory.mktemp('bookshelf')
    for name in ('app.py', 'helpers.py', 'api_requests.py', 'image.py', 'schema.sql'):
        shutil.copy(os.path.join(ROOT, name), workdir)
    shutil.copytree(os.path.join(ROOT, 'templates'), workdir / 'templates')
    os.makedirs(workdir / 'static' / 'book_img')
    os.makedirs(workdir / 'static' / 'shelf_img')
    shutil.copy(os.path.join(ROOT, 'static', 'book_img', 'generic_book.jpg'), workdir / 'static' / 'book_img')
    shutil.copy(os.path.join(ROOT, 'static', 'shelf_img', 'generic.png'), workdir / 'static' / 'shelf_img')

    os.environ['SECRET_KEY'] = 'test-secret'
    os.environ.pop('BOOKSHELF_DB', None)
    os.environ.pop('SENDGRID_API_KEY', None)
    sys.path.insert(0, str(workdir))
    module = importlib.import_module('app')
    module.app.config['TESTING'] = True
    # never hit the real Google Books API from the tests
    module.search_for_books = lambda query, max_results=10: []
    module.get_book_data = lambda isbn: False
    return module


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()


def page_text(response):
    """Response body with HTML entities (e.g. &#39;) turned back into characters."""
    return html.unescape(response.get_data(as_text=True))


def register(client, username, email='user@example.com', password='Passw0rd'):
    return client.post('/register', data={
        'username': username, 'user-email': email, 'password': password, 'confirmation': password,
    }, follow_redirects=True)


@pytest.fixture
def user_client(app_module):
    """A client logged in as a fresh, unique user."""
    client = app_module.app.test_client()
    n = app_module.db.execute("SELECT COUNT(*) AS n FROM users;")[0]['n']
    register(client, f'user{n}', email=f'user{n}@example.com')
    return client


@pytest.fixture
def guest_client(app_module):
    client = app_module.app.test_client()
    client.post('/login', data={'demo_login': 'true'})
    return client
