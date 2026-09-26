"""
Entry point to run the DAT Discord Bot service.
"""

import sys
from apps.discord_bot.main import main

if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    main()
