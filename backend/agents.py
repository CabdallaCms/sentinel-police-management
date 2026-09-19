"""Sentinel AI-agent seam (disabled by default).

HONESTY NOTE — READ BEFORE USE
------------------------------
The Sentinel backend (this revision) contains **no AI / LLM call paths**:
no prompt strings, no LLM client, no multi-agent loop ever existed in
``backend/server.py``. This module therefore does NOT extract behaviour —
it *reserves* the seam where such behaviour must live when it is built,
so that:

* all future prompts live in :data:`PROMPTS` (one registry, versioned
  here — never scattered through view code);
* all future model traffic goes through :class:`LLMConnectionHandler`
  (one place for timeouts, retries, auth and audit);
* all future routing goes through :class:`AgentRouter`
  (one place for allow-lists, step budgets and fallbacks).

Nothing in this module is called by any route today, and
:data:`AGENTS_ENABLED` defaults to ``False``. Importing this module has
zero observable effect on the API, the database or the test suite.

DESIGN CONTRACT FOR FUTURE AGENTS
---------------------------------
1. Agents are **read-mostly advisors**: they may rank, summarise or draft,
   but every write still goes through the existing ``case_views`` /
   ``auth_views`` functions with the caller's RBAC context.
2. Every agent invocation must be auditable via :func:`audit`-style rows
   (who asked, which prompt version, which model, token/cost estimate).
3. The router enforces a hard step budget (see :class:`AgentRouter`) so a
   misbehaving agent can never hang a request worker.
4. Prompts are data: register them with :func:`register_prompt` (or ship
   them in :data:`PROMPTS`) and reference them by ``name:version``.

Standard library only. Standalone — imports no other Sentinel module so
the dependency graph stays acyclic.
"""
import os

# Kill-switch. Set SENTINEL_AGENTS_ENABLED=1 to allow the router and the
# LLM handler to run. Every entry point below refuses to act while this
# is False, so a half-wired integration fails closed, not open.
AGENTS_ENABLED = os.environ.get('SENTINEL_AGENTS_ENABLED', '').strip() == '1'

# Default safety rails for the (future) multi-agent loop.
AGENT_DEFAULT_MAX_STEPS = int(os.environ.get('SENTINEL_AGENT_MAX_STEPS', '5'))
AGENT_DEFAULT_TIMEOUT_SECONDS = float(os.environ.get('SENTINEL_AGENT_TIMEOUT', '20.0'))

# ---------------------------------------------------------------------------
# Prompt registry.
#
# Prompts are versioned strings keyed by "name:version". There are no
# production prompts yet; the two entries below document the expected
# shape and are inert (nothing renders them).
# ---------------------------------------------------------------------------
PROMPTS = {
    # 'screening-summary:1': (
    #     'Summarise the checkpoint screening {record_id} for officer review. '
    #     'Facts only; flag uncertainty explicitly.'
    # ),
}


def register_prompt(name, template):
    """Register (or replace) a versioned prompt template.

    ``name`` must look like ``'screening-summary:1'``. Returns the name.
    Raises :class:`ValueError` on an empty name/template.
    """
    if not str(name or '').strip():
        raise ValueError('prompt name is required (expected "name:version")')
    if not str(template or '').strip():
        raise ValueError('prompt template must be a non-empty string')
    PROMPTS[str(name).strip()] = str(template)
    return str(name).strip()


def get_prompt(name):
    """Return the template registered under ``name``.

    Raises :class:`LookupError` when the prompt is unknown.
    """
    try:
        return PROMPTS[str(name).strip()]
    except KeyError:
        raise LookupError('unknown prompt: %r' % (name,))


class LLMConnectionError(Exception):
    """Raised when the LLM backend cannot serve a completion."""


class LLMConnectionHandler:
    """Single choke point for all future model traffic.

    Configuration is environment-driven so no secret is ever hard-coded:

    * ``SENTINEL_LLM_BASE_URL`` — chat-completions endpoint (https).
    * ``SENTINEL_LLM_API_KEY``  — bearer credential (never logged).
    * ``SENTINEL_LLM_MODEL``    — model id (default ``'unset-model'``).
    * ``SENTINEL_AGENT_TIMEOUT``— per-request timeout in seconds.

    Today :meth:`complete` always raises :class:`LLMConnectionError`
    because no provider is wired; wire exactly one provider here when the
    programme approves AI assistance.
    """

    def __init__(self, base_url=None, api_key=None, model=None, timeout=None):
        self.base_url = base_url or os.environ.get('SENTINEL_LLM_BASE_URL', '')
        self.api_key = api_key or os.environ.get('SENTINEL_LLM_API_KEY', '')
        self.model = model or os.environ.get('SENTINEL_LLM_MODEL', 'unset-model')
        self.timeout = float(timeout if timeout is not None
                             else AGENT_DEFAULT_TIMEOUT_SECONDS)

    @property
    def is_configured(self):
        """True only when an endpoint, a credential and a model are set."""
        return bool(self.base_url and self.api_key
                    and self.model != 'unset-model')

    def complete(self, prompt_name, variables=None, system=None):
        """Render ``prompt_name`` and request one completion.

        Raises :class:`LLMConnectionError` while agents are disabled or no
        provider is configured. Returns a ``dict`` with ``text``,
        ``model``, ``prompt`` and ``usage`` once a provider is wired.
        """
        if not AGENTS_ENABLED:
            raise LLMConnectionError(
                'agents are disabled (set SENTINEL_AGENTS_ENABLED=1 to enable)')
        template = get_prompt(prompt_name)  # LookupError on unknown prompt
        try:
            rendered = template.format(**(variables or {}))
        except KeyError as e:
            raise LLMConnectionError('prompt %r is missing variable %s'
                                     % (prompt_name, e))
        if not self.is_configured:
            raise LLMConnectionError(
                'no LLM provider configured (need SENTINEL_LLM_BASE_URL, '
                'SENTINEL_LLM_API_KEY and SENTINEL_LLM_MODEL)')
        # -- provider call goes here (exactly one implementation) --------
        # Example shape of the future return value:
        #   return {'text': ..., 'model': self.model,
        #           'prompt': prompt_name, 'usage': {...}}
        raise LLMConnectionError(
            'no LLM provider is wired in this revision; refusing to call '
            'prompt %r with model %r (rendered %d chars)'
            % (prompt_name, self.model, len(rendered)))

    def __repr__(self):  # pragma: no cover - never leaks the key
        return ('LLMConnectionHandler(model=%r, base_url=%r, configured=%s)'
                % (self.model, self.base_url or '(unset)',
                   self.is_configured))


