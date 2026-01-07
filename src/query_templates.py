"""
SQL Template Engine
Generates SQL from classified queries without LLM.
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def build_date_filter(time_filter: Dict, table_alias: str = "") -> str:
    """
    Build WHERE clause for date filtering.
    
    Args:
        time_filter: Dict with 'type', 'raw', 'groups'
        table_alias: Optional table alias prefix (e.g., 'c.')
    
    Returns:
        WHERE clause string (e.g., "WHERE DATE >= DATEADD(day, -30, GETDATE())")
    """
    if not time_filter:
        return ""
    
    prefix = f"{table_alias}." if table_alias else ""
    date_col = f"{prefix}DATE"
    
    filter_type = time_filter.get('type')
    groups = time_filter.get('groups', ())
    raw = time_filter.get('raw', '').lower()
    
    # "last N days/months/years"
    if 'last' in raw and len(groups) >= 2:
        n = groups[0]
        unit = groups[1].rstrip('s')  # Remove plural
        return f"WHERE {date_col} >= DATEADD({unit}, -{n}, GETDATE())"
    
    # "this month/quarter/year"
    if 'this month' in raw:
        return f"WHERE {date_col} >= DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0) AND {date_col} < DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)"
    elif 'this quarter' in raw:
        return f"WHERE {date_col} >= DATEADD(quarter, DATEDIFF(quarter, 0, GETDATE()), 0) AND {date_col} < DATEADD(quarter, DATEDIFF(quarter, 0, GETDATE()) + 1, 0)"
    elif 'this year' in raw:
        return f"WHERE {date_col} >= DATEADD(year, DATEDIFF(year, 0, GETDATE()), 0) AND {date_col} < DATEADD(year, DATEDIFF(year, 0, GETDATE()) + 1, 0)"
    
    # "year to date" / "ytd"
    if 'year to date' in raw or 'ytd' in raw:
        return f"WHERE {date_col} >= DATEADD(year, DATEDIFF(year, 0, GETDATE()), 0)"
    
    # Month name ("in January")
    months = ['january', 'february', 'march', 'april', 'may', 'june', 
              'july', 'august', 'september', 'october', 'november', 'december']
    for idx, month in enumerate(months, 1):
        if month in raw:
            return f"WHERE MONTH({date_col}) = {idx}"
    
    return ""


def generate_sql_from_template(classification: Dict) -> str:
    """
    Generate SQL directly from classification without LLM.
    
    Args:
        classification: Output from query_classifier.classify_query()
        
    Returns:
        SQL query string
    """
    query_type = classification['type']
    params = classification['params']
    
    if query_type == 'ranking':
        return generate_ranking_sql(params)
    elif query_type == 'aggregation':
        return generate_aggregation_sql(params)
    elif query_type == 'segmentation':
        return generate_segmentation_sql(params)
    elif query_type == 'detail':
        return generate_detail_sql(params)
    elif query_type == 'time_breakdown':
        return generate_time_breakdown_sql(params)
    elif query_type == 'comparison':
        return generate_comparison_sql(params)
    else:
        return None


def generate_ranking_sql(params: Dict) -> str:
    """
    Generate TOP N ranking query.
    
    Business logic:
    - Default: Both departments combined (Yarn + Greige)
    - Rank by total Amount across both
    - No movement type filter unless explicitly specified
    - If breakdown requested: Show Department × Movement Type segmentation
    """
    entity = params['entity']
    limit = params['limit']
    movement_type = params['movement_type']
    dept = params['department']
    breakdown = params.get('breakdown')
    time_filter = params.get('time_filter')
    
    # Build date filter clause
    date_filter_yarn = build_date_filter(time_filter)
    date_filter_greige = build_date_filter(time_filter)
    
    # BUSINESS RULE: Suppliers default to BOTH departments combined
    if entity == 'supplier':
        
        # MULTI-DIMENSIONAL BREAKDOWN: Department × Movement Type
        if breakdown and 'department' in breakdown and 'movement_type' in breakdown:
            # Get top N suppliers, then show breakdown for each
            sql = f"""WITH TopSuppliers AS (
    SELECT TOP {limit} Supplier, SUM(TotalAmount) as GrandTotal
    FROM (
        SELECT SUPPLIER as Supplier, SUM(AMOUNT) as TotalAmount
        FROM YarnData
        GROUP BY SUPPLIER
        
        UNION ALL
        
        SELECT SUPP_NAME as Supplier, SUM(AMOUNT) as TotalAmount
        FROM GreigeData
        GROUP BY SUPP_NAME
    ) AS AllSuppliers
    GROUP BY Supplier
    ORDER BY SUM(TotalAmount) DESC
)
SELECT c.Supplier, c.Department, c.MovementType,
       SUM(c.Amount) as 'Total PKR',
       SUM(c.Quantity) as 'Total Quantity',
       COUNT(*) as 'Record Count'
