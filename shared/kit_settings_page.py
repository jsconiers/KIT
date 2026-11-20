"""kit_settings_page: how the `kit-settings ui` page looks and behaves in the browser (HTML, CSS, and script).

kit_settings_ui serves it and enforces every rule (session, CSRF, the allowlist, validation); this module only
renders. The page has a section list on the left (Setup, then the groups in kit_settings.GROUPS with how many
settings each shows, then Snapshots and Review loop), a search box ("/" jumps to it) and filters at the top, and one
card per setting: a plain-English label, a line of help, the raw key and source small beneath, a badge when it's
changed from its default, not set, or read-only, and a control that suits its type (a switch for on/off, a list for
fixed choices, a number box with its range, else text). Changes are held on the page, each checked against the
server as you type, until you press Review & save in the bar at the bottom: that shows every change's diff, and
Confirm saves them all in one step (a configuration snapshot first). Nothing is sent anywhere else: no external
script, style, font, or image, and everything inline carries the page's nonce, so the Content-Security-Policy holds.
"""
import html

import kit_settings as ks

e = html.escape

CSS = """
:root{--bg:#FFFFFF;--fg:#15202B;--muted:#4F5D6B;--line:#C9D0D6;--panel:#F3F5F7;--accent:#0B5CAD;--accent-fg:#FFFFFF;
--warn:#8A5A00;--warn-bg:#FFF4DC;--ok:#1E6B3D;--bad:#B00020;--bad-bg:#FDECEE;--chg:#0B5CAD;--chg-bg:#E6F0FA;--focus:#F2A900}
@media (prefers-color-scheme:dark){:root{--bg:#12171C;--fg:#E6EAEE;--muted:#A9B4BF;--line:#36414B;--panel:#1B232A;
--accent:#6FB1F2;--accent-fg:#0B1218;--warn:#F2C46B;--warn-bg:#3A2E12;--ok:#7BD49C;--bad:#FF8A95;--bad-bg:#3A1A1E;
--chg:#8EC5FF;--chg-bg:#18324A;--focus:#F2C46B}}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{font:15px/1.45 system-ui,-apple-system,"Segoe UI",Arial,sans-serif;margin:0;color:var(--fg);background:var(--bg)}
a{color:var(--accent)}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.note{color:var(--muted)}
code,.kkey,pre{font-family:ui-monospace,Menlo,Consolas,monospace}
button{font:inherit;padding:.3rem .7rem;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);color:var(--accent-fg);border-color:var(--accent)}
button:disabled{opacity:.55;cursor:not-allowed}
input,select{font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:.3rem .45rem}
.ktop{position:sticky;top:0;z-index:3;display:flex;flex-wrap:wrap;gap:.6rem 1.2rem;align-items:center;padding:.7rem 1.2rem;
background:var(--bg);border-bottom:1px solid var(--line)}
.ktop h1{margin:0;font-size:1.35rem}
.ktop .ksearch{flex:1 1 18rem;display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
.ktop #kq{flex:1 1 14rem;min-width:12rem}
.klayout{display:grid;grid-template-columns:15.5rem minmax(0,1fr);min-height:calc(100vh - 4rem)}
@media (max-width:760px){.klayout{grid-template-columns:1fr}#knav{position:static;border-right:0;border-bottom:1px solid var(--line)}}
#knav{position:sticky;top:3.6rem;align-self:start;padding:.8rem .6rem;border-right:1px solid var(--line);max-height:calc(100vh - 4rem);overflow:auto}
#knav ul{list-style:none;margin:0;padding:0}
#knav li{margin:0 0 .15rem}
#knav button{width:100%;text-align:left;display:flex;justify-content:space-between;align-items:center;gap:.4rem;border:0;background:none;padding:.4rem .6rem}
#knav button[aria-current=true]{background:var(--chg-bg);color:var(--chg);font-weight:600}
#knav .kn{color:var(--muted);font-size:.85rem;font-variant-numeric:tabular-nums}
#knav .kpn,.kbadge{font-size:.72rem;font-weight:600;padding:.05rem .4rem;border-radius:999px;white-space:nowrap}
#knav .kpn{background:var(--chg);color:var(--accent-fg)}
#knav .kns{background:var(--warn-bg);color:var(--warn);font-size:.72rem;font-weight:600;padding:.05rem .4rem;border-radius:999px}
#knav hr{border:0;border-top:1px solid var(--line);margin:.6rem 0}
main{padding:1rem 1.4rem 7rem;max-width:68rem}
main h2{margin:.2rem 0 .2rem;font-size:1.3rem}
.kgroup-help{margin:0 0 .8rem}
details.ksub{border:1px solid var(--line);border-radius:8px;margin:0 0 .8rem;background:var(--bg)}
details.ksub>summary{cursor:pointer;padding:.55rem .8rem;font-weight:600;display:flex;gap:.6rem;align-items:baseline}
details.ksub>summary .ksub-n{color:var(--muted);font-weight:400;font-size:.85rem}
details.ksub>summary .ksub-src{color:var(--muted);font-weight:400;font-size:.8rem;margin-left:auto}
.kitem{display:grid;grid-template-columns:minmax(0,1fr) minmax(12rem,22rem);gap:.3rem 1rem;padding:.65rem .8rem;border-top:1px solid var(--line)}
@media (max-width:900px){.kitem{grid-template-columns:1fr}}
.kitem.kpending{background:var(--chg-bg)}
.kitem.kbad{background:var(--bad-bg)}
.khead{display:flex;flex-wrap:wrap;gap:.3rem .5rem;align-items:baseline}
.klabel{font-weight:600}
.kkey{color:var(--muted);font-size:.78rem;overflow-wrap:anywhere}
.khelp{margin:.1rem 0 0;color:var(--muted);font-size:.9rem}
.knote{margin:.2rem 0 0;color:var(--muted);font-size:.84rem}
.kbadge.changed{background:var(--chg-bg);color:var(--chg)}
.kbadge.notset{background:var(--warn-bg);color:var(--warn)}
.kbadge.ro{background:var(--panel);color:var(--muted);border:1px solid var(--line)}
.kctl{display:flex;flex-direction:column;gap:.3rem;align-items:stretch}
.kctl .kin{width:100%}
.kctl .kswitch input.kin{width:2.6rem;flex:none}
.kctl .krow{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center}
.kctl .kval{font-size:.86rem;overflow-wrap:anywhere;background:var(--panel);padding:.25rem .45rem;border-radius:6px}
.kerr{color:var(--bad);font-size:.84rem;min-height:0}
.kerr:empty{display:none}
.kswitch{display:inline-flex;align-items:center;gap:.5rem;cursor:pointer}
.kswitch input{appearance:none;-webkit-appearance:none;width:2.6rem;height:1.45rem;border-radius:999px;background:var(--line);
position:relative;border:0;padding:0;cursor:pointer;transition:background .15s}
.kswitch input::after{content:"";position:absolute;top:.17rem;left:.18rem;width:1.1rem;height:1.1rem;border-radius:50%;background:#fff;transition:left .15s}
.kswitch input:checked{background:var(--accent)}
.kswitch input:checked::after{left:1.32rem}
.ksmall{font-size:.8rem;padding:.15rem .5rem}
#kbar{position:fixed;left:0;right:0;bottom:0;z-index:4;background:var(--panel);border-top:2px solid var(--accent);padding:.6rem 1.2rem;
box-shadow:0 -4px 14px rgba(0,0,0,.12)}
#kbar .kbar-row{display:flex;gap:.8rem;align-items:center;flex-wrap:wrap}
#kbar-n{font-weight:600}
#kreview{max-height:55vh;overflow:auto;margin-top:.6rem}
.kdiffitem{margin:.5rem 0}
pre.kdiff{white-space:pre-wrap;font-size:.8rem;line-height:1.35;background:var(--bg);border:1px solid var(--line);padding:.45rem;margin:.3rem 0;border-radius:6px}
.kmsg{font-size:.9rem;margin:.3rem 0}
.kmsg.bad{color:var(--bad)}
.kwiz{background:var(--panel);padding:.8rem 1rem;border-radius:8px;margin:0 0 1rem}
.kwiz summary{font-weight:600;cursor:pointer}
.kwiz .kq{font-size:1.1rem;margin:.4rem 0}
.kwiz .kin{width:100%;max-width:46rem}
.kwiz .kbar{width:100%;max-width:46rem}
.kwiz button{margin:.4rem .4rem 0 0}
.kprio{color:var(--warn);font-weight:600}
.krev h2{font-size:1.3rem}
.kreview{border-collapse:collapse;width:100%}
.kreview th,.kreview td{text-align:left;vertical-align:top;padding:.4rem .5rem;border-top:1px solid var(--line)}
.kscore{font-weight:600}.kscore.ok{color:var(--ok)}.kscore.warn{color:var(--warn)}.kscore.bad{color:var(--bad)}
.klinks a{margin-right:.6rem}
.kjob{background:var(--panel);padding:.5rem .8rem;margin:.6rem 0}
table.ksnaps{border-collapse:collapse;width:100%;margin:.6rem 0}
table.ksnaps th,table.ksnaps td{text-align:left;padding:.4rem .5rem;border-top:1px solid var(--line);vertical-align:top}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
"""

