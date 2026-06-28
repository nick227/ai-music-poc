/** Human-readable labels for generation engines and LoRA metadata. */
window.RenderLabels = {
  engineLabel(song) {
    const vd = song?.version_details || {};
    const settings = vd.settings || {};
    const quality = settings.quality || '';
    const backend = vd.backend || song?.generation?.backend || '';
    const generator = vd.generator_name || song?.generation?.generator || '';
    const renderRoute = vd.render_route || '';
    const useLora = vd.use_lora || vd.lora_path || vd.style_version_id;

    if (renderRoute === 'draft-parametric' || backend === 'procedural-v3' || backend === 'procedural-fallback') {
      return quality === 'draft' ? 'Draft preview (parametric synth)' : 'Parametric fallback';
    }
    if (backend === 'external-command' || renderRoute === 'final-neural' || generator === 'ace-step-command' || generator === 'auto-render') {
      if (useLora) return 'ACE-Step neural + LoRA';
      return 'ACE-Step neural (base model)';
    }
    if (generator === 'mock-ai') return 'Mock adapter';
    return backend || generator || '—';
  },

  loraAdapterLabel(vd) {
    if (!vd?.style_version_id) return 'None (base model only)';
    const name = vd.lora_adapter_name || vd.style_version_id;
    const scale = vd.lora_scale != null ? ` · scale ${vd.lora_scale}` : '';
    const loaded = vd.lora_load_succeeded === true ? ' · loaded' : vd.lora_load_attempted ? ' · load failed' : '';
    return `${name}${scale}${loaded}`;
  },
};
