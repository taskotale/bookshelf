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
    if 'title' in book_data:
        title = book_data['title']
    else:
        title = 'Unknown'
    if 'authors' in book_data:
        authors = book_data['authors']
    else:
        authors = 'Unknown'
    if 'language' in book_data:
        language = book_data['language']
    else:
        language = 'Unknown'
    if 'imageLinks' in book_data:
        cover = get_cover(book_data['imageLinks']['thumbnail'])
    else:
        cover = Image.open('static/book_img/generic_book.jpg')
    if query:
        image = cover
        image_bytes = BytesIO()
        image.save(image_bytes, format='JPEG')
        image_bytes = image_bytes.getvalue()
        encoded_image = b64encode(image_bytes).decode('utf-8')
        cover = encoded_image
        authors = authors[0]
        if 'previewLink' in book_data:
            link = book_data['previewLink']
    else:
            link = ''
    book = {
        'title': title,
        'author': authors,
        'language': language,
        'cover': cover,
        'link': link
    }
    return book

def get_cover(url):
    response = requests.get(url)
    if response.status_code == 200:
        cover = response.content
        cover_img = Image.open(BytesIO(cover))
        return cover_img
    else:
        return False

def search_for_books(query):
    url = f"https://www.googleapis.com/books/v1/volumes?q=search+terms:{query}"
    response = requests.get(url)
    if response.status_code == 200:
        api_response = response.json()
        books = []
        if api_response['totalItems'] > 0:
            found_books = api_response['items']
            for item in found_books:
                book_data = item['volumeInfo']
                books.append(get_book(book_data, True))
            return books
        else:
            False
    else:
        return False
