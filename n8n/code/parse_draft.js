const r=$input.first().json;
if(r.choices?.[0]?.finish_reason!=='stop')throw new Error('Incomplete DeepSeek review');
const output=JSON.parse(r.choices[0].message.content);
if(typeof output.summary!=='string'||!Array.isArray(output.findings)||secretPattern.test(JSON.stringify(output)))throw new Error('Invalid or unsafe review output');
return [{json:{candidate:output,usage:r.usage}}];
