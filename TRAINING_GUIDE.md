# 🧠 DBAI Intelligent Training System Guide

## Overview

This system makes your AI database assistant **smarter over time** by understanding your business context, learning from interactions, and helping users ask better questions.

---

## 🎯 Core Features

### 1. **Business Context Intelligence** (`metadata.json`)
- **What it does**: Teaches AI about your Pakistani textile business
- **Includes**:
  - Column definitions with units (PKR, LBS, meters, inches)
  - Business terminology (greige fabric, CT/carton, PC/pieces)
  - Common query patterns with SQL templates
  - Department-specific context

**Example**: When user asks "total amount", AI knows:
- Could mean `SUM(AMOUNT)` in PKR currency
- Should clarify: by supplier? by date range? by type?

### 2. **Query Clarity Analysis** (`src/clarity.py`)
- **What it does**: Detects vague questions and asks for clarification
- **Detects**:
  - Single-word queries ("supplier", "total")
  - Ambiguous terms ("amount wise", "supplier name")
  - Missing context (time period, filters)

**Example Flow**:
```
User: "supplier total"
AI: Could you clarify which of these you're looking for?
    1. Total amount spent per supplier
    2. Total LBS ordered per supplier
    3. Total bags received per supplier
    4. List all supplier names
```

### 3. **Learning System** (`src/learnings.py`)
- **What it does**: Remembers successful clarifications and patterns
- **Features**:
  - Auto-categorizes queries (supplier, amount, inventory, time-based)
  - Fuzzy matching to avoid duplicate learnings
  - Usage tracking and feedback history
  - Multi-factor relevance scoring

**Example Learning**:
```json
{
  "original_query": "total for ahmed textile",
  "clarified_query": "Total amount in PKR spent with supplier 'Ahmed Textile'",
  "sql": "SELECT SUM(AMOUNT) FROM YarnData WHERE SUPPLIER LIKE '%ahmed%'",
  "category": "amount_calculations",
  "usage_count": 5,
  "feedback": ["positive", "positive"]
}
```

### 4. **Enhanced SQL Generation** (`src/llm.py`)
- **What it does**: Injects metadata and learnings into LLM prompts
- **Process**:
  1. Load metadata (column definitions, units, business terms)
  2. Find relevant past learnings (fuzzy match current query)
  3. Build enhanced prompt with context
  4. Generate more accurate SQL

---

## 📊 How It Works

### User Query Flow

```
1. User asks question
   ↓
2. Clarity analyzer checks vagueness (score 0-100)
   ↓
3a. If clear (score ≥ 70) → Proceed to SQL generation
3b. If vague (score < 70) → Show clarification options
   ↓
4. User selects option or rephrases
   ↓
5. LLM generates SQL using:
   - Metadata (column definitions, units)
   - Relevant learnings (similar past queries)
   - Business context (Pakistani textile terms)
   ↓
6. Execute SQL and show results
   ↓
7. Save learning (original → clarified → SQL)
   ↓
8. Next time similar query comes → AI is smarter!
```

### Learning Accumulation

```
Day 1: User asks "supplier total" → AI asks clarification → User picks "Total amount per supplier"
       Saved as Learning #1

Day 2: User asks "supplier wise total" → AI finds Learning #1 (fuzzy match) → Suggests similar SQL
       Usage count++ → Pattern reinforced

Day 30: User asks "total by supplier" → AI instantly knows based on 20+ similar learnings
        → Generates accurate SQL without clarification
```

---

## 🛠️ Configuration & Customization

### Metadata Configuration (`metadata.json`)

**Add New Column**:
```json
{
  "QUALITY": {
    "description": "Fabric quality grade (A, B, C)",
    "type": "VARCHAR",
    "unit": null,
    "unit_full": null,
    "examples": ["A Grade", "B Grade", "C Grade"]
  }
}
```

**Add Business Term**:
```json
{
  "RFD": {
    "full_form": "Ready For Dyeing",
    "explanation": "Fabric prepared and ready to be dyed",
    "related_columns": ["QUALITY", "DEPARTMENT"]
  }
}
```

**Add Query Pattern**:
```json
{
  "pattern": "quality wise breakdown",
  "intent": "Group data by quality grade",
  "template": "SELECT QUALITY, COUNT(*), SUM(METERS) FROM GreigeData GROUP BY QUALITY"
}
```

### Clarity Patterns (`src/clarity.py`)

**Add Vague Pattern**:
```python
{
    "pattern": r"\b(quality|grade)\s+wise\b",
    "type": "grouping_request",
    "description": "Ambiguous grouping - needs metric clarification"
}
```

**Add Clarification Template**:
```python
CLARIFICATION_TEMPLATES["grouping_request"] = [
    "Show count and total meters grouped by {term}",
    "Show total amount (PKR) grouped by {term}",
    "List all distinct {term} values",
    "Show average rate for each {term}"
]
```

### Learning Categories (`src/learnings.py`)

**Add Category**:
```python
CATEGORY_KEYWORDS = {
    "quality_analysis": [
        "quality", "grade", "a grade", "b grade",
        "defect", "inspection", "standard"
    ]
}
```

---

## 📈 Monitoring & Analytics

### Check Learning Stats

In the chat interface, you'll see:
```
🧠 AI has learned 47 patterns from your team
```

### Export Learnings Report

