"""
Entry point to run the TTS Server service on port 13300.
"""

import sys
import uvicorn
from shared.config import settings

if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    print(f"Starting DAT TTS Engine on {settings.TTS_HOST}:{settings.TTS_PORT}...")
    uvicorn.run(
        "apps.tts_server.main:app",
        host=settings.TTS_HOST,
        port=settings.TTS_PORT,
        log_level="info",
        reload=False
    )
