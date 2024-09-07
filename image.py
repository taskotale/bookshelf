from PIL import Image


def compress(upload, path):
    img = Image.open(upload)
    (width, height) = (int(img.width/3), int(img.height/3))
    img = img.resize((width, height))
    img.save(path, quality=70)
    return



def check_file_type(file):
    allowed_types = ['image/jpeg', 'image/png', 'image/gif']

    if file.content_type not in allowed_types:
        return False

    return True