JS = r"""
(function(){var csrf=document.querySelector('meta[name=kit-csrf]').content;
function post(path,body){return fetch(path,{method:'POST',credentials:'same-origin',
headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body||{})})
.then(function(r){return r.json().then(function(j){j.status=r.status;return j;});});}
function $(s,r){return (r||document).querySelector(s);}
function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}
function el(t,cls,txt){var x=document.createElement(t);if(cls)x.className=cls;if(txt!=null)x.textContent=txt;return x;}
var pending={},invalid={},timers={};
var bar=$('#kbar'),barN=$('#kbar-n'),rvw=$('#kreview'),saveBtn=$('#kbar-review');
function val(inp){if(inp.type==='checkbox')return inp.checked?inp.getAttribute('data-on'):inp.getAttribute('data-off');return inp.value;}
function setVal(inp,v){if(inp.type==='checkbox')inp.checked=(v===inp.getAttribute('data-on'));else inp.value=v;}
function item(x){return x.closest('.kitem');}
function counts(){$$('#knav button[data-group]').forEach(function(b){var p=$('#p-'+b.getAttribute('data-panel'));if(!p)return;
var vis=$$('.kitem:not([hidden])',p).length,pend=$$('.kitem.kpending',p).length,c=$('.kn',b),pb=$('.kpn',b);
if(c)c.textContent=vis;if(pb){pb.textContent=pend?pend+' unsaved':'';pb.hidden=!pend;}});}
function refreshBar(){var n=Object.keys(pending).length,bad=Object.keys(invalid).length;
bar.hidden=n===0;barN.textContent=n+' unsaved change'+(n===1?'':'s')+(bad?' ('+bad+' to fix first)':'');
saveBtn.disabled=bad>0;if(n===0){rvw.hidden=true;rvw.textContent='';}
$$('.kitem[data-id]').forEach(function(it){it.classList.toggle('kpending',!!pending[it.getAttribute('data-id')]);});counts();}
function check(it){var id=it.getAttribute('data-id'),inp=$('.kin',it),err=$('.kerr',it),v=val(inp);
clearTimeout(timers[id]);var undo=$('button[data-act=undo]',it);
if(v===it.getAttribute('data-orig')){delete pending[id];delete invalid[id];err.textContent='';it.classList.remove('kbad');
if(undo)undo.hidden=true;refreshBar();return;}
if(undo)undo.hidden=false;
pending[id]={id:id,value:v,expect:it.getAttribute('data-expect')};refreshBar();
timers[id]=setTimeout(function(){post('/api/preview',{id:id,value:v,expect:it.getAttribute('data-expect')}).then(function(j){
if(!pending[id]||pending[id].value!==v)return;
if(j.ok){delete invalid[id];err.textContent='';it.classList.remove('kbad');}
else{invalid[id]=1;err.textContent=j.error||'Not allowed';it.classList.add('kbad');}refreshBar();});},350);}
function isCard(t){return t.classList&&t.classList.contains('kin')&&item(t)&&!t.closest('#kwiz');}
document.addEventListener('input',function(ev){if(isCard(ev.target))check(item(ev.target));});
document.addEventListener('change',function(ev){if(isCard(ev.target))check(item(ev.target));});
window.addEventListener('beforeunload',function(ev){if(Object.keys(pending).length){ev.preventDefault();ev.returnValue='';}});
var q=$('#kq'),show=$('#kshow'),oc=$('#kchanged'),found=$('#kfound'),nav=$('#knav');
function open(name,push){if(!$('#p-'+name))name=nav.getAttribute('data-first');
$$('.kpanel').forEach(function(p){p.hidden=p.id!=='p-'+name;});
$$('#knav button[data-panel]').forEach(function(b){b.setAttribute('aria-current',b.getAttribute('data-panel')===name?'true':'false');});
if(push&&history.replaceState)history.replaceState(null,'','#'+name);}
function searching(){return !!(q.value.trim()||show.value||oc.checked);}
function filter(){var t=q.value.trim().toLowerCase(),s=show.value,only=oc.checked,any=searching();
$$('.kitem[data-search]').forEach(function(it){var ed=it.getAttribute('data-editable')==='1';
var ok=(!t||it.getAttribute('data-search').indexOf(t)>=0)&&
(!s||(s==='editable'?ed:s==='readonly'?!ed:it.getAttribute('data-status')===s))&&
(!only||it.getAttribute('data-changed')==='1'||it.classList.contains('kpending'));it.hidden=!ok;});
$$('details.ksub').forEach(function(d){var n=$$('.kitem:not([hidden])',d).length;d.hidden=n===0;var c=$('.ksub-n',d);
if(c)c.textContent=n+(n===1?' setting':' settings');if(any&&n)d.open=true;});
if(any){$$('.kpanel').forEach(function(p){p.hidden=!p.hasAttribute('data-group')||!$$('.kitem:not([hidden])',p).length;});
var m=$$('.kpanel[data-group] .kitem:not([hidden])').length;found.textContent=m+' matching';}
else{found.textContent='';open((location.hash||'').slice(1),false);}counts();}
q.addEventListener('input',filter);show.addEventListener('change',filter);oc.addEventListener('change',filter);
nav.addEventListener('click',function(ev){var b=ev.target.closest('button[data-panel]');if(!b)return;
q.value='';show.value='';oc.checked=false;var name=b.getAttribute('data-panel');filter();open(name,true);
var h=$('#p-'+name+' h2');if(h){h.setAttribute('tabindex','-1');h.focus();}});
document.addEventListener('keydown',function(ev){var a=document.activeElement;
if(ev.key==='/'&&!(a&&(a.tagName==='INPUT'||a.tagName==='TEXTAREA'||a.tagName==='SELECT'))){ev.preventDefault();q.focus();}
if(ev.key==='Escape'&&a===q&&q.value){q.value='';filter();}});
function diffs(box,items,title){box.textContent='';box.appendChild(el('h3',null,title));items.forEach(function(x){
var d=el('div','kdiffitem');d.appendChild(el('strong',null,x.label));d.appendChild(document.createTextNode(' '));
if(x.source)d.appendChild(el('span','kkey',x.source));
if(x.ok)d.appendChild(el('pre','kdiff',x.diff));else d.appendChild(el('div','kmsg bad',x.error));box.appendChild(d);});}
function changes(){return Object.keys(pending).map(function(k){return pending[k];});}
document.addEventListener('click',function(ev){var b=ev.target.closest('button[data-act]');if(!b)return;
var act=b.getAttribute('data-act');
if(act.indexOf('rv-')===0){if(typeof review==='function')review(b,act);return;}
if(act.indexOf('sq-')===0){if(typeof setupq==='function')setupq(b,act);return;}
if(act==='stop'){if(Object.keys(pending).length&&!window.confirm('You have unsaved changes. Stop anyway?'))return;
post('/api/stop').then(function(){document.body.textContent='Stopped. You can close this tab.';});return;}
if(act==='reset'||act==='undo'){var it=item(b),inp=$('.kin',it);
setVal(inp,it.getAttribute(act==='reset'?'data-default':'data-orig'));check(it);inp.focus();return;}
if(act==='discard'){$$('.kitem[data-id]').forEach(function(it){if(pending[it.getAttribute('data-id')]){
setVal($('.kin',it),it.getAttribute('data-orig'));$('.kerr',it).textContent='';it.classList.remove('kbad');
var u=$('button[data-act=undo]',it);if(u)u.hidden=true;}});pending={};invalid={};refreshBar();filter();return;}
if(act==='batch-preview'){post('/api/batch/preview',{changes:changes()}).then(function(j){rvw.hidden=false;
if(!j.items){rvw.textContent='';rvw.appendChild(el('div','kmsg bad',j.error||'Refused'));return;}
diffs(rvw,j.items,'Review '+j.items.length+' change'+(j.items.length===1?'':'s'));
rvw.appendChild(el('p','note',j.message||''));
if(j.ok){var c=el('button','primary','Confirm and save all');c.type='button';c.setAttribute('data-act','batch-apply');rvw.appendChild(c);
rvw.appendChild(document.createTextNode(' '));}
var x=el('button',null,'Keep editing');x.type='button';x.setAttribute('data-act','batch-close');rvw.appendChild(x);
var h=$('h3',rvw);h.setAttribute('tabindex','-1');h.focus();});return;}
if(act==='batch-close'){rvw.hidden=true;rvw.textContent='';return;}
if(act==='batch-apply'){b.disabled=true;post('/api/batch/apply',{changes:changes()}).then(function(j){rvw.textContent='';rvw.hidden=false;
rvw.appendChild(el('div','kmsg'+(j.ok?'':' bad'),j.message||j.error||'Refused'));
(j.results||[]).forEach(function(r){rvw.appendChild(el('div','kmsg'+(r.ok?'':' bad'),r.label+': '+(r.ok?'saved':r.error)));});
if(j.ok){pending={};invalid={};setTimeout(function(){location.reload();},1600);}});return;}
var sbox=$('#ksnap-box'),sid=b.getAttribute('data-snap');
function sayS(t,bad){sbox.appendChild(el('div','kmsg'+(bad?' bad':''),t));}
if(act==='snap-take'){post('/api/snapshots/take',{note:$('#ksnap-note').value}).then(function(j){sbox.textContent='';
sayS(j.message||j.error,!j.ok);if(j.ok&&j['new'])setTimeout(function(){location.hash='snapshots';location.reload();},1200);});return;}
if(act==='snap-diff'){post('/api/snapshots/diff',{id:sid}).then(function(j){sbox.textContent='';
sbox.appendChild(el('h3',null,'Snapshot '+sid+' compared with now'));
if(!j.ok){sayS(j.error,true);return;}sbox.appendChild(el('pre','kdiff',j.diff||'No differences.'));
sbox.scrollIntoView({block:'nearest'});});return;}
if(act==='snap-restore'){post('/api/snapshots/restore-preview',{id:sid}).then(function(j){sbox.textContent='';
sbox.appendChild(el('h3',null,'Restore snapshot '+sid+'?'));if(!j.ok){sayS(j.error,true);return;}
sbox.appendChild(el('pre','kdiff',j.diff||'Nothing would change.'));sbox.appendChild(el('p','note',j.message));
if(j.changes){var c=el('button','primary','Confirm and restore');c.type='button';c.setAttribute('data-act','snap-go');
c.setAttribute('data-snap',sid);sbox.appendChild(c);}sbox.scrollIntoView({block:'nearest'});});return;}
if(act==='snap-go'){b.disabled=true;post('/api/snapshots/restore',{id:sid,confirm:true}).then(function(j){
sayS(j.message||j.error,!j.ok);if(j.ok)setTimeout(function(){location.hash='snapshots';location.reload();},2200);});return;}
});
window.addEventListener('hashchange',function(){if(!searching())open(location.hash.slice(1),false);});
var h0=(location.hash||'').slice(1);if(h0==='kwiz'){h0='setup';if(history.replaceState)history.replaceState(null,'','#setup');}
open(h0,false);refreshBar();filter();
})();
"""

