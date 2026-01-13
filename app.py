"""
DBAI Application Runner
Ensures the project root is on sys.path and launches the main application.
"""
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Run the main application
if __name__ == "__main__":
    from src.main import main
    main()
