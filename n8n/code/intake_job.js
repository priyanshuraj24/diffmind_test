const event=$('Verify signature and route events').first().json;
const pr=$('Fetch incoming PR').first().json;
if(event.command){const p=$input.first().json.permission;if(!['admin','maintain','write'].includes(p))throw new Error('Command requires repository write permission');}
if(pr.state!=='open' || pr.draft)return [];
return [{json:{...event,head:pr.head.sha,installation_id:$('Find App installation').first().json.id,kind:event.command?'manual:'+event.delivery:'review',id:crypto.randomUUID()}}];
