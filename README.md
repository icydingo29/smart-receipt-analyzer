# Smart Receipt Analyzer

A Python application that processes PDF invoices using OCR and an LLM. It extracts structured data, categorizes line items, persists results to a PostgreSQL database, and generates a PDF expense report. The entire application runs inside Docker containers via a single command.

---

## Features

- **PDF ingestion** — upload any PDF invoice through the web UI or REST API
- **OCR extraction** — Groq Vision API extracts text from scanned or image-based PDFs; falls back to `pdfplumber`
- **LLM enrichment** — Groq `llama-3.3-70b-versatile` categorizes line items, corrects OCR errors, and generates a per-category expense summary
- **Database persistence** — all receipt data, raw LLM responses, and parsed results stored in PostgreSQL
- **PDF report generation** — structured expense report with header, itemized table, category summary, and grand total
- **Dual interface** — Streamlit web UI and FastAPI REST endpoints

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI |
| Web UI | Streamlit |
| Database | PostgreSQL 15 |
| ORM | SQLAlchemy |
| Validation | Pydantic v2 |
| OCR (primary) | Groq Vision (`llama-4-scout-17b-16e-instruct`) |
| OCR (fallback) | pdfplumber |
| LLM enrichment | Groq (`llama-3.3-70b-versatile`) |
| PDF generation | ReportLab |
| Containerization | Docker + Docker Compose |

---

## Project Structure

```
smart-receipt-analyzer/
├── app/
│   ├── api/
│   │   └── main.py              # FastAPI app and REST endpoints
│   ├── data/
│   │   ├── models.py            # SQLAlchemy ORM models
│   │   └── schemas.py           # Pydantic validation schemas
│   ├── foundation/
│   │   ├── config.py            # Settings via pydantic-settings
│   │   └── database.py          # Database session management
│   ├── processing/
│   │   ├── ocr_engine.py        # PDF text extraction
│   │   ├── llm_processor.py     # Groq LLM enrichment
│   │   └── pdf_generator.py     # Expense report generation
│   └── ui_layer/
│       └── ui.py                # Streamlit web interface
├── samples/                     # Sample PDF invoices for testing
├── data/                        # Runtime data (gitignored)
│   ├── saved_pdf_files/         # Generated expense reports
│   └── temp_pdf_files/          # Temporary upload storage
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- A Groq API key — free at [console.groq.com](https://console.groq.com)

---

## Setup

**1. Clone the repository**

```bash
git clone https://github.com/icydingo29/smart-receipt-analyzer.git
cd smart-receipt-analyzer
```

**2. Configure environment variables**

```bash
cp .env.example .env
```

Open `.env` and set your Groq API key:

```
GROQ_API_KEY=your_groq_api_key_here
```

All other values are pre-configured for the Docker environment and do not need to be changed.

**3. Start all services**

```bash
docker compose up --build
```

This starts three containers: `db` (PostgreSQL), `app` (FastAPI), and `streamlit` (web UI). The app container waits for the database to be healthy before starting.

First-time build takes 2–3 minutes. Subsequent starts (without `--build`) are faster.

---

## Usage

### Web UI

Go to **http://localhost:8501**

- **Upload Receipt** tab — upload a PDF invoice, process it, and download the generated expense report
- **View Receipts** tab — browse all previously processed receipts, view line items and category summaries, download any past report

### REST API

Interactive docs are available at **http://localhost:8000/docs** (Swagger UI). All endpoints can be tested directly in the browser — no extra tooling needed.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/receipts` | Upload and process a PDF invoice |
| `GET` | `/api/receipts` | List all processed receipts (paginated) |
| `GET` | `/api/receipts/{id}` | Get receipt details with line items |
| `GET` | `/api/receipts/{id}/report` | Download the PDF expense report |

**How to use the Swagger UI:**

1. Open **http://localhost:8000/docs** in your browser
2. Click on any endpoint row to expand it
3. Click the **"Try it out"** button on the right
4. Fill in any required fields:
   - `GET /health` — no fields required, just click **"Execute"**
   - `POST /api/receipts` — click **"Choose File"** to select a PDF, then click **"Execute"**
   - `GET /api/receipts` — enter the number of most recent receipts to skip and maximum receipts to return, then click **"Execute"**
   - `GET /api/receipts/{id}` — enter the receipt ID in the `id` field, then click **"Execute"**
   - `GET /api/receipts/{id}/report` — enter the receipt ID in the `id` field, then click **"Execute"**, then click **"Download file"**
5. The response appears below

---

## Processing Pipeline

```
PDF upload
    │
    ▼
OCR extraction
  ├─ Groq Vision API (scanned/image PDFs)
  └─ pdfplumber fallback 
    │
    ▼
LLM enrichment (Groq llama-3.3-70b-versatile)
  ├─ Correct OCR errors
  ├─ Categorize each line item
  └─ Generate category expense summary
    │
    ▼
Pydantic validation + PostgreSQL persistence
    │
    ▼
PDF report generation (ReportLab)
```

Typical processing time: 2-3 seconds per invoice.

---

## Configuration

All settings are managed via environment variables. See `.env.example` for the full list.

| Variable | Description | Default |
|---|---|---|
| `GROQ_API_KEY` | Groq API key (required) | — |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@db:5432/receipt_analyzer` |
| `OCR_MODEL` | Groq Vision model for OCR | `meta-llama/llama-4-scout-17b-16e-instruct` |
| `LLM_MODEL` | Groq model for enrichment | `llama-3.3-70b-versatile` |
| `SAVED_PDF_FILES_PATH` | Directory for generated reports | `./data/saved_pdf_files` |
| `TEMP_PDF_FILES_PATH` | Directory for temporary uploads | `./data/temp_pdf_files` |

---

## Resetting the Database

To wipe all data and start fresh:

```bash
docker compose down -v
docker compose up --build
```

The `-v` flag removes the persistent PostgreSQL volume.

---

## Sample Invoices

The `samples/` directory contains six test invoices covering different invoice types:

| File | Type |
|---|---|
| `01_florist_shop.pdf` | Retail — florist |
| `02_construction_implicit_currency_extraction.pdf` | Construction services |
| `03_casual_dining.pdf` | Restaurant |
| `04_clothing_shop.pdf` | Retail — clothing |
| `05_steakhouse.pdf` | Restaurant |
| `06_restaurant.pdf` | Restaurant |

---

## Acknowledgements

- **Sample invoices** sourced from:
  - [Receipts dataset — Kaggle (Jens Walter)](https://www.kaggle.com/datasets/jenswalter/receipts)
  - [Invoice samples thread — UiPath Community Forum](https://forum.uipath.com/t/i-need-pdf-invoice-samples-6/772486)
- **`.gitignore` template** from [github/gitignore](https://github.com/github/gitignore)