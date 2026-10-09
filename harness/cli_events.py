"""Version-certified CLI event normalization; unrecognized streams fail audit closed."""
from __future__ import annotations
import json

class EventCounter:
    def __init__(self,cli,rounds=60,tools=120):
        if cli not in {'codex','opencode','qwen','codebuddy'}:raise ValueError('unknown CLI')
        self.cli=cli;self.round_limit=rounds;self.tool_limit=tools
        self.rounds=0;self.tools=0;self.seen=set();self.recognized=0;self.events=[]
        self.started=False
    def feed(self,line):
        try:d=json.loads(line)
        except ValueError:return []
        if not isinstance(d,dict):return []
        kinds=[];typ=d.get('type');item=d.get('item',{});part=d.get('part',{})
        if self.cli=='codex':
            if typ in {'thread.started','turn.started','turn.completed','turn.failed','item.started','item.completed','error'}:self.recognized+=1
            if typ in {'item.started','item.completed'} and item.get('type') in {'command_execution','mcp_tool_call','web_search','file_change'}:kinds.append(('tool',item.get('id')))
            if typ=='item.completed' and item.get('type') in {'reasoning','agent_message'}:kinds.append(('round',item.get('id')))
        elif self.cli=='opencode':
            if typ in {'step_start','step_finish','tool_use','text','reasoning','error'}:self.recognized+=1
            if typ=='step_start':kinds.append(('round',part.get('id') or d.get('timestamp')))
            if typ=='tool_use':kinds.append(('tool',part.get('callID') or part.get('id')))
        else:
            if typ in {'system','assistant','user','result','tool_use','tool_result'}:self.recognized+=1
            if typ=='assistant':
                message=d.get('message',{});kinds.append(('round',message.get('id') or d.get('uuid')))
                content=message.get('content',[])
                if isinstance(content,list):
                    for block in content:
                        if isinstance(block,dict) and block.get('type')=='tool_use':kinds.append(('tool',block.get('id')))
            if typ=='tool_use':kinds.append(('tool',d.get('id')))
        added=[]
        if kinds or typ in ['thread.started','step_start'] or (self.cli in {'qwen','codebuddy'} and typ=='system' and d.get('subtype')=='init'):self.started=True
        for kind,identity in kinds:
            # Missing identifiers cannot be reliably deduplicated; reject certification.
            if identity is None:raise ValueError('event lacks stable identity')
            key=(kind,str(identity))
            if key in self.seen:continue
            self.seen.add(key)
            if kind=='round':self.rounds+=1
            else:self.tools+=1
            event={'kind':kind,'id':str(identity),'rounds':self.rounds,'tools':self.tools};self.events.append(event);added.append(event)
        return added
    @property
    def exhausted(self):return self.rounds>=self.round_limit or self.tools>=self.tool_limit
    def summary(self):return {'agent_rounds':self.rounds,'tool_calls':self.tools,'budget_exhausted':self.exhausted,'stream_assessable':bool(self.recognized),'agent_started':self.started}

def command(cli,model,effort,prompt):
    if not model:raise ValueError('explicit frozen model is required')
    if cli=='codex':return ['codex','exec','--json','--ephemeral','--ignore-rules','--skip-git-repo-check','--dangerously-bypass-approvals-and-sandbox','-m',model,'-c','model_reasoning_effort='+json.dumps(effort),prompt]
    if cli=='opencode':return ['opencode','run','--pure','--auto','--format','json','--model',model,'--variant',effort,prompt]
    if cli=='qwen':return ['qwen','-p',prompt,'--advisor','off','--output-format','stream-json','--model',model,'--yolo','--max-session-turns','60','--max-tool-calls','120']
    raise ValueError(cli)
