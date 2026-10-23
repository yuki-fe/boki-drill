"""簿記用語ドリル（簿記検定3級・2級の用語）の静的サイトを docs/ に書き出す。

使い方:  python build.py
入力:    config.json（サイトの設定）、data/terms.json（用語。data/make_terms.py が作る）、static/（CSS・JS）
出力:    docs/（GitHub Pages でそのまま公開できる）
"""
import json
import random
import re
import shutil
import sys
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
OUT = ROOT / "docs"
FIELDS = {"K": "簿記の基本", "A": "現金・債権・債務", "G": "商品売買", "F": "固定資産・税金・純資産", "P": "収益と費用", "C": "決算",
          "N": "2級 商業簿記", "W": "2級 工業簿記"}
LEVEL2 = ("N", "W")   # 2級の分野
level = lambda t: "2級" if t["field"] in LEVEL2 else "3級"
KINDS = ["資産", "負債", "純資産", "収益", "費用"]
KANA = ["ア", "イ", "ウ", "エ"]
# ミニテストの1回分の問題数（3級の6つの分野と、2級の2つの分野から。用語の数に合わせた）
TEST_COUNTS = {"K": 2, "A": 3, "G": 2, "F": 2, "P": 2, "C": 2, "N": 4, "W": 3}

config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
terms = json.loads((ROOT / "data" / "terms.json").read_text(encoding="utf-8"))
BASE = config["base_url"].rstrip("/")
SITE = config["site_name"]
SISTERS = config.get("sisters", [])
TODAY = date.today().isoformat()
KAMOKU = [t for t in terms if t.get("kind")]


# ---------- 用語の文字列処理 ----------

def aliases(term):
    """「排他的論理和（XOR）」→ 全体・「排他的論理和」・「XOR」のように別名を返す。"""
    out = [term]
    m = re.match(r"^(.*?)[（(](.*?)[)）](.*)$", term)
    if m:
        out.append((m.group(1) + m.group(3)).strip())
        out += [s.strip() for s in re.split(r"[、,]", m.group(2))]
    for a in list(out):
        out += [s.strip() for s in re.split(r"\s*/\s*", a)]
    return [a for a in dict.fromkeys(out) if a]


def mask_words(term):
    """隠す言葉。「AとB」の形の用語は、AとBも隠す（「の」を含む用語は分けない）。"""
    out = aliases(term)
    for a in list(out):
        if "の" not in a and "と" in a:
            out += [p.strip() for p in re.split(r"\s*と\s*", a) if p.strip() != "AI"]
    return [a for a in dict.fromkeys(out) if len(a) >= 2]


def masked(t):
    """説明文の中に出てくる答えの用語を「〇〇」で隠す。"""
    d = t["desc"]
    for a in sorted(mask_words(t["term"]), key=len, reverse=True):
        d = d.replace(a, "〇〇")
    return d


# ---------- 共通レイアウト ----------

