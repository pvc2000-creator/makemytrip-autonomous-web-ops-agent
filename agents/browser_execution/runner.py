"""Browser action runner.

Executes a plan step by step in a real browser (Playwright/Chromium), or with a plain HTTP engine
for read-only monitoring when Chromium is not installed.

Every action:
  1. waits at the RunControl checkpoint (pause / step / stop from the UI)
  2. highlights the target element in the page and captures a frame for the live view
  3. performs the action and captures a second frame of the result
Governance: every navigation, including ones caused by clicking links, must stay on the domain
allowlist; the agent never types into card, CVV, OTP or password fields; approval steps block until a
person decides in the UI.
"""
import asyncio
import os
import re
import sys
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from backend.auth.policy import PolicyViolation, policy
from backend.config import settings
from backend.jobs.live import StopRequested, hub
from extraction.normalizers import normalize_price

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36 MMT-WebOpsAgent/2.0")
SPEED_DELAY_MS = {"fast": 0, "normal": 350, "slow": 1100}
INTERACTIVE = {"click", "fill", "select", "check", "uncheck", "press", "scroll", "pick_best", "approval"}
POST_TOOLS = {"compare", "summarize", "route"}
SENSITIVE = re.compile(r"card|cc-|cvv|cvc|password|passwd|otp|\bpin\b|upi-pin|netbanking", re.I)


class BrowserError(Exception):
    def __init__(self, category: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.category, self.retryable = category, retryable


def _status_error(code: int):
    if code in (401, 403):
        return BrowserError("browser_blocked", f"Source refused access (HTTP {code})")
    if code == 429:
        return BrowserError("rate_limited_by_source", "Source rate-limited the agent (HTTP 429)", True)
    if code == 404:
        return BrowserError("source_unavailable", "Page not found (HTTP 404)")
    if code >= 500:
        return BrowserError("source_unavailable", f"Source error (HTTP {code})", True)
    return None


def render(template, variables: dict):
    if not isinstance(template, str):
        return template
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(variables.get(m.group(1), m.group(0))), template)


HIGHLIGHT_JS = """(el, label) => {
  el.scrollIntoView({block: 'center', inline: 'nearest'});
  const r = el.getBoundingClientRect();
  let box = document.getElementById('__agent_hl');
  if (!box) { box = document.createElement('div'); box.id = '__agent_hl'; document.documentElement.appendChild(box); }
  Object.assign(box.style, {position: 'fixed', left: (r.left - 4) + 'px', top: (r.top - 4) + 'px',
    width: (r.width + 8) + 'px', height: (r.height + 8) + 'px', border: '3px solid #f59e0b', borderRadius: '6px',
    boxShadow: '0 0 0 4px rgba(245,158,11,.25)', zIndex: 2147483647, pointerEvents: 'none'});
  box.innerHTML = '<span style="position:absolute;top:-24px;left:-3px;background:#f59e0b;color:#111;font:600 12px system-ui;padding:2px 7px;border-radius:4px;white-space:nowrap">' + label + '</span>';
}"""


