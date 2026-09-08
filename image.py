from PIL import Image, ImageOps

ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}


def check_file_type(file):
    """Cheap first check on an upload, based on the content type the browser sent."""
    return file.content_type in ALLOWED_TYPES


def open_image(file_storage):
    """Open an uploaded image safely. Returns a PIL image, or None if the file is not a readable image."""
    try:
        img = Image.open(file_storage.stream)
        img = ImageOps.exif_transpose(img)  # phone photos carry their rotation in EXIF
        img.load()
        return img
    except Exception:
        return None


def to_rgb(img):
    """JPEG cannot store transparency; convert PNG/GIF images before saving as JPEG."""
    return img if img.mode == 'RGB' else img.convert('RGB')


def compress(img, path):
    """Save a bookshelf photo as a reasonably sized JPEG."""
    img = to_rgb(img)
    img.thumbnail((1200, 1200))
    img.save(path, 'JPEG', quality=70)
