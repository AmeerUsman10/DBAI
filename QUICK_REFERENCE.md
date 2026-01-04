# 🎯 DBAI Quick Reference Card
## Training the AI

### Interactive Column Training
Navigate to **🎓 Train → 📊 Column Training** tab:

1. Click **📥 Load Database Schema**
2. Select a table from dropdown (e.g., YarnData)
3. Select a column (e.g., SUPPLIER)
4. Fill in:
   - **Description**: "Supplier name for yarn/fabric orders"
   - **Unit**: (leave empty if not applicable)
   - **Examples**: "Ahmed Textile, XYZ Mills, ABC Fabrics"
5. Click **💾 Save Training**

Your training is instantly saved to [metadata.json](metadata.json) and the AI uses it immediately!

---
## Common User Queries

### ✅ Good (Specific)
- "Show total amount in PKR for supplier 'Ahmed Textile' in last 30 days"
- "How many LBS of yarn type 'Cotton' do we have in inventory?"
- "List all greige fabric suppliers with total meters ordered"
- "What is the average rate per LBS for count 30/1 yarn?"

### ⚠️ Vague (Needs Clarification)
- "supplier total" → AI will ask: amount? LBS? bags? count?
- "stock" → AI will ask: which table? which metric? time period?
- "Ahmed" → AI will ask: amount spent? quantities ordered? invoices?
- "monthly" → AI will ask: which month? which metric? which table?

---

## Business Terminology

| Term | Full Form | Meaning |
|------|-----------|---------|
| **PKR** | Pakistani Rupee | Currency for amounts |
| **LBS** | Pounds | Weight unit for yarn/fabric |
| **Greige** | - | Unfinished fabric (before dyeing) |
| **CT** | Carton | Packaging unit |
| **PC** | Pieces | Count unit |
| **Count** | - | Yarn thickness (e.g., 30/1, 20/1) |

---

## Quick Commands

### Check AI Learning Stats
Look for message at bottom of chat:
```
🧠 AI has learned 47 patterns from your team
```

### View Token Usage (OpenAI only)
```
🔹 Tokens: 1,234 · Session: 45,678
```

### Respond to Clarification
When AI shows numbered options:
```
1. Total amount in PKR per supplier
2. Total LBS per supplier
3. Total bags per supplier
4. List all supplier names
```
Just type: `1` or `2` or `3` or `4`

---

## Example Query Flows

### Flow 1: Supplier Analysis
```
You: supplier wise total
AI: Could you clarify which of these you're looking for?
    1. Total amount in PKR per supplier
    2. Total LBS ordered per supplier
    3. Total invoice count per supplier
    4. List all suppliers with contact info
You: 1
AI: [Shows table with suppliers and amounts]
✓ AI learns this pattern
```

### Flow 2: Inventory Check
```
You: stock for cotton yarn
AI: [Directly shows results - query was clear enough]
    Shows: COUNT, LBS, BAGS for cotton type yarn
```

### Flow 3: Time-Based Query
```
You: last month data
AI: Could you clarify which of these you're looking for?
    1. Total amount (PKR) for last month
    2. Total LBS received last month
    3. All invoices from last month
    4. Supplier-wise breakdown for last month
You: 4
AI: [Shows supplier-wise breakdown]
✓ AI learns "last month data" → supplier breakdown pattern
```

---

## Column Quick Reference

### YarnData Table
| Column | Type | Unit | Example |
|--------|------|------|---------|
| SUPPLIER | VARCHAR | - | "Ahmed Textile" |
| AMOUNT | DECIMAL | PKR | 150000.00 |
| LBS | DECIMAL | pounds | 2500.50 |
| BAGS | INT | bags | 50 |
| RATE | DECIMAL | PKR/LBS | 60.00 |
| DATE | DATE | - | 2024-01-15 |
| TYPE | VARCHAR | - | "Cotton", "Polyester" |
| COUNT | VARCHAR | - | "30/1", "20/1" |
| COLOR | VARCHAR | - | "White", "Ecru" |

