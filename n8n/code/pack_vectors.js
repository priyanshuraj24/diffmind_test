const batch=$('Index chunk batches').item.json;
const dense=$('Generate document embeddings').item.json,sparse=$('Generate lexical document vectors').item.json;
if(dense.vectors.length!==batch.chunks.length || sparse.vectors.length!==batch.chunks.length)throw new Error('Embedding count mismatch');
return [{json:{points:batch.chunks.map((c,i)=>({id:c.id,vector:{dense:dense.vectors[i],bm25:sparse.vectors[i]},payload:c})),embedded:batch.chunks.length-dense.cached,reused:dense.cached}}];
