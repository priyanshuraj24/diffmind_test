const job=$('Claim next review job').first().json, pr=$('Fetch current PR').first().json;
const state=$('Load previous review state').first().json;
const current=pr.head.sha===job.head && pr.state==='open' && !pr.draft && !state.paused;
return [{json:{job,pr,state,current}}];
