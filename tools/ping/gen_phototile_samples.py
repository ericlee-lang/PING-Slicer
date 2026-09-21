#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""照片磚內建範例圖：把 resources/images/phototile_samples/ 生成 resources/web/phototile/samples.js。

為什麼要生成 data URI 而不是讓頁面自己讀檔：
  工作室是 `file://` 載入（WebViewDialog.cpp），`fetch()` 會被 CORS 擋、
  `<img src=file://>` 畫到 canvas 又會 taint ⇒ 拿不到位元組送給 C++ 引擎。
  款式庫 `款式庫_照片磚.json` 內嵌進 index.html 是同一個理由。

正本＝`resources/images/phototile_samples/`（manifest.json ＋ *.jpg）。
改圖或改清單之後**一定要重跑這支**，否則 tools/ping/phototile_samples_test.js 會紅。
"""
import base64, io, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC  = os.path.join(ROOT, 'resources', 'images', 'phototile_samples')
OUT  = os.path.join(ROOT, 'resources', 'web', 'phototile', 'samples.js')

HEAD = (u'/* 自動生成，不要手改。\n'
        u'   正本＝resources/images/phototile_samples/（manifest.json ＋ *.jpg）\n'
        u'   重生＝python tools/ping/gen_phototile_samples.py\n'
        u'   為什麼是 data URI：工作室是 file:// 載入，'
        u'fetch() 被 CORS 擋、file:// 圖畫進 canvas 又會 taint，'
        u'拿不到位元組送給引擎。 */\n')


def build():
    man = json.load(io.open(os.path.join(SRC, 'manifest.json'), encoding='utf-8'))
    items = []
    for it in man['items']:
        raw = open(os.path.join(SRC, it['file']), 'rb').read()
        # subject＝題材（款式庫 subjects 的 id）：點範例直接套、不再問「主角是？」（牌 c-0918-PTS-01）。
        # 用 it['subject'] 而不是 .get()——manifest 漏填要當場炸，不要生出一張沒題材的範例。
        items.append({'name': it['name'], 'cat': it['cat'], 'mode': it['mode'], 'subject': it['subject'],
                      'file': it['file'],
                      'src': 'data:image/jpeg;base64,' + base64.b64encode(raw).decode('ascii')})
    body = ',\n'.join(json.dumps(i, ensure_ascii=False, sort_keys=True) for i in items)
    return HEAD + 'var PT_SAMPLES=[\n' + body + '\n];\n'


def main():
    text = build()
    check = '--check' in sys.argv
    old = io.open(OUT, encoding='utf-8').read() if os.path.exists(OUT) else None
    if check:
        if old == text:
            print('OK  samples.js 與圖檔一致')
            return 0
        print('DRIFT  samples.js 跟 resources/images/phototile_samples/ 對不上'
              '——請重跑 python tools/ping/gen_phototile_samples.py')
        return 1
    io.open(OUT, 'w', encoding='utf-8', newline='\n').write(text)
    print('寫出 %s（%.0f KB，%d 張）'
          % (os.path.relpath(OUT, ROOT), len(text.encode('utf-8')) / 1024.0, text.count('"src"')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
