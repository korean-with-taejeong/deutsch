#!/usr/bin/env python3
"""Model audio for a practice set: ElevenLabs text-to-speech, alignment, pauses.

The API key is read from the environment variable ELEVENLABS_API_KEY and never written anywhere.

  python3 tools/audio.py credits
  python3 tools/audio.py tts    sets/<id>.json [--only a,c] [--dict DICT_ID:VERSION_ID]
        one request per paragraph to /v1/text-to-speech/{voice}/with-timestamps
        -> work/<id>/<p>.mp3 + work/<id>/<p>.align.json
  python3 tools/audio.py align  sets/<id>.json <p> my-file.mp3
        your own mp3 (e.g. made on the ElevenLabs website) for paragraph <p>,
        matched to the script with /v1/forced-alignment -> same files as tts
  python3 tools/audio.py timing sets/<id>.json
        joins the paragraphs (with set["gap"] seconds of silence between them) into audio/<id>.mp3,
        word times from the alignment, real pauses from the silences in the audio
        -> sets/<id>.timing.json
"""
import base64, json, os, re, subprocess, sys, urllib.error, urllib.request, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setlib

API = 'https://api.elevenlabs.io'
LET = re.compile(r'[A-Za-zÄÖÜäöüß0-9]')
SR = 44100


def key():
    k = os.environ.get('ELEVENLABS_API_KEY')
    if not k:
        sys.exit('Set ELEVENLABS_API_KEY first.')
    return k


def call(path, body=None, form=None):
    hdr = {'xi-api-key': key()}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); hdr['Content-Type'] = 'application/json'
    if form is not None:
        b = '----de' + uuid.uuid4().hex
        parts = []
        for n, v in form.items():
            if isinstance(v, tuple):
                parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{n}"; filename="{v[0]}"\r\nContent-Type: {v[1]}\r\n\r\n'.encode() + v[2] + b'\r\n')
            else:
                parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n'.encode())
        data = b''.join(parts) + f'--{b}--\r\n'.encode(); hdr['Content-Type'] = 'multipart/form-data; boundary=' + b
    req = urllib.request.Request(API + path, data=data, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=300) as f:
            return json.load(f), {k.lower(): v for k, v in f.headers.items()}
    except urllib.error.HTTPError as e:
        sys.exit(f'{path}: HTTP {e.code} {e.read()[:500].decode("utf-8", "replace")}')


def credits():
    s, _ = call('/v1/user/subscription')
    return s['character_limit'] - s['character_count'], s['character_count'], s['character_limit']


def cmd_credits():
    left, used, lim = credits()
    print(f'{left} credits left ({used} of {lim} used)')


def cmd_tts(set_path, only=None, dict_loc=None):
    st = setlib.load(set_path); v = st['voice']
    out = setlib.paths(st['id'])['parts']; os.makedirs(out, exist_ok=True)
    before = credits()[0]
    for p in st['paras']:
        if only and p['id'] not in only:
            continue
        text = setlib.para_text(p)
        body = {'text': text, 'model_id': v['model'], 'language_code': 'de',
                'voice_settings': {'stability': v['stability'], 'similarity_boost': v['similarity']}}
        if dict_loc:
            did, ver = dict_loc.split(':')
            body['pronunciation_dictionary_locators'] = [{'pronunciation_dictionary_id': did, 'version_id': ver}]
        d, h = call(f'/v1/text-to-speech/{v["id"]}/with-timestamps?output_format=mp3_44100_128', body)
        open(os.path.join(out, p['id'] + '.mp3'), 'wb').write(base64.b64decode(d['audio_base64']))
        al = d['alignment']
        json.dump({'text': text, 'chars': al['characters'], 'start': al['character_start_times_seconds'],
                   'end': al['character_end_times_seconds'], 'source': 'tts', 'cost': h.get('character-cost')},
                  open(os.path.join(out, p['id'] + '.align.json'), 'w'), ensure_ascii=False)
        print(p['id'], len(text), 'chars', 'cost', h.get('character-cost'), 'audio', round(al['character_end_times_seconds'][-1], 2), 's')
    after = credits()[0]
    print(f'used {before - after} credits this run, {after} left')


def cmd_align(set_path, pid, mp3):
    st = setlib.load(set_path)
    p = next(x for x in st['paras'] if x['id'] == pid)
    text = setlib.para_text(p)
    out = setlib.paths(st['id'])['parts']; os.makedirs(out, exist_ok=True)
    audio = open(mp3, 'rb').read()
    d, _ = call('/v1/forced-alignment', form={'file': (os.path.basename(mp3), 'audio/mpeg', audio), 'text': text})
    ch = d['characters']  # [{text, start, end}]
    got = ''.join(c['text'] for c in ch)
    if got != text:
        print('warning: aligned text differs from the script; check the result', file=sys.stderr)
    open(os.path.join(out, pid + '.mp3'), 'wb').write(audio)
    json.dump({'text': got, 'chars': [c['text'] for c in ch], 'start': [c['start'] for c in ch], 'end': [c['end'] for c in ch], 'source': 'forced-alignment'},
              open(os.path.join(out, pid + '.align.json'), 'w'), ensure_ascii=False)
    print(pid, 'aligned', len(ch), 'characters')


