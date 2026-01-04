# ⚡ Quick Training Guide

## What is Quick Training?

**Quick Training** lets you teach the AI in plain English - no technical knowledge needed! Just write what you mean, and the AI follows your rules immediately.

---

## How to Use

### Step 1: Navigate to Quick Training
**🎓 Train → ⚡ Quick Training** (first tab)

### Step 2: Write Your Rule
In the text box, write exactly how you want the AI to interpret queries.

### Step 3: Click "Add Training Rule"
Your rule is saved and applies to the very next query!

---

## Real Examples

### Example 1: Specifying Units

**Problem**: You ask "total arrival yarn" and AI returns amount in PKR, but you wanted LBS.

**Solution**: Write this training rule:
```
When I ask "total arrival yarn", return total LBS of yarn received, NOT the amount in PKR
```

**Result**: Next time you ask "total arrival yarn", AI will return LBS!

---

### Example 2: Default Metrics

**Problem**: "greige rcvd" could mean meters, count, or amount.

**Solution**: Write this:
```
When I ask "total greige rcvd", always return the meters of greige fabric received (format: 1234556 Meters)
```

**Result**: AI now knows your preferred format!

---

### Example 3: Stock Queries

**Problem**: "stock check" is vague - which table? Which metric?

**Solution**:
```
Stock check should show current inventory from YarnData in both LBS and bags, grouped by type
```

**Result**: AI generates the exact query you want!

---

### Example 4: Supplier Queries

**Problem**: "Ahmed total" could mean total amount, total LBS, or total invoices.

**Solution**:
```
When I mention a supplier name with "total", I want total amount in PKR and total LBS, both shown together
```

**Result**: You get both metrics every time!

---

## Writing Good Training Rules

### ✅ Good Rules (Specific)
```
✓ "When I say 'monthly report', show supplier-wise breakdown of amount (PKR) and LBS for current month"
✓ "Arrival data should always include supplier, date, LBS, and amount - sorted by date DESC"
✓ "Quality check means show defect count by department from GreigeData"
```

### ❌ Avoid (Too Vague)
```
✗ "Make queries better"
✗ "Show everything"
✗ "Be smart about it"
```

---

## Tips for Success

1. **Be Specific About Units**
   - Mention PKR, LBS, meters, bags, etc.
   - Specify the exact format you want

2. **Name the Table (if you know it)**
   - "from YarnData" or "from GreigeData"
   - Helps AI target the right data

3. **Include Format Preferences**
   - "Show as: 1,234,556 Meters"
   - "Group by supplier"
   - "Sort by date DESC"

4. **Handle Edge Cases**
   - Think about what could be ambiguous
   - Write rules for YOUR specific workflow

5. **One Rule Per Instruction**
   - Don't combine multiple rules
   - Keep each rule focused

---

## Viewing Your Rules

All active rules appear below the input box in the **Active Training Rules** section.

You'll see:
- Rule text
- When it was added
- Total number of rules

---

## How It Works Behind the Scenes

1. You write a rule
2. System saves it to `quick_training_rules.json`
3. Every query includes your rules in the AI prompt
4. AI follows your rules when generating SQL
5. You get exactly what you asked for!

---

## Training Stats Display

After each query, you'll see:
```
🧠 Knowledge: 15 learned patterns · 8 training rules
```

This shows:
- **Learned patterns**: From clarification interactions
- **Training rules**: Your custom instructions

---

## Examples from Pakistani Textile Business

### For Yarn Tracking
```
"Total yarn arrival" means sum of LBS received, grouped by supplier, for last 30 days
```

```
When checking yarn inventory, show TYPE, COUNT, total LBS, and total BAGS currently in stock
```

### For Greige Fabric
```
"Greige summary" should show total METERS and AMOUNT (PKR) grouped by QUALITY grade
```

```
Department-wise greige report means METERS and AMOUNT by DEPARTMENT from GreigeData
```

### For Suppliers
```
When I ask about supplier performance, show total AMOUNT (PKR), total LBS or METERS, and invoice count
```

```
Top suppliers means ordered by total AMOUNT in PKR descending, show top 10
```

### For Time-Based Queries
```
"This month" means current calendar month from DATE column
```

```
Monthly trend means group by MONTH and YEAR, show last 6 months
```

---

## Immediate Reflection

**The beauty of this system**: Your training rules apply **instantly**!

```
Step 1: Write rule at 10:00 AM
        "total arrival = LBS received"

Step 2: Ask query at 10:01 AM
        "total arrival yarn"

Step 3: AI uses your rule immediately!
        Shows: 12,345 LBS (not amount in PKR)
```

No waiting, no retraining, no delays!

---

## Combine with Other Features

Quick Training works alongside:
- **Clarity detection**: When AI asks clarification, your rules help
- **Learning patterns**: From team interactions
- **Column training**: Metadata you've added
- **System instructions**: General database context

All these work together to make the AI smarter!

---

## Troubleshooting

### Rule Not Working?

1. **Check rule wording**: Be very specific
2. **Check query wording**: Must match your rule
3. **View active rules**: Make sure it was saved
4. **Try exact phrasing**: Use the same words from your rule

### Want to Update a Rule?

Currently you need to:
1. Note the rule you want to change
2. Think of better wording
3. Add a new improved rule
4. (Old rules stay active but new one takes priority)

---

## Best Practices

### Daily Usage
- Add rules as you discover edge cases
- Review active rules weekly
- Remove outdated rules (if feature added)

### Team Training
- Share successful rules with team
- Document common queries and their rules
- Build a knowledge base over time

### Maintenance
- Keep rules simple and clear
- Update when business logic changes
- Archive old rules that no longer apply

---

## Success Metrics

**Week 1**: Add 5-10 rules for common queries
**Month 1**: 20-30 rules covering 80% of your queries
**Month 3**: Rarely need clarifications, AI "just knows"

---

## Real User Experience

**Before Quick Training**:
```
You: "total arrival"
AI: Shows amount in PKR
You: "No, I meant LBS"
AI: Regenerates query
```

**After Quick Training**:
```
[Rule: "arrival = LBS received"]

You: "total arrival"
AI: Shows LBS immediately ✅
```

**Time saved**: 2-3 interactions per query!

---

## Questions?

- Check [TRAINING_GUIDE.md](TRAINING_GUIDE.md) for comprehensive training info
- Check [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for query examples
- View your active rules anytime in the Quick Training tab

---

**💡 Pro Tip**: Start with the queries you ask most often. Write rules for those first, and watch your productivity soar! 🚀
