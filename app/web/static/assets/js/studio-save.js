window.StudioSave = (() => {
  function resolveFeedback(feedbackEl) {
    if (!feedbackEl) return null;
    if (typeof feedbackEl === 'string') return document.getElementById(feedbackEl);
    return feedbackEl;
  }

  function showFeedback(el, message, state) {
    if (!el) return;
    el.hidden = false;
    el.classList.remove('saving', 'saved', 'error', 'hidden');
    el.classList.add(state);
    el.textContent = message;
  }

  async function run(button, task, options = {}) {
    const {
      savingLabel = 'Saving…',
      successMessage = 'Saved.',
      feedbackEl = null,
      resetMs = 2500,
    } = options;

    const feedback = resolveFeedback(feedbackEl);
    if (!button || button.dataset.saveBusy === '1') return;

    const originalLabel = button.textContent;
    button.dataset.saveBusy = '1';
    button.disabled = true;
    button.classList.add('save-busy');
    button.textContent = savingLabel;
    showFeedback(feedback, savingLabel, 'saving');

    try {
      const result = await task();
      button.classList.remove('save-busy');
      button.classList.add('save-ok');
      button.textContent = 'Saved ✓';
      const message = typeof successMessage === 'function' ? successMessage(result) : successMessage;
      showFeedback(feedback, message, 'saved');
      window.setTimeout(() => {
        button.textContent = originalLabel;
        button.classList.remove('save-ok');
        button.disabled = false;
        delete button.dataset.saveBusy;
      }, resetMs);
      return result;
    } catch (err) {
      button.classList.remove('save-busy');
      button.textContent = originalLabel;
      button.disabled = false;
      delete button.dataset.saveBusy;
      showFeedback(feedback, err.message || 'Save failed.', 'error');
      throw err;
    }
  }

  return { run };
})();
