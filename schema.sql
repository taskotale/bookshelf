-- Bookshelf 1.0 schema. Applied automatically on first run when bookshelf.db does not exist.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    username TEXT NOT NULL,
    hash TEXT NOT NULL,
    email VARCHAR
);

CREATE TABLE IF NOT EXISTS bookshelves (
    id INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    description TEXT,
    image TEXT,
    user_id INTEGER NOT NULL,
    PRIMARY KEY(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    language TEXT,
    location_x INTEGER,
    location_y INTEGER,
    status TEXT,
    note TEXT,
    image TEXT,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    bookshelf_id INTEGER,
    user_id INTEGER,
    borrowed TEXT,
    FOREIGN KEY(bookshelf_id) REFERENCES bookshelves(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);
