# Clue

AI-powered screenshot assistant. Press a hotkey to capture your active window and get instant AI analysis.

Supports both Google Gemini (cloud) and Ollama (local) backends.

## Setup

### Option 1: Gemini (Cloud)

1. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

2. Create a `.env` file:
   ```
   GEMINI_API_KEY=your-api-key-here
   ```

3. Run:
   ```bash
   chmod +x run.sh
   ./run.sh
   ```

### Option 2: Ollama (Local)

1. Install [Ollama](https://ollama.ai) and pull a vision model:
   ```bash
   ollama pull qwen3-vl:8b
   ```

2. Create a `.env` file:
   ```
   CLUE_BACKEND=ollama
   OLLAMA_MODEL=qwen3-vl:8b
   ```

3. Make sure Ollama is running (`ollama serve`) and run:
   ```bash
   chmod +x run.sh
   ./run.sh
   ```

## Configuration

Environment variables (set in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `CLUE_BACKEND` | `gemini` | Backend to use: `gemini` or `ollama` |
| `GEMINI_API_KEY` | - | API key for Gemini |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Gemini model name |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen3-vl:8b` | Ollama model name |

## Usage

- **Cmd+Shift+F** - Capture active window and analyze
- A small notification appears while analyzing
- Response appears in a floating window
- Click **Close** to dismiss

## Requirements

- macOS
- Python 3
- Accessibility permissions for Terminal (System Settings → Privacy & Security → Accessibility)