```python
from src.learnings import export_learnings_report

report = export_learnings_report()
print(report)
```

**Output**:
```
=== DBAI Learning System Report ===
Generated: 2024-01-15 10:30:00

Total Learnings: 47
Total Clarifications: 89
Successful Patterns: 45

=== Categories ===
- supplier_queries: 12 learnings
- amount_calculations: 18 learnings
- inventory_checks: 8 learnings
...

=== Top Learnings (by usage) ===
1. "supplier total" → "Total amount per supplier" (23 uses)
2. "stock check" → "Current inventory in LBS" (19 uses)
...
```

### View Learning File

```bash
cat conversation_learnings.json | jq '.learnings[] | select(.usage_count > 10)'
```

Shows all learnings used more than 10 times.

---

## 🎓 Training Tips

### For End Users

1. **Be Specific**: Instead of "total", say "total amount in PKR for last month"
2. **Use Options**: When AI asks clarification, pick the closest option
3. **Learn from Suggestions**: AI's clarifications teach you what it can do
4. **Provide Feedback**: Correct answers help AI learn faster

### For Administrators

1. **Review Learnings Weekly**: Check `conversation_learnings.json` for patterns
2. **Update Metadata**: Add new terms, columns, patterns as business evolves
3. **Monitor Clarity Scores**: If many queries score < 50, add more metadata
4. **Categorize Manually**: Move important learnings to metadata for faster access

---

## 🔧 Troubleshooting

### AI Asks Too Many Clarifications

**Solution**: Lower clarity threshold
```python
# In src/ui.py, change:
if needs_clarification(clarity_score, threshold=70):
# To:
if needs_clarification(clarity_score, threshold=50):
```

### AI Doesn't Learn From Interactions

**Check**:
1. `conversation_learnings.json` file exists and is writable
2. Learning save function is called after successful queries
3. No JSON syntax errors in learnings file

**Test**:
```python
from src.learnings import save_learning, get_learning_stats

save_learning("test query", "clarified test", "SELECT 1", "positive")
print(get_learning_stats())  # Should show total: 1
```

### Duplicate Learnings

**The system auto-deduplicates** using 85% similarity threshold. If you see duplicates:
- Increase threshold in `src/learnings.py`:
```python
if similarity > 0.85:  # Change to 0.90 for stricter matching
```

### SQL Generation Not Using Learnings

**Check** that `src/llm.py` calls:
```python
relevant_learnings = get_relevant_learnings(query, limit=5)
enhanced_prompt = build_enhanced_prompt(metadata, relevant_learnings)
```

---

## 📚 Advanced Usage

### Custom Training Examples

Manually add high-value learnings:

```python
from src.learnings import save_learning

# Add common query pattern
save_learning(
    original_query="monthly report",
    clarified_query="Show monthly totals for amount (PKR) and LBS for the last 3 months grouped by supplier",
    sql="""
        SELECT 
            DATEPART(MONTH, DATE) as Month,
            SUPPLIER,
            SUM(AMOUNT) as Total_PKR,
            SUM(LBS) as Total_LBS
        FROM YarnData
        WHERE DATE >= DATEADD(MONTH, -3, GETDATE())
        GROUP BY DATEPART(MONTH, DATE), SUPPLIER
        ORDER BY Month DESC, Total_PKR DESC
    """,
    feedback="positive",
    category="time_based_queries"
)
```

### Bulk Import Learnings

```python
import json
from src.learnings import save_learning

# Load from CSV or another system
learnings_to_import = [
    {"original": "q1", "clarified": "c1", "sql": "s1"},
    {"original": "q2", "clarified": "c2", "sql": "s2"},
]

for learning in learnings_to_import:
    save_learning(
        learning["original"],
        learning["clarified"],
        learning["sql"],
        "positive"
    )
```

---

## 🚀 What Makes This System "Amazing"

1. **Zero Configuration Required**: Works out of the box with your existing data
2. **Business Context Aware**: Understands Pakistani textile industry terms
3. **Self-Improving**: Gets smarter with every interaction
4. **Non-Invasive**: Preserves original v2 UI, just adds intelligence
5. **Production Ready**: Error handling, logging, fuzzy matching
6. **Elegant Code**: Clean separation of concerns, well-documented
7. **Real-Time Learning**: No training delays or batch processes
8. **Team Intelligence**: Everyone benefits from each other's clarifications

---

## 📝 File Structure Summary

```
DBAI/
├── metadata.json                    # Business context & column definitions
├── conversation_learnings.json      # Learned patterns (auto-generated)
├── TRAINING_GUIDE.md               # This file
└── src/
    ├── clarity.py                   # Query vagueness detection
    ├── learnings.py                 # Learning management system
    ├── llm.py                       # Enhanced prompt building
    ├── database.py                  # Metadata load/save functions
    └── ui.py                        # Clarity integration in chat
```

---

## 💡 Next Steps

1. **Commit & Push**: `git push origin copilot/implement-interactive-features`
2. **Pull on Windows Laptop**: `git pull`
3. **Test with Real Queries**: Try vague queries like "supplier total"
4. **Monitor Learning Growth**: Check `conversation_learnings.json` after 1 week
5. **Customize Metadata**: Add company-specific terms and patterns
6. **Share with Team**: Train users on how to use clarifications effectively

---

**Built with ❤️ for Pakistani Textile Industry**

*Questions? Check the code comments or review the examples above.*
