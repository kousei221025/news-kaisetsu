"""3分ニュース解説：src/ の記事からサイト全体を作る。

使い方：python build.py

記事ファイル src/articles/<スラッグ>.html の形：
<!--
{
  "title": "記事タイトル",
  "date": "2026-11-04",
  "category": "economy",          # world / economy / life / basics
  "description": "検索結果や一覧に出る説明文",
  "summary": ["3行まとめ1", "3行まとめ2", "3行まとめ3"],
  "rank": 5,                      # 同じ日付の中で大きいほど上に出る（省略可）
  "terms": ["basics-yen"],        # 用語メモに出す基礎解説記事のスラッグ（無ければ省略）
  "eyecatch": "円安",             # サムネイル画像に大きく出す言葉（短く。省略するとジャンル名）
  "impact": "輸入品が値上がりしやすい",  # ニュースだけ：一覧に出す「生活への影響」1行（記事の内容から）
  "keywords": ["円安", "円高"],   # 基礎解説だけ：他の記事の本文でこの言葉が出たら自動でリンクする
  "sources": [["出典名", "URL"]]
}
-->
<h2>何が起きた？</h2>
<p>本文…</p>

棒グラフ：本文の好きな場所に次のように書く（数字は出典で確かめたものだけ）。
<!--bars グラフの題名（いつの数字か）
項目名|数字|単位
*項目名|数字|単位　← 先頭に * を付けると、その棒がオレンジで強調される（今の値など、一番見てほしい1本に）
出典：〇〇-->

流れ図：「なぜ生活に関係するか」のつながりを、本文に次のように書く（3〜5段。最後が生活への影響。出典で確かめたつながりだけ）。
<!--flow 題名
原因
起きること
生活への影響-->

これからの予定：src/schedule.json（date・time・label・note・article（関係する基礎解説のスラッグ）・source。日付は出典で確かめたものだけ。過ぎた予定は自動で表示されない）

数字の帯：src/numbers.json（"trend": "up"/"down"/"flat" と "trend_note" は、記事で上がった・下がったを確かめたときだけ入れる）（label・value・note（いつの数字か）・article（根拠の記事スラッグ））。
記事で確かめた数字だけを入れ、古くなったら更新する。

作られるもの：articles/*.html、index.html、category/*.html、search.html、search.json、
404.html、feed.xml、sitemap.xml、robots.txt、固定ページ（src/pages）、og/*.png（SNS用画像）
"""
import html
import json
import math
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).parent
SRC = ROOT / "src"
SITE_URL = "https://kousei221025.github.io/news-kaisetsu/"
SITE_PATH = "/news-kaisetsu/"
SITE_NAME = "3分ニュース解説"
TAGLINE = "世界と経済のニュースを、会社員目線で3分で"
AUTHOR = "ミナト"
GOOGLE_VERIFICATION = "NpGkUOpVZOv7Xnzv4UJs-QAGNuditPmdn-a93lYZJIo"  # Google Search Console の所有権確認
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

CATS = {
    "world": "世界情勢",
    "economy": "経済",
    "life": "くらし・お金",
    "basics": "基礎解説",
}
CAT_INTRO = {
    "world": "戦争や選挙、外交など、世界の動きが私たちの暮らしにどう関わるかを解説します。",
    "economy": "金利、円相場、物価など、ニュースでよく聞く経済の話題を会社員目線で解説します。",
    "life": "税金、ガソリン代、電気代など、家計に直接関わるニュースを解説します。",
    "basics": "ニュースを読むための基礎知識。一度読んでおくと、毎日のニュースがぐっと分かりやすくなります。",
}
# テーマ：タイトル・説明・3行まとめにキーワードが入っている記事を自動で集める
TOPICS = {
    "energy": ("中東・エネルギー", "原油・ガソリン・電気代など、中東情勢とエネルギー価格の動き。",
               ["原油", "ガソリン", "電気", "ホルムズ", "イラン", "中東"]),
    "rates": ("金利・円相場", "日銀の金融政策、金利、円安・円高の動き。",
              ["金利", "円安", "円高", "日銀", "利上げ", "ドル円", "158円"]),
    "household": ("税金・家計", "年末調整や補助金など、手取りや家計に直接関わる話題。",
                  ["年末調整", "税", "補助", "控除", "手取り"]),
    "us": ("アメリカ政治", "中間選挙や議会など、アメリカの政治の動き。",
           ["中間選挙", "上院", "下院"]),
    "russia": ("ロシア・ウクライナ", "ロシアとウクライナの戦闘と和平交渉の動き。", ["ロシア", "ウクライナ"]),
}

CAT_COLOR = {"world": "#1b4f8c", "economy": "#7a3e9d", "life": "#a8500e", "basics": "#2e7d5b"}

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='7' fill='%231b4f8c'/%3E%3Ctext x='16' y='23' "
           "font-size='20' font-weight='900' text-anchor='middle' fill='white' "
           "font-family='sans-serif'%3E3%3C/text%3E%3C/svg%3E")

e = html.escape


# ---------- 記事の読み込み ----------
def load_articles():
    items = []
    for f in sorted((SRC / "articles").glob("*.html")):
        text = f.read_text(encoding="utf-8")
        m = re.match(r"\s*<!--(.*?)-->(.*)", text, re.S)
        if not m:
            raise SystemExit(f"記事情報が読めません: {f.name}")
        meta = json.loads(m.group(1))
        meta["slug"] = f.stem
        meta["body"] = m.group(2).strip()
        meta.setdefault("terms", [])
        meta.setdefault("sources", [])
        meta.setdefault("keywords", [])
        if meta["category"] not in CATS:
            raise SystemExit(f"ジャンルが不正です: {f.name} {meta['category']}")
        items.append(meta)
    items.sort(key=lambda a: (a["date"], a.get("rank", 0), a["slug"]), reverse=True)
    return items


def plain(body):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body)).strip()


def reading_minutes(body):
    return max(1, math.ceil(len(plain(body).replace(" ", "")) / 500))


def jp_date(d):
    y, m, dd = d.split("-")
    return f"{int(y)}年{int(m)}月{int(dd)}日"


def md_date(d):
    _, m, dd = d.split("-")
    return f"{int(m)}月{int(dd)}日"


def add_heading_ids(body):
    heads = []

    def repl(m):
        n = len(heads) + 1
        heads.append(re.sub(r"<[^>]+>", "", m.group(1)))
        return f'<h2 id="s{n}">{m.group(1)}</h2>'

    return re.sub(r"<h2>(.*?)</h2>", repl, body), heads


# ---------- 用語の自動リンク ----------
def link_terms(body, arts, self_slug):
    """基礎解説の keywords が本文に出てきたら、記事ごとに最初の1回だけリンクする。"""
    linked = []
    for b in arts:
        if b["category"] != "basics" or b["slug"] == self_slug or not b["keywords"]:
            continue
        kws = sorted(b["keywords"], key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(k) for k in kws))
        parts = re.split(r"(<[^>]+>)", body)
        depth = 0  # a / h1-h3 / b の中はリンクしない
        done = False
        for i, p in enumerate(parts):
            if p.startswith("<"):
                if re.match(r"<(a|h[1-3]|b)\b", p):
                    depth += 1
                elif re.match(r"</(a|h[1-3]|b)>", p):
                    depth -= 1
                continue
            if depth or done:
                continue
            m = pattern.search(p)
            if m:
                parts[i] = (p[:m.start()] + f'<a class="term" href="{b["slug"]}.html" data-tip="{e((b.get("summary") or [b["description"]])[0])}">'
                            + m.group(0) + "</a>" + p[m.end():])
                done = True
                linked.append(b["slug"])
        body = "".join(parts)
    return body, linked


# ---------- 棒グラフ ----------
def render_bars(body):
    def repl(m):
        lines = [x.strip() for x in m.group(1).strip().splitlines() if x.strip()]
        title, rows, note = lines[0], [], ""
        for x in lines[1:]:
            if x.count("|") == 2:
                label, val, unit = x.split("|")
                hot = label.startswith("*")  # 先頭に * を付けた行は強調（オレンジ）
                rows.append((label.lstrip("*"), float(val), unit, hot))
            else:
                note = x
        mx = max(r[1] for r in rows)
        bars = "".join(
            f'<div class="bar-row{" hot" if h else ""}"><span class="bar-label">{e(l)}</span><span class="bar-track">'
            f'<span class="bar-fill" style="width:{v / mx * 100:.1f}%"></span></span>'
            f'<span class="bar-val">{v:,g}{e(u)}</span></div>' for l, v, u, h in rows)
        return (f'<figure class="bars"><figcaption>{e(title)}</figcaption>{bars}'
                + (f'<p class="bar-note">{e(note)}</p>' if note else "") + '</figure>')
    return re.sub(r"<!--bars(.*?)-->", repl, body, flags=re.S)


# ---------- 流れ図 ----------
def render_flow(body):
    """<!--flow 題名
    ステップ1
    ステップ2
    ...-->  を矢印でつないだ図にする。最後のステップは「生活への影響」としてオレンジ。"""
    def repl(m):
        lines = [x.strip() for x in m.group(1).strip().splitlines() if x.strip()]
        title, steps = lines[0], lines[1:]
        lis = "".join(f'<li{" class=\"last\"" if i == len(steps) - 1 else ""}><span>{e(s)}</span></li>' for i, s in enumerate(steps))
        return f'<figure class="flow"><figcaption>{e(title)}</figcaption><ol>{lis}</ol></figure>'
    return re.sub(r"<!--flow(.*?)-->", repl, body, flags=re.S)


# ---------- 数字を太字に ----------
NUM_RE = re.compile(r"\d[\d,.]*(?:万|億|兆)?(?:円|ドル|%|％|件|倍|人)(?:台|超|分)?")


