"""
CFG Generator for Neo4j Research Q&A System

This script generates a Control Flow Graph (CFG) for the backend.py system.
It uses networkx for graph creation and can export to various formats for visualization.
"""

import networkx as nx
import json
from typing import Dict, List, Tuple


def create_system_cfg() -> nx.DiGraph:
    """
    Create a detailed Control Flow Graph of the answer_question pipeline.
    
    Returns:
        nx.DiGraph: A directed graph representing the system's control flow
    """
    G = nx.DiGraph()
    
    # Define nodes with metadata
    nodes = {
        # Entry point
        "START": {"type": "entry", "label": "User Question Input", "color": "#4CAF50"},
        
        # Step 1: Intent Classification
        "classify_intent": {"type": "process", "label": "Classify Intent\n(LLM Call)", "color": "#2196F3"},
        "normalize_intent": {"type": "process", "label": "Normalize Intent\n(Expand Departments)", "color": "#2196F3"},
        
        # Step 2: Author Resolution
        "check_selected_user": {"type": "decision", "label": "Selected User ID\nProvided?", "color": "#FF9800"},
        "set_user_id": {"type": "process", "label": "Set authorUserId\nPromote to AUTHOR_MAIN", "color": "#2196F3"},
        
        "check_author_field": {"type": "decision", "label": "Author Field\nPresent?", "color": "#FF9800"},
        "extract_name": {"type": "process", "label": "Extract Name\n(LLM Call)", "color": "#2196F3"},
        
        "resolve_author": {"type": "process", "label": "Resolve Author\n(Exact + Fuzzy Search)", "color": "#2196F3"},
        "check_candidates": {"type": "decision", "label": "Multiple\nCandidates?", "color": "#FF9800"},
        "return_candidates": {"type": "output", "label": "Return Candidate List\nfor User Selection", "color": "#F44336"},
        
        "check_single_match": {"type": "decision", "label": "Single Match\nFound?", "color": "#FF9800"},
        "set_author_info": {"type": "process", "label": "Set Author Info\n& UserId", "color": "#2196F3"},
        "promote_intent": {"type": "decision", "label": "Intent is\nOPEN_QUESTION?", "color": "#FF9800"},
        "promote_to_author": {"type": "process", "label": "Promote to\nAUTHOR_PUBLICATIONS", "color": "#2196F3"},
        
        # Step 3: Branching Logic
        "check_template": {"type": "decision", "label": "Is Template Intent\n& Has Required Slots?", "color": "#FF9800"},
        
        # Branch A: Template-Driven Flow
        "generate_cypher": {"type": "process", "label": "Generate Cypher\n(LLM Call)", "color": "#2196F3"},
        "run_cypher": {"type": "process", "label": "Run Cypher Query\n(Neo4j)", "color": "#9C27B0"},
        
        "check_topic_intent": {"type": "decision", "label": "Is Topic\nIntent?", "color": "#FF9800"},
        "semantic_search_topic": {"type": "process", "label": "Semantic Search\nPublications (Vector)", "color": "#9C27B0"},
        
        "check_empty_results": {"type": "decision", "label": "DB Rows or\nSemantic Hits?", "color": "#FF9800"},
        "semantic_fallback": {"type": "process", "label": "Semantic Search UofA\n(Fallback)", "color": "#9C27B0"},
        
        "synthesize_answer": {"type": "process", "label": "Synthesize Answer\n(LLM Call)", "color": "#2196F3"},
        
        "check_second_pass": {"type": "decision", "label": "No DB Rows but\nSemantic Hits?", "color": "#FF9800"},
        "recursive_semantic": {"type": "process", "label": "Recursive Semantic\nAnswer (LLM)", "color": "#2196F3"},
        
        "return_template_result": {"type": "output", "label": "Return Template\nResult", "color": "#4CAF50"},
        
        # Branch B: Semantic/Fallback Flow
        "semantic_search_uofa": {"type": "process", "label": "Semantic Search UofA\n(Vector)", "color": "#9C27B0"},
        "check_semantic_hits": {"type": "decision", "label": "Semantic Hits\nFound?", "color": "#FF9800"},
        "return_no_results": {"type": "output", "label": "Return 'No Results'", "color": "#F44336"},
        
        "generate_author_cypher": {"type": "process", "label": "Generate Author\nCypher (LLM)", "color": "#2196F3"},
        "run_author_cypher": {"type": "process", "label": "Run Author Cypher\n(Neo4j)", "color": "#9C27B0"},
        "synthesize_final_author": {"type": "process", "label": "Synthesize Final\nAuthor Answer (LLM)", "color": "#2196F3"},
        "return_semantic_result": {"type": "output", "label": "Return Semantic\nResult", "color": "#4CAF50"},
        
        # End
        "END": {"type": "exit", "label": "Response to User", "color": "#4CAF50"},
    }
    
    # Add all nodes
    for node_id, attrs in nodes.items():
        G.add_node(node_id, **attrs)
    
    # Define edges (control flow)
    edges = [
        # Main flow
        ("START", "classify_intent"),
        ("classify_intent", "normalize_intent"),
        ("normalize_intent", "check_selected_user"),
        
        # Selected user path
        ("check_selected_user", "set_user_id", {"label": "Yes"}),
        ("set_user_id", "check_template"),
        
        # Author resolution path
        ("check_selected_user", "check_author_field", {"label": "No"}),
        ("check_author_field", "resolve_author", {"label": "Yes"}),
        ("check_author_field", "extract_name", {"label": "No"}),
        ("extract_name", "resolve_author"),
        
        ("resolve_author", "check_candidates"),
        ("check_candidates", "return_candidates", {"label": "Yes (>1)"}),
        ("return_candidates", "END"),
        
        ("check_candidates", "check_single_match", {"label": "No"}),
        ("check_single_match", "set_author_info", {"label": "Yes"}),
        ("set_author_info", "promote_intent"),
        ("promote_intent", "promote_to_author", {"label": "Yes"}),
        ("promote_to_author", "check_template"),
        ("promote_intent", "check_template", {"label": "No"}),
        
        ("check_single_match", "check_template", {"label": "No"}),
        
        # Template branch decision
        ("check_template", "generate_cypher", {"label": "Yes"}),
        ("generate_cypher", "run_cypher"),
        ("run_cypher", "check_topic_intent"),
        
        ("check_topic_intent", "semantic_search_topic", {"label": "Yes"}),
        ("semantic_search_topic", "check_empty_results"),
        ("check_topic_intent", "check_empty_results", {"label": "No"}),
        
        ("check_empty_results", "semantic_fallback", {"label": "No"}),
        ("semantic_fallback", "synthesize_answer"),
        ("check_empty_results", "synthesize_answer", {"label": "Yes"}),
        
        ("synthesize_answer", "check_second_pass"),
        ("check_second_pass", "recursive_semantic", {"label": "Yes"}),
        ("recursive_semantic", "return_template_result"),
        ("check_second_pass", "return_template_result", {"label": "No"}),
        ("return_template_result", "END"),
        
        # Semantic/Fallback branch
        ("check_template", "semantic_search_uofa", {"label": "No"}),
        ("semantic_search_uofa", "check_semantic_hits"),
        ("check_semantic_hits", "return_no_results", {"label": "No"}),
        ("return_no_results", "END"),
        
        ("check_semantic_hits", "generate_author_cypher", {"label": "Yes"}),
        ("generate_author_cypher", "run_author_cypher"),
        ("run_author_cypher", "synthesize_final_author"),
        ("synthesize_final_author", "return_semantic_result"),
        ("return_semantic_result", "END"),
    ]
    
    # Add all edges
    for edge in edges:
        if len(edge) == 3:
            G.add_edge(edge[0], edge[1], **edge[2])
        else:
            G.add_edge(edge[0], edge[1])
    
    return G


