# Story Forge

A self-publishing dashboard for managing books from outline to audiobook generation.

## Features

- 📚 **Book Management** — Create, edit, and organize book projects with chapters
- ✍️ **Chapter Editor** — Write chapters with word count tracking
- 🔐 **Google OAuth** — Secure single-sign-on authentication
- 🎙️ **Audiobook Generation** — Convert chapters to audio using MiniMax TTS (scaffolded)
- ☁️ **Cloud Backup** — GCS backup infrastructure (scaffolded for future use)

## Tech Stack

- **UI Framework**: NiceGUI (Python-native)
- **Database**: SQLite (WAL mode)
- **Auth**: Google OAuth 2.0
- **TTS**: MiniMax API (scaffolded)
- **Infrastructure**: Terraform + Cloud Run (scaffolded for future deployment)

## Running Locally

### Prerequisites

- Python 3.12+
- Google Cloud Platform account (for OAuth)
- MiniMax API account (for TTS, optional)

### Quick Start

```bash
# Clone and enter directory
git clone https://github.com/gptkiosk/story-forge.git
cd story-forge

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GOOGLE_CLIENT_ID="your-client-id"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export PORT=8080

# Run
python main.py
```

Visit `http://localhost:8080` to use the app.

### System Service (Mac Mini)

Run as a launchd service for 24/7 availability:

```bash
# Copy the service definition
cp com.storyforge.plist ~/Library/LaunchAgents/

# Edit the plist with your environment variables, then:
launchctl load ~/Library/LaunchAgents/com.storyforge.plist
launchctl start com.storyforge
```

## Project Structure

```
story-forge/
├── main.py              # NiceGUI app entry point
├── db.py                # Database models, session, encryption
├── auth.py              # Google OAuth handlers
├── tts.py               # MiniMax TTS client (scaffolded)
├── backup.py            # GCS backup (scaffolded)
├── requirements.txt     # Python dependencies
├── data/                 # SQLite DB and uploads (gitignored)
└── tests/               # Test suite
```

## Development

```bash
# Run tests
pytest tests/ -v

# Lint
ruff check . --fix
```

## CI/CD

GitHub Actions runs lint + tests on every push. Docker/GCP deployment is scaffolded but disabled — the app is designed to run as a local system service for now.
