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
  "sources": [["出典名", "URL"]]
}
-->
<h2>何が起きた？</h2>
<p>本文…</p>
"""
import html
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
SITE_URL = "https://kousei221025.github.io/news-kaisetsu/"
SITE_NAME = "3分ニュース解説"
TAGLINE = "世界と経済のニュースを、会社員目線で3分で"

CATS = {
    "world": "世界情勢",
    "economy": "経済",
    "life": "くらし・お金",
    "basics": "基礎解説",
}

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
        if meta["category"] not in CATS:
            raise SystemExit(f"ジャンルが不正です: {f.name} {meta['category']}")
        items.append(meta)
    items.sort(key=lambda a: (a["date"], a.get("rank", 0), a["slug"]), reverse=True)
    return items


def reading_minutes(body):
    chars = len(re.sub(r"<[^>]+>|\s", "", body))
    return max(1, math.ceil(chars / 500))


def jp_date(d):
    y, m, dd = d.split("-")
    return f"{int(y)}年{int(m)}月{int(dd)}日"


def add_heading_ids(body):
    heads = []

    def repl(m):
        n = len(heads) + 1
        heads.append(re.sub(r"<[^>]+>", "", m.group(1)))
        return f'<h2 id="s{n}">{m.group(1)}</h2>'

    return re.sub(r"<h2>(.*?)</h2>", repl, body), heads


# ---------- 共通の枠 ----------
def page(rel, title, description, body, canonical, active=None, og_type="website", extra_head=""):
    full_title = title if title == SITE_NAME else f"{title}｜{SITE_NAME}"
    nav = "".join(
        f'<li><a href="{rel}{href}"{" class=\"on\"" if key == active else ""}>{label}</a></li>'
        for key, href, label in [("home", "index.html", "トップ")]
        + [(k, f"category/{k}.html", v) for k, v in CATS.items()]
    )
    foot_cats = "".join(f'<a href="{rel}category/{k}.html">{v}</a>' for k, v in CATS.items())
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
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary">
<link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{rel}style.css">
{extra_head}</head>
<body>
<header class="site">
  <div class="wrap bar">
    <a class="logo" href="{rel}index.html">3分<b>ニュース解説</b><small>{TAGLINE}</small></a>
    <a class="head-link" href="{rel}about.html">このサイトについて</a>
  </div>
  <nav class="cats" aria-label="ジャンル"><div class="wrap"><ul>{nav}</ul></div></nav>
</header>
<main class="wrap">
{body}
</main>
<footer class="site">
  <div class="wrap">
    <div class="links">{foot_cats}<a href="{rel}about.html">このサイトについて・プライバシーポリシー</a></div>
    © 2026 {SITE_NAME}
  </div>
</footer>
</body>
</html>
"""


def tag(cat, rel=""):
    cls = "tag basics" if cat == "basics" else "tag"
    return f'<span class="{cls}">{CATS[cat]}</span>'


def meta_line(a):
    return (f'<span class="meta"><span>{jp_date(a["date"])}</span>'
            f'<span>{reading_minutes(a["body"])}分で読めます</span></span>')


def list_items(arts, rel):
    return "".join(
        f'<li><a href="{rel}articles/{a["slug"]}.html">{tag(a["category"])} {meta_line(a)}'
        f'<h3>{e(a["title"])}</h3></a></li>'
        for a in arts
    )


