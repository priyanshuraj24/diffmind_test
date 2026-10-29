const r=$input.first().json,context=$('Fuse rankings and build evidence').item.json;
if(r.choices?.[0]?.finish_reason!=='stop')throw new Error('Incomplete DeepSeek verification');
const output=JSON.parse(r.choices[0].message.content),accepted=[],rejected=[];
if(typeof output.summary!=='string'||!Array.isArray(output.findings)||secretPattern.test(JSON.stringify(output)))throw new Error('Invalid or unsafe verified output');
const all=$('Read tracked source blobs').first().json.files,g=$('Fetch pinned Git commits').first().json;
for(const f of output.findings){const locations=context.context.commentable_lines[f.path];const ids=new Set(f.evidence_ids||[]);
 if(!locations||!['RIGHT','LEFT'].includes(f.side)||!Number.isInteger(f.line)||!locations[f.side].includes(f.line)) {rejected.push({title:f.title,reason:'invalid_diff_line'});continue;}
 const evidence=context.context.evidence.filter(e=>ids.has(e.evidence_id));
 if(!ids.size||evidence.length!==ids.size||!evidence.some(e=>e.path===f.path)){rejected.push({title:f.title,reason:'invalid_evidence'});continue;}
 if(!['high','medium','low'].includes(f.severity)||!['correctness','security','reliability','performance'].includes(f.category)||!['title','body','scenario'].every(k=>typeof f[k]==='string')){rejected.push({title:f.title,reason:'invalid_schema'});continue;}
 const source=f.side==='RIGHT'?(all.find(x=>x.path===f.path)?.text||''):git(g.root,['show',g.merge_base+':'+f.path],{optional:true});
 const anchor=(source.split('\n')[f.line-1]||f.title).trim();
 accepted.push({...f,fingerprint:sha(f.path+':'+f.category+':'+anchor).slice(0,24),evidence:evidence.map(({path,start,end,head,evidence_id})=>({path,start,end,head,evidence_id}))});
}
return [{json:{summary:output.summary,findings:accepted.slice(0,5),rejected,trace:context.trace,usage:[$('Parse draft findings').item.json.usage,r.usage]}}];
