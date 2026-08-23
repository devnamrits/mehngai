import time

import httpx

from app.core.config import Settings
from app.ports.scraper import HealRequest, HealResult, ScraperStudioPort


class BrightDataError(RuntimeError):
    pass


class BrightDataAdapter(ScraperStudioPort):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=30.0)

    def trigger_and_collect(self, collector_id: str, url: str | None) -> list[dict]:
        snapshot_id = self._trigger(collector_id, url)
        return self._poll_snapshot(snapshot_id)

    def heal(self, request: HealRequest) -> HealResult:
        if request.auto_approve:
            return self._heal_auto(request)
        return self._heal_supervised(request)

    def _trigger(self, collector_id: str, url: str | None) -> str:
        payload: dict = {"collector_id": collector_id}
        if url:
            payload["url"] = url
        response = self._client.post(
            f"{self._settings.brightdata_api_base}/dca/trigger",
            json=payload,
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise BrightDataError(f"trigger failed {response.status_code}: {response.text[:300]}")
        body = response.json()
        snapshot_id = body.get("snapshot_id") or body.get("id")
        if not snapshot_id:
            raise BrightDataError(f"no snapshot id for {collector_id}: {body}")
        return str(snapshot_id)

    def _poll_snapshot(self, snapshot_id: str, timeout_s: int = 900, interval_s: int = 10) -> list[dict]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            response = self._client.get(
                f"{self._settings.brightdata_api_base}/dca/dataset/{snapshot_id}",
                params={"format": "json"},
                headers=self._headers(),
            )
            if response.status_code >= 400:
                raise BrightDataError(f"dataset poll failed {response.status_code}")
            try:
                body = response.json()
            except ValueError:
                time.sleep(interval_s)
                continue
            if isinstance(body, list):
                return body
            status = str(body.get("status", "")).lower()
            if status in ("running", "pending", "collected"):
                time.sleep(interval_s)
                continue
            if status == "failed":
                raise BrightDataError(f"snapshot {snapshot_id} failed")
            time.sleep(interval_s)
        raise BrightDataError(f"snapshot {snapshot_id} timed out")

    def _heal_supervised(self, request: HealRequest) -> HealResult:
        job_id = self._start_refactor(request)
        prompt_answer = self._await_refactor(job_id)
        approved = self._resume_job(job_id, approve=True)
        detail = str(prompt_answer)[:500]
        return HealResult(approved=approved, status="done" if approved else "rejected", detail=detail)

    def _heal_auto(self, request: HealRequest) -> HealResult:
        result = self._heal_supervised(request)
        return result

    def _start_refactor(self, request: HealRequest) -> str:
        url = f"{self._settings.brightdata_api_base}/dca/collectors/{request.collector_id}/refactor_template"
        payload = {"prompt": request.prompt[:1000]}
        if request.url:
            payload["url"] = request.url
        response = self._client.post(url, json=payload, headers=self._headers())
        if response.status_code >= 400:
            raise BrightDataError(f"refactor start failed {response.status_code}: {response.text[:300]}")
        body = response.json()
        job_id = body.get("job_id") or body.get("id")
        if not job_id:
            raise BrightDataError(f"no refactor job id: {body}")
        return str(job_id)

    def _await_refactor(self, job_id: str, timeout_s: int = 1200, interval_s: int = 15):
        deadline = time.monotonic() + timeout_s
        progress_url = (
            f"{self._settings.brightdata_api_base}"
            f"/dca/collectors/refactor_template/{job_id}/progress"
        )
        while time.monotonic() < deadline:
            response = self._client.get(progress_url, headers=self._headers())
            if response.status_code >= 400:
                raise BrightDataError(f"refactor progress failed {response.status_code}")
            body = response.json()
            status = str(body.get("status", "")).lower()
            if status in ("pending_answer", "done", "completed"):
                return body
            time.sleep(interval_s)
        raise BrightDataError(f"refactor job {job_id} timed out")

    def _resume_job(self, job_id: str, approve: bool) -> bool:
        url = (
            f"{self._settings.brightdata_api_base}"
            f"/dca/collectors/refactor_template/{job_id}/resume_automation_job"
        )
        response = self._client.post(url, json={"approve": approve}, headers=self._headers())
        if response.status_code >= 400:
            raise BrightDataError(f"resume failed {response.status_code}: {response.text[:300]}")
        return True

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.brightdata_api_key}",
            "Content-Type": "application/json",
        }
