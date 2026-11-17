const OWNER = "wting2658-debug";
const REPOSITORY = "ph-shopee-dashboard-wting";
const WORKFLOW = "refresh-dashboard.yml";
const DEPLOY_WORKFLOW = "deploy-dashboard.yml";
const BRANCH = "main";
const GITHUB_API = "https://api.github.com";

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function githubHeaders(token) {
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${token}`,
    "User-Agent": "PH-Shopee-Dashboard-Refresh",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

async function githubRequest(token, path, options = {}) {
  const response = await fetch(`${GITHUB_API}${path}`, {
    ...options,
    headers: {
      ...githubHeaders(token),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 500);
    throw new Error(`GitHub API ${response.status}: ${detail}`);
  }
  return response;
}

async function listWorkflowRuns(token, workflow = WORKFLOW, event = "") {
  const query = new URLSearchParams({ branch: BRANCH, per_page: "30" });
  if (event) query.set("event", event);
  const response = await githubRequest(
    token,
    `/repos/${OWNER}/${REPOSITORY}/actions/workflows/${workflow}/runs?${query}`,
  );
  return (await response.json()).workflow_runs || [];
}

function validRunId(value) {
  return typeof value === "string" && /^[1-9]\d*$/.test(value) ? value : null;
}

function refreshStatus(run) {
  return run.status === "queued" || run.status === "waiting" || run.status === "requested" || run.status === "pending"
    ? "downloading" : "processing";
}

function secureEquals(left, right) {
  if (typeof left !== "string" || typeof right !== "string" || left.length !== right.length) return false;
  let result = 0;
  for (let index = 0; index < left.length; index += 1) {
    result |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return result === 0;
}

function requireConfiguration(context) {
  const token = context.env.GITHUB_ACTIONS_TOKEN;
  if (!token) {
    return {
      error: json(
        {
          ok: false,
          error: "Cloudflare 尚未配置 GITHUB_ACTIONS_TOKEN",
        },
        503,
      ),
    };
  }
  const refreshKey = context.env.REFRESH_KEY;
  if (!refreshKey) {
    return {
      error: json(
        {
          ok: false,
          error: "Cloudflare 尚未配置 REFRESH_KEY",
        },
        503,
      ),
    };
  }
  if (!secureEquals(context.request.headers.get("X-Refresh-Key") || "", refreshKey)) {
    return { error: json({ ok: false, error: "刷新口令不正确" }, 401) };
  }
  return { token };
}

export async function onRequestPost(context) {
  const credential = requireConfiguration(context);
  if (credential.error) return credential.error;

  try {
    const now = Date.now();
    // Reuse only an active refresh, including the scheduled run. Completed runs
    // must never suppress a new manual request, even if they just finished.
    const runs = await listWorkflowRuns(credential.token);
    const activeRun = runs.find((run) => run.status !== "completed");
    if (activeRun) {
      return json({
        ok: true,
        job_id: String(Date.parse(activeRun.created_at)),
        run_id: String(activeRun.id),
        status: refreshStatus(activeRun),
        reused: true,
      });
    }

    await githubRequest(
      credential.token,
      `/repos/${OWNER}/${REPOSITORY}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ref: BRANCH }),
      },
    );

    // GitHub's dispatch endpoint does not return a run ID. This lower bound
    // distinguishes the new run from a previous run created in the same second.
    const afterRunId = runs.reduce((last, run) => BigInt(run.id) > BigInt(last) ? String(run.id) : last, "0");
    return json({ ok: true, job_id: String(now), after_run_id: afterRunId, status: "downloading" }, 202);
  } catch (error) {
    return json({ ok: false, error: error.message || "无法触发 GitHub Actions" }, 502);
  }
}

export async function onRequestGet(context) {
  const credential = requireConfiguration(context);
  if (credential.error) return credential.error;

  const params = new URL(context.request.url).searchParams;
  const rawJobId = params.get("job_id");
  const requestedAt = Number(rawJobId);
  const runId = validRunId(params.get("run_id"));
  const rawAfterId = params.get("after_run_id");
  const afterRunId = rawAfterId === "0" ? "0" : validRunId(rawAfterId);
  if (!rawJobId || !Number.isFinite(requestedAt) || requestedAt <= 0 || requestedAt > Date.now() + 60000 ||
      (params.has("run_id") && !runId) || (params.has("after_run_id") && afterRunId === null)) {
    return json({ ok: false, error: "缺少有效的刷新任务编号" }, 400);
  }

  try {
    let run;
    if (runId) {
      const response = await githubRequest(credential.token, `/repos/${OWNER}/${REPOSITORY}/actions/runs/${runId}`);
      run = await response.json();
      if (run.head_branch !== BRANCH || run.path !== `.github/workflows/${WORKFLOW}`) {
        return json({ ok: false, status: "error", error: "刷新任务编号不属于此看板" }, 400);
      }
    } else {
      const runs = await listWorkflowRuns(credential.token, WORKFLOW, "workflow_dispatch");
      run = runs.filter((item) =>
        Date.parse(item.created_at) >= Math.floor(requestedAt / 1000) * 1000 &&
        (afterRunId === null || BigInt(item.id) > BigInt(afterRunId)))
        .sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at) || left.id - right.id)[0];
    }

    if (!run) {
      if (Date.now() - requestedAt < 120000) {
        return json({ ok: true, job_id: String(requestedAt), after_run_id: afterRunId, status: "downloading" });
      }
      return json({ ok: false, job_id: String(requestedAt), status: "error", error: "GitHub Actions 未创建刷新任务，请重试" });
    }

    const job = { job_id: String(requestedAt), run_id: String(run.id), run_url: run.html_url };
    if (run.status !== "completed") {
      return json({ ok: true, ...job, status: refreshStatus(run) });
    }
    if (run.conclusion !== "success") {
      return json({ ok: false, ...job, status: "error", error: `数据刷新失败：${run.conclusion || "unknown"}` });
    }

    // A completed data build is not yet a published dashboard. The deployment
    // run name contains the originating refresh ID, so another refresh/deploy
    // cannot accidentally satisfy this request.
    const [deployments, branchResponse] = await Promise.all([
      listWorkflowRuns(credential.token, DEPLOY_WORKFLOW, "workflow_run"),
      githubRequest(credential.token, `/repos/${OWNER}/${REPOSITORY}/git/ref/heads/${BRANCH}`),
    ]);
    const latestSha = (await branchResponse.json()).object.sha;
    const deployment = deployments.filter((item) =>
      item.display_title === `Refresh ${run.id}` && item.head_sha === latestSha)
      .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at) || right.id - left.id)[0];
    if (!deployment) {
      if (Date.now() - Date.parse(run.updated_at) > 10 * 60 * 1000) {
        return json({ ok: false, ...job, status: "error", error: "数据已生成，但线上部署未启动，请重试或检查部署任务" });
      }
      return json({ ok: true, ...job, status: "publishing" });
    }
    const publishedJob = { ...job, deploy_run_id: String(deployment.id), deploy_url: deployment.html_url };
    if (deployment.status !== "completed") {
      return json({ ok: true, ...publishedJob, status: "publishing" });
    }
    if (deployment.conclusion !== "success") {
      return json({ ok: false, ...publishedJob, status: "error", error: `线上部署失败：${deployment.conclusion || "unknown"}` });
    }
    return json({ ok: true, ...publishedJob, status: "complete" });
  } catch (error) {
    return json({ ok: false, status: "error", error: error.message || "无法查询刷新进度" }, 502);
  }
}
