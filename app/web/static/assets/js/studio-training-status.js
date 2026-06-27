window.StudioTrainingStatus = {
  mediaLabel(row) {
    if (row.ready_audio) return 'ready audio';
    if ((row.ingestion_status || '') === 'INGESTING') return 'packaging';
    if ((row.ingestion_status || '') === 'INGESTED') return 'packaged';
    if ((row.rights_status || '') === 'DO_NOT_TRAIN') return 'do not train';
    if ((row.review_status || '') === 'REJECTED') return 'rejected';
    return 'needs tags';
  },
  runBadgeClass(run) {
    if (run.dry_run && run.status === 'SUCCEEDED') return 'draft';
    if (run.status === 'SUCCEEDED') return 'ready';
    if (run.status === 'FAILED') return 'draft';
    return 'running';
  },
  runSummary(run) {
    if (run.status_label) return run.status_label;
    return (run.status || 'unknown').toLowerCase();
  },
  packageSummary(pkg) {
    return pkg.status_label || 'Training package ready';
  },
  completionMessage(run) {
    if (!run) return '';
    if (run.dry_run && run.status === 'SUCCEEDED') {
      return 'ACE command rendered. Real ACE training is not enabled and no artifact was produced.';
    }
    if (run.mock_training && run.status === 'SUCCEEDED' && run.artifact_produced) {
      return 'Mock training complete. Placeholder artifact produced.';
    }
    if (run.status === 'SUCCEEDED') return run.status_label || 'Training complete.';
    return `Run ${(run.status || '').toLowerCase()}.`;
  },
};
