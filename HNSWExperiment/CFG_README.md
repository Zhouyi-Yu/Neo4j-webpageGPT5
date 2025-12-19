# Control Flow Graph (CFG) - Neo4j Research Q&A System

## 📊 Overview

This directory contains a complete Control Flow Graph analysis of the Neo4j Research Q&A System. The CFG visualizes the entire question-answering pipeline from user input to final response.

## 📈 System Statistics

- **Total Nodes**: 33
- **Total Edges**: 42
- **Decision Points**: 10
- **LLM Calls**: 7
- **Database Operations**: 2
- **Cyclomatic Complexity**: 11
- **Max Path Length**: 23

## 🎯 Key System Components

### 1. **Intent Classification** (Entry Point)
- Classifies user questions using LLM
- Normalizes department names (e.g., "Engineering" → specific departments)

### 2. **Author Resolution**
- Exact name matching (case-insensitive)
- Fuzzy search fallback using Neo4j fulltext index
- Candidate disambiguation for multiple matches

### 3. **Branching Logic**
Two main execution paths:

#### **Branch A: Template-Driven Flow**
- For structured queries (author publications, collaborations, etc.)
- Generates Cypher queries via LLM
- Executes against Neo4j graph database
- Optional semantic search for topic-based queries
- Synthesizes answer from structured data

#### **Branch B: Semantic/Fallback Flow**
- For open-ended questions
- Vector similarity search on publications
- Author discovery from semantic hits
- LLM synthesis from unstructured data

## 📁 Generated Files

### 1. **cfg_generator.py**
Python script using NetworkX to generate the CFG and export to multiple formats.

**Usage:**
```bash
python cfg_generator.py
```

### 2. **visualize_cfg.html**
Interactive web-based visualization using Cytoscape.js.

**Usage:**
```bash
# Open in browser
open visualize_cfg.html
```

**Features:**
- Interactive node/edge selection
- Reset layout
- Fit to screen
- Export to PNG
- Toggle labels
- Real-time statistics

### 3. **system_cfg.graphml**
GraphML format for professional graph editors.

**Recommended Tools:**
- **yEd Graph Editor** (Desktop): https://www.yworks.com/products/yed
- **Gephi** (Desktop): https://gephi.org/

### 4. **system_cfg.json**
JSON format for web frameworks and custom visualizations.

**Recommended Tools:**
- **D3.js**: https://d3js.org/
- **Observable**: https://observablehq.com/
- **Cytoscape.js**: https://js.cytoscape.org/

### 5. **system_cfg.mmd**
Mermaid diagram format for markdown and documentation.

**Recommended Tools:**
- **Mermaid Live Editor**: https://mermaid.live/
- **GitHub/GitLab** (native support in markdown)
- **VS Code** (with Mermaid extension)

## 🎨 Visualization Recommendations

### Best for Quick Viewing
1. **Mermaid Live Editor** ⭐ RECOMMENDED
   - Open `system_cfg.mmd` at https://mermaid.live/
   - Instant visualization, no installation
   - Export to PNG/SVG
   - Shareable links

2. **visualize_cfg.html** ⭐ RECOMMENDED
   - Open directly in browser
   - Interactive controls
   - Built-in statistics
   - Export to PNG

### Best for Professional Diagrams
1. **yEd Graph Editor**
   - Import `system_cfg.graphml`
   - Auto-layout algorithms (hierarchical, organic, circular)
   - Export to high-quality PNG/SVG/PDF
   - Professional styling options

### Best for Analysis
1. **Gephi**
   - Import `system_cfg.graphml`
   - Network analysis metrics
   - Community detection
   - Advanced filtering

### Best for Web Integration
1. **Cytoscape.js**
   - Load `system_cfg.json`
   - Embed in web applications
   - Custom interactions
   - Responsive design

## 🔍 Understanding the CFG

### Node Types (Color-Coded)

- 🟢 **Green**: Entry/Exit points
- 🔵 **Blue**: Process nodes (LLM calls, data processing)
- 🟠 **Orange**: Decision points (conditional branching)
- 🟣 **Purple**: Database operations (Neo4j queries)
- 🔴 **Red**: Output/Return nodes

### Critical Decision Points

1. **Selected User ID Provided?**
   - Bypasses author resolution if user selected from candidates

2. **Author Field Present?**
   - Triggers name extraction if not found by classifier

3. **Multiple Candidates?**
   - Returns candidate list for user disambiguation

4. **Is Template Intent?**
   - Determines execution path (structured vs. semantic)

5. **Is Topic Intent?**
   - Triggers semantic search for topic-based queries

6. **No DB Rows but Semantic Hits?**
   - Activates recursive semantic answer refinement

## 🚀 Quick Start

### Option 1: Interactive HTML (Fastest)
```bash
open visualize_cfg.html
```

### Option 2: Mermaid Live Editor
1. Open https://mermaid.live/
2. Copy contents of `system_cfg.mmd`
3. Paste into editor
4. View and export

### Option 3: yEd (Best Quality)
1. Download yEd: https://www.yworks.com/products/yed
2. Open `system_cfg.graphml`
3. Apply layout: Layout → Hierarchical
4. Export: File → Export → PNG/SVG

## 🛠️ Customization

### Modify the CFG
Edit `cfg_generator.py` to:
- Add new nodes/edges
- Change colors and labels
- Adjust layout parameters
- Add custom statistics

### Regenerate Files
```bash
python cfg_generator.py
```

## 📚 Additional Resources

### Understanding Control Flow Graphs
- [Wikipedia: Control-flow graph](https://en.wikipedia.org/wiki/Control-flow_graph)
- [Cyclomatic Complexity](https://en.wikipedia.org/wiki/Cyclomatic_complexity)

### Visualization Tools
- [NetworkX Documentation](https://networkx.org/)
- [Cytoscape.js Documentation](https://js.cytoscape.org/)
- [Mermaid Documentation](https://mermaid.js.org/)

## 🐛 Troubleshooting

### Missing pydot (DOT export)
If you need DOT format:
```bash
pip install pydot
python cfg_generator.py
```

### HTML Visualization Not Loading
- Ensure you have internet connection (loads Cytoscape.js from CDN)
- Try a different browser
- Check browser console for errors

### GraphML Won't Open in yEd
- Ensure you have the latest version of yEd
- Try importing instead of opening
- Check file permissions

## 📝 License

This CFG analysis is part of the Neo4j Research Q&A System project.

---

**Generated**: 2025-12-18  
**System Version**: HNSWExperiment  
**Analysis Tool**: NetworkX + Custom CFG Generator
