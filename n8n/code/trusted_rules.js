const g=$('Fetch pinned Git commits').first().json,ctx=$('Prepare review context').first().json;
const raw=git(g.root,['show',ctx.pr.base.sha+':.diffmind.json'],{optional:true});
const rules=raw && raw.length<20000?JSON.parse(raw):{};
if(!Array.isArray(rules.exclude??[])||!(rules.exclude??[]).every(s=>typeof s==='string')||typeof(rules.instructions??'')!=='string')throw new Error('Invalid trusted repository rules');
return [{json:{exclude:rules.exclude||[],instructions:(rules.instructions||'').slice(0,12000)}}];
