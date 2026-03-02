import requests

from base64 import b64encode
from io import BytesIO
from PIL import Image


def get_book_data(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    response = requests.get(url)
    if response.status_code == 200:
        api_response = response.json()
        if api_response['totalItems'] > 0:
            book_data = api_response['items'][0]['volumeInfo']
            return get_book(book_data, False)
        else:
            return False
    return False


def get_book(book_data, query):
    # Safe data extraction with defaults
    title = book_data.get('title', 'Unknown')
    # Keep as list for now
    authors = book_data.get('authors', ['Unknown Author'])
    language = book_data.get('language', 'Unknown')
    link = book_data.get('previewLink', '')  # Default to empty string

    if 'imageLinks' in book_data:
        cover = get_cover(book_data['imageLinks']['thumbnail'])
    else:
        # Ensure this path is correct for your Mac/Linux environment
        cover = Image.open('static/book_img/generic_book.jpg')

    if query:
        # Process for online search results
        image_bytes = BytesIO()
        cover.save(image_bytes, format='JPEG')
        encoded_image = b64encode(image_bytes.getvalue()).decode('utf-8')

        # Safe author extraction: handle lists vs strings
        display_author = authors[0] if isinstance(authors, list) else authors

        return {
            'title': title,
            # Return as list to stay consistent with app.py
            'author': [display_author],
            'language': language,
            'cover': encoded_image,
            'link': link
        }

    # Process for direct ISBN/Manual entry
    return {
        'title': title,
        'author': authors,
        'language': language,
        'cover': cover,
        'link': link
    }


def get_cover(url):
    response = requests.get(url)
    if response.status_code == 200:
        cover = response.content
        cover_img = Image.open(BytesIO(cover))
        return cover_img
    else:
        return False


def search_for_books(query):
    # Google Books API search
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
    try:
        response = requests.get(url, timeout=5)  # Add timeout to prevent hangs
        if response.status_code == 200:
            api_response = response.json()
            books = []
            if 'items' in api_response:  # Safer than checking totalItems
                for item in api_response['items']:
                    book_data = item['volumeInfo']
                    books.append(get_book(book_data, True))
                return books
        return []  # Return empty list, NOT False
    except Exception as e:
        print(f"Connection Error: {e}")
        return []