def export_to_graphml(G: nx.DiGraph, filename: str = "system_cfg.graphml"):
    """Export graph to GraphML format for yEd, Gephi, etc."""
    nx.write_graphml(G, filename)
    print(f"✓ Exported to {filename} (use with yEd, Gephi)")


def export_to_dot(G: nx.DiGraph, filename: str = "system_cfg.dot"):
    """Export graph to DOT format for Graphviz."""
    try:
        from networkx.drawing.nx_pydot import write_dot
        write_dot(G, filename)
        print(f"✓ Exported to {filename} (use with Graphviz)")
    except ImportError:
        print(f"⚠ Skipped {filename} (pydot not installed - run: pip install pydot)")


def export_to_json(G: nx.DiGraph, filename: str = "system_cfg.json"):
    """Export graph to JSON format for D3.js, Cytoscape.js, etc."""
    from networkx.readwrite import json_graph
    data = json_graph.node_link_data(G)
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"✓ Exported to {filename} (use with D3.js, Cytoscape.js)")


def export_to_mermaid(G: nx.DiGraph, filename: str = "system_cfg.mmd"):
    """Export graph to Mermaid format for markdown/web visualization."""
    lines = ["flowchart TD"]
    
    # Add nodes with styling
    for node_id, attrs in G.nodes(data=True):
        label = attrs.get('label', node_id).replace('\n', '<br/>')
        node_type = attrs.get('type', 'process')
        
        # Different shapes for different node types
        if node_type == 'decision':
            lines.append(f'    {node_id}{{{label}}}')
        elif node_type == 'entry' or node_type == 'exit':
            lines.append(f'    {node_id}([{label}])')
        elif node_type == 'output':
            lines.append(f'    {node_id}[/{label}/]')
        else:
            lines.append(f'    {node_id}[{label}]')
    
    lines.append("")
    
    # Add edges
    for u, v, attrs in G.edges(data=True):
        label = attrs.get('label', '')
        if label:
            lines.append(f'    {u} -->|{label}| {v}')
        else:
            lines.append(f'    {u} --> {v}')
    
    # Add styling
    lines.append("")
    lines.append("    classDef decision fill:#FF9800,stroke:#E65100,stroke-width:2px,color:#000")
    lines.append("    classDef process fill:#2196F3,stroke:#0D47A1,stroke-width:2px,color:#fff")
    lines.append("    classDef database fill:#9C27B0,stroke:#4A148C,stroke-width:2px,color:#fff")
    lines.append("    classDef entry fill:#4CAF50,stroke:#1B5E20,stroke-width:3px,color:#fff")
    lines.append("    classDef output fill:#F44336,stroke:#B71C1C,stroke-width:2px,color:#fff")
    
    with open(filename, 'w') as f:
        f.write('\n'.join(lines))
    print(f"✓ Exported to {filename} (use with Mermaid Live Editor)")


