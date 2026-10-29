const g=$('Fetch pinned Git commits').first().json,source=$('Read tracked source blobs').first().json;
const chunks=[],skipped=[...source.skipped];
for(const file of source.files){
 const lines=file.text.match(/[^\n]*\n|[^\n]+$/g)||[];
 let lineNumber=1,offset=0,symbol='module',body='',start=1,startOffset=0,startColumn=1,end=1,header='';
 const flush=()=>{
  if(!body)return;
  const search_text=header+body;
  if(Buffer.byteLength(search_text,'utf8')>DENSE_INPUT_BYTES)throw new Error('Embedding byte budget exceeded');
  const id=sha(g.repo+':'+g.head+':'+file.path+':'+startOffset+':'+body).slice(0,32);
  chunks.push({id:id.slice(0,8)+'-'+id.slice(8,12)+'-'+id.slice(12,16)+'-'+id.slice(16,20)+'-'+id.slice(20),repo:g.repo,head:g.head,path:file.path,start,end,start_column:startColumn,start_offset:startOffset,end_offset:startOffset+body.length,symbol,text:body,search_text});
  body='';
 };
 for(const line of lines){
  const match=line.match(/^\s*(?:export\s+)?(?:async\s+)?(?:def|function|class|interface|struct|func|fn)\s+([\w]+)/);
  if(match){flush();symbol=match[1];}
  if(body && lineNumber-start>=32)flush();
  let remaining=line,column=1;
  while(remaining){
   if(!body){start=lineNumber;startOffset=offset;startColumn=column;header=utf8Prefix(file.path,160)+'\n'+utf8Prefix(symbol,64)+'\n';}
   const available=DENSE_INPUT_BYTES-Buffer.byteLength(header+body,'utf8');
   // Prefer whole lines; fragment only a line which cannot fit on its own.
   if(body && Buffer.byteLength(remaining,'utf8')>available){flush();continue;}
   const piece=utf8Prefix(remaining,available);
   if(!piece)throw new Error('Embedding prefix leaves no room for source');
   body+=piece;end=lineNumber;remaining=remaining.slice(piece.length);offset+=piece.length;column+=piece.length;
   if(remaining)flush();
  }
  lineNumber++;
 }
 flush();
}
if(chunks.length>30000)throw new Error('Index exceeds 30000 chunk budget; configure exclusions');
const groups=[];for(let i=0;i<chunks.length;i+=24)groups.push({json:{chunks:chunks.slice(i,i+24),total_chunks:chunks.length,skipped}});
return groups.length?groups:[{json:{chunks:[],total_chunks:0,skipped}}];
