"""Visible linking/retrieval stages using the original evidence algorithms."""
from ...offline.schema_catalog import load_schema_catalog
from ...online import context_builder as business


def schema_link(inputs, config, **kwargs):
    catalog=load_schema_catalog(inputs['schema_catalog_path'])
    items=business.link_schema_elements(inputs['question'],catalog,
        table_k=int(config.get('table_k',5)),column_k=int(config.get('column_k',12)),
        min_score=float(config.get('schema_min_score',.12)))
    return {'items':items,'database_id':catalog['database_id']}


def value_link(inputs, config, **kwargs):
    catalog=load_schema_catalog(inputs['schema_catalog_path'])
    return {'items':business.link_literal_values(inputs['question']+' '+inputs.get('evidence',''),catalog,
        top_k=int(config.get('value_k',10)),fuzzy_threshold=float(config.get('value_fuzzy_threshold',.84)))}


def business_retrieval(inputs, config, *, settings, **kwargs):
    return {'items':business.retrieve_hybrid_evidence(inputs['question'],knowledge_id=inputs['knowledge_id'],
        doc_id=inputs['doc_id'],settings=settings,parameters=config)}


def example_retrieval(inputs, config, **kwargs):
    index=business.load_optional_example_index(inputs.get('example_index_path'))
    return {'items':business.retrieve_similar_examples(inputs['question'],index,
        database_id=inputs['database_id'],top_k=int(config.get('example_k',3))),
        'corpus':'train' if index else 'unavailable'}


def linked_evidence(inputs, config, **kwargs):
    bird={'id':'bird-evidence:'+inputs['database_id'],'kind':'business',
          'text':"BIRD evidence: "+(inputs.get('evidence') or 'Không có'),
          'source':'bird-case-evidence','score':100.0,'metadata':{'provided_with_question':True}}
    selected,trace=business.select_evidence_bundle([bird,*inputs['schema'],*inputs['values'],*inputs['business'],*inputs['examples']],
        token_budget=int(config.get('token_budget',5000)))
    text='\n\n'.join(business._render_item(item) for item in selected)
    trace.append({'summary':{'schema':len(inputs['schema']),'value':len(inputs['values']),
        'business':len(inputs['business']),'example':len(inputs['examples']),'selected':len(selected),
        'estimated_tokens':business.estimate_tokens(text),'example_corpus':inputs['example_corpus']}})
    return {'text':text,'items':selected,'trace':trace}
