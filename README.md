# Clue

AI-powered screenshot assistant. Press a hotkey to capture your active window and get instant AI analysis.

## Setup

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

## Usage

- **Cmd+Shift+F** - Capture active window and analyze
- A small notification appears while analyzing
- Response appears in a floating window
- Click **Close** to dismiss

## Requirements

- macOS
- Python 3
- Accessibility permissions for Terminal (System Settings → Privacy & Security → Accessibility)
