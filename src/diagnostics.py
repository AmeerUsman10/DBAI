"""
Diagnostics Collector
Gathers platform info, installed packages, configuration, and logs for troubleshooting.

Next-level export: create a complete session bundle (zip) including
session state, queries, training, logs, config, and environment snapshot.
"""
import logging
import platform
import sys
import tempfile
import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
import importlib.metadata
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

def analyze_recent_logs(limit: int = 100) -> Dict:
    """
    Analyze recent log entries for errors, warnings, and user queries.

    Args:
        limit: Number of recent log lines to analyze

    Returns:
        Dict with analysis results including errors, warnings, queries, and SQL statements
    """
    project_root = Path(__file__).parent.parent
    log_path = project_root / "logs" / "diagnostics.log"

    analysis = {
        "errors": [],
        "warnings": [],
        "user_queries": [],
        "sql_queries": [],
        "database_operations": [],
        "recent_activity": [],
        "summary": ""
    }

    if not log_path.exists():
        analysis["summary"] = "No diagnostics log found"
        return analysis

    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-limit:] if len(lines) > limit else lines

        for i, line in enumerate(recent_lines):
            line = line.strip()

            # Capture errors
            if " - ERROR - " in line:
                # Get error and next few lines for context
                error_context = [line]
                for j in range(i+1, min(i+5, len(recent_lines))):
                    if recent_lines[j].strip() and not recent_lines[j].startswith("20"):
                        error_context.append(recent_lines[j].strip())
                analysis["errors"].append("\n".join(error_context))

            # Capture warnings
            elif " - WARNING - " in line:
                analysis["warnings"].append(line)

            # Capture user queries
            if "User question:" in line or "Query:" in line:
                match = re.search(r'(?:User question:|Query:)\s*(.+)', line)
                if match:
                    analysis["user_queries"].append(match.group(1))

            # Capture SQL queries
            if "Generated SQL:" in line or "SELECT " in line or "FROM " in line:
                analysis["sql_queries"].append(line)

            # Capture database operations
            if any(keyword in line for keyword in ["database", "connection", "query execution"]):
                analysis["database_operations"].append(line)

            # Keep recent activity (last 20 lines)
            if i >= len(recent_lines) - 20:
                analysis["recent_activity"].append(line)

        # Generate summary
        error_count = len(analysis["errors"])
        warning_count = len(analysis["warnings"])
        query_count = len(analysis["user_queries"])

        summary_parts = []
        if error_count > 0:
            summary_parts.append(f"🔴 {error_count} error(s)")
        if warning_count > 0:
            summary_parts.append(f"⚠️ {warning_count} warning(s)")
        if query_count > 0:
            summary_parts.append(f"💬 {query_count} user query(ies)")

        analysis["summary"] = " | ".join(summary_parts) if summary_parts else "✅ No issues detected"

    except Exception as e:
        logger.error(f"Error analyzing logs: {e}")
        analysis["summary"] = f"Error analyzing logs: {str(e)}"

    return analysis


