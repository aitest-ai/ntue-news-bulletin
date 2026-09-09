import { sleep } from "workflow";

const REPOSITORY = "aitest-ai/ntue-news-bulletin";

export async function profileDeliveryWakeWorkflow(
  profileId: string,
  slot: string,
  localDate: string,
  wakeAtIso: string,
) {
  "use workflow";

  // Durable sleep survives serverless shutdowns and deployments. The GitHub
  // guard is woken before the slot and performs the final exact-time wait.
  await sleep(new Date(wakeAtIso));
  return dispatchGitHubWake(profileId, slot, localDate);
}

async function dispatchGitHubWake(profileId: string, slot: string, localDate: string) {
  "use step";

  const token = process.env.GITHUB_PAT || process.env.GITHUB_TOKEN;
  if (!token) throw new Error("GITHUB_PAT is unavailable to the durable scheduler");

  const response = await fetch(`https://api.github.com/repos/${REPOSITORY}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
      "User-Agent": "NTUE-Vercel-Durable-Scheduler/1.0",
    },
    body: JSON.stringify({
      event_type: "vercel-scheduler-wake",
      client_payload: {
        profile_id: profileId,
        slot,
        local_date: localDate,
      },
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`GitHub repository_dispatch failed (${response.status}): ${detail.slice(0, 400)}`);
  }

  return { ok: true, profileId, slot, localDate };
}
