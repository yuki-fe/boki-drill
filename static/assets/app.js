/* 簿記用語ドリル: ホームの学習機能。用語データは terms.js（build.py が生成）の window.SITE_TERMS */
(function () {
  const FIELD = window.SITE_FIELDS;
  const TERMS = window.SITE_TERMS.map((t, i) => ({ ...t, n: i }));
  const KANA = ["ア", "イ", "ウ", "エ"];
  const MODES = [
    { id: "card", name: "カード", cap: "めくって覚える", title: "カード", sub: "タップで裏返し、覚えたかどうかを仕分けます" },
    { id: "quiz", name: "4択", cap: "ア〜エから選ぶ", title: "4択クイズ", sub: "10問ずつ。覚えていない用語から出ます" },
    { id: "type", name: "書いて答える", short: "書く", cap: "意味から用語を入力", title: "書いて答える", sub: "説明を読んで用語を入力します。カタカナの用語はひらがなでも、かっこの中の別名でも答えられます" },
    { id: "review", name: "今日の復習", short: "復習", cap: "復習の日が来た用語", title: "今日の復習", sub: "間違えた用語と、復習の日が来た用語が出ます。正解を重ねると、次の復習が1日後・2日後・約4日後・約7日後・約14日後と延びます" },
    { id: "list", name: "一覧", cap: "検索・チェック", title: "用語一覧", sub: "検索して、覚えた用語に印を付けられます" }
  ];
  const KINDS = [["card", "カード"], ["quiz", "4択"], ["type", "書いて答える"]];

  /* ---------- 保存 ---------- */
  function load(k, d) { try { const v = JSON.parse(localStorage.getItem(k)); return v && typeof v === "object" ? v : d; } catch (e) { return d; } }
  function store(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  let known = load("boki-drill-v1", {});
  let weak = load("boki-drill-weak", {});
  /* 日付での復習: 用語 → { s: 続けて正解した回数, d: 次に復習する日（YYYY-MM-DD） } */
  let srs = load("boki-drill-srs", {});
  const INTERVALS = [1, 2, 4, 7, 14];   // 続けて正解した回数ごとの、次の復習までの日数
  const prefs = Object.assign({ mode: "card", field: "all", cardDir: "d2t", quizDir: "d2t", reviewKind: "card" }, load("boki-drill-prefs", {}));
  const hashMode = location.hash.slice(1);
  if (MODES.some((m) => m.id === hashMode)) prefs.mode = hashMode;
  if (!MODES.some((m) => m.id === prefs.mode)) prefs.mode = "card";
  if (prefs.field !== "all" && !FIELD[prefs.field]) prefs.field = "all";
  if (!KINDS.some(([k]) => k === prefs.reviewKind)) prefs.reviewKind = "card";
  const savePrefs = () => store("boki-drill-prefs", prefs);
  const isKnown = (t) => !!known[t.term];
  const isWeak = (t) => !!weak[t.term];
  function saveProgress() { store("boki-drill-v1", known); store("boki-drill-weak", weak); store("boki-drill-srs", srs); renderFields(); updateWeakCount(); renderRevPlan(); }
  /* 学習での答え: 正解・覚えた → 次の復習の日を先へ、間違い・まだ → 今日の復習に */
  function record(t, ok) {
    schedule(t, ok);
    if (ok) { known[t.term] = 1; delete weak[t.term]; } else { delete known[t.term]; weak[t.term] = 1; }
    saveProgress();
  }
  /* 一覧での印の付け外し: 印を付けた用語は明日の復習に入れ、外したら予定も消す */
  function setKnown(t, v) {
    if (v) {
      known[t.term] = 1; delete weak[t.term];
      if (!srs[t.term] || !srs[t.term].s) srs[t.term] = { s: 1, d: addDays(INTERVALS[0]) };
    } else {
      delete known[t.term];
      if (!isWeak(t)) delete srs[t.term];
    }
    saveProgress();
  }

  /* ---------- 日付での復習 ---------- */
  const dayKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const todayKey = () => dayKey(new Date());
  function addDays(n) { const d = new Date(); d.setDate(d.getDate() + n); return dayKey(d); }
  const shortDay = (k) => `${+k.slice(5, 7)}/${+k.slice(8, 10)}`;
  const isDue = (t) => isWeak(t) || (!!srs[t.term] && srs[t.term].d <= todayKey());
  /* 正解は復習の日が来ているときだけ間隔を進める（同じ日に何度も正解しても先へ延びすぎない） */
  function schedule(t, ok) {
    const today = todayKey(), e = srs[t.term];
    if (!ok) { srs[t.term] = { s: 0, d: today }; return; }
    if (e && e.d > today && !isWeak(t)) return;
    const s = (e ? e.s : 0) + 1;
    const base = INTERVALS[Math.min(s, INTERVALS.length) - 1];
    /* 4日以上は前後1日ずらす（同じ日に復習が固まらないように） */
    const days = base >= 4 ? base + Math.floor(Math.random() * 3) - 1 : base;
    srs[t.term] = { s, d: addDays(days) };
  }
  /* はじめて開いたとき: 間違えた用語は今日に、覚えた用語は一度に出ないよう次の7日に分ける */
  (function seedSrs() {
    Object.keys(srs).forEach((k) => { const e = srs[k]; if (!e || !/^\d{4}-\d{2}-\d{2}$/.test(e.d) || !(e.s >= 0)) delete srs[k]; });
    let n = 0;
    TERMS.forEach((t) => {
      if (srs[t.term]) return;
      if (isWeak(t)) srs[t.term] = { s: 0, d: todayKey() };
      else if (isKnown(t)) srs[t.term] = { s: 1, d: addDays((n++ % 7) + 1) };
    });
    store("boki-drill-srs", srs);
  })();
  function nextReview(t) {
    const e = srs[t.term];
    if (!e) return "";
    const today = todayKey();
    const text = e.d <= today ? "今日の復習に入りました" : `次の復習: ${e.d === addDays(1) ? "明日" : shortDay(e.d)}`;
    return `<p class="next-review">${text}</p>`;
  }
  /* 今日の復習の数と、これからの7日の予定（過ぎた分は今日に数える） */
  function renderRevPlan() {
    const el = $("#revPlan");
    if (!el) return;
    if (!Object.keys(srs).length) { el.innerHTML = ""; el.hidden = true; return; }
    const week = [];
    for (let i = 0; i < 7; i++) { const k = addDays(i); week.push({ k, n: TERMS.filter((x) => { const e = srs[x.term]; return e && (i === 0 ? isDue(x) : e.d === k && !isWeak(x)); }).length }); }
    el.hidden = false;
    el.innerHTML = `
      <button class="rev-now" type="button" id="goReview"><span>今日の復習</span><span><b class="mono">${week[0].n}</b> 語</span></button>
      <ol class="rev-week" aria-label="これから7日の復習の数">${week.map((w, i) =>
        `<li class="${w.n ? "on" : ""}"><small>${i ? shortDay(w.k) : "今日"}</small><b class="mono">${w.n}</b></li>`).join("")}</ol>`;
    $("#goReview").onclick = () => { mode = "review"; refresh(); $("#study").scrollIntoView(); };
  }

  /* ---------- 文字列 ---------- */
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const link = (t) => `terms/${t.id}.html`;
  function shuffle(a) { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
  function aliases(term) {
    const out = new Set([term]);
    const m = term.match(/^(.*?)[（(](.*?)[)）](.*)$/);
    if (m) { out.add((m[1] + m[3]).trim()); m[2].split(/[、,]/).forEach((s) => out.add(s.trim())); }
    [...out].forEach((a) => a.split(/\s*\/\s*/).forEach((s) => out.add(s.trim())));
    return [...out].filter(Boolean);
  }
  function primary(term) {
    const m = term.match(/^(.*?)[（(].*?[)）](.*)$/);
    return (m ? m[1] + m[2] : term).split(/\s*\/\s*/)[0].trim();
  }
  const norm = (s) => s.normalize("NFKC").toLowerCase()
    .replace(/[ぁ-ゖ]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 0x60))
    .replace(/[\s・･\-‐_/／]/g, "");
  /* 「AとB」の形の用語は、AとBも隠す（「の」を含む用語は分けない） */
  function maskWords(term) {
    const out = new Set(aliases(term));
    [...out].forEach((a) => { if (!a.includes("の") && a.includes("と")) a.split(/\s*と\s*/).forEach((p) => { if (p.trim() !== "AI") out.add(p.trim()); }); });
    return [...out].filter((a) => a.length >= 2);
  }
  function masked(t) {
    let d = t.desc;
    maskWords(t.term).sort((a, b) => b.length - a.length).forEach((a) => { d = d.split(a).join("〇〇"); });
    return d;
  }

  let field = prefs.field, mode = prefs.mode, query = "";
  let deck = [], idx = 0, flipped = false, quiz = null, typing = null;
  const reviewing = () => mode === "review";
  const kind = () => reviewing() ? prefs.reviewKind : mode;
  const basePool = () => field === "all" ? TERMS : TERMS.filter((t) => t.f === field);
  const pool = () => reviewing() ? basePool().filter(isDue) : basePool();
  /* 今日の復習は、間違えた用語 → 復習の日が古い用語の順 */
  const reviewOrder = (p) => shuffle(p).sort((a, b) => (isWeak(b) - isWeak(a)) || (srs[a.term] && srs[b.term] ? srs[a.term].d.localeCompare(srs[b.term].d) : 0));
  const studyOrder = (p) => reviewing() ? reviewOrder(p) : [...shuffle(p.filter((t) => !isKnown(t))), ...shuffle(p.filter(isKnown))];

  /* ---------- サイドバー ---------- */
  function renderModes() {
    $("#modes").innerHTML = MODES.map((m) => `
      <button class="mode" type="button" role="tab" data-mode="${m.id}" aria-selected="${m.id === mode}">
        <span class="bub" aria-hidden="true"></span><b><span class="nm${m.short ? " has-short" : ""}">${m.name}</span>${m.short ? `<span class="nm-short">${m.short}</span>` : ""}${m.id === "review" ? `<span class="count" id="weakCount"></span>` : ""}</b><small>${m.cap}</small>
      </button>`).join("");
    updateWeakCount();
  }
  function updateWeakCount() {
    const el = $("#weakCount");
    if (!el) return;
    const n = basePool().filter(isDue).length;
    el.textContent = n ? String(n) : "";
    el.setAttribute("aria-label", `今日復習する用語 ${n}語`);
  }
  function renderFields() {
    const rows = [["all", "すべて", TERMS], ...Object.entries(FIELD).map(([k, v]) => [k, v, TERMS.filter((t) => t.f === k)])];
    $("#fields").innerHTML = rows.map(([k, v, list]) => {
      const n = list.filter(isKnown).length;
      return `<button class="frow" type="button" data-f="${k}" aria-pressed="${field === k}">
        <span class="top"><span>${v}</span><span class="mono">${n}/${list.length}</span></span>
        <span class="bar"><i style="width:${(n / list.length) * 100}%"></i></span>
      </button>`;
    }).join("");
  }
  function renderToolbar() {
    const m = MODES.find((x) => x.id === mode);
    let seg = "";
    if (reviewing()) {
      seg = `<div class="seg" role="group" aria-label="復習のしかた">${KINDS.map(([k, label]) =>
        `<button type="button" data-kind="${k}" aria-pressed="${prefs.reviewKind === k}">${label}</button>`).join("")}</div>`;
    } else if (mode === "card" || mode === "quiz") {
      const key = mode === "card" ? "cardDir" : "quizDir";
      seg = `<div class="seg" role="group" aria-label="出題の向き">
        <button type="button" data-dir="d2t" data-key="${key}" aria-pressed="${prefs[key] === "d2t"}">意味 → 用語</button>
        <button type="button" data-dir="t2d" data-key="${key}" aria-pressed="${prefs[key] === "t2d"}">用語 → 意味</button>
      </div>`;
    }
    $("#toolbar").innerHTML = `<h2>${m.title}<small>${m.sub}</small></h2>${seg}`;
  }

  function renderRoundEnd(head, big, unit, extra, btn, fn) {
    $("#panel").innerHTML = `<div class="result"><div>${head}</div><div class="score">${big}<span> ${unit}</span></div>${extra}<button class="btn primary" type="button" id="again2">${btn}</button></div>`;
    $("#again2").onclick = fn; $("#again2").focus({ preventScroll: true });
  }
  function missList(miss) {
    return miss.length ? `<ul class="misses">${miss.map((t) => `<li><a href="${link(t)}">${esc(t.term)}</a>: ${esc(t.desc)}</li>`).join("")}</ul>` : `<div>全問正解です</div>`;
  }
  /* 復習モードで1回分を終えたときの「続ける」ボタン */
  function reviewNext(fallbackLabel, fallback) {
    if (!reviewing()) return [fallbackLabel, fallback];
    const n = pool().length;
    return n ? [`続けて復習する（残り${n}語）`, start] : ["復習を終える", start];
  }
  function renderReviewEmpty() {
    const scope = field === "all" ? "" : `${FIELD[field]}の`;
    const later = basePool().map((t) => srs[t.term] && srs[t.term].d).filter(Boolean).sort();
    const nextDay = later[0], nextN = later.filter((d) => d === nextDay).length;
    $("#panel").innerHTML = `
      <div class="result">
        <div class="score" style="font-size:1.35rem;line-height:1.4">${nextDay ? `今日の${scope}復習は終わりました` : `復習する${scope}用語はありません`}</div>
        <p style="margin:0">${nextDay ? `次の復習は <b>${nextDay === addDays(1) ? "明日" : shortDay(nextDay)}</b>（${nextN}語）です。` : "カードで「まだ」を押した用語や、4択・書いて答えるで答えた用語が、復習の日にここに出ます。"}</p>
        <div class="cta-row" style="justify-content:center">
          <button class="btn primary" type="button" data-go="quiz">4択クイズをする</button>
          <button class="btn" type="button" data-go="card">カードで覚える</button>
        </div>
      </div>`;
    document.querySelectorAll("[data-go]").forEach((b) => b.onclick = () => { mode = b.dataset.go; refresh(); });
  }

  /* ---------- カード ---------- */
  function newDeck() { deck = studyOrder(pool()); idx = 0; flipped = false; }
  function renderCard() {
    const t = deck[idx];
    if (!t) { $("#panel").innerHTML = `<div class="empty">用語がありません</div>`; return; }
    const left = reviewing() ? `今日の復習 残り <span class="mono">${pool().length}</span>` : `まだ覚えていない用語 <span class="mono">${pool().filter((x) => !isKnown(x)).length}</span>`;
    const rev = prefs.cardDir === "d2t";
    const full = t.abbr ? `<div class="hint" lang="en">${esc(t.abbr)}</div>` : "";
    let body;
    if (!rev) body = `<div class="term">${esc(t.term)}</div>` + (flipped ? `${full}<div class="desc">${esc(t.desc)}</div>` : `<div class="hint">タップして意味を見る</div>`);
    else body = flipped ? `<div class="term">${esc(t.term)}</div>${full}<div class="desc">${esc(t.desc)}</div>`
                        : `<div class="desc big">${esc(masked(t))}</div><div class="hint">用語を思い浮かべてからタップ</div>`;
    $("#panel").innerHTML = `
      <div class="meta"><span class="mono">${idx + 1} / ${deck.length}</span><span>${left}</span></div>
      <div class="card" id="flashcard" tabindex="0" role="button" aria-label="カードを裏返す">
        ${isKnown(t) ? `<span class="known-badge">覚えた</span>` : ""}
        <span class="tag">${FIELD[t.f]}・${esc(t.sub)}</span>${body}
      </div>
      <div class="actions"><button class="btn again" type="button" id="again">まだ</button><button class="btn ok" type="button" id="ok">覚えた</button></div>
      <div class="kbd">Space で裏返す / ← まだ / → 覚えた</div>`;
    $("#flashcard").onclick = flip;
    $("#again").onclick = () => answerCard(false);
    $("#ok").onclick = () => answerCard(true);
  }
  function flip() { flipped = !flipped; renderCard(); $("#flashcard").focus({ preventScroll: true }); }
  function answerCard(ok) {
    record(deck[idx], ok); idx++; flipped = false;
    if (idx < deck.length) return renderCard();
    if (reviewing()) {
      const n = pool().length;
      return renderRoundEnd("1周しました", n, "語が今日の復習に残っています", "", ...reviewNext());
    }
    renderRoundEnd("1周しました", pool().filter(isKnown).length, `/ ${pool().length} 覚えた`, "", "もう1周する", () => { newDeck(); renderCard(); });
  }

  /* ---------- 4択 ---------- */
  function newQuiz() {
    const p = pool(), all = basePool(), src = all.length >= 4 ? all : TERMS;
    quiz = { qs: studyOrder(p).slice(0, 10).map((t) => {
      const same = shuffle(src.filter((x) => x.id !== t.id && x.sub === t.sub));
      const rest = shuffle(src.filter((x) => x.id !== t.id && x.sub !== t.sub));
      return { t, choices: shuffle([t, ...[...same, ...rest].slice(0, 3)]), picked: null };
    }), i: 0, score: 0, dir: prefs.quizDir };
  }
  function renderQuiz() {
    const q = quiz.qs[quiz.i];
    if (!q) {
      const miss = quiz.qs.filter((x) => x.choices[x.picked].id !== x.t.id).map((x) => x.t);
      return renderRoundEnd("結果", quiz.score, `/ ${quiz.qs.length} 問正解`, missList(miss), ...reviewNext("次の10問", () => { newQuiz(); renderQuiz(); }));
    }
    const d2t = quiz.dir === "d2t", done = q.picked !== null;
    const stem = d2t ? `<p>${esc(masked(q.t))}</p>` : `<div class="qterm">${esc(q.t.term)}</div>`;
    const label = (c) => d2t ? esc(c.term) : esc(c.id === q.t.id ? masked(c) : c.desc);
    let explain = "";
    if (done && q.choices[q.picked].id !== q.t.id) {
      const c = q.choices[q.picked];
      explain = d2t ? `<div class="explain"><b>${esc(c.term)}</b>: ${esc(c.desc)}</div>` : `<div class="explain">選んだ説明は「<b>${esc(c.term)}</b>」の説明です。</div>`;
    }
    $("#panel").innerHTML = `
      <div class="meta"><span class="mono">問${quiz.i + 1} / ${quiz.qs.length}</span><span>正解 <span class="mono">${quiz.score}</span></span></div>
      <div class="question"><div class="q">${FIELD[q.t.f]}・${esc(q.t.sub)}</div>${stem}</div>
      <div class="choices">${q.choices.map((c, k) => {
        const cls = done && c.id === q.t.id ? "correct" : done && k === q.picked ? "wrong" : "";
        return `<button class="choice ${cls}" type="button" data-k="${k}" ${done ? "disabled" : ""}><span class="oval">${KANA[k]}</span><span>${label(c)}</span></button>`;
      }).join("")}</div>
      ${done ? `${explain}${nextReview(q.t)}<button class="btn primary" type="button" id="next">${quiz.i + 1 < quiz.qs.length ? "次の問題" : "結果を見る"}</button>` : ""}
      <div class="kbd">1〜4 で解答 / Enter で次へ</div>`;
    document.querySelectorAll(".choice").forEach((b) => b.onclick = () => pick(+b.dataset.k));
    if (done) { $("#next").onclick = () => { quiz.i++; renderQuiz(); }; $("#next").focus({ preventScroll: true }); }
  }
  function pick(k) {
    const q = quiz.qs[quiz.i];
    if (q.picked !== null || !q.choices[k]) return;
    q.picked = k;
    const ok = q.choices[k].id === q.t.id;
    if (ok) quiz.score++;
    record(q.t, ok);
    renderQuiz();
  }

  /* ---------- 書いて答える ---------- */
  function newTyping() { typing = { qs: studyOrder(pool()).slice(0, 10).map((t) => ({ t, input: "", result: null, hint: false })), i: 0, score: 0 }; }
  function renderTyping() {
    const q = typing.qs[typing.i];
    if (!q) {
      const miss = typing.qs.filter((x) => x.result !== "ok").map((x) => x.t);
      return renderRoundEnd("結果", typing.score, `/ ${typing.qs.length} 問正解`, missList(miss), ...reviewNext("次の10問", () => { newTyping(); renderTyping(); }));
    }
    const chars = Array.from(primary(q.t.term));
    const hint = q.hint ? `<div class="hint" style="padding:0">ヒント: 「${esc(chars[0])}」から始まる${chars.length}文字</div>` : "";
    let foot;
    if (q.result === null) {
      foot = `
        <div class="answer-row">
          <input id="answer" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="用語を入力" aria-label="答え" value="${esc(q.input)}">
          <button class="btn primary" type="button" id="submit">答える</button>
        </div>
        <div class="sub-actions">
          <button class="btn ghost" type="button" id="hintBtn" ${q.hint ? "disabled" : ""}>ヒントを見る</button>
          <button class="btn ghost" type="button" id="skip">わからない</button>
        </div>
        <div class="kbd">Enter で答える</div>`;
    } else {
      const ok = q.result === "ok";
      foot = `
        <div class="verdict ${ok ? "ok" : "ng"}">
          <span class="v">${ok ? "正解" : q.result === "skip" ? "答え" : "不正解"}</span>
          <span class="t">${esc(q.t.term)}</span>
          ${q.result === "ng" ? `<span class="yours">あなたの答え: ${esc(q.input)}</span>` : ""}
          <a href="${link(q.t)}">この用語の解説ページを見る</a>
        </div>
        ${nextReview(q.t)}
        <button class="btn primary" type="button" id="next">${typing.i + 1 < typing.qs.length ? "次の問題" : "結果を見る"}</button>`;
    }
    $("#panel").innerHTML = `
      <div class="meta"><span class="mono">問${typing.i + 1} / ${typing.qs.length}</span><span>正解 <span class="mono">${typing.score}</span></span></div>
      <div class="question"><div class="q">${FIELD[q.t.f]}・${esc(q.t.sub)}</div><p>${esc(masked(q.t))}</p>${hint}</div>
      ${foot}`;
    if (q.result === null) {
      const inp = $("#answer");
      inp.oninput = () => { q.input = inp.value; };
      inp.onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); submitTyping(); } };
      $("#submit").onclick = submitTyping;
      $("#hintBtn").onclick = () => { q.hint = true; renderTyping(); };
      $("#skip").onclick = () => { q.result = "skip"; record(q.t, false); renderTyping(); };
      inp.focus({ preventScroll: true });
    } else {
      $("#next").onclick = () => { typing.i++; renderTyping(); };
      $("#next").focus({ preventScroll: true });
    }
  }
  function submitTyping() {
    const q = typing.qs[typing.i];
    const v = norm(q.input);
    if (!v) { $("#answer").focus(); return; }
    const ok = aliases(q.t.term).some((a) => norm(a) === v);
    q.result = ok ? "ok" : "ng";
    if (ok) typing.score++;
    record(q.t, ok);
    renderTyping();
  }

  /* ---------- 一覧 ---------- */
  function renderList() {
    $("#panel").innerHTML = `
      <input class="search" id="search" type="search" placeholder="用語や説明で検索（例: KPI、著作権）" value="${esc(query)}" aria-label="用語を検索">
      <div class="list" id="list"></div>`;
    $("#search").oninput = (e) => { query = e.target.value; renderRows(); };
    renderRows();
  }
  function renderRows() {
    const qq = norm(query);
    const rows = pool().filter((t) => !qq || norm(t.term + t.desc + t.sub).includes(qq));
    $("#list").innerHTML = rows.length ? rows.map((t) => `
      <div class="row">
        <button class="st" type="button" data-n="${t.n}" aria-pressed="${isKnown(t)}" aria-label="${esc(t.term)}を覚えたにする" title="覚えた"></button>
        <div><h3><a href="${link(t)}">${esc(t.term)}</a>${isDue(t) ? `<span class="weak-tag">今日の復習</span>` : srs[t.term] ? `<span class="next-tag">次 ${shortDay(srs[t.term].d)}</span>` : ""}<small>${FIELD[t.f]}・${esc(t.sub)}</small></h3><p>${esc(t.desc)}</p></div>
      </div>`).join("") : `<div class="empty">「${esc(query)}」に当てはまる用語はありません</div>`;
    document.querySelectorAll(".st").forEach((b) => b.onclick = () => {
      const t = TERMS[+b.dataset.n]; setKnown(t, !isKnown(t)); renderRows();
    });
  }

  /* ---------- 切り替え ---------- */
  function start() {
    if (reviewing() && !pool().length) return renderReviewEmpty();
    const k = kind();
    if (k === "card") { newDeck(); renderCard(); }
    else if (k === "quiz") { newQuiz(); renderQuiz(); }
    else if (k === "type") { newTyping(); renderTyping(); }
    else renderList();
  }
  function refresh() {
    prefs.mode = mode; prefs.field = field; savePrefs();
    try { history.replaceState(null, "", "#" + mode); } catch (e) {}
    renderModes(); renderFields(); renderToolbar(); start();
  }

  $("#modes").onclick = (e) => { const b = e.target.closest(".mode"); if (b) { mode = b.dataset.mode; refresh(); } };
  $("#fields").onclick = (e) => { const b = e.target.closest(".frow"); if (b) { field = b.dataset.f; refresh(); } };
  $("#toolbar").onclick = (e) => {
    const kb = e.target.closest("[data-kind]");
    if (kb) { prefs.reviewKind = kb.dataset.kind; savePrefs(); renderToolbar(); start(); return; }
    const b = e.target.closest("[data-dir]"); if (!b) return;
    prefs[b.dataset.key] = b.dataset.dir; savePrefs(); renderToolbar();
    if (mode === "card") { flipped = false; renderCard(); } else { newQuiz(); renderQuiz(); }
  };

  let resetArmed = false;
  $("#reset").onclick = () => {
    const btn = $("#reset");
    if (!resetArmed) { resetArmed = true; btn.textContent = "もう一度押すとリセットします"; setTimeout(() => { resetArmed = false; btn.textContent = "進み具合をリセット"; }, 3000); return; }
    known = {}; weak = {}; srs = {}; store("boki-drill-v1", known); store("boki-drill-weak", weak); store("boki-drill-srs", srs);
    resetArmed = false; btn.textContent = "進み具合をリセット"; renderRevPlan(); refresh();
  };

  document.addEventListener("keydown", (e) => {
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "A" || (tag === "BUTTON" && (e.key === "Enter" || e.key === " "))) return;
    const k = kind();
    if (k === "card" && deck[idx] && $("#flashcard")) {
      if (e.key === " ") { e.preventDefault(); flip(); }
      else if (e.key === "ArrowLeft") answerCard(false);
      else if (e.key === "ArrowRight") answerCard(true);
    } else if (k === "quiz" && quiz && quiz.qs[quiz.i] && $(".choices")) {
      const q = quiz.qs[quiz.i];
      if (["1", "2", "3", "4"].includes(e.key)) pick(+e.key - 1);
      else if (e.key === "Enter" && q.picked !== null) { quiz.i++; renderQuiz(); }
    }
  });

  renderRevPlan();
  refresh();
})();