### GreigeData Table
| Column | Type | Unit | Example |
|--------|------|------|---------|
| SUPPLIER | VARCHAR | - | "XYZ Fabrics" |
| AMOUNT | DECIMAL | PKR | 200000.00 |
| METERS | DECIMAL | meters | 5000.00 |
| INCHES | DECIMAL | inches | 58.5 |
| RATE | DECIMAL | PKR/meter | 40.00 |
| DATE | DATE | - | 2024-01-15 |
| QUALITY | VARCHAR | - | "A Grade" |
| CONSTRUCTION | VARCHAR | - | "58x48" |
| DEPARTMENT | VARCHAR | - | "Weaving" |

---

## Tips for Better Results

### 1. Include Units
❌ "show total rate"
✅ "show total amount in PKR"

### 2. Specify Table (if known)
❌ "supplier data"
✅ "supplier data from YarnData table"

### 3. Add Time Context
❌ "total amount"
✅ "total amount for last 3 months"

### 4. Use Exact Column Names (if known)
❌ "show suppliers and money"
✅ "show SUPPLIER and AMOUNT from YarnData"

### 5. Trust the AI's Suggestions
When AI asks for clarification, the options are based on:
- Your actual database schema
- Common query patterns
- Past successful queries from your team
- Pakistani textile business context

---

## Troubleshooting

### "No results found"
- Check spelling of supplier names
- Try partial names: "ahmed" instead of "Ahmed Textile Mills Pvt Ltd"
- Use LIKE patterns: "supplier LIKE '%ahmed%'"

### "Database not available"
- Check database connection in Settings tab
- Verify SQL Server is running
- Test connection button should show ✅

### "Too many clarifications"
- Be more specific in your query
- Use column names when you know them
- Include units (PKR, LBS, meters)

### "Query too slow"
- Add date filters: "last 30 days" instead of "all time"
- Limit results: "top 10 suppliers"
- Use specific filters: "supplier='Ahmed'" instead of "all suppliers"

---

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Submit query | `Enter` |
| New line in query | `Shift + Enter` |
| Clear chat | Click 🔄 Clear |

---

## Common Query Patterns

### Supplier Queries
```sql
-- All suppliers
"list all suppliers from YarnData"

-- Supplier totals
"total amount spent per supplier in last month"

-- Top suppliers
"top 10 suppliers by amount in PKR"

-- Specific supplier
"all orders from supplier 'Ahmed Textile'"
```

### Amount Calculations
```sql
-- Grand total
"total amount in PKR from YarnData for 2024"

-- Average
"average rate per LBS for cotton yarn"

-- Grouped sums
"total amount by supplier and type"
```

### Inventory Checks
```sql
-- Current stock
"total LBS and bags currently in YarnData"

-- By type
"inventory breakdown by yarn type"

-- Low stock
"suppliers with less than 100 LBS remaining"
```

### Time-Based Queries
```sql
-- Last period
"total amount for last 30 days"

-- Monthly trend
"monthly totals for last 6 months"

-- Specific date
"all invoices from January 2024"
```

### Department Analysis (GreigeData)
```sql
-- By department
"total meters by department"

-- Quality breakdown
"meters and amount by quality grade"

-- Department efficiency
"average rate by department for last month"
```

---

## Advanced Tips

### Use Aggregations
```
"show supplier, count of orders, total amount, average rate"
```

### Combine Conditions
```
"cotton yarn from Ahmed Textile in last 30 days with rate > 50 PKR"
```

### Request Sorting
```
"top 10 suppliers by total amount in descending order"
```

### Ask for Calculations
```
"what percentage of total amount does Ahmed Textile represent?"
```

---

**💡 Pro Tip**: The more you use the system, the smarter it gets. Your team's queries train the AI to better understand your specific business needs!

---

**📞 Need Help?**
- Check [TRAINING_GUIDE.md](TRAINING_GUIDE.md) for detailed documentation
- Review [metadata.json](metadata.json) for column definitions
- Examine [conversation_learnings.json](conversation_learnings.json) for learned patterns