class ActionRunner:
    def __init__(self, run_id, task, steps, schema_name, options, log, set_state, store_capture):
        self.run_id, self.task, self.steps, self.schema_name = run_id, task, steps, schema_name
        self.options = options or {}
        self.log, self.set_state, self.store_capture = log, set_state, store_capture
        self.control = hub.control(run_id)
        from agents.planner.workflows import resolved_inputs
        self.vars = resolved_inputs(task)
        self.transactional = self.options.get("kind") == "transaction"
        self.pages = 0
        self.captures, self.failures = {}, {}
        self.declined = None
        self.delay = SPEED_DELAY_MS.get(self.options.get("speed", "normal"), 350) / 1000
        self.engine = self._pick_engine()
        self._pw = self._browser = self._ctx = self.page = None
        self._http_url = self._http_html = None
        self._http_client = None

    # ------------------------------------------------------------------ lifecycle
    def _pick_engine(self):
        wanted = settings.browser_engine
        needs_browser = any(s["tool"] in INTERACTIVE for s in self.steps)
        if wanted == "http" and not needs_browser:
            return "http"
        try:
            import playwright.sync_api  # noqa: F401
            return "playwright"
        except ImportError:
            if needs_browser:
                raise BrowserError("engine_unavailable", "This workflow clicks and types, which needs the Playwright browser. "
                                   "Run: python -m playwright install chromium")
            return "http"

    def __enter__(self):
        if self.engine == "playwright":
            if sys.platform == "win32":
                # uvicorn may install a selector event loop policy on Windows; Playwright needs Proactor
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            from playwright.sync_api import sync_playwright
            try:
                self._pw = sync_playwright().start()
            except Exception as e:
                raise BrowserError("engine_unavailable", f"Could not start Playwright: {e}")
            headed = bool(self.options.get("headed"))
            try:
                self._browser = self._pw.chromium.launch(headless=not headed, slow_mo=int(self.delay * 400) if headed else 0)
            except Exception as e:
                if headed:
                    self.log("warning", f"Could not open a visible browser window ({e.__class__.__name__}); running headless")
                    self._browser = self._pw.chromium.launch(headless=True)
                else:
                    self._pw.stop()
                    raise BrowserError("engine_unavailable", "Chromium is not installed. Run: python -m playwright install chromium")
            self._ctx = self._browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800}, locale="en-IN")
            self.page = self._ctx.new_page()
            self.page.set_default_timeout(settings.browser_timeout_s * 1000)
            self.page.route("**/*", self._guard_navigation)
            self.log("browser", f"Chromium started ({'visible window' if headed else 'headless'}, speed {self.options.get('speed', 'normal')})")
        else:
            self._http_client = httpx.Client(timeout=settings.browser_timeout_s, follow_redirects=True, headers={"User-Agent": USER_AGENT})
            self.log("browser", "HTTP engine started (read-only; no live frames)")
        hub.update(self.run_id, engine=self.engine)
        return self

    def __exit__(self, *exc):
        for closer in (lambda: self._ctx and self._ctx.close(), lambda: self._browser and self._browser.close(),
                       lambda: self._pw and self._pw.stop(), lambda: self._http_client and self._http_client.close()):
            try:
                closer()
            except Exception:
                pass

    def _guard_navigation(self, route):
        req = route.request
        if req.is_navigation_request() and req.frame == self.page.main_frame and not policy.is_allowed(req.url):
            self.log("policy", f"Blocked navigation to non-allowlisted {policy.domain(req.url)}", {"url": req.url})
            return route.abort("blockedbyclient")
        return route.continue_()

    # ------------------------------------------------------------------ live frames
    def _frame(self, caption, idx=None):
        if self.engine != "playwright" or not self.page:
            hub.update(self.run_id, caption=caption, url=self._http_url)
            return
        try:
            jpeg = self.page.screenshot(type="jpeg", quality=60)
            hub.frame(self.run_id, jpeg, caption, self.page.url, idx)
        except Exception:
            hub.update(self.run_id, caption=caption)

    def _highlight(self, locator, label):
        try:
            locator.evaluate(HIGHLIGHT_JS, label)
        except Exception:
            pass

    def _unhighlight(self):
        try:
            self.page.evaluate("() => { const b = document.getElementById('__agent_hl'); if (b) b.remove(); }")
        except Exception:
            pass

    def _pause(self):
        if self.delay:
            time.sleep(self.delay)

    def _locator(self, args):
        if args.get("text"):
            loc = self.page.get_by_text(render(args["text"], self.vars), exact=bool(args.get("exact"))).first
        else:
            loc = self.page.locator(args["selector"]).nth(int(args.get("nth", 0)))
        try:
            loc.wait_for(state="visible", timeout=args.get("timeout_s", 10) * 1000)
        except Exception:
            raise BrowserError("page_structure_changed", f"Element not found: {args.get('selector') or args.get('text')}")
        return loc

    def _after_nav(self):
        before = getattr(self, "_last_url", None)
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=settings.browser_timeout_s * 1000)
        except Exception:
            pass
        if not policy.is_allowed(self.page.url):
            raise BrowserError("policy_restriction", f"Page moved off the allowlist to {policy.domain(self.page.url)}")
        if self.page.url != before:
            self.pages += 1
            self._last_url = self.page.url

    # ------------------------------------------------------------------ main loop
    def run(self) -> dict:
        skip_target = None
        for i, step in enumerate(self.steps):
            tool, args, target = step["tool"], dict(step.get("args") or {}), step.get("target")
            if tool in POST_TOOLS:
                continue
            if skip_target and target == skip_target and tool != "navigate":
                hub.step_status(self.run_id, i, "skipped")
                continue
            skip_target = None
            self.control.checkpoint(on_pause=lambda: (hub.update(self.run_id, caption="Paused. Resume or step from the controls."),
                                                      self.log("control", "Paused before: " + step.get("purpose", tool))))
            hub.step_status(self.run_id, i, "running")
            try:
                getattr(self, f"_do_{tool}")(i, args, target, step)
                hub.step_status(self.run_id, i, "done")
            except StopRequested:
                hub.step_status(self.run_id, i, "stopped")
                raise
            except BrowserError as e:
                hub.step_status(self.run_id, i, "failed")
                self._frame(f"Failed: {e}", i)
                url = target or (self.page.url if self.page else self._http_url) or "?"
                self.failures[url] = {"category": e.category, "message": str(e), "step": step.get("purpose", tool)}
                self.log("error", f"Step {i + 1} ({tool}) failed: {e.category}: {e}", {"url": url, "category": e.category, "step": i})
                if self.transactional:
                    for j in range(i + 1, len(self.steps)):
                        hub.step_status(self.run_id, j, "skipped")
                    break
                skip_target = target
            except Exception as e:  # unexpected Playwright errors become visible step failures
                hub.step_status(self.run_id, i, "failed")
                msg = str(e).split("\n")[0][:300]
                url = target or (self.page.url if self.page else "?")
                self.failures[url] = {"category": "action_error", "message": msg, "step": step.get("purpose", tool)}
                self.log("error", f"Step {i + 1} ({tool}) failed: {msg}", {"url": url, "category": "action_error", "step": i})
                self._frame(f"Failed: {msg[:80]}", i)
                if self.transactional:
                    break
                skip_target = target
            finally:
                if self.engine == "playwright":
                    self._unhighlight()
            self.control.after_action()
            if self.declined is not None:
                for j in range(i + 1, len(self.steps)):
                    if self.steps[j]["tool"] not in POST_TOOLS:
                        hub.step_status(self.run_id, j, "skipped")
                break
        return {"captures": self.captures, "failures": self.failures, "vars": self.vars, "declined": self.declined,
                "pages": self.pages, "engine": self.engine}

    def revisit(self, urls):
        """Used by the reasoning loop: re-open sources that returned nothing and extract again."""
        for url in urls:
            try:
                self._do_navigate(None, {}, url, {})
                self._do_extract(None, {}, url, {})
            except BrowserError as e:
                self.failures[url] = {"category": e.category, "message": str(e), "step": "rerun"}
                self.log("error", f"Rerun failed for {url}: {e.category}", {"url": url, "category": e.category})

    # ------------------------------------------------------------------ tools
    def _do_navigate(self, i, args, target, step):
        url = render(target or args.get("url"), self.vars)
        try:
            policy.check(url, self.pages)
        except PolicyViolation as e:
            raise BrowserError("policy_restriction", str(e))
        last = None
        for attempt in range(1, settings.max_retries + 2):
            self.pages += 1
            t0 = time.time()
            try:
                if self.engine == "playwright":
                    hub.update(self.run_id, caption=f"Opening {url}", url=url)
                    try:
                        resp = self.page.goto(url, wait_until="domcontentloaded")
                    except Exception as e:
                        if "ERR_BLOCKED_BY_CLIENT" in str(e):
                            raise BrowserError("policy_restriction", "Navigation blocked by allowlist")
                        raise BrowserError("timeout" if "Timeout" in type(e).__name__ else "source_unavailable",
                                           str(e).split("\n")[0][:200], True)
                    status = resp.status if resp else 200
                else:
                    try:
                        r = self._http_client.get(url)
                    except httpx.TimeoutException:
                        raise BrowserError("timeout", "No response in time", True)
                    except httpx.HTTPError as e:
                        raise BrowserError("source_unavailable", f"Network error: {e.__class__.__name__}", True)
                    status, self._http_url, self._http_html = r.status_code, str(r.url), r.text
                err = _status_error(status)
                if err:
                    raise err
                self.log("browser", f"Opened {url} (HTTP {status}, {time.time() - t0:.1f}s, attempt {attempt})", {"url": url, "status": status})
                self._last_url = self.page.url if self.page else url
                self._frame(f"Opened {url}", i)
                return
            except BrowserError as e:
                last = e
                self.log("warning", f"{e.category} on {url}: {e} (attempt {attempt})", {"url": url, "category": e.category})
                if not e.retryable or attempt > settings.max_retries:
                    break
                time.sleep(min(2 ** (attempt - 1), 4))
        raise last

    def _do_dismiss_popups(self, i, args, target, step):
        if self.engine != "playwright":
            return
        for sel in args.get("selectors", []):
            loc = self.page.locator(sel).first
            try:
                if loc.is_visible(timeout=1200):
                    self._highlight(loc, "dismiss pop-up")
                    self._frame("Found a pop-up blocking the page", i)
                    self._pause()
                    loc.click(timeout=3000)
                    self.log("browser", f"Dismissed pop-up via '{sel}'")
                    self._unhighlight()
                    self._frame("Pop-up dismissed", i)
                    return
            except Exception:
                continue

    def _do_wait_for(self, i, args, target, step):
        sels = args.get("selectors") or [args.get("selector")]
        if self.engine == "playwright":
            try:
                self.page.wait_for_selector(", ".join(sels), timeout=args.get("timeout_s", 15) * 1000)
            except Exception:
                self.log("warning", "Expected content did not appear; extraction will flag a layout change", {"url": self.page.url})
        elif not any(BeautifulSoup(self._http_html or "", "html.parser").select_one(s) for s in sels):
            self.log("warning", "Expected content not present; extraction will flag a layout change", {"url": self._http_url})

    def _need_browser(self, tool):
        if self.engine != "playwright":
            raise BrowserError("engine_unavailable", f"'{tool}' needs the Playwright browser (python -m playwright install chromium)")

    def _do_click(self, i, args, target, step):
        self._need_browser("click")
        loc = self._locator(args)
        label = args.get("label") or "click"
        self._highlight(loc, label)
        self._frame(step.get("purpose") or f"Clicking {args.get('selector') or args.get('text')}", i)
        self._pause()
        self._unhighlight()
        loc.click()
        self._after_nav()
        self.log("browser", f"Clicked {args.get('selector') or args.get('text')}", {"url": self.page.url})
        self._frame(f"Done: {step.get('purpose') or 'clicked'}. Now on '{self.page.title()}'", i)

    def _guard_sensitive(self, loc, selector):
        attrs = loc.evaluate("e => [e.type, e.name, e.id, e.autocomplete, e.getAttribute('aria-label')].join(' ')")
        if SENSITIVE.search(f"{selector} {attrs}") or "password" in attrs:
            raise BrowserError("policy_restriction", "Refused to type into a payment, OTP or password field; a person must do this")

    def _do_fill(self, i, args, target, step):
        self._need_browser("fill")
        value = str(render(args.get("value", ""), self.vars))
        if "{{" in value:
            raise BrowserError("missing_input", f"No value provided for {value}; add it to the workflow inputs")
        loc = self._locator(args)
        self._guard_sensitive(loc, args.get("selector", ""))
        self._highlight(loc, f"type: {value[:30]}")
        self._frame(step.get("purpose") or f"Typing into {args.get('selector')}", i)
        loc.fill("")
        if loc.get_attribute("type") in ("date", "number", "time"):
            loc.fill(value)
        else:
            loc.press_sequentially(value, delay=int(40 * (self.delay / 0.35)) if self.delay else 0)
        self.log("browser", f"Typed into {args.get('selector')}", {"url": self.page.url})
        self._frame(f"Typed '{value[:40]}'", i)

    def _do_select(self, i, args, target, step):
        self._need_browser("select")
        value = str(render(args.get("value", ""), self.vars))
        if "{{" in value:
            raise BrowserError("missing_input", f"No value provided for {value}; add it to the workflow inputs")
        loc = self._locator(args)
        self._highlight(loc, f"select: {value}")
        self._frame(step.get("purpose") or f"Choosing {value}", i)
        self._pause()
        self._unhighlight()
        loc.select_option(value)
        self._after_nav()
        self.log("browser", f"Selected '{value}' in {args.get('selector')}", {"url": self.page.url})
        self._frame(f"Done: {step.get('purpose') or 'selected ' + value}", i)

    def _set_checked(self, i, args, step, checked):
        self._need_browser("check")
        loc = self._locator(args)
        if loc.is_checked() == checked:
            self.log("browser", f"{args.get('selector')} already {'checked' if checked else 'unchecked'}")
            return
        self._highlight(loc, "tick" if checked else "untick")
        self._frame(step.get("purpose") or ("Ticking " if checked else "Unticking ") + args.get("selector", ""), i)
        self._pause()
        self._unhighlight()
        loc.set_checked(checked)
        self._after_nav()
        self.log("browser", f"{'Checked' if checked else 'Unchecked'} {args.get('selector')}", {"url": self.page.url})
        self._frame(f"Done: {step.get('purpose') or args.get('selector', '')}", i)

    def _do_check(self, i, args, target, step):
        self._set_checked(i, args, step, True)

    def _do_uncheck(self, i, args, target, step):
        self._set_checked(i, args, step, False)

    def _do_press(self, i, args, target, step):
        self._need_browser("press")
        self.page.keyboard.press(args.get("key", "Enter"))
        self._after_nav()
        self._frame(f"Pressed {args.get('key', 'Enter')}", i)

    def _do_scroll(self, i, args, target, step):
        self._need_browser("scroll")
        self.page.mouse.wheel(0, int(args.get("pixels", 600)))
        self._pause()
        self._frame("Scrolled", i)

    def _html(self):
        if self.engine == "playwright":
            self._unhighlight()
            return self.page.url, self.page.content(), self.page.title()
        soup = BeautifulSoup(self._http_html or "", "html.parser")
        return self._http_url, self._http_html or "", soup.title.get_text(strip=True) if soup.title else ""

    def _do_extract(self, i, args, target, step):
        url, html, title = self._html()
        shot = None
        if self.engine == "playwright" and args.get("screenshot", True):
            shot = os.path.join(settings.snapshot_dir, self.run_id, f"evidence_{len(self.captures) + 1:03d}.png")
            os.makedirs(os.path.dirname(shot), exist_ok=True)
            try:
                self.page.screenshot(path=shot, full_page=True)
            except Exception:
                shot = None
        n = self.store_capture(url, html, title, 200, shot, args.get("schema") or self.schema_name)
        self.captures[url] = {"title": title, "records": n}
        self.vars["records_extracted"] = self.vars.get("records_extracted", 0) + n
        self._frame(f"Extracted {n} record(s) from this page", i)

    def _do_paginate(self, i, args, target, step):
        max_pages = int(args.get("max_pages", 3))
        for page_no in range(1, max_pages + 1):
            self.control.checkpoint()
            self._do_extract(i, {"schema": args.get("schema")}, target, step)
            if page_no == max_pages:
                break
            nxt_sel = args.get("next_selector", "a.next")
            if self.engine == "playwright":
                nxt = self.page.locator(nxt_sel).first
                if not nxt.count() or not nxt.is_visible():
                    self.log("browser", f"No more pages after page {page_no}")
                    break
                self._highlight(nxt, f"next page ({page_no + 1})")
                self._frame(f"Going to page {page_no + 1}", i)
                self._pause()
                self._unhighlight()
                nxt.click()
                self._after_nav()
                self.log("browser", f"Opened page {page_no + 1}", {"url": self.page.url})
            else:
                el = BeautifulSoup(self._http_html or "", "html.parser").select_one(nxt_sel)
                if not el or not el.get("href"):
                    break
                self._do_navigate(i, {}, urljoin(self._http_url, el["href"]), step)

    def _do_pick_best(self, i, args, target, step):
        self._need_browser("pick_best")
        items = self.page.locator(args["items"])
        n = items.count()
        if not n:
            raise BrowserError("page_structure_changed", f"No options found with {args['items']}")
        best, best_val = None, None
        for k in range(n):
            item = items.nth(k)
            raw = item.locator(args["value"]).first.inner_text()
            val, _ = normalize_price(raw)
            if not val:
                continue
            v = val["amount_inr"]
            if best is None or (v < best_val if args.get("strategy", "min") == "min" else v > best_val):
                best, best_val = k, v
        if best is None:
            raise BrowserError("extraction_failed", "Could not read prices to compare options")
        item = items.nth(best)
        if args.get("label_selector"):
            sels = args["label_selector"] if isinstance(args["label_selector"], list) else [args["label_selector"]]
            parts = []
            for sel in sels:
                try:
                    parts.append(item.locator(sel).first.inner_text(timeout=2000).strip())
                except Exception:
                    pass
            text = " · ".join(p for p in parts if p)
        else:
            text = item.inner_text()
            try:
                text = text.replace(item.locator(args["click"]).first.inner_text(), "")
            except Exception:
                pass
        summary = re.sub(r"\s+", " ", text).strip()[:160]
        key = args.get("save_as", "chosen_option")
        self.vars.update({key: summary, key + "_price": best_val, "chosen_price": best_val, "options_compared": n})
        self._highlight(item, f"best of {n}: ₹{best_val:,.0f}")
        self._frame(f"Compared {n} options; picking the {'cheapest' if args.get('strategy', 'min') == 'min' else 'highest'} at ₹{best_val:,.0f}", i)
        self.log("tool", f"pick_best: option {best + 1} of {n} at ₹{best_val:,.0f}: {summary}")
        self._pause()
        self._pause()
        self._unhighlight()
        item.locator(args["click"]).first.click()
        self._after_nav()
        self._frame(f"Selected. Now on {self.page.title()}", i)

    def _do_capture(self, i, args, target, step):
        name = args["name"]
        if self.engine == "playwright":
            loc = self.page.locator(args["selector"]).first
            try:
                text = loc.inner_text(timeout=5000).strip()
            except Exception:
                raise BrowserError("page_structure_changed", f"Could not read {args['selector']}")
            self._highlight(loc, f"read {name}")
            self._frame(f"Read {name}: {text[:60]}", i)
        else:
            el = BeautifulSoup(self._http_html or "", "html.parser").select_one(args["selector"])
            if not el:
                raise BrowserError("page_structure_changed", f"Could not read {args['selector']}")
            text = el.get_text(" ", strip=True)
        if args.get("kind") == "price":
            val, _ = normalize_price(text)
            self.vars[name] = f"₹ {val['amount_inr']:,.0f}" if val else text
            if val:
                self.vars[name + "_value"] = val["amount_inr"]
        else:
            self.vars[name] = text
        self.log("tool", f"Captured {name} = {self.vars[name]}")

    def _do_assert_text(self, i, args, target, step):
        _, html, _ = self._html()
        want = render(args["text"], self.vars)
        if want.lower() not in BeautifulSoup(html, "html.parser").get_text(" ").lower():
            raise BrowserError("assertion_failed", f"Expected to see '{want}' on the page")
        self._frame(f"Verified the page shows '{want}'", i)

    def _do_screenshot(self, i, args, target, step):
        if self.engine != "playwright":
            return
        shot = os.path.join(settings.snapshot_dir, self.run_id, f"evidence_{int(time.time() * 1000)}.png")
        self.page.screenshot(path=shot, full_page=True)
        url, html, title = self._html()
        self.store_capture(url, html, title, 200, shot, None)
        self._frame(args.get("caption") or "Saved evidence screenshot", i)

    def _do_approval(self, i, args, target, step):
        message = render(args.get("message", "Continue?"), self.vars)
        self._frame(f"Waiting for your approval: {message}", i)
        self.log("policy", f"Waiting for human approval: {message}")
        self.set_state("awaiting_input")
        resp = self.control.ask(message, float(args.get("timeout_s", 900)))
        self.set_state("browser_execution")
        if resp.get("approve"):
            self.log("policy", "Approved by reviewer" + (f": {resp['note']}" if resp.get("note") else ""))
            self.vars["approved"] = True
            self._frame("Approved. Continuing.", i)
        else:
            self.declined = resp.get("note") or "Declined by reviewer"
            self.vars["approved"] = False
            self.log("policy", f"Not approved: {self.declined}. Stopping before the irreversible step.")
            self._frame("Not approved. Stopped before confirming.", i)

   # ---- Aviationstack: live flight status (added) ----