FROM (
    SELECT SUPPLIER as Supplier, 'Yarn' as Department,
           ENTRY_TYPE as MovementType,
           AMOUNT as Amount, LBS as Quantity
    FROM YarnData
    
    UNION ALL
    
    SELECT SUPP_NAME as Supplier, 'Greige' as Department,
           ENTRY_TYPE as MovementType,
           AMOUNT as Amount, METER as Quantity
    FROM GreigeData
) AS c
WHERE c.Supplier IN (SELECT Supplier FROM TopSuppliers)
GROUP BY c.Supplier, c.Department, c.MovementType
ORDER BY (
    SELECT GrandTotal FROM TopSuppliers ts WHERE ts.Supplier = c.Supplier
) DESC, c.Supplier, c.Department, c.MovementType"""
            
            logger.info(f"Generated multi-dimensional breakdown SQL (Supplier × Department × Movement Type)")
            return sql
        
        # AGGREGATED VIEW: Single ranking by total amount
        # Combine movement type and date filters
        yarn_where_parts = []
        if movement_type:
            yarn_where_parts.append(f"ENTRY_TYPE = '{movement_type}'")
        if date_filter_yarn:
            yarn_where_parts.append(date_filter_yarn.replace('WHERE ', ''))
        yarn_where = f"WHERE {' AND '.join(yarn_where_parts)}" if yarn_where_parts else ""
        
        greige_where_parts = []
        if movement_type:
            greige_where_parts.append(f"ENTRY_TYPE = '{movement_type}'")
        if date_filter_greige:
            greige_where_parts.append(date_filter_greige.replace('WHERE ', ''))
        greige_where = f"WHERE {' AND '.join(greige_where_parts)}" if greige_where_parts else ""
        
        sql = f"""SELECT TOP {limit} Supplier, SUM(TotalAmount) as 'Total PKR', SUM(TotalQty) as 'Total Quantity', SUM(RecordCount) as 'Record Count'
FROM (
    SELECT SUPPLIER as Supplier, SUM(AMOUNT) as TotalAmount, SUM(LBS) as TotalQty, COUNT(*) as RecordCount
    FROM YarnData
    {yarn_where}
    GROUP BY SUPPLIER
    
    UNION ALL
    
    SELECT SUPP_NAME as Supplier, SUM(AMOUNT) as TotalAmount, SUM(METER) as TotalQty, COUNT(*) as RecordCount
    FROM GreigeData
    {greige_where}
    GROUP BY SUPP_NAME
) AS CombinedSuppliers
GROUP BY Supplier
ORDER BY SUM(TotalAmount) DESC"""
        
        logger.info(f"Generated aggregated multi-department supplier ranking SQL from template")
        return sql
    
    # Single department for other entities (quality, type)
    if dept == 'yarn':
        table = 'YarnData'
        entity_col = 'QUALITY'
        metric_cols = [
            f"SUM(AMOUNT) as 'Total PKR'",
            f"SUM(LBS) as 'Total LBS'",
            f"SUM(BAGS) as 'Total Bags'",
            f"COUNT(*) as 'Record Count'"
        ]
    elif dept == 'greige':
        table = 'GreigeData'
        entity_col = 'AC_NAME'
        metric_cols = [
            f"SUM(AMOUNT) as 'Total PKR'",
            f"SUM(METER) as 'Total Meters'",
            f"COUNT(*) as 'Record Count'"
        ]
    else:
        # Default to yarn for non-supplier entities
        table = 'YarnData'
        entity_col = 'QUALITY'
        metric_cols = [
            f"SUM(AMOUNT) as 'Total PKR'",
            f"SUM(LBS) as 'Total LBS'",
            f"COUNT(*) as 'Record Count'"
        ]
    
    # WHERE clause
    where_clause = ""
    if movement_type:
        where_clause = f"WHERE ENTRY_TYPE = '{movement_type}'"
    
    sql = f"""SELECT TOP {limit} 
    {entity_col} as '{entity.capitalize()}',
    {', '.join(metric_cols)}
