import os
import re
import json
import openai
import networkx as nx
from pathlib import Path
from pyvis.network import Network
import time


class SQLKnowledgeGraphBuilder:
    def __init__(self, use_local=True, api_key=None, base_url=None, model=None):
        if use_local:
            self.client = openai.OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama"
            )
            self.model = model if model else "llama3"
            print(f"--- Đang dùng GPU + OLLAMA với model: {self.model} ---")
        else:
            self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
            self.model = model if model else "deepseek-ai/DeepSeek-V3"
            print(f"--- Đang dùng CLOUD API ---")

        self.kg = nx.DiGraph()

    def parse_ddl_folder(self, folder_path):
        print(f"--- Đọc DDL: {folder_path} ---")
        path = Path(folder_path)
        if not path.exists(): return
        for file_path in path.glob("*.sql"):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                tables = re.findall(r"CREATE TABLE\s+(\w+)\s*\((.*?)\);", content, re.DOTALL | re.IGNORECASE)
                for table_name, col_block in tables:
                    table_name = table_name.lower()
                    self.kg.add_node(table_name, type="table", color="#e74c3c", label=table_name)
                    cols = re.findall(r"^\s*(\w+)\s+", col_block, re.MULTILINE)
                    for col in cols:
                        col_node = f"{table_name}.{col.lower()}"
                        self.kg.add_node(col_node, type="column", color="#3498db", label=col.lower())
                        self.kg.add_edge(col_node, table_name, label="belongs_to")

    def parse_business_folder(self, folder_path):
        print(f"--- Đọc Business Rules: {folder_path} ---")
        path = Path(folder_path)
        if not path.exists(): return
        for file_path in path.glob("*.md"):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                prompt = f"Convert these business rules into a JSON array of SPO triples [{{'subject': '...', 'predicate': '...', 'object': '...'}}]. Text: {content[:2000]}"
                self._llm_extract_to_graph(prompt, "business_rule")

    def parse_gold_folder(self, folder_path):
        print(f"--- Đọc Gold Standard: {folder_path} ---")
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.endswith(".sql"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        blocks = re.split(r'-- \[question_id=', content)
                        for block in blocks[1:20]:
                            query_match = re.search(r'-- Query: (.*?)\n', block)
                            evidence_match = re.search(r'-- Evidence: (.*?)\n', block)
                            if query_match and evidence_match:
                                question = query_match.group(1).strip()
                                evidence = evidence_match.group(1).strip()

                                prompt = f"""
                                Task: Map Natural Language to SQL logic.
                                Question: {question}
                                Evidence: {evidence}
                                Output ONLY a JSON array. Use double quotes for all keys and values. 
                                Escape any internal quotes with a backslash.
                                Format: [{{"subject": "NL phrase", "predicate": "mapping", "object": "SQL concept"}}]
                                """
                                self._llm_extract_to_graph(prompt, "gold_evidence")

    def _llm_extract_to_graph(self, prompt, node_type):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            raw = response.choices[0].message.content.strip()

            raw = re.sub(r'```json|```', '', raw).strip()

            json_match = re.search(r'\[.*\]', raw, re.DOTALL)
            triples = []

            if json_match:
                json_str = json_match.group()
                try:
                    triples = json.loads(json_str)
                except:
                    json_str = re.sub(r"(['\"])\s*(\w+)\s*(['\"])\s*:", r'"\2":', json_str)
                    object_matches = re.findall(r'\{.*?\}', json_str, re.DOTALL)
                    for obj_str in object_matches:
                        try:
                            triples.append(json.loads(obj_str))
                        except:
                            s_match = re.search(r'"subject":\s*"(.*?)"', obj_str)
                            p_match = re.search(r'"predicate":\s*"(.*?)"', obj_str)
                            o_match = re.search(r'"object":\s*"(.*?)"', obj_str)
                            if s_match and o_match:
                                triples.append({
                                    "subject": s_match.group(1),
                                    "predicate": p_match.group(1) if p_match else "logic",
                                    "object": o_match.group(1)
                                })

            # 4. Lưu vào Graph
            if triples:
                count = 0
                for t in triples:
                    if isinstance(t, dict) and 'subject' in t and 'object' in t:
                        s, o = str(t['subject']).lower(), str(t['object']).lower()
                        p = str(t.get('predicate', 'logic')).lower()
                        if s and o and s != o:
                            self.kg.add_node(s, type=node_type, color="#f1c40f", label=s)
                            self.kg.add_edge(s, o, label=p)
                            count += 1
                if count > 0:
                    print(f"  [OK] Đã thêm {count} quan hệ.")
            else:
                print(f"  [?] Không parse được JSON. Raw (100 char): {raw[:100]}...")

        except Exception as e:
            print(f"  [!] Lỗi hệ thống: {e}")

    def save_and_visualize(self):
        if not self.kg.nodes:
            print("Graph trống, không có gì để lưu!")
            return

        import json
        from networkx.readwrite import json_graph

        data = json_graph.node_link_data(self.kg)
        with open("final_sql_kb.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("--- Đã lưu file: final_sql_kb.json ---")
        net = Network(height="850px", width="100%", bgcolor="#222222", font_color="white", directed=True)
        net.force_atlas_2based()
        for n, attrs in self.kg.nodes(data=True):
            net.add_node(n, label=attrs.get('label', n), color=attrs.get('color', '#888888'))
        for u, v, d in self.kg.edges(data=True):
            net.add_edge(u, v, label=d['label'])

        net.save_graph("sql_knowledge_map.html")
        print(f"--- HOÀN THÀNH: {len(self.kg.nodes)} Nodes ---")


if __name__ == "__main__":
    BASE_PATH = r"/benchmark_data"
    builder = SQLKnowledgeGraphBuilder(use_local=True, model="llama3")

    builder.parse_ddl_folder(os.path.join(BASE_PATH, "sql"))
    builder.parse_business_folder(os.path.join(BASE_PATH, "business"))
    builder.parse_gold_folder(os.path.join(BASE_PATH, "gold"))
    builder.save_and_visualize()