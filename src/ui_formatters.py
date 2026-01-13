"""
UI Formatter Module
Handles formatting of query results, charts, and conversational components.
"""
import logging
from typing import Any, List, Dict, Optional

logger = logging.getLogger(__name__)

def format_result_as_html_table(rows: List[Any], columns: List[str], result_label: Optional[str] = None) -> str:
    \"\"\"Creates a professional HTML table for Gradio display.\"\"\"
    if not rows or not columns:
        return "<p>No results found.</p>"
    
    response = ""
    if result_label:
        response += f"**📊 Data Source:** {result_label}\\n\\n"
    
    response += f"**Query Results** ({len(rows)} rows)\\n\\n"
    
    # Header with gradient background
    table_html = '<div style="overflow-x: auto; max-height: 600px;">'
    table_html += '<table style="width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">'
    table_html += '<thead style="position: sticky; top: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;"><tr>'
    
    for col in columns:
        table_html += f'<th style="padding: 14px 16px; text-align: left; font-weight: 600; text-transform: uppercase; font-size: 12px;">{col}</th>'
    table_html += '</tr></thead><tbody>'
    
    # Body with alternating rows
    for idx, row in enumerate(rows[:100]):
        bg_color = "#f8f9fa" if idx % 2 == 0 else "#ffffff"
        table_html += f'<tr style="background-color: {bg_color};">'
        for val in row:
            formatted_val = f"{val:,.2f}" if isinstance(val, (float)) else (f"{val:,}" if isinstance(val, int) else str(val or ""))
            table_html += f'<td style="padding: 12px 16px; border-bottom: 1px solid #e9ecef;">{formatted_val}</td>'
        table_html += '</tr>'
    
    table_html += '</tbody></table></div>'
    
    if len(rows) > 100:
        table_html += f"\\n\\n*Showing first 100 of {len(rows):,} rows*"
        
    return response + table_html


