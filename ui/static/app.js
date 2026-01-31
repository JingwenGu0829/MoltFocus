async function postJSON(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status} ${txt}`);
  }
  return res.json();
}

function debounce(fn, ms) {
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function currentMode() {
  const el = document.querySelector('input[name="mode"]:checked');
  return el ? el.value : 'commit';
}

function collectDraft() {
  const items = [];
  document.querySelectorAll('[data-item-row]').forEach(row => {
    const key = row.getAttribute('data-key');
    const label = row.querySelector('[data-label]')?.textContent || '';
    const done = row.querySelector('input[type=checkbox]')?.checked || false;
    const comment = row.querySelector('input[data-comment]')?.value || '';
    items.push({ key, label, done, comment });
  });
  const reflection = document.querySelector('#reflection')?.value || '';
  const mode = currentMode();
  return { mode, items, reflection };
}

async function saveDraftNow() {
  const status = document.querySelector('#saveStatus');
  try {
    if (status) status.textContent = 'Saving…';
    const payload = collectDraft();
    await postJSON('/api/checkin_draft', payload);
    if (status) status.textContent = 'Saved';
  } catch (e) {
    if (status) status.textContent = 'Save failed';
    console.error(e);
  }
}

const saveDraft = debounce(saveDraftNow, 500);

async function writeFocus(payload) {
  try {
    await postJSON('/api/focus', payload);
  } catch (e) {
    console.error(e);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  // Plan: preview by default
  if (document.querySelector('#planPreview')) {
    showPlanPreview();
  }
  const planTA = document.querySelector('#plan');
  if (planTA) planTA.addEventListener('input', debounce(renderPlanPreview, 200));


  const toggleBtn = document.querySelector('#planToggle');
  const planPane = document.querySelector('#planPane');
  const planTA = document.querySelector('#plan');
  const planPV = document.querySelector('#planPreview');

  function setToggleLabel() {
    if (!toggleBtn || !planTA) return;
    toggleBtn.textContent = (planTA.style.display === 'none') ? 'Edit' : 'Preview';
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const ta = document.querySelector('#plan');
      if (!ta) return;
      if (ta.style.display === 'none') showPlanEdit();
      else showPlanPreview();
      setToggleLabel();
    });
  }

  // Click plan preview to edit
  if (planPV) {
    planPV.addEventListener('click', (e) => {
      // avoid toggling when selecting text
      showPlanEdit();
      setToggleLabel();
    });
  }

  // Click outside plan pane -> preview
  document.addEventListener('click', (e) => {
    const ta = document.querySelector('#plan');
    if (!ta || ta.style.display === 'none') return; // already preview
    if (planPane && planPane.contains(e.target)) return;
    showPlanPreview();
    setToggleLabel();
  });


  document.querySelectorAll('input, textarea, select').forEach(el => {
    if (el.closest('[data-checkin]')) {
      el.addEventListener('input', saveDraft);
      el.addEventListener('change', saveDraft);
    }
  });

  const manual = document.querySelector('#manualSave');
  if (manual) manual.addEventListener('click', (e) => { e.preventDefault(); saveDraftNow(); });

  const focusStart = document.querySelector('#focusStart');
  const focusStop = document.querySelector('#focusStop');
  const focusSelect = document.querySelector('#focusSelect');
  const focusStatus = document.querySelector('#focusStatus');

  if (focusStart && focusSelect) {
    focusStart.addEventListener('click', async (e) => {
      e.preventDefault();
      const key = focusSelect.value;
      if (!key) return;
      const label = focusSelect.options[focusSelect.selectedIndex]?.textContent || '';
      const startedAt = new Date().toISOString();
      await writeFocus({ active: true, key, label, startedAt });
      if (focusStatus) focusStatus.textContent = `Focus started: ${label}`;
    });
  }

  if (focusStop) {
    focusStop.addEventListener('click', async (e) => {
      e.preventDefault();
      const stoppedAt = new Date().toISOString();
      await writeFocus({ active: false, stoppedAt });
      if (focusStatus) focusStatus.textContent = 'Focus stopped.';
    });
  }
});


function renderPlanPreview() {
  const ta = document.querySelector('#plan');
  const pv = document.querySelector('#planPreview');
  if (!ta || !pv) return;
  const src = ta.value || '';
  if (window.marked) {
    pv.innerHTML = window.marked.parse(src);
  } else {
    pv.textContent = src;
  }
}

function showPlanEdit() {
  const ta = document.querySelector('#plan');
  const pv = document.querySelector('#planPreview');
  if (!ta || !pv) return;
  pv.style.display = 'none';
  ta.style.display = 'block';
  ta.focus();
}

function showPlanPreview() {
  const ta = document.querySelector('#plan');
  const pv = document.querySelector('#planPreview');
  if (!ta || !pv) return;
  renderPlanPreview();
  ta.style.display = 'none';
  pv.style.display = 'block';
}
