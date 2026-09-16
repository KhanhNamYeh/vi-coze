# M0 baseline: node/state inventory

## Baseline

The existing MVP regression suite was run before introducing the shared workflow layer:

```text
python -m pytest src/branch_sql_MVP/tests/test_text2sql_benchmark.py \
  src/branch_sql_MVP/tests/test_studio.py \
  src/branch_sql_MVP/tests/test_fresh_setup.py -q
```

The test suite requires a writable pytest temp directory on Windows; use `--basetemp=.test-tmp/<unique>` when the default temp root is denied. The baseline tests must remain green after every migration step.

## Existing mapping

| Existing node/function | Shared node type | Inputs | Outputs | Used by |
|---|---|---|---|---|
| `build_full_context` | `context_builder(mode=full)` | question, evidence, schema, business | text, evidence_items, stats | P1, G1 full |
| `build_linked_context` | `context_builder(mode=linked)` | question, evidence, schema, retrieval config | text, evidence_items, trace | B4, B5, B6, G1 |
| `retrieve_seed_events` | `event_seeds` | question, evidence_items, event index | seed IDs, trace | B5, B6, G1 |
| `expand_event_neighborhood` | `event_expansion` | seed IDs, event index, budgets | events, trace | B5, B6, G1 |
| `select_contextual_evidence` | `llm` instance (`response_format=json`) | question, evidence items | selected items, usage | B5, B6, optional G1 |
| `generate_sql_candidate` | `llm` instance (`response_format=json`) | question, context, strategy | SQL prediction, usage | all online scenarios |
| `execute_readonly_sql` | `sql_executor` | database path, SQL, limits | observation | B6, G1 |
| `repair_sql_candidate` | `llm` instance (`response_format=json`) | question, context, SQL, observation | repaired SQL prediction | B6 |
| `select_candidate_with_model` | `llm` instance (`response_format=json`) | question, candidates, observations | candidate ID, reason | G1 |
| `select_best_candidate` | `candidate_selector` | candidates + observations | selected candidate | B6, fallback G1 |
| `decide_workflow_route` | `llm` instance (`response_format=json`) | question, difficulty | route, candidate count | G1 |
| offline `preprocess/extract/link/chunk/embed/graph/index` | offline adapter node | source/doc/config | artifact refs + status | offline pipeline |

The existing builders duplicate node closures. M1 introduces the shared contracts/registry without changing these builders yet; M3 migrates them progressively.

## Settings consumers

`settings.py` is the canonical model. `paths`, `preprocess`, `chunk`, `embedding`, `graph`, `index`, `retrieval`, `api`, `llm` and `eval` are validated there. `eval` is benchmark-only and must not be required by fresh user datasets. `api` and `llm` are used by online and chat calls; `graph` is used by offline graph extraction; `index` and `retrieval` are used by offline indexing and online retrieval. The new workflow layer must snapshot effective values per run and never persist secrets.
