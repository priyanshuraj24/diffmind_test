// Bundled into the relevant n8n Code nodes; no remote review worker is called.
const crypto = require('crypto');
const fs = require('fs');
const cp = require('child_process');
const sha = s => crypto.createHash('sha256').update(s).digest('hex');
const secretPattern = /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:ghp_|ghs_|github_pat_)[A-Za-z0-9_]{20,}|\bsk-[A-Za-z0-9_-]{24,}/;
function eligible(path, excludes=[]) {
  if (!path || path.startsWith('/') || /[\x00-\x1f"\\]/.test(path)) return false;
  const parts=path.split('/'), name=parts.at(-1);
  if(parts.some(p=>['..','.git','node_modules','vendor','dist','build','.next','.venv','coverage','__pycache__'].includes(p))) return false;
  if(/^\.env|\.(pem|key|lock)$|-lock\.json$|\.min\.js$/.test(name) || /^(credentials|secrets)\./i.test(name)) return false;
  if(!/\.(py|ts|tsx|js|jsx|go|rs|java|cs|rb|php|c|cpp|h|md|sql|json|ya?ml|toml|graphql)$/.test(name)) return false;
  return !excludes.some(g=>new RegExp('^'+g.split('*').map(p=>p.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('.*')+'$').test(path));
}
function git(path, args, options={}) {
  const token=$('Review installation token').first().json.token;
  const env={PATH:'/usr/local/bin:/usr/bin:/bin',HOME:'/home/node',GIT_TERMINAL_PROMPT:'0',GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_CONFIG_COUNT:'3',
    GIT_CONFIG_KEY_0:'http.https://github.com/.extraheader',GIT_CONFIG_VALUE_0:'Authorization: Basic '+Buffer.from('x-access-token:'+token).toString('base64'),
    GIT_CONFIG_KEY_1:'core.hooksPath',GIT_CONFIG_VALUE_1:'/dev/null',GIT_CONFIG_KEY_2:'core.quotePath',GIT_CONFIG_VALUE_2:'false'};
  try {return cp.execFileSync('git',['--literal-pathspecs','-C',path,...args],{env,timeout:180000,maxBuffer:60000000,encoding:options.binary?null:'utf8',input:options.input,stdio:['pipe','pipe','pipe']});}
  catch(e){ if(options.optional)return '';throw new Error('Git '+args[0]+' failed; credentials omitted from error'); }
}
function parseDiff(patch) {
  const out={}; let path=null,old=null,now=null;
  for(const line of patch.split('\n')) {
    if(line.startsWith('diff --git ')){path=null;old=null;now=null;}
    else if(line.startsWith('--- ') && line.slice(4)!='/dev/null') path=line.slice(4).replace(/^a\//,'');
    else if(line.startsWith('+++ ')){if(line.slice(4)!='/dev/null')path=line.slice(4).replace(/^b\//,'');if(path)out[path]??={LEFT:[],RIGHT:[],changed:[]};}
    else if(line.startsWith('@@ ')){const m=line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);if(m){old=+m[1];now=+m[2];out[path]??={LEFT:[],RIGHT:[],changed:[]};}}
    else if(out[path] && old!==null){if(line.startsWith('-'))out[path].LEFT.push(old++);else if(line.startsWith('+')){out[path].RIGHT.push(now);out[path].changed.push(now++);}else if(line.startsWith(' ')){out[path].LEFT.push(old++);out[path].RIGHT.push(now++);}}
  } return out;
}
const lexical = s => s+'\n'+s.replace(/([a-z0-9])([A-Z])/g,'$1 $2').replaceAll('_',' ');
const scope = (repo,head) => ({must:[{key:'repo',match:{value:repo}},{key:'head',match:{value:head}}]});