SHOW_FILTERS = [("", "All settings"), ("not set", "Not set"), ("editable", "Editable here"), ("readonly", "Read-only")]


def _is_number(v):
    """Empty or a plain number: what a number box can show. A documented default like "300 s" gets a text box."""
    try:
        return v == "" or float(v) == float(v)
    except ValueError:
        return False


def control(s, p, uid):
    """The input for one editable setting, by its type."""
    t = s["type"]
    kind = t[0]
    cur = "" if (s["status"] == "not set" and s["kind"] == "setup") else s["raw"]
    label = f'aria-labelledby="{uid}-l"'
    if kind == "onoff" and cur in ("on", "off", ""):
        return (f'<label class="kswitch"><input class="kin" id="{uid}" type="checkbox" role="switch" data-on="on" '
                f'data-off="off"{" checked" if cur == "on" else ""} {label}><span class="note">on</span></label>'), \
            ("on" if cur == "on" else "off") if cur else "off"
    opts = p.get("options")
    if opts:
        allopts = ([cur] if cur and cur not in opts else []) + ([""] if not cur else []) + opts
        o = "".join(f'<option value="{e(x)}"{" selected" if x == cur else ""}>{e(x) if x else "(not set)"}</option>'
                    for x in allopts)
        return f'<select class="kin" id="{uid}" {label}>{o}</select>', cur
    if kind in ("int", "float") and _is_number(cur):
        step = "1" if kind == "int" else "any"
        return (f'<input class="kin" id="{uid}" type="number" inputmode="decimal" min="{t[1]}" max="{t[2]}" '
                f'step="{step}" value="{e(cur)}" {label} aria-describedby="{uid}-h">'
                f'<span class="kkey">{t[1]} to {t[2]}{", or empty" if len(t) > 3 and t[3] else ""}</span>'), cur
    ph = {"days": "e.g. 6 7", "waits": "e.g. 30 90", "modes": "e.g. morning weekly", "email": "you@company.com",
          "phone_or_email": "+15551234567", "setup_path": "`~/Documents/Library`", "date": "02-Oct-2026",
          "channels": "e.g. local outlook-drafts", "path": "~/folder", "window": "minutes, or off"}.get(kind, "")
    return (f'<input class="kin" id="{uid}" type="text" value="{e(cur)}" autocomplete="off" spellcheck="false" '
            f'placeholder="{e(ph)}" {label} aria-describedby="{uid}-h">'), cur


