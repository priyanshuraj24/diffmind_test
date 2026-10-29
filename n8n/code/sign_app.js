const jwt=require('jsonwebtoken');
const config=JSON.parse(fs.readFileSync('/home/node/.n8n-files/diffmind-native-config.json','utf8'));
const key=fs.readFileSync('/home/node/.n8n-files/github.pem','utf8');
const now=Math.floor(Date.now()/1000);
return $input.all().map(i=>({json:{...i.json,app_jwt:jwt.sign({iat:now-60,exp:now+540,iss:String(config.app_id)},key,{algorithm:'RS256'})}}));
