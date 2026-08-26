import pandas as pd
import time
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import openai
import re
import itertools

# 1. Setup Client
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)
MODEL_ID = "llama3"


# 2. Define the Retry Logic
def clean_format_text(text):
    """
    Rule-based function to ensure text looks like a single paragraph:
    - Removes newlines/extra tabs.
    - Trims leading/trailing whitespace.
    - Ensures it ends with a period.
    """
    cleaned = re.sub(r'\s+', ' ', text).strip()

    if cleaned and not cleaned.endswith(('.', '!', '?')):
        cleaned += '.'

    return cleaned


def get_summary_with_retry(name, combined_desc, threshold=250):
    if len(combined_desc) < threshold:
        return clean_format_text(combined_desc)

    prompt = f"Summarize these various descriptions of the entity '{name}' into one professional paragraph: {combined_desc}"

    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling LLM: {e}")
        return clean_format_text(combined_desc)


def resolve_entities():
    try:
        df = pd.read_csv("result/communities/raw_entities.csv")
    except FileNotFoundError:
        return

    df['norm_name'] = df['name'].str.lower().str.strip()

    resolved_data = []
    groups = list(df.groupby('norm_name'))
    total = len(groups)

    for i, (name, group) in enumerate(groups):
        combined_desc = " | ".join(group['description'].dropna().astype(str).unique())

        try:
            summary = get_summary_with_retry(name, combined_desc)
            resolved_data.append({"name": name.lower(), "description": summary})

            # progress check
            if (i + 1) % 5 == 0:
                print(f"Processed {i + 1}/{total} entities...")

            time.sleep(2)

        except Exception as e:
            print(f"Skipping entity '{name}' after repeated failures: {e}")

    pd.DataFrame(resolved_data).to_csv("result/communities/resolved_entities.csv", index=False)

    # 1. Create a list for edges
    all_edges = []

    # 2. Add Extracted Relationships first (High Quality)
    try:
        raw_rel_df = pd.read_csv("result/communities/raw_relationships.csv")
        for _, row in raw_rel_df.iterrows():
            all_edges.append({
                "source": str(row['source']).lower().strip(),
                "target": str(row['target']).lower().strip(),
                "description": row['description'],
                "weight": 5  # Give LLM-extracted edges higher initial weight
            })
    except FileNotFoundError:
        pass

    # 3. Add Co-occurrences (Lower Quality/Support)
    chunk_groups = df.groupby('source_chunk')['norm_name'].apply(list)
    for entity_list in chunk_groups:
        unique_entities = list(set(entity_list))
        if len(unique_entities) > 1:
            limited_entities = unique_entities[:10]
            for source, target in itertools.combinations(limited_entities, 2):
                all_edges.append({
                    "source": source,
                    "target": target,
                    "description": "co-occurrence",
                    "weight": 1  # Lower weight for simple co-occurrence
                })

    pd.DataFrame(all_edges).to_csv("result/communities/resolved_relationships.csv", index=False)

def normalize_relationships():
    try:
        rel_df = pd.read_csv("result/communities/resolved_relationships.csv")
    except FileNotFoundError:
        return

    rel_df['source'] = rel_df['source'].astype(str)
    rel_df['target'] = rel_df['target'].astype(str)

    # Remove self-loops
    rel_df = rel_df[rel_df['source'] != rel_df['target']]

    # 4. Aggregate by source/target and SUM weights
    normalized = rel_df.groupby(['source', 'target']).agg({
        'weight': 'sum',
        'description': lambda x: " | ".join(set(str(s) for s in x if s and s != 'nan'))
    }).reset_index()

    normalized.to_csv("resolved_relationships.csv", index=False)


if __name__ == "__main__":
    resolve_entities()
    normalize_relationships()