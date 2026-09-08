# Bookshelf 1.0 (legacy)

A personal library manager: catalogue your books, put them on virtual copies of your real
bookshelves, and find them again later.

**Live:** https://taskotale.pythonanywhere.com

> **This is version 1.0**, my first full-stack project (2024). It stays online exactly as it was
> designed, with stability fixes only, as part of my portfolio.
> **Version 2.0 is in progress** and lives at the link shown in the footer of the app.

## What it does

- Register / log in, or click **Explore as Guest** for a read-only tour of a real collection
- Add books three ways: by **ISBN** (Google Books), from a **photo of the barcode** (pyzbar), or
  **manually** with your own cover image
- Build **bookshelves** with a photo, a number of shelves and slots, and place each book on one
- Search your collection; if a title is not on your shelf, the app searches Google Books and
  lets you add the result with one click
- Mark books as read or lent out, keep private notes, and let **Surprise me!** pick an unread book

## Stack

Python / Flask, SQLite (via the cs50 SQL wrapper), Jinja templates with Bootstrap 5, Pillow for
images, pyzbar for barcodes, the Google Books API. Hosted on PythonAnywhere.

## Run it locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then set SECRET_KEY (see the comment in the file)
flask --app app run --debug
```

The database is created from `schema.sql` on first run, with a `guest` account so the demo button
works. Barcode photos need the zbar library (`brew install zbar` on macOS, `apt install libzbar0`
on Debian/Ubuntu); without it the app still runs and ISBN / manual entry work.

### Configuration (`.env`)

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signs the session cookie. Required in production. |
| `SECURITY_PASSWORD_SALT` | Salt for password-reset tokens. |
| `DEMO_USER_ID` | Which account "Explore as Guest" opens (default `1`). |
| `DEMO_READ_ONLY` | `1` (default) makes the guest account read-only. |
| `V2_URL` | Where the "Version 2.0" link in the footer points. |
| `GOOGLE_BOOKS_API_KEY` | Optional. Raises the Google Books rate limit. |
| `SENDGRID_API_KEY`, `MAIL_DEFAULT_SENDER` | Optional. Only needed for password-reset emails. |

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests run against a throwaway copy of the app in a temp folder, so they never touch
`bookshelf.db` or the images in `static/`.

## Deploying to PythonAnywhere

`bookshelf.db` holds real user data and is **not** tracked in git any more. Before pulling a new
version, back it up, because git will try to remove the old tracked copy:

```bash
# in a PythonAnywhere bash console
cd ~/bookshelf
cp bookshelf.db ~/bookshelf.db.backup-$(date +%F)
mv bookshelf.db ~/bookshelf.db.keep
git pull
mv ~/bookshelf.db.keep bookshelf.db
pip install -r requirements.txt      # inside the web app's virtualenv
```

Then reload the web app from the **Web** tab. The virtualenv must live outside the repo
(for example `~/.virtualenvs/bookshelf`); if the Web tab points at `~/bookshelf/venv`, recreate
it outside first, because that folder is no longer part of the repository.
