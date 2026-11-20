// Local fixture for the documented Slack Web API subset. Never deploy this mock.
const http = require('http');
let posts = [];
http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  let body = req.body;
  if (!body) {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    try { body = JSON.parse(raw || '{}'); } catch { body = Object.fromEntries(new URLSearchParams(raw)); }
  }
  let result;
  let status = 200;
  if (url.pathname === '/reset') { posts = []; result = {ok: true}; }
  else if (url.pathname === '/records') result = {posts};
  else if (url.pathname === '/api/conversations.replies') {
    const ts = url.searchParams.get('ts') || body.ts;
    if (ts === '1794800000.000003') result = {ok: false, error: 'thread_not_found'};
    else if (ts === '1794800000.000004') { status = 503; result = {ok: false, error: 'service_unavailable'}; }
    else if (ts === '1794800000.000005') { status = 200; result = {ok: true, messages: []}; }
    else if (ts === '1794800000.000002') result = {ok: true, messages: [
      {ts, thread_ts: '1794800000.000001', text: 'reply evidence'}
    ]};
    else result = {ok: true, messages: [
      {ts: '1794800000.000001', text: 'root symptom'},
      {ts: '1794800000.000002', thread_ts: '1794800000.000001', text: 'reply evidence'}
    ]};
  } else if (url.pathname === '/api/chat.postMessage') {
    if (!body.channel?.startsWith('D') || !body.thread_ts) { status = 400; result = {ok: false, error: 'invalid_arguments'}; }
    else { posts.push(body); result = {ok: true, channel: body.channel, ts: `1794800001.${String(posts.length).padStart(6, '0')}`}; }
  } else if (url.pathname === '/api/chat.update') result = {ok: true, channel: body.channel, ts: body.ts};
  else { status = 501; result = {ok: false, error: 'not_modelled'}; }
  res.writeHead(status, {'Content-Type': 'application/json'});
  res.end(JSON.stringify(result));
}).listen(process.env.PORT);
