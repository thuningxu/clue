#!/usr/bin/env python3
"""
Clue - AI-powered screenshot assistant
Press Cmd+Shift+S to capture screen and get AI analysis
"""

import os
import sys
import re
import base64
import json
import subprocess
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
import urllib.parse
from tkinter import scrolledtext
from dotenv import load_dotenv
from pynput import keyboard
from PIL import Image, ImageTk

# Load environment variables from .env file
load_dotenv()

# Configuration
HOTKEY = '<cmd>+<shift>+f'

# Backend: 'gemini', 'ollama', or 'gauth'
BACKEND = os.environ.get('CLUE_BACKEND', 'gemini').lower()

# Gemini settings (API key)
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3-flash-preview')

# Ollama settings
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen3-vl:8b')

# Gauth settings (OAuth via Antigravity)
GAUTH_CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), 'credentials.json')
GAUTH_MODEL = os.environ.get('GAUTH_MODEL', 'gemini-3-pro-image')
GAUTH_ENDPOINT = 'https://cloudcode-pa.googleapis.com'
GAUTH_API_VERSION = 'v1internal'

# Default prompt - can be customized
DEFAULT_PROMPT = """Analyze this screenshot and help me understand what I'm looking at.
If it appears to be a problem or question, provide a clear, helpful answer.
If it's code, explain what it does or identify any issues.
Be concise but thorough."""


class NotificationWindow:
    """Small notification toast in upper-right corner with thumbnail"""

    def __init__(self, root):
        self.root = root
        self.window = None
        self.thumbnail_ref = None  # Keep reference to prevent garbage collection

    def show(self, message: str, image_path: str = None):
        """Show notification with optional thumbnail"""
        if self.window is None:
            self._create_window()

        self.label.config(text=message)

        # Show thumbnail if image path provided
        if image_path and os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                # Scale to fit in thumbnail (max 120px height)
                ratio = 80 / img.height
                new_size = (int(img.width * ratio), 80)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                self.thumbnail_ref = ImageTk.PhotoImage(img)
                self.thumbnail_label.config(image=self.thumbnail_ref)
                self.thumbnail_label.pack(side=tk.LEFT, padx=(10, 0))
                width = new_size[0] + 180
            except Exception:
                self.thumbnail_label.pack_forget()
                width = 260
        else:
            self.thumbnail_label.pack_forget()
            width = 260

        self.window.deiconify()
        self.window.lift()
        self.window.attributes('-topmost', True)

        # Position in upper-right corner
        self.window.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        x = screen_w - width - 20
        y = 40
        self.window.geometry(f'{width}x100+{x}+{y}')

    def _create_window(self):
        """Create notification window"""
        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.configure(bg='#3a3a3a')
        self.window.attributes('-topmost', True)

        # Container frame
        container = tk.Frame(self.window, bg='#3a3a3a')
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Thumbnail label (initially hidden)
        self.thumbnail_label = tk.Label(container, bg='#3a3a3a')

        # Text label
        self.label = tk.Label(
            container,
            text="",
            font=('SF Pro Text', 11) if sys.platform == 'darwin' else ('Segoe UI', 9),
            bg='#3a3a3a',
            fg='#ffffff',
            padx=12,
            pady=8
        )
        self.label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.window.withdraw()

    def hide(self):
        """Hide notification"""
        if self.window:
            self.window.withdraw()


