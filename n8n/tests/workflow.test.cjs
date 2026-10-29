const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const common=fs.readFileSync(path.join(root,'code/_common.js'),'utf8');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
function refs(data){return name=>({first:()=>({json:data[name]}),item:{json:data[name]},all:()=>Array.isArray(data[name])?data[name].map(json=>({json})):[{json:data[name]}]});}
async function run(file,data={},input={},customRequire=require,helpers={}){
 const body=common+'\n'+fs.readFileSync(path.join(root,'code',file),'utf8');
 return new AsyncFunction('require','Buffer','$','$input','$json',body).call({helpers},customRequire,Buffer,refs(data),{first:()=>({json:input}),all:()=>[{json:input}]},input);
}
test('diff locations handle additions, context and deletions',async()=>{
 const output=await new AsyncFunction('require',common+"\nreturn parseDiff('diff --git a/x.py b/x.py\\n--- a/x.py\\n+++ b/x.py\\n@@ -3,2 +3,2 @@\\n-old\\n+new\\n context');")(require);
 assert.deepEqual(output['x.py'].LEFT,[3,4]);assert.deepEqual(output['x.py'].changed,[3]);
});
test('source policy excludes credentials and generated files',async()=>{
 const result=await new AsyncFunction('require',common+"\nreturn ['.env','x.pem','node_modules/a.js','../a.py','src/a.py'].map(p=>eligible(p));")(require);
 assert.deepEqual(result,[false,false,false,false,true]);
});

test('Git subprocesses yield to heartbeats and pass blob input without a shell',async()=>{
 let ticks=0,received;
 const timer=setInterval(()=>ticks++,5);
 const fake={execFile:(command,args,options,callback)=>{
  assert.equal(command,'git');assert(!args.some(a=>a.includes('private-test-token')));
  assert.equal(options.encoding,null);assert.equal(options.timeout,120000);
  assert.equal(options.env.GIT_TERMINAL_PROMPT,'0');
  return {stdin:{on(){},end(input){received=input;setTimeout(()=>callback(null,Buffer.from('blob output'),''),50);}}};
 }};
 const customRequire=name=>name==='child_process'?fake:require(name);
 try{
  const output=await new AsyncFunction('require','Buffer','$',common+"\nreturn await git('/repo',['cat-file','--batch'],{binary:true,input:'oid\\n'});")(customRequire,Buffer,refs({'Review installation token':{token:'private-test-token'}}));
  assert(ticks>0);assert.equal(received,'oid\n');assert(Buffer.isBuffer(output));assert.equal(output.toString(),'blob output');
 }finally{clearInterval(timer);}
});

test('Git failure diagnostics classify errors without leaking stderr credentials',async()=>{
 const fake={execFile:(command,args,options,callback)=>({stdin:{on(){},end(){queueMicrotask(()=>callback(Object.assign(new Error('private-test-token'),{code:128}),'',"fatal: Unable to create shallow.lock: File exists; private-test-token"));}}})};
 const call=new AsyncFunction('require','Buffer','$',common+"\nreturn await git('/repo',['fetch']);");
 await assert.rejects(call(name=>name==='child_process'?fake:require(name),Buffer,refs({'Review installation token':{token:'private-test-token'}})),error=>error.message.includes('repository lock contention')&&!error.message.includes('private-test-token'));
});

test('pinned Git fetches retain refs for cache negotiation',async()=>{
 const calls=[],head='a'.repeat(40),base='b'.repeat(40);
 const fake={execFile:(command,args,options,callback)=>({stdin:{on(){},end(){
  calls.push(args.slice(3));
  const output=args[3]==='rev-parse'?args[5].replace('^{commit}','')+'\n':args[3]==='merge-base'?base+'\n':'';
  queueMicrotask(()=>callback(null,output,''));
 }}})};
 const result=await run('fetch_git.js',{'Prepare review context':{job:{repo:'org/a',number:73,head,kind:'review'},pr:{base:{sha:base}},state:{}},'Review installation token':{token:'private-test-token'}},{},name=>name==='child_process'?fake:name==='fs'?{mkdirSync(){},existsSync(){return true;}}:require(name));
 assert.equal(result[0].json.merge_base,base);
 assert(calls.some(a=>a[0]==='update-ref'&&a[1]==='refs/diffmind/pr/73/head'&&a[2]===head));
 const fetch=calls.find(a=>a[0]==='fetch');
 assert(fetch.includes('+'+head+':refs/diffmind/pr/73/head'));
 assert(fetch.includes('+'+base+':refs/diffmind/pr/73/base'));
});
test('chunking preserves source line ranges',async()=>{
 const text='def first():\n    return 1\n\ndef second():\n    return 2\n';
 const result=await run('chunk_sources.js',{'Fetch pinned Git commits':{repo:'org/a',head:'a'.repeat(40)},'Read tracked source blobs':{files:[{path:'x.py',text}],skipped:[]}});
 const chunks=result.flatMap(x=>x.json.chunks);
 assert.equal(chunks.length,2);assert.equal(chunks[1].start,4);assert.equal(chunks[1].symbol,'second');
 assert.equal(chunks[0].text,text.split('\n').slice(0,3).join('\n')+'\n');
});
test('retrieval reserves evidence for every changed file',async()=>{
 const chunks=Array.from({length:35},(_,i)=>({path:'big.py',start:i+1,end:i+1,text:'helper '+i}));chunks.push({path:'refund.py',start:1,end:4,text:'require_positive_cents(amount)'});
 const patch='diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n@@ -1,1 +1,35 @@\n'+Array.from({length:35},(_,i)=>'+helper_'+i+'()').join('\n')+'\ndiff --git a/refund.py b/refund.py\n--- a/refund.py\n+++ b/refund.py\n@@ -1,1 +1,1 @@\n-require_positive_cents(amount)\n+# removed';
 const out=await run('retrieval_batches.js',{'Parse full and incremental diffs':{batches:[{paths:['big.py','refund.py'],patch}]},'Fetch pinned Git commits':{repo:'org/a',head:'a'.repeat(40)},'Chunk source with line ranges':[{chunks}]});
 assert(out[0].json.local.some(c=>c.path==='refund.py'));assert(out[0].json.terms.includes('require_positive_cents'));
});