def card(s, n):
    """One setting's card."""
    uid = f"k{n}"
    p = ks.public(s) if s["editable"] else None
    where = s["source"] + (f":{s['line']}" if s["line"] else " (not in the file; shows the default)")
    key = s["name"] if s["kind"] == "config" else (s["section"] + " · " if s["section"] else "") + s["name"]
    badges = ""
    if s["status"] == "not set":
        badges += '<span class="kbadge notset">not set</span>'
    elif s["status"] == "set" and s["kind"] in ("config", "setup"):
        badges += '<span class="kbadge changed" title="Different from the shipped default">changed</span>'
    if not s["editable"]:
        badges += '<span class="kbadge ro">read-only</span>'
    search = " ".join([s["label"], s["name"], s["section"], s["source"], s["help"], s["value"][:300]]).lower()
    head = (f'<div><div class="khead"><span class="klabel" id="{uid}-l">{e(s["label"])}</span>{badges}</div>'
            f'<div class="kkey">{e(key)} · {e(where)}</div>'
            + (f'<p class="khelp" id="{uid}-h">{e(s["help"])}</p>' if s["help"] else f'<span id="{uid}-h"></span>'))
    changed = "1" if s["status"] == "set" and s["kind"] in ("config", "setup") else "0"
    common = (f'data-search="{e(search)}" data-status="{e(s["status"])}" data-changed="{changed}" '
              f'data-editable="{1 if s["editable"] else 0}" data-group="{e(s["group"])}"')
    if not s["editable"]:
        v = s["value"]
        shown = (e(v[:300]) + "…") if len(v) > 300 else (e(v) if v else "<em>(empty)</em>")
        note = f'<p class="knote">{e(s["note"])}</p>' if s["note"] else ""
        return (f'<div class="kitem" {common}>{head}{note}</div>'
                f'<div class="kctl"><code class="kval" title="{e(v[:2000])}">{shown}</code></div></div>')
    ctl, orig = control(s, p, uid)
    reset = ""
    if p.get("can_reset"):
        dv = p["default"]
        reset = (f'<button type="button" class="ksmall" data-act="reset" '
                 f'title="Reset to the shipped default">Reset to default{": " + e(dv[:40]) if dv else " (empty)"}</button>')
    return (f'<div class="kitem" data-id="{e(s["id"])}" data-expect="{e(p["expect"])}" data-orig="{e(orig)}" '
            f'data-default="{e(p.get("default") or "")}" {common}>{head}</div>'
            f'<div class="kctl">{ctl}<div class="kerr" role="alert"></div><div class="krow">{reset}'
            f'<button type="button" class="ksmall" data-act="undo" hidden>Undo</button></div></div></div>')