class ResponseWindow:
    """Floating window to display AI responses - Spotlight style"""

    def __init__(self):
        self.root = None
        self.text_widget = None
        self.notification = None

    def show(self, title: str, content: str):
        """Show the response in a floating window with markdown rendering"""
        if self.root is None:
            self._create_window()

        # Hide notification when showing response
        if self.notification:
            self.notification.hide()

        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.focus_force()
        self.text_widget.focus_set()

        # Update content with markdown rendering
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete(1.0, tk.END)
        self._render_markdown(content)
        self.text_widget.config(state=tk.DISABLED)

        # Center on screen, positioned upper third like Spotlight
        self.root.update_idletasks()
        width = 800
        height = 800
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 3) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def show_notification(self, message: str, image_path: str = None):
        """Show a small notification toast with optional thumbnail"""
        if self.root is None:
            self._create_window()
        if self.notification is None:
            self.notification = NotificationWindow(self.root)
        self.notification.show(message, image_path)

    def _render_markdown(self, content: str):
        """Render markdown content with basic formatting"""
        # Process line by line
        lines = content.split('\n')
        i = 0
        in_code_block = False
        code_buffer = []

        while i < len(lines):
            line = lines[i]

            # Code blocks
            if line.startswith('```'):
                if in_code_block:
                    # End code block
                    code_text = '\n'.join(code_buffer)
                    self.text_widget.insert(tk.END, code_text + '\n', 'code')
                    code_buffer = []
                    in_code_block = False
                else:
                    # Start code block
                    in_code_block = True
                i += 1
                continue

            if in_code_block:
                code_buffer.append(line)
                i += 1
                continue

            # Headers
            if line.startswith('### '):
                self.text_widget.insert(tk.END, line[4:] + '\n', 'h3')
            elif line.startswith('## '):
                self.text_widget.insert(tk.END, line[3:] + '\n', 'h2')
            elif line.startswith('# '):
                self.text_widget.insert(tk.END, line[2:] + '\n', 'h1')
            # Bullet points
            elif line.startswith('- ') or line.startswith('* '):
                self._render_inline('  • ' + line[2:] + '\n')
            elif re.match(r'^\d+\. ', line):
                self._render_inline('  ' + line + '\n')
            # Regular text with inline formatting
            else:
                self._render_inline(line + '\n')

            i += 1

    def _render_inline(self, text: str):
        """Render inline markdown (bold, italic, code)"""
        # Pattern for **bold**, *italic*, `code`
        pattern = r'(\*\*.*?\*\*|\*.*?\*|`[^`]+`)'
        parts = re.split(pattern, text)

        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                self.text_widget.insert(tk.END, part[2:-2], 'bold')
            elif part.startswith('*') and part.endswith('*'):
                self.text_widget.insert(tk.END, part[1:-1], 'italic')
            elif part.startswith('`') and part.endswith('`'):
                self.text_widget.insert(tk.END, part[1:-1], 'inline_code')
            else:
                self.text_widget.insert(tk.END, part)

    def _create_window(self):
        """Create the tkinter window - borderless Spotlight style"""
        self.root = tk.Tk()
        self.root.title("")

        # Borderless window
        self.root.overrideredirect(True)
        self.root.configure(bg='#2d2d2d')
        self.root.attributes('-topmost', True)

        # Main frame with padding
        main_frame = tk.Frame(self.root, bg='#2d2d2d', padx=2, pady=2)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Inner content frame
        content_frame = tk.Frame(main_frame, bg='#1a1a1a')
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Base font
        base_font = ('SF Pro Text', 10) if sys.platform == 'darwin' else ('Segoe UI', 9)
        mono_font = ('SF Mono', 9) if sys.platform == 'darwin' else ('Consolas', 9)

        # Text widget
        self.text_widget = scrolledtext.ScrolledText(
            content_frame,
            wrap=tk.WORD,
            font=base_font,
            bg='#1a1a1a',
            fg='#e0e0e0',
            insertbackground='white',
            padx=16,
            pady=14,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True)

        # Close button
        close_btn = tk.Button(
            content_frame,
            text="Close",
            command=self._hide,
            font=(base_font[0], 9),
            bg='#333333',
            fg='#cccccc',
            activebackground='#444444',
            activeforeground='#ffffff',
            relief=tk.FLAT,
            padx=16,
            pady=4,
            cursor='hand2'
        )
        close_btn.pack(pady=(0, 10))

        # Configure text tags for markdown
        self.text_widget.tag_configure('h1', font=(base_font[0], 14, 'bold'), foreground='#ffffff')
        self.text_widget.tag_configure('h2', font=(base_font[0], 12, 'bold'), foreground='#ffffff')
        self.text_widget.tag_configure('h3', font=(base_font[0], 11, 'bold'), foreground='#ffffff')
        self.text_widget.tag_configure('bold', font=(base_font[0], 10, 'bold'))
        self.text_widget.tag_configure('italic', font=(base_font[0], 10, 'italic'))
        self.text_widget.tag_configure('code', font=mono_font, background='#2a2a2a', foreground='#80c080')
        self.text_widget.tag_configure('inline_code', font=mono_font, background='#2a2a2a', foreground='#80c080')

        # Minimal scrollbar
        self.text_widget.vbar.config(width=8)

        # Bind Escape to close (on both root and text widget)
        self.root.bind('<Escape>', lambda e: self._hide())
        self.text_widget.bind('<Escape>', lambda e: self._hide())

        # Start hidden
        self.root.withdraw()

    def _hide(self):
        """Hide the window"""
        if self.root:
            self.root.withdraw()

    def run(self):
        """Start the tkinter main loop"""
        if self.root is None:
            self._create_window()
        self.root.mainloop()


