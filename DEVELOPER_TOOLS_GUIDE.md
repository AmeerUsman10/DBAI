# Developer Tools Tab - Quick Start Guide

## 🎯 What It Does
The Developer Tools tab gives you **complete visibility** into how your AI database assistant works. Every query, every decision, every piece of data flows through this tracking system.

## 📊 Session Summary
The left panel shows your current session stats:
- **Session ID**: Unique identifier for this run
- **Duration**: How long you've been using the app
- **Total Queries**: Number of questions asked
- **Success Rate**: How many queries worked correctly
- **Avg Response Time**: Speed metrics
- **Training Events**: New rules/metadata you've added
- **Errors**: Problems encountered

### 💡 Smart Recommendations
The system automatically suggests improvements:
- Low success rate → Enable Developer Mode to see why
- Slow queries → Check execution times in logs
- Frequent errors → Export session for deeper analysis

## ⚙️ Configuration Controls (Right Panel)

### Tier 1: Essential Metrics (Always On) ✅
- User questions
- SQL queries generated
- Success/failure status
- Query execution time
- Basic error tracking

**Overhead**: ~10ms per query  
**Privacy**: No sensitive data captured

### Tier 2: Developer Mode 🔧
**When to Enable:**
- ❌ Getting wrong results
- 🐌 Queries are slow
- 🤔 Need to understand AI reasoning
- 🐛 Debugging complex issues

**What it captures:**
- Full LLM prompts and responses
- Detailed reasoning chain
- Sample data (if enabled separately)
- Complete error tracebacks

**Overhead**: ~100ms per query  
**Privacy**: Contains more detail, but sample data OFF by default

### Individual Flags

#### 📝 Capture Full LLM Prompts
Shows exactly what's sent to GPT-4/Groq and what comes back.

**Enable when:**
- LLM generating wrong SQL
- Need to debug prompt engineering
- Copilot asks for prompt details

#### 🧠 Capture Reasoning Chain (Recommended ✅)
Tracks how the AI thinks through your query:
1. Clarity analysis
2. Metadata lookup
3. SQL generation logic
4. Result formatting

**Enable when:**
- Want to understand AI decisions
- Training the system
- General debugging

**Keep ON by default** - minimal overhead, high value.

#### 📊 Capture Sample Data (Privacy Flag ⚠️)
Records first 3 rows of query results.

**Enable when:**
- Debugging data formatting issues
- Copilot needs to see actual results
- Data type problems

**⚠️ Privacy Note**: This captures real data from your database. Only enable when:
- Data is not sensitive
- Debugging requires seeing actual values
- You'll delete the logs after troubleshooting

## 📤 Export for Copilot

### When to Export:
1. **Complex Bugs**: Multiple failed queries, unclear errors
2. **Performance Issues**: Slow responses, timeout errors
3. **AI Behavior Problems**: Wrong SQL, misunderstood queries
4. **Getting Help**: When asking Copilot to investigate

### How It Works:
1. Click **"📤 Export Session for Copilot"**
2. Report saved to: `logs/copilot_report_YYYYMMDD_HHMMSS.json`
3. File path shown in UI
4. Git add the file: `git add logs/copilot_report_*.json`
5. Ask Copilot: "Check my latest session report - why are queries failing?"

### What's in the Export:
- Complete session timeline (all queries)
- Success/failure patterns
- Error frequencies
- Performance metrics
- Auto-generated recommendations
- Current configuration settings
- Anonymized (no passwords, sensitive data)

## 🔄 Workflow Examples

### Normal Usage (Default Settings)
```
✅ Tier 1 ON
❌ Tier 2 OFF
✅ Reasoning Chain ON
❌ Sample Data OFF
```
**What you get**: Clean tracking, fast performance, privacy-safe

### Debugging Wrong Results
```
✅ Tier 1 ON
✅ Tier 2 ON
✅ Full LLM Prompts ON
✅ Reasoning Chain ON
✅ Sample Data ON (if needed)
```
**What you get**: Complete visibility into AI decisions

### Performance Investigation
```
✅ Tier 1 ON
✅ Tier 2 ON
❌ LLM Prompts OFF (not needed)
✅ Reasoning Chain ON
❌ Sample Data OFF
```
**What you get**: Timing breakdowns without extra overhead

### Privacy-Conscious Troubleshooting
```
✅ Tier 1 ON
✅ Tier 2 ON
✅ Full LLM Prompts ON
✅ Reasoning Chain ON
❌ Sample Data OFF
```
**What you get**: Full debugging without exposing real data

## 📝 Log File Locations

### Latest Session (Auto-Updated)
`logs/latest_session.json`
- Always current
- Overwrites on each run
- Good for quick checks

### Archived Sessions
`logs/sessions/session_YYYYMMDD_HHMMSS.json`
- Saved on app exit
- Historical record
- Compare across sessions

### Copilot Reports
`logs/copilot_report_YYYYMMDD_HHMMSS.json`
- On-demand export
- Formatted for AI analysis
- Includes recommendations

### Configuration
`logs/observability_config.json`
- Your tier settings
- Persists across runs
- Edit manually if needed

## 💬 Ask Copilot for Help

### Example Prompts:
```
"Check my latest session - why is the success rate only 60%?"

"Export shows slow queries - what's the bottleneck?"

"I enabled Developer Mode - can you analyze the reasoning chain?"

"My session report is ready - diagnose the LLM prompt issues"
```

### What Copilot Can Do:
- Analyze session patterns
- Identify prompt problems
- Suggest training improvements
- Debug clarity analysis
- Optimize query performance
- Explain AI reasoning

## 🎓 Best Practices

1. **Start with defaults** (Tier 1 only)
2. **Enable Tier 2 only when debugging**
3. **Turn OFF Tier 2 when done** (saves overhead)
4. **Export before asking for help**
5. **Check recommendations** after each session
6. **Keep reasoning chain ON** (minimal cost, high value)
7. **Be careful with sample data** (privacy)

## 🔧 Troubleshooting

### Session summary not loading
1. Check `logs/latest_session.json` exists
2. Click "🔄 Refresh Summary"
3. If still broken, restart app

### Export fails
1. Check `logs/` directory exists and is writable
2. Check disk space
3. Try refreshing session first

### Configuration not saving
1. Check `logs/observability_config.json` permissions
2. Restart app to reload
3. Check browser console for errors

### Performance impact from tracking
1. Disable Tier 2 if not debugging
2. Turn OFF sample data capture
3. Reduce max_queries_in_memory (default: 50)

## 📚 Related Documentation
- [OBSERVABILITY_GUIDE.md](OBSERVABILITY_GUIDE.md) - Complete technical documentation
- [README.md](README.md) - Main application guide
- Session tracker source: [src/session_tracker.py](src/session_tracker.py)

---

**Questions?** Ask Copilot - this entire system was designed to make AI troubleshooting seamless! 🤖
