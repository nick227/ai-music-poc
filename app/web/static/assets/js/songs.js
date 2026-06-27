let songs = [];
let selectedId = null;

function formatDuration(seconds) {
  if (seconds == null) return '—';
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—';
}

function reviewPillClass(status) {
  if (status === 'NEEDS_REVIEW') return 'status-pill needs-review';
  if (status === 'REJECTED') return 'status-pill rejected';
  return 'status-pill reviewed';
}

function formatLabel(value) {
  if (value == null || value === '') return '—';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function versionDetailRows(song) {
  const vd = song.version_details || {};
  const gen = song.generation || {};
  const settings = vd.settings || {};
  return [
    ['Generation ID', vd.generation_id || gen.id],
    ['Backend', vd.backend || gen.backend],
    ['Model version', vd.model_version || gen.model_version],
    ['Style version', vd.style_version_id],
    ['Training run', vd.training_run_id],
    ['Dataset slice', vd.dataset_slice_id],
    ['Target concept', vd.target_concept_id],
    ['Target categories', vd.target_category_ids],
    ['Prompt', vd.prompt || gen.prompt],
    ['Lyrics', vd.lyrics || gen.lyrics],
    ['Seed', vd.seed ?? gen.seed],
    ['Duration', formatDuration(vd.duration_seconds ?? song.duration_seconds)],
    ['Quality', settings.quality],
    ['Mode', settings.mode],
    ['Structure', settings.structure],
    ['BPM', settings.bpm],
    ['Key', settings.key],
    ['Vocal style', settings.vocal_style || settings.vocalStyle],
    ['Output file', vd.output_file || song.file_path],
    ['Created', formatDate(song.created_at)],
  ];
}

function renderVersionDetails(song) {
  const list = document.getElementById('version-details');
  list.innerHTML = versionDetailRows(song)
    .map(([label, value]) => `<dt>${label}</dt><dd>${formatLabel(value)}</dd>`)
    .join('');
}

function setActiveDecision(decision) {
  document.querySelectorAll('#review-actions button').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.decision === decision);
  });
}

function renderDetail(song) {
  const empty = document.querySelector('.empty-detail');
  const body = document.getElementById('song-detail-body');
  if (!song) {
    empty.hidden = false;
    body.hidden = true;
    return;
  }

  empty.hidden = true;
  body.hidden = false;

  document.getElementById('detail-title').textContent = song.title;
  const pill = document.getElementById('detail-review-pill');
  pill.className = reviewPillClass(song.review_status);
  pill.textContent = song.review_status.replace(/_/g, ' ').toLowerCase();

  const player = document.getElementById('detail-player');
  player.src = song.audio_url || '';
  player.load();

  renderVersionDetails(song);
  document.getElementById('review-score').value = song.review_score ?? '';
  document.getElementById('review-notes').value = song.review_notes || '';
  setActiveDecision(song.review_decision || null);

  const feedback = document.getElementById('review-feedback');
  feedback.hidden = true;
  feedback.classList.remove('saving', 'saved', 'error');
}

function renderTable() {
  const tbody = document.getElementById('song-rows');
  if (!songs.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="table-meta">No generated songs yet — use Generate</td></tr>';
    renderDetail(null);
    return;
  }

  tbody.innerHTML = songs.map((song) => {
    const backend = song.generation?.backend || song.version_details?.backend || '—';
    const reviewClass = reviewPillClass(song.review_status);
    const decision = song.review_decision ? song.review_decision.replace(/_/g, ' ').toLowerCase() : '—';
    const selected = song.id === selectedId ? 'selected' : '';
    return `
      <tr class="${selected}" data-id="${song.id}">
        <td class="table-title">${song.title}</td>
        <td class="table-meta">${backend}</td>
        <td><span class="${reviewClass}">${song.review_status.replace(/_/g, ' ').toLowerCase()}</span></td>
        <td class="table-meta">${decision}</td>
        <td>${formatDuration(song.duration_seconds)}</td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('tr[data-id]').forEach((row) => {
    row.addEventListener('click', () => selectSong(row.dataset.id));
  });

  if (!selectedId && songs.length) selectedId = songs[0].id;
  renderDetail(songs.find((s) => s.id === selectedId) || null);
}

async function selectSong(id) {
  selectedId = id;
  const song = await StudioApi.getSong(id);
  songs = songs.map((item) => (item.id === id ? song : item));
  renderTable();
}

async function submitReview(decision, button) {
  if (!selectedId || !button) return;
  const overallScore = document.getElementById('review-score').value;
  const notes = document.getElementById('review-notes').value.trim();
  const payload = {
    decision,
    overall_score: overallScore ? Number(overallScore) : null,
    notes: notes || null,
  };
  await StudioSave.run(
    button,
    async () => {
      const song = await StudioApi.reviewSong(selectedId, payload);
      songs = songs.map((item) => (item.id === song.id ? song : item));
      setActiveDecision(decision);
      renderTable();
      renderDetail(song);
      return song;
    },
    {
      savingLabel: 'Saving…',
      successMessage: `Saved ${decision.replace(/_/g, ' ').toLowerCase()}.`,
      feedbackEl: 'review-feedback',
    },
  );
}

async function loadSongs() {
  const reviewStatus = document.getElementById('filter-review').value;
  songs = await StudioApi.listSongs({ limit: 100, review_status: reviewStatus || undefined });
  if (selectedId && !songs.some((s) => s.id === selectedId)) selectedId = null;
  renderTable();
}

document.getElementById('filter-review').addEventListener('change', loadSongs);

document.querySelectorAll('#review-actions button').forEach((btn) => {
  btn.addEventListener('click', () => submitReview(btn.dataset.decision, btn).catch(() => {}));
});

loadSongs();