class ClueApp:
    """Main application class"""

    def __init__(self):
        self.window = ResponseWindow()
        self.hotkey_listener = None
        self.backend = BACKEND

        if self.backend == 'gemini':
            if not GEMINI_API_KEY:
                print("ERROR: GEMINI_API_KEY environment variable not set")
                print("Please set it with: export GEMINI_API_KEY='your-api-key'")
                sys.exit(1)
            from google import genai
            self.genai = genai
            self.client = genai.Client(api_key=GEMINI_API_KEY)
        elif self.backend == 'ollama':
            # Test Ollama connection
            try:
                req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                print(f"ERROR: Cannot connect to Ollama at {OLLAMA_URL}")
                print(f"Make sure Ollama is running: ollama serve")
                sys.exit(1)
        elif self.backend == 'gauth':
            # Load OAuth credentials from gauth
            if not os.path.exists(GAUTH_CREDENTIALS_PATH):
                print(f"ERROR: Gauth credentials not found at {GAUTH_CREDENTIALS_PATH}")
                print("Please run 'cd ~/sd/gauth && ./run.sh --provider antigravity' to login first")
                sys.exit(1)
            try:
                with open(GAUTH_CREDENTIALS_PATH, 'r') as f:
                    self.gauth_credentials = json.load(f)
            except Exception as e:
                print(f"ERROR: Failed to load gauth credentials: {e}")
                sys.exit(1)
        else:
            print(f"ERROR: Unknown backend '{self.backend}'. Use 'gemini', 'ollama', or 'gauth'")
            sys.exit(1)

    def capture_screenshot(self) -> str:
        """Capture screenshot of active window using macOS screencapture"""
        # Create temp file
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)

        # Get the frontmost window ID using CGWindowListCopyWindowInfo via Python
        # This is more reliable than AppleScript
        get_window_script = f'''
import Quartz
import sys
import os

my_pid = {os.getpid()}

# Get list of windows, front to back
options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)

# Find first window that belongs to a regular app (not menubar, dock, etc.)
for window in window_list:
    layer = window.get('kCGWindowLayer', 0)
    owner = window.get('kCGWindowOwnerName', '')
    owner_pid = window.get('kCGWindowOwnerPID', 0)
    # Layer 0 is normal windows, skip system UI and our own process
    if layer == 0 and owner != 'Window Server' and owner_pid != my_pid:
        window_id = window.get('kCGWindowNumber')
        if window_id:
            print(window_id)
            sys.exit(0)

# Fallback: no suitable window found
sys.exit(1)
'''
        result = subprocess.run(
            ['python3', '-c', get_window_script],
            capture_output=True, text=True
        )

        if result.returncode == 0 and result.stdout.strip():
            window_id = result.stdout.strip()
            print(f"[DEBUG] Capturing window ID: {window_id}")
            # -x: no sound, -o: no shadow, -l: capture window by ID
            cmd = ['screencapture', '-x', '-o', '-l', window_id, path]
        else:
            # Fallback to full screen if we can't get window ID
            print("[DEBUG] Could not get window ID, capturing full screen")
            cmd = ['screencapture', '-x', '-o', path]

        result = subprocess.run(cmd, capture_output=True)

        if result.returncode != 0:
            raise Exception(f"Screenshot failed: {result.stderr.decode()}")

        return path

    def analyze_image(self, image_path: str, prompt: str = DEFAULT_PROMPT) -> str:
        """Send image to AI for analysis"""
        if self.backend == 'gemini':
            return self._analyze_gemini(image_path, prompt)
        elif self.backend == 'ollama':
            return self._analyze_ollama(image_path, prompt)
        else:
            return self._analyze_gauth(image_path, prompt)

    def _analyze_gemini(self, image_path: str, prompt: str) -> str:
        """Send image to Gemini for analysis"""
        with open(image_path, 'rb') as f:
            image_data = f.read()

        image_part = self.genai.types.Part.from_bytes(data=image_data, mime_type='image/png')

        response = self.client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, image_part]
        )

        return response.text

    def _analyze_ollama(self, image_path: str, prompt: str) -> str:
        """Send image to Ollama for analysis"""
        with open(image_path, 'rb') as f:
            image_data = f.read()

        image_b64 = base64.b64encode(image_data).decode('utf-8')

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False
        }

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        return result.get('response', 'No response from Ollama')

    def _refresh_gauth_token(self) -> str:
        """Refresh gauth access token if expired"""
        current_time = int(time.time() * 1000)

        if current_time < self.gauth_credentials.get('expires_at', 0):
            return self.gauth_credentials['access_token']

        # Token expired, refresh it
        print("[DEBUG] Refreshing gauth token...")
        refresh_token = self.gauth_credentials.get('refresh_token')
        provider = self.gauth_credentials.get('provider', 'antigravity')

        # Antigravity OAuth config
        client_id = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
        client_secret = "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"

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=urllib.parse.urlencode(data).encode('utf-8'),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            tokens = json.loads(resp.read().decode('utf-8'))

        # Update credentials
        self.gauth_credentials['access_token'] = tokens['access_token']
        self.gauth_credentials['expires_at'] = current_time + (tokens.get('expires_in', 3600) * 1000)

        # Save updated credentials
        with open(GAUTH_CREDENTIALS_PATH, 'w') as f:
            json.dump(self.gauth_credentials, f, indent=2)

        return tokens['access_token']

    def _analyze_gauth(self, image_path: str, prompt: str) -> str:
        """Send image to Gemini via gauth OAuth (Antigravity)"""
        with open(image_path, 'rb') as f:
            image_data = f.read()

        image_b64 = base64.b64encode(image_data).decode('utf-8')
        access_token = self._refresh_gauth_token()
        project_id = self.gauth_credentials.get('project_id', 'rising-fact-p41fc')

        # Build request payload for Code Assist API (Antigravity format)
        request_id = f"clue-{int(time.time() * 1000)}"
        session_id = f"clue-session-{int(time.time() * 1000)}"

        payload = {
            "model": GAUTH_MODEL,
            "project": project_id,
            "request": {
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": image_b64
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 8192,
                },
                "sessionId": session_id,
            },
            "requestId": request_id,
            # Antigravity-specific fields
            "requestType": "agent",
            "userAgent": "antigravity",
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity/1.0 darwin/arm64",
            "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
            "Client-Metadata": json.dumps({
                "ideType": "IDE_UNSPECIFIED",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
            }),
        }

        url = f"{GAUTH_ENDPOINT}/{GAUTH_API_VERSION}:generateContent"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        # Extract text from response (Code Assist wraps in "response" field)
        inner = result.get('response', result)
        candidates = inner.get('candidates', [])
        if candidates:
            parts = candidates[0].get('content', {}).get('parts', [])

            # Separate thinking and response parts
            thinking_parts = []
            response_parts = []
            for p in parts:
                if p.get('thought') or p.get('thinking'):
                    if 'text' in p:
                        thinking_parts.append(p['text'])
                elif 'text' in p:
                    response_parts.append(p['text'])

            # Log thinking first
            if thinking_parts:
                print("\n" + "=" * 50)
                print("THINKING:")
                print("=" * 50)
                for t in thinking_parts:
                    print(t)
                print("=" * 50 + "\n")

            # Then log response
            response_text = '\n'.join(response_parts) if response_parts else 'No text in response'
            print("\n" + "-" * 50)
            print("RESPONSE:")
            print("-" * 50)
            print(response_text)
            print("-" * 50 + "\n")

            return response_text
        return 'No response from model'

    def on_hotkey(self):
        """Handle hotkey press"""
        print("Hotkey pressed! Capturing screenshot...")

        def process():
            try:
                # Capture screenshot FIRST before showing any UI
                image_path = self.capture_screenshot()
                print(f"Screenshot saved to: {image_path}")

                # Show small notification in upper-right with thumbnail
                self.window.root.after(0, lambda p=image_path: self.window.show_notification(
                    "Analyzing...", p
                ))

                # Analyze with AI
                print(f"Sending to {self.backend} for analysis...")
                start_time = time.time()
                response = self.analyze_image(image_path)
                elapsed = time.time() - start_time
                print(f"Analysis completed in {elapsed:.2f}s")

                # Show response (this also hides the notification)
                self.window.root.after(0, lambda: self.window.show("Clue", response))

                # Cleanup temp file
                os.unlink(image_path)

            except Exception as e:
                error_msg = f"Error: {str(e)}"
                print(error_msg)
                self.window.root.after(0, lambda: self.window.show("Clue - Error", error_msg))

        # Run in background thread to not block
        thread = threading.Thread(target=process)
        thread.daemon = True
        thread.start()

    def run(self):
        """Start the application"""
        if self.backend == 'gemini':
            model = GEMINI_MODEL
        elif self.backend == 'ollama':
            model = OLLAMA_MODEL
        else:
            model = GAUTH_MODEL
        print("=" * 50)
        print("Clue - AI Screenshot Assistant")
        print("=" * 50)
        print(f"Backend: {self.backend}")
        print(f"Model: {model}")
        print(f"Hotkey: {HOTKEY}")
        print("")
        print("Press Cmd+Shift+F to capture and analyze your screen")
        print("Press Ctrl+C to quit")
        print("=" * 50)

        # Track modifier states manually (more reliable than HotKey)
        self.cmd_pressed = False
        self.shift_pressed = False

        def on_press(key):
            if key == keyboard.Key.cmd or key == keyboard.Key.cmd_r:
                self.cmd_pressed = True
            elif key == keyboard.Key.shift or key == keyboard.Key.shift_r:
                self.shift_pressed = True
            elif hasattr(key, 'char') and key.char == 'f':
                if self.cmd_pressed and self.shift_pressed:
                    print("[DEBUG] Hotkey Cmd+Shift+F detected!")
                    self.on_hotkey()

        def on_release(key):
            if key == keyboard.Key.cmd or key == keyboard.Key.cmd_r:
                self.cmd_pressed = False
            elif key == keyboard.Key.shift or key == keyboard.Key.shift_r:
                self.shift_pressed = False

        self.hotkey_listener = keyboard.Listener(
            on_press=on_press,
            on_release=on_release
        )
        self.hotkey_listener.start()

        # Run the tkinter main loop (blocks)
        try:
            self.window.run()
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.hotkey_listener.stop()

    def canonical(self, key):
        """Convert key to canonical form for hotkey matching"""
        if hasattr(key, 'vk'):
            return keyboard.KeyCode.from_vk(key.vk)
        return key


def main():
    app = ClueApp()
    app.run()


if __name__ == '__main__':
    main()
