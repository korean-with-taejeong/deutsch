"""Shared helpers: read a practice set (sets/<id>.json) and parse its segment markup.

Segment markup (one string per segment):
    Grüß[ɡʁyːs] {Gott} zu{sam}men,[tsuˈzamən]
  - words are separated by spaces
  - {...}   the stressed syllable (shown bold + underlined)
  - [...]   IPA, written straight after the word (after its punctuation); shown small above the word
  - |       a short pause inside the segment, after the previous word
A segment is [markup, tone] or [markup, tone, "laugh"]; tone is ↘ / ↗ / →.
"laugh" adds a 웃음 marker after the segment: wait for the audience in the real talk.
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = re.compile(r'^(?P<t>.+?)(?:\[(?P<ipa>[^\]]+)\])?$')
PUNCT = '„“”"‚‘’\'.,:;!?–—()…'


def load(path):
    return json.load(open(path, encoding='utf-8'))


def parse_seg(markup):
    """-> list of words {t (with braces), ipa?, q? (pause after)}"""
    words = []
    for tok in markup.split():
        if tok == '|':
            if not words:
                raise ValueError('pause mark | at segment start: ' + markup)
            words[-1]['q'] = 1
            continue
        m = TOKEN.match(tok)
        w = {'t': m.group('t')}
        if m.group('ipa'):
            w['ipa'] = m.group('ipa')
        if w['t'].count('{') != w['t'].count('}'):
            raise ValueError('unbalanced { } in ' + tok)
        words.append(w)
    return words


def plain(t):
    return t.replace('{', '').replace('}', '')


def bare(t):
    """word without braces and surrounding punctuation, for matching item targets"""
    return plain(t).strip(PUNCT)


def para_text(para):
    """the text sent to text-to-speech for one paragraph"""
    out = []
    for seg in para['segs']:
        out.extend(plain(w['t']) for w in parse_seg(seg[0]))
    return ' '.join(out)


def paths(set_id):
    return {
        'set': os.path.join(ROOT, 'sets', set_id + '.json'),
        'timing': os.path.join(ROOT, 'sets', set_id + '.timing.json'),
        'html': os.path.join(ROOT, 'sets', set_id + '.html'),
        'audio': os.path.join(ROOT, 'audio', set_id + '.mp3'),
        'parts': os.path.join(ROOT, 'work', set_id),  # per-paragraph audio + alignment (not committed)
    }
