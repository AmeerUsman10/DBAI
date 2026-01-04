"""
SQL Template Engine
Generates SQL from classified queries without LLM.
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


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
        yarn_where = f"WHERE ENTRY_TYPE = '{movement_type}'" if movement_type else ""
        greige_where = f"WHERE ENTRY_TYPE = '{movement_type}'" if movement_type else ""
        
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


def generate_ranking_both_departments(params: Dict) -> str:
    """Handle ranking across both departments (special case)."""
    # This is complex - better to fall back to LLM
    return None
