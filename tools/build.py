#!/usr/bin/env python3
"""Build a practice page and the index.

  python3 tools/build.py sets/<id>.json [more sets...]
  python3 tools/build.py --index           (only rebuild index.html)

Reads   template/de-practice-template.html, sets/<id>.json (content), sets/<id>.timing.json and audio/<id>.mp3
        (both made by tools/audio.py).
Writes  sets/<id>.html (one self-contained page, audio inside) and index.html (list of all practices).
Checks  every marked word exists in its sentence, pause marks match real pauses in the audio.
"""
import base64, glob, html, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setlib

ROOT = setlib.ROOT
TONES = {'↘', '↗', '→'}
TYPES = {'강세', '억양', '쉼', '발음'}


def fail(msg):
    raise SystemExit('ERROR: ' + msg)


def dur_ko(s):
    s = int(round(s))
    return f'{s // 60}분 {s % 60}초' if s >= 60 else f'{s}초'


def compile_set(st, tm):
    long_p, short_p = st.get('pauseLong', 0.42), st.get('pauseShort', 0.12)
    W, S, P, warn = [], [], [], []
    seg_gap = tm['segGap']
    for p in st['paras']:
        s0 = len(S)
        for li, seg in enumerate(p['segs']):
            if seg[1] not in TONES:
                fail(f'{p["key"]}{li}: tone must be ↘ ↗ →')
            ws = setlib.parse_seg(seg[0])
            a = len(W)
            W.extend(ws)
            g = seg_gap[len(S)]
            pause = '' if g is None else ('||' if g >= long_p else '|' if g >= short_p else '')
            S.append({'w': [a, len(W) - 1], 'tone': seg[1], 'pause': pause, 'gap': g, 'laugh': 1 if 'laugh' in seg[2:] else 0, 'para': p['id']})
        P.append((p, s0, len(S) - 1))
    if len(W) != len(tm['words']):
        fail(f'{len(W)} words in the script but {len(tm["words"])} in the timing file; run tools/audio.py timing again')
    for j, (s, e) in enumerate(tm['words']):
        W[j]['s'], W[j]['e'] = s, e
    # inline pauses must be real; real inner pauses should be marked
    gaps = {j: g for j, g in tm.get('wordGap', [])}
    for j, w in enumerate(W):
        if w.get('q') and gaps.get(j, 0) < short_p:
            warn.append(f'| after "{setlib.plain(w["t"])}" but the audio pauses only {gaps.get(j, 0):.2f}s there')
        if not w.get('q') and gaps.get(j, 0) >= 0.18:
            warn.append(f'audio pauses {gaps[j]:.2f}s after "{setlib.plain(w["t"])}" but there is no | mark')
    # snap word edges to real silences: the alignment often starts the first word after a pause late
    sil = tm.get('sil', [])
    sounding = [any(c.isalnum() for c in setlib.plain(w['t'])) for w in W]
    for j in range(len(W)):
        if not sounding[j]:
            continue
        pj = next((k for k in range(j - 1, -1, -1) if sounding[k]), None)
        lo = W[pj]['e'] - 0.12 if pj is not None else -1
        for x0, x1 in sil:  # silence ending just before this word -> speech starts at its end
            if x0 >= lo and x0 < W[j]['s'] and W[j]['s'] - 0.4 < x1 < W[j]['s'] + 0.12 and abs(x1 - W[j]['s']) > 0.02:
                W[j]['s'] = round(x1 - 0.01, 3)
        nj = next((k for k in range(j + 1, len(W)) if sounding[k]), None)
        hi = W[nj]['s'] if nj is not None else 1e9
        for x0, x1 in sil:  # silence starting just after this word -> speech lasts until its start
            if W[j]['e'] < x0 < min(W[j]['e'] + 0.35, hi):
                W[j]['e'] = round(x0, 3)
                break
    # playback windows for each segment: they meet inside the real pause between two segments
    paras = tm['paras']
    def last_sounding(sg):
        return max(k for k in range(sg['w'][0], sg['w'][1] + 1) if sounding[k])
    for i, sg in enumerate(S):
        a = sg['w'][0]; b = last_sounding(sg)
        off = paras[sg['para']]['off']; pend = off + paras[sg['para']]['dur']
        if i == 0 or S[i - 1]['para'] != sg['para']:
            st_ = off
        else:
            pb = last_sounding(S[i - 1]); pe, ns = W[pb]['e'], W[a]['s']
            gaps = [(x0, x1) for x0, x1 in sil if x0 >= pe - 0.05 and x1 <= ns + 0.15 and x1 > x0]
            if gaps:
                x0, x1 = gaps[-1]
                S[i - 1]['t'][1] = round(min(x1 - 0.03, x0 + 0.3), 3)
                st_ = max(S[i - 1]['t'][1], x1 - 0.06)
            else:
                st_ = round((pe + ns) / 2, 3); S[i - 1]['t'][1] = st_
        last = i + 1 == len(S) or S[i + 1]['para'] != sg['para']
        sg['t'] = [round(st_, 3), round(min(pend, W[b]['e'] + 0.35), 3) if last else None]
    out_p = []
    for p, s0, s1 in P:
        n = s1 - s0 + 1
        def G(li, where):
            if not (0 <= li < n):
                fail(f'paragraph {p["key"]}: {where} refers to sentence {li}, but there are only {n}')
            return s0 + li
        items = []
        for it in p['items']:
            ty, li, tg, tx = it
            if ty not in TYPES:
                fail(f'{p["key"]}: item type {ty}')
            gi = G(li, 'item'); sg = S[gi]
            if tg == '@t':
                ref = '@t'
            elif tg == '@p':
                if not sg['pause'] and not (sg['laugh']):
                    warn.append(f'{p["key"]}{li}: item points at a pause, but the audio does not pause after this sentence')
                ref = '@p'
            elif tg == '@l':
                if not sg['laugh']:
                    fail(f'{p["key"]}{li}: @l but the sentence has no "laugh"')
                ref = '@l'
            elif tg == '@q':
                q = [j for j in range(sg['w'][0], sg['w'][1] + 1) if W[j].get('q')]
                if not q:
                    fail(f'{p["key"]}{li}: @q but no | in the sentence')
                ref = '@q'
            else:
                name, _, nth = tg.partition('#')
                hits = [j for j in range(sg['w'][0], sg['w'][1] + 1) if setlib.bare(W[j]['t']) == name]
                if len(hits) < int(nth or 1):
                    fail(f'{p["key"]}{li}: "{name}" is not in "{" ".join(setlib.plain(W[j]["t"]) for j in range(sg["w"][0], sg["w"][1] + 1))}"')
                ref = hits[int(nth or 1) - 1]
            items.append([ty, gi, ref, tx])
        out_p.append({'id': p['id'], 'key': p['key'], 'title': p['title'], 'segs': [s0, s1],
                      'chunks': [[G(x, 'chunk') for x in c] for c in p['chunks']], 'tr': p['tr'], 'items': items,
                      'why': p.get('why', []), 'idi': [dict(d, s=G(d['s'], 'expression')) for d in p.get('idi', [])], 'checks': p['checks']})
    for sg in S:
        del sg['gap'], sg['para']
    model = dur_ko(tm['dur'])
    data = {k: st[k] for k in ('id', 'title', 'short', 'h1', 'h1b', 'purpose', 'date', 'when', 'place', 'level') if k in st}
    data.update({'voice': st['voice']['name'], 'dur': tm['dur'], 'words': W, 'segs': S, 'paras': out_p,
                 'fullChecks': [c.replace('{dur}', model) for c in st.get('fullChecks', [])], 'tips': st.get('tips', [])})
    return data, warn