# ---------- 記事ページ ----------
def build_article(a, all_arts, by_slug):
    rel = "../"
    body, heads = add_heading_ids(a["body"])
    url = f"{SITE_URL}articles/{a['slug']}.html"

    summary = "".join(f"<li>{e(s)}</li>" for s in a.get("summary", []))
    toc = "".join(f'<li><a href="#s{i}">{e(h)}</a></li>' for i, h in enumerate(heads, 1))

    terms = [by_slug[t] for t in a["terms"] if t in by_slug and t != a["slug"]]
    terms_box = ""
    if terms:
        lis = "".join(f'<li><a href="{t["slug"]}.html">{e(t["title"])}</a></li>' for t in terms)
        terms_box = f'<div class="box terms"><b>用語メモ：あわせて読むと分かりやすい基礎解説</b><ul>{lis}</ul></div>'

    srcs = "".join(f'<li><a href="{e(u)}" rel="nofollow noopener" target="_blank">{e(n)}</a></li>'
                   for n, u in a["sources"])
    caution = "投資やローンの判断はご自身でお願いします。" if a["category"] in ("economy", "life", "basics") else ""

    share_text = f"{a['title']}｜{SITE_NAME}"
    from urllib.parse import quote
    share = (f'<div class="share"><span>この記事をシェア</span>'
             f'<a class="x" href="https://twitter.com/intent/tweet?url={quote(url)}&text={quote(share_text)}" target="_blank" rel="noopener">X</a>'
             f'<a class="line" href="https://social-plugins.line.me/lineit/share?url={quote(url)}" target="_blank" rel="noopener">LINE</a></div>')

    related = [r for r in all_arts if r["slug"] != a["slug"] and r not in terms and
               (r["category"] == a["category"] or set(r["terms"]) & set(a["terms"]) or a["slug"] in r["terms"])][:4]
    related_html = (f'<h2 class="section-title">関連記事</h2><ul class="list">{list_items(related, rel)}</ul>'
                    if related else "")

    ld = {
        "@context": "https://schema.org",
        "@type": "Article" if a["category"] == "basics" else "NewsArticle",
        "headline": a["title"],
        "description": a["description"],
        "datePublished": a["date"],
        "dateModified": a.get("updated", a["date"]),
        "inLanguage": "ja",
        "author": {"@type": "Person", "name": "ミナト"},
        "publisher": {"@type": "Organization", "name": SITE_NAME},
        "mainEntityOfPage": url,
    }
    extra = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n'

    updated = f'<p class="meta">{jp_date(a["updated"])} 更新</p>' if a.get("updated") else ""
    content = f"""<div class="narrow">
<nav class="crumbs"><a href="{rel}index.html">トップ</a> ＞ <a href="{rel}category/{a["category"]}.html">{CATS[a["category"]]}</a></nav>
<article class="post">
  {tag(a["category"])} {meta_line(a)}
  <h1>{e(a["title"])}</h1>
  {updated}
  <div class="summary"><b>3行まとめ</b><ul>{summary}</ul></div>
  <nav class="toc"><b>目次</b><ol>{toc}</ol></nav>
  {body}
  {terms_box}
  <div class="sources">
    <b>出典</b><ul>{srcs}</ul>
    <p class="note-ai">この記事はAIの補助を受けて作成し、上記の出典で内容を確認しています。{caution}誤りに気づいた方は<a href="{rel}about.html">お問い合わせ</a>からお知らせください。</p>
  </div>
  {share}
</article>
{related_html}
</div>"""
    out = ROOT / "articles" / f"{a['slug']}.html"
    out.write_text(page(rel, a["title"], a["description"], content, url,
                        active=a["category"], og_type="article", extra_head=extra), encoding="utf-8")


# ---------- トップ ----------
def build_index(arts):
    news = [a for a in arts if a["category"] != "basics"]
    basics = [a for a in arts if a["category"] == "basics"]
    points = "".join(
        f'<li><a href="articles/{a["slug"]}.html"><span>{tag(a["category"])} {meta_line(a)}</span>'
        f'<h3>{e(a["title"])}</h3><p>{e(a["description"])}</p></a></li>'
        for a in news[:3]
    )
    shelf = "".join(
        f'<a href="articles/{a["slug"]}.html">{tag("basics")}<h3>{e(a["title"])}</h3></a>' for a in basics
    )
    body = f"""<section class="hero">
  <h1>むずかしいニュースを、<br>会社員目線で3分で。</h1>
  <p>世界情勢・経済のニュースが「自分の生活にどう関係するか」まで、やさしく解説します。</p>
</section>
<h2 class="section-title">今日のポイント<small>まずはこの3本</small></h2>
<ol class="points">{points}</ol>
<h2 class="section-title">基礎から学ぶ<small>ニュースがもっと分かる</small></h2>
<div class="shelf">{shelf}</div>
<h2 class="section-title">新着記事</h2>
<ul class="list">{list_items(news[3:23], "")}</ul>"""
    (ROOT / "index.html").write_text(
        page("", SITE_NAME, "世界情勢や経済のむずかしいニュースを、会社員の生活にどう関係するかという目線で、3分で読めるように解説します。",
             body, SITE_URL, active="home"), encoding="utf-8")


# ---------- ジャンル別 ----------
def build_categories(arts):
    (ROOT / "category").mkdir(exist_ok=True)
    for key, label in CATS.items():
        items = [a for a in arts if a["category"] == key]
        body = (f'<section class="hero"><h1>{label}</h1><p>{len(items)}本の記事</p></section>'
                f'<ul class="list">{list_items(items, "../")}</ul>')
        url = f"{SITE_URL}category/{key}.html"
        (ROOT / "category" / f"{key}.html").write_text(
            page("../", label, f"{label}の記事一覧。{TAGLINE}。", body, url, active=key), encoding="utf-8")


# ---------- 固定ページ ----------
def build_pages():
    for f in (SRC / "pages").glob("*.html"):
        text = f.read_text(encoding="utf-8")
        m = re.match(r"\s*<!--(.*?)-->(.*)", text, re.S)
        meta = json.loads(m.group(1))
        content = f'<div class="narrow"><article class="post">{m.group(2).strip()}</article></div>'
        (ROOT / f.name).write_text(
            page("", meta["title"], meta["description"], content, SITE_URL + f.name), encoding="utf-8")


# ---------- sitemap / robots ----------
def build_sitemap(arts):
    urls = [(SITE_URL, date.today().isoformat())]
    urls += [(f"{SITE_URL}category/{k}.html", date.today().isoformat()) for k in CATS]
    urls += [(f"{SITE_URL}articles/{a['slug']}.html", a.get("updated", a["date"])) for a in arts]
    urls += [(SITE_URL + "about.html", date.today().isoformat())]
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
    for a in arts:
        build_article(a, arts, by_slug)
    build_index(arts)
    build_categories(arts)
    build_pages()
    build_sitemap(arts)
    print(f"完了：記事{len(arts)}本")


if __name__ == "__main__":
    main()
