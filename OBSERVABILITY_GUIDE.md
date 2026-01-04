# 🔬 Observability System Guide

## Overview

The DBAI Observability System captures complete application intelligence to help Copilot understand exactly what's happening in your sessions - not just errors, but successful queries, performance patterns, UI interactions, and more.

## 🎯 Three-Tier Architecture

### **Tier 1: Essential Metrics** (Always On by Default) ✅

**What it captures:**
- ✅ Every user query
- ✅ Success/failure status
- ✅ Response times
- ✅ Rows returned
- ✅ Errors with context

**Why always on:**
- Minimal overhead (~10ms per query)
- Essential for troubleshooting
- Helps Copilot understand your usage patterns
- Small file size (~2KB per query)

**File:** `logs/latest_session.json`

---

### **Tier 2: Developer Mode** (Enable When Debugging) 🔧

**What it captures:**
- Full LLM prompts sent to API
- Complete LLM responses
- Reasoning chain (which learnings/rules applied)
- Sample data (first 3 rows)
- Detailed performance breakdown
- Clarity analysis results

**When to enable:**
- ❌ Queries giving wrong results
- ❌ Performance issues (slow responses)
- ❌ Investigating why AI made certain decisions
- ✅ Training the AI and want to see impact
- ✅ Copilot asks for more details

**How to enable:**
Settings → Developer Tools → Toggle "Developer Mode"

**Overhead:** ~50-100ms per query, ~10KB per query

---

### **Tier 3: On-Demand Export** (Manual Trigger) 📤

**What it does:**
- Packages complete session data
- Generates summary statistics
- Creates recommendations
- Exports formatted report for Copilot

**When to use:**
- 💬 Asking Copilot for help
- 🐛 Complex bug that needs full context
- 📊 Analyzing session patterns
- 🎓 Sharing training progress

**How to use:**
Diagnostics Tab → "Export Session for Copilot"

**Output:** `logs/sessions/copilot_report_YYYYMMDD_HHMMSS.json`

---

## 🎛️ Control Panel Settings

### Recommended Defaults ⭐

```
✅ Tier 1: Essential Metrics         [Always ON]
❌ Tier 2: Developer Mode             [OFF until needed]
❌ Capture Full LLM Prompts           [OFF - very detailed]
✅ Capture Reasoning Chain            [ON - useful for training]
❌ Capture Sample Data                [OFF - privacy concern]
```

### When to Toggle Settings

#### Enable "Developer Mode" When:
1. **Wrong Results**
   - Query returns unexpected data
   - Column names not matching expectations
   - Units not showing correctly

2. **Performance Issues**
   - Responses taking > 5 seconds
   - Want to see time breakdown (LLM vs DB vs processing)

3. **Training Impact**
   - Added training rules, want to verify they're working
   - Testing different prompts/instructions

#### Enable "Capture Full LLM Prompts" When:
- Copilot specifically asks: "What prompt was sent to the LLM?"
- Investigating why LLM generated specific SQL
- Debugging metadata/learning injection

#### Enable "Capture Sample Data" When:
- Results look correct in count but data seems wrong
- Need to verify actual values returned
- ⚠️ **WARNING**: Contains real data from your database

---

## 📂 File Structure

```
logs/
├── diagnostics.log              # Traditional log file
├── latest_session.json          # Current session (auto-updated)
├── observability_config.json    # Your settings
└── sessions/
    ├── session_20260104_094626.json
    ├── session_20260104_101530.json
    └── copilot_report_20260104_094626.json  # Exported reports
```

---

## 🤖 How Copilot Uses This Data

### Automatic Context Loading
When you ask for help, Copilot automatically reads:
1. `latest_session.json` - Your current session
2. Recent timeline - What you've been doing
3. Error patterns - What's failing

### What Copilot Can See

**With Tier 1 (Always On):**
```
✅ "User asked 15 queries, 3 failed"
✅ "Average response time: 2.1s"
✅ "Last error: KeyError at line 158"
❌ Can't see: Why specific SQL was generated
❌ Can't see: What LLM was thinking
```

**With Tier 2 (Developer Mode):**
```
✅ Everything from Tier 1
✅ "LLM generated AS 'TotalYarnWeight' which was auto-corrected"
✅ "Applied 3 learnings and 1 training rule"
✅ "Spent 1.8s on LLM, 45ms on database"
✅ "Returned sample: [[22371100]]"
```

**With Tier 3 (Export):**
```
✅ Everything from Tier 1 + 2
✅ Complete session package
✅ Performance trends over time
✅ Training evolution
✅ Automated recommendations
```

---

## 💡 Copilot's Recommendations

