function formatDuration(seconds) {
  if (seconds == null) return '—';
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—';
}

async function load() {
  StudioNav.render('songs');
  const songs = await StudioApi.listSongs(100);
  const tbody = document.getElementById('song-rows');
  if (!songs.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="table-meta">No generated songs yet — use Generate</td></tr>';
    return;
  }
  tbody.innerHTML = songs.map((song) => {
    const backend = song.generation?.backend || song.version_details?.backend || '—';
    const status = song.generation?.status || '—';
    const reviewClass = song.review_status === 'NEEDS_REVIEW' ? 'status-pill needs-review' : 'status-pill reviewed';
    return `
      <tr>
        <td><button type="button" class="ghost small play-btn" data-id="${song.id}">▶</button></td>
        <td class="table-title">${song.title}</td>
        <td class="table-meta">${backend}</td>
        <td class="table-meta">${status}</td>
        <td><span class="${reviewClass}">${song.review_status.replace(/_/g, ' ').toLowerCase()}</span></td>
        <td>${formatDuration(song.duration_seconds)}</td>
        <td class="table-meta">${formatDate(song.created_at)}</td>
        <td><a class="button ghost small" href="/media-detail.html?id=${song.id}">Open</a></td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.play-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      new Audio(`/api/media/${btn.dataset.id}/audio`).play();
    });
  });
}

load();
