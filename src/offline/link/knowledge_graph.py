import os
import re
import json
import openai
import networkx as nx
from pathlib import Path
from pyvis.network import Network
from networkx.readwrite import json_graph

from ...branch_sql.config import KNOWLEDGE_DIR, PROCESSED_DIR, ROOT


class SQLKnowledgeGraphBuilder:
    def __init__(self, use_local=True, api_key=None, base_url=None, model=None):
        if use_local:
            self.client = openai.OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
            self.model = model if model else "llama3"
            print(f"--- Using Local LLM: {self.model} ---")
        else:
            self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
            self.model = model if model else "deepseek-ai/DeepSeek-V3"

        self.kg = nx.MultiDiGraph()
        self.ignore_nodes = {
            "number", "varchar2", "char", "date", "timestamp", "clob", "blob",
            "integer", "int", "float", "null", "not", "other_table", "unknown"
        }

        self.colors = {
            "table": "#ff4757",
            "column": "#1e90ff",
            "business_rule": "#ffa502",
            "formula": "#2ed573",
            "concept": "#a55eea",
            "synonym": "#eccc68",
            "link": "#7f8c8d"
        }

    def _add_node(self, node_id, label, node_type, **kwargs):
        clean_id = str(node_id).lower().strip()
        if clean_id in self.ignore_nodes or not clean_id or len(clean_id) < 2:
            return

        sizes = {"table": 85, "column": 30, "business_rule": 50, "formula": 45, "concept": 55}
        base_size = sizes.get(node_type, 30)
        color = self.colors.get(node_type, "#888888")

        self.kg.add_node(
            clean_id,
            label=label,
            type=node_type,
            color=color,
            size=base_size,
            font={'size': 18 if node_type == 'table' else 12, 'color': 'white', 'strokeWidth': 2},
            **kwargs
        )

    def process_files(self, input_paths):
        # List of supported extensions
        supported_exts = [".md", ".sql", ".txt", ".csv", ".json", ".jsonl"]

        files = []
        for p in input_paths:
            possible_locs = [Path(p), ROOT / p]
            target_loc = next((loc for loc in possible_locs if loc.exists()), None)

            if target_loc:
                print(f"--- Finding data at: {target_loc} ---")
                if target_loc.is_dir():
                    # Collect all supported file types
                    for ext in supported_exts:
                        files.extend(list(target_loc.rglob(f"*{ext}")))
                else:
                    files.append(target_loc)

        unique_files = list(dict.fromkeys([f for f in files if f.is_file()]))
        if not unique_files:
            print("!!! No files found. Check your paths. !!!")
            return

        for f_path in unique_files:
            print(f"--- Processing: {f_path.name} ---")
            try:
                with open(f_path, "r", encoding="utf-8") as f:
                    content = f.read()

                suffix = f_path.suffix.lower()
                if suffix == ".md":
                    self._parse_markdown_schema(content)
                elif suffix in [".json", ".jsonl"]:
                    # Try to simplify JSON content for the LLM
                    try:
                        # If it's JSONL, this is a quick way to get text
                        clean_text = re.sub(r'[{} "\[\]]', ' ', content)
                        self._parse_generic_content(clean_text, f_path.stem)
                    except:
                        self._parse_generic_content(content, f_path.stem)
                elif suffix in [".sql", ".txt", ".csv"]:
                    self._parse_generic_content(content, f_path.stem)

            except Exception as e:
                print(f"Error reading {f_path.name}: {e}")

        self.save_and_visualize(str(KNOWLEDGE_DIR / "sql_knowledge_map"))

    def _parse_markdown_schema(self, content):
        table_sections = re.split(r'##\s*Bảng\s+', content)
        for section in table_sections[1:]:
            lines = section.strip().split('\n')
            if not lines: continue

            raw_table_name = lines[0].strip()
            table_name = re.sub(r'TABLE\((.*?)\)', r'\1', raw_table_name).split('(')[0].strip().lower()
            table_name = table_name.split(' ')[0]

            self._add_node(table_name, table_name.upper(), "table", title=f"Table: {table_name}")

            # Extract Columns
            col_matches = re.findall(r'\|\s*([\w_]+)\s*\|\s*([^|]*)\s*\|\s*([^|]*)\s*\|', section)
            for col_name, col_type, col_desc in col_matches:
                col_name = col_name.strip().lower()
                if col_name in ["tên_cột", "mô_tả", "column_name", "tên"]: continue
                col_id = f"{table_name}.{col_name}"
                self._add_node(col_id, col_name, "column", title=f"Type: {col_type}\nDesc: {col_desc}")
                self.kg.add_edge(table_name, col_id, label="has_column", weight=1, color="#1e90ff")

            # Link Detection
            link_section = re.search(r'Mối liên kết:\s*(.*?)(?=Ghi chú|##|$)', section, re.S)
            if link_section:
                potential_keys = re.findall(r'([A-Z0-9_]{5,})', link_section.group(1).strip())
                for key in potential_keys:
                    self.kg.add_edge(table_name, key.lower(), label="links_via", color="#7f8c8d", style="dashed")

            # LLM Enrichment
            self._llm_extract_everything(section, table_name)

    def _parse_generic_content(self, content, filename):
        """Processes the entire file by splitting it into overlapping chunks for the LLM."""
        print(f"  > Processing full file: {filename} ({len(content)} chars)")

        # Configuration for chunking
        CHUNK_SIZE = 4000
        OVERLAP = 200

        start = 0
        chunk_count = 0

        while start < len(content):
            chunk_count += 1
            end = start + CHUNK_SIZE
            chunk = content[start:end]

            print(f"    - Processing chunk {chunk_count} (chars {start} to {min(end, len(content))})...")

            prompt = f"""
            Analyze the following technical content (Part {chunk_count}) from the file '{filename}':

            {chunk}

            INSTRUCTIONS:
            1. Identify the primary Tables or Business Subjects mentioned in this segment.
            2. Extract columns, business rules, SQL formulas, and relationships.
            3. If this is a continuation of a previous segment, focus on the new entities or properties.

            Return ONLY a JSON array of triples:
            [
              {{"subject": "TABLE_NAME", "predicate": "has_column", "object": "COLUMN_NAME", "type": "column"}},
              {{"subject": "TABLE_NAME", "predicate": "defined_as", "object": "EXPRESSION", "type": "formula"}},
              {{"subject": "CONCEPT_A", "predicate": "related_to", "object": "CONCEPT_B", "type": "concept"}}
            ]
            """

            self._llm_run_and_merge(prompt)

            start += (CHUNK_SIZE - OVERLAP)

            if CHUNK_SIZE - OVERLAP <= 0:
                break

    def _llm_extract_everything(self, text_chunk, table_context):
        """Processes the entire markdown section in chunks to extract formulas and concepts."""
        print(f"    - Deep diving into: {table_context} ({len(text_chunk)} chars)")

        # Configuration for chunking
        CHUNK_SIZE = 4000
        OVERLAP = 200

        start = 0
        chunk_count = 0

        while start < len(text_chunk):
            chunk_count += 1
            end = start + CHUNK_SIZE
            current_segment = text_chunk[start:end]

            prompt = f"""
                        Analyze the following documentation segment (Part {chunk_count}) for table '{table_context}':

                        {current_segment}

                        Extract:
                        1. Business Concepts: (e.g., "PTM", "VLR")
                        2. SQL Formulas/Filters: (e.g., "STATUS = 1")
                        3. Calculations: (e.g., "Total = MC + MF")
                        4. Relationships: Identify other tables mentioned and link them.

                        IMPORTANT: 
                        - Do NOT use placeholders like "OTHER_TABLE" or "CONCEPT_A". 
                        - Use only REAL names found in the text.
                        - If no relationship is found, return an empty array [].

                        Return ONLY a JSON array of triples:
                        [
                          {{"subject": "ActualName", "predicate": "has_formula", "object": "Value", "type": "formula"}}
                        ]
                        """

            self._llm_run_and_merge(prompt)

            start += (CHUNK_SIZE - OVERLAP)

            if (CHUNK_SIZE - OVERLAP) <= 0: break

    def _llm_run_and_merge(self, prompt):
        """Helper to execute LLM call and add results to the graph."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "You are a Data Architect. Output JSON only."},
                          {"role": "user", "content": prompt}],
                temperature=0.1
            )
            raw_content = response.choices[0].message.content
            if not raw_content: return

            match = re.search(r'\[.*\]', raw_content, re.DOTALL)
            if not match: return

            triples = json.loads(match.group())

            for t in triples:
                # Use .get() with defaults to prevent KeyErrors
                subj = t.get('subject')
                pred = t.get('predicate', 'related_to')
                obj = t.get('object')
                n_type = t.get('type', 'concept')

                if subj is None or obj is None:
                    continue

                s_id = str(subj).lower().replace(" ", "_")
                o_id = str(obj).lower().replace(" ", "_")

                if not s_id or not o_id:
                    continue

                if s_id not in self.kg:
                    self._add_node(s_id, str(subj), n_type if n_type != "column" else "table")
                if o_id not in self.kg:
                    self._add_node(o_id, str(obj), n_type)

                self.kg.add_edge(s_id, o_id, label=pred,
                                 color=self.colors.get(n_type, "#a55eea"))
        except Exception as e:
            print(f"  > LLM Parsing error: {e}")

    def save_and_visualize(self, output_prefix):
        if not self.kg.nodes:
            print("Graph is empty.")
            return

        centrality = nx.degree_centrality(self.kg)
        for node in self.kg.nodes:
            base_size = 15
            scaling_factor = 100
            self.kg.nodes[node]['size'] = base_size + (centrality[node] * scaling_factor)

        with open(f"{output_prefix}.json", "w", encoding="utf-8") as f:
            json.dump(json_graph.node_link_data(self.kg), f, ensure_ascii=False, indent=2)

        net = Network(height="1000px", width="100%", bgcolor="#1a1a1a", font_color="white", directed=True)
        net.from_nx(self.kg)

        # 2. DISABLE CURVED LINES AND TUNE PHYSICS
        net.set_options("""
        {
          "physics": {
            "forceAtlas2Based": { 
                "gravitationalConstant": -150, 
                "springLength": 150,
                "avoidOverlap": 0.5
            },
            "solver": "forceAtlas2Based",
            "stabilization": { "iterations": 100 }
          },
          "edges": { 
            "smooth": false, 
            "arrows": { "to": { "enabled": true, "scaleFactor": 0.4 } },
            "color": { "inherit": "from" },
            "width": 1
          }
        }
        """)

        net.save_graph(f"{output_prefix}.html")
        print(f"--- Success! Graph created with {self.kg.number_of_nodes()} nodes ---")


def build(markdown_path, *, out_dir=None, model="llama3") -> dict:
    """Bước `knowledge` của chain trong `offline_sql.py`.

    markdown -> node-link JSON + HTML. Trả về đường dẫn và kích thước graph để
    `offline_sql.main()` in ra, giống các bước khác.
    """
    out_dir = Path(out_dir or KNOWLEDGE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "sql_knowledge_map"

    builder = SQLKnowledgeGraphBuilder(use_local=True, model=model)
    builder.process_files([str(markdown_path)])

    return {
        "json": prefix.with_suffix(".json"),
        "html": prefix.with_suffix(".html"),
        "n_nodes": builder.kg.number_of_nodes(),
        "n_edges": builder.kg.number_of_edges(),
    }


if __name__ == "__main__":
    # Chạy riêng trên toàn bộ markdown đã có, không qua offline_sql.
    for md in sorted(PROCESSED_DIR.glob("*.md")):
        print(build(md))