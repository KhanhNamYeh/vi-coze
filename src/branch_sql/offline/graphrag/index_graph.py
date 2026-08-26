import os
import networkx as nx
import pandas as pd
import time
from graspologic.partition import hierarchical_leiden
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import openai
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. Setup Client
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=600.0 # Increase to 10 minutes to be safe for local inference
)
MODEL_ID = "llama3"

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((openai.APITimeoutError, openai.APIConnectionError))
)
def get_community_report(community_id, level, context_text):
    """
    Generates a report-like summary.
    """
    prompt = f"""
    WRITE A COMPREHENSIVE COMMUNITY REPORT

    COMMUNITY ID: {community_id}
    HIERARCHY LEVEL: {level}

    CONTEXT:
    {context_text}

    GOAL:
    Write a report that understands the global structure and semantics of this community. 
    Include:
    1. TITLE: A short, specific name for this community.
    2. SUMMARY: An executive summary of the overall structure and how entities relate.
    3. DETAILED FINDINGS: 3-5 key insights about the relationships and roles within this group.

    Format the output as a professional report.
    """
    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def build_hierarchical_index():
    try:
        nodes_df = pd.read_csv("result/communities/resolved_entities.csv")
        edges_df = pd.read_csv("result/communities/resolved_relationships.csv")
    except FileNotFoundError:
        print("Error: Missing CSV files.")
        return

    G = nx.Graph()

    # 1. Add Nodes
    for _, row in nodes_df.iterrows():
        G.add_node(str(row['name']).strip().lower(),
                   display_name=row['name'],
                   description=row['description'])

    # 2. Add Edges
    for _, row in edges_df.iterrows():
        src, tgt = str(row['source']).strip().lower(), str(row['target']).strip().lower()
        if src in G and tgt in G:
            if G.has_edge(src, tgt):
                G[src][tgt]['weight'] += row['weight']
            else:
                G.add_edge(src, tgt, weight=row['weight'], description=row['description'])

    print(f"Graph stats: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    isolates = list(nx.isolates(G))
    G.remove_nodes_from(isolates)
    print(f"Removed {len(isolates)} isolated nodes.")

    # 3. Hierarchical Leiden
    print("\n--- Starting Hierarchical Leiden ---")
    print(f"Graph stats: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    node_membership = []
    levels = {}
    node_level_map = {}

    try:
        # These parameters successfully generated a 3-level hierarchy
        communities = hierarchical_leiden(
            G,
            max_cluster_size=5,
            resolution=2.5
        )

        communities_list = list(communities)
        print(f"Raw community records returned: {len(communities_list)}")

        # Map levels to nodes
        for node_comm in communities_list:
            node = node_comm.node
            level = getattr(node_comm, 'level', None)
            cluster_id = node_comm.cluster

            if node not in node_level_map:
                node_level_map[node] = {}

            if level is None:
                level = len(node_level_map[node])

            node_level_map[node][level] = cluster_id

        # Convert map to CSV records and update Graph G
        max_depth_found = 0
        for node, levels_dict in node_level_map.items():
            sorted_level_indices = sorted(levels_dict.keys())
            max_depth_found = max(max_depth_found, len(sorted_level_indices))

            membership_record = {"node": node}
            for level_idx in sorted_level_indices:
                comm_id = levels_dict[level_idx]

                # Update Graph object attributes for GEXF
                G.nodes[node][f'community_level_{level_idx}'] = comm_id
                # Update CSV record
                membership_record[f'level_{level_idx}'] = comm_id
                # Populate levels dict for the next steps in the script
                levels.setdefault(level_idx, {}).setdefault(comm_id, []).append(node)

            node_membership.append(membership_record)

        print(f"Processed {len(node_membership)} unique nodes.")
        print(f"Maximum hierarchy depth reached: {max_depth_found}")

    except Exception as e:
        print(f"Hierarchical Leiden failed: {e}")
        import traceback
        traceback.print_exc()
        from graspologic.partition import leiden
        partition = leiden(G)
        levels = {0: {}}
        node_membership = []
        for node, comm_id in partition.items():
            levels[0].setdefault(comm_id, []).append(node)
            G.nodes[node]['community_level_0'] = comm_id
            node_membership.append({"node": node, "level_0": comm_id})

    # Final Export
    df_membership = pd.DataFrame(node_membership)
    print("\nDataFrame Summary (Nodes per level):")
    print(df_membership.notnull().sum())

    df_membership.to_csv("node_community_membership.csv", index=False)
    nx.write_gexf(G, "result/communities/community_graph.gexf")
    print(f"Saved node_community_membership.csv and community_graph.gexf")

    def process_comm(comm_id, level_idx, members):
        # Move the logic for single report generation here
        ent_ctx = [f"ENTITY: {G.nodes[m]['display_name']} - {G.nodes[m]['description']}" for m in members]
        subgraph = G.subgraph(members)
        rel_ctx = [f"RELATION: {G.nodes[u]['display_name']} -> {G.nodes[v]['display_name']}" for u, v, d in
                   subgraph.edges(data=True)]

        full_ctx = "\n".join(ent_ctx + rel_ctx)
        try:
            print(f"  Generating report for Level {level_idx} / Comm {comm_id} ({len(members)} nodes)...")
            report = get_community_report(comm_id, level_idx, full_ctx)
            return {"level": level_idx, "community_id": comm_id, "report": report, "members": ", ".join(members)}
        except Exception as e:
            print(f"Error in Comm {comm_id} (Level {level_idx}): {type(e).__name__} - {e}")
            return None

    # 4. Bottom-Up Reporting
    REPORT_FILE = "result/communities/hierarchical_community_reports.csv"
    processed_ids = set()

    # Load existing reports to skip them
    if os.path.exists(REPORT_FILE):
        try:
            existing_df = pd.read_csv(REPORT_FILE)
            # Create unique keys (level + ID) to ensure we don't skip the wrong one
            processed_ids = set(zip(existing_df['level'], existing_df['community_id']))
            print(f"Resuming: Found {len(processed_ids)} already processed communities.")
        except Exception as e:
            print(f"Could not read existing reports, starting fresh: {e}")

    all_reports = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {}
        for level_idx in sorted(levels.keys(), reverse=True):
            for comm_id, members in levels[level_idx].items():
                if (level_idx, comm_id) in processed_ids:
                    continue

                job = executor.submit(process_comm, comm_id, level_idx, members)
                futures[job] = (level_idx, comm_id)

        for future in as_completed(futures):
            res = future.result()
            if res:
                all_reports.append(res)
                df_temp = pd.DataFrame([res])
                file_exists = os.path.isfile(REPORT_FILE)
                df_temp.to_csv(REPORT_FILE, mode='a', index=False, header=not file_exists)

                print(f"  [SAVED] Level {res['level']} Comm {res['community_id']}")

    print(f"\nIndexing complete. Final reports saved to {REPORT_FILE}")

if __name__ == "__main__":
    build_hierarchical_index()