"""
Developer Notes Management
Persistent note-taking and change tracking within the DBAI application.
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Tuple

logger = logging.getLogger(__name__)

# Notes storage location
NOTES_DIR = Path(__file__).parent.parent / "logs"
NOTES_FILE = NOTES_DIR / "dev_notes.md"

# Default template
DEFAULT_NOTES = """# DBAI Development Notes
*Last updated: {timestamp}*

---

## 🎯 Planned Changes (Not Started)
<!-- List planned features, improvements, or fixes here -->

- [ ] Example: Add new feature X
- [ ] Example: Fix bug in Y
- [ ] Example: Improve Z performance

---

## 🚧 In Progress
<!-- Currently working on these items -->

- [ ] Example: Implementing feature A
  - Started: {date}
  - Notes: Working on backend logic

---

## ✅ Completed
<!-- Finished and deployed changes -->

- [x] Added in-chat feedback system (Jan 7, 2026)
  - Thumbs up/down buttons
  - Comment collection
  - Analytics dashboard
  - Training rule integration

---

## 🐛 Known Bugs
<!-- Issues that need fixing -->

- Example: Issue with X under Y conditions

---

## 💡 Ideas & Future Enhancements
<!-- Backlog of ideas for later consideration -->

- Example: Consider adding feature Z
- Example: Explore technology W for better performance

---

## 📝 Session Notes
<!-- Quick notes from development sessions -->

### Session {date}
- Notes from today's work...

---

## 🔧 Configuration Changes
<!-- Track important config/environment changes -->

- Example: Updated database driver to version X (Date)

---

## 📚 Technical Decisions
<!-- Document why certain approaches were chosen -->

- **Gradio vs Chainlit**: Starting with Gradio enhancement, will evaluate migration based on feedback (Jan 7, 2026)

"""

def ensure_notes_file():
    """Ensure notes directory and file exist."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    
    if not NOTES_FILE.exists():
        # Create with default template
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date = datetime.now().strftime("%Y-%m-%d")
        
        default_content = DEFAULT_NOTES.format(timestamp=timestamp, date=date)
        
        with open(NOTES_FILE, 'w', encoding='utf-8') as f:
            f.write(default_content)
        
        logger.info(f"Created dev notes file: {NOTES_FILE}")

def load_notes() -> str:
    """Load developer notes from file."""
    ensure_notes_file()
    
    try:
        with open(NOTES_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        logger.error(f"Error loading notes: {e}")
        return f"❌ Error loading notes: {str(e)}"

def save_notes(content: str) -> Tuple[bool, str]:
    """
    Save developer notes to file.
    
    Args:
        content: Markdown content to save
    
    Returns:
        Tuple of (success, message)
    """
    ensure_notes_file()
    
    try:
        # Update timestamp in first line
        lines = content.split('\n')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Update the timestamp line if it exists
        for i, line in enumerate(lines):
            if line.startswith('*Last updated:'):
                lines[i] = f"*Last updated: {timestamp}*"
                break
        
        updated_content = '\n'.join(lines)
        
        # Save to file
        with open(NOTES_FILE, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        logger.info(f"Saved dev notes ({len(updated_content)} chars)")
        return True, f"✅ Notes saved successfully at {timestamp}"
        
    except Exception as e:
        logger.error(f"Error saving notes: {e}")
        return False, f"❌ Error saving notes: {str(e)}"

def add_quick_note(note: str, section: str = "Session Notes") -> Tuple[bool, str]:
    """
    Add a quick note to a specific section.
    
    Args:
        note: Note content to add
        section: Section to add to (default: Session Notes)
    
    Returns:
        Tuple of (success, message)
    """
    try:
        content = load_notes()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date = datetime.now().strftime("%Y-%m-%d")
        
        # Find the section
        section_marker = f"## {section}"
        
        if section_marker in content:
            # Add note under the section
            parts = content.split(section_marker)
            if len(parts) >= 2:
                # Find next section or end
                after_section = parts[1]
                next_section_idx = after_section.find('\n##')
                
                if next_section_idx != -1:
                    before_next = after_section[:next_section_idx]
                    after_next = after_section[next_section_idx:]
                    
                    # Add note
                    new_note = f"\n- [{timestamp}] {note}\n"
                    updated_section = before_next + new_note
                    
                    content = parts[0] + section_marker + updated_section + after_next
                else:
                    # Last section
                    new_note = f"\n- [{timestamp}] {note}\n"
                    content = parts[0] + section_marker + parts[1] + new_note
        else:
            # Section doesn't exist, add at end
            content += f"\n\n## {section}\n\n- [{timestamp}] {note}\n"
        
        return save_notes(content)
        
    except Exception as e:
        logger.error(f"Error adding quick note: {e}")
        return False, f"❌ Error: {str(e)}"

def get_notes_preview() -> str:
    """Get a preview of current notes (first 500 chars)."""
    content = load_notes()
    
    if len(content) <= 500:
        return content
    
    return content[:500] + "\n\n*... (truncated, open Developer Notes tab to see full content)*"