test('embedding chunks include metadata in the bound and preserve long Unicode lines',async()=>{
 const file={path:'目录/'.repeat(90)+'types.ts',text:'function '+('LongIdentifier'.repeat(30))+'() {\n'+('甲🙂a_'.repeat(600))+'\nreturn 1;\n}\n'};
 const data={'Fetch pinned Git commits':{repo:'org/a',head:'a'.repeat(40)},'Read tracked source blobs':{files:[file],skipped:[]}};
 const chunks=(await run('chunk_sources.js',data)).flatMap(x=>x.json.chunks);
 assert.equal(chunks.map(c=>c.text).join(''),file.text);
 assert(chunks.every(c=>Buffer.byteLength(c.search_text,'utf8')<=450));
 assert.equal(new Set(chunks.map(c=>c.id)).size,chunks.length);
 for(const c of chunks){
  assert.equal(c.text,file.text.slice(c.start_offset,c.end_offset));
  assert.equal(c.start,file.text.slice(0,c.start_offset).split('\n').length);
  assert.equal(c.end,file.text.slice(0,c.end_offset-(c.text.endsWith('\n')?1:0)).split('\n').length);
 }
 assert(chunks.filter(c=>c.start===2).length>1);
 assert.deepEqual(chunks,(await run('chunk_sources.js',data)).flatMap(x=>x.json.chunks));
});

test('dense query is bounded independently of lexical query',async()=>{
 const p='深层目录/'.repeat(70)+'test.ts';
 const out=await run('retrieval_batches.js',{'Parse full and incremental diffs':{batches:[{paths:[p],patch:''}]},'Fetch pinned Git commits':{repo:'org/a',head:'a'.repeat(40)},'Chunk source with line ranges':[{chunks:[{path:p}]}]});
 assert(Buffer.byteLength(out[0].json.semantic_query)<=450);
 assert(out[0].json.query.length>out[0].json.semantic_query.length);
 assert(!out[0].json.semantic_query.includes('\ufffd'));
});

test('retrieval retains distinct fragments from the same source line',async()=>{
 const fragments=[0,200].map(start_offset=>({path:'x.ts',start:1,end:1,start_offset,head:'a'.repeat(40),text:'fragment '+start_offset}));
 const result=await run('fuse_context.js',{'Review diff batches':{local:fragments,paths:['x.ts'],patch:''},'Search semantic code context':{result:{points:[]}},'Search lexical code context':{result:{points:[]}},'Search exact symbols':{result:{points:[]}},'Prepare review context':{job:{repo:'org/a',head:'a'.repeat(40)},pr:{title:'test'},state:{}},'Parse full and incremental diffs':{locations:{'x.ts':{RIGHT:[1],LEFT:[]}}},'Read trusted repository rules':{instructions:''}});
 assert.equal(result[0].json.context.evidence.length,2);
});
test('validator rejects fabricated evidence and invalid diff lines',async()=>{
 const base={title:'Fault',body:'Details',path:'x.py',line:2,side:'RIGHT',severity:'high',category:'correctness',scenario:'Example',evidence_ids:['E1']};
 const input={choices:[{finish_reason:'stop',message:{content:JSON.stringify({summary:'Review',findings:[base,{...base,line:99},{...base,evidence_ids:['fake']}]})}}]};
 const out=await run('validate_findings.js',{'Fuse rankings and build evidence':{context:{commentable_lines:{'x.py':{RIGHT:[2],LEFT:[]}},evidence:[{path:'x.py',start:1,end:3,head:'a'.repeat(40),evidence_id:'E1'}]},trace:{}},'Read tracked source blobs':{files:[{path:'x.py',text:'one\ntwo\nthree'}]},'Fetch pinned Git commits':{},'Parse draft findings':{usage:{}}},input);
 assert.equal(out[0].json.findings.length,1);assert.equal(out[0].json.rejected.length,2);
});
test('all generated expressions and code nodes compile',()=>{
 const workflow=JSON.parse(fs.readFileSync(path.join(root,'workflow.json'),'utf8'));
 for(const n of workflow.nodes){
  function check(v){if(typeof v==='string'&&v.startsWith('={{ '))new Function('return ('+v.slice(4,-3)+')');else if(v&&typeof v==='object')Object.values(v).forEach(check);}check(n.parameters);
  if(n.type.endsWith('.code'))new AsyncFunction(n.parameters.jsCode);
 }
 assert(workflow.nodes.some(n=>n.name==='A job was claimed'));
 assert(!JSON.stringify(workflow).includes('/internal/run-once'));
});
