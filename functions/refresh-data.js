const OWNER = "rishisann1999-coder";
const REPOSITORY = "PH-shopee-dashboard";
const WORKFLOW = "refresh-dashboard.yml";
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

async function listWorkflowRuns(token) {
  const response = await githubRequest(
    token,
    `/repos/${OWNER}/${REPOSITORY}/actions/workflows/${WORKFLOW}/runs?event=workflow_dispatch&per_page=20`,
  );
  return (await response.json()).workflow_runs || [];
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
    const runs = await listWorkflowRuns(credential.token);
    const activeRun = runs.find((run) => ["queued", "in_progress", "waiting"].includes(run.status));
    if (activeRun) {
      return json({
        ok: true,
        job_id: String(Date.parse(activeRun.created_at)),
        status: activeRun.status === "queued" ? "downloading" : "processing",
        reused: true,
      });
    }

    const recentRun = runs.find((run) => now - Date.parse(run.created_at) < 120000);
    if (recentRun) {
      return json({
        ok: true,
        job_id: String(Date.parse(recentRun.created_at)),
        status: recentRun.status === "completed" ? "processing" : "downloading",
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

    return json({ ok: true, job_id: String(now), status: "downloading" }, 202);
  } catch (error) {
    return json({ ok: false, error: error.message || "无法触发 GitHub Actions" }, 502);
  }
}

export async function onRequestGet(context) {
  const credential = requireConfiguration(context);
  if (credential.error) return credential.error;

  const requestedAt = Number(new URL(context.request.url).searchParams.get("job_id"));
  if (!Number.isFinite(requestedAt)) {
    return json({ ok: false, error: "缺少有效的刷新任务编号" }, 400);
  }

  try {
    const runs = await listWorkflowRuns(credential.token);
    const run = runs
      .filter((item) => Date.parse(item.created_at) >= requestedAt - 15000)
      .sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at))[0];

    if (!run) {
      if (Date.now() - requestedAt < 90000) {
        return json({ ok: true, job_id: String(requestedAt), status: "downloading" });
      }
      return json({ ok: false, job_id: String(requestedAt), status: "error", error: "GitHub Actions 未创建刷新任务" });
    }

    if (run.status !== "completed") {
      return json({
        ok: true,
        job_id: String(requestedAt),
        status: run.status === "queued" ? "downloading" : "processing",
        run_url: run.html_url,
      });
    }

    if (run.conclusion !== "success") {
      return json({
        ok: false,
        job_id: String(requestedAt),
        status: "error",
        error: `GitHub Actions 执行失败：${run.conclusion || "unknown"}`,
        run_url: run.html_url,
      });
    }

    const completedAt = Date.parse(run.updated_at);
    if (Date.now() - completedAt < 90000) {
      return json({
        ok: true,
        job_id: String(requestedAt),
        status: "processing",
        run_url: run.html_url,
      });
    }

    return json({
      ok: true,
      job_id: String(requestedAt),
      status: "complete",
      run_url: run.html_url,
    });
  } catch (error) {
    return json({ ok: false, status: "error", error: error.message || "无法查询刷新进度" }, 502);
  }
}
