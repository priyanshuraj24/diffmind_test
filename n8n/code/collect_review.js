const rows=$input.all().map(i=>i.json),ctx=$('Prepare review context').first().json,g=$('Fetch pinned Git commits').first().json;
const chunks=$('Chunk source with line ranges').first().json;
const findings=[...new Map(rows.flatMap(r=>r.findings||[]).map(f=>[f.fingerprint,f])).values()].slice(0,5);
return [{json:{head:ctx.job.head,summary:rows.map(r=>r.summary).join('\n\n'),findings,incremental:g.incremental,
 traces:rows.map(r=>r.trace),usage:rows.flatMap(r=>r.usage||[]),skipped:[...chunks.skipped,...$('Parse full and incremental diffs').first().json.skipped],chunks:chunks.total_chunks,index:$('Require complete index').first().json}}];
