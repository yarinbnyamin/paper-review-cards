"""Build the artifact version of the review page from index.html.

    python3 "Claude Artifact/build_page.py" [out.html]      (default: "Claude Artifact/review-cards.html")

The artifact page is index.html with its transport swapped: instead of the
local server's /api routes it reads the cards from the artifact's database
(`cards`, `meta/paper`) and writes the user's decisions and skips into it
(`decisions`, `skips`). Same look, same card logic, so the two never drift.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "index.html"), encoding="utf-8").read()

style = re.search(r"<style>(.*?)</style>", src, re.S).group(1)
body = re.search(r"<body>(.*?)<script>", src, re.S).group(1)
script = re.search(r"<script>(.*?)</script>", src, re.S).group(1)

# the artifact skeleton pads :root by the safe-area insets; a sticky header sits below them
style = style.replace("header{position:sticky;top:0;", "header{position:sticky;top:env(safe-area-inset-top,0px);")
# drop the local start-up line (meta fetch + polling); the database start-up below replaces it
script = re.sub(r"\nfetch\('/api/meta'\).*$", "\n", script.rstrip(), flags=re.S)

TRANSPORT = r"""
// ---- artifact transport: the artifact's database instead of the local server ----
// cards/<id>     written by Claude from the paper (scan.py + proposals + statuses)
// meta/paper     {tex, macros}
// decisions/<x>  written here when you press Done; Claude applies them and sets handled
// skips/<id>     written here by Skip; the card comes back when the thread's sig changes
let CARDS=null,DEC=[],SKIPS={},DB=null;
function compose(){
 ALL=(CARDS||[]).map(c=>{const s=SKIPS[c.id],pend=DEC.some(e=>e.id===c.id&&!e.handled);
  let st=c.status||'';if(s)st=s.sig===c.sig?'skip':'reopened';else if(pend)st='pending';
  return Object.assign({},c,{status:st})});
 Q=DEC.slice();}
function message(t){document.getElementById('card').innerHTML=`<div class="card none">${t}</div>`}
async function refresh(){compose();
 if(CARDS===null)return message('Loading the cards…');
 if(!CARDS.length){dots();return message('No cards yet. Claude fills this page from the paper.')}
 const a=document.activeElement;if(a&&a.tagName==='TEXTAREA'){view();dots()}else render()}
function poll(){}
async function post(u,b){
 if(!DB)throw new Error('no database');
 const now=Date.now()/1000;
 if(u==='/api/done')await DB.collection('decisions').add(Object.assign({},b,{ts:now,handled:false}));
 else if(u==='/api/skip')await DB.doc('skips/'+b.id).set({sig:b.sig,ts:now});
 else if(u==='/api/unskip')await DB.doc('skips/'+b.id).delete();}
message('Loading the cards…');
(async()=>{
 const db=window.claude&&window.claude.use?await window.claude.use('db'):null;
 if(!db)return message('Open this page on claude.ai while signed in to see and answer the cards.');
 DB=db;
 const fail=e=>message('The cards could not be loaded ('+esc(e&&e.code||'error')+'). Reload the page to try again.');
 db.doc('meta/paper').onSnapshot(s=>{if(s.exists){META=s.data();document.getElementById('file').textContent=META.tex||''}refresh()},fail);
 db.collection('cards').onSnapshot(s=>{CARDS=s.docs.map(d=>d.data());refresh()},fail);
 db.collection('decisions').onSnapshot(s=>{DEC=s.docs.map(d=>d.data());refresh()},fail);
 db.collection('skips').onSnapshot(s=>{const m={};s.docs.forEach(d=>m[d.id]=d.data());SKIPS=m;refresh()},fail);
})();
"""

page = ("<title>Paper Review Cards</title>\n<style>" + style + "</style>\n"
        + body.strip() + "\n<script>" + script + TRANSPORT + "</script>\n")
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "review-cards.html")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(page)
print("wrote", out, len(page), "bytes")
