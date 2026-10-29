const d=$('Parse full and incremental diffs').first().json,g=$('Fetch pinned Git commits').first().json;
const chunks=$('Chunk source with line ranges').all().flatMap(i=>i.json.chunks);
const batches=d.batches.length?d.batches:[{paths:[],patch:''}];
const output=[];
for(const [index,b] of batches.entries()){const changed=parseDiff(b.patch);const local=b.paths.flatMap(path=>chunks.filter(c=>c.path===path&&(changed[path]?.RIGHT||[]).some(n=>n>=c.start&&n<=c.end)).slice(0,3));
 for(const path of b.paths)if(!chunks.some(c=>c.path===path)){const text=await git(g.root,['show',g.merge_base+':'+path],{optional:true});if(text&&!secretPattern.test(text))local.push({path,start:1,end:text.split('\n').length,text:text.slice(0,10000),head:g.merge_base,revision_role:'before'});}
 const terms=[...new Set(b.patch.split(/(?=^diff --git )/m).flatMap(section=>[...new Set(section.match(/[A-Za-z_][A-Za-z_0-9]{2,}/g)||[])].slice(0,35)))].slice(0,120);
 const query=(b.paths.join(' ')+' '+terms.join(' ')).slice(0,1000);
 output.push({json:{...b,index,local,query,semantic_query:utf8Prefix(query,DENSE_INPUT_BYTES),terms,filter:scope(g.repo,g.head)}});
}
return output;