FROM {table}
{where_clause}
GROUP BY {entity_col}
ORDER BY SUM(AMOUNT) DESC"""
    
    logger.info(f"Generated ranking SQL from template: {sql[:100]}...")
    return sql


def generate_aggregation_sql(params: Dict) -> str:
    """
    Generate aggregation/total query.
    
    BUSINESS RULE: Only include data from requested department.
    - 'yarn total' → Only YarnData
    - 'greige total' → Only GreigeData
    - 'total' (both) → Both departments with subqueries
    """
    dept = params['department']
    movement_type = params['movement_type']
    
    if dept == 'yarn':
        # Yarn only
        where_clause = f"WHERE ENTRY_TYPE = '{movement_type}'" if movement_type else ""
        
        sql = f"""SELECT 
    SUM(LBS) as 'Total LBS',
    SUM(AMOUNT) as 'Total PKR',
    SUM(BAGS) as 'Total Bags',
    COUNT(*) as 'Record Count'
FROM YarnData
{where_clause}"""
        logger.info(f"Generated yarn-only aggregation SQL from template")
    
    elif dept == 'greige':
        # Greige only
        where_clause = f"WHERE ENTRY_TYPE = '{movement_type}'" if movement_type else ""
        
        sql = f"""SELECT 
    SUM(METER) as 'Total Meters',
    SUM(AMOUNT) as 'Total PKR',
    COUNT(*) as 'Record Count'
FROM GreigeData
{where_clause}"""
        logger.info(f"Generated greige-only aggregation SQL from template")
    
    else:  # both
        # Multi-department - use subqueries (Training Rule #2: NO JOIN)
        where_yarn = f"WHERE ENTRY_TYPE = '{movement_type}'" if movement_type else ""
        where_greige = f"WHERE ENTRY_TYPE = '{movement_type}'" if movement_type else ""
        
        sql = f"""SELECT 
    (SELECT SUM(LBS) FROM YarnData {where_yarn}) as 'Yarn Total LBS',
    (SELECT SUM(AMOUNT) FROM YarnData {where_yarn}) as 'Yarn Total PKR',
    (SELECT SUM(BAGS) FROM YarnData {where_yarn}) as 'Yarn Total Bags',
    (SELECT COUNT(*) FROM YarnData {where_yarn}) as 'Yarn Count',
    (SELECT SUM(METER) FROM GreigeData {where_greige}) as 'Greige Total Meters',
    (SELECT SUM(AMOUNT) FROM GreigeData {where_greige}) as 'Greige Total PKR',
    (SELECT COUNT(*) FROM GreigeData {where_greige}) as 'Greige Count'"""
        logger.info(f"Generated multi-department aggregation SQL from template")
    
    return sql


def generate_segmentation_sql(params: Dict) -> str:
    """
    Generate segmentation query (GROUP BY).
    
    Template: SELECT dimension, SUM(metric), COUNT(*)
              FROM table
              GROUP BY dimension
              ORDER BY SUM(metric) DESC
    """
    dept = params['department']
    entity = params['entity']
    
    if dept == 'yarn':
        table = 'YarnData'
        
        if entity == 'entry_type':
            group_col = 'ENTRY_TYPE'
            sql = f"""SELECT 
    ENTRY_TYPE as 'Movement Type',
    SUM(LBS) as 'Total LBS',
    SUM(AMOUNT) as 'Total PKR',
    SUM(BAGS) as 'Total Bags',
    COUNT(*) as 'Record Count'
FROM YarnData
GROUP BY ENTRY_TYPE
ORDER BY SUM(AMOUNT) DESC"""
        
        elif entity == 'supplier':
            sql = f"""SELECT 
    SUPPLIER as 'Supplier',
    SUM(LBS) as 'Total LBS',
    SUM(AMOUNT) as 'Total PKR',
    SUM(BAGS) as 'Total Bags',
    COUNT(*) as 'Record Count'
FROM YarnData
GROUP BY SUPPLIER
ORDER BY SUM(AMOUNT) DESC"""
        
        else:
            sql = f"""SELECT 
    QUALITY as 'Quality',
    SUM(LBS) as 'Total LBS',
    SUM(AMOUNT) as 'Total PKR',
    COUNT(*) as 'Record Count'
FROM YarnData
GROUP BY QUALITY
ORDER BY SUM(AMOUNT) DESC"""
    
    else:  # greige
        if entity == 'supplier':
            sql = f"""SELECT 
    SUPP_NAME as 'Supplier',
    SUM(METER) as 'Total Meters',
    SUM(AMOUNT) as 'Total PKR',
    COUNT(*) as 'Record Count'