class AgentRouter:
    """Routes a named task to a registered agent callable.

    An agent callable receives ``(payload, context)`` and returns a
    JSON-serialisable ``dict``. ``context`` always carries the handler
    plus the RBAC snapshot (``user``, ``modules``, ``is_admin``) so an
    agent can never silently exceed the caller's permissions.

    The router itself performs no I/O; :meth:`run_loop` simply chains at
    most ``max_steps`` agent calls, threading each result into the next
    payload. While :data:`AGENTS_ENABLED` is False every entry point
    raises :class:`LLMConnectionError` (fail closed).
    """

    def __init__(self, handler=None, max_steps=None):
        self.handler = handler or LLMConnectionHandler()
        self.max_steps = int(max_steps if max_steps is not None
                             else AGENT_DEFAULT_MAX_STEPS)
        self._agents = {}

    def register(self, name, func):
        """Register ``func`` as the agent called ``name``. Returns ``func``."""
        if not str(name or '').strip():
            raise ValueError('agent name is required')
        if not callable(func):
            raise ValueError('agent %r must be callable' % (name,))
        self._agents[str(name).strip()] = func
        return func

    @property
    def agent_names(self):
        """Sorted names of the registered agents."""
        return sorted(self._agents)

    def _guard(self, name):
        if not AGENTS_ENABLED:
            raise LLMConnectionError(
                'agents are disabled (set SENTINEL_AGENTS_ENABLED=1 to enable)')
        try:
            return self._agents[str(name).strip()]
        except KeyError:
            raise LookupError('unknown agent: %r (registered: %s)'
                              % (name, ', '.join(self.agent_names) or 'none'))

    def route(self, name, payload=None, context=None):
        """Run agent ``name`` once and return its result dict."""
        agent = self._guard(name)
        result = agent(payload or {}, dict(context or {},
                                           llm=self.handler,
                                           agent=name))
        if not isinstance(result, dict):
            raise LLMConnectionError(
                'agent %r must return a dict, got %s'
                % (name, type(result).__name__))
        return result

    def run_loop(self, plan, payload=None, context=None):
        """Run a multi-agent plan: ``[agent_name, ...]`` in order.

        Each step receives the previous step's result under
        ``payload['previous']``. Stops after ``max_steps`` steps with
        :class:`LLMConnectionError` instead of looping forever. Returns
        ``{'steps': [...], 'result': <last result>}``.
        """
        plan = list(plan or [])
        if not plan:
            raise ValueError('plan must list at least one agent name')
        if len(plan) > self.max_steps:
            raise LLMConnectionError(
                'plan has %d steps, budget is %d'
                % (len(plan), self.max_steps))
        ctx = dict(context or {}, llm=self.handler)
        seen = []
        current = dict(payload or {})
        for name in plan:
            result = self.route(name, current, ctx)
            seen.append({'agent': name, 'result': result})
            current = dict(current, previous=result)
        return {'steps': seen, 'result': seen[-1]['result']}


# Process-wide default router. Views (in a future revision) should use
# ``default_router().route(...)`` rather than constructing routers inline.
_DEFAULT_ROUTER = None


def default_router():
    """Return the process-wide :class:`AgentRouter` (created on demand)."""
    global _DEFAULT_ROUTER
    if _DEFAULT_ROUTER is None:
        _DEFAULT_ROUTER = AgentRouter()
    return _DEFAULT_ROUTER


def agents_health():
    """Inert status snapshot for future ``/api/agents/health`` wiring.

    Today this always reports disabled with zero agents; it is imported
    by :mod:`server` only so the symbol exists for that future route.
    Not wired to any URL in this revision.
    """
    handler = LLMConnectionHandler()
    return {
        'enabled': bool(AGENTS_ENABLED),
        'agents': default_router().agent_names,
        'llm_configured': bool(handler.is_configured),
        'model': handler.model,
        'max_steps': AGENT_DEFAULT_MAX_STEPS,
    }