def _do_fetch_api(self, i, args, target, step):
    """Live flight status from Aviationstack, passed through the normal extraction pipeline."""
    from html import escape
    from backend.services import aviationstack as av
    url = render(target or "https://api.aviationstack.com/v1/flights", self.vars)
    try:
        policy.check(url, self.pages)
    except PolicyViolation as e:
        raise BrowserError("policy_restriction", str(e))
    dep = str(render(args.get("dep_iata", ""), self.vars)).strip()
    arr = str(render(args.get("arr_iata", ""), self.vars)).strip()
    try:
        rows = av.get_flights(dep_iata=dep or None, arr_iata=arr or None, limit=int(args.get("limit", 10)))
    except av.MissingApiKey:
        raise BrowserError("missing_input", "AVIATIONSTACK_API_KEY is not set on this server")
    except av.QuotaExceeded as e:
        raise BrowserError("rate_limited_by_source", str(e))
    except av.AviationstackError as e:
        raise BrowserError("source_unavailable", str(e))
    if not rows:
        raise BrowserError("source_unavailable", "Aviationstack returned no flights for this route")
    self.pages += 1

    def t(v):
        return escape(str(v)) if v not in (None, "") else ""

    cards = "".join(
        '<article class="flight-status">'
        f'<span class="flight-no">{t(r["flight_iata"])}</span>'
        f'<span class="airline">{t(r["airline"])}</span>'
        f'<span class="route" data-route="{t(r["dep_iata"])}-{t(r["arr_iata"])}">{t(r["dep_iata"])} to {t(r["arr_iata"])}</span>'
        f'<time class="flight-date" data-date="{t(r["flight_date"])}">{t(r["flight_date"])}</time>'
        f'<span class="status">{t(r["status"])}</span>'
        f'<span class="depart">{t(r["dep_estimated"] or r["dep_scheduled"])}</span>'
        f'<span class="arrive">{t(r["arr_estimated"] or r["arr_scheduled"])}</span>'
        f'<span class="dep-delay">{r["dep_delay_min"] or 0}</span>'
        f'<span class="gate">{t(r["dep_gate"])}</span>'
        f'<span class="terminal">{t(r["dep_terminal"])}</span>'
        '</article>'
        for r in rows)
    self._http_url = url
    self._http_html = ("<html><head><title>Aviationstack flight status</title></head><body><main>"
                       + cards + "</main></body></html>")
    self.log("browser", f"Fetched {len(rows)} flights from Aviationstack "
                        f"({av.requests_used_this_month()} requests used this month)", {"url": url})
    self._do_extract(i, {"schema": args.get("schema")}, url, step)


ActionRunner._do_fetch_api = _do_fetch_api

_original_pick_engine = ActionRunner._pick_engine


def _pick_engine_with_api(self):
    """Workflows that only call an API do not need a browser."""
    if all(s["tool"] == "fetch_api" or s["tool"] in POST_TOOLS for s in self.steps):
        return "http"
    return _original_pick_engine(self)


ActionRunner._pick_engine = _pick_engine_with_api
