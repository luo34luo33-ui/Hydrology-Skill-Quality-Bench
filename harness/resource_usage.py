"""Content-free token accounting; estimates are explicitly heuristic."""
import json
import math
from pathlib import Path


def text_weight(text):
    # CJK characters are closer to one token; other characters use chars/4.
    return sum(1 if '\u3400' <= c <= '\u9fff' else .25 for c in text)


def reported_usage(value):
    if not isinstance(value, dict):return None
    def number(*keys):
        for key in keys:
            v=value.get(key)
            if isinstance(v,int) and not isinstance(v,bool) and v>=0:return v
        return None
    prompt=number('input_tokens','prompt_tokens');output=number('output_tokens','completion_tokens')
    if prompt is None and output is None:return None
    cached=value.get('input_tokens_details',value.get('prompt_tokens_details',{})) or {}
    details=value.get('output_tokens_details',value.get('completion_tokens_details',{})) or {}
    if not isinstance(cached,dict):cached={}
    if not isinstance(details,dict):details={}
    return {'input_tokens':prompt,'output_tokens':output,
        'cached_input_tokens':number('cached_input_tokens','prompt_cache_hit_tokens') if number('cached_input_tokens','prompt_cache_hit_tokens') is not None else cached.get('cached_tokens'),
        'reasoning_output_tokens':number('reasoning_output_tokens') if number('reasoning_output_tokens') is not None else details.get('reasoning_tokens')}


class ResponseUsage:
    """Parse streamed JSON/SSE incrementally; retain counts, never payload text."""
    def __init__(self,body):
        self.input_estimate=math.ceil(text_weight(body.decode('utf-8',errors='replace')))
        self.buffer=b'';self.output_weight=0.;self.reported=None;self.saw_delta=False;self.json_response=False;self.truncated=False

    def observe(self,event):
        if not isinstance(event,dict):return
        response=event.get('response')
        value=reported_usage(event.get('usage')) or reported_usage(response.get('usage') if isinstance(response,dict) else None)
        if value:self.reported=value # cumulative final usage; do not sum duplicate events
        kind=event.get('type','')
        if kind.endswith('.delta') and isinstance(event.get('delta'),str):
            self.saw_delta=True;self.output_weight+=text_weight(event['delta'])
        for choice in event.get('choices',[]) or []:
            message=choice.get('delta',choice.get('message',{}))
            for key in ['content','reasoning_content']:
                if isinstance(message.get(key),str):self.output_weight+=text_weight(message[key])
            for call in message.get('tool_calls',[]):
                argument=call.get('function',{}).get('arguments','')
                if isinstance(argument,str):self.output_weight+=text_weight(argument)
        if not self.saw_delta:
            for item in event.get('output',(response or {}).get('output',[]) if isinstance(response,dict) else []) or []:
                for part in item.get('content',[]):
                    if isinstance(part.get('text'),str):self.output_weight+=text_weight(part['text'])
                if isinstance(item.get('arguments'),str):self.output_weight+=text_weight(item['arguments'])

    def line(self,line):
        line=line.strip()
        if line.startswith(b'data:'):line=line[5:].strip()
        if not line or line==b'[DONE]':return
        try:self.observe(json.loads(line))
        except (ValueError,TypeError,AttributeError):pass

    def feed(self,chunk):
        self.buffer+=chunk
        if self.buffer.lstrip().startswith(b'{'):self.json_response=True
        if self.json_response:
            if len(self.buffer)>2*1024*1024:self.buffer=b'';self.truncated=True
            return
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1);self.line(line)
        if len(self.buffer)>2*1024*1024:self.buffer=b'';self.truncated=True # bounded, atypical oversized event

    def finish(self):
        self.line(self.buffer);self.buffer=b''
        values=self.reported or {}
        input_reported=values.get('input_tokens') is not None
        output_reported=values.get('output_tokens') is not None
        prompt=values.get('input_tokens') if input_reported else self.input_estimate
        output=values.get('output_tokens') if output_reported else math.ceil(self.output_weight)
        return {**values,'input_tokens':prompt,'output_tokens':output,'total_tokens':prompt+output,
            'measurement':'reported' if input_reported and output_reported else 'mixed' if input_reported or output_reported else 'estimated',
            'input_reported':input_reported,'output_reported':output_reported,
            'accounting_truncated':self.truncated,
            'estimation_method':'serialized request and emitted response text: CJK chars + other chars/4; includes repeated prompt history; invisible reasoning cannot be estimated'}


def sum_usage(usages):
    if not usages:return {'measurement':'unavailable','input_tokens':None,'output_tokens':None,'total_tokens':None,'requests_accounted':0}
    result={key:sum(u[key] for u in usages if isinstance(u.get(key),int)) if any(isinstance(u.get(key),int) for u in usages) else None
        for key in ['input_tokens','output_tokens','total_tokens','cached_input_tokens','reasoning_output_tokens']}
    kinds={u['measurement'] for u in usages}
    result.update(measurement=next(iter(kinds)) if len(kinds)==1 else 'mixed',requests_accounted=len(usages))
    result['accounting_truncated']=any(u.get('accounting_truncated',False) for u in usages)
    result['note']='Input totals include repeated context and cached tokens. Reasoning is included in reported output totals, not added again. Estimated output omits invisible reasoning. Unreported token use is not a billing statement.'
    return result


def usage_from_logs(task_dir):
    task_dir=Path(task_dir);gateway=task_dir/'model_gateway_audit.jsonl';usages=[]
    if gateway.is_file():
        for line in gateway.read_text(encoding='utf-8').splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('kind')=='model_usage':usages.append(event['token_usage'])
    if usages:return sum_usage(usages)
    stdout=task_dir/'stdout.log'
    if stdout.is_file():
        for line in stdout.read_text(encoding='utf-8',errors='replace').splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('type')=='turn.completed':
                value=reported_usage(event.get('usage'))
                if value and value['input_tokens'] is not None and value['output_tokens'] is not None:
                    usages.append({**value,'total_tokens':value['input_tokens']+value['output_tokens'],'measurement':'reported_cli'})
    return sum_usage(usages)


def resource_fields(row):
    usage=row.get('resource_usage',{});tokens=usage.get('tokens',{})
    return {'wall_seconds':usage.get('wall_seconds'),'agent_seconds':usage.get('agent_seconds'),
        **{key:tokens.get(key) for key in ['input_tokens','output_tokens','total_tokens']},
        'token_measurement':tokens.get('measurement','unavailable')}


def resource_summary(rows):
    fields=[resource_fields(row) for row in rows]
    return {**{key:{'observed_runs':len(values),'sum':sum(values) if values else None,'mean':sum(values)/len(values) if values else None}
        for key in ['wall_seconds','agent_seconds','total_tokens']
        for values in [[f[key] for f in fields if isinstance(f[key],(int,float))]]},
        'token_measurements':{kind:sum(f['token_measurement']==kind for f in fields) for kind in sorted({f['token_measurement'] for f in fields})}}
