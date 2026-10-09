import json

from harness.resource_usage import ResponseUsage,resource_summary,sum_usage,usage_from_logs


def test_sse_usage_is_cumulative_not_duplicated_and_reasoning_not_added():
    tracker=ResponseUsage(b'{"messages":[]}')
    event={'type':'response.completed','response':{'usage':{'input_tokens':100,'output_tokens':20,
        'input_tokens_details':{'cached_tokens':80},'output_tokens_details':{'reasoning_tokens':5}}}}
    stream=('data: '+json.dumps(event)+'\n\n')*2+'data: [DONE]\n\n'
    for offset in range(0,len(stream),7):tracker.feed(stream[offset:offset+7].encode())
    result=tracker.finish()
    assert result['measurement']=='reported'
    assert result['total_tokens']==120
    assert result['cached_input_tokens']==80
    assert result['reasoning_output_tokens']==5


def test_estimate_stream_handles_split_unicode_and_tool_arguments():
    tracker=ResponseUsage('中文abcd'.encode())
    stream=('data: '+json.dumps({'choices':[{'delta':{'content':'中文','tool_calls':[
        {'function':{'arguments':'abcd'}}]}}]},ensure_ascii=False)+'\n\n').encode()
    for byte in stream:tracker.feed(bytes([byte]))
    value=tracker.finish()
    assert value['measurement']=='estimated'
    assert (value['input_tokens'],value['output_tokens'],value['total_tokens'])==(3,3,6)


def test_partial_usage_and_pretty_nonstream_json():
    tracker=ResponseUsage(b'abcdefgh')
    tracker.feed(json.dumps({'usage':{'prompt_tokens':10},'choices':[{'message':{'content':'abcd'}}]},indent=2).encode())
    result=tracker.finish()
    assert result['measurement']=='mixed'
    assert result['total_tokens']==11


def test_historical_usage_unknown_is_not_zero_and_cli_usage_recovers(tmp_path):
    assert usage_from_logs(tmp_path)['total_tokens'] is None
    (tmp_path/'stdout.log').write_text(json.dumps({'type':'turn.completed','usage':{
        'input_tokens':100,'cached_input_tokens':80,'output_tokens':20}})+'\n')
    assert usage_from_logs(tmp_path)['total_tokens']==120
    (tmp_path/'model_gateway_audit.jsonl').write_text(json.dumps({'kind':'model_usage','token_usage':{
        'input_tokens':8,'output_tokens':2,'total_tokens':10,'measurement':'estimated'}})+'\n')
    assert usage_from_logs(tmp_path)['total_tokens']==10 # prefer gateway, do not double count CLI


def test_summary_keeps_unknown_runs_out_of_numeric_denominators():
    summary=resource_summary([{'resource_usage':{'agent_seconds':4,'tokens':sum_usage([])}},
        {'resource_usage':{'wall_seconds':10,'agent_seconds':6,'tokens':{'measurement':'reported','total_tokens':20}}}])
    assert summary['agent_seconds']['mean']==5
    assert summary['wall_seconds']['observed_runs']==1
    assert summary['total_tokens']['mean']==20