def get_session_transcript(lines: int = 100) -> str:
    """
    Get a clean session transcript showing user queries and system responses.

    Args:
        lines: Number of recent log lines to analyze

    Returns:
        Formatted transcript of the session
    """
    project_root = Path(__file__).parent.parent
    log_path = project_root / "logs" / "diagnostics.log"

    if not log_path.exists():
        return "No diagnostics log found"

    try:
        with open(log_path, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        transcript = []
        transcript.append("=" * 80)
        transcript.append("SESSION TRANSCRIPT")
        transcript.append("=" * 80)
        transcript.append("")

        for line in recent_lines:
            line = line.strip()

            # Extract user queries
            if "USER QUERY:" in line:
                query = line.split("USER QUERY:", 1)[1].strip()
                transcript.append(f"\n👤 USER: {query}")

            # Extract generated SQL
            elif "GENERATED SQL:" in line:
                sql = line.split("GENERATED SQL:", 1)[1].strip()
                transcript.append(f"   🔧 SQL: {sql[:150]}{'...' if len(sql) > 150 else ''}")

            # Extract query results
            elif "QUERY SUCCESS:" in line:
                result = line.split("QUERY SUCCESS:", 1)[1].strip()
                transcript.append(f"   ✅ {result}")

            elif "QUERY FAILED:" in line:
                error = line.split("QUERY FAILED:", 1)[1].strip()
                transcript.append(f"   ❌ ERROR: {error[:200]}")

            # Extract response info
            elif "RESPONSE SENT:" in line:
                info = line.split("RESPONSE SENT:", 1)[1].strip()
                transcript.append(f"   📤 {info}")

            # Extract training events
            elif "USER TRAINING:" in line:
                training = line.split("USER TRAINING:", 1)[1].strip()
                transcript.append(f"\n🎓 TRAINING: {training}")

            elif "TRAINING SUCCESS:" in line:
                success = line.split("TRAINING SUCCESS:", 1)[1].strip()
                transcript.append(f"   ✅ {success}")

        transcript.append("")
        transcript.append("=" * 80)

        return "\n".join(transcript)

    except Exception as e:
        return f"Error reading session transcript: {str(e)}"


def get_recent_session_context(lines: int = 50) -> str:
    """
    Get recent session context in a human-readable format.

    Args:
        lines: Number of recent log lines to include

    Returns:
        Formatted string with recent session activity
    """
    project_root = Path(__file__).parent.parent
    log_path = project_root / "logs" / "diagnostics.log"

    if not log_path.exists():
        return "No diagnostics log found"

    try:
        with open(log_path, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        return "".join(recent_lines)
    except Exception as e:
        return f"Error reading logs: {str(e)}"


def redact_sensitive_data(content: str) -> str:
    """Redact API keys and sensitive information from content."""
    lines = content.split('\n')
    redacted_lines = []

    for line in lines:
        # Redact API keys and passwords
        if any(keyword in line.lower() for keyword in ['api_key', 'password', 'secret', 'token']):
            if '=' in line:
                key, _ = line.split('=', 1)
                redacted_lines.append(f"{key}=***REDACTED***")
            elif ':' in line:
                key, _ = line.split(':', 1)
                redacted_lines.append(f"{key}: ***REDACTED***")
            else:
                redacted_lines.append(line)
        else:
            redacted_lines.append(line)

    return '\n'.join(redacted_lines)

def get_installed_packages():
    """Get list of installed Python packages."""
    try:
        packages = []
        for dist in importlib.metadata.distributions():
            packages.append(f"{dist.name}=={dist.version}")
        return sorted(packages)
    except Exception as e:
        logger.error(f"Error getting installed packages: {e}")
        return [f"Error: {str(e)}"]

def collect_diagnostics() -> str:
    """
    Collect system diagnostics and return path to diagnostics file.

    Returns:
        Path to the diagnostics file
    """
    logger.info("Collecting diagnostics...")

    diagnostics = []

    # Header
    diagnostics.append("=" * 80)
    diagnostics.append("DBAI Diagnostics Report")
    diagnostics.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    diagnostics.append("=" * 80)
    diagnostics.append("")

    # System Information
    diagnostics.append("## System Information")
    diagnostics.append(f"Platform: {platform.platform()}")
    diagnostics.append(f"Python Version: {sys.version}")
    diagnostics.append(f"Python Executable: {sys.executable}")
    diagnostics.append("")

    # Installed Packages
    diagnostics.append("## Installed Packages")
    packages = get_installed_packages()
    for pkg in packages:
        diagnostics.append(pkg)
    diagnostics.append("")

    # Configuration File
    diagnostics.append("## Configuration (config.yaml)")
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config.yaml"

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config_content = f.read()
            diagnostics.append(redact_sensitive_data(config_content))
        except Exception as e:
            diagnostics.append(f"Error reading config: {e}")
    else:
        diagnostics.append("config.yaml not found")
    diagnostics.append("")

    # Environment Variables (redacted)
    diagnostics.append("## Environment Variables (.env)")
    env_path = project_root / ".env"

    if env_path.exists():
        try:
            with open(env_path, 'r') as f:
                env_content = f.read()
            diagnostics.append(redact_sensitive_data(env_content))
        except Exception as e:
            diagnostics.append(f"Error reading .env: {e}")
    else:
        diagnostics.append(".env file not found")
    diagnostics.append("")

    # Diagnostics Log Tail
    diagnostics.append("## Diagnostics Log (last 100 lines)")
    log_path = project_root / "logs" / "diagnostics.log"

    if log_path.exists():
        try:
            with open(log_path, 'r') as f:
                lines = f.readlines()
                tail_lines = lines[-100:] if len(lines) > 100 else lines
                diagnostics.extend([line.rstrip() for line in tail_lines])
        except Exception as e:
            diagnostics.append(f"Error reading diagnostics.log: {e}")
    else:
        diagnostics.append("diagnostics.log not found")
    diagnostics.append("")

    # Write to temporary file
    diagnostics_content = '\n'.join(diagnostics)

    try:
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            prefix=f'dbai_diagnostics_{datetime.now().strftime("%Y%m%d_%H%M%S")}_',
            delete=False
        )
        temp_file.write(diagnostics_content)
        temp_file.close()

        logger.info(f"Diagnostics saved to: {temp_file.name}")
        return temp_file.name
    except Exception as e:
        logger.error(f"Error writing diagnostics file: {e}")
        raise


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"<unavailable: {e}>"


def collect_full_session_bundle(include_sensitive: bool = False) -> str:
    """
    Create a complete diagnostics bundle as a zip archive with everything from the session.

    Contents typically include:
    - Session report (fresh Copilot export) and latest session state
    - All queries/errors/training events
    - Observability config
    - Training rules and audit trail
    - Knowledge store SQLite DB
    - Logs (runtime, diagnostics, audit JSONs if present)
    - Config files (config.yaml, .env [redacted unless include_sensitive])
    - Environment snapshot (platform, python, packages)

    Returns:
        Path to created .zip file
    """
    project_root = Path(__file__).parent.parent
    out_dir = project_root / "logs" / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_name = f"diagnostics_bundle_{timestamp}.zip"
    bundle_path = out_dir / bundle_name

    # Prepare transient manifest
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "paths": [],
        "notes": []
    }

    # Ensure a fresh Copilot session report is generated
    try:
        from src.session_tracker import get_session_tracker
        tracker = get_session_tracker()
        report_path = tracker.export_for_copilot()
        if report_path:
            manifest["copilot_report"] = report_path
    except Exception as e:
        manifest["notes"].append(f"export_for_copilot failed: {e}")

    # Candidate files and folders to include
    candidates = [
        project_root / "logs" / "latest_session.json",
        project_root / "logs" / "observability_config.json",
        project_root / "quick_training_rules.json",
        project_root / "logs" / "training_rule_audit.json",
        project_root / "logs" / "audit_events.json",
        project_root / "logs" / "diagnostics.log",
        project_root / "logs" / "runtime.log",
        project_root / "auto_generated_examples.md",
        project_root / "requirements.txt",
        project_root / "logs" / "dbai_training.db",
    ]

    # Include sessions folder (JSONs)
    sessions_dir = project_root / "logs" / "sessions"
    training_versions_dir = project_root / "logs" / "training" / "versions"

    # Config files
    config_yaml = project_root / "config.yaml"
    env_file = project_root / ".env"

    # Environment snapshot content
    env_snapshot = {
        "platform": platform.platform(),
        "python_version": sys.version,
        "executable": sys.executable,
        "installed_packages": get_installed_packages(),
    }

    with zipfile.ZipFile(bundle_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Write environment snapshot early; manifest will be written once at the end
        zf.writestr("environment_snapshot.json", json.dumps(env_snapshot, indent=2))

        # Add copilot report if available
        if manifest.get("copilot_report"):
            rp = Path(manifest["copilot_report"]).resolve()
            if rp.exists():
                zf.write(rp, arcname=f"sessions/{rp.name}")
                manifest["paths"].append(f"sessions/{rp.name}")

        # Add candidate files
        for path in candidates:
            try:
                if path and path.exists():
                    arc = path.relative_to(project_root)
                    zf.write(path, arcname=str(arc))
                    manifest["paths"].append(str(arc))
            except Exception as e:
                manifest["notes"].append(f"skip {path}: {e}")

        # Add sessions directory
        if sessions_dir.exists():
            for p in sessions_dir.glob("*.json"):
                try:
                    arc = p.relative_to(project_root)
                    zf.write(p, arcname=str(arc))
                    manifest["paths"].append(str(arc))
                except Exception:
                    pass

        # Add training versions if present
        if training_versions_dir.exists():
            for p in training_versions_dir.rglob("*"):
                if p.is_file():
                    try:
                        arc = p.relative_to(project_root)
                        zf.write(p, arcname=str(arc))
                        manifest["paths"].append(str(arc))
                    except Exception:
                        pass

        # Config.yaml (redacted if not include_sensitive)
        if config_yaml.exists():
            content = _safe_read_text(config_yaml)
            if not include_sensitive:
                content = redact_sensitive_data(content)
            zf.writestr("config.yaml", content)
            manifest["paths"].append("config.yaml")

        # .env (redacted unless include_sensitive)
        if env_file.exists():
            content = _safe_read_text(env_file)
            if not include_sensitive:
                content = redact_sensitive_data(content)
            zf.writestr(".env", content)
            manifest["paths"].append(".env")

    # Write manifest inside the zip with final paths (single write)
    try:
        with zipfile.ZipFile(bundle_path, mode="a", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    except Exception:
        pass

    logger.info(f"Full diagnostics bundle created: {bundle_path}")
    return str(bundle_path)

if __name__ == "__main__":
    # Test diagnostics collection
    diag_file = collect_diagnostics()
    print(f"Diagnostics saved to: {diag_file}")
