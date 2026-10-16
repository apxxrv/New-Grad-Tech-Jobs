(function () {
  var q = document.getElementById('q'), cycle = document.getElementById('cycle'),
      cat = document.getElementById('cat'), spon = document.getElementById('spon'),
      h1b = document.getElementById('h1b'), age = document.getElementById('age'),
      stated = document.getElementById('stated'),
      program = document.getElementById('program'),
      remote = document.getElementById('remote'),
      savedonly = { checked: false },
      savedn = document.getElementById('savedn'),
      empty = document.getElementById('empty'),
      rows = Array.prototype.slice.call(document.getElementById('rows').rows),
      count = document.getElementById('count');

  // --- saved roles -----------------------------------------------------------
  // Deliberately localStorage and nothing else: a tracker that needs an account
  // is a tracker most people bounce off, and we have no business holding anyone's
  // application list on a server. Everything here stays in this browser.
  var KEY = 'ie.saved.v1', saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { saved = {}; }
  if (typeof saved !== 'object' || Array.isArray(saved)) saved = {};
  // Remove ids no longer present in the current artifact. Otherwise the badge
  // counts invisible roles that cannot be viewed, exported, or unstarred.
  //
  // A row can stand for several requisitions (an employer that opened the same
  // job three times). Every one of those ids has to count as present, and a
  // star on a requisition that is now represented by a sibling has to MOVE to
  // the surviving row — otherwise folding the display would quietly delete
  // roles a reader had saved.
  var currentIds = {};
  rows.forEach(function (tr) {
    var ids = (tr.dataset.ids || tr.dataset.id).split('|');
    ids.forEach(function (id) { currentIds[id] = true; });
    if (ids.length > 1 && !saved[tr.dataset.id]) {
      for (var i = 0; i < ids.length; i++) {
        if (saved[ids[i]]) { saved[tr.dataset.id] = saved[ids[i]]; break; }
      }
    }
    ids.forEach(function (id) { if (id !== tr.dataset.id) delete saved[id]; });
  });
  Object.keys(saved).forEach(function (id) { if (!currentIds[id]) delete saved[id]; });
  function persist() {
    try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) { document.getElementById('storage-status').textContent = 'Your browser cannot store saved jobs. Export your shortlist before leaving this page.'; }
  }
  persist();
  function savedCount() { return Object.keys(saved).length; }
  function paintRow(tr) {
    var on = !!saved[tr.dataset.id], btn = tr.querySelector('.star');
    if (btn) {
      btn.querySelector('.save-label').textContent = on ? 'Saved' : 'Save';
      btn.setAttribute('aria-label', (on ? 'Unsave ' : 'Save ') + tr.dataset.title + ' at ' + tr.dataset.company);
      btn.classList.toggle('on', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    tr.classList.toggle('saved', on);
  }
  function paintAll() { rows.forEach(paintRow); savedn.textContent = savedCount(); }

  document.getElementById('rows').addEventListener('click', function (ev) {
    var btn = ev.target.closest ? ev.target.closest('.star') : null;
    if (!btn) return;
    var tr = btn.closest('tr'), id = tr.dataset.id;
    if (saved[id]) { delete saved[id]; } else { saved[id] = Date.now(); }
    persist(); paintRow(tr); savedn.textContent = savedCount();
    apply();
  });

  // Same formula-injection guard the server-side CSV uses: Excel/Sheets execute
  // a cell starting with = + - or @, and these cells are third-party job text.
  // Quoting alone doesn't stop it — the leading apostrophe does.
  function csvCell(v) {
    var s = String(v == null ? '' : v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  }
  document.getElementById('export').addEventListener('click', function () {
    var head = ['company', 'role', 'class_year', 'category', 'location', 'salary', 'posted', 'url'],
        lines = [head.join(',')];
    rows.forEach(function (tr) {
      if (!saved[tr.dataset.id]) return;
      var record = JSON.parse(tr.dataset.export);
      JSON.parse(tr.dataset.urls).forEach(function (url) {
        record[7] = url;
        lines.push(record.map(csvCell).join(','));
      });
    });
    if (lines.length === 1) { document.getElementById('result-status').textContent = 'Save a role first to export your shortlist.'; return; }
    var blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }),
        a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'my-saved-new-grad-jobs.csv';
    a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  });

  function cutoffISO(days) {
    var d = new Date(new Date(document.body.dataset.asOf).getTime() - days * 86400000);
    return d.toISOString().slice(0, 10);
  }
  // What each sponsorship option actually means. The old single "F-1 friendly"
  // checkbox only HID the explicit negatives, so ~97% of what it returned was
  // simply postings that never mention sponsorship — shown to students as if
  // it had been checked. Each verdict is now nameable on its own.
  function sponsorOK(mode, value) {
    var restricted = (value === 'citizens-only' || value === 'no-sponsorship');
    if (mode === 'no-restriction') return !restricted;
    if (mode === 'offers') return value === 'offers';
    if (mode === 'unknown') return value === 'unknown' || !value;
    if (mode === 'restricted') return restricted;
    return true;
  }
  function apply() {
    var text = q.value.trim().toLowerCase(), cy = cycle.value, ca = cat.value,
        sp = spon.value, proven = h1b.checked, shown = 0,
        minPosted = age.value ? cutoffISO(parseInt(age.value, 10)) : '',
        statedOnly = stated.checked, prog = program.value,
        remoteOnly = remote.checked, onlySaved = savedonly.checked;
    rows.forEach(function (tr) {
      // A posting that states several class years matches EVERY one of them,
      // so filtering to "Class of 2026" still finds a requisition open to
      // graduates from December 2026 through June 2027.
      var cycles = (tr.dataset.cycles || tr.dataset.cycle || '').split('|');
      var ok = (!text || text.split(/\s+/).every(function (word) { return tr.dataset.text.indexOf(word) !== -1; }))
        && (!cy || cycles.indexOf(cy) !== -1)
        && (!ca || tr.dataset.category === ca)
        && sponsorOK(sp, tr.dataset.sponsor)
        && (!proven || tr.dataset.h1b === '1')
        && (!prog || tr.dataset.program === prog)
        && (!remoteOnly || tr.dataset.remote === '1')
        && (!onlySaved || !!saved[tr.dataset.id])
        && (!minPosted || (tr.dataset.posted && tr.dataset.posted >= minPosted))
        && (!statedOnly || tr.dataset.inferred === '0');
      tr.style.display = ok ? '' : 'none';
      // Count OPENINGS, not rows. A row standing for eight requisitions is
      // eight jobs you can apply to, and the headline number has to agree
      // with the one in the hero and the JSON API.
      if (ok) shown += parseInt(tr.dataset.openings || '1', 10) || 1;
    });
    count.textContent = shown;
    empty.hidden = shown !== 0;
    var noun = shown === 1 ? 'opening' : 'openings';
    document.getElementById('result-label').textContent = (onlySaved ? 'saved ' : '') + noun;
    document.getElementById('result-status').textContent = shown + (onlySaved ? ' saved ' : ' ') + noun + (shown === 1 ? ' matches' : ' match') + ' your filters.';
    var active = controls.filter(function (el) { return el.type === 'checkbox' ? el.checked : !!el.value; });
    document.getElementById('reset').hidden = active.length === 0;
    var secondary = [age, spon, program, remote, h1b, stated].filter(function (el) { return el.type === 'checkbox' ? el.checked : !!el.value; }).length;
    document.getElementById('filter-n').textContent = secondary ? '(' + secondary + ')' : '';
    var unsaved = onlySaved && savedCount() === 0;
    document.getElementById('empty-title').textContent = unsaved ? 'Your shortlist starts here.' : 'No roles match those filters.';
    document.getElementById('empty-help').textContent = unsaved ? 'Choose Save beside a role to keep it here for later.' : 'Try a broader search or remove a filter.';
    document.getElementById('reset2').textContent = unsaved ? 'Browse jobs' : 'Clear filters';
    document.getElementById('export').disabled = savedCount() === 0;
  }
  var controls = [q, cycle, cat, age, spon, program, remote, h1b, stated];
  controls.forEach(function (el) {
    el.addEventListener('input', apply); el.addEventListener('change', apply);
  });
  function reset() {
    controls.forEach(function (el) {
      if (el.type === 'checkbox') el.checked = false; else el.value = '';
    });
    apply();
  }
  document.getElementById('reset').addEventListener('click', reset);
  document.getElementById('reset2').addEventListener('click', reset);

  document.getElementById('filters').addEventListener('submit', function (ev) { ev.preventDefault(); apply(); });
  var more = document.getElementById('more-filters'), moreToggle = document.getElementById('more-toggle');
  moreToggle.addEventListener('click', function () {
    more.hidden = !more.hidden;
    moreToggle.setAttribute('aria-expanded', String(!more.hidden));
  });
  function showSaved(value) {
    savedonly.checked = value;
    document.getElementById('saved-note').hidden = !value;
    document.getElementById('saved-nav').toggleAttribute('aria-current', value);
    document.getElementById('browse-nav').toggleAttribute('aria-current', !value);
    document.getElementById(value ? 'saved-nav' : 'browse-nav').setAttribute('aria-current', 'page');
    apply();
  }
  document.getElementById('saved-nav').addEventListener('click', function () { showSaved(true); });
  document.getElementById('browse-nav').addEventListener('click', function () { showSaved(false); });
  document.getElementById('reset2').addEventListener('click', function () {
    if (savedonly.checked && savedCount() === 0) showSaved(false);
  });
  var sort = document.getElementById('sort');
  sort.addEventListener('change', function () {
    rows.sort(function (a, b) {
      if (sort.value === 'company') return a.dataset.company.localeCompare(b.dataset.company) || a.dataset.title.localeCompare(b.dataset.title);
      if (!a.dataset.posted) return b.dataset.posted ? 1 : 0;
      if (!b.dataset.posted) return -1;
      return (sort.value === 'oldest' ? 1 : -1) * a.dataset.posted.localeCompare(b.dataset.posted);
    });
    rows.forEach(function (tr) { document.getElementById('rows').appendChild(tr); });
  });
  paintAll();
  apply();
  // Radar search (separate list, separate box).
  var rq = document.getElementById('rq');
  if (rq) {
    var rrows = Array.prototype.slice.call(document.getElementById('rrows').rows),
        rcount = document.getElementById('rcount');
    rq.addEventListener('input', function () {
      var text = rq.value.trim().toLowerCase(), shown = 0;
      rrows.forEach(function (tr) {
        var ok = !text || text.split(/\s+/).every(function (word) { return tr.dataset.text.indexOf(word) !== -1; });
        tr.style.display = ok ? '' : 'none';
        if (ok) shown++;
      });
      rcount.textContent = shown;
    });
  }
  // Chart hover tooltip: one floating div fed by each bar's data-tip.
  var tip = document.createElement('div'); tip.id = 'tip'; document.body.appendChild(tip);
  document.querySelectorAll('.cbar').forEach(function (bar) {
    bar.addEventListener('mousemove', function (ev) {
      tip.textContent = bar.dataset.tip; tip.style.display = 'block';
      tip.style.left = (ev.clientX + 12) + 'px'; tip.style.top = (ev.clientY - 28) + 'px';
    });
    bar.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
  });
})();
