const plan=$('Plan revision index reuse').first().json;
if($json.result.count!==plan.expected)throw new Error('Index count mismatch');
// Written only after Qdrant confirms every chunk. Partial runs never become hits.
fs.mkdirSync(plan.directory,{recursive:true});
const temporary=plan.manifest_path+'.'+crypto.randomUUID()+'.tmp';
fs.writeFileSync(temporary,JSON.stringify({fingerprint:plan.fingerprint,expected:plan.expected}),{mode:0o600});
fs.renameSync(temporary,plan.manifest_path);
const reused=plan.manifest_matches && $('Check reusable revision index').first().json.result.count===plan.expected;
return [{json:{indexed:plan.expected,reused_revision:reused,embedding_batches:reused?0:Math.ceil(plan.expected/128)}}];