def head_extras():
    tags = []
    ga = config.get("google_analytics_id")
    if ga:
        tags.append(f'<script async src="https://www.googletagmanager.com/gtag/js?id={escape(ga)}"></script>'
                    f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}"
                    f"gtag('js',new Date());gtag('config','{escape(ga)}');</script>")
    ad = config.get("adsense_client")
    if ad:
        tags.append(f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={escape(ad)}" crossorigin="anonymous"></script>')
    return "\n".join(tags)


SITEMAP = []  # page() で書き出したページの URL（sitemap.xml に載せる）


# ---------- レイアウト（FE用語ドリルと同じ形。見た目は static/assets/layout.css） ----------
NAV = [('index.html', '用語ドリル'), ('test.html', 'ミニテスト'), ('kamoku.html', '勘定科目'), ('terms/index.html', '用語一覧'), ('about.html', 'このサイトについて')]


def nav_links(path, rel):
    """今いる場所のリンクに aria-current を付ける（用語ページなら「用語一覧」）"""
    def current(href):
        return path == href or (href == "terms/index.html" and path.startswith("terms/"))
    cur = ' aria-current="page"'
    return "".join(f'<a href="{rel}{h}"{cur if current(h) else ""}>{label}</a>' for h, label in NAV)


# 線のアイコン（Lucide の形をもとに、そのまま SVG で入れる）
ICONS = {
    "cards": '<rect x="3" y="6" width="14" height="14" rx="2"/><path d="M7 2h12a2 2 0 0 1 2 2v12"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "type": '<path d="M4 7V5h16v2"/><path d="M9 20h6"/><path d="M12 5v15"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "pencil": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
}


def icon(name):
    return f'<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


# 「カードで練習する」など、学び方つきのリンク（#card）から来たときは、学習の欄まで送る（app.js が # を書き換える前に読む）
JUMP = '<script>if (/^#(card|quiz|type|review|list)$/.test(location.hash)) addEventListener("load", () => document.getElementById("study").scrollIntoView());</script>\n'


def page(path, title, desc, body, rel, body_class="", jsonld=None, scripts="", index=True):
    """path は docs/ からの相対パス。rel はそのページからサイトのルートへの相対パス（"" / "../"）。"""
    url = BASE + "/" + ("" if path == "index.html" else path)
    if index:
        SITEMAP.append(url)
    ld = "".join(f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>' for j in (jsonld or []))
    sister = ("<p>姉妹サイト: " + "／".join(f'<a href="{escape(s["url"])}/">{escape(s["name"])}</a>' for s in SISTERS) + "</p>"
              if SISTERS else "")
    html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{escape(url)}">
<meta property="og:type" content="{'website' if path == 'index.html' else 'article'}">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:url" content="{escape(url)}">
<meta property="og:site_name" content="{escape(SITE)}">
<meta name="twitter:card" content="summary">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Zen+Maru+Gothic:wght@400;500;700&family=JetBrains+Mono:wght@500&display=swap">
<link rel="stylesheet" href="{rel}assets/style.css">
<link rel="stylesheet" href="{rel}assets/layout.css">
<link rel="icon" href="{rel}favicon.ico" sizes="48x48">
<link rel="icon" href="{rel}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{rel}apple-touch-icon.png">
{'' if index else '<meta name="robots" content="noindex">'}
{head_extras()}
{ld}
</head>
<body class="{body_class}" data-root="{rel}">
<a class="skip" href="#content">本文へ移動</a>
<header class="site-head">
  <div class="site-head-in">
    <a class="brand" href="{rel}index.html"><img src="{rel}favicon.svg" alt="" width="28" height="28">{escape(SITE)}</a>
    <nav class="site-nav" aria-label="サイト内">
      {nav_links(path, rel)}
    </nav>
  </div>
</header>
<div id="content"></div>
{body}
<footer class="site-foot">
  <nav aria-label="フッター">
    <a href="{rel}terms/index.html">用語一覧</a>
    <a href="{rel}about.html">運営者情報</a>
    <a href="{rel}privacy.html">プライバシーポリシー・免責事項</a>
  </nav>
  {sister}
  <p>簿記検定（商工会議所簿記検定試験）は、日本商工会議所と各地の商工会議所が実施する検定です。当サイトは、検定の実施団体とは関係のない個人の学習サイトです。</p>
  <p>© {date.today().year} {escape(config.get("operator") or SITE)}</p>
</footer>
{scripts}
</body>
</html>
"""
    dest = OUT / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")


def pr_box():
    """アフィリエイトの枠。景品表示法（ステマ規制）に従い「PR」と表示する。"""
    snippet = config.get("affiliate_html", "").strip()
    if not snippet:
        return ""
    return f'<aside class="pr-box"><span class="pr-label">PR</span><p class="pr-title">試験対策におすすめの教材</p>{snippet}</aside>'


def breadcrumb_ld(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)]}


def crumbs(rel, *items):
    parts = [f'<a href="{rel}index.html">ホーム</a>']
    for label, href in items:
        parts.append(f'<a href="{href}">{escape(label)}</a>' if href else f"<span>{escape(label)}</span>")
    return '<nav class="crumbs" aria-label="パンくずリスト">' + "<span>›</span>".join(parts) + "</nav>"


# ---------- 各ページ ----------

def build_home():
    counts = {k: sum(t["field"] == k for t in terms) for k in FIELDS}
    field_links = "".join(f'<li><a href="terms/index.html#{k}">{v}</a><span class="mono">{counts[k]}語</span></li>' for k, v in FIELDS.items())
    n_test = sum(TEST_COUNTS.values())
    sisters = ""
    if SISTERS:
        items = "".join(f'<li><a href="{escape(s["url"])}/">{escape(s["name"])}</a>（{escape(s["desc"])}）</li>' for s in SISTERS)
        sisters = f"""
  <h2>姉妹サイト</h2>
  <p>同じ運営者が、IT の資格の学習サイトをほかにも作っています。</p>
  <ul>{items}</ul>"""
    body = f"""
<section class="hero" aria-labelledby="hero-h">
  <div class="hero-text">
    <p class="hero-eyebrow">簿記検定3級・2級の対策・無料</p>
    <h1 id="hero-h"><span>簿記の用語を、</span><span>すきま時間に。</span><br><span>勘定科目の分類も、</span><span>クイズで覚える。</span></h1>
    <p class="hero-lead">3級・2級（商業簿記・工業簿記）の勘定科目と用語{len(terms)}語を、単語帳とクイズで覚えられます。2027年4月からの出題範囲に対応しています。登録は要りません。</p>
    <div class="hero-cta">
      <a class="btn primary" href="#study">用語を覚えはじめる</a>
      <a class="btn" href="test.html">ミニテストに挑戦</a>
    </div>
    <ul class="hero-stats" aria-label="収録の数">
      <li><b class="mono">{len(terms)}</b><span>用語</span></li>
      <li><b class="mono">{len(KAMOKU)}</b><span>勘定科目</span></li>
      <li><b class="mono">{len(FIELDS)}</b><span>分野</span></li>
    </ul>
  </div>
  <aside class="hero-progress" aria-labelledby="prog-h">
    <h2 id="prog-h">あなたの進み具合</h2>
    <p class="hero-progress-sub">分野を押すと、その分野だけで学習します</p>
    <div class="fields" id="fields"></div>
    <p class="save-note">進み具合はこのブラウザに保存されます。<button id="reset" type="button">リセット</button></p>
  </aside>
</section>

<section class="study" id="study" aria-labelledby="study-h">
  <div class="study-head">
    <h2 id="study-h" class="sec-title">学習する</h2>
    <nav class="modes" role="tablist" id="modes" aria-label="学び方"></nav>
  </div>
  <div class="study-body">
    <div class="toolbar" id="toolbar"></div>
    <section class="panel" id="panel"><noscript><p class="empty">この学習機能を使うには JavaScript を有効にしてください。<a href="terms/index.html">用語一覧</a>はそのまま読めます。</p></noscript></section>
  </div>
</section>

<section class="features" aria-labelledby="feat-h">
  <h2 id="feat-h" class="sec-title">できること</h2>
  <div class="feat-grid"><a class="feat" href="#study">{icon("cards")}<b>単語帳とクイズ</b><span>{len(terms)}語をカード・4択・書いて答えるで。間違えた用語だけを復習できます。</span><em>学習を始める →</em></a><a class="feat" href="test.html">{icon("target")}<b>ミニテスト</b><span>3級・2級の8つの分野から{n_test}問。分野ごとの正答率がわかる。</span><em>挑戦する →</em></a><a class="feat" href="kamoku.html">{icon("layers")}<b>勘定科目</b><span>資産・負債・純資産・収益・費用のどれ？{len(KAMOKU)}科目の分類クイズ。</span><em>覚える →</em></a><a class="feat" href="terms/index.html">{icon("list")}<b>用語一覧</b><span>分野・小分類ごとに全部の用語を一覧で。1語ずつ解説ページがあります。</span><em>一覧を見る →</em></a></div>
</section>

<section class="prose home-intro">
  <h2 class="intro-title">{escape(SITE)}について<small>{escape(config["tagline"])}</small></h2>
  <p>簿記検定3級・2級に出てくる勘定科目と用語を、{len(terms)}語収録しています。3級の簿記の基本から、現金・預金、商品の売買、固定資産、税金、決算まで。2級の有価証券・収益認識・リース・税効果会計・連結会計と、工業簿記（原価計算）まで。はじめて簿記を学ぶ人にも分かるように、やさしい言葉で説明しています。登録は不要で、スマホでもパソコンでも無料で使えます。</p>
  <h2>学び方</h2>
  <dl class="howto">
    <dt>カード</dt><dd>意味を読んで用語を思い出し、裏返して確かめます。「用語 → 意味」の向きにも切り替えられます。</dd>
    <dt>4択クイズ</dt><dd>ア〜エの選択肢から答えを選びます。同じ分野の、まぎらわしい用語がひっかけとして並びます。</dd>
    <dt>書いて答える</dt><dd>説明を読んで、用語を自分で入力します。「法人税、住民税及び事業税（法人税等）」なら「法人税等」でも正解になります。</dd>
    <dt>復習</dt><dd>「まだ」を押した用語や、クイズで間違えた用語だけを集めて、学習し直せます。</dd>
    <dt>ミニテスト</dt><dd>3級・2級の8つの分野から{n_test}問を出します。分野ごとの正答率がわかります。</dd>
    <dt>勘定科目の分類</dt><dd>勘定科目が資産・負債・純資産・収益・費用のどれに入るか、増えたら借方か貸方かを覚えます。</dd>
  </dl>
  <h2>試験の範囲</h2>
  <p>試験の範囲は、実施団体の「出題区分表」で級ごとに決められています。このサイトでは、3級を6つの分野、2級を「2級 商業簿記」と「2級 工業簿記」の2つの分野に分けています。3級は60分で、2級は90分です。どちらも70%以上の得点で合格です。テストセンターで受けるネット試験と、決まった日に受ける統一試験があります。</p>
  <p><b>2027年4月からの試験では</b>、紙の手形・小切手の廃止と、新しいリースの会計基準にあわせて出題区分表が改定されます。「手形」が範囲から外れ、有形固定資産の除却・定率法などが2級から3級に移ります。2級のリースは「使用権資産」「リース負債」を使う形になります。このサイトは2027年4月からの範囲にもとづいています。2027年3月までに受ける人のために、手形の用語も「手形（2027年3月まで）」にまとめて残しています。</p>
  <ul class="field-list">{field_links}</ul>
  <p>すべての用語は<a href="terms/index.html">用語一覧</a>から、1語ずつ解説ページで読めます。</p>
  {sisters}
  <p class="muted">このサイトは、実施団体が公開している出題区分表と勘定科目表（2027年4月1日施行の版）にもとづいています（2026年10月時点）。試験の日程・範囲・配点は変わることがあるので、受験の前に、実施団体のサイトで確認してください。</p>
</section>
"""
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": SITE, "url": BASE + "/", "description": config["description"]}]
    page("index.html", f"{SITE}｜{config['tagline']}", config["description"], body, "", "home", ld,
         JUMP + '<script src=\"assets/terms.js\"></script>\n<script src="assets/app.js"></script>')


def related_terms(t, n=6):
    same = [x for x in terms if x["sub"] == t["sub"] and x["id"] != t["id"]]
    if len(same) < 3:
        same += [x for x in terms if x["field"] == t["field"] and x["sub"] != t["sub"]][: 3 - len(same) + 3]
    i = int(t["id"])
    same.sort(key=lambda x: abs(int(x["id"]) - i))
    return same[:n]


def mini_quiz(t, related):
    rng = random.Random(t["id"])
    target = rng.choice(related)
    pool = [x for x in terms if x["sub"] == target["sub"] and x["id"] != target["id"]]
    if len(pool) < 3:
        pool += [x for x in terms if x["field"] == target["field"] and x["sub"] != target["sub"]]
    choices = rng.sample(pool, 3) + [target]
    rng.shuffle(choices)
    answer = choices.index(target)
    buttons = "".join(
        f'<button class="choice" type="button" data-k="{k}"><span class="oval">{KANA[k]}</span><span>{escape(c["term"])}</span></button>'
        for k, c in enumerate(choices))
    return f"""
  <section class="mini-quiz" data-answer="{answer}" data-term="{escape(target['term'])}" data-href="{target['id']}.html">
    <h2>確認問題</h2>
    <p>次の説明に当てはまる用語はどれか。</p>
    <p class="qd">{escape(masked(target))}</p>
    <div class="choices">{buttons}</div>
    <p class="quiz-result" hidden></p>
  </section>"""


def build_term(t, prev, nxt):
    field = FIELDS[t["field"]]
    rel = related_terms(t)
    related_html = "".join(f'<li><a href="{x["id"]}.html">{escape(x["term"])}</a><p>{escape(x["desc"])}</p></li>' for x in rel)
    pager = '<nav class="pager" aria-label="前後の用語">'
    pager += f'<a href="{prev["id"]}.html" rel="prev"><small>前の用語</small>{escape(prev["term"])}</a>' if prev else "<span></span>"
    pager += f'<a href="{nxt["id"]}.html" rel="next" class="next"><small>次の用語</small>{escape(nxt["term"])}</a>' if nxt else "<span></span>"
    pager += "</nav>"
    side = {"資産": "増えたら借方", "負債": "増えたら貸方", "純資産": "増えたら貸方", "収益": "発生したら貸方", "費用": "発生したら借方"}
    abbr = f'<p class="abbr-full kind-full"><span>分類</span><span>{t["kind"]}の勘定（{side[t["kind"]]}）</span></p>' if t.get("kind") else ""
    abbr_cta = '<a class="btn" href="../kamoku.html">勘定科目の分類クイズ</a>' if t.get("kind") else '<a class="btn" href="../index.html#type">書いて答える問題に挑戦</a>'
    body = f"""
<div class="term-wrap">
  <nav class="crumbs" aria-label="パンくずリスト"><a href="../index.html">ホーム</a><span>›</span><a href="index.html#{t['field']}">{field}</a><span>›</span><a href="index.html#sub-{t['field']}-{escape(t['sub'])}">{escape(t['sub'])}</a></nav>
  <div class="term-grid">
    <main class="prose term-page term-main">
      <p class="eyebrow">{field}・{escape(t['sub'])}<span class="term-no mono">No.{int(t['id']):03d} / {len(terms)}</span></p>
      <h1>{escape(t['term'])}</h1>
      {abbr}
      <p class="lead">{escape(t['desc'])}</p>
      <div class="cta-row cta-mobile">
        <a class="btn primary" href="../index.html#card">{icon("cards")}カードで練習</a>
        {abbr_cta}
      </div>
      {mini_quiz(t, rel)}
      {pr_box()}
      {pager}
    </main>
    <aside class="term-side" aria-label="練習と関連する用語">
      <section class="side-card">
        <h2>この用語を練習する</h2>
        <a class="btn primary" href="../index.html#card">{icon("cards")}カードで練習</a>
        <a class="btn" href="../index.html#type">{icon("pencil")}書いて答える</a>
        <a class="btn" href="../test.html">{icon("target")}ミニテストに挑戦</a>
      </section>
      <section class="side-card">
        <h2>同じ分野の用語</h2>
        <ul class="related">{related_html}</ul>
      </section>
    </aside>
  </div>
</div>
"""
    url = f"{BASE}/terms/{t['id']}.html"
    ld = [
        {"@context": "https://schema.org", "@type": "DefinedTerm", "name": t["term"], "description": t["desc"], "url": url,
         "inDefinedTermSet": {"@type": "DefinedTermSet", "name": f"{SITE} 簿記3級・2級 用語集", "url": f"{BASE}/terms/index.html"}},
        breadcrumb_ld([("ホーム", BASE + "/"), (field, f"{BASE}/terms/index.html#{t['field']}"), (t["term"], url)]),
    ]
    short = t["desc"] if len(t["desc"]) <= 100 else t["desc"][:99] + "…"
    page(f"terms/{t['id']}.html", f"{t['term']}とは？意味と覚え方｜簿記{level(t)}の用語｜{SITE}",
         f"{t['term']}（{field}・{t['sub']}）: {short}", body, "../", "", ld, '<script src="../assets/term.js"></script>')


def build_index():
    sections, toc = [], []
    for k, v in FIELDS.items():
        group = [t for t in terms if t["field"] == k]
        subs = list(dict.fromkeys(t["sub"] for t in group))
        toc.append(f'<li><a href="#{k}">{v}</a><span class="mono">{len(group)}語</span></li>')
        sub_toc = "".join(f'<a href="#sub-{k}-{escape(s)}">{escape(s)}</a>' for s in subs)
        blocks = []
        for s in subs:
            items = "".join(f'<li><a href="{t["id"]}.html">{escape(t["term"])}</a><p>{escape(t["desc"])}</p></li>' for t in group if t["sub"] == s)
            blocks.append(f'<h3 id="sub-{k}-{escape(s)}">{escape(s)}</h3><ul class="term-list">{items}</ul>')
        sections.append(f'<section><h2 id="{k}">{v}</h2><p class="sub-toc">{sub_toc}</p>{"".join(blocks)}</section>')
    body = f"""
<main class="prose wide">
  {crumbs("../", ("用語一覧", None))}
  <h1>簿記3級・2級の用語一覧<small>{len(terms)}語</small></h1>
  <p>簿記3級・2級の勘定科目と用語を、分野ごとに並べています。2級の分野は「2級 商業簿記」「2級 工業簿記」です。用語名から解説ページに進めます。</p>
  <ul class="field-list">{''.join(toc)}</ul>
  {pr_box()}
  {''.join(sections)}
</main>
"""
    page("terms/index.html", f"簿記3級・2級の用語一覧（{len(terms)}語）｜{SITE}",
         f"簿記3級・2級の勘定科目と用語{len(terms)}語を、分野ごとに一覧にしました。各用語の意味を、やさしい言葉で確認できます。",
         body, "../", "", [breadcrumb_ld([("ホーム", BASE + "/"), ("用語一覧", f"{BASE}/terms/index.html")])])


def build_test():
    n = sum(TEST_COUNTS.values())
    mix = "・".join(f"{FIELDS[k]} {v}問" for k, v in TEST_COUNTS.items())
    body = f"""
<main class="prose wide drill-page">
  {crumbs("", ("ミニテスト", None))}
  <h1>分野別ミニテスト<small>3級・2級の8つの分野から{n}問。分野ごとの正答率がわかる</small></h1>
  <div id="drill" data-drill="test"><noscript><p class="empty">ミニテストを使うには JavaScript を有効にしてください。</p></noscript></div>
  <section>
    <h2>ミニテストについて</h2>
    <ul>
      <li>1回{n}問（{mix}）。</li>
      <li>説明文を読んで、当てはまる用語をア〜エから選びます。答えはすべて解き終わってから表示します。</li>
      <li>間違えた用語は、ホームの「復習」に入ります。</li>
    </ul>
    <p>本番の試験は60分で、仕訳の問題がたくさん出ます。仕訳では、取引に合う勘定科目を選べることが大切です。正答率の低い分野から重点的に復習しましょう。</p>
    <p class="muted">このミニテストは用語の確認のためのもので、本番の問題の形や採点の方法とは異なります。</p>
  </section>
</main>
"""
    page("test.html", f"簿記3級・2級 分野別ミニテスト（{n}問）｜{SITE}",
         f"簿記3級・2級の8つの分野から{n}問の用語ミニテスト。分野ごとの正答率がわかり、苦手な分野を見つけられます。無料・登録不要。",
         body, "", "", scripts='<script src="assets/terms.js"></script>\n<script src="assets/drill.js"></script>')


def build_kamoku():
    rule = "".join(f'<tr><th>{k}</th><td>{w}たら<b>{s}</b></td><td>{"減ったら" if w == "増え" else "減ったら"}{"貸方" if s == "借方" else "借方"}</td></tr>'
                   for k, w, s in [("資産", "増え", "借方"), ("負債", "増え", "貸方"), ("純資産", "増え", "貸方"),
                                   ("収益", "発生し", "貸方"), ("費用", "発生し", "借方")])
    tables = []
    for k in KINDS:
        rows = "".join(f'<tr><th><a href="terms/{t["id"]}.html">{escape(t["term"])}</a></th><td>{escape(t["desc"])}</td></tr>'
                       for t in KAMOKU if t["kind"] == k)
        tables.append(f'<h3 id="kind-{k}">{k}（{sum(t["kind"] == k for t in KAMOKU)}科目）</h3><div class="table-scroll"><table class="abbr-table"><thead><tr><th>勘定科目</th><th>意味</th></tr></thead><tbody>{rows}</tbody></table></div>')
    body = f"""
<main class="prose wide drill-page">
  {crumbs("", ("勘定科目の分類", None))}
  <h1>勘定科目の分類クイズ<small>資産・負債・純資産・収益・費用のどれ？（{len(KAMOKU)}科目）</small></h1>
  <p>仕訳で迷わないためには、勘定科目が5つのグループのどれに入るかと、増えたときに借方・貸方のどちらに書くかを覚えるのが近道です。</p>
  <div id="drill" data-drill="kamoku"><noscript><p class="empty">クイズを使うには JavaScript を有効にしてください。下の早見表はそのまま読めます。</p></noscript></div>
  <section>
    <h2>増えたら借方？貸方？</h2>
    <div class="table-scroll"><table class="abbr-table kind-rule"><thead><tr><th>グループ</th><th>増えたとき・発生したとき</th><th>減ったとき</th></tr></thead><tbody>{rule}</tbody></table></div>
    <p>貸借対照表で左側にある資産は借方、右側にある負債・純資産は貸方が「増える側」です。損益計算書では、費用が借方、収益が貸方です。</p>
  </section>
  <section>
    <h2>勘定科目の早見表</h2>
    <p class="sub-toc">{"".join(f'<a href="#kind-{k}">{k}</a>' for k in KINDS)}</p>
    {"".join(tables)}
    <p class="muted">貸倒引当金や減価償却累計額は、資産から差し引いて見る勘定、現金過不足は一時的な勘定なので、このクイズには入れていません。</p>
  </section>
</main>
"""
    page("kamoku.html", f"勘定科目の分類クイズと一覧（{len(KAMOKU)}科目）｜{SITE}",
         f"簿記3級・2級の勘定科目{len(KAMOKU)}個が、資産・負債・純資産・収益・費用のどれに入るかを覚えるクイズと早見表。増えたら借方か貸方かも確認できます。無料・登録不要。",
         body, "", "", scripts='<script src="assets/terms.js"></script>\n<script src="assets/drill.js"></script>')


def contact_html():
    c = config.get("contact", "").strip()
    if not c:
        return "（お問い合わせ先を config.json の contact に設定してください）"
    if c.startswith("http"):
        return f'<a href="{escape(c)}">お問い合わせフォーム</a>'
    return escape(c)


def build_about():
    op = escape(config.get("operator") or "（運営者名を config.json の operator に設定してください）")
    sister = ("<h2>姉妹サイト</h2><ul>" + "".join(f'<li><a href="{escape(s["url"])}/">{escape(s["name"])}</a>: {escape(s["desc"])}</li>' for s in SISTERS)
              + "</ul><p>同じ運営者が作っています。</p>") if SISTERS else ""
    body = f"""
<main class="prose">
  <h1>このサイトについて</h1>
  <h2>サイトの目的</h2>
  <p>{escape(SITE)}は、簿記検定3級・2級を受ける人が、すきま時間に勘定科目と用語を覚えられるように作った無料の学習サイトです。はじめて簿記を学ぶ人にも分かるように、やさしい言葉で説明することを心がけています。</p>
  <h2>用語の説明について</h2>
  <p>用語の説明は、運営者がAIの支援を受けて作成し、内容を確認したうえで掲載しています。収録する用語は、検定の実施団体が公開している出題区分表と勘定科目表（2027年4月1日施行の版）の3級・2級の範囲と、工業簿記・原価計算の出題区分表の2級の範囲をもとに選んでいます。会計の基準や税金の決まりは変わることがあるので、最新の情報は、実施団体の発表で確認してください。誤りに気づいた場合は、下記のお問い合わせ先から教えていただけると助かります。</p>
  <h2>運営者情報</h2>
  <table class="info">
    <tr><th>サイト名</th><td>{escape(SITE)}</td></tr>
    <tr><th>運営者</th><td>{op}</td></tr>
    <tr><th>開設日</th><td>{escape(config.get("established", ""))}</td></tr>
    <tr><th>お問い合わせ</th><td>{contact_html()}</td></tr>
  </table>
  {sister}
  <p>当サイトは、検定の実施団体とは関係ありません。</p>
</main>
"""
    page("about.html", f"このサイトについて｜{SITE}", f"{SITE}の目的と運営者情報です。", body, "")


def build_privacy():
    parts = []
    if config.get("google_analytics_id"):
        parts.append("""<h2>アクセス解析ツールについて</h2>
  <p>当サイトでは、Googleによるアクセス解析ツール「Googleアナリティクス」を使っています。Googleアナリティクスはデータの収集のためにCookieを使用します。このデータは匿名で収集されており、個人を特定するものではありません。この機能はブラウザの設定でCookieを無効にすることで拒否できます。詳しくは<a href="https://marketingplatform.google.com/about/analytics/terms/jp/">Googleアナリティクス利用規約</a>をご覧ください。</p>""")
    if config.get("adsense_client"):
        parts.append("""<h2>広告の配信について</h2>
  <p>当サイトでは、第三者配信の広告サービス「Google AdSense」を利用しています。Googleなどの第三者配信事業者は、Cookieを使用して、利用者が当サイトや他のサイトに過去にアクセスした際の情報に基づいて広告を配信します。利用者は<a href="https://adssettings.google.com/">広告設定</a>でパーソナライズ広告を無効にできます。詳しくは<a href="https://policies.google.com/technologies/ads?hl=ja">Googleの広告に関するポリシー</a>をご覧ください。</p>""")
    if config.get("affiliate_html") or config.get("amazon_associate"):
        amazon = "<p>当サイトは、Amazon.co.jpを宣伝しリンクすることによってサイトが紹介料を獲得できる手段を提供することを目的に設定されたアフィリエイトプログラムである、Amazonアソシエイト・プログラムの参加者です。</p>" if config.get("amazon_associate") else ""
        parts.append(f"""<h2>アフィリエイトプログラムについて</h2>
  <p>当サイトには、商品やサービスを紹介するアフィリエイトリンクが含まれます。該当する箇所には「PR」と表示しています。</p>
  {amazon}""")
    body = f"""
<main class="prose">
  <h1>プライバシーポリシー・免責事項</h1>
  <h2>学習の記録について</h2>
  <p>学習機能の進み具合（覚えた用語やミニテストの結果など）は、利用者のブラウザの中（localStorage）にだけ保存されます。運営者のサーバに送られることはありません。ブラウザのデータを消去すると、進み具合も消えます。</p>
  <h2>個人情報の利用目的</h2>
  <p>お問い合わせの際に、お名前やメールアドレスなどの個人情報をご提供いただく場合があります。これらの情報は、お問い合わせへの回答や必要な連絡のためにだけ利用し、法令に基づく場合を除き、本人の同意なく第三者に提供しません。</p>
  {''.join(parts)}
  <h2>免責事項</h2>
  <p>当サイトの内容は、できる限り正確な情報を掲載するよう努めていますが、正確性や最新性を保証するものではありません。当サイトの情報を利用したことで生じた損害について、運営者は責任を負いません。</p>
  <p>当サイトからリンクしている外部サイトの内容について、運営者は責任を負いません。</p>
  <h2>著作権</h2>
  <p>当サイトに掲載している文章の著作権は運営者に帰属します。無断での転載はご遠慮ください。</p>
  <h2>お問い合わせ</h2>
  <p>{contact_html()}</p>
  <h2>改定</h2>
  <p>このページの内容は、必要に応じて予告なく変更することがあります。</p>
  <p class="muted">制定日: {escape(config.get("established", ""))} / 最終更新日: {TODAY}</p>
</main>
"""
    page("privacy.html", f"プライバシーポリシー・免責事項｜{SITE}", f"{SITE}のプライバシーポリシーと免責事項です。", body, "")


def build_404():
    body = """
<main class="prose">
  <h1>ページが見つかりません</h1>
  <p>お探しのページは、移動したか削除された可能性があります。</p>
  <p><a href="index.html">ホームに戻る</a> / <a href="terms/index.html">用語一覧を見る</a></p>
</main>
"""
    page("404.html", f"ページが見つかりません｜{SITE}", "お探しのページは見つかりませんでした。", body, "", index=False)


def build_meta_files():
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "".join(f"  <url><loc>{escape(u)}</loc><lastmod>{TODAY}</lastmod></url>\n" for u in SITEMAP)
    sitemap += "</urlset>\n"
    (OUT / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    ad = config.get("adsense_client", "")
    if ad:
        pub = ad.replace("ca-", "")
        (OUT / "ads.txt").write_text(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    # 独自ドメインのときは GitHub Pages 用の CNAME を書く（docs/ を作り直しても設定が消えないように）
    host = urlparse(BASE).hostname or ""
    if host and not host.endswith("github.io"):
        (OUT / "CNAME").write_text(host + "\n", encoding="utf-8")
    data = [{"id": t["id"], "f": t["field"], "sub": t["sub"], "term": t["term"], "desc": t["desc"], **({"k": t["kind"]} if t.get("kind") else {})}
            for t in terms]
    (OUT / "assets" / "terms.js").write_text("window.SITE_TERMS = " + json.dumps(data, ensure_ascii=False) + ";\n"
                                             + "window.SITE_FIELDS = " + json.dumps(FIELDS, ensure_ascii=False) + ";\n"
                                             + "window.SITE_TEST = " + json.dumps(TEST_COUNTS) + ";\n", encoding="utf-8")


def check():
    """データと設定の問題を探す。致命的なものがあれば中断する。"""
    errors, warnings = [], []
    ids = [t["id"] for t in terms]
    names = [t["term"] for t in terms]
    for x in set(ids):
        if ids.count(x) > 1:
            errors.append(f"id が重複しています: {x}")
    for x in set(names):
        if names.count(x) > 1:
            errors.append(f"用語が重複しています: {x}")
    for t in terms:
        if t["field"] not in FIELDS:
            errors.append(f"{t['id']} の field が不正です: {t['field']}")
        if not re.fullmatch(r"\d{4}", t["id"]):
            errors.append(f"id は4桁の数字にしてください: {t['id']}")
    for k, n in TEST_COUNTS.items():
        if sum(t["field"] == k for t in terms) < max(n, 4):
            errors.append(f"{FIELDS[k]}の用語が少なすぎて、ミニテストを作れません")
    for t in KAMOKU:
        if t["kind"] not in KINDS:
            errors.append(f"{t['id']} の kind が不正です: {t['kind']}")
    if len(KAMOKU) < 10:
        errors.append("勘定の分類（kind）のある用語が10語より少ないので、分類クイズを作れません")
    if "YOUR-NAME" in BASE:
        warnings.append("config.json の base_url が仮の値のままです（公開するURLに変えてください）")
    if not config.get("operator"):
        warnings.append("config.json の operator（運営者名）が空です")
    if not config.get("contact"):
        warnings.append("config.json の contact（お問い合わせ先）が空です。AdSense の審査ではほぼ必須です")
    if not config.get("google_analytics_id"):
        warnings.append("config.json の google_analytics_id が空です（アクセス解析を使うなら GA4 の測定ID を入れてください）")
    return errors, warnings


def main():
    errors, warnings = check()
    for e in errors:
        print("エラー:", e)
    if errors:
        sys.exit(1)
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)
    build_home()
    build_index()
    for i, t in enumerate(terms):
        build_term(t, terms[i - 1] if i > 0 else None, terms[i + 1] if i + 1 < len(terms) else None)
    build_test()
    build_kamoku()
    build_about()
    build_privacy()
    build_404()
    build_meta_files()
    n = sum(1 for _ in OUT.rglob("*.html"))
    print(f"docs/ に {n} ページを書き出しました（用語 {len(terms)} 語、うち勘定科目 {len(KAMOKU)} 語）")
    for w in warnings:
        print("注意:", w)


if __name__ == "__main__":
    main()
