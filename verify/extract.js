/* Captures every number the website displays, page by page, and posts it to
   verify/collect_server.py (saved in verify/out). Run inside the site page:
     const s = document.createElement('script'); s.src = '/verify/extract.js'; document.body.appendChild(s);
   Progress: window.__vx.progress. It finishes by saving out/_done.json. */
(async () => {
  const W = window.__vx = { progress: 'starting', saved: 0, errors: [] };
  window.addEventListener('error', e => W.errors.push(String(e.message)));
  const oe = console.error; console.error = (...a) => { W.errors.push(a.map(String).join(' ').slice(0, 300)); oe.apply(console, a); };
  // turn off the count-up animation so numbers are final when read
  const mm = window.matchMedia.bind(window);
  window.matchMedia = q => /reduced-motion/.test(q) ? { matches: true, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} } : mm(q);

  const D = window.PISTOLS_DATA;
  const tick = ms => new Promise(r => setTimeout(r, ms));
  const rid = s => String(s).replace(/[^A-Za-z0-9-]/g, '-');
  const T = el => el ? el.textContent.replace(/\s+/g, ' ').trim() : null;
  const H2 = el => { const p = el && el.closest('.panel'); return p ? T(p.querySelector('h2')) : null; };
  const app = document.getElementById('app');
  const fire = el => el.dispatchEvent(new Event('change', { bubbles: true }));

  async function go(h) {
    if (location.hash === '#' + h) window.dispatchEvent(new HashChangeEvent('hashchange'));
    else location.hash = h;
    await tick(45);
  }
  function charts() {
    return [...app.querySelectorAll('canvas')].map(c => {
      const ch = window.Chart && Chart.getChart(c);
      return ch ? { id: c.id, labels: ch.data.labels || null, sets: ch.data.datasets.map(d => ({ label: d.label, data: d.data })) } : { id: c.id, missing: true };
    });
  }
  function snap(extra) {
    const s = { hash: location.hash, filters: JSON.parse(localStorage.getItem('pistols.filters') || 'null') };
    s.hero = [...app.querySelectorAll('.rec-n')].map(n => [T(n.querySelector('span')), T(n.querySelector('b'))]);
    s.heroNote = T(app.querySelector('.hero-note'));
    s.heroSub = T(app.querySelector('.hero-sub'));
    s.headSub = T(app.querySelector('.view-head .sub'));
    s.headTitle = T(app.querySelector('.view-head h1'));
    s.raw = T(app.querySelector('.phead .raw'));
    s.chips = [...app.querySelectorAll('.phead .chip')].map(T);
    s.kpis = [...app.querySelectorAll('.kpi')].map(k => ({ l: T(k.querySelector('.l')), v: T(k.querySelector('.v')), s: T(k.querySelector('.s')) }));
    s.facts = [...app.querySelectorAll('.fact')].map(f => ({ panel: H2(f), l: T(f.querySelector('.l')), v: T(f.querySelector('.v')), s: T(f.querySelector('.s')), links: [...f.querySelectorAll('a')].map(a => a.getAttribute('href')) }));
    s.tables = [...app.querySelectorAll('table.tbl')].map(t => ({
      id: t.id || null, panel: H2(t),
      head: [...t.tHead.rows[0].cells].map(c => T(c).replace(/[▾▴]/g, '').trim()),
      rows: [...t.tBodies[0].rows].map(r => ({ href: r.dataset.href || null, cells: [...r.cells].map(T), links: [...r.querySelectorAll('a')].map(a => a.getAttribute('href')), mvp: !!r.querySelector('.mvp'), empty: !!r.querySelector('.empty-row') })),
      foot: t.tFoot ? [...t.tFoot.rows].map(r => [...r.cells].map(T)) : []
    }));
    s.leads = [...app.querySelectorAll('ol.lead')].map(o => ({ panel: H2(o), items: [...o.children].map(li => { const a = li.querySelector('.n a'); return { name: T(a), href: a ? a.getAttribute('href') : null, x: T(li.querySelector('.x')), xlinks: [...li.querySelectorAll('.x a')].map(x => x.getAttribute('href')), v: T(li.querySelector('.v')) }; }) }));
    s.leadEmpty = [...app.querySelectorAll('.panel')].filter(p => !p.querySelector('ol.lead') && /Not enough games|None in the games shown|No teammates/.test(p.textContent)).map(p => T(p.querySelector('h2')));
    s.charts = charts();
    s.vs = [...app.querySelectorAll('.vs')].map(v => ({ panel: H2(v), head: [...v.querySelectorAll('.vs-head span')].map(T), rows: [...v.querySelectorAll('.vs-row')].map(r => [T(r.querySelector('.vs-lbl')), T(r.querySelector('.vs-side.l .vs-v')), T(r.querySelector('.vs-side.r .vs-v'))]) }));
    const sb = app.querySelector('.scoreboard');
    if (sb) s.scoreboard = { meta: T(sb.querySelector('.sb-meta')), us: T(sb.querySelector('.sb-team.us .sb-pts')), them: T(sb.querySelector('.sb-team.them .sb-pts')), oppName: T(sb.querySelector('.sb-team.them .sb-name')), res: T(sb.querySelector('.sb-mid')), qt: [...sb.querySelectorAll('.qt tr')].map(r => [...r.cells].map(T)) };
    s.notes = [...app.querySelectorAll('.note')].map(T);
    s.cards = [...app.querySelectorAll('.pcard')].map(c => ({ href: c.getAttribute('href'), name: T(c.querySelector('.pcard-n')), sub: T(c.querySelector('.pcard-s')), stats: [...c.querySelectorAll('.pcard-stats b')].map(T), cap: T(c.querySelector('.spark-cap')) }));
    s.legend = [...app.querySelectorAll('.legend span')].map(T);
    s.panelSubs = [...app.querySelectorAll('.panel')].map(p => [T(p.querySelector('h2')), T(p.querySelector('.panel-h .sub'))]);
    s.text = T(app).slice(0, 300);
    s.empty = !!app.querySelector('.panel.empty');
    return Object.assign(s, extra || {});
  }
  async function save(name, data) {
    await fetch('/save?name=' + encodeURIComponent(name), { method: 'POST', body: JSON.stringify(data) });
    W.saved++;
  }
  const FL = document.getElementById('filters');
  async function setF(o) {
    document.getElementById('f-reset').click(); await tick(40);
    for (const s of (o.seasons || [])) { const i = FL.querySelector(`input[name=season][value="${s}"]`); i.checked = true; fire(i); await tick(30); }
    for (const c of (o.comps || [])) { const i = FL.querySelector(`input[name=comp][value="${c}"]`); i.checked = true; fire(i); await tick(30); }
    if (o.opp) { const s = document.getElementById('f-opp'); s.value = o.opp; fire(s); await tick(30); }
    if (o.venue) { FL.querySelector(`[data-venue="${o.venue}"]`).click(); await tick(30); }
    if (o.result) { FL.querySelector(`[data-result="${o.result}"]`).click(); await tick(30); }
    if (o.ff === false) { const c = document.getElementById('f-ff'); c.checked = false; fire(c); await tick(30); }
    // make sure the stored filter state is written even when nothing changed
    const c = document.getElementById('f-ff'); c.checked = !c.checked; fire(c); await tick(20); c.checked = !c.checked; fire(c); await tick(30);
  }
  async function sel(id, v) { const s = document.getElementById(id); if (!s) return false; s.value = v; fire(s); await tick(40); return true; }
  async function clickUI(key, v) { const b = document.querySelector(`[data-ui="${key}"][data-v="${v}"]`); if (b) { b.click(); await tick(40); } return !!b; }
  async function setMin(v) { const i = document.getElementById('ui-pmin'); if (!i) return; i.value = v; fire(i); await tick(40); }

  const ours = D.players.filter(l => l.is_our_team);
  const players = [...new Set(ours.map(l => l.player_id))];
  const byGames = players.slice().sort((a, b) => ours.filter(l => l.player_id === b).length - ours.filter(l => l.player_id === a).length);
  const opps = [...new Set(D.games.filter(g => g.result === 'W' || g.result === 'L').map(g => g.opponent_id))];
  const seasons = [...new Set(D.games.map(g => g.season))];
  const REC = ['pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'eff', 'gs'];
  const CAR = ['gp', 'pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'mvp', 'dd', 'eff', 'min'];
  const SB = ['ppg', 'rpg', 'apg', 'spg', 'effpg', 'ts'];
  const SEAM = ['reb', 'ast', 'stl', 'blk', 'eff', 'gsum', 'min', 'fg3m'];

  async function sections(sc) {
    for (const h of ['overview', 'games', 'opponents', 'seasons', 'team']) { W.progress = `${sc} ${h}`; await go(h); await save(`${sc}__${h}`, snap()); }
    await go('players'); await setMin('0');
    for (const m of ['pg', 'tot', 'p40', 'shoot', 'adv']) { await clickUI('pmode', m); await save(`${sc}__players__${m}`, snap({ mode: m, pmin: 0 })); }
    await setMin(''); await clickUI('pmode', 'pg'); await save(`${sc}__players__auto`, snap({ mode: 'pg', pmin: 'auto' }));
    await go('records');
    for (const k of REC) { await clickUI('rec', k); await save(`${sc}__records__rec_${k}`, snap({ rec: k })); }
    for (const k of CAR) { await sel('ui-car', k); await save(`${sc}__records__car_${k}`, snap({ car: k })); }
    for (const k of SB) { await sel('ui-sb', k); await save(`${sc}__records__sb_${k}`, snap({ sb: k })); }
    await clickUI('rec', 'pts'); await sel('ui-car', 'pts'); await sel('ui-sb', 'ppg');
    await go('compare');
    const cur = () => [0, 1, 2].map(i => { const s = document.getElementById('cmp-' + i); return s ? s.value : ''; }).filter(Boolean);
    if (document.getElementById('cmp-0')) {
      await save(`${sc}__compare__default`, snap({ cmpSel: cur() }));
      const avail = [...document.getElementById('cmp-0').options].map(o => o.value);
      const combos = [avail.slice(0, 3), [avail[avail.length - 1], avail[0]], [avail[1], avail[Math.floor(avail.length / 2)], avail[2]]];
      let ci = 0;
      for (const c of combos) {
        if (c.some(x => !x) || new Set(c).size !== c.length) continue;
        await sel('cmp-0', c[0]); await sel('cmp-1', c[1]); await sel('cmp-2', c[2] || '');
        await save(`${sc}__compare__${ci++}`, snap({ cmpSel: cur() }));
      }
    } else await save(`${sc}__compare__empty`, snap({ cmpSel: [] }));
  }
  async function playerPage(sc, p, metrics) {
    await go('player-' + rid(p));
    await save(`${sc}__player__${rid(p)}`, snap({ pid: p }));
    if (metrics) {
      for (const m of SEAM) { if (await sel('ui-seaM', m)) await save(`${sc}__psea__${rid(p)}__${m}`, { hash: location.hash, pid: p, metric: m, filters: JSON.parse(localStorage.getItem('pistols.filters') || 'null'), charts: charts() }); }
      await sel('ui-seaM', 'pts');
    }
  }

  try {
    // Scenario A: no filters (everything)
    await setF({});
    await sections('A');
    for (const p of players) { W.progress = `A player ${p}`; await playerPage('A', p, true); }
    for (const o of opps) { W.progress = `A opponent ${o}`; await go('opponent-' + rid(o)); await save(`A__opponent__${rid(o)}`, snap({ okey: o })); }
    for (const s of seasons) { await go('season-' + s.replace(/\D/g, '')); await save(`A__season__${s.replace(/\D/g, '')}`, snap({ season: s })); }
    for (const g of D.games) { W.progress = `A game ${g.game_id}`; await go('game-' + rid(g.game_id)); await save(`A__game__${rid(g.game_id)}`, snap({ gid: g.game_id })); }

    // Scenario B: one season, away games only
    await setF({ seasons: ['24/25'], venue: 'Away' });
    await sections('B');
    for (const p of byGames.slice(0, 6)) await playerPage('B', p, false);
    for (const o of ['cosa-nostra', 'phoenix-bums', 'reboot', 'the-jokers']) { await go('opponent-' + rid(o)); await save(`B__opponent__${rid(o)}`, snap({ okey: o })); }
    for (const s of ['24/25', '23/24']) { await go('season-' + s.replace(/\D/g, '')); await save(`B__season__${s.replace(/\D/g, '')}`, snap({ season: s })); }

    // Scenario C: forfeits left out of the record, cups only
    await setF({ ff: false });
    await sections('C');
    for (const p of byGames.slice(0, 3)) await playerPage('C', p, false);
    for (const o of ['smokin-aces', 'aguanile', 'golden-steak-warriors']) { await go('opponent-' + rid(o)); await save(`C__opponent__${rid(o)}`, snap({ okey: o })); }
    await go('season-1920'); await save('C__season__1920', snap({ season: '19/20' }));

    // Scenario D: cup games, losses only
    await setF({ comps: ['Athens Superbet Cup'], result: 'L' });
    await sections('D');
    await playerPage('D', byGames[0], false);

    await setF({});
    await go('overview');
    W.progress = 'done';
    await save('_done', { saved: W.saved, errors: W.errors });
  } catch (e) {
    W.progress = 'failed: ' + e.message;
    await save('_done', { saved: W.saved, errors: W.errors.concat(['EXTRACTOR: ' + e.stack]) });
  }
})();
