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
async function git(path, args, options={}) {
  const token=$('Review installation token').first().json.token;
  const env={PATH:'/usr/local/bin:/usr/bin:/bin',HOME:'/home/node',GIT_TERMINAL_PROMPT:'0',GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_CONFIG_COUNT:'3',
    GIT_CONFIG_KEY_0:'http.https://github.com/.extraheader',GIT_CONFIG_VALUE_0:'Authorization: Basic '+Buffer.from('x-access-token:'+token).toString('base64'),
    GIT_CONFIG_KEY_1:'core.hooksPath',GIT_CONFIG_VALUE_1:'/dev/null',GIT_CONFIG_KEY_2:'core.quotePath',GIT_CONFIG_VALUE_2:'false'};
  try {
    return await new Promise((resolve,reject)=>{
      const child=cp.execFile('git',['--literal-pathspecs','-C',path,...args],
        {env,timeout:120000,maxBuffer:60000000,encoding:options.binary?null:'utf8'},
        (error,stdout,stderr)=>{if(error){error.stderr=stderr;reject(error);}else resolve(stdout);});
      child.stdin.on('error',error=>{if(error.code!=='EPIPE')reject(error);});
      child.stdin.end(options.input);
    });
  } catch(e){
    // Never expose raw stderr, arguments, or environment: Git can echo credentials.
    if(options.optional && !e.killed && [1,128].includes(e.code))return '';
    const message=String(e.stderr||'');
    let reason='exit '+(Number.isInteger(e.code)?e.code:'unavailable');
    if(e.killed||e.code==='ETIMEDOUT')reason='timed out after 120 seconds';
    else if(/(?:unable to create|already exists|another git process)[^\n]*lock|shallow\.lock/i.test(message))reason='repository lock contention';
    else if(/Authentication failed|could not read Username|Repository not found|HTTP (?:401|403)/i.test(message))reason='repository access or authentication failed';
    else if(/Could not resolve host|Failed to connect|Connection.*reset|RPC failed|timed out/i.test(message))reason='network transfer failed';
    else if(/No space left on device/i.test(message))reason='disk full';
    else if(/not our ref|couldn.t find remote ref|bad object/i.test(message))reason='requested commit unavailable';
    throw new Error('Git '+args[0]+' failed: '+reason+'; credentials omitted');
  }
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

// Bound the complete BGE WordPiece input by UTF-8 bytes, including metadata.
// Leave 50 tokens of headroom for special tokens and query framing.
const DENSE_INPUT_BYTES = 450;
function utf8Prefix(text, budget) {
  let output='', bytes=0;
  for(const character of text){const size=Buffer.byteLength(character,'utf8');if(bytes+size>budget)break;output+=character;bytes+=size;}
  return output;
}
