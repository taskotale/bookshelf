"""Google Books lookups. Every network failure degrades to 'nothing found' instead of a crash."""
import os
from base64 import b64encode
from io import BytesIO

import requests
from PIL import Image

GOOGLE_BOOKS_URL = 'https://www.googleapis.com/books/v1/volumes'
API_KEY = os.getenv('GOOGLE_BOOKS_API_KEY')  # optional, but raises the per-IP rate limit a lot
TIMEOUT = 8
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GENERIC_COVER = os.path.join(BASE_DIR, 'static', 'book_img', 'generic_book.jpg')


def generic_cover():
    img = Image.open(GENERIC_COVER)
    img.load()
    return img


def _volumes(params):
    if API_KEY:
        params['key'] = API_KEY
    try:
        response = requests.get(GOOGLE_BOOKS_URL, params=params, timeout=TIMEOUT)
        if response.status_code != 200:
            print(f'Google Books returned HTTP {response.status_code}')
            return []
        return response.json().get('items') or []
    except (requests.RequestException, ValueError) as e:
        print(f'Google Books request failed: {e}')
        return []


def get_book_data(isbn):
    """Look up one book by ISBN. Returns a book dict with a PIL cover, or False."""
    items = _volumes({'q': f'isbn:{isbn}'})
    if not items:
        return False
    return get_book(items[0].get('volumeInfo') or {}, False)


def search_for_books(query, max_results=10):
    """Free-text search. Returns a list of book dicts with base64 covers (possibly empty)."""
    items = _volumes({'q': query, 'maxResults': max_results})
    return [get_book(item.get('volumeInfo') or {}, True) for item in items]


def get_book(book_data, query):
    title = book_data.get('title') or 'Unknown Title'
    authors = book_data.get('authors') or ['Unknown Author']
    if isinstance(authors, str):
        authors = [authors]
    language = (book_data.get('language') or 'EN').upper()
    link = book_data.get('previewLink') or book_data.get('infoLink') or ''

    image_links = book_data.get('imageLinks') or {}
    cover = get_cover(image_links.get('thumbnail') or image_links.get('smallThumbnail'))
    if cover is None:
        cover = generic_cover()

    if query:
        # Search results are rendered straight into the page, so ship the cover as base64
        # and the author as plain text.
        buffer = BytesIO()
        cover.convert('RGB').save(buffer, format='JPEG')
        return {
            'title': title,
            'author': ', '.join(authors),
            'language': language,
            'cover': b64encode(buffer.getvalue()).decode('utf-8'),
            'link': link,
        }

    return {
        'title': title,
        'author': authors,
        'language': language,
        'cover': cover,
        'link': link,
    }


def get_cover(url):
    if not url:
        return None
    try:
        response = requests.get(url, timeout=TIMEOUT)
        if response.status_code != 200:
            return None
        img = Image.open(BytesIO(response.content))
        img.load()
        return img
    except Exception:
        return None
