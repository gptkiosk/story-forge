# Story Forge

A self-publishing dashboard for managing the entire workflow from outline to audiobook generation.

## Features

- 📚 **Book Management** - Organize your book projects with chapters
- ✍️ **Chapter Editor** - Write and edit chapters with rich text
- 🎙️ **Audiobook Generation** - Convert chapters to audio using MiniMax TTS
- 🔐 **Google OAuth** - Secure single-sign-on authentication
- ☁️ **Cloud Backup** - Automatic backup to Google Cloud Storage

## Tech Stack

- **Backend**: Python, FastAPI
- **Frontend**: NiceGUI (Python-native UI framework)
- **Database**: SQLite (WAL mode)
- **TTS**: MiniMax API (speech-02-hd with voice cloning)
- **Auth**: Google OAuth 2.0
- **Infrastructure**: Terraform (for future Cloud Run deployment)

## Getting Started

### Prerequisites

- Python 3.12+
- Google Cloud Platform account (for OAuth and GCS)
- MiniMax API account (for TTS)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/gptkiosk/story-forge.git
cd story-forge
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

5. Run the application:
```bash
python main.py
```

The app will be available at `http://localhost:8080`

## Project Structure

```
story-forge/
├── main.py              # Application entry point
├── db.py                # Database setup and queries
├── tts.py               # MiniMax TTS API client
├── auth.py              # Google OAuth authentication
├── backup.py            # GCS backup functions
├── models/              # SQLAlchemy ORM models
├── ui/                  # NiceGUI pages and components
├── requirements.txt     # Python dependencies
└── .github/workflows/   # CI/CD pipelines
```

## Development

### Running Tests
```bash
pytest tests/ -v
```

### Linting
```bash
ruff check . --fix
```

## License

MIT License
