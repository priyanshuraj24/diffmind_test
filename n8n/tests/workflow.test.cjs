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