def sub_title(src, items):
    if src == ks.CONFIG_REL:
        return "Run settings", src
    if items and items[0]["kind"] == "json":
        return items[0]["source"].split("/")[-1] + " (read-only)", src
    name = src.split("/")[-1]
    return name[:-3].replace("-", " ").capitalize() + " setup", src


def group_panels(items):
    """(nav buttons, panels) for the groups, each split into sub-sections by source file."""
    navs, panels = [], []
    n = 0
    for gid, glabel, ghelp in ks.GROUPS:
        rows = [s for s in items if s["group"] == gid]
        if not rows:
            continue
        notset = sum(1 for s in rows if s["status"] == "not set" and s["editable"])
        navs.append(f'<li><button type="button" data-panel="{gid}" data-group="{gid}" aria-controls="p-{gid}">'
                    f'<span>{e(glabel)}</span><span><span class="kpn" hidden></span>'
                    + (f' <span class="kns" title="{notset} not set">{notset}</span>' if notset else "")
                    + f' <span class="kn">{len(rows)}</span></span></button></li>')
        subs = {}
        for s in rows:
            subs.setdefault(s["source"], []).append(s)
        order = sorted(subs, key=lambda k: (0 if k == ks.CONFIG_REL else 2 if subs[k][0]["kind"] in ("json", "info")
                                            else 1, k))
        body = ""
        rank = {k: i for i, k in enumerate(ks.META)}
        for src in order:
            its = subs[src]
            if src == ks.CONFIG_REL:      # the table's order: related settings together, the main one first
                its = sorted(its, key=lambda s: rank.get(s["name"], len(rank)))
            title, path = sub_title(src, its)
            cards = ""
            for s in its:
                n += 1
                cards += card(s, n)
            editable = any(s["editable"] for s in its)
            opened = " open" if (src == ks.CONFIG_REL or len(order) <= 2 or
                                 any(s["status"] == "not set" and s["editable"] for s in its)) and editable else ""
            body += (f'<details class="ksub"{opened}><summary>{e(title)} <span class="ksub-n">{len(its)} settings</span>'
                     f'<span class="ksub-src">{e(path)}</span></summary>{cards}</details>')
        panels.append(f'<section class="kpanel" id="p-{gid}" data-group="{gid}" aria-labelledby="h-{gid}" hidden>'
                      f'<h2 id="h-{gid}">{e(glabel)}</h2><p class="note kgroup-help">{e(ghelp)}</p>{body}</section>')
    return navs, panels


