# Spatial Academy (server-backed MVP)

This is a backend-powered prototype for a Starfall competitor with:

- **User authentication** (register/login/logout with signed session cookie)
- **Parent forum** persisted in SQLite
- **Reading + math task library** for Kindergarten through Grade 3

## Run

```bash
python app.py
```

Then open `http://localhost:5000`.

## Notes

- Data is stored in `spatial.db`.
- Passwords are hashed before storage.
- This is an MVP and should be further hardened for production (TLS, CSRF, stronger password hashing, persistent session storage).
