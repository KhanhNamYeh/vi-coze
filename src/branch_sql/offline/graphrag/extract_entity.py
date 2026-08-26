import json
import os
import pandas as pd
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. Setup Client
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama" # Required by the library but ignored by Ollama
)

MODEL_ID = "llama3"
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUT_FILE = os.path.join(base_dir, "data", "processed", "sql", "p1", "mo_ta_bang_bds_new__docx.chunks.jsonl")

def extract_entities_and_relations(chunk_text):
    """
    Same extraction logic as before, now receiving
    chunk_content directly from the JSONL.
    """
    prompt = f"""
    Walk through step by step reasoning
    
    Extract:
    
    + Entities (name, type, description): objects, names, items, concepts, ...
    
    + Relationships (source, target, description): direct relationships, semantic relationships, implicit, explicit, ...
    
    Return ONLY a JSON object with this structure:
    {{
      "entities": [{{"name": "string", "type": "string", "description": "string"}}],
      "relationships": [{{"source": "string", "target": "string", "description": "string"}}]
    }}
    TEXT: {chunk_text}
    """

    try:
        # Step 1: Initial pass
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)

        if "entities" not in data: data["entities"] = []
        if "relationships" not in data: data["relationships"] = []

        # Step 2: Self-Reflection
        reflection_prompt = f"""
        Walk through step by step reasoning
        Review these extractions: {json.dumps(data)}
        Based on this text: {chunk_text}
        Did you miss any entities or relationships? Return ONLY the new ones in the same JSON format.
        """
        reflection = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": reflection_prompt}],
            response_format={"type": "json_object"}
        )

        extra_data = json.loads(reflection.choices[0].message.content)
        data["entities"].extend(extra_data.get("entities", []))
        data["relationships"].extend(extra_data.get("relationships", []))

        return data
    except Exception as e:
        print(f"Error processing chunk: {e}")
        return {"entities": [], "relationships": []}

def process_chunk_task(chunk_id, content):
    res = extract_entities_and_relations(content)
    # Add the chunk_id to each item before returning
    for ent in res.get("entities", []):
        ent["source_chunk"] = chunk_id
    for rel in res.get("relationships", []):
        rel["source_chunk"] = chunk_id
    return res

# --- Run Program ---

all_entities = []
all_relationships = []

if not os.path.exists(INPUT_FILE):
    print(f"Error: Could not find {INPUT_FILE}")
else:
    print(f"Reading chunks from {INPUT_FILE}...")

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        chunks = [json.loads(line) for line in f]

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for i, chunk_data in enumerate(chunks):
            chunk_id = chunk_data.get("metadata", {}).get("chunk_id", f"unknown_{i}")
            content = chunk_data.get("page_content", "")

            if not content:
                continue

            print(f"Submitting chunk {i + 1}: {chunk_id}...")
            futures.append(executor.submit(process_chunk_task, chunk_id, content))

        for future in as_completed(futures):
            res = future.result()
            all_entities.extend(res.get("entities", []))
            all_relationships.extend(res.get("relationships", []))
            print(f"[{i + 1}/{len(futures)}] Chunk extraction complete.")

    # Save Results
    pd.DataFrame(all_entities).to_csv("result/communities/raw_entities.csv", index=False)
    pd.DataFrame(all_relationships).to_csv("result/communities/raw_relationships.csv", index=False)
    print("\nExtraction complete. Files saved: raw_entities.csv, raw_relationships.csv")