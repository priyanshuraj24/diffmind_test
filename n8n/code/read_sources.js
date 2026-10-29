const g=$('Fetch pinned Git commits').first().json,rules=$('Read trusted repository rules').first().json;
const entries=git(g.root,['ls-tree','-rlz',g.head]).split('\0'),files=[],skipped=[];let bytes=0;
for(const entry of entries){if(!entry)continue;const tab=entry.indexOf('\t'),path=entry.slice(tab+1),[mode,type,oid,sizeString]=entry.slice(0,tab).trim().split(/\s+/),size=+sizeString;
 if(type!=='blob'||!['100644','100755'].includes(mode)||!eligible(path,rules.exclude))continue;
 if(size>250000||bytes+size>15000000||files.length>=10000){skipped.push({path,reason:'source_budget'});continue;}files.push({path,oid,size});bytes+=size;}
const data=git(g.root,['cat-file','--batch'],{binary:true,input:files.map(f=>f.oid+'\n').join('')});let cursor=0;const source=[];
for(const f of files){const stop=data.indexOf(10,cursor),size=+data.subarray(cursor,stop).toString().split(' ')[2],raw=data.subarray(stop+1,stop+1+size);cursor=stop+size+2;
 const text=raw.toString('utf8');if(raw.includes(0)||secretPattern.test(text)){skipped.push({path:f.path,reason:'binary_or_possible_secret'});continue;}source.push({path:f.path,text});}
return [{json:{files:source,skipped,bytes}}];
