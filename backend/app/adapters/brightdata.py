import json
import time

import httpx

from app.core.config import Settings
from app.ports.scraper import HealRequest, HealResult, ScraperStudioPort


class BrightDataError(RuntimeError):
    pass


class BrightDataAdapter(ScraperStudioPort):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=60.0)

    def trigger_and_collect(self, collector_id: str, url: str | None) -> list[dict]:
        collection_id = self._trigger(collector_id, url)
        return self._poll_dataset(collection_id)

    def heal(self, request: HealRequest) -> HealResult:
        base = f"{self._settings.brightdata_api_base}/dca/collectors/{request.collector_id}"
        headers = self._headers()

        start_body = {"prompt": request.prompt[:1000], "custom_input": []}
        if request.url:
            start_body["url"] = request.url
        response = self._client.post(f"{base}/refactor_template", json=start_body, headers=headers)
        if response.status_code >= 400:
            raise BrightDataError(f"heal start failed {response.status_code}: {response.text[:300]}")

        progress = self._await_status(base, headers, ("awaiting_approval", "done"))
        if not request.auto_approve and progress.get("status") != "done":
            return HealResult(approved=False, status="awaiting_approval",
                              detail=str(progress.get("preview_result"))[:500])

        resume_body = {"message": True}
        response = self._client.post(f"{base}/resume_automation_job", json=resume_body, headers=headers)
        if response.status_code >= 400:
            raise BrightDataError(f"resume failed {response.status_code}: {response.text[:300]}")

        final = self._await_status(base, headers, ("done", "completed"))
        return HealResult(approved=True, status=str(final.get("status")), detail="heal applied")

    def _await_status(self, base: str, headers: dict, done_statuses: tuple[str, ...],
                      timeout_s: int = 1500, interval_s: int = 15) -> dict:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            response = self._client.get(f"{base}/refactor_template/progress", headers=headers)
            if response.status_code >= 400:
                raise BrightDataError(f"progress failed {response.status_code}")
            body = response.json()
            status = str(body.get("status", "")).lower()
            if status in done_statuses:
                return body
            time.sleep(interval_s)
        raise BrightDataError("heal timed out")

    def _trigger(self, collector_id: str, url: str | None) -> str:
        params = {"collector": collector_id}
        payload = [{"url": u.strip()} for u in url.split(",") if u.strip()] if url else []
        response = self._client.post(
            f"{self._settings.brightdata_api_base}/dca/trigger",
            params=params,
            json=payload,
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise BrightDataError(f"trigger failed {response.status_code}: {response.text[:300]}")
        body = response.json()
        collection_id = body.get("collection_id") or body.get("snapshot_id") or body.get("id")
        if not collection_id:
            raise BrightDataError(f"no collection id: {str(body)[:200]}")
        return str(collection_id)

    def _poll_dataset(self, collection_id: str, timeout_s: int = 1200, interval_s: int = 10) -> list[dict]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            response = self._client.get(
                f"{self._settings.brightdata_api_base}/dca/dataset",
                params={"id": collection_id, "format": "json"},
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
            result = body.get("result")
            raw = result
            if isinstance(result, dict):
                raw = result.get("body", result.get("data", result))

            if status in ("ready", "done", "completed", "collected"):
                parsed = self._parse_payload(raw)
                if parsed is not None:
                    return parsed
            elif status in ("failed", "error"):
                raise BrightDataError(f"collection {collection_id} failed")
            time.sleep(interval_s)
        raise BrightDataError(f"collection {collection_id} timed out")

    @staticmethod
    def _parse_payload(raw):
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else [parsed]
            except ValueError:
                return [{"text": raw}]
        if isinstance(raw, dict):
            return [raw]
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.brightdata_api_key}",
            "Content-Type": "application/json",
        }


