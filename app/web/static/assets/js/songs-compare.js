function formatDuration(seconds) {
  if (seconds == null) return '—';
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function formatLabel(value) {
  if (value == null || value === '') return '—';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—';
  return String(value);
}

function reviewPillClass(status) {
  if (status === 'NEEDS_REVIEW') return 'status-pill needs-review';
  if (status === 'REJECTED') return 'status-pill rejected';
  return 'status-pill reviewed';
}

function renderShared(shared) {
  const rows = [
    ['Prompt', shared.prompt],
    ['Seed', shared.seed],
    ['Duration', formatDuration(shared.duration_seconds)],
    ['Mode', shared.mode],
    ['Quality', shared.quality],
    ['Generator', shared.generator],
  ];
  document.getElementById('compare-shared-details').innerHTML = rows
    .map(([label, value]) => `<dt>${label}</dt><dd>${formatLabel(value)}</dd>`)
    .join('');
  document.getElementById('compare-shared').hidden = false;
}

function renderCompareColumn(label, song, side) {
  const vd = song.version_details || {};
  const settings = vd.settings || {};
  return `
    <article class="card compare-column" data-side="${side}" data-song-id="${song.id}">
      <div class="compare-column-head">
        <h2>${label}</h2>
        <span class="${reviewPillClass(song.review_status)}">${song.review_status.replace(/_/g, ' ').toLowerCase()}</span>
      </div>
      <p class="compare-title">${song.title}</p>
      <audio controls preload="metadata" src="${song.audio_url || ''}"></audio>
      <dl class="detail-meta compare-meta">
        <dt>Style version</dt><dd>${formatLabel(vd.style_version_id)}</dd>
        <dt>Training run</dt><dd>${formatLabel(vd.training_run_id)}</dd>
        <dt>LoRA path</dt><dd>${formatLabel(vd.lora_path)}</dd>
        <dt>LoRA scale</dt><dd>${formatLabel(vd.lora_scale)}</dd>
        <dt>LoRA loaded</dt><dd>${vd.lora_load_succeeded === true ? 'yes' : vd.lora_load_attempted ? 'attempted' : 'no'}</dd>
        <dt>Backend</dt><dd>${formatLabel(vd.backend)}</dd>
        <dt>Quality</dt><dd>${formatLabel(settings.quality)}</dd>
      </dl>
      <section class="review-card">
        <h3>Review</h3>
        <div class="review-actions">
          <button type="button" class="ghost small" data-decision="KEEPER">Keeper</button>
          <button type="button" class="ghost small" data-decision="REJECT">Reject</button>
          <button type="button" class="ghost small" data-decision="USE_AS_REFERENCE">Use as reference</button>
          <button type="button" class="ghost small" data-decision="USE_AS_NEGATIVE">Use as negative</button>
        </div>
        <label class="review-score-label">
          Overall score
          <select class="review-score">
            <option value="">—</option>
            ${[1, 2, 3, 4, 5].map((n) => `<option value="${n}" ${song.review_score === n ? 'selected' : ''}>${n}</option>`).join('')}
          </select>
        </label>
        <label class="review-notes-label">
          Notes
          <textarea class="review-notes" rows="3">${song.review_notes || ''}</textarea>
        </label>
        <p class="save-feedback compare-feedback" hidden aria-live="polite"></p>
      </section>
    </article>
  `;
}

async function submitReview(side, decision, button) {
  const column = document.querySelector(`.compare-column[data-side="${side}"]`);
  const songId = column.dataset.songId;
  const payload = {
    decision,
    overall_score: column.querySelector('.review-score').value ? Number(column.querySelector('.review-score').value) : null,
    notes: column.querySelector('.review-notes').value.trim() || null,
  };
  await StudioSave.run(
    button,
    () => StudioApi.reviewSong(songId, payload),
    {
      savingLabel: 'Saving…',
      successMessage: `Saved ${decision.replace(/_/g, ' ').toLowerCase()}.`,
      feedbackEl: column.querySelector('.compare-feedback'),
    },
  );
}

function wireReviewHandlers() {
  document.querySelectorAll('.compare-column').forEach((column) => {
    const side = column.dataset.side;
    column.querySelectorAll('[data-decision]').forEach((btn) => {
      btn.addEventListener('click', () => submitReview(side, btn.dataset.decision, btn).catch((err) => {
        const feedback = column.querySelector('.compare-feedback');
        feedback.hidden = false;
        feedback.className = 'save-feedback compare-feedback error';
        feedback.textContent = err.message;
      }));
    });
  });
}

async function loadComparison() {
  const params = new URLSearchParams(window.location.search);
  const baselineId = params.get('baseline_id') || params.get('baseline');
  const styledId = params.get('styled_id') || params.get('styled');
  const errorEl = document.getElementById('compare-error');
  if (!baselineId || !styledId) {
    errorEl.hidden = false;
    errorEl.textContent = 'Provide baseline_id and styled_id query parameters.';
    return;
  }
  const data = await StudioApi.compareSongs(baselineId, styledId);
  document.getElementById('compare-meta').textContent = [
    data.style_version_id ? `style_version_id=${data.style_version_id}` : null,
    data.training_run_id ? `training_run_id=${data.training_run_id}` : null,
  ].filter(Boolean).join(' · ');
  renderShared(data.shared);
  document.getElementById('compare-grid').innerHTML = [
    renderCompareColumn('Baseline', data.baseline, 'baseline'),
    renderCompareColumn('Styled', data.styled, 'styled'),
  ].join('');
  wireReviewHandlers();
}

loadComparison().catch((err) => {
  const errorEl = document.getElementById('compare-error');
  errorEl.hidden = false;
  errorEl.textContent = err.message;
});
