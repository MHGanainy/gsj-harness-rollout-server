"""SERVER — `gsj-rollout serve | submit` (ADR-0008 §4).

`serve` is the smallest honest thing: it starts OUR receiver, renders
Polar's topology from the one YAML, and prints the two Polar commands
for the operator — no process supervisor (the gsj-collect lesson was
observability and bounded exit, not lifecycle ownership). `submit`
renders one TaskRequest from the config plus the task triple, waits with
bounded progress output, re-checks client-side, and exits with stated
codes. No signal handler is installed at import (embeddability) —
`serve()` installs and owns them for its own lifetime only.

Exit codes: 0 all episodes collected; 1 not all episodes collected
(rejected, ERROR/TIMEOUT sessions, or the bounded wait expired); 2 config
or usage error; 3 rollout server unreachable or answered an HTTP error.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading

import httpx
import yaml

from . import config as config_mod
from .client import RolloutClient, partition_session_results
from .receiver import Receiver

EXIT_OK, EXIT_PARTIAL, EXIT_CONFIG, EXIT_UNREACHABLE = 0, 1, 2, 3


def _load(config_path: str) -> config_mod.RunConfig:
    try:
        return config_mod.load_config(config_path)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"gsj-rollout: {exc}") from exc


def serve(args: argparse.Namespace) -> int:
    try:
        cfg = _load(args.config)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return EXIT_CONFIG
    topology_path = os.path.join(os.path.dirname(os.path.abspath(args.config)),
                                 "topology.rendered.yaml")
    with open(topology_path, "w") as handle:
        yaml.safe_dump(config_mod.render_topology(cfg), handle, sort_keys=False)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"topology rendered: {topology_path}")
    print("run Polar's two processes yourself (not supervised here):")
    print(f"  PYTHONPATH={repo_root} vendor/polar/.venv/bin/polar serve_rollout -c {topology_path}")
    print(f"  {cfg.estate.mcp_token_secret_env}=<secret> PYTHONPATH={repo_root} "
          f"vendor/polar/.venv/bin/polar serve_gateway -c {topology_path}")
    print(f"receiver callback endpoint: {cfg.receiver.base_url}/callbacks/session_result")
    print(f"traces -> {cfg.receiver.traces_dir}  quarantine -> {cfg.receiver.resolved_quarantine_dir}")
    if args.render_only:
        return EXIT_OK

    receiver = Receiver(cfg.receiver.host, cfg.receiver.port,
                        cfg.receiver.traces_dir, cfg.receiver.resolved_quarantine_dir)
    print(f"receiver listening on {cfg.receiver.host}:{receiver.port}")
    stop = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stop.set())
                for sig in (signal.SIGINT, signal.SIGTERM)}
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    try:
        stop.wait()
    finally:
        receiver.shutdown()
        thread.join(timeout=5.0)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(f"receiver stopped: accepted={receiver.accepted} rejected={receiver.rejected}")
    return EXIT_OK


def submit(args: argparse.Namespace) -> int:
    try:
        cfg = _load(args.config)
        if args.prompt_file:
            with open(args.prompt_file) as handle:
                instruction = handle.read()
        else:
            instruction = args.prompt
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return EXIT_CONFIG
    except OSError as exc:
        print(f"gsj-rollout: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    request = config_mod.render_task_request(
        cfg, task_id=args.task_id, instruction=instruction, case_id=args.case,
        timestep=args.timestep, episodes=args.episodes, timeout_seconds=args.timeout,
    )
    client = RolloutClient(cfg.polar.rollout.base_url, poll_interval_s=args.poll_interval)
    seen: list[int] = [-1]

    def progress(status: dict) -> None:  # bounded: one line per change, not per poll
        if status["completed_sessions"] != seen[0]:
            seen[0] = status["completed_sessions"]
            print(f"task {args.task_id}: {status['completed_sessions']}/"
                  f"{status['total_sessions']} sessions terminal")

    try:
        task_id = client.submit(request)
        results = client.wait(task_id, timeout_s=args.timeout + args.grace, on_poll=progress)
    except httpx.HTTPError as exc:  # transport failures AND 4xx/5xx responses
        print(f"gsj-rollout: rollout server unreachable or errored at "
              f"{cfg.polar.rollout.base_url}: {exc}", file=sys.stderr)
        return EXIT_UNREACHABLE
    except TimeoutError as exc:
        print(f"gsj-rollout: {exc}", file=sys.stderr)
        return EXIT_PARTIAL

    accepted, rejected = partition_session_results(results)
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        for result in accepted:
            with open(os.path.join(args.out, f"{result['session_id']}.json"), "w") as handle:
                json.dump(result, handle)
    for result, findings in rejected:
        print(f"rejected {result.get('session_id')}: {findings}")
    print(f"collected {len(accepted)}/{args.episodes} episodes"
          + (f" -> {args.out}" if args.out else ""))
    return EXIT_OK if len(accepted) == args.episodes else EXIT_PARTIAL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gsj-rollout",
        description="Rollout server for the gsj corpus: task -> sandbox -> agent -> trace.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="start the receiver; render topology; print the Polar commands")
    serve_p.add_argument("--config", required=True, help="the one YAML (config.py)")
    serve_p.add_argument("--render-only", action="store_true",
                         help="render topology, print commands, exit")
    serve_p.set_defaults(func=serve)

    submit_p = sub.add_parser(
        "submit", help="submit a task triple; wait; collect validated traces",
        epilog=config_mod.COLLECT_SEMANTICS + "\n\nExit codes: 0 all collected; "
        "1 not all collected (rejected/errored/timed out); 2 config/usage error; "
        "3 server unreachable or HTTP error.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    submit_p.add_argument("--config", required=True, help="the one YAML (config.py)")
    submit_p.add_argument("--case", required=True, help="case repo name, e.g. case_0001")
    submit_p.add_argument("--timestep", required=True, type=int, help="T — branch and cutoff claim")
    prompt = submit_p.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt", help="the instruction text")
    prompt.add_argument("--prompt-file", help="file containing the instruction text")
    submit_p.add_argument("--episodes", type=int, default=1,
                          help="ATTEMPTS to run (num_samples) — see collect-N semantics below")
    submit_p.add_argument("--task-id", default="gsj-task", help="Polar task id")
    submit_p.add_argument("--timeout", type=float, default=900.0, help="per-task timeout_seconds")
    submit_p.add_argument("--grace", type=float, default=120.0,
                          help="extra wait beyond --timeout before giving up (callback grace)")
    submit_p.add_argument("--poll-interval", type=float, default=2.0, help="poll period seconds")
    submit_p.add_argument("--out", default=None,
                          help="directory for collected SessionResult JSON (default: report only)")
    submit_p.set_defaults(func=submit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
