"""
BitcoinTX's backend. Importing it, as every entry point does first (the
server, the CLI, the migrations, the Mac app, the tests), makes the pinned
tzdata package the only source of timezone rules (#889).

Python's zoneinfo reads the computer's own zone files (zoneinfo.TZPATH,
/usr/share/zoneinfo first) before that package: Debian's in the Docker image
and so on StartOS, macOS's in the Mac app. A base-image or macOS update could
then move tax-year bounds, Form 8949 dates and holding periods with no change
to our lock, and two machines could read one ledger differently, which the
tax timezone promises they never do (#407).
"""

import zoneinfo

zoneinfo.reset_tzpath([])
# A zone read before this line (an import of another package's) is cached
# from the computer's files; none may outlive the switch.
zoneinfo.ZoneInfo.clear_cache()
