"""
Diagnostics Collector
Gathers platform info, installed packages, configuration, and logs for troubleshooting.
"""
import logging
import platform
import sys
import tempfile
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

if __name__ == "__main__":
    # Test diagnostics collection
    diag_file = collect_diagnostics()
    print(f"Diagnostics saved to: {diag_file}")