FROM GreigeData
GROUP BY SUPP_NAME
ORDER BY SUM(AMOUNT) DESC"""
        else:
            sql = f"""SELECT 
    AC_NAME as 'Article',
    SUM(METER) as 'Total Meters',
    SUM(AMOUNT) as 'Total PKR',
    COUNT(*) as 'Record Count'
FROM GreigeData
GROUP BY AC_NAME
ORDER BY SUM(AMOUNT) DESC"""
    
    logger.info(f"Generated segmentation SQL from template")
    return sql


def generate_detail_sql(params: Dict) -> str:
    """
    Generate detail/list query.
    
    Template: SELECT * FROM table WHERE condition
    """
    dept = params['department']
    specific = params['specific_value']
    
    if dept == 'yarn':
        table = 'YarnData'
        # Try to match supplier name
        sql = f"""SELECT 
    DOCDATE as 'Date',
    SUPPLIER as 'Supplier',
    YARN as 'Yarn Type',
    QUALITY as 'Quality',
    LBS as 'LBS',
    AMOUNT as 'Amount PKR',
    BAGS as 'Bags',
    ENTRY_TYPE as 'Movement Type'
FROM YarnData
WHERE SUPPLIER LIKE '%{specific}%'
ORDER BY DOCDATE DESC"""
    else:
        sql = f"""SELECT 
    DOCDATE as 'Date',
    SUPP_NAME as 'Supplier',
    AC_NAME as 'Article',
    METER as 'Meters',
    AMOUNT as 'Amount PKR',
    ENTRY_TYPE as 'Type'
FROM GreigeData
WHERE SUPP_NAME LIKE '%{specific}%'
ORDER BY DOCDATE DESC"""
    
    logger.info(f"Generated detail SQL from template")
    return sql


def generate_time_breakdown_sql(params: Dict) -> str:
    """
    Generate time-based breakdown query (monthly/quarterly/yearly totals).
    
    Template: SELECT FORMAT(DATE, 'yyyy-MM'), SUM(metric)
              FROM table
              GROUP BY FORMAT(DATE, 'yyyy-MM')
              ORDER BY FORMAT(DATE, 'yyyy-MM')
    """
    dept = params['department']
    time_filter = params.get('time_filter', {})
    period = time_filter.get('period', 'monthly')
    
    # Date format for grouping
    if period == 'yearly':
        date_format = 'yyyy'
        label = 'Year'
    elif period == 'quarterly':
        date_format = 'yyyy-Q'
        label = 'Quarter'
    else:  # monthly
        date_format = 'yyyy-MM'
        label = 'Month'
    
    if dept == 'yarn':
        sql = f"""SELECT 
    FORMAT(DATE, '{date_format}') as '{label}',
    SUM(AMOUNT) as 'Total PKR',
    SUM(LBS) as 'Total LBS',
    SUM(BAGS) as 'Total Bags',
    COUNT(*) as 'Record Count'
FROM YarnData
GROUP BY FORMAT(DATE, '{date_format}')
ORDER BY FORMAT(DATE, '{date_format}')"""
    
    elif dept == 'greige':
        sql = f"""SELECT 
    FORMAT(DATE, '{date_format}') as '{label}',
    SUM(AMOUNT) as 'Total PKR',
    SUM(METER) as 'Total Meters',
    COUNT(*) as 'Record Count'
FROM GreigeData
GROUP BY FORMAT(DATE, '{date_format}')
ORDER BY FORMAT(DATE, '{date_format}')"""
    
    else:  # both
        sql = f"""SELECT 
    Period as '{label}',
    SUM(TotalPKR) as 'Total PKR',
    SUM(TotalQty) as 'Total Quantity',
    SUM(RecordCount) as 'Record Count'
