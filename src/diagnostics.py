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

logger = logging.getLogger(__name__)

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
