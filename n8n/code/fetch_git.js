const ctx=$('Prepare review context').first().json, {job,pr,state}=ctx;
const root='/home/node/.n8n-files/diffmind-native/repos/'+sha(job.repo);
fs.mkdirSync(root,{recursive:true});
if(!fs.existsSync(root+'/HEAD'))await git(root,['init','--bare']);
if(!/^[a-f0-9]{40}$/.test(job.head)||!/^[a-f0-9]{40}$/.test(pr.base.sha)||!Number.isInteger(job.number)||job.number<1)throw new Error('Expected immutable Git SHA and PR number');
// Named refs make cached objects visible to fetch negotiation across reviews.
const targets=[[job.head,'refs/diffmind/pr/'+job.number+'/head'],[pr.base.sha,'refs/diffmind/pr/'+job.number+'/base']];
for(const [commit,ref] of targets){
 const cached=(await git(root,['rev-parse','--verify',commit+'^{commit}'],{optional:true})).trim();
 if(cached===commit)await git(root,['update-ref',ref,commit]);
}
const refspecs=targets.map(([commit,ref])=>'+'+commit+':'+ref);
await git(root,['fetch','--no-tags','--depth=100','https://github.com/'+job.repo+'.git',...refspecs]);
let base=(await git(root,['merge-base',job.head,pr.base.sha],{optional:true})).trim();
if(!base){await git(root,['fetch','--no-tags','--deepen=1000','https://github.com/'+job.repo+'.git',...refspecs]);base=(await git(root,['merge-base',job.head,pr.base.sha])).trim();}
let incremental=false;
if(job.kind==='review' && state.last_head){const ancestor=(await git(root,['merge-base',state.last_head,job.head],{optional:true})).trim();incremental=ancestor===state.last_head;}
return [{json:{root,merge_base:base,analysis_base:incremental?state.last_head:base,incremental,head:job.head,repo:job.repo}}];
