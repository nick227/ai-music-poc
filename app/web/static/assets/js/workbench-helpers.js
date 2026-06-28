window.WorkbenchHelpers = (() => {
  function formatWhen(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  function formatDuration(seconds) {
    if (!seconds) return '0m';
    const mins = Math.round(seconds / 60);
    if (mins < 60) return `${mins}m`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  }

  function tierLabel(tier) {
    const labels = { CANDIDATE: 'candidate', TRAINABLE: 'trainable', STRONG: 'strong fit' };
    return labels[tier] || 'candidate';
  }

  function runsForPackage(runs, sliceId) {
    return runs
      .filter((run) => run.dataset_slice_id === sliceId)
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }

  function packageTrainingState(runs, sliceId, globalActive) {
    const history = runsForPackage(runs, sliceId);
    const latest = history[0] || null;
    const neverTrained = history.length === 0;
    const isActive = latest && (latest.status === 'QUEUED' || latest.status === 'RUNNING');
    const succeeded = latest && latest.status === 'SUCCEEDED';
    return { history, latest, neverTrained, isActive, succeeded, globalActive };
  }

  function trainingActionLabel(state) {
    if (state.globalActive && !state.isActive) return 'Waiting…';
    if (state.isActive) return 'Running…';
    if (state.neverTrained) return 'Start training';
    return 'Re-run training';
  }

  function trainingStatusLine(state) {
    if (state.neverTrained) return 'Never trained';
    const run = state.latest;
    const when = formatWhen(run.finished_at || run.started_at || run.created_at);
    const summary = StudioTrainingStatus.runSummary(run);
    const count = state.history.length;
    const extra = count > 1 ? ` · ${count} runs total` : '';
    return `Last run ${when} · ${summary}${extra}`;
  }

  function pendingSummaryHtml(readyAudio) {
    if (!readyAudio.total) {
      return '<p class="pending-empty">No songs ready for training yet. Tag and approve songs in the library first.</p>';
    }
    const totalDur = readyAudio.items.reduce((sum, item) => sum + (item.duration_seconds || 0), 0);
    const groupLines = readyAudio.groups.slice(0, 6).map((group) => {
      const dur = group.items.reduce((sum, item) => sum + (item.duration_seconds || 0), 0);
      return `<li><strong>${group.label}</strong> · ${group.items.length} song${group.items.length === 1 ? '' : 's'} · ${formatDuration(dur)}</li>`;
    }).join('');
    const more = readyAudio.groups.length > 6
      ? `<li class="muted">+ ${readyAudio.groups.length - 6} more groups</li>`
      : '';
    return `
      <div class="pending-stats">
        <span class="pending-stat"><strong>${readyAudio.total}</strong> songs pending</span>
        <span class="pending-stat"><strong>${readyAudio.groups.length}</strong> group${readyAudio.groups.length === 1 ? '' : 's'}</span>
        <span class="pending-stat"><strong>${formatDuration(totalDur)}</strong> audio</span>
      </div>
      <ul class="pending-groups">${groupLines}${more}</ul>
    `;
  }

  function candidateSummaryMessage(slices, readyAudio) {
    if (!slices.length) {
      if (!readyAudio.total) {
        return 'No tagged songs available to scan. Add tags in the library first.';
      }
      return 'No new dataset candidates found. Existing combos may already be listed below, or songs need more category overlap (min 3 tracks, 60s).';
    }
    const tracks = slices.reduce((sum, slice) => sum + slice.asset_count, 0);
    return `Found ${slices.length} candidate${slices.length === 1 ? '' : 's'} covering ${tracks} song${tracks === 1 ? '' : 's'}. Freeze any you want to train.`;
  }

  return {
    formatWhen,
    formatDuration,
    tierLabel,
    runsForPackage,
    packageTrainingState,
    trainingActionLabel,
    trainingStatusLine,
    pendingSummaryHtml,
    candidateSummaryMessage,
  };
})();
