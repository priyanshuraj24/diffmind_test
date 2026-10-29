const g=$('Fetch pinned Git commits').first().json;
const batches=$('Chunk source with line ranges').all().map(i=>i.json);
const chunks=batches.flatMap(b=>b.chunks);
// Include the model/chunk policy and every complete embedding input. A matching
// count alone cannot establish that the right data is stored for this revision.
const fingerprint=sha(JSON.stringify(['bge-small-en-v1.5:bm25:bytes450:v1',chunks.map(c=>[c.id,c.search_text])]));
const directory=g.root+'/diffmind-index-manifests';
const manifest_path=directory+'/'+g.head+'.json';
let saved=null;
try{saved=JSON.parse(fs.readFileSync(manifest_path,'utf8'));}catch{}
return [{json:{expected:chunks.length,fingerprint,directory,manifest_path,
 manifest_matches:saved?.fingerprint===fingerprint && saved?.expected===chunks.length}}];