def snapshots_panel(rows):
    if rows:
        trs = "".join(
            f'<tr><td><code>{e(r["id"])}</code></td><td>{e(r["created"][:16].replace("T", " "))}</td>'
            f'<td>{e(r["note"]) or "<span class=note>(no note)</span>"}</td><td>{r["files"]}</td>'
            f'<td><button type="button" class="ksmall" data-act="snap-diff" data-snap="{e(r["id"])}">Compare with now</button> '
            f'<button type="button" class="ksmall" data-act="snap-restore" data-snap="{e(r["id"])}">Restore…</button></td></tr>'
            for r in rows)
        table = (f'<table class="ksnaps"><thead><tr><th scope="col">Snapshot</th><th scope="col">Taken</th>'
                 f'<th scope="col">Note</th><th scope="col">Files</th><th scope="col">Actions</th></tr></thead>'
                 f'<tbody>{trs}</tbody></table>')
    else:
        table = '<p class="note">No snapshots yet. The first save here takes one.</p>'
    return ('<section class="kpanel" id="p-snapshots" aria-labelledby="h-snapshots" hidden>'
            '<h2 id="h-snapshots">Snapshots</h2><p class="note kgroup-help">A copy of Kit\'s configuration (the run '
            'settings, setup files, JSON configs, and Kit\'s permission rules), taken before every save here and '
            'before each install or update. Credentials are never in one. Restore shows the change first and takes a '
            'snapshot of the current state, so it can be undone. Kit\'s permission rules are restored only with '
            '<code>kit-config restore ID --include-permissions</code> in a terminal.</p>'
            '<p><label for="ksnap-note">Note </label><input id="ksnap-note" type="text" maxlength="200" '
            'placeholder="what this is before"> <button type="button" data-act="snap-take">Take a snapshot now</button></p>'
            f'{table}<div id="ksnap-box" aria-live="polite"></div></section>')


