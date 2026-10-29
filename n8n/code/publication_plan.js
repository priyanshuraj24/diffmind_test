const job=$('Claim next review job').first().json,ctx=$('Prepare review context').first().json;
const result=$('Load saved publication intent').first().json.result;
function pages(name){const rows=$(name).all().flatMap(i=>i.json.body??i.json);if(rows.length>=10000)throw new Error('GitHub comment pagination budget exceeded');return rows.filter(r=>r.id);}
const reviews=pages('Fetch existing PR reviews'),comments=pages('Fetch existing inline comments'),timeline=pages('Fetch existing summary comments');
const config=JSON.parse(fs.readFileSync('/home/node/.n8n-files/diffmind-native-config.json','utf8'));
const own=c=>c.user?.login===config.bot_login && c.user?.type==='Bot';
const marker='<!-- diffmind:n8n:review:'+job.id+' -->',summaryMarker='<!-- diffmind:n8n:summary -->';
const known=new Set((ctx.state.findings||[]).map(f=>f.fingerprint));
for(const c of comments.filter(own))for(const f of result.findings)if(c.body.includes('<!-- diffmind:n8n:finding:'+f.fingerprint+' -->'))known.add(f.fingerprint);
const fresh=result.findings.filter(f=>!known.has(f.fingerprint));
const inline=fresh.map(f=>{const evidence=f.evidence.map(e=>'- ['+e.evidence_id+' '+e.path+':'+e.start+'](https://github.com/'+job.repo+'/blob/'+e.head+'/'+e.path+'#L'+e.start+')').join('\n');
 let body='**['+f.severity+'] '+f.title+'**\n\n'+f.body+'\n\nScenario: '+f.scenario+'\n\nEvidence:\n'+evidence+'\n\n<!-- diffmind:n8n:finding:'+f.fingerprint+' -->';
 if(typeof f.suggestion==='string'&&f.side==='RIGHT'&&!f.suggestion.includes('```'))body+='\n\n```suggestion\n'+f.suggestion+'\n```';
 return {path:f.path,line:f.line,side:f.side,body};});
const summary=timeline.find(c=>own(c)&&c.body.includes(summaryMarker));
let body=summaryMarker+'\n## DiffMind n8n review\n\nReviewed `'+job.head.slice(0,12)+'` · '+(result.incremental?'Incremental':'Full')+' review\n\n'+result.summary+'\n\n**Retrieval:** '+result.chunks+' indexed chunks; exact, BM25 and semantic search completed for '+result.traces.length+' batches.\n\n**Findings:** '+fresh.length+' new; '+(result.findings.length-fresh.length)+' already reported. Tests were not executed. Existing threads remain open for human confirmation.';
if(result.skipped.length)body+='\n\n**Partial coverage:**\n'+result.skipped.slice(0,25).map(s=>'- `'+s.path+'`: '+s.reason).join('\n');
return [{json:{result,review_body:{commit_id:job.head,event:'COMMENT',body:marker,comments:inline},publish_inline:!!inline.length&&!reviews.some(r=>own(r)&&r.body.includes(marker)),summary_id:summary?.id||null,summary_body:{body}}}];
