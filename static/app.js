const $ = (id) => document.getElementById(id);
const button = $("generate");
const result = $("result");
const statusEl = $("status");
const metadataEl = $("metadata");
const audioEl = $("audio");
const downloadEl = $("download");

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollJob(jobId) {
  while (true) {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) throw new Error(`Failed to read job: ${res.status}`);
    const job = await res.json();
    statusEl.textContent = job.status;
    metadataEl.textContent = JSON.stringify({
      job_id: job.job_id,
      status: job.status,
      metadata: job.metadata,
      error: job.error,
    }, null, 2);

    if (job.status === "complete") {
      const url = `/api/jobs/${jobId}/download`;
      audioEl.src = url;
      downloadEl.href = url;
      audioEl.classList.remove("hidden");
      downloadEl.classList.remove("hidden");
      return;
    }
    if (job.status === "failed") return;
    await sleep(900);
  }
}

button.addEventListener("click", async () => {
  button.disabled = true;
  audioEl.classList.add("hidden");
  downloadEl.classList.add("hidden");
  result.classList.remove("hidden");
  statusEl.textContent = "queued";
  metadataEl.textContent = "Submitting job...";

  const seedRaw = $("seed").value.trim();
  const payload = {
    prompt: $("prompt").value,
    lyrics: $("lyrics").value,
    duration_seconds: Number($("duration").value || 45),
  };
  if (seedRaw) payload.seed = Number(seedRaw);

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text);
    }
    const created = await res.json();
    await pollJob(created.job_id);
  } catch (err) {
    statusEl.textContent = "failed";
    metadataEl.textContent = err instanceof Error ? err.message : String(err);
  } finally {
    button.disabled = false;
  }
});