def build(set_path):
    st = setlib.load(set_path)
    P = setlib.paths(st['id'])
    tm = setlib.load(P['timing'])
    data, warn = compile_set(st, tm)
    for w in warn:
        print('  check:', w)
    tpl = open(os.path.join(ROOT, 'template', 'de-practice-template.html'), encoding='utf-8').read()
    audio = open(os.path.join(ROOT, st['audio']), 'rb').read()
    js = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    out = (tpl.replace('/*__TITLE__*/', html.escape(st['h1'] + ' · ' + st['title']))
              .replace('/*__SET__*/{}', js)
              .replace('/*__AUDIO__*/', 'data:audio/mpeg;base64,' + base64.b64encode(audio).decode())
              .replace('/*__LAME__*/', '../vendor/lame.min.js')
              .replace('/*__INDEX__*/', '../index.html'))
    for ph in ('/*__TITLE__*/', '/*__SET__*/', '/*__AUDIO__*/', '/*__LAME__*/', '/*__INDEX__*/'):
        if ph in out:
            fail('placeholder left: ' + ph)
    open(P['html'], 'w', encoding='utf-8').write(out)
    print('wrote', os.path.relpath(P['html'], ROOT), len(out) // 1024, 'KB,', len(data['words']), 'words,', len(data['segs']), 'sentences')


def build_index():
    sets = []
    for p in glob.glob(os.path.join(ROOT, 'sets', '*.json')):
        if p.endswith('.timing.json'):
            continue
        s = setlib.load(p)
        if os.path.exists(setlib.paths(s['id'])['html']):
            sets.append(s)
    sets.sort(key=lambda s: s.get('date', ''), reverse=True)
    rows = json.dumps([{'id': s['id'], 'title': s['title'], 'h1': s.get('h1', ''), 'purpose': s.get('purpose', ''), 'date': s.get('date', ''),
                        'place': s.get('place', ''), 'level': s.get('level', '')} for s in sets], ensure_ascii=False).replace('</', '<\\/')
    open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8').write(INDEX.replace('/*__SETS__*/[]', rows))
    print('wrote index.html with', len(sets), 'practice(s)')


INDEX = r'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Deutsch · 발음 연습</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22%3E%3Ccircle cx=%2216%22 cy=%2216%22 r=%2214%22 fill=%22%23F28C28%22/%3E%3Cpath d=%22M16 8v8l5 3%22 stroke=%22%232B1700%22 stroke-width=%223%22 fill=%22none%22 stroke-linecap=%22round%22/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;500;700&family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{color-scheme:light;--bg:#FAF7F2;--bg2:#F2ECE3;--card:#FFFFFF;--line:#E6DCCF;--ink:#2B2420;--hi:#1C1713;--mut:#6B5F56;--dim:#998C81;--y:#F28C28;--yi:#2B1700;--at:#B4560F}
:root[data-look=night]{color-scheme:dark;--bg:#1F1A16;--bg2:#2A231E;--card:#28211C;--line:#3D342C;--ink:#F1EAE0;--hi:#FFF8EF;--mut:#C0B3A6;--dim:#8F8277;--y:#F5A04A;--yi:#2B1700;--at:#F5A04A}
*{box-sizing:border-box;min-width:0}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 "IBM Plex Sans KR",-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif}
main{max-width:680px;margin:0 auto;padding:calc(36px + env(safe-area-inset-top)) 20px calc(48px + env(safe-area-inset-bottom))}
.ov{font-size:12.5px;font-weight:700;color:var(--at)}
h1{font-size:clamp(28px,6.4vw,36px);line-height:1.15;margin:4px 0 10px;color:var(--hi)}
.lead{color:var(--mut);margin:0 0 22px}
.pc{display:flex;gap:16px;align-items:center;padding:16px 18px;background:var(--card);border:1.5px solid var(--line);border-radius:22px;margin-bottom:12px;color:inherit;text-decoration:none}
.pc.nx{border-color:var(--y)}
.dt{width:56px;flex:none;text-align:center;border-radius:14px;background:var(--bg2);padding:7px 0;line-height:1.15}
.dt b{display:block;font-size:20px;color:var(--at)}.dt span{font-size:12px;color:var(--mut)}
.pb{flex:1}
.pt{display:block;font-weight:700;font-size:16.5px;color:var(--hi);font-family:"Atkinson Hyperlegible Next","IBM Plex Sans KR",sans-serif}
.meta{display:block;font-size:13px;color:var(--mut)}
.chip{font-size:12px;font-weight:700;padding:5px 10px;border-radius:999px;background:var(--bg2);color:var(--mut);white-space:nowrap;flex:none}
.chip.y{background:var(--y);color:var(--yi)}
.foot{font-size:12.5px;color:var(--dim);margin-top:24px}
</style>
</head>
<body>
<main>
<div class="ov">Deutsch · 발음 연습</div>
<h1>내 연습 목록</h1>
<p class="lead">원어민 음성을 듣고, 덩어리로 따라 하고, 녹음해서 비교해요. 새 연습이 생기면 여기에 추가돼요.</p>
<div id="list"></div>
<p class="foot">녹음과 진행 상황은 각자의 기기에만 저장돼요.</p>
</main>
<script>
const SETS=/*__SETS__*/[];
try{if(localStorage.getItem('de:look')==='"night"')document.documentElement.dataset.look='night'}catch(e){}
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const today=new Date();const t0=new Date(today.getFullYear(),today.getMonth(),today.getDate());
const dd=s=>{if(!s)return null;const [y,m,d]=s.split('-').map(Number);return Math.round((new Date(y,m-1,d)-t0)/864e5)};
let nextShown=false;
document.getElementById('list').innerHTML=SETS.map(s=>{const n=dd(s.date),[y,m,d]=(s.date||'--').split('-');
 const chip=n==null?'':n>0?'D-'+n:n===0?'D-day':'끝';const up=n!=null&&n>=0;
 return '<a class="pc'+(up?' nx':'')+'" href="sets/'+encodeURIComponent(s.id)+'.html"><span class="dt"><b>'+esc(+d||'')+'</b><span>'+esc(m?(+m)+'월':'')+'</span></span><span class="pb"><span class="pt">'+esc(s.title)+'</span><span class="meta">'+esc([s.h1,s.purpose,s.place,s.level].filter(Boolean).join(' · '))+'</span><span class="meta">'+esc(s.date)+'</span></span>'+(chip?'<span class="chip'+(up?' y':'')+'">'+chip+'</span>':'')+'</a>'}).join('')||'<p class="lead">아직 연습이 없어요.</p>';
</script>
</body>
</html>
'''

if __name__ == '__main__':
    args = sys.argv[1:]
    for a in args:
        if a != '--index':
            build(a)
    build_index()