def silences(path, db=-38, d=0.10):
    err = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-af', f'silencedetect=noise={db}dB:d={d}', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', err)]
    en = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', err)]
    return list(zip(st, en + [1e9] * (len(st) - len(en))))


def pcm(path):
    return subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 's16le', '-ac', '1', '-ar', str(SR), '-'], capture_output=True, check=True).stdout


def word_times(al, words):
    """character alignment -> [s, e] per script word (e = end of the last letter)"""
    text = ''.join(al['chars'])
    toks = list(re.finditer(r'\S+', text))
    if [t.group() for t in toks] != [setlib.plain(w['t']) for w in words]:
        raise SystemExit('alignment words differ from the script')
    out = []
    for m in toks:
        idx = [k for k in range(m.start(), m.end()) if LET.match(text[k])] or list(range(m.start(), m.end()))
        out.append([round(al['start'][idx[0]], 3), round(al['end'][idx[-1]], 3)])
    return out


def gap_between(sil, a, b):
    """seconds of real silence between time a (end of a word) and b (start of the next)"""
    return round(sum(max(0.0, min(y, b + 0.03) - max(x, a - 0.03)) for x, y in sil), 3)


def cmd_timing(set_path):
    st = setlib.load(set_path); P = setlib.paths(st['id'])
    gap = float(st.get('gap', 0.75))
    words_all, seg_gap, word_gap, paras, buf, t0, sil_all = [], [], [], {}, bytearray(), 0.0, []
    for p in st['paras']:
        mp3 = os.path.join(P['parts'], p['id'] + '.mp3')
        al = json.load(open(os.path.join(P['parts'], p['id'] + '.align.json'), encoding='utf-8'))
        segw = [setlib.parse_seg(s[0]) for s in p['segs']]
        flat = [w for ws in segw for w in ws]
        wt = word_times(al, flat)
        sil = silences(mp3)
        raw = pcm(mp3); dur = len(raw) / 2 / SR
        has = [bool(LET.search(setlib.plain(w['t']))) for w in flat]  # '–' and the like carry no sound
        nxt = lambda i: next((x for x in range(i, len(flat)) if has[x]), None)
        k = 0
        for si, ws in enumerate(segw):
            lw = max(x for x in range(k, k + len(ws)) if has[x])  # last sounding word of the segment
            for j in range(k, k + len(ws)):
                if not has[j]:
                    continue
                n = nxt(j + 1)
                a, b = wt[j][1], (wt[n][0] if n is not None else dur)
                g = gap_between(sil, a, b)
                if j == lw:
                    seg_gap.append(g if si < len(segw) - 1 else None)
                    break
                word_gap.append([len(words_all) + j, g])
            k += len(ws)
        words_all += [[round(s + t0, 3), round(e + t0, 3)] for s, e in wt]
        sil_all += [[round(x + t0, 3), round(min(y, dur) + t0, 3)] for x, y in sil]
        paras[p['id']] = {'off': round(t0, 3), 'dur': round(dur, 3)}
        buf += raw
        t0 += dur
        if p is not st['paras'][-1]:
            n = int(round(gap * SR)); buf += b'\0\0' * n; t0 += n / SR
    os.makedirs(os.path.dirname(P['audio']), exist_ok=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', '-', '-c:a', 'libmp3lame', '-b:a', '128k', P['audio']],
                   input=bytes(buf), check=True)
    json.dump({'dur': round(t0, 3), 'gap': gap, 'paras': paras, 'words': words_all, 'segGap': seg_gap, 'wordGap': [x for x in word_gap if x[1] >= 0.1], 'sil': sil_all},
              open(P['timing'], 'w'), ensure_ascii=False, indent=0)
    print('wrote', os.path.relpath(P['audio'], setlib.ROOT), round(t0, 2), 's and', os.path.relpath(P['timing'], setlib.ROOT))


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    opt = {x.split('=', 1)[0]: (x.split('=', 1)[1] if '=' in x else True) for x in a if x.startswith('--')}
    a = [x for x in a if not x.startswith('--')]
    if a[0] == 'credits':
        cmd_credits()
    elif a[0] == 'tts':
        cmd_tts(a[1], only=set(opt['--only'].split(',')) if '--only' in opt else None, dict_loc=opt.get('--dict'))
    elif a[0] == 'align':
        cmd_align(a[1], a[2], a[3])
    elif a[0] == 'timing':
        cmd_timing(a[1])
    else:
        sys.exit(__doc__)
