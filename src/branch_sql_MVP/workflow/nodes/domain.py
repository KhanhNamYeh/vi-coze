"""Deterministic adapters. LLM calls live exclusively in the LLM node."""
from ...online.candidate_selection import select_best_candidate
from ...offline.event_index import load_event_index
from ...online.sag_retrieval import retrieve_seed_events, expand_event_neighborhood
from ...online.context_builder import select_evidence_bundle


def events(inputs, config, **kwargs):
    index = load_event_index(inputs['event_index_path'])
    items = inputs['items']
    if not config.get('use_events', True):
        return {'items': items}
    seeds = retrieve_seed_events(inputs['question'], items, index, top_k=int(config.get('event_top_k', 8)))
    expanded = expand_event_neighborhood(seeds, index,
        hops=int(config.get('event_hops', 1)) if config.get('expand_events', True) else 0,
        node_budget=int(config.get('event_node_budget', 24)), token_budget=int(config.get('event_token_budget', 1800)))
    return {'items': [*items, *expanded], 'seeds': seeds}


def evidence_filter(inputs, config, **kwargs):
    items = inputs['items']
    if 'selected_ids' in inputs:
        by_id = {item['id']: item for item in items}
        selected = [by_id[key] for key in dict.fromkeys(inputs['selected_ids']) if key in by_id]
        selected = (selected or items)[:int(config.get('max_items', 24))]
        # The selector picks *which* evidence is relevant; the budget still caps
        # how much of it reaches the prompt.
        selected, trace = select_evidence_bundle(selected, token_budget=int(config.get('token_budget', 5000)))
    else:
        selected, trace = select_evidence_bundle(items, token_budget=int(config.get('token_budget', 5000)))
    return {'items': selected, 'trace': trace,
        'text': '\n\n'.join(f"[{i['kind'].upper()} id={i['id']} source={i['source']}]\n{i['text']}" for i in selected)}


def branch(inputs, config, **kwargs):
    operation = config.get('operation', 'route')
    if operation == 'repair':
        observation = inputs['observation']
        again = observation['status'] not in {'success','empty_result'} and inputs['iteration'] < config['max_repairs']
        return {'route': 'repair' if again else 'done'}
    if operation == 'answer':
        return {'route': 'answer' if inputs.get('mode') == 'answer' else 'sql'}
    return {'route': str(inputs.get('route', config.get('route', '')))}


def merge(inputs, config, *, state=None, **kwargs):
    values = (state or {}).get('node_outputs', {})
    for source in config['sources']:
        if source in values:
            return values[source]
    # Isolated node debugging has no upstream state, so accept the branch output
    # supplied directly as an input instead.
    for source in config['sources']:
        if source in inputs:
            return inputs[source]
    raise ValueError('No selected branch output; cần một trong: ' + ', '.join(config['sources']))


def candidate(inputs, config, **kwargs):
    prediction = dict(inputs['prediction'])
    generation = inputs.get('generation')
    if generation:
        usage=generation.get('usage',{})
        prediction.update(model=generation.get('model',''), latency_seconds=generation.get('latency',0), input_tokens=usage.get('input_tokens',0), output_tokens=usage.get('output_tokens',0), prompt_version='workflow-llm-v1')
    if not isinstance(prediction, dict) or not prediction.get('sql'):
        raise ValueError('Candidate requires SQL prediction')
    candidate_id = str(inputs.get('candidate_id', config.get('candidate_id', 'candidate_1')))
    observation = inputs.get('observation')
    if observation is not None:
        observation = {**observation, 'candidate_id': candidate_id}
    return {'candidate_id': candidate_id,
        'prediction': prediction, 'observation': observation,
        'continue': bool(config.get('continue', False))}


def candidate_select(inputs, config, **kwargs):
    candidates = inputs['candidates']
    if not candidates:
        raise ValueError('No candidates')
    requested = inputs.get('candidate_id')
    chosen = next((item for item in candidates if item['candidate_id'] == requested), None)
    best = select_best_candidate(candidates)
    if chosen is None or ((best.get('observation') or {}).get('status') in {'success','empty_result'} and
                          (chosen.get('observation') or {}).get('status') not in {'success','empty_result'}):
        chosen = best
    return {**chosen, 'candidates': candidates}


def strategies(inputs, config, **kwargs):
    maximum = int(config.get('max_candidates', 3))
    count = max(1, min(maximum, int(inputs['candidate_count']), 3))
    return {'items': ['join_first','aggregation_first','literal_first'][:count]}


def answer_guard(inputs, config, **kwargs):
    observation = inputs['observation']
    if observation['status'] not in {'success','empty_result'}:
        raise ValueError('Không diễn giải SQL lỗi: ' + str(observation.get('error')))
    return {'observation': observation}


def result(inputs, config, **kwargs):
    return inputs
