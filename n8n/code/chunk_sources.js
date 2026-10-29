const g=$('Fetch pinned Git commits').first().json,source=$('Read tracked source blobs').first().json;
const chunks=[],skipped=[...source.skipped];
for(const file of source.files){const lines=file.text.split('\n');let start=0,symbol='module';
 while(start<lines.length){let end=start,body='';
  const match=lines[start].match(/(?:def|function|class|interface|struct|func|fn)\s+([\w]+)/);if(match)symbol=match[1];
  while(end<lines.length && end-start<32 && (body.length+lines[end].length<1100 || end===start)){
   if(end>start && /^\s*(?:export\s+)?(?:async\s+)?(?:def|function|class|interface|struct|func|fn)\s+/.test(lines[end]))break;
   body+=lines[end]+'\n';end++;
  }
  if(body.trim() && body.length<=1400){const id=sha(g.repo+':'+g.head+':'+file.path+':'+start+':'+body).slice(0,32);chunks.push({id:id.slice(0,8)+'-'+id.slice(8,12)+'-'+id.slice(12,16)+'-'+id.slice(16,20)+'-'+id.slice(20),repo:g.repo,head:g.head,path:file.path,start:start+1,end,symbol,text:body,search_text:file.path+'\n'+symbol+'\n'+body});}
  else if(body.trim())skipped.push({path:file.path,reason:'oversized_line',line:start+1});start=Math.max(end,start+1);
 }
}
if(chunks.length>30000)throw new Error('Index exceeds 30000 chunk budget; configure exclusions');
// Emit bounded batches. Even an empty repository retains a sentinel so the workflow can summarize it.
const groups=[];for(let i=0;i<chunks.length;i+=24)groups.push({json:{chunks:chunks.slice(i,i+24),total_chunks:chunks.length,skipped}});
return groups.length?groups:[{json:{chunks:[],total_chunks:0,skipped}}];
