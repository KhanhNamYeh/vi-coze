import json
import openai
import re


class SQLRetrievalBot:
    def __init__(self, kb_path="final_sql_kb.json", model="llama3"):
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                self.kb_data = json.load(f)
            print(f"--- Đã nạp tri thức: {len(self.kb_data['nodes'])} Nodes, {len(self.kb_data['edges'])} Edges ---")
        except FileNotFoundError:
            self.kb_data = {"nodes": [], "edges": []}

        self.client = openai.OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        self.model = model

    def get_hints(self, query):
        query_lower = query.lower()
        all_found = []

        for link in self.kb_data.get('edges', []):
            source = str(link['source']).lower()
            target = str(link['target'])
            label = str(link['label'])

            if source in query_lower and len(source) > 2:
                all_found.append({
                    "source": source,
                    "hint": f"RULE: IF context is '{source}', THEN use SQL: {target}",
                    "length": len(source)
                })

        # Sắp xếp theo độ dài từ khóa giảm dần và lấy top 5 gợi ý tốt nhất
        all_found = sorted(all_found, key=lambda x: x['length'], reverse=True)
        top_hints = [item['hint'] for item in all_found[:5]]
        found_nodes = [item['source'] for item in all_found[:5]]

        return "\n".join(top_hints), list(set(found_nodes))

    def ask(self, user_query):
        hints, nodes = self.get_hints(user_query)

        print(f"\n[QUERY]: {user_query}")
        if nodes:
            print(f"✅ [KG MATCH]: {', '.join(nodes)}")

        # PROMPT SIÊU ÉP BUỘC
        prompt = f"""
You are a SQL Generator. 
STRICT RULES:
1. Return ONLY the SQL query. 
2. DO NOT explain. DO NOT say "Here is your query".
3. Use the MANDATORY business rules below:

{hints if hints else "Use standard SQL logic."}

QUESTION: {user_query}
SQL:"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "You only output pure SQL code."},
                          {"role": "user", "content": prompt}],
                temperature=0
            )
            raw_sql = response.choices[0].message.content.strip()
            # Xử lý cắt bỏ mọi phần giải thích thừa nếu AI vẫn cố tình nói
            sql_match = re.search(r"(SELECT|WITH|UPDATE|DELETE).*?;", raw_sql, re.DOTALL | re.IGNORECASE)
            return sql_match.group(0) if sql_match else raw_sql
        except Exception as e:
            return f"Error: {e}"


if __name__ == "__main__":
    bot = SQLRetrievalBot()
    test_queries = [
        "Có bao nhiêu khách hàng dùng đồng koruna của séc?",
        "Tính mức lương trung bình thấp nhất của khách hàng nữ",
        "Tìm khách hàng 6 đã tiêu thụ bao nhiêu"
    ]
    for q in test_queries:
        print(f"[FINAL SQL]:\n{bot.ask(q)}")
        print("-" * 50)