def bold_numbers(body):
    """本文（p と li）の中の金額・％などを太字にする。見出しやリンクの中は触らない。"""
    parts = re.split(r"(<[^>]+>)", body)
    skip = 0
    for i, s in enumerate(parts):
        if s.startswith("<"):
            if re.match(r"<(a|h[1-3]|b|strong)[ >]", s):
                skip += 1
            elif re.match(r"</(a|h[1-3]|b|strong)>", s):
                skip -= 1
            continue
        if not skip:
            parts[i] = NUM_RE.sub(lambda m: f'<strong class="num">{m.group(0)}</strong>', s)
    return "".join(parts)


# ---------- SNS用画像 ----------
OG_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{css}"><style>
html,body{{margin:0;width:1200px;height:630px;overflow:hidden;background:#fff}}
body{{display:flex;font-family:"Noto Sans JP","Yu Gothic",sans-serif;color:#1c2024}}
.left{{width:470px;flex:none}} .left .art{{width:470px;height:630px;aspect-ratio:auto}}
.left .art-cat,.left .art-logo{{display:none}}
.right{{flex:1;display:flex;flex-direction:column;justify-content:space-between;padding:56px 60px 48px;border-top:14px solid {color}}}
.cat{{display:inline-block;background:{color};color:#fff;font-weight:700;font-size:26px;padding:4px 22px;border-radius:999px}}
h1{{font-size:{size}px;line-height:1.45;font-weight:900;margin:22px 0 0}}
.imp{{margin-top:22px;font-size:25px;line-height:1.55;color:#3a3f45}} .imp b{{background:#a8500e;color:#fff;font-size:20px;padding:2px 10px;border-radius:4px;margin-right:10px}}
.logo{{display:flex;align-items:center;gap:12px;font-weight:900;font-size:34px}} .logo b{{color:#1b4f8c}}
.logo i{{display:inline-grid;place-items:center;width:46px;height:46px;border-radius:10px;background:#1b4f8c;color:#fff;font-style:normal;font-size:28px}}
</style></head><body><div class="left">{art}</div><div class="right"><div><span class="cat">{cat}</span><h1>{title}</h1>{impact}</div>
<div class="logo"><i>3</i><span>3分<b>ニュース解説</b></span></div></div></body></html>"""


def make_og_images(arts):
    """og/<スラッグ>.png が無い記事だけ、Edge で画像にする。Edge が無ければ何もしない。"""
    out_dir = ROOT / "og"
    out_dir.mkdir(exist_ok=True)
    if not EDGE.exists():
        print("注意：Edge が見つからないため、SNS用画像は作りません")
        return
    jobs = [a for a in arts if not (out_dir / f"{a['slug']}.png").exists()]
    if not (out_dir / "default.png").exists():
        jobs.append({"slug": "default", "category": "world", "title": "むずかしいニュースを、会社員目線で3分で。",
                     "eyecatch": "3分解説", "body": "", "description": ""})
    with tempfile.TemporaryDirectory() as tmp:
        for a in jobs:
            title = a["title"]
            size = 54 if len(title) <= 30 else 48 if len(title) <= 40 else 44
            imp = (f'<p class="imp">{e(a["og_note"])}</p>' if a.get("og_note") else
                   f'<p class="imp"><b>くらしへの影響</b>{e(a["impact"])}</p>' if a.get("impact") else "")
            src = Path(tmp) / f"{a['slug']}.html"
            cat = a.get("og_cat") or ("ニュース解説" if a["slug"] == "default" else CATS[a["category"]])
            color = "#1b4f8c" if a["slug"] == "default" else CAT_COLOR[a["category"]]
            src.write_text(OG_TEMPLATE.format(css=(ROOT / "style.css").as_uri(), art=thumb(a, "", "og-art", lazy=False),
                                              cat=e(cat), title=e(title), color=color, size=size, impact=imp),
                           encoding="utf-8")
            subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                            f"--user-data-dir={Path(tmp) / 'profile'}", "--window-size=1200,630",
                            f"--screenshot={out_dir / (a['slug'] + '.png')}", src.as_uri()],
                           capture_output=True, timeout=60)
            print(f"SNS用画像を作成：{a['slug']}")


THUMB_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:800px;height:450px;overflow:hidden}}
body{{position:relative;background:linear-gradient(135deg,{c1} 0%,{c2} 100%);font-family:"Noto Sans JP","Yu Gothic",sans-serif;color:#fff}}
.o1{{position:absolute;right:-120px;top:-140px;width:520px;height:520px;border-radius:50%;background:rgba(255,255,255,.09)}}
.o2{{position:absolute;right:120px;bottom:-220px;width:380px;height:380px;border-radius:50%;background:rgba(255,255,255,.06)}}
.cat{{position:absolute;left:48px;top:40px;font-size:24px;font-weight:700;padding:4px 18px;border:2px solid rgba(255,255,255,.7);border-radius:999px}}
.w{{position:absolute;left:46px;top:50%;transform:translateY(-46%);font-size:{size}px;font-weight:900;letter-spacing:.02em;line-height:1.1;text-shadow:0 4px 18px rgba(0,0,0,.18)}}
.logo{{position:absolute;left:48px;bottom:34px;font-size:22px;font-weight:700;opacity:.85}}
</style></head><body><div class="o1"></div><div class="o2"></div><span class="cat">{cat}</span><div class="w">{word}</div><div class="logo">3分ニュース解説</div></body></html>"""
THUMB_COLORS = {"world": ("#1b4f8c", "#0d2c52"), "economy": ("#6b3590", "#3b1a55"),
                "life": ("#b5560f", "#7a3605"), "basics": ("#2e7d5b", "#164a34")}


def render_png(html_text, out, w, h, tmp):
    src = Path(tmp) / "render.html"
    src.write_text(html_text, encoding="utf-8")
    subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                    f"--user-data-dir={Path(tmp) / 'profile'}", f"--window-size={w},{h}",
                    f"--screenshot={out}", src.as_uri()], capture_output=True, timeout=60)


def make_thumbs(arts):
    """thumb/<スラッグ>.png（800x450）が無い記事だけ作る。言葉を変えたら画像を消して作り直す。"""
    out_dir = ROOT / "thumb"
    out_dir.mkdir(exist_ok=True)
    if not EDGE.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        for a in arts:
            out = out_dir / f"{a['slug']}.png"
            if out.exists():
                continue
            word = a.get("eyecatch") or CATS[a["category"]]
            size = 150 if len(word) <= 3 else 120 if len(word) <= 4 else 100 if len(word) <= 5 else 84
            c1, c2 = THUMB_COLORS[a["category"]]
            render_png(THUMB_TEMPLATE.format(c1=c1, c2=c2, size=size, cat=CATS[a["category"]], word=e(word)),
                       out, 800, 450, tmp)
            print(f"サムネイルを作成：{a['slug']}")


ICON_RULES = [  # 言葉 → サムネイルのアイコン（上から順に判定。どれにも当たらなければジャンルのアイコン）
    ("chart", ["NISA", "株", "iDeCo", "日経平均"]),
    ("person", ["雇用", "年収の壁"]),
    ("bank", ["FRB", "住宅ローン"]),
    ("fuel", ["原油", "ガソリン", "ホルムズ", "中東"]),
    ("bolt", ["電気"]),
    ("yen", ["円安", "円高", "ドル", "為替"]),
    ("receipt", ["年末調整", "万円", "税"]),
    ("ballot", ["選挙", "議会"]),
    ("bank", ["日銀", "金利", "利上げ"]),
    ("percent", ["物価", "インフレ", "%"]),
]


def icon_class(a):
    text = (a.get("eyecatch") or "") + a["title"]
    for name, words in ICON_RULES:
        if any(w in (a.get("eyecatch") or "") for w in words):
            return f" i-{name}"
    for name, words in ICON_RULES:
        if any(w in text for w in words):
            return f" i-{name}"
    return ""


LIFE_ICONS = [  # 「生活への影響」の見出しの言葉 → アイコン（上から順に判定）
    ("person", ["会社員", "パート", "給料", "働く"]), ("fuel", ["ガソリン", "車"]), ("bolt", ["電気", "ガス", "エネルギー"]),
    ("chart", ["株", "NISA"]), ("plane", ["旅行", "通販"]), ("yen", ["円", "外貨", "ドル"]),
    ("bank", ["ローン", "預金", "貯金", "金利"]), ("percent", ["物価", "値段"]), ("receipt", ["税", "年末"]), ("eye", ["見方", "できること"]),
]


def life_icon(label):
    for name, words in LIFE_ICONS:
        if any(w in label for w in words):
            return f'<span class="lic i-{name}" aria-hidden="true"></span>'
    return ""


def thumb(a, rel, cls="thumb", lazy=True):
    """サムネイル。画像ファイルを使わず CSS で描く（表示が速い）。"""
    word = a.get("eyecatch") or CATS[a["category"]]
    size = "w1" if len(word) <= 3 else "w2" if len(word) <= 4 else "w3" if len(word) <= 5 else "w4"
    return (f'<span class="{cls} art c-{a["category"]} {size}{icon_class(a)}" role="img" aria-label="{e(word)}">'
            f'<span class="art-cat">{CATS[a["category"]]}</span><span class="art-word">{e(word)}</span>'
            f'<span class="art-logo">3分ニュース解説</span></span>')


def og_url(slug):
    return f"{SITE_URL}og/{slug if (ROOT / 'og' / f'{slug}.png').exists() else 'default'}.png"


# ---------- 共通の枠 ----------
LATEST_HTML = ""  # ヘッダーに出す最新ニュース（main() で設定）
DAILY_LATEST = ""  # 最新の「まとめ読み」の日付（main() で設定）


def page(rel, title, description, body, canonical, active=None, og_type="website", extra_head="",
         og_image=None, extra_body=""):
    full_title = title if title == SITE_NAME else f"{title}｜{SITE_NAME}"
    nav = "".join(
        f'<li><a href="{rel}{href}"{" class=\"on\" aria-current=\"page\"" if key == active else ""}>{label}</a></li>'
        for key, href, label in [("home", "index.html", "トップ")]
        + ([("daily", f"daily/{DAILY_LATEST}.html", '<span class="nav-dot"></span>まとめ読み')] if DAILY_LATEST else [])
        + [(k, f"category/{k}.html", v) for k, v in CATS.items()]
    )
    foot_cats_li = "".join(f'<li><a href="{rel}category/{k}.html">{v}</a></li>' for k, v in CATS.items())
    foot_topics_li = "".join(f'<li><a href="{rel}topic/{k}.html">#{v[0]}</a></li>' for k, v in TOPICS.items())
    topic_nav = "".join(f'<li><a class="tp{" on" if active == "topic-" + k else ""}" href="{rel}topic/{k}.html">#{v[0]}</a></li>'
                        for k, v in TOPICS.items())
    og_image = og_image or f"{SITE_URL}og/default.png"
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#1b4f8c">
<meta name="google-site-verification" content="{GOOGLE_VERIFICATION}">
<meta name="robots" content="max-image-preview:large">
<link rel="icon" href="{FAVICON}">
<link rel="apple-touch-icon" href="{rel}apple-touch-icon.png">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="{SITE_URL}feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{rel}style.css">
{extra_head}</head>
<body>
<a class="skip" href="#main">本文へスキップ</a>
<header class="site">
  <div class="wrap bar">
    <a class="logo" href="{rel}index.html"><svg class="mark" viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="9" fill="#1b4f8c"/><path d="M8 31h24" stroke="#f0a560" stroke-width="3" stroke-linecap="round"/><text x="20" y="26" text-anchor="middle" font-size="22" font-weight="900" fill="#fff" font-family="sans-serif">3</text></svg><span class="logo-text">3分<b>ニュース解説</b><small>{TAGLINE}</small></span></a>
    {LATEST_HTML.replace("{rel}", rel)}
    <p class="today" data-today></p>
    <form class="head-search" action="{rel}search.html" role="search"><input name="q" type="search" placeholder="記事を検索（例：円安）" aria-label="記事を検索"><button type="submit" aria-label="検索する"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg></button></form>
    <a class="search-btn" href="{rel}search.html" aria-label="記事を検索"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg><span>記事を検索</span></a>
  </div>
  <nav class="cats" aria-label="ジャンル"><div class="wrap"><ul>{nav}<li class="sep" aria-hidden="true"></li>{topic_nav}</ul></div></nav>
</header>
<main class="wrap" id="main">
{body}
</main>
<footer class="site">
  <div class="wrap foot-grid">
    <div class="foot-about">
      <p class="foot-logo"><svg class="mark" viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="9" fill="#1b4f8c"/><path d="M8 31h24" stroke="#f0a560" stroke-width="3" stroke-linecap="round"/><text x="20" y="26" text-anchor="middle" font-size="22" font-weight="900" fill="#fff" font-family="sans-serif">3</text></svg><span>3分<b>ニュース解説</b></span></p>
      <p class="foot-tag">{TAGLINE}。むずかしいニュースが「自分の生活にどう関係するか」まで、やさしく解説します。</p>
    </div>
    <nav aria-label="ジャンル"><p class="foot-h">ジャンル</p><ul>{foot_cats_li}</ul></nav>
    <nav aria-label="テーマ"><p class="foot-h">テーマ</p><ul>{foot_topics_li}</ul></nav>
    <nav aria-label="サイト情報"><p class="foot-h">サイト情報</p><ul>{f'<li><a href="{rel}daily/{DAILY_LATEST}.html">まとめ読み</a></li>' if DAILY_LATEST else ""}<li><a href="{rel}glossary.html">ニュースの用語集</a></li><li><a href="{rel}search.html">記事を検索</a></li><li><a href="{rel}about.html">このサイトについて</a></li><li><a href="{rel}about.html#policy">編集方針（5つの約束）</a></li><li><a href="{rel}about.html#contact">お問い合わせ</a></li><li><a href="{rel}about.html">プライバシーポリシー</a></li><li><a href="{SITE_URL}feed.xml">RSS</a></li></ul></nav>
  </div>
  <div class="wrap foot-copy"><small>© 2026 {SITE_NAME}</small><span class="foot-promise">出典で確かめた事実だけ・結果は予想しない・中立に <a href="{rel}about.html#policy">5つの約束 ›</a></span><a class="foot-top" href="#">ページの上へ ↑</a></div>
</footer>
<nav class="tabbar" aria-label="スマホ用メニュー">
  <a href="{rel}index.html"{' class="on"' if active == "home" else ''}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11 12 4l9 7v9h-6v-6H9v6H3z"/></svg>トップ</a>
  <a href="{rel}daily/{DAILY_LATEST}.html"{' class="on"' if active == "daily" else ''}><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>まとめ</a>
  <a href="{rel}category/world.html"{' class="on"' if active == "world" else ''}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c3 3 3 14 0 17M12 3.5c-3 3-3 14 0 17"/></svg>世界</a>
  <a href="{rel}category/economy.html"{' class="on"' if active == "economy" else ''}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19h16M6 16v-5M11 16V7M16 16v-7"/></svg>経済</a>
  <a href="{rel}category/life.html"{' class="on"' if active == "life" else ''}><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="6.5" width="17" height="12" rx="2"/><path d="M3.5 10.5h17"/></svg>くらし</a>
  <a href="{rel}category/basics.html"{' class="on"' if active == "basics" else ''}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5c3-1 5.5-1 8 1 2.5-2 5-2 8-1v13c-3-1-5.5-1-8 1-2.5-2-5-2-8-1z"/><path d="M12 6.5v13"/></svg>基礎</a>
</nav>
<script>(function(){{var K='later',L=[];try{{L=JSON.parse(localStorage.getItem(K)||'[]')}}catch(e){{}}
function save(){{try{{localStorage.setItem(K,JSON.stringify(L))}}catch(e){{}}}}
var b=document.querySelector('.later');if(b){{var s=b.dataset.slug,f=function(){{var on=L.some(function(x){{return x.s===s}});b.setAttribute('aria-pressed',on);b.textContent=on?'✓ 保存済み':'＋ あとで読む'}};f();
b.addEventListener('click',function(){{var i=L.findIndex(function(x){{return x.s===s}});if(i>=0)L.splice(i,1);else L.unshift({{s:s,t:b.dataset.title}});L=L.slice(0,10);save();f()}})}}
if(L.length){{var S={{}};L.forEach(function(x){{S[x.s]=1}});document.querySelectorAll('a.card h3, .rows a h3, .lead-side a h3').forEach(function(h){{var a=h.closest('a'),m=a&&a.getAttribute('href').match(/([^/]+)[.]html$/);if(m&&S[m[1]]){{var s=document.createElement('span');s.className='saved';s.textContent='保存済み';h.prepend(s)}}}})}}
var box=document.querySelector('.later-box');if(box&&L.length){{box.hidden=false;var ol=box.querySelector('.later-list'),r=box.closest('[data-rel]');L.forEach(function(x){{var li=document.createElement('li'),a=document.createElement('a');a.href='{rel}articles/'+x.s+'.html';a.textContent=x.t;var d=document.createElement('button');d.type='button';d.textContent='×';d.setAttribute('aria-label','リストから外す');d.onclick=function(){{L=L.filter(function(y){{return y.s!==x.s}});save();li.remove();if(!L.length)box.hidden=true}};li.appendChild(a);li.appendChild(d);ol.appendChild(li)}})}}
}})();</script>
<script>(function(){{var td=new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);document.querySelectorAll('.sc-list li[data-date]').forEach(function(li){{if(li.dataset.date<td)li.remove()}});var sc=document.querySelector('.sched');if(sc&&!sc.querySelector('li'))sc.remove();}})();</script>
<script>(function(){{var n=Date.now();document.querySelectorAll('time[datetime]').forEach(function(t){{var d=new Date(t.getAttribute('datetime')+'T00:00:00+09:00');if(n-d<36*3600*1000&&!t.closest('.post-meta,.timeline,.tl-date')){{var s=document.createElement('span');s.className='new';s.textContent='NEW';t.parentNode.insertBefore(s,t)}}}});}})();</script>
<script>(function(){{var a=document.querySelectorAll('.latest-items a'),i=0;if(a.length<2||matchMedia('(prefers-reduced-motion: reduce)').matches)return;setInterval(function(){{a[i].classList.remove('on');i=(i+1)%a.length;a[i].classList.add('on')}},4500);}})();</script>
<script>(function(){{var d=new Date(),w="日月火水木金土"[d.getDay()],el=document.querySelector('[data-today]');if(el)el.textContent=(d.getMonth()+1)+"月"+d.getDate()+"日（"+w+"）";}})();</script>
{extra_body}</body>
</html>
"""


def topics_of(a):
    text = a["title"] + a["description"] + "".join(a.get("summary", []))
    return [k for k, (_, _, kws) in TOPICS.items() if any(w in text for w in kws)]


def topic_chips(keys, rel):
    return "".join(f'<a class="chip" href="{rel}topic/{k}.html">#{TOPICS[k][0]}</a>' for k in keys)


def tag(cat):
    cls = f"tag t-{cat}"
    return f'<span class="{cls}">{CATS[cat]}</span>'


def short_meta(a):
    return (f'<span class="meta"><time datetime="{a["date"]}">{md_date(a["date"])}</time>'
            f'<span>{reading_minutes(a["body"])}分</span>'
            + (f'<span class="upd">{md_date(a["updated"])}更新</span>' if a.get("updated") else "") + '</span>')


def meta_line(a):
    return (f'<span class="meta"><time datetime="{a["date"]}">{jp_date(a["date"])}</time>'
            f'<span>{reading_minutes(a["body"])}分で読めます</span></span>')


def lead_text(a):
    return a["summary"][0] if a.get("summary") else a["description"]


def impact(a):
    return f'<p class="impact"><b>くらしへの影響</b>{e(a["impact"])}</p>' if a.get("impact") else ""


def list_items(arts, rel):
    """横長の一覧（小さいサムネイル付き）。"""
    return "".join(
        f'<li><a href="{rel}articles/{a["slug"]}.html">{thumb(a, rel, "mini-thumb")}'
        f'<div>{tag(a["category"])} {meta_line(a)}<h3>{e(a["title"])}</h3></div></a></li>'
        for a in arts
    )


def cards(arts, rel, cls="grid-3"):
    """サムネイルが上にあるカードの並び。"""
    items = "".join(
        f'<a class="card" data-cat="{a["category"]}" href="{rel}articles/{a["slug"]}.html">{thumb(a, rel)}'
        f'<div class="card-body">{tag(a["category"])} {short_meta(a) if a["category"] != "basics" else ""}<h3>{e(a["title"])}</h3>'
        f'{impact(a) or "<p>" + e(lead_text(a)) + "</p>"}</div></a>'
        for a in arts
    )
    return f'<div class="cards {cls}">{items}</div>'


def row_list(arts, rel):
    """新着の2段目以降：見出し＋くらしへの影響の横長一覧。"""
    return "".join(
        f'<li data-cat="{a["category"]}"><a href="{rel}articles/{a["slug"]}.html">{thumb(a, rel, "mini-thumb")}'
        f'<div>{tag(a["category"])} {short_meta(a)}<h3>{e(a["title"])}</h3>{impact(a)}</div></a></li>'
        for a in arts)


def dated_rows(arts, rel):
    """日付ごとに見出しを付けた一覧（テーマ別ページの時系列）。"""
    out = ""
    for d in sorted({a["date"] for a in arts}, reverse=True):
        day = [a for a in arts if a["date"] == d]
        out += (f'<div class="tl-day"><p class="tl-date"><time datetime="{d}">{jp_date(d)}</time><span>{len(day)}本</span></p>'
                f'<ul class="rows">{row_list(day, rel)}</ul></div>')
    return f'<div class="tl-days">{out}</div>'


def genre_columns(news, rel):
    """トップ下部：世界情勢・経済・くらしの3列。"""
    cols = ""
    for k in ("world", "economy", "life"):
        items = [a for a in news if a["category"] == k][:5]
        if not items:
            continue
        first, rest = items[0], items[1:]
        more = "".join(f'<li><a href="{rel}articles/{a["slug"]}.html">{e(a["title"])}</a></li>' for a in rest)
        cols += (f'<section class="gcol g-{k}"><h2><a href="{rel}category/{k}.html">{CATS[k]}<span>すべて見る ›</span></a></h2>'
                 f'<a class="gfirst" href="{rel}articles/{first["slug"]}.html">{thumb(first, rel, "mini-thumb")}'
                 f'<h3>{e(first["title"])}</h3></a>' + (f'<ul>{more}</ul>' if more else "") + '</section>')
    return f'<div class="genre-cols">{cols}</div>'


def topic_band(news, rel):
    """横幅いっぱいの帯：テーマごとに記事数と最新の見出し。"""
    items = ""
    for k, (label, intro, _) in TOPICS.items():
        arts = [a for a in news if k in topics_of(a)]
        if not arts:
            continue
        items += (f'<a class="tcard" href="{rel}topic/{k}.html"><span class="tc-n">{len(arts)}本</span>'
                  f'<b>#{label}</b><span class="tc-i">{intro}</span>'
                  f'<span class="tc-l">最新：{e(arts[0]["title"])}</span></a>')
    return (f'<section class="band"><div class="band-in"><h2>テーマで追う<small>続報をまとめて読める</small></h2>'
            f'<div class="tcards">{items}</div></div></section>')


def basics_rows(basics, rel):
    return "".join(
        f'<a class="brow" href="{rel}articles/{a["slug"]}.html">{thumb(a, rel, "mini-thumb")}<span class="bt">{e(a["title"])}</span></a>'
        for a in basics)


def rank_list(arts, rel):
    return "".join(
        f'<li><a href="{rel}articles/{a["slug"]}.html"><span class="no">{i}</span>'
        f'<span class="rt">{e(a["title"])}</span>{thumb(a, rel, "rank-thumb")}</a></li>' for i, a in enumerate(arts, 1)
    )


def timeline_box(a, arts, rel):
    """同じテーマの記事を古い順に並べた「これまでの流れ」。"""
    tps = topics_of(a)
    if not tps:
        return ""
    # タイトルに言葉が出てくるテーマを優先（例：円安の記事は「金利・円相場」）
    key = max(tps, key=lambda k: sum(a["title"].count(w) for w in TOPICS[k][2]))
    items = sorted([x for x in arts if key in topics_of(x) and x["category"] != "basics"],
                   key=lambda x: (x["date"], x.get("rank", 0)))
    if len(items) < 2:
        return ""
    lis = "".join(
        f'<li{" class=\"here\"" if x["slug"] == a["slug"] else ""}><time datetime="{x["date"]}">{md_date(x["date"])}</time>'
        + (f'<span>{e(x["title"])}（この記事）</span>' if x["slug"] == a["slug"]
           else f'<a href="{rel}articles/{x["slug"]}.html">{e(x["title"])}</a>') + '</li>'
        for x in items[-6:])
    return (f'<section class="side-box keep"><h2 class="side-title">#{TOPICS[key][0]} これまでの流れ</h2>'
            f'<ol class="timeline">{lis}</ol><a class="more" href="{rel}topic/{key}.html">このテーマの記事をすべて見る ›</a></section>')


def schedule_box(rel):
    """これからの予定（src/schedule.json。過ぎた予定は表示しない）。"""
    f = SRC / "schedule.json"
    if not f.exists():
        return ""
    today = date.today().isoformat()
    items = [x for x in json.loads(f.read_text(encoding="utf-8")) if x["date"] >= today][:4]
    if not items:
        return ""
    wd = "月火水木金土日"
    lis = "".join(
        f'<li data-date="{x["date"]}"><span class="sc-d"><b>{md_date(x["date"])}</b>（{wd[date.fromisoformat(x["date"]).weekday()]}）{(" " + x["time"]) if x.get("time") else ""}</span>'
        f'<a href="{rel}articles/{x["article"]}.html">{e(x["label"])}</a><small>{e(x["note"])}</small></li>' for x in items)
    return (f'<section class="side-box sched"><h2 class="side-title">これからの予定<small>ニュースが動きやすい日</small></h2>'
            f'<ol class="sc-list">{lis}</ol></section>')


def sidebar(arts, rel, toc_html="", exclude=(), home=False, extra="", show_digest=True):
    news = [a for a in arts if a["category"] != "basics" and a["slug"] not in exclude]
    basics = [a for a in arts if a["category"] == "basics" and a["slug"] not in exclude]
    topics = "".join(
        f'<a class="chip" href="{rel}topic/{k}.html">#{v[0]}<span>{sum(1 for a in arts if k in topics_of(a))}</span></a>'
        for k, v in TOPICS.items() if any(k in topics_of(a) for a in arts))
    basics_li = "".join(f'<li><a href="{rel}articles/{b["slug"]}.html">{thumb(b, rel, "side-thumb")}<span>{e(b["title"])}</span></a></li>' for b in basics[:5])
    toc_box = f'<section class="side-box side-toc">{toc_html}</section>' if toc_html else ""
    latest = next((a["date"] for a in arts if a["category"] != "basics"), None)
    n_day = sum(1 for a in arts if a["category"] != "basics" and a["date"] == latest)
    digest = (f'<a class="digest-cta" href="{rel}daily/{latest}.html"><span>忙しい人へ</span><b>{md_date(latest)}のニュースを<br>3分でまとめ読み</b>'
          f'<small>{n_day}本の3行まとめを1ページで ›</small></a>') if latest and show_digest else ""
    if home:
        glossary = "".join(f'<a href="{rel}articles/{b["slug"]}.html">{e(b["keywords"][0])}</a>'
                           for b in basics if b.get("keywords"))
        genres = "".join(
            f'<li><a href="{rel}category/{k}.html"><b>{v}</b><span>{sum(1 for a in arts if a["category"] == k)}本</span></a></li>'
            for k, v in CATS.items())
        return f"""<aside class="sidebar" aria-label="サイドメニュー">
  {digest}
  <section class="side-box later-box" hidden><h2 class="side-title">あとで読む<small>この端末に保存</small></h2><ol class="later-list"></ol></section>
  {schedule_box(rel)}
  <section class="side-box guide"><h2 class="side-title">このサイトの読み方</h2>
    <ol class="steps"><li><b>3行まとめ</b>で、何が起きたかを10秒でつかむ</li>
    <li><b>生活への影響</b>（オレンジの枠）で、自分のお金や仕事との関係を知る</li>
    <li>点線の言葉をタップすると、<b>基礎解説</b>で用語が分かる</li>
    <li>矢印の<b>流れ図</b>で、ニュースが生活に届くまでのつながりが分かる</li></ol></section>
  <section class="side-box sp-hide"><h2 class="side-title">注目のテーマ</h2><div class="chips-wrap">{topics}</div></section>
  <section class="side-box sp-hide"><h2 class="side-title">ジャンルから探す</h2><ul class="genre-list">{genres}</ul></section>
  <section class="side-box"><h2 class="side-title">用語さくいん<small>タップで基礎解説へ</small></h2><div class="glossary">{glossary}</div><a class="more" href="{rel}glossary.html">意味つきの用語集を見る ›</a></section>
  <section class="side-box about-box"><h2 class="side-title">このサイトについて</h2>
    <p>ニュースを見ても「で、自分の生活にどう関係あるの？」と思う会社員のために、世界と経済のニュースを3分で読めるように解説しています。</p>
    <a class="more" href="{rel}about.html">運営者・記事の作り方 ›</a></section>
</aside>"""
    return f"""<aside class="sidebar" aria-label="サイドメニュー">
  {extra}
  {digest}
  {schedule_box(rel)}
  <section class="side-box"><h2 class="side-title">今日のポイント</h2><ol class="rank">{rank_list(news[:5], rel)}</ol></section>
  <section class="side-box"><h2 class="side-title">注目のテーマ</h2><div class="chips-wrap">{topics}</div></section>
  <section class="side-box side-basics"><h2 class="side-title">基礎から学ぶ</h2><ul class="side-list">{basics_li}</ul>
    <a class="more" href="{rel}category/basics.html">基礎解説をすべて見る ›</a></section>
  <section class="side-box about-box"><h2 class="side-title">このサイトについて</h2>
    <p>ニュースを見ても「で、自分の生活にどう関係あるの？」と思う会社員のために、世界と経済のニュースを3分で読めるように解説しています。</p>
    <a class="more" href="{rel}about.html">運営者・記事の作り方 ›</a></section>
  {toc_box}
</aside>"""


ARTICLE_JS = """<button class="to-top" type="button" aria-label="ページの先頭へ戻る">↑</button>
<script>(function(){
  var links=[].slice.call(document.querySelectorAll('.toc-list a'));if(!links.length)return;
  var hs=links.map(function(a){return document.getElementById(a.getAttribute('href').slice(1))});
  function upd(){var y=innerHeight*0.3,cur=-1;hs.forEach(function(h,i){if(h&&h.getBoundingClientRect().top<y)cur=i});
    links.forEach(function(a,i){a.classList.toggle('now',i===cur)})}
  addEventListener('scroll',upd,{passive:true});upd();
})();</script>
<script>
(function(){
  var bar=document.querySelector('.progress'),top=document.querySelector('.to-top'),post=document.querySelector('article.post');
  function upd(){
    var r=post.getBoundingClientRect(),h=r.height-innerHeight,p=h>0?Math.min(1,Math.max(0,-r.top/h)):1;
    bar.style.transform='scaleX('+p+')';
    top.classList.toggle('show',scrollY>600);
  }
  addEventListener('scroll',upd,{passive:true});upd();
  top.addEventListener('click',function(){scrollTo({top:0,behavior:'smooth'})});
})();
</script>
"""


# ---------- 記事ページ ----------
def build_article(a, all_arts, by_slug, backlinks):
    rel = "../"
    body = re.sub(r"(<h2>これからの注目点</h2>\s*)<ul>", r'\1<ul class="watch">', a["body"], count=1)
    body = re.sub(r'<div class="life"><b>(.*?)</b>', lambda m: f'<div class="life"><b>{life_icon(m.group(1))}{m.group(1)}</b>', body)
    body, heads = add_heading_ids(render_flow(render_bars(body)))
    body, linked = link_terms(body, all_arts, a["slug"])
    body = bold_numbers(body)
    url = f"{SITE_URL}articles/{a['slug']}.html"

    summary = "".join(f"<li>{e(s)}</li>" for s in a.get("summary", []))
    if a["category"] == "basics":  # 基礎解説は「3つのポイント」の図にする
        pts = "".join(f'<li><span class="pn">{i}</span><p>{e(s)}</p></li>' for i, s in enumerate(a.get("summary", []), 1))
        summary_box = f'<div class="points3"><b>3つのポイント</b><ol>{pts}</ol></div>'
    else:
        summary_box = f'<div class="summary"><b>3行まとめ</b><ul>{summary}</ul>{impact(a)}</div>'
    toc = "".join(f'<li><a href="#s{i}">{e(h)}</a></li>' for i, h in enumerate(heads, 1))

    term_slugs = [t for t in a["terms"] if t in by_slug and t != a["slug"]]
    term_slugs += [t for t in linked if t not in term_slugs]
    terms = [by_slug[t] for t in term_slugs]
    terms_box = ""
    if terms:
        lis = "".join(f'<li><a href="{t["slug"]}.html">{e(t["title"])}</a></li>' for t in terms)
        terms_box = f'<aside class="box terms"><b>用語メモ：あわせて読むと分かりやすい基礎解説</b><ul>{lis}</ul></aside>'

    srcs = "".join(f'<li><a href="{e(u)}" rel="nofollow noopener" target="_blank">{e(n)}</a></li>'
                   for n, u in a["sources"])
    caution = "投資やローンの判断はご自身でお願いします。" if a["category"] in ("economy", "life", "basics") else ""

    share_text = f"{a['title']}｜{SITE_NAME}"
    share = (f'<div class="share"><span>この記事をシェア</span>'
             f'<a class="x" href="https://twitter.com/intent/tweet?url={quote(url)}&text={quote(share_text)}" target="_blank" rel="noopener">Xでポスト</a>'
             f'<a class="line" href="https://social-plugins.line.me/lineit/share?url={quote(url)}" target="_blank" rel="noopener">LINEで送る</a>'
             f'<button class="copy" type="button" data-url="{url}">URLをコピー</button></div>')

    related = [r for r in all_arts if r["slug"] != a["slug"] and r not in terms and
               (r["category"] == a["category"] or set(r["terms"]) & set(a["terms"]) or a["slug"] in r["terms"])][:4]
    related_html = (f'<section><h2 class="section-title">関連記事</h2>{cards(related[:4], rel, "grid-4")}</section>'
                    if related else "")
    if a["category"] == "basics":
        users = [by_slug[s] for s in backlinks.get(a["slug"], []) if by_slug[s]["category"] != "basics"]
        others = [r for r in all_arts if r["category"] == "basics" and r["slug"] != a["slug"]][:4]
        related_html = (f'<section><h2 class="section-title">ほかの基礎解説</h2>{cards(others[:4], rel, "grid-4")}</section>'
                        if others else "")
        if users:
            related_html = (f'<section><h2 class="section-title">この用語が出てくるニュース</h2>'
                            f'<ul class="rows">{row_list(users[:8], rel)}</ul></section>') + related_html

    ld = [{
        "@context": "https://schema.org",
        "@type": "Article" if a["category"] == "basics" else "NewsArticle",
        "headline": a["title"],
        "description": a["description"],
        "image": [og_url(a["slug"])],
        "datePublished": a["date"],
        "dateModified": a.get("updated", a["date"]),
        "inLanguage": "ja",
        "author": {"@type": "Person", "name": AUTHOR, "url": SITE_URL + "about.html"},
        "publisher": {"@type": "Organization", "name": SITE_NAME,
                      "logo": {"@type": "ImageObject", "url": SITE_URL + "icon-512.png"}},
        "mainEntityOfPage": url,
    }, {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "トップ", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": CATS[a["category"]],
             "item": f"{SITE_URL}category/{a['category']}.html"},
            {"@type": "ListItem", "position": 3, "name": a["title"]},
        ],
    }]
    extra = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>\n' for x in ld)
    extra += (f'<meta property="article:published_time" content="{a["date"]}">\n'
              f'<meta property="article:modified_time" content="{a.get("updated", a["date"])}">\n'
              f'<meta property="article:section" content="{CATS[a["category"]]}">\n')

    updated = f'<p class="updated">{jp_date(a["updated"])} 更新</p>' if a.get("updated") else ""
    if a["category"] != "basics" and topics_of(a):  # 同じテーマで後の日付の記事があれば「続報」を案内
        later = [x for x in all_arts if x["category"] != "basics" and x["date"] > a["date"]
                 and set(topics_of(x)) & set(topics_of(a))]
        if later:
            n = later[0]
            updated += (f'<a class="followup" href="{n["slug"]}.html"><b>続報があります</b>'
                        f'<span>{md_date(n["date"])}：{e(n["title"])}</span></a>')
    same = [x for x in all_arts if (x["category"] == "basics") == (a["category"] == "basics")]
    i = next(n for n, x in enumerate(same) if x["slug"] == a["slug"])
    nxt = same[(i + 1) % len(same)] if len(same) > 1 else None
    next_card = (f'<a class="next-card" href="{nxt["slug"]}.html"><span class="nc-label">次に読む</span>{thumb(nxt, rel, "mini-thumb")}'
                 f'<div>{tag(nxt["category"])}<h3>{e(nxt["title"])}</h3>{impact(nxt)}</div><span class="nc-arrow" aria-hidden="true">›</span></a>') if nxt else ""
    toc_side = f'<h2 class="side-title">この記事の目次</h2><ol class="toc-list">{toc}</ol>'
    content = f"""<div class="progress" aria-hidden="true"></div>
<nav class="crumbs" aria-label="現在地"><a href="{rel}index.html">トップ</a> <span aria-hidden="true">›</span> <a href="{rel}category/{a["category"]}.html">{CATS[a["category"]]}</a></nav>
<div class="layout">
<div class="main-col">
<article class="post">
  <div class="post-meta">{tag(a["category"])} {meta_line(a)}</div>
  <h1>{e(a["title"])}</h1>
  {updated}
  <div class="post-tools">
    <div class="share-mini"><a class="x" href="https://twitter.com/intent/tweet?url={quote(url)}&text={quote(share_text)}" target="_blank" rel="noopener" aria-label="Xでポスト">X</a><a class="line" href="https://social-plugins.line.me/lineit/share?url={quote(url)}" target="_blank" rel="noopener" aria-label="LINEで送る">LINE</a><button class="copy" type="button" data-url="{url}">URLをコピー</button></div>
    <button class="later" type="button" data-slug="{a["slug"]}" data-title="{e(a["title"])}" aria-pressed="false">＋ あとで読む</button>
    <div class="font-size" role="group" aria-label="文字の大きさ"><span>文字</span><button type="button" data-fs="s">小</button><button type="button" data-fs="m">中</button><button type="button" data-fs="l">大</button></div>
  </div>
  {thumb(a, rel, "post-thumb", lazy=False)}
  {summary_box}
  <details class="toc"><summary>この記事の目次</summary><ol>{toc}</ol></details>
  {body}
  {terms_box}
  <div class="sources">
    <b>この記事の出典（確認した情報）</b><ul>{srcs}</ul>
    <p class="note-ai">この記事はAIの補助を受けて作成し、上記の出典で内容を確認しています。{caution}誤りに気づいた方は<a href="{rel}about.html#contact">お問い合わせ</a>からお知らせください。</p>
  </div>
  {share}
  {('<div class="topics"><span>この記事のテーマ</span>' + topic_chips(topics_of(a), rel) + '</div>') if topics_of(a) else ''}
  <div class="author"><svg class="mark" viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="9" fill="#1b4f8c"/><path d="M8 31h24" stroke="#f0a560" stroke-width="3" stroke-linecap="round"/><text x="20" y="26" text-anchor="middle" font-size="22" font-weight="900" fill="#fff" font-family="sans-serif">3</text></svg>
    <div><p class="author-name">この記事を書いた人：{AUTHOR}（会社員）</p>
    <p>ニュースを「自分の生活にどう関係するか」の目線で解説しています。記事はAIの補助を受けて作成し、出典で内容を確かめています。<a href="{rel}about.html#policy">このサイトの5つの約束 ›</a></p></div></div>
<div class="ask-box"><p><b>この記事、分かりやすかったですか？</b>分かりにくかった言葉や、もっと知りたいことがあれば教えてください。次の記事や基礎解説づくりの参考にします。</p><a href="https://docs.google.com/forms/d/e/1FAIpQLSdu8msfvuKb1s2RHIGpLfftHXKe3P_dkvoz3MX5pVMIugq-OA/viewform" target="_blank" rel="noopener">意見を送る（1分）›</a></div>
{next_card}
</article>
</div>
{sidebar(all_arts, rel, toc_side, exclude=(a["slug"],), extra=timeline_box(a, all_arts, rel)).replace('class="sidebar"', 'class="sidebar art-side"', 1)}
</div>
<div class="after-post">{related_html}
<section><h2 class="section-title">ジャンル別の新着<small>次に読む記事を探す</small></h2>{genre_columns([x for x in all_arts if x["category"] != "basics" and x["slug"] != a["slug"]], rel)}</section></div>"""
    copy_js = """<script>
document.querySelectorAll('.copy').forEach(function(b){b.addEventListener('click',function(){
  navigator.clipboard&&navigator.clipboard.writeText(b.dataset.url).then(function(){b.textContent='コピーしました';setTimeout(function(){b.textContent='URLをコピー'},2000)});
})});
(function(){
  var post=document.querySelector('article.post'),btns=document.querySelectorAll('[data-fs]'),fs='m';
  try{fs=localStorage.getItem('fs')||'m'}catch(e){}
  function set(v){post.dataset.fs=v;btns.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.fs===v)});try{localStorage.setItem('fs',v)}catch(e){}}
  btns.forEach(function(b){b.addEventListener('click',function(){set(b.dataset.fs)})});set(fs);
})();
</script>
"""
    out = ROOT / "articles" / f"{a['slug']}.html"
    out.write_text(page(rel, a["title"], a["description"], content, url, active=a["category"],
                        og_type="article", extra_head=extra, og_image=og_url(a["slug"]),
                        extra_body=ARTICLE_JS + copy_js), encoding="utf-8")


# ---------- 数字で見るいま ----------
def numbers_html(by_slug, rel):
    f = SRC / "numbers.json"
    if not f.exists():
        return ""
    items = "".join(
        f'<li><a href="{rel}articles/{n["article"]}.html"><span class="nl">{e(n["label"])}</span>'
        f'<b class="nv">{e(n["value"])}'
        + (f'<span class="nt nt-{n["trend"]}" title="{e(n.get("trend_note", ""))}">{ {"up": "▲", "down": "▼", "flat": "→"}[n["trend"]] }</span>' if n.get("trend") else "")
        + f'</b><span class="nn">{e(n["note"])}</span></a></li>'
        for n in json.loads(f.read_text(encoding="utf-8")) if n["article"] in by_slug)
    return f'<section class="numbers" aria-label="数字で見るいま"><p class="numbers-h"><span>数字で</span><span>見るいま</span></p><ul>{items}</ul></section>'


# ---------- トップ ----------
def build_index(arts):
    news = [a for a in arts if a["category"] != "basics"]
    basics = [a for a in arts if a["category"] == "basics"]
    latest = news[0]["date"] if news else date.today().isoformat()
    lead = news[0]
    lead_sum = "".join(f"<li>{e(s)}</li>" for s in lead.get("summary", []))
    side_news = "".join(
        f'<li><a href="articles/{a["slug"]}.html">{thumb(a, "", "mini-thumb")}<div>{tag(a["category"])}'
        f'<h3>{e(a["title"])}</h3>{impact(a)}</div></a></li>' for a in news[1:4])
    by_slug = {a["slug"]: a for a in arts}
    also = "".join(f'<li><a href="articles/{s}.html">{e(by_slug[s]["title"])}</a></li>'
                   for s in lead["terms"][:2] if s in by_slug)
    also_html = f'<div class="also"><p>今日の1本目とあわせて読む</p><ul>{also}</ul></div>' if also else ""
    tcount = {k: sum(1 for a in news if k in topics_of(a)) for k in TOPICS}
    top_topic = max(tcount, key=tcount.get)
    feature = (f'<a class="feature" href="topic/{top_topic}.html"><span class="ft">特集</span>'
               f'<b>{TOPICS[top_topic][0]}</b><span class="fd">{TOPICS[top_topic][1]}</span><span class="fc">{tcount[top_topic]}本の記事 ›</span>'
               f'<span class="fl">{"".join("<span>" + e(a["title"]) + "</span>" for a in [x for x in news if top_topic in topics_of(x)][:3])}</span></a>')
    body = f"""{numbers_html(by_slug, "")}
<div class="layout">
<div class="main-col">
  <section class="lead" aria-label="今日の注目記事">
    <a class="lead-main" href="articles/{lead["slug"]}.html">
      {thumb(lead, "", "lead-thumb", lazy=False)}
      <div class="lead-body"><span class="label">今日の1本目</span>{tag(lead["category"])} {meta_line(lead)}
        <h2>{e(lead["title"])}</h2><ul>{lead_sum}</ul>{impact(lead)}<span class="lead-go">この記事を読む（{reading_minutes(lead["body"])}分） ›</span></div>
    </a>
    <div class="lead-right"><ul class="lead-side">{side_news}</ul>{also_html}</div>
  </section>
  <a class="digest-cta sp-only" href="daily/{latest}.html"><span>忙しい人へ</span><b>{md_date(latest)}のニュースを3分でまとめ読み</b><small>{sum(1 for a in news if a["date"] == latest)}本の3行まとめを1ページで ›</small></a>
  {feature}
  <section class="newest"><h2 class="section-title">新着記事<small>{md_date(latest)}更新</small></h2>
    <div class="ftabs" role="group" aria-label="ジャンルで絞り込む"><button type="button" aria-pressed="true" data-f="all">すべて</button>{"".join(f'<button type="button" aria-pressed="false" data-f="{k}">{CATS[k]}</button>' for k in ("world", "economy", "life"))}</div>
    <p class="fempty" hidden>このジャンルの新着は、上の注目記事をご覧ください。</p>
    {cards(news[4:7], "")}
    {f'<ul class="rows">{row_list(news[7:16], "")}</ul>' if len(news) > 7 else ""}</section>
</div>
{sidebar(arts, "", home=True).replace('class="sidebar"', 'class="sidebar home-side"', 1)}
</div>
{topic_band(news, "")}
<script>(function(){{var s=document.querySelector('.newest');if(!s)return;var bs=s.querySelectorAll('.ftabs button'),items=s.querySelectorAll('[data-cat]'),em=s.querySelector('.fempty');
bs.forEach(function(b){{b.addEventListener('click',function(){{var f=b.dataset.f,n=0;bs.forEach(function(x){{x.setAttribute('aria-pressed',x===b)}});
items.forEach(function(it){{var on=f==='all'||it.dataset.cat===f;it.hidden=!on;if(on)n++}});em.hidden=n>0}})}})}})();</script>
<section class="full"><h2 class="section-title">ジャンル別の新着<small>気になる分野から読む</small></h2>{genre_columns(news, "")}</section>
<section class="full basics-band"><h2 class="section-title">基礎から学ぶ<small>新しく追加した解説から</small><a class="more" href="glossary.html">用語集 ›</a><a class="more" href="category/basics.html">すべて見る ›</a></h2>
  <div class="brows">{basics_rows(sorted(basics, key=lambda a: (a["date"], -a.get("rank", 0)), reverse=True)[:8], "")}</div></section>"""
    ld = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": SITE_URL,
          "potentialAction": {"@type": "SearchAction", "target": SITE_URL + "search.html?q={q}",
                              "query-input": "required name=q"}}
    (ROOT / "index.html").write_text(
        page("", SITE_NAME, "世界情勢や経済のむずかしいニュースを、会社員の生活にどう関係するかという目線で、3分で読めるように解説します。",
             body, SITE_URL, active="home",
             extra_head=f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n'),
        encoding="utf-8")


# ---------- ジャンル別 ----------
def page_head(kicker, title, intro, count, color=None, unit="本の記事"):
    style = f' style="--c:{color}"' if color else ""
    return (f'<section class="page-head"{style}><div><p class="kicker">{kicker}</p><h1>{title}</h1><p>{intro}</p></div>'
            f'<p class="count"><b>{count}</b>{unit}</p></section>')


def cat_lead(a, rel):
    """一覧ページの先頭の大きい記事。"""
    lis = "".join(f"<li>{e(s)}</li>" for s in a.get("summary", []))
    return (f'<a class="cat-lead" href="{rel}articles/{a["slug"]}.html">{thumb(a, rel, "lead-thumb", lazy=False)}'
            f'<div>{tag(a["category"])} {meta_line(a)}<h2>{e(a["title"])}</h2><ul>{lis}</ul>{impact(a)}</div></a>')


def related_basics(items, all_arts, rel, title):
    by_slug = {a["slug"]: a for a in all_arts}
    slugs = list(dict.fromkeys(s for a in items for s in a.get("terms", []) if s in by_slug))
    if not slugs:
        return ""
    return (f'<section class="basics-band"><h2 class="section-title">{title}<small>先に読むとニュースが分かる</small></h2>'
            f'<div class="brows two">{basics_rows([by_slug[s] for s in slugs][:6], rel)}</div></section>')


def build_categories(arts):
    (ROOT / "category").mkdir(exist_ok=True)
    make_og_images([{"slug": "cat-" + k, "category": k, "title": "ニュースが分かる基礎知識を、やさしく解説" if k == "basics" else f"{v}のニュースを、会社員目線で3分で",
                     "eyecatch": v.split("・")[0], "body": "", "description": "", "og_cat": "ジャンル", "og_note": CAT_INTRO[k]}
                    for k, v in CATS.items()])
    for key, label in CATS.items():
        items = [a for a in arts if a["category"] == key]
        news = [a for a in arts if a["category"] != "basics"]
        if key == "basics" or not items:
            main = cards(items, "../")
        else:
            rest = items[1:]
            main = (cat_lead(items[0], "../")
                    + (f'<section><h2 class="section-title">{label}の記事</h2>{cards(rest[:6], "../")}'
                       + (f'<ul class="rows">{row_list(rest[6:], "../")}</ul>' if len(rest) > 6 else "") + '</section>' if rest else "")
                    + related_basics(items, arts, "../", f"{label}の基礎解説"))
        if key == "basics":  # 基礎解説は右列を省き、用語さくいん＋横幅いっぱいの4列
            gl = "".join(f'<a href="../articles/{b["slug"]}.html">{e(w)}</a>' for b in items for w in b.get("keywords", []))
            layout = (f'<div class="gloss-bar"><b>用語さくいん</b><div class="glossary">{gl}</div><a class="gl-all" href="../glossary.html">用語集（意味つき）›</a></div>'
                      f'{cards(items, "../", "grid-4")}')
        else:
            layout = f'<div class="layout"><div class="main-col">{main}</div>{sidebar(arts, "../")}</div>'
        body = (page_head("ジャンル", label, CAT_INTRO[key], len(items), CAT_COLOR[key]) + layout +
                f'<section class="full"><h2 class="section-title">ジャンル別の新着<small>ほかの分野も読む</small></h2>{genre_columns(news, "../")}</section>')
        url = f"{SITE_URL}category/{key}.html"
        (ROOT / "category" / f"{key}.html").write_text(
            page("../", label, f"{label}の記事一覧。{CAT_INTRO[key]}", body, url, active=key, og_image=og_url("cat-" + key)),
            encoding="utf-8")


# ---------- テーマ別 ----------
def build_topics(arts):
    (ROOT / "topic").mkdir(exist_ok=True)
    make_og_images([{"slug": "topic-" + k, "category": "economy" if k == "rates" else "life" if k == "household" else "world",
                     "title": f"#{v[0]} これまでの流れと解説", "eyecatch": v[0].split("・")[0], "body": "", "description": "",
                     "og_cat": "テーマ", "og_note": v[1]} for k, v in TOPICS.items()])
    for key, (label, intro, _) in TOPICS.items():
        items = [a for a in arts if key in topics_of(a)]
        news = [a for a in items if a["category"] != "basics"]
        basics = [a for a in items if a["category"] == "basics"]
        basics_html = (f'<section class="basics-band"><h2 class="section-title">まず読みたい基礎解説<small>先に読むとニュースが分かる</small></h2>'
                       f'<div class="brows two">{basics_rows(basics, "../")}</div></section>' if basics else "")
        body = (page_head("テーマ", f"#{label}", intro, len(items)) +
                f'<div class="layout"><div class="main-col">{basics_html}'
                f'<section><h2 class="section-title">ニュース解説<small>日付ごと・新しい順</small></h2>{dated_rows(news, "../")}</section></div>{sidebar(arts, "../")}</div>'
                f'<section class="full"><h2 class="section-title">ジャンル別の新着<small>ほかの話題も読む</small></h2>{genre_columns([a for a in arts if a["category"] != "basics"], "../")}</section>')
        url = f"{SITE_URL}topic/{key}.html"
        (ROOT / "topic" / f"{key}.html").write_text(
            page("../", f"#{label}", f"{label}に関する記事の一覧。{intro}", body, url, active="topic-" + key,
                 og_image=og_url("topic-" + key)), encoding="utf-8")


# ---------- アイコン ----------
ICON_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;width:{s}px;height:{s}px;overflow:hidden}}
body{{background:#1b4f8c;color:#fff;font-family:"Noto Sans JP","Yu Gothic",sans-serif;display:flex;align-items:center;justify-content:center;
font-weight:900;font-size:{f}px}}</style></head><body>3</body></html>"""


def make_icons():
    if not EDGE.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        for name, s in [("apple-touch-icon.png", 180), ("icon-512.png", 512)]:
            if (ROOT / name).exists():
                continue
            src = Path(tmp) / "icon.html"
            src.write_text(ICON_HTML.format(s=s, f=int(s * .62)), encoding="utf-8")
            subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                            f"--user-data-dir={Path(tmp) / 'profile'}", f"--window-size={s},{s}",
                            f"--screenshot={ROOT / name}", src.as_uri()], capture_output=True, timeout=60)
            print(f"アイコンを作成：{name}")


# ---------- 検索 ----------
SEARCH_JS = """<script>
(function(){
  var input=document.getElementById('q'),out=document.getElementById('results'),info=document.getElementById('info'),data=[];
  var cats=%s;
  function esc(s){return s.replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function run(){
    var q=input.value.trim();
    history.replaceState(null,'',q?'?q='+encodeURIComponent(q):location.pathname);
    if(!q){out.innerHTML='';info.textContent='キーワードを入れると、タイトルや本文から記事を探します。';return}
    var words=q.split(/[\\s　]+/);
    var hits=data.map(function(a){
      var score=0;
      for(var i=0;i<words.length;i++){
        var w=words[i];
        var lw=w.toLowerCase();if(a.lt.indexOf(lw)>=0)score+=10; else if(a.ld.indexOf(lw)>=0)score+=4; else if(a.lb.indexOf(lw)>=0)score+=1; else return null;
      }
      return {a:a,s:score};
    }).filter(Boolean).sort(function(x,y){return y.s-x.s||(y.a.date>x.a.date?1:-1)});
    info.textContent='「'+q+'」の検索結果：'+hits.length+'件';
    function hl(s){s=esc(s);words.forEach(function(w){if(!w)return;var lw=esc(w).toLowerCase(),ls=s.toLowerCase(),out='',i=0,j;while((j=ls.indexOf(lw,i))>=0){out+=s.slice(i,j)+'<mark>'+s.slice(j,j+lw.length)+'</mark>';i=j+lw.length}s=out+s.slice(i)});return s}
    function snip(a){var txt=a.lt+a.ld;if(words.some(function(w){return txt.indexOf(w.toLowerCase())>=0}))return '';
      var w=words.find(function(w){return a.lb.indexOf(w.toLowerCase())>=0});if(!w)return '';var i=a.lb.indexOf(w.toLowerCase());
      return '<p class="snip">…'+hl(a.b.slice(Math.max(0,i-30),i+50))+'…</p>'}
    out.innerHTML=hits.map(function(h){var a=h.a;
      var w=a.e||cats[a.c],sz=w.length<=3?'w1':w.length<=4?'w2':w.length<=5?'w3':'w4';
      return '<a class="card" href="articles/'+a.s+'.html"><span class="thumb art c-'+a.c+' '+sz+(a.ic||'')+'" role="img" aria-label="'+esc(w)+'"><span class="art-cat">'+cats[a.c]+'</span><span class="art-word">'+esc(w)+'</span><span class="art-logo">3分ニュース解説</span></span>'
        +'<div class="card-body"><span class="tag t-'+a.c+'">'+cats[a.c]+'</span> <span class="meta"><time datetime="'+a.date+'">'+a.jd+'</time></span><h3>'+hl(a.t)+'</h3>'
        +(a.i?'<p class="impact"><b>くらしへの影響</b>'+hl(a.i)+'</p>':'<p>'+hl(a.d)+'</p>')+snip(a)+'</div></a>'
    }).join('');
  }
  fetch('search.json').then(function(r){return r.json()}).then(function(j){
    j.forEach(function(a){a.lt=a.t.toLowerCase();a.ld=(a.d+(a.i||'')).toLowerCase();a.lb=a.b.toLowerCase()});data=j;var p=new URLSearchParams(location.search).get('q');if(p){input.value=p}run();
  });
  input.addEventListener('input',run);
  document.querySelectorAll('.chips button').forEach(function(b){b.addEventListener('click',function(){input.value=b.textContent;run();input.focus()})});
})();
</script>
"""


def build_search(arts):
    data = [{"s": a["slug"], "t": a["title"], "d": a["description"], "c": a["category"], "date": a["date"],
             "jd": jp_date(a["date"]), "e": a.get("eyecatch", ""), "i": a.get("impact", ""), "ic": icon_class(a),
             "b": plain(a["body"])[:1500]} for a in arts]
    (ROOT / "search.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    chips = "".join(f"<button type=\"button\">{w}</button>" for w in ["円安", "金利", "ガソリン", "電気代", "日銀", "年末調整", "中間選挙", "新NISA", "iDeCo", "ふるさと納税", "年収の壁", "住宅ローン"])
    body = f"""<section class="page-head"><p class="kicker">検索</p><h1>記事を検索</h1><p>タイトル・説明・本文から記事を探せます。言葉はスペースで区切って複数入れられます。</p></section>
<div class="layout"><div class="main-col">
<div class="search-box"><input id="q" type="search" placeholder="例：円安、住宅ローン、ガソリン" aria-label="検索キーワード" autofocus></div>
<div class="chips"><span>よく読まれる言葉：</span>{chips}</div>
<p id="info" class="meta"></p>
<div class="cards grid-3" id="results"></div>
</div>{sidebar(arts, "", home=True)}</div>"""
    (ROOT / "search.html").write_text(
        page("", "記事を検索", "3分ニュース解説の記事をキーワードで検索できます。", body, SITE_URL + "search.html",
             extra_body=SEARCH_JS % json.dumps(CATS, ensure_ascii=False)), encoding="utf-8")


# ---------- まとめ読み（日付ごと） ----------
def day_impacts(items):
    """その日のニュースの「くらしへの影響」を、重要な順に最大5つ並べた箱。"""
    lis = "".join(f'<li><a href="#d{n}">{e(a["impact"])}</a></li>' for n, a in enumerate(items, 1) if a.get("impact"))
    if not lis:
        return ""
    return f'<section class="day-imp"><h2>この日の「くらしへの影響」まとめ</h2><ol>{lis}</ol></section>'


def build_daily(arts):
    (ROOT / "daily").mkdir(exist_ok=True)
    news = [a for a in arts if a["category"] != "basics"]
    days = sorted({a["date"] for a in news}, reverse=True)
    make_og_images([{"slug": "daily-" + d, "category": "world", "title": f"{jp_date(d)}のニュースを3分でまとめ読み",
                     "eyecatch": "まとめ読み", "body": "", "description": "", "og_cat": "まとめ読み",
                     "og_note": f"この日のニュース{sum(1 for a in news if a['date'] == d)}本を、3行まとめで一気に確認"} for d in days])
    for i, d in enumerate(days):
        items = sorted([a for a in news if a["date"] == d], key=lambda a: -a.get("rank", 0))
        lis = "".join(
            f'<li id="d{n}"><div class="dg-head"><span class="dg-no">{n}</span>{tag(a["category"])}</div>'
            f'<h2><a href="../articles/{a["slug"]}.html">{e(a["title"])}</a></h2>'
            f'<ul>{"".join(f"<li>{e(s)}</li>" for s in a.get("summary", []))}</ul>{impact(a)}'
            f'<a class="dg-more" href="../articles/{a["slug"]}.html">くわしく読む（{reading_minutes(a["body"])}分） ›</a></li>'
            for n, a in enumerate(items, 1))
        nav = ""
        if i + 1 < len(days):
            nav += f'<a href="{days[i + 1]}.html">‹ {md_date(days[i + 1])}のまとめ</a>'
        if i > 0:
            nav += f'<a class="next" href="{days[i - 1]}.html">{md_date(days[i - 1])}のまとめ ›</a>'
        body = (page_head("まとめ読み", f"{jp_date(d)}のニュース",
                          "この日のニュースを3行まとめで一気に確認できます。気になった記事だけ開いてください。", len(items)) +
                (numbers_html({a["slug"]: a for a in arts}, "../") if i == 0 else "") +
                f'<div class="post-tools dg-share"><span>このまとめをシェア</span><div class="share-mini">'
                f'<a class="x" href="https://twitter.com/intent/tweet?url={quote(SITE_URL + "daily/" + d + ".html")}&text={quote(jp_date(d) + "のニュースを3分でまとめ読み｜" + SITE_NAME)}" target="_blank" rel="noopener">Xでポスト</a>'
                f'<a class="line" href="https://social-plugins.line.me/lineit/share?url={quote(SITE_URL + "daily/" + d + ".html")}" target="_blank" rel="noopener">LINEで送る</a></div></div>' +
                f'<div class="layout"><div class="main-col">{day_impacts(items)}<ol class="digest">{lis}</ol>'
                + (f'<nav class="dg-nav">{nav}</nav>' if nav else "") + f'</div>{sidebar(arts, "../", show_digest=False)}</div>')
        (ROOT / "daily" / f"{d}.html").write_text(
            page("../", f"{jp_date(d)}のニュースまとめ読み", f"{jp_date(d)}の世界情勢・経済ニュース{len(items)}本を、3行まとめで確認できます。",
                 body, f"{SITE_URL}daily/{d}.html", active="daily", og_image=og_url("daily-" + d)), encoding="utf-8")
    return days


# ---------- 用語集 ----------
def build_glossary(arts):
    basics = [a for a in arts if a["category"] == "basics"]
    rows = "".join(
        f'<div class="gl-row" id="g-{a["slug"]}"><dt>{"".join(f"<span>{e(w)}</span>" for w in a.get("keywords", []))}</dt>'
        f'<dd><p>{e(a["summary"][0] if a.get("summary") else a["description"])}</p>'
        f'<a href="articles/{a["slug"]}.html">{e(a["title"])} ›</a></dd></div>'
        for a in basics)
    n = sum(len(a.get("keywords", [])) for a in basics)
    body = (page_head("基礎解説", "ニュースの用語集", "ニュースによく出てくる言葉を、ひと言で説明しています。くわしくは各基礎解説へ。", n, unit="の言葉") +
            f'<div class="layout"><div class="main-col"><dl class="glossary-list">{rows}</dl></div>{sidebar(arts, "", home=True)}</div>')
    (ROOT / "glossary.html").write_text(
        page("", "ニュースの用語集", "円安、金利、インフレ、年収の壁など、ニュースによく出てくる言葉をひと言で説明した用語集。", body,
             SITE_URL + "glossary.html", active="basics"), encoding="utf-8")


# ---------- 404 ----------
def build_404(arts):
    news = [a for a in arts if a["category"] != "basics"][:5]
    body = f"""<section class="page-head"><p class="kicker">404</p><h1>ページが見つかりませんでした</h1>
<p>URLが間違っているか、ページが移動した可能性があります。言葉で探すか、新しい記事からお探しください。</p></section>
<div class="layout"><div class="main-col">
<form class="search-box" action="{SITE_PATH}search.html"><input name="q" type="search" placeholder="例：円安、住宅ローン、ガソリン" aria-label="検索キーワード"></form>
<section><h2 class="section-title">新しい記事</h2><ul class="rows">{row_list(news, SITE_PATH)}</ul></section>
</div>{sidebar(arts, SITE_PATH, home=True)}</div>"""
    (ROOT / "404.html").write_text(
        page(SITE_PATH, "ページが見つかりません", "お探しのページは見つかりませんでした。", body, SITE_URL)
        .replace('<meta name="description"', '<meta name="robots" content="noindex">\n<meta name="description"'),
        encoding="utf-8")


# ---------- 固定ページ ----------
def build_pages(arts):
    for f in (SRC / "pages").glob("*.html"):
        text = f.read_text(encoding="utf-8")
        m = re.match(r"\s*<!--(.*?)-->(.*)", text, re.S)
        meta = json.loads(m.group(1))
        content = (f'<div class="layout page-layout"><div class="main-col"><article class="post">{m.group(2).strip()}</article></div>'
                   f'{sidebar(arts, "", home=True)}</div>')
        (ROOT / f.name).write_text(
            page("", meta["title"], meta["description"], content, SITE_URL + f.name), encoding="utf-8")


# ---------- RSS / sitemap / robots ----------
def build_feed(arts):
    jst = timezone(timedelta(hours=9))

    def rfc822(d):
        return datetime.strptime(d, "%Y-%m-%d").replace(hour=6, tzinfo=jst).strftime("%a, %d %b %Y %H:%M:%S +0900")

    items = "".join(
        f"<item><title>{e(a['title'])}</title><link>{SITE_URL}articles/{a['slug']}.html</link>"
        f"<guid>{SITE_URL}articles/{a['slug']}.html</guid><pubDate>{rfc822(a['date'])}</pubDate>"
        f"<category>{CATS[a['category']]}</category><description>{e(a['description'] + ('【くらしへの影響】' + a['impact'] if a.get('impact') else ''))}</description></item>\n"
        for a in arts[:30]
    )
    (ROOT / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{SITE_NAME}</title><link>{SITE_URL}</link><description>{TAGLINE}</description>"
        f"<language>ja</language>\n{items}</channel></rss>\n", encoding="utf-8")


def build_sitemap(arts):
    today = date.today().isoformat()
    urls = [(SITE_URL, today)]
    urls += [(f"{SITE_URL}category/{k}.html", today) for k in CATS]
    urls += [(f"{SITE_URL}topic/{k}.html", today) for k in TOPICS]
    urls += [(f"{SITE_URL}articles/{a['slug']}.html", a.get("updated", a["date"])) for a in arts]
    urls += [(f"{SITE_URL}daily/{d}.html", d) for d in sorted({a["date"] for a in arts if a["category"] != "basics"})]
    urls += [(SITE_URL + "about.html", today), (SITE_URL + "glossary.html", today)]
    xml = "".join(f"<url><loc>{u}</loc><lastmod>{d}</lastmod></url>\n" for u, d in urls)
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{xml}</urlset>\n', encoding="utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    arts = load_articles()
    by_slug = {a["slug"]: a for a in arts}
    for a in arts:
        for t in a["terms"]:
            if t not in by_slug:
                print(f"注意：{a['slug']} の用語メモ {t} はまだ記事がありません（表示されません）")
    (ROOT / "articles").mkdir(exist_ok=True)
    make_og_images(arts)
    make_icons()
    global LATEST_HTML, DAILY_LATEST
    DAILY_LATEST = next((a["date"] for a in arts if a["category"] != "basics"), "")
    ON_CLASS = ' class="on"'
    latest_news = [a for a in arts if a["category"] != "basics"][:3]
    LATEST_HTML = ('<div class="latest"><span class="latest-label">最新</span><div class="latest-items">' + "".join(
        f'<a{ON_CLASS if i == 0 else ""} href="{{rel}}articles/{a["slug"]}.html">{e(a["title"])}</a>'
        for i, a in enumerate(latest_news)) + '</div></div>')
    backlinks = {}
    for a in arts:  # どの記事がどの基礎解説を使っているか（新しい順）
        _, linked = link_terms(a["body"], arts, a["slug"])
        for t in dict.fromkeys(a["terms"] + linked):
            backlinks.setdefault(t, []).append(a["slug"])
    for a in arts:
        build_article(a, arts, by_slug, backlinks)
    build_index(arts)
    build_categories(arts)
    build_topics(arts)
    build_search(arts)
    build_daily(arts)
    build_glossary(arts)
    build_404(arts)
    build_pages(arts)
    build_feed(arts)
    build_sitemap(arts)
    print(f"完了：記事{len(arts)}本")


if __name__ == "__main__":
    main()
