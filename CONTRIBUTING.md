# Contributing to Citidy

Thank you for your interest in contributing to **Citidy** (*"Your City. Your Voice. Tracked to Resolution."*), developed for **DATATHON 2026 (Track 3: Smart City)**.

We welcome contributions from municipal engineers, civic technology developers, data scientists, and UI/UX designers.

---

## Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free environment for everyone. Please treat all contributors and community members with dignity, professionalism, and respect.

---

## Getting Started

1. **Fork the Repository**: Create your own fork of `datathon`.
2. **Clone your fork**:
   ```bash
   git clone https://github.com/<your-username>/datathon.git
   cd datathon
   ```
3. **Run Local Server**:
   Citidy requires **Python 3.9+** and standard web technologies with **zero mandatory external pip/npm packages**:
   ```bash
   python server.py --port 8000
   ```
4. **Access the Application**:
   Open [http://localhost:8000](http://localhost:8000) in any modern browser.

---

## Development Guidelines

### 1. Code Quality & Standards
- Keep code clean, modular, and self-documenting.
- Preserve existing comments and docstrings unless updating related logic.
- Avoid exposing any API keys, credentials, or secrets in client-side code (`index.html`, `app.js`, `styles.css`).
- Ensure all API endpoints handle errors gracefully, returning structured JSON error payloads with standard HTTP status codes (400, 401, 403, 404, 500) rather than unhandled HTML or tracebacks.

### 2. Database & Migrations
- Citidy dual-targets **SQLite** for rapid local evaluation and **Supabase PostgreSQL with Row Level Security (RLS)** for cloud deployment.
- When adding tables or modifying schemas, update both `database.py` (SQLite schema + migrations) and `supabase/migrations/20260101000000_citidy_schema.sql` (PostgreSQL DDL + RLS policies).

### 3. Testing Requirements
Before submitting any pull request, you **must run all test suites** and ensure 100% pass rate:
```bash
python -m unittest discover tests -v
```
All integration tests, authentication tests, and unit tests must pass cleanly.

---

## Commit & Pull Request Workflow

1. Create a descriptive feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Commit your changes with clear, imperative commit messages:
   ```bash
   git commit -m "feat(triage): add proximity cluster indicator for road hazard complaints"
   ```
3. Push to your fork and submit a Pull Request against `main`.
4. Include a detailed description of changes, screenshots (if UI-related), and test evidence in your PR description.
