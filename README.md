# Attendance Auditor ⏱️📊

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18%2F19-61DAFB.svg?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Project Status](https://img.shields.io/badge/Status-Work_In_Progress-orange.svg)]()

> ⚠️ **Project Status: Active Work in Progress (WIP)**  
> This project is currently under active development. Core components—including the asynchronous backend API, vectorized reconciliation engine, and role-based frontend SPA—are functional, while additional features, integrations, and automated deployment pipelines are actively being built.

A high-performance, full-stack **Biometric Attendance Audit, Secure Ingestion, and Vectorized Labor Reconciliation System** powered by **FastAPI**, **SQLAlchemy 2.0 (Async)**, **Pandas**, and a **React + TypeScript SPA**.

---

## 📑 Table of Contents

1. [Architecture & Tech Stack](#-architecture--tech-stack)
2. [Key Features](#-key-features)
3. [Repository Structure](#-repository-structure)
4. [Prerequisites](#-prerequisites)
5. [Getting Started (Step-by-Step)](#-getting-started-step-by-step)
   - [Step 1: Clone the Repository](#step-1-clone-the-repository)
   - [Step 2: Backend Setup & Execution](#step-2-backend-setup--execution)
   - [Step 3: Frontend Setup & Execution](#step-3-frontend-setup--execution)
6. [Demo Seed Credentials](#-demo-seed-credentials)
7. [API Endpoints Overview](#-api-endpoints-overview)
8. [Testing & Code Quality](#-testing--code-quality)
9. [Development Roadmap](#-development-roadmap)
10. [License](#-license)

---

## 🛠️ Architecture & Tech Stack

### Backend
- **Runtime & Language**: Python 3.11+
- **Web Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Fully asynchronous)
- **Database & ORM**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) with dual configuration:
  - Local fast-iteration: Asynchronous SQLite (`sqlite+aiosqlite`).
  - Production-ready: Asynchronous PostgreSQL (`postgresql+asyncpg`) with mandatory SSL/TLS support (e.g. Neon.tech).
- **Database Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Labor Calculation & Reconciliation**: [Pandas](https://pandas.pydata.org/) (Vectorized operations without inefficient Python iteration loops)
- **Spreadsheet Generation**: [openpyxl](https://openpyxl.readthedocs.io/)
- **Security & Hardening**:
  - Secure password hashing using **Argon2id** via `argon2-cffi`.
  - Ephemeral **JWT (JSON Web Tokens)** with strict Role-Based Access Control (**RBAC**: `ADMIN`, `SUPERVISOR`, `WORKER`).
  - Strict Multi-Tenant scoping preventing IDOR / BOLA vulnerabilities.
  - Safe binary upload inspection using magic byte analysis (`python-magic`), 10 MB quota enforcement, and UUID4 path traversal mitigation.
  - Formula Injection / CSV Injection mitigation in generated `.xlsx` exports (`=`, `+`, `-`, `@` neutralization).
  - Security headers middleware, distributed request correlation (`X-Request-ID`), and sensitive data logging masking.

### Frontend
- **Framework**: [React](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
- **Build Tool**: [Vite](https://vitejs.dev/)
- **Architecture**: Single Page Application (SPA) with context-based authentication, token management, and role-guarded routes.
- **UI Components & Icons**: Modern custom dashboard layout with [Lucide React](https://lucide.dev/).

---

## 🚀 Key Features

- **Multi-Tenant Isolation**: Every database query and business transaction is strictly partitioned by organization ID.
- **Vectorized Attendance Reconciliation**:
  - Time-window pairing of `IN` and `OUT` biometric punches using fast vectorized shifts.
  - Configurable debounce filter discarding duplicate/bouncing biometric badge taps.
  - Vectorized distribution across standard daytime hours, public holiday hours, and statutory night shifts (`[22:00, 06:00]`).
  - Automated anomaly classification (missing punches, unjustified absences, overtime excesses).
- **Incident Management & Justification**: Dedicated supervisory workflows to review, approve, or reject attendance discrepancies with audit logs.
- **Live / Manual Punching**: Real-time punch-clock endpoint and interface for remote workers and supervisors.
- **Multilayer Excel Exporter**: High-performance in-memory (`BytesIO`) workbook generation with 3 structured sheets (*General Summary*, *Punch Details*, *Incidents*), frozen panes, and conditional formatting traffic-light indicators.
- **Role-Tailored Dashboards**:
  - **Administrator**: Tenant overview, system metrics, and audit settings.
  - **Supervisor**: Biometric file ingestion, employee summaries, incident resolution, and Excel exports.
  - **Worker**: Real-time clock-in/out button and personal attendance history.

---

## 📁 Repository Structure

```text
ControlAsistencia/
├── alembic/                  # Database migration configuration and scripts
│   └── versions/             # Alembic revision history
├── frontend/                 # Client SPA (React + TypeScript + Vite)
│   ├── src/
│   │   ├── auth/             # Auth context, protected routes, and permission guards
│   │   ├── components/       # Reusable layout and UI components
│   │   ├── types/            # TypeScript API types and schema definitions
│   │   └── views/            # Role-specific dashboard views (Admin, Supervisor, Worker, Login)
│   ├── package.json
│   └── vite.config.ts
├── scripts/                  # Auxiliary automation scripts (database seeder)
├── src/                      # Backend application source code
│   ├── api/                  # FastAPI routers, Pydantic v2 schemas, and dependencies
│   ├── core/                 # File parsers, reconciliation engine, security & export helpers
│   ├── db/                   # SQLAlchemy declarative models and async session management
│   └── services/             # Business logic layer (attendance reconciliation, authentication)
├── storage/                  # Local storage directory for file uploads (git-ignored)
├── tests/                    # Automated test suite (unit and integration tests)
├── .env.example              # Environment variables template for backend
├── pyproject.toml            # Python dependencies and tool settings (Poetry)
└── README.md                 # Project documentation
```

---

## 📋 Prerequisites

- **Python**: 3.11 or later
- **Node.js**: v18 or later with **npm**
- **Poetry** (recommended for Python package management) or `pip`
- **Git**

---

## 💻 Getting Started (Step-by-Step)

### Step 1: Clone the Repository

```bash
git clone https://github.com/Sulfuracion/attendance-auditor.git
cd attendance-auditor
```

---

### Step 2: Backend Setup & Execution

1. **Install Python dependencies**:
   ```bash
   # Using Poetry (recommended):
   poetry install

   # Or using standard virtualenv and pip:
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # Linux/macOS: source .venv/bin/activate
   pip install -r <(poetry export --without-hashes)
   ```

2. **Configure environment variables**:
   Create your `.env` file from the provided template:
   ```bash
   cp .env.example .env
   ```
   *(On Windows PowerShell: `Copy-Item .env.example .env`)*

   Default local development configuration (`sqlite+aiosqlite`):
   ```ini
   ENVIRONMENT=development
   LOG_LEVEL=INFO
   DATABASE_URL=sqlite+aiosqlite:///./attendance_dev.db
   JWT_SECRET=supersecretdevkeyatleast32characterslongforsecurity
   JWT_ALGORITHM=HS256
   JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
   MAX_UPLOAD_SIZE_BYTES=10485760
   CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]
   ```

3. **Apply database migrations**:
   ```bash
   poetry run alembic upgrade head
   ```

4. **Populate demo seed data**:
   ```bash
   poetry run python -m scripts.seed_local
   ```

5. **Start the backend development server**:
   ```bash
   poetry run uvicorn src.main:app --reload --port 8000
   ```
   - **Base API**: `http://localhost:8000`
   - **Interactive Swagger Docs**: `http://localhost:8000/docs`
   - **Alternative ReDoc**: `http://localhost:8000/redoc`

---

### Step 3: Frontend Setup & Execution

1. **Navigate to the frontend folder**:
   ```bash
   cd frontend
   ```

2. **Install JavaScript dependencies**:
   ```bash
   npm install
   ```

3. **Configure environment variables (optional)**:
   ```bash
   cp .env.example .env
   ```
   Defaults to `VITE_API_BASE_URL=http://127.0.0.1:8000`.

4. **Start the frontend development server**:
   ```bash
   npm run dev
   ```
   The application dashboard will be live at `http://localhost:5173`.

---

## 🔑 Demo Seed Credentials

Once the seed script has run (`scripts.seed_local`), the following accounts are ready for testing:

| Role | Email | Password | Permissions & Scope |
|---|---|---|---|
| **ADMIN** | `admin@empresa.com` | `AdminPass123!` | System configuration, tenant management, and global audit. |
| **SUPERVISOR** | `supervisor@empresa.com` | `SupervisorPass123!` | Biometric upload, attendance reconciliation, incident review, and Excel exports. |
| **WORKER** | `worker@empresa.com` | `WorkerPass123!` | Live clock in/out and personal attendance records. |

---

## 📡 API Endpoints Overview

### Authentication (`/auth`)
- `POST /auth/token`: OAuth2 credentials login, returns JWT access token.
- `GET /auth/me`: Returns profile and active role of authenticated user.

### Attendance & Auditing (`/attendance`)
- `POST /attendance/upload`: Secure ingestion and immediate reconciliation of CSV/XLSX biometric punch logs.
- `GET /attendance/summary`: Aggregated employee work-hour summaries with optional date range filters.
- `GET /attendance/records`: Paginated detailed view of daily reconciled shifts.
- `GET /attendance/incidents`: Unresolved discrepancies and anomalies requiring attention.
- `POST /attendance/incidents/{incident_id}/justify`: Approve or reject incident justifications with audit notes.
- `POST /attendance/punch`: Real-time clock-in/clock-out registration.
- `GET /attendance/export`: Downloads formatted, formula-sanitized Excel audit report (`.xlsx`).

---

## 🧪 Testing & Code Quality

The codebase enforces strict quality controls and automated test coverage:

```bash
# Run unit and integration tests
poetry run pytest

# Static code analysis and linting
poetry run ruff check .

# Strict type checking
poetry run mypy src tests scripts

# Static security analysis
poetry run bandit -r src

# Dependency vulnerability auditing
poetry run pip-audit
```

---

## 🗺️ Development Roadmap

- [x] High-performance vectorized reconciliation engine.
- [x] Multi-tenant role-based security model (JWT + Argon2id).
- [x] Biometric file ingestion with Magic Number and Path Traversal validation.
- [x] Multilayer corporate Excel export with formula sanitization.
- [x] Role-tailored frontend SPA (React + TypeScript).
- [x] Live manual clock-in / clock-out capability.
- [ ] Automated email alerts for pending attendance anomalies.
- [ ] Hardware connectors / API integration for biometric clock terminals (ZKTeco, Hikvision).
- [ ] Automated GitHub Actions CI/CD pipeline (tests, lint, security scans, docker build).
- [ ] Containerized deployment with Docker and Docker Compose.
- [ ] Support for complex rotating shifts and time-off compensation balances.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
