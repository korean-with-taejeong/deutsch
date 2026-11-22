# Deutsch · 발음 연습

독일어 원고로 만드는 발음 연습 앱. 원어민 음성을 듣고 → 덩어리로 따라 하고 → 녹음해서 원어민과 비교하고 → 스스로 확인해요.

- 연습 목록: https://korean-with-taejeong.github.io/deutsch/
- 녹음과 진행 상황은 각 기기(브라우저)에만 저장돼요. 아무 데도 올라가지 않아요.

## 구조

| 경로 | 내용 |
|---|---|
| `index.html` | 연습 목록 (날짜, 제목, 용도, D-day). `tools/build.py`가 만들어요 |
| `sets/<id>.json` | 연습 데이터: 원고(강세·IPA·쉼 표시), 억양, 단락, 번역, 표시 설명, 표현 카드, 체크리스트 |
| `sets/<id>.timing.json` | 단어별 시간, 실제 쉼(무음 구간). `tools/audio.py timing`이 만들어요 |
| `sets/<id>.html` | 실제로 여는 앱 (음원 포함 파일 하나) |
| `audio/<id>.mp3` | 원어민 음성 (ElevenLabs, 단락 사이 0.75초) |
| `template/de-practice-template.html` | 앱 템플릿 (자기소개_발음연습.html의 디자인 + 한국어 앱의 녹음·비교·저장) |
| `tools/` | `audio.py` (음성·시간 맞추기), `build.py` (앱·목록 만들기), `setlib.py` (원고 표시 읽기) |
| `vendor/lame.min.js` | m4a로 녹음이 안 되는 기기에서 mp3로 바꾸는 인코더 (LAME, LGPL, lame.sourceforge.net) |

## 원고 표시법 (`sets/<id>.json`의 `segs`)

```
["Grüß[ɡʁyːs] {Gott} zu{sam}men,[tsuˈzamən]", "↘"]
["mit Ende {zwan}zig nach {Deutsch}land, | um {Uhr}macher zu werden!", "↘", "laugh"]
```

- `{…}` 강세 음절 (굵게 + 밑줄)
- `[…]` 단어 바로 뒤에 IPA (단어 위에 작게, 누르면 그 단어만 재생)
- `|` 문장 안의 짧은 쉼 (실제 음성에서 쉰 곳만)
- 억양: `↘` 평서문·명령문·의문사 질문, `↗` 예/아니요 질문, `→` 이어짐
- `"laugh"` 농담·관용구 뒤 웃음 기다리기 표시
- 문장 끝의 쉼(`|` / `||`)은 음성의 무음 길이로 자동으로 정해져요 (0.12초 이상 / 0.42초 이상)
- 표시 설명 `items`: `["강세"|"억양"|"쉼"|"발음", 문장 번호(단락 안), 단어 또는 "@t"(억양) "@p"(문장 끝 쉼) "@q"(문장 안 쉼) "@l"(웃음), "설명"]`

## 새 연습 만들기

```sh
# 1) sets/<날짜-이름>.json 작성 (기존 파일을 복사해서 고치기)
export ELEVENLABS_API_KEY=...        # 파일에 저장하지 않기
python3 tools/audio.py credits
python3 tools/audio.py tts    sets/<id>.json          # 단락별 음성 + 글자별 시간 → work/<id>/
#    직접 만든 mp3를 쓸 때:  python3 tools/audio.py align sets/<id>.json a 내파일.mp3
python3 tools/audio.py timing sets/<id>.json          # 이어 붙이기, 단어 시간, 실제 쉼 측정
python3 tools/build.py        sets/<id>.json          # 앱과 목록 만들기 (표시 단어·쉼 검사 포함)
```

`build.py`는 표시한 단어가 그 문장에 정말 있는지, `|` 표시가 실제 쉼과 맞는지 검사하고 맞지 않으면 알려 줘요.

음성: ElevenLabs `eleven_v4`, Leon (`KJGvwDt0zADAAvDmMQEN`), stability 0.69, similarity 0.75.