FROM (
    SELECT FORMAT(DATE, '{date_format}') as Period,
           SUM(AMOUNT) as TotalPKR,
           SUM(LBS) as TotalQty,
           COUNT(*) as RecordCount
    FROM YarnData
    GROUP BY FORMAT(DATE, '{date_format}')
    
    UNION ALL
    
    SELECT FORMAT(DATE, '{date_format}') as Period,
           SUM(AMOUNT) as TotalPKR,
           SUM(METER) as TotalQty,
           COUNT(*) as RecordCount
    FROM GreigeData
    GROUP BY FORMAT(DATE, '{date_format}')
) AS Combined
GROUP BY Period
ORDER BY Period"""
    
    logger.info(f"Generated {period} time breakdown SQL from template")
    return sql


def generate_comparison_sql(params: Dict) -> str:
    """
    Generate comparison query (Department A vs B, Supplier X vs Y, etc.).
    
    Template: SELECT entity, metrics FROM table WHERE entity IN (A, B)
              GROUP BY entity
    """
    comparison = params.get('comparison', {})
    entities = comparison.get('entities', ())
    dept = params['department']
    time_filter = params.get('time_filter')
    
    if not entities or len(entities) < 2:
        return None
    
    entity1 = entities[0].strip()
    entity2 = entities[1].strip()
    
    # Detect comparison type
    if entity1 in ['yarn', 'greige'] or entity2 in ['yarn', 'greige']:
        # Department comparison
        date_filter = build_date_filter(time_filter)
        
        sql = f"""SELECT 
    'Yarn' as Department,
    SUM(AMOUNT) as 'Total PKR',
    SUM(LBS) as 'Total Quantity',
    SUM(BAGS) as 'Total Bags',
    COUNT(*) as 'Record Count'
FROM YarnData
{date_filter}

UNION ALL

SELECT 
    'Greige' as Department,
    SUM(AMOUNT) as 'Total PKR',
    SUM(METER) as 'Total Quantity',
    NULL as 'Total Bags',
    COUNT(*) as 'Record Count'
FROM GreigeData
{date_filter}"""
        
        logger.info(f"Generated department comparison SQL from template")
        return sql
    
    else:
        # Supplier comparison or other entity comparison
        if dept == 'yarn':
            table = 'YarnData'
            entity_col = 'SUPPLIER'
            date_filter = build_date_filter(time_filter)
            
            sql = f"""SELECT 
    {entity_col} as 'Supplier',
    SUM(AMOUNT) as 'Total PKR',
    SUM(LBS) as 'Total LBS',
    SUM(BAGS) as 'Total Bags',
    COUNT(*) as 'Record Count'
FROM {table}
WHERE {entity_col} LIKE '%{entity1}%' OR {entity_col} LIKE '%{entity2}%'
{date_filter.replace('WHERE', 'AND') if date_filter else ''}
GROUP BY {entity_col}
ORDER BY {entity_col}"""
        
        elif dept == 'greige':
            table = 'GreigeData'
            entity_col = 'SUPP_NAME'
            date_filter = build_date_filter(time_filter)
            
            sql = f"""SELECT 
    {entity_col} as 'Supplier',
    SUM(AMOUNT) as 'Total PKR',
    SUM(METER) as 'Total Meters',
    COUNT(*) as 'Record Count'
FROM {table}
WHERE {entity_col} LIKE '%{entity1}%' OR {entity_col} LIKE '%{entity2}%'
{date_filter.replace('WHERE', 'AND') if date_filter else ''}
GROUP BY {entity_col}
ORDER BY {entity_col}"""
        
        else:  # both
            # Multi-department supplier comparison
            date_filter_yarn = build_date_filter(time_filter)
            date_filter_greige = build_date_filter(time_filter)
            
            sql = f"""SELECT 
    Supplier,
    SUM(TotalPKR) as 'Total PKR',
    SUM(TotalQty) as 'Total Quantity',
    COUNT(*) as 'Record Count'
FROM (
    SELECT SUPPLIER as Supplier,
           SUM(AMOUNT) as TotalPKR,
           SUM(LBS) as TotalQty
    FROM YarnData
    WHERE SUPPLIER LIKE '%{entity1}%' OR SUPPLIER LIKE '%{entity2}%'
    {date_filter_yarn.replace('WHERE', 'AND') if date_filter_yarn else ''}
    GROUP BY SUPPLIER
    
    UNION ALL
    
    SELECT SUPP_NAME as Supplier,
           SUM(AMOUNT) as TotalPKR,
           SUM(METER) as TotalQty
    FROM GreigeData
    WHERE SUPP_NAME LIKE '%{entity1}%' OR SUPP_NAME LIKE '%{entity2}%'
    {date_filter_greige.replace('WHERE', 'AND') if date_filter_greige else ''}
    GROUP BY SUPP_NAME
) AS Combined
GROUP BY Supplier
ORDER BY Supplier"""
        
        logger.info(f"Generated supplier comparison SQL from template")
        return sql


def generate_ranking_both_departments(params: Dict) -> str:
    """Handle ranking across both departments (special case)."""
    # This is complex - better to fall back to LLM
    return None
