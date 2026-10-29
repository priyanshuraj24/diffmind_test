const ctx=$('Prepare review context').first().json, {job,pr,state}=ctx;
const root='/home/node/.n8n-files/diffmind-native/repos/'+sha(job.repo);
fs.mkdirSync(root,{recursive:true});
if(!fs.existsSync(root+'/HEAD'))git(root,['init','--bare']);
if(!/^[a-f0-9]{40}$/.test(job.head)||!/^[a-f0-9]{40}$/.test(pr.base.sha))throw new Error('Expected immutable Git SHA');
git(root,['fetch','--no-tags','--depth=100','https://github.com/'+job.repo+'.git',job.head,pr.base.sha]);
let base=git(root,['merge-base',job.head,pr.base.sha],{optional:true}).trim();
if(!base){git(root,['fetch','--no-tags','--deepen=1000','https://github.com/'+job.repo+'.git',job.head,pr.base.sha]);base=git(root,['merge-base',job.head,pr.base.sha]).trim();}
let incremental=false;
if(job.kind==='review' && state.last_head){const ancestor=git(root,['merge-base',state.last_head,job.head],{optional:true}).trim();incremental=ancestor===state.last_head;}
return [{json:{root,merge_base:base,analysis_base:incremental?state.last_head:base,incremental,head:job.head,repo:job.repo}}];
