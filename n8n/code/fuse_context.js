const batch=$('Review diff batches').item.json;
const dense=$('Search semantic code context').item.json.result.points;
const sparse=$('Search lexical code context').item.json.result.points;
const exact=$('Search exact symbols').item.json.result.points;
const scores=new Map(),byId=new Map();
for(const list of [exact,sparse,dense])list.forEach((p,i)=>{scores.set(p.id,(scores.get(p.id)||0)+1/(61+i));byId.set(p.id,p.payload);});
const ranked=[...scores.keys()].sort((a,b)=>scores.get(b)-scores.get(a)).slice(0,15).map(id=>byId.get(id));
const selected=[],seen=new Set();let chars=0;
for(const item of [...batch.local,...ranked]){const key=item.path+':'+item.start+':'+item.head;if(seen.has(key)||chars+item.text.length>32000)continue;seen.add(key);chars+=item.text.length;selected.push({...item,evidence_id:'E'+(selected.length+1)});}
if(batch.paths.length && !selected.length)throw new Error('No retrieval evidence for changed code');
const ctx=$('Prepare review context').first().json,d=$('Parse full and incremental diffs').first().json;
const outputSchema={summary:'string',findings:[{title:'string',body:'string',path:'repository-relative path',line:'integer',side:'RIGHT or LEFT',severity:'high or medium or low',category:'security or correctness or reliability or performance',scenario:'concrete failure scenario',evidence_ids:['E1'],suggestion:'optional exact single-line replacement or null'}]};
const context={repository:ctx.job.repo,head:ctx.job.head,title:ctx.pr.title,description:(ctx.pr.body||'').slice(0,3000),patch:batch.patch,
 trusted_rules:$('Read trusted repository rules').first().json.instructions,evidence:selected,previous_findings:ctx.state.findings||[],
 commentable_lines:Object.fromEntries(batch.paths.map(p=>[p,d.locations[p]])),output_schema:outputSchema};
return [{json:{context,trace:{batch:batch.index,exact_candidates:exact.length,lexical_candidates:sparse.length,semantic_candidates:dense.length,evidence:selected.map(({path,start,end,head,evidence_id})=>({path,start,end,head,evidence_id}))}}}];
