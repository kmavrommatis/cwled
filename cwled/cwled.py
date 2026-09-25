#!/usr/bin/env python3
import sys
from pathlib import Path


# Check if running as a bundled app (py2app)
if getattr(sys, 'frozen', False):
    # Running as bundled app
    # Add cwled package directory to path so relative imports work
    import os
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    cwled_pkg_path = os.path.join(bundle_dir, 'lib', 'python3.10', 'cwled')
    if os.path.exists(cwled_pkg_path):
        sys.path.insert(0, cwled_pkg_path)
else:
    # Running as script - add the src directory to the Python path
    sys.path.append(str(Path(__file__).parent / "cwled"))

if __name__ == "__main__":
    main()
