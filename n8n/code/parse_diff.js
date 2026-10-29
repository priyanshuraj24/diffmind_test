const g=$('Fetch pinned Git commits').first().json, rules=$('Read trusted repository rules').first().json;
const paths=(await git(g.root,['diff','--name-only','-z','--no-renames',g.analysis_base,g.head])).split('\0').filter(p=>eligible(p,rules.exclude));
const full=await git(g.root,['diff','--no-ext-diff','--no-textconv','--no-renames','--unified=5',g.merge_base,g.head]);
const locations=parseDiff(full),batches=[],skipped=[];let batch={paths:[],patch:''};
for(const path of paths){const patch=await git(g.root,['diff','--no-ext-diff','--no-textconv','--no-renames','--unified=5',g.analysis_base,g.head,'--',path]);
 if(patch.length>40000||secretPattern.test(patch)){skipped.push({path,reason:patch.length>40000?'diff_budget':'possible_secret'});continue;}
 if(batch.patch.length+patch.length>40000||batch.paths.length>=6){batches.push(batch);batch={paths:[],patch:''};}batch.paths.push(path);batch.patch+=patch+'\n';}
if(batch.paths.length)batches.push(batch);
for(const b of batches.slice(12))for(const path of b.paths)skipped.push({path,reason:'batch_budget'});
return [{json:{locations,batches:batches.slice(0,12),skipped,changed_paths:paths}}];