def generate_statistics(G: nx.DiGraph) -> Dict:
    """Generate statistics about the CFG."""
    stats = {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "decision_points": sum(1 for _, attrs in G.nodes(data=True) if attrs.get('type') == 'decision'),
        "llm_calls": sum(1 for _, attrs in G.nodes(data=True) 
                        if 'LLM' in attrs.get('label', '')),
        "database_operations": sum(1 for _, attrs in G.nodes(data=True) 
                                  if attrs.get('type') == 'process' and 'Neo4j' in attrs.get('label', '')),
        "cyclomatic_complexity": G.number_of_edges() - G.number_of_nodes() + 2,
        "max_path_length": nx.dag_longest_path_length(G) if nx.is_directed_acyclic_graph(G) else "N/A (contains cycles)",
    }
    return stats


def print_statistics(stats: Dict):
    """Print CFG statistics in a readable format."""
    print("\n" + "="*60)
    print("CONTROL FLOW GRAPH STATISTICS")
    print("="*60)
    for key, value in stats.items():
        formatted_key = key.replace('_', ' ').title()
        print(f"{formatted_key:.<40} {value}")
    print("="*60 + "\n")


if __name__ == "__main__":
    print("Generating Control Flow Graph for Neo4j Research Q&A System...\n")
    
    # Create the CFG
    G = create_system_cfg()
    
    # Generate and print statistics
    stats = generate_statistics(G)
    print_statistics(stats)
    
    # Export to multiple formats
    print("Exporting to various formats...\n")
    export_to_graphml(G, "system_cfg.graphml")
    export_to_dot(G, "system_cfg.dot")
    export_to_json(G, "system_cfg.json")
    export_to_mermaid(G, "system_cfg.mmd")
    
    print("\n" + "="*60)
    print("VISUALIZATION RECOMMENDATIONS")
    print("="*60)
    print("""
1. **yEd Graph Editor** (RECOMMENDED - Desktop)
   - File: system_cfg.graphml
   - Download: https://www.yworks.com/products/yed
   - Features: Auto-layout, hierarchical view, export to PNG/SVG
   - Best for: Professional diagrams, presentations

2. **Mermaid Live Editor** (RECOMMENDED - Online)
   - File: system_cfg.mmd
   - URL: https://mermaid.live/
   - Features: Interactive, markdown-compatible, shareable
   - Best for: Quick visualization, documentation

3. **Graphviz Online** (Online)
   - File: system_cfg.dot
   - URL: https://dreampuf.github.io/GraphvizOnline/
   - Features: Classic graph layouts, simple interface
   - Best for: Quick DOT visualization

4. **Gephi** (Desktop - Advanced)
   - File: system_cfg.graphml
   - Download: https://gephi.org/
   - Features: Network analysis, advanced layouts, statistics
   - Best for: Complex analysis, large graphs

5. **D3.js / Observable** (Online - Interactive)
   - File: system_cfg.json
   - URL: https://observablehq.com/
   - Features: Custom interactive visualizations
   - Best for: Web embedding, custom interactions

6. **Cytoscape.js** (Web Framework)
   - File: system_cfg.json
   - URL: https://js.cytoscape.org/
   - Features: Web-based graph visualization library
   - Best for: Embedding in web applications
    """)
    print("="*60)