def render(items, wizard, review_html, snaps, csrf, nonce, idle_text, extra_css="", extra_js=""):
    c = ks.counts(items)
    navs, panels = group_panels(items)
    wiz_left = sum(1 for s in items if s["kind"] == "setup" and s["status"] == "not set")
    opts = "".join(f'<option value="{e(v)}">{e(t)}</option>' for v, t in SHOW_FILTERS)
    nav = (f'<nav id="knav" aria-label="Settings sections" data-first="{"setup" if wiz_left else ks.GROUPS[0][0]}"><ul>'
           f'<li><button type="button" data-panel="setup" aria-controls="p-setup"><span>Setup questions</span>'
           f'<span class="kn">{wiz_left}</span></button></li><li><hr></li>'
           + "".join(navs) +
           f'<li><hr></li><li><button type="button" data-panel="snapshots" aria-controls="p-snapshots">'
           f'<span>Snapshots</span><span class="kn">{len(snaps)}</span></button></li>'
           f'<li><button type="button" data-panel="review" aria-controls="p-review"><span>Review loop</span></button></li>'
           f'</ul></nav>')
    top = (f'<header class="ktop"><h1>Kit settings</h1>'
           f'<div class="ksearch" role="search"><label for="kq" class="vh">Search settings</label>'
           f'<input id="kq" type="search" placeholder="Search {len(items)} settings (press /)" autocomplete="off">'
           f'<label for="kshow" class="vh">Show</label><select id="kshow">{opts}</select>'
           f'<label><input id="kchanged" type="checkbox"> Only changed</label>'
           f'<span id="kfound" class="note" aria-live="polite"></span></div>'
           f'<span class="note">{c["set"]} changed, {c["not set"]} not set. This computer only; stops after {idle_text} idle.</span>'
           f'<button type="button" data-act="stop">Stop</button></header>')
    setup = (f'<section class="kpanel" id="p-setup" aria-labelledby="h-setup" hidden><h2 id="h-setup">Setup questions</h2>'
             f'<p class="note kgroup-help">The setup fields still not set, one at a time, the ones that hold Kit\'s '
             f'agents back most first. Preview shows the change before it\'s saved.</p>{wizard}</section>')
    review = f'<section class="kpanel" id="p-review" aria-labelledby="krev-h" hidden>{review_html}</section>'
    barhtml = ('<div id="kbar" role="region" aria-label="Unsaved changes" hidden><div class="kbar-row">'
               '<span id="kbar-n" aria-live="polite"></span>'
               '<button type="button" class="primary" id="kbar-review" data-act="batch-preview">Review &amp; save</button>'
               '<button type="button" data-act="discard">Discard all</button>'
               '<span class="note">Nothing is saved until you confirm. A snapshot is taken first.</span></div>'
               '<div id="kreview" aria-live="polite" hidden></div></div>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="color-scheme" content="light dark">'
            f'<meta name="kit-csrf" content="{e(csrf)}"><title>Kit settings</title>'
            f'<style nonce="{nonce}">{CSS}{extra_css}</style></head><body>{top}'
            f'<div class="klayout">{nav}<main id="kmain">{setup}{"".join(panels)}{snapshots_panel(snaps)}{review}</main></div>'
            f'{barhtml}<script nonce="{nonce}">{extra_js}{JS}</script></body></html>')