### For Normal Use (Day-to-Day):
```
Settings:
- Tier 1: ON
- Tier 2: OFF
- Capture Reasoning Chain: ON  (helps understand training impact)
```
**Why:** Minimal overhead, good context for Copilot, privacy-safe

### For Debugging/Development:
```
Settings:
- Tier 1: ON
- Tier 2: ON
- Capture Full LLM Prompts: ON
- Capture Sample Data: OFF (unless Copilot asks)
```
**Why:** Maximum insight into what's happening

### For Performance Analysis:
```
Settings:
- Tier 1: ON
- Tier 2: ON
- Focus on: Performance metrics in session summary
```
**Why:** Detailed timing breakdown

---

## 🚀 Workflow Examples

### Example 1: "AI giving wrong answers"

1. ✅ Enable Developer Mode
2. ✅ Ask problematic query again
3. ✅ Go to Diagnostics → "Export Session for Copilot"
4. ✅ Commit: `git add logs/latest_session.json && git commit -m "Session with wrong answer issue"`
5. ✅ Ask Copilot: "Check latest_session.json - query 'total yarn' is giving wrong result"

**Copilot will see:**
- Your exact question
- SQL generated
- What corrections were applied
- Which learnings/rules were used
- Actual results returned

### Example 2: "App is slow"

1. ✅ Enable Developer Mode
2. ✅ Run several queries
3. ✅ Check session summary (shows timing breakdown)
4. ✅ Ask Copilot: "Performance analysis needed - check latest_session.json"

**Copilot will see:**
- Total time vs LLM time vs DB time
- Which queries are slowest
- Performance patterns

### Example 3: "Training not working"

1. ✅ Enable "Capture Reasoning Chain"
2. ✅ Add training rule
3. ✅ Test query that should use the rule
4. ✅ Export session
5. ✅ Ask Copilot: "Is my training rule being applied?"

**Copilot will see:**
- What rules are active
- Which rules were applied to each query
- Training events timeline

---

## 📊 Understanding the Session File

### Key Sections in `latest_session.json`:

```json
{
  "session_id": "20260104_094626",        // Unique session identifier
  "total_queries": 15,                    // How many questions asked
  "total_errors": 2,                      // How many failed
  "total_successes": 13,                  // How many worked
  
  "current_state": {                      // App configuration
    "provider": "openai",
    "model": "gpt-4o-mini",
    "database_connected": true
  },
  
  "last_query": {                         // Most recent query details
    "timestamp": "2026-01-04T09:47:04Z",
    "user_question": "Total yarn weight in LBS",
    "success": true,
    "execution_time_ms": 2100,
    "rows_returned": 1
  },
  
  "session_timeline": [                   // Chronological event list
    {"type": "query", "timestamp": "...", "question": "...", "success": true},
    {"type": "training", "timestamp": "...", "event_type": "rule_added"},
    {"type": "error", "timestamp": "...", "error_type": "KeyError"}
  ]
}
```

---

## 🔒 Privacy & Data Safety

### What Gets Logged:
- ✅ Your questions (stored locally only)
- ✅ Generated SQL queries
- ✅ Error messages
- ✅ Performance metrics
- ⚠️ Sample data (only if "Capture Sample Data" enabled)

### What NEVER Gets Logged:
- ❌ API keys
- ❌ Database passwords
- ❌ Full database dumps

### Sharing with Copilot:
- You control what gets committed to GitHub
- `latest_session.json` is in `.gitignore` by default
- Only commit when you explicitly want Copilot to see it

---

## 🛠️ Troubleshooting

### "Session file getting too large"
- Disable "Capture Sample Data"
- Disable "Capture Full LLM Prompts"
- Files auto-rotate after 50 queries

### "Want to start fresh"
- Restart the app (creates new session)
- Or: Delete `logs/latest_session.json`

### "Copilot says it can't see my session"
- Make sure you committed the file: `git add logs/latest_session.json`
- Or paste the file contents directly in your message

---

## 📞 Getting Help from Copilot

### Quick Reference:

**Good:** "Check latest_session.json - why is query X slow?"
**Better:** "Enable developer mode, export session, check report - query X slow"
**Best:** [Export session] + "Full report in logs/sessions/copilot_report_*.json"

---

## 🎯 Summary

**For 90% of use cases:**
- Keep Tier 1 ON
- Keep Tier 2 OFF
- Enable Tier 2 only when debugging
- Export (Tier 3) when asking Copilot for help

**This gives:**
- Clean logs
- Fast performance
- Complete context when needed
- Privacy-safe defaults

**When in doubt:** Ask Copilot "Should I enable developer mode for this issue?"